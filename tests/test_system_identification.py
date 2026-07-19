from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from sim2claw.recorded_replay import (
    load_recorded_episode,
    load_sysid_config,
    nominal_parameter_values,
    sha256_file,
)
from sim2claw.system_identification import (
    SystemIdentificationError,
    _local_least_squares,
    fit_parameter_stage,
    freeze_episode_split,
    held_out_improvement_gate,
    inspect_recording_catalog_inputs,
    mujoco_sysid_capability,
    run_system_identification,
    validate_split_manifest,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "sysid"
CONFIG_PATH = FIXTURE_ROOT / "smooth_slider_sysid_v1.json"
EPISODE_PATH = FIXTURE_ROOT / "recorded_slider_episode_v1.json"
PHYSICAL_CATALOG = (
    REPO_ROOT / "configs" / "data" / "physical_pawn_move_catalog_20260719.json"
)


class SystemIdentificationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_sysid_config(CONFIG_PATH)
        self.episode = load_recorded_episode(EPISODE_PATH, self.config)

    def test_pinned_official_sysid_surface_is_importable_and_exercised(self) -> None:
        capability = mujoco_sysid_capability(exercise=True)
        self.assertEqual(capability["version"], "3.10.0")
        self.assertTrue(capability["compatible"])
        self.assertTrue(capability["official_surface_exercised"])
        self.assertEqual(capability["missing_exports"], [])
        self.assertLessEqual(capability["exercise"]["absolute_error"], 1e-8)

    def test_version_mismatched_official_surface_fails_closed_actionably(self) -> None:
        with patch(
            "sim2claw.system_identification.importlib.metadata.version",
            return_value="3.9.0",
        ):
            capability = mujoco_sysid_capability(exercise=True)
        self.assertFalse(capability["compatible"])
        self.assertFalse(capability["official_surface_exercised"])
        self.assertIsNone(capability["exercise"])
        self.assertIn("expected 3.10.0", capability["actionable_resolution"])

    def test_official_adapter_runs_bounded_multistart_and_reports_ensemble(self) -> None:
        report = fit_parameter_stage(
            self.config["parameter_stages"][0],
            [self.episode],
            self.config,
            nominal_parameter_values(self.config),
            backend="official",
            model_base_directory=FIXTURE_ROOT,
        )
        self.assertEqual(report["status"], "optimized")
        self.assertEqual(report["best_backend"], "mujoco.sysid.optimize")
        self.assertEqual(report["multi_start_count"], 3)
        self.assertGreaterEqual(report["near_equivalent"]["fit_count"], 1)
        self.assertFalse(report["near_equivalent"]["unique_fit_claimed"])
        distribution = report["near_equivalent"]["parameter_distribution"]
        self.assertIn("tool_offset_x_m", distribution)
        self.assertGreaterEqual(
            distribution["tool_offset_x_m"]["maximum"],
            distribution["tool_offset_x_m"]["minimum"],
        )

    def test_auto_backend_falls_back_deterministically_for_smooth_parameters(self) -> None:
        reports = []
        for _ in range(2):
            with patch(
                "sim2claw.system_identification._official_least_squares",
                side_effect=RuntimeError("fixture official surface unavailable"),
            ):
                reports.append(
                    fit_parameter_stage(
                        self.config["parameter_stages"][0],
                        [self.episode],
                        self.config,
                        nominal_parameter_values(self.config),
                        backend="auto",
                        model_base_directory=FIXTURE_ROOT,
                    )
                )
        first, second = reports
        self.assertEqual(first["status"], "optimized")
        self.assertEqual(first["best_backend"], "local_bounded_gauss_newton")
        self.assertEqual(first["best_parameters"], second["best_parameters"])
        self.assertEqual(first["best_train_loss"], second["best_train_loss"])
        self.assertTrue(
            all(
                "fixture official surface unavailable"
                in attempt["official_attempt_failure"]
                for attempt in first["attempts"]
            )
        )

    def test_contact_stage_rejects_missing_pawn_and_contact_data(self) -> None:
        report = fit_parameter_stage(
            self.config["parameter_stages"][2],
            [self.episode],
            self.config,
            nominal_parameter_values(self.config),
            backend="auto",
            model_base_directory=FIXTURE_ROOT,
        )
        self.assertEqual(report["status"], "rejected_no_data")
        self.assertTrue(report["parameters_unchanged"])
        self.assertIn("measured pawn or contact", report["reason"])

    def test_local_fallback_rejects_non_smooth_contact_parameter(self) -> None:
        descriptor = self.config["parameter_stages"][2]["parameters"][0]
        with self.assertRaisesRegex(SystemIdentificationError, "non-smooth"):
            _local_least_squares(
                [descriptor],
                np.asarray([1.0]),
                lambda value: value - 1.0,
                maximum_iterations=2,
                relative_step=1e-4,
            )

    def test_non_improving_held_out_candidate_cannot_claim_success(self) -> None:
        equal = held_out_improvement_gate(
            0.25,
            0.25,
            self.config["held_out_acceptance"],
        )
        worse = held_out_improvement_gate(
            0.25,
            0.30,
            self.config["held_out_acceptance"],
        )
        self.assertFalse(equal["passed"])
        self.assertFalse(worse["passed"])
        self.assertEqual(
            equal["claim"],
            "calibration_success_rejected_no_held_out_improvement",
        )

    def test_leave_one_column_out_is_whole_episode_and_leakage_is_rejected(self) -> None:
        hashes = [f"{index:064x}" for index in range(1, 5)]
        catalog = {
            "catalog_id": "fixture-catalog",
            "episodes": [
                {
                    "recording_id": f"episode-{index}",
                    "source_path": f"datasets/episode-{index}",
                    "samples_sha256": hashes[index],
                    "source_square": source,
                    "destination_square": destination,
                    "proof_class": "synthetic",
                    "assets": {"samples": f"datasets/episode-{index}/samples.jsonl"},
                }
                for index, (source, destination) in enumerate(
                    [("a1", "a2"), ("b1", "c1"), ("c2", "d2"), ("e1", "e2")]
                )
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog_path = root / "catalog.json"
            output_path = root / "split.json"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            manifest = freeze_episode_split(
                catalog_path,
                CONFIG_PATH,
                output_path,
                strategy="leave_one_column_out",
                held_out_column="c",
            )
            assignments = {
                entry["episode_id"]: entry["split"]
                for entry in manifest["episodes"]
            }
            self.assertEqual(assignments["episode-0"], "train")
            self.assertEqual(assignments["episode-1"], "held_out")
            self.assertEqual(assignments["episode-2"], "held_out")
            self.assertEqual(assignments["episode-3"], "train")
            leaked = copy.deepcopy(manifest)
            leaked.pop("manifest_path")
            leaked.pop("manifest_sha256")
            leaked["episodes"][0]["source_samples_sha256"] = leaked["episodes"][1][
                "source_samples_sha256"
            ]
            with self.assertRaisesRegex(SystemIdentificationError, "leakage"):
                validate_split_manifest(leaked)
            unguarded = copy.deepcopy(manifest)
            unguarded["leakage_guards"]["row_level_split_forbidden"] = False
            with self.assertRaisesRegex(SystemIdentificationError, "leakage guards"):
                validate_split_manifest(unguarded)
            incomplete_catalog = copy.deepcopy(catalog)
            incomplete_catalog["episodes"][0]["destination_square"] = None
            incomplete_path = root / "incomplete-catalog.json"
            incomplete_path.write_text(
                json.dumps(incomplete_catalog), encoding="utf-8"
            )
            with self.assertRaisesRegex(
                SystemIdentificationError,
                "source and destination column metadata",
            ):
                freeze_episode_split(
                    incomplete_path,
                    CONFIG_PATH,
                    root / "incomplete-split.json",
                    strategy="leave_one_column_out",
                    held_out_column="c",
                )

    def test_physical_catalog_report_is_exact_about_missing_payloads_and_observables(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = inspect_recording_catalog_inputs(
                PHYSICAL_CATALOG,
                repo_root=Path(temporary),
            )
            self.assertEqual(report["episode_count"], 18)
            self.assertEqual(report["joint_replay_ready_episode_count"], 0)
            self.assertEqual(report["metadata_conflict_episode_count"], 11)
            self.assertEqual(report["missing_required_asset_count"], 36)
            self.assertEqual(
                report["aggregate_observable_status"]["pawn_position"],
                "unavailable",
            )
            self.assertEqual(report["inspection_scope"]["kind"], "explicit_repo_root")
            self.assertTrue(report["inspection_scope"]["provided_root_inspected"])
            self.assertFalse(
                report["inspection_scope"]["canonical_checkout_inspected"]
            )
            self.assertEqual(
                report["coordinator_reported_canonical_state"][
                    "physical_recording_directories_recovered"
                ],
                18,
            )
            self.assertEqual(
                report["coordinator_reported_canonical_state"][
                    "catalog_bound_hashes_verified"
                ],
                54,
            )
            self.assertFalse(
                report["coordinator_reported_canonical_state"][
                    "verified_by_this_receipt"
                ]
            )
            self.assertFalse(report["video_used_for_metric_observables"])
            self.assertFalse(
                report["endpoint_visual_proposals_used_for_metric_observables"]
            )
            self.assertFalse(report["contact_object_stage_ready"])
            self.assertFalse(report["joint_timing_replay_ready"])
            self.assertFalse(report["timing_control_fit_ready"])
            self.assertFalse(report["calibration_ready"])
            self.assertEqual(report["claim"], "missing_input_manifest_only")
            self.assertEqual(
                report["current_root_catalog_integrity"][
                    "catalog_bound_asset_count"
                ],
                54,
            )
            self.assertEqual(
                report["current_root_catalog_integrity"][
                    "verified_catalog_bound_hash_count"
                ],
                0,
            )
            self.assertIn(
                "--inspection-scope canonical_checkout",
                report["post_cherry_pick_canonical_commands"][2],
            )
            self.assertIn(
                "uv run --frozen sim2claw sysid-fit",
                report["post_cherry_pick_canonical_commands"][3],
            )

    def test_input_report_recognizes_present_joint_payloads_without_inventing_contact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            recording = root / "datasets" / "recording-001"
            recording.mkdir(parents=True)
            (recording / "samples.jsonl").write_text("{}\n", encoding="utf-8")
            samples_sha256 = sha256_file(recording / "samples.jsonl")
            (recording / "recording_receipt.json").write_text(
                json.dumps(
                    {
                        "mode": "physical_follower",
                        "recording_id": "recording-001",
                        "samples_sha256": samples_sha256,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (recording / "overhead.mp4").write_bytes(b"fixture video bytes")
            catalog = {
                "catalog_id": "present-payload-fixture",
                "episodes": [
                    {
                        "recording_id": "recording-001",
                        "proof_class": "physical_read_only",
                        "metadata_status": "consistent_folder_label_and_receipt",
                        "assets": {
                            "receipt": (
                                "datasets/recording-001/recording_receipt.json"
                            ),
                            "samples": "datasets/recording-001/samples.jsonl",
                            "overhead_video": "datasets/recording-001/overhead.mp4",
                        },
                        "receipt_sha256": sha256_file(
                            recording / "recording_receipt.json"
                        ),
                        "samples_sha256": samples_sha256,
                        "overhead_video_sha256": sha256_file(
                            recording / "overhead.mp4"
                        ),
                    }
                ],
            }
            catalog_path = root / "catalog.json"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            report = inspect_recording_catalog_inputs(
                catalog_path,
                repo_root=root,
                inspection_scope="canonical_checkout",
            )
            self.assertEqual(report["joint_replay_ready_episode_count"], 1)
            self.assertEqual(report["missing_required_asset_count"], 0)
            self.assertTrue(report["joint_timing_replay_ready"])
            self.assertTrue(report["timing_control_fit_ready"])
            self.assertFalse(report["geometry_stage_ready"])
            self.assertFalse(report["contact_object_stage_ready"])
            self.assertFalse(report["calibration_ready"])
            self.assertEqual(report["claim"], "joint_timing_replay_inputs_present")
            self.assertEqual(
                report["aggregate_observable_status"]["joint_position"],
                "available_for_all_episodes",
            )
            self.assertEqual(
                report["aggregate_observable_status"]["contact_active"],
                "unavailable",
            )
            self.assertFalse(report["contact_object_stage_ready"])
            self.assertEqual(report["inspection_scope"]["kind"], "canonical_checkout")
            self.assertTrue(
                report["inspection_scope"]["canonical_checkout_inspected"]
            )
            self.assertTrue(report["inspection_scope"]["provided_root_inspected"])
            self.assertNotIn("coordinator_reported_canonical_state", report)
            self.assertEqual(
                report["current_root_catalog_integrity"][
                    "verified_catalog_bound_hash_count"
                ],
                3,
            )
            self.assertTrue(
                report["current_root_catalog_integrity"][
                    "all_catalog_bound_hashes_verified"
                ]
            )
            (recording / "samples.jsonl").write_text(
                '{"tampered":true}\n', encoding="utf-8"
            )
            tampered = inspect_recording_catalog_inputs(
                catalog_path,
                repo_root=root,
                inspection_scope="canonical_checkout",
            )
            self.assertEqual(tampered["joint_replay_ready_episode_count"], 0)
            self.assertEqual(tampered["mismatched_required_asset_count"], 1)
            self.assertFalse(tampered["joint_timing_replay_ready"])
            self.assertFalse(tampered["calibration_ready"])

    def test_end_to_end_receipt_does_not_claim_full_calibration_without_contact_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            train_payload = json.loads(EPISODE_PATH.read_text(encoding="utf-8"))
            held_payload = copy.deepcopy(train_payload)
            held_payload["episode_id"] = "fixture-slider-held-out-001"
            held_payload["column"] = "d"
            held_payload["proof_class"] = "physical_read_only_contract_fixture"
            held_payload["proof_class_category"] = "physical_read_only"
            train_path = root / "train.json"
            held_path = root / "held.json"
            train_path.write_text(json.dumps(train_payload), encoding="utf-8")
            held_path.write_text(json.dumps(held_payload), encoding="utf-8")
            manifest = {
                "schema_version": "sim2claw.sysid_episode_split.v1",
                "split_id": "fixture-end-to-end",
                "frozen": True,
                "owner": "fixture_evaluator",
                "unit": "whole_episode",
                "strategy": "deterministic_hash",
                "held_out_column": None,
                "holdout_fraction": 0.5,
                "seed": "fixture",
                "source_catalog": {
                    "path": "fixture",
                    "sha256": "f" * 64,
                    "catalog_id": "fixture"
                },
                "sysid_config": {
                    "path": str(CONFIG_PATH),
                    "sha256": sha256_file(CONFIG_PATH),
                    "config_id": self.config["config_id"]
                },
                "split_counts": {"train": 1, "held_out": 1},
                "episodes": [
                    {
                        "episode_id": train_payload["episode_id"],
                        "source_path": str(train_path),
                        "source_samples_sha256": sha256_file(train_path),
                        "split": "train"
                    },
                    {
                        "episode_id": held_payload["episode_id"],
                        "source_path": str(held_path),
                        "source_samples_sha256": sha256_file(held_path),
                        "split": "held_out"
                    }
                ],
                "leakage_guards": {
                    "episode_id_disjoint": True,
                    "source_samples_sha256_disjoint": True,
                    "row_level_split_forbidden": True
                },
                "created_at": "2026-07-19T00:00:00+00:00"
            }
            manifest_path = root / "split.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            receipt = run_system_identification(
                manifest_path,
                config_path=CONFIG_PATH,
                output_directory=root / "fit",
                backend="official",
            )
            self.assertFalse(receipt["calibration_success"])
            self.assertFalse(receipt["parameters_promoted"])
            self.assertEqual(receipt["stages"][2]["status"], "rejected_no_data")
            self.assertTrue(receipt["official_sysid_exercised"])
            self.assertTrue(receipt["proof"]["physical_read_only_input"])
            self.assertFalse(receipt["proof"]["physical_task"])
            self.assertTrue((root / "fit" / "fit_receipt.json").is_file())
            self.assertTrue((root / "fit" / "baseline_metrics.json").is_file())
            self.assertTrue((root / "fit" / "candidate_metrics.json").is_file())


if __name__ == "__main__":
    unittest.main()

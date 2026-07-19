from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from sim2claw.recorded_replay import (
    ReplayContractError,
    ReplayRangeError,
    canonical_json_sha256,
    load_recorded_episode,
    load_sysid_config,
    nominal_parameter_values,
    sha256_file,
    simulate_and_align,
    write_replay_receipt,
)
from sim2claw.system_identification import (
    SystemIdentificationError,
    _local_least_squares,
    _hash_fraction,
    _split_authority_from_config,
    _split_assignment_digest,
    fit_parameter_stage,
    freeze_episode_split,
    held_out_improvement_gate,
    inspect_recording_catalog_inputs,
    load_manifest_episodes,
    load_split_manifest,
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


def _approved_physical_config(root: Path) -> Path:
    payload = json.loads(
        (REPO_ROOT / "configs/sysid/recorded_action_sysid_v1.json").read_text(
            encoding="utf-8"
        )
    )
    transform = payload["physical_adapter"]["joint_transform"]
    transform["calibration_approved"] = True
    transform["review_status"] = "approved_synthetic_fixture_only"
    transform["review"] = {
        "reviewer": "synthetic_test_evaluator",
        "reviewed_at": "2026-07-19T00:00:00+00:00",
        "decision_id": "synthetic-transform-fixture-v1",
        "evidence_sha256": "e" * 64,
    }
    payload["physical_adapter"]["joint_transform_sha256"] = canonical_json_sha256(
        transform
    )
    payload["split"].update(
        {
            "owner": "fixture_evaluator",
            "holdout_fraction": 0.5,
            "seed": "fixture",
        }
    )
    path = root / "approved-sysid-config.json"
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _physical_fixture(
    root: Path,
    *,
    rows: list[dict[str, object]],
    recording_id: str = "recording-001",
    metadata_status: str = "consistent_folder_label_and_receipt",
) -> tuple[Path, Path, dict[str, object]]:
    recording = root / "datasets" / recording_id
    recording.mkdir(parents=True)
    samples_path = recording / "samples.jsonl"
    samples_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    samples_sha256 = sha256_file(samples_path)
    receipt_path = recording / "recording_receipt.json"
    receipt_path.write_text(
        json.dumps(
            {
                "mode": "physical_follower",
                "recording_id": recording_id,
                "sample_count": len(rows),
                "sample_hz": 20,
                "samples_sha256": samples_sha256,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    video_path = recording / "overhead.mp4"
    video_path.write_bytes(b"fixture video bytes")
    catalog = {
        "catalog_id": "present-payload-fixture",
        "episodes": [
            {
                "recording_id": recording_id,
                "source_path": f"datasets/{recording_id}",
                "proof_class": "physical_teleoperation_source_unqualified",
                "metadata_status": metadata_status,
                "source_square": "b1",
                "destination_square": "b2",
                "assets": {
                    "receipt": f"datasets/{recording_id}/recording_receipt.json",
                    "samples": f"datasets/{recording_id}/samples.jsonl",
                    "overhead_video": f"datasets/{recording_id}/overhead.mp4",
                },
                "receipt_sha256": sha256_file(receipt_path),
                "samples_sha256": samples_sha256,
                "overhead_video_sha256": sha256_file(video_path),
            }
        ],
    }
    catalog_path = root / "catalog.json"
    catalog_path.write_text(json.dumps(catalog, sort_keys=True), encoding="utf-8")
    return catalog_path, recording, catalog


def _valid_physical_rows(values: list[float] | None = None) -> list[dict[str, object]]:
    joint_values = values or [0.0, 0.0, 0.0, 0.0, 0.0, 20.0]
    return [
        {
            "schema_version": "sim2claw.physical_teleoperation_sample.v1",
            "timestamp_monotonic_seconds": index * 0.05,
            "follower_command_degrees": joint_values,
            "follower_actual_position_degrees": joint_values,
        }
        for index in range(2)
    ]


def _physical_provenance(
    catalog_path: Path,
    catalog: dict[str, object],
) -> dict[str, object]:
    entry = catalog["episodes"][0]
    return {
        "episode_id": entry["recording_id"],
        "chain_complete": True,
        "catalog": {
            "kind": "repo_relative",
            "path": catalog_path.name,
            "_runtime_path": str(catalog_path),
            "catalog_id": catalog["catalog_id"],
            "sha256": sha256_file(catalog_path),
        },
        "recording_receipt": {
            "kind": "repo_relative",
            "path": entry["assets"]["receipt"],
            "sha256": entry["receipt_sha256"],
        },
        "samples": {
            "kind": "repo_relative",
            "path": entry["assets"]["samples"],
            "sha256": entry["samples_sha256"],
        },
    }


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
        self.assertTrue(report["sensitivity"]["all_parameters_identifiable"])
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

    def test_geometry_parameter_is_unidentifiable_from_pawn_only_observations(self) -> None:
        payload = json.loads(EPISODE_PATH.read_text(encoding="utf-8"))
        payload["initial_object_state"] = {
            "status": "available",
            "body_name": "fixture_object",
            "free_joint_name": "fixture_object_free",
            "frame": "world",
            "position_unit": "m",
            "orientation_convention": "wxyz_unit_quaternion",
            "linear_velocity_unit": "m/s",
            "angular_velocity_unit": "rad/s",
            "position": [0.2, 0.0, 0.2],
            "quaternion_wxyz": [1.0, 0.0, 0.0, 0.0],
            "linear_velocity": [0.0, 0.0, 0.0],
            "angular_velocity": [0.0, 0.0, 0.0],
            "measurement_provenance": {
                "source_id": "pawn-only-fixture",
                "measurement_method": "synthetic_exact_state",
                "sha256": "a" * 64,
            },
        }
        payload["unavailable_observables"]["end_effector_position"] = (
            "regression intentionally has no measured end-effector position"
        )
        payload["unavailable_observables"].pop("pawn_position")
        for sample in payload["samples"]:
            sample["measured"].pop("end_effector_position_m")
            sample["measured"]["pawn_position_m"] = [0.2, 0.0, 0.2]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "pawn-only.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            episode = load_recorded_episode(path, self.config)
            config = copy.deepcopy(self.config)
            config["parameter_stages"][0]["requires_any_observable"] = [
                "pawn_position"
            ]
            report = fit_parameter_stage(
                config["parameter_stages"][0],
                [episode],
                config,
                nominal_parameter_values(config),
                backend="official",
                model_base_directory=FIXTURE_ROOT,
            )
        self.assertEqual(report["status"], "skipped_unidentifiable")
        self.assertFalse(report["data"]["parameter_dependency_ready"])
        self.assertTrue(report["parameters_unchanged"])
        missing_binding = replace(
            episode,
            initial_object_state={
                "status": "unavailable",
                "reason": "regression removes the object binding",
            },
        )
        contact_config = copy.deepcopy(self.config)
        contact_config["loss"]["weights"]["pawn_position"] = 1.0
        contact_report = fit_parameter_stage(
            contact_config["parameter_stages"][2],
            [missing_binding],
            contact_config,
            nominal_parameter_values(contact_config),
            backend="official",
            model_base_directory=FIXTURE_ROOT,
        )
        self.assertEqual(contact_report["status"], "rejected_missing_model_binding")
        self.assertIn("body/free-joint", contact_report["reason"])

    def test_zero_perturbation_sensitivity_blocks_stage_optimization(self) -> None:
        payload = json.loads(EPISODE_PATH.read_text(encoding="utf-8"))
        for sample in payload["samples"]:
            sample["command_joint_position"] = [0.0]
            sample["measured"]["joint_position"] = [0.0]
            sample["measured"]["end_effector_position_m"] = [0.1, 0.0, 0.1]
            sample["measured"]["gripper_position"] = 0.0
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "constant.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            episode = load_recorded_episode(path, self.config)
            report = fit_parameter_stage(
                self.config["parameter_stages"][1],
                [episode],
                self.config,
                nominal_parameter_values(self.config),
                backend="official",
                model_base_directory=FIXTURE_ROOT,
            )
        self.assertEqual(report["status"], "skipped_unidentifiable")
        self.assertFalse(report["sensitivity"]["all_parameters_identifiable"])
        self.assertTrue(report["parameters_unchanged"])

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
                    "metadata_status": "reviewed_adjudicated",
                    "column_adjudication": {
                        "status": "reviewed",
                        "decision_id": f"fixture-column-{index}",
                        "reviewer": "fixture_evaluator",
                        "reviewed_at": "2026-07-19T00:00:00+00:00",
                        "evidence_sha256": f"{index + 10:064x}",
                        "source_square": source,
                        "destination_square": destination,
                    },
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
                validate_split_manifest(leaked, config=self.config)
            unguarded = copy.deepcopy(manifest)
            unguarded["leakage_guards"]["row_level_split_forbidden"] = False
            with self.assertRaisesRegex(SystemIdentificationError, "leakage guards"):
                validate_split_manifest(unguarded, config=self.config)
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
            unresolved_catalog = copy.deepcopy(catalog)
            unresolved_catalog["episodes"][1]["metadata_status"] = (
                "conflict_folder_label_vs_receipt"
            )
            unresolved_catalog["episodes"][1].pop("column_adjudication")
            unresolved_path = root / "unresolved-catalog.json"
            unresolved_path.write_text(
                json.dumps(unresolved_catalog), encoding="utf-8"
            )
            with self.assertRaisesRegex(
                SystemIdentificationError, "reviewed column adjudication lineage"
            ):
                freeze_episode_split(
                    unresolved_path,
                    CONFIG_PATH,
                    root / "unresolved-split.json",
                    strategy="leave_one_column_out",
                    held_out_column="c",
                )

    def test_split_validator_recomputes_assignments_fractions_columns_and_digest(self) -> None:
        catalog = {
            "catalog_id": "deterministic-tamper-fixture",
            "episodes": [
                {
                    "recording_id": f"episode-{index:02d}",
                    "source_path": f"episode-{index:02d}.json",
                    "samples_sha256": f"{index + 1:064x}",
                    "proof_class": "synthetic",
                    "assets": {"samples": f"episode-{index:02d}.json"},
                }
                for index in range(12)
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog_path = root / "catalog.json"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            manifest = freeze_episode_split(
                catalog_path,
                CONFIG_PATH,
                root / "split.json",
                strategy="deterministic_hash",
            )
            portable = copy.deepcopy(manifest)
            portable.pop("manifest_path")
            portable.pop("manifest_sha256")
            train = next(
                entry for entry in portable["episodes"] if entry["split"] == "train"
            )
            held = next(
                entry
                for entry in portable["episodes"]
                if entry["split"] == "held_out"
            )
            swapped = copy.deepcopy(portable)
            by_id = {entry["episode_id"]: entry for entry in swapped["episodes"]}
            by_id[train["episode_id"]]["split"] = "held_out"
            by_id[held["episode_id"]]["split"] = "train"
            with self.assertRaisesRegex(SystemIdentificationError, "assignment drifted"):
                validate_split_manifest(swapped, config=self.config)
            fraction_tamper = copy.deepcopy(portable)
            fraction_tamper["episodes"][0]["assignment_fraction"] += 0.001
            with self.assertRaisesRegex(
                SystemIdentificationError, "assignment_fraction drifted"
            ):
                validate_split_manifest(fraction_tamper, config=self.config)
            digest_tamper = copy.deepcopy(portable)
            digest_tamper["episodes"][0]["proof_class"] = "replay"
            with self.assertRaisesRegex(SystemIdentificationError, "digest drifted"):
                validate_split_manifest(digest_tamper, config=self.config)
            authority_tamper = copy.deepcopy(portable)
            authority_tamper["seed"] = "attacker-selected-seed"
            authority_tamper["split_authority"]["seed"] = "attacker-selected-seed"
            for entry in authority_tamper["episodes"]:
                fraction = _hash_fraction(
                    authority_tamper["seed"], entry["episode_id"]
                )
                entry["assignment_fraction"] = fraction
                entry["split"] = (
                    "held_out"
                    if fraction < authority_tamper["holdout_fraction"]
                    else "train"
                )
            authority_tamper["split_counts"] = {
                name: sum(
                    entry["split"] == name
                    for entry in authority_tamper["episodes"]
                )
                for name in ("train", "held_out")
            }
            authority_tamper["assignment_digest_sha256"] = (
                _split_assignment_digest(authority_tamper)
            )
            with self.assertRaisesRegex(
                SystemIdentificationError, "split authority drifted"
            ):
                validate_split_manifest(authority_tamper, config=self.config)

    def test_loco_validator_rejects_column_rule_tamper(self) -> None:
        catalog = {
            "catalog_id": "loco-tamper-fixture",
            "episodes": [],
        }
        for index, (source, destination) in enumerate(
            (("b1", "b2"), ("c1", "c2"), ("d1", "d2"))
        ):
            catalog["episodes"].append(
                {
                    "recording_id": f"episode-{index}",
                    "source_path": f"episode-{index}.json",
                    "samples_sha256": f"{index + 1:064x}",
                    "source_square": source,
                    "destination_square": destination,
                    "proof_class": "synthetic",
                    "metadata_status": "reviewed_adjudicated",
                    "column_adjudication": {
                        "status": "reviewed",
                        "decision_id": f"decision-{index}",
                        "reviewer": "fixture_evaluator",
                        "reviewed_at": "2026-07-19T00:00:00+00:00",
                        "evidence_sha256": f"{index + 20:064x}",
                        "source_square": source,
                        "destination_square": destination,
                    },
                    "assets": {"samples": f"episode-{index}.json"},
                }
            )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog_path = root / "catalog.json"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            manifest = freeze_episode_split(
                catalog_path,
                CONFIG_PATH,
                root / "split.json",
                strategy="leave_one_column_out",
                held_out_column="c",
            )
            manifest.pop("manifest_path")
            manifest.pop("manifest_sha256")
            tampered = copy.deepcopy(manifest)
            c_entry = next(
                entry for entry in tampered["episodes"] if entry["source_column"] == "c"
            )
            c_entry["split"] = "train"
            tampered["split_counts"] = {"train": 3, "held_out": 0}
            with self.assertRaisesRegex(SystemIdentificationError, "assignment drifted"):
                validate_split_manifest(tampered, config=self.config)

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
            self.assertNotIn(
                "sysid-fit",
                "\n".join(report["post_cherry_pick_canonical_commands"]),
            )

    def test_input_report_rejects_hash_valid_but_malformed_samples(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog_path, _, _ = _physical_fixture(root, rows=[{}])
            report = inspect_recording_catalog_inputs(
                catalog_path,
                repo_root=root,
                config_path=_approved_physical_config(root),
                inspection_scope="explicit_repo_root",
            )
            self.assertEqual(report["joint_replay_ready_episode_count"], 0)
            self.assertEqual(report["missing_required_asset_count"], 0)
            self.assertFalse(report["episodes"][0]["sample_semantics_valid"])
            self.assertIn(
                "finite values", report["episodes"][0]["sample_semantics_error"]
            )
            self.assertFalse(report["joint_timing_replay_ready"])

    def test_input_report_accepts_strict_range_valid_reviewed_transform_without_canonical_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog_path, recording, _ = _physical_fixture(
                root, rows=_valid_physical_rows()
            )
            config_path = _approved_physical_config(root)
            report = inspect_recording_catalog_inputs(
                catalog_path,
                repo_root=root,
                config_path=config_path,
                inspection_scope="canonical_checkout",
            )
            self.assertEqual(report["joint_replay_ready_episode_count"], 1)
            self.assertTrue(report["episodes"][0]["sample_semantics_valid"])
            self.assertTrue(
                report["episodes"][0]["joint_limit_validation"][
                    "all_within_limits"
                ]
            )
            self.assertTrue(
                report["episodes"][0][
                    "full_catalog_receipt_sample_provenance_bound"
                ]
            )
            self.assertTrue(report["physical_joint_transform"]["calibration_approved"])
            self.assertTrue(report["joint_timing_replay_ready"])
            self.assertTrue(report["timing_control_fit_ready"])
            self.assertFalse(report["calibration_ready"])
            self.assertEqual(report["claim"], "joint_timing_replay_inputs_present")
            self.assertEqual(report["inspection_scope"]["kind"], "explicit_repo_root")
            self.assertEqual(
                report["inspection_scope"]["requested_kind"], "canonical_checkout"
            )
            self.assertFalse(
                report["inspection_scope"]["canonical_checkout_inspected"]
            )
            self.assertEqual(
                report["inspection_scope"]["canonical_checkout_state"],
                "caller_supplied_root_inspected_without_canonical_identity_claim",
            )
            self.assertIn("coordinator_reported_canonical_state", report)
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
                config_path=config_path,
                inspection_scope="canonical_checkout",
            )
            self.assertEqual(tampered["joint_replay_ready_episode_count"], 0)
            self.assertEqual(tampered["mismatched_required_asset_count"], 1)
            self.assertFalse(tampered["joint_timing_replay_ready"])
            self.assertFalse(tampered["calibration_ready"])

    def test_live_like_out_of_range_series_report_exact_counts_and_block_fit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            values = [0.0, 110.0, 0.0, 0.0, 0.0, 20.0]
            catalog_path, _, _ = _physical_fixture(
                root, rows=_valid_physical_rows(values)
            )
            report = inspect_recording_catalog_inputs(
                catalog_path,
                repo_root=root,
                config_path=_approved_physical_config(root),
                inspection_scope="explicit_repo_root",
            )
            limits = report["aggregate_joint_limit_validation"]
            self.assertEqual(
                limits["initial_measured_state"]["violating_row_count"], 1
            )
            self.assertEqual(limits["measured_trajectory"]["violating_row_count"], 2)
            self.assertEqual(limits["recorded_commands"]["violating_row_count"], 2)
            self.assertGreater(
                limits["recorded_commands"]["maximum_exceedance"], 0.1
            )
            self.assertFalse(report["joint_timing_replay_ready"])
            self.assertFalse(report["timing_control_fit_ready"])
            self.assertEqual(report["joint_range_valid_episode_count"], 0)

    def test_provisional_transform_blocks_even_range_valid_physical_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog_path, _, _ = _physical_fixture(
                root, rows=_valid_physical_rows()
            )
            report = inspect_recording_catalog_inputs(
                catalog_path,
                repo_root=root,
                config_path=REPO_ROOT
                / "configs/sysid/recorded_action_sysid_v1.json",
                inspection_scope="explicit_repo_root",
            )
            self.assertEqual(report["strict_sample_semantics_valid_episode_count"], 1)
            self.assertEqual(report["joint_range_valid_episode_count"], 1)
            self.assertFalse(report["physical_joint_transform"]["calibration_approved"])
            self.assertFalse(report["joint_timing_replay_ready"])
            self.assertEqual(
                report["claim"], "joint_timing_replay_blocked_by_transform_or_ranges"
            )

    def test_transform_hash_shape_sign_and_offset_drift_fail_closed(self) -> None:
        base = json.loads(
            (REPO_ROOT / "configs/sysid/recorded_action_sysid_v1.json").read_text(
                encoding="utf-8"
            )
        )
        mutations = []
        sign = copy.deepcopy(base)
        sign["physical_adapter"]["joint_transform"]["joints"][0]["sign"] = -1
        mutations.append(("hash", sign, False))
        offset = copy.deepcopy(base)
        offset["physical_adapter"]["joint_transform"]["joints"][0][
            "zero_offset"
        ] = 0.1
        mutations.append(("hash", offset, False))
        shape = copy.deepcopy(base)
        shape_transform = shape["physical_adapter"]["joint_transform"]
        shape_transform["joints"].pop()
        shape["physical_adapter"]["joint_transform_sha256"] = canonical_json_sha256(
            shape_transform
        )
        mutations.append(("equal unique shape", shape, True))
        invalid_sign = copy.deepcopy(base)
        invalid_transform = invalid_sign["physical_adapter"]["joint_transform"]
        invalid_transform["joints"][0]["sign"] = 0
        invalid_sign["physical_adapter"][
            "joint_transform_sha256"
        ] = canonical_json_sha256(invalid_transform)
        mutations.append(("sign/scale", invalid_sign, True))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, (message, payload, _) in enumerate(mutations):
                path = root / f"bad-transform-{index}.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.subTest(message=message), self.assertRaisesRegex(
                    ReplayContractError, message
                ):
                    load_sysid_config(path)

    def test_physical_replay_receipt_is_relocation_invariant_and_provenance_bound(self) -> None:
        sources: list[dict[str, object]] = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                catalog_path, recording, catalog = _physical_fixture(
                    root, rows=_valid_physical_rows()
                )
                config_path = _approved_physical_config(root)
                config = load_sysid_config(config_path)
                provenance = _physical_provenance(catalog_path, catalog)
                episode = load_recorded_episode(
                    recording,
                    config,
                    source_provenance=provenance,
                )
                replay = simulate_and_align(episode, config)
                receipt = write_replay_receipt(replay, config, root / "output")
                self.assertTrue(receipt["source"]["full_physical_provenance_bound"])
                self.assertTrue(receipt["proof"]["physical_read_only_input"])
                self.assertNotIn(temporary, json.dumps(receipt["source"]))
                sources.append(receipt["source"])
                tampered = copy.deepcopy(provenance)
                tampered["recording_receipt"]["sha256"] = "f" * 64
                with self.assertRaisesRegex(ReplayContractError, "provenance chain"):
                    load_recorded_episode(
                        recording,
                        config,
                        source_provenance=tampered,
                    )
        self.assertEqual(sources[0], sources[1])

    def test_caller_supplied_catalog_identity_cannot_fake_complete_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog_path, recording, catalog = _physical_fixture(
                root, rows=_valid_physical_rows()
            )
            config_path = _approved_physical_config(root)
            config = load_sysid_config(config_path)
            fake = _physical_provenance(catalog_path, catalog)
            fake["catalog"] = {
                "kind": "content_addressed",
                "catalog_id": "nonexistent",
                "sha256": "0" * 64,
            }
            episode = load_recorded_episode(
                recording,
                config,
                source_provenance=fake,
            )
            self.assertFalse(episode.source_provenance["chain_complete"])
            replay = simulate_and_align(episode, config)
            receipt = write_replay_receipt(replay, config, root / "fake-output")
            self.assertFalse(receipt["source"]["full_physical_provenance_bound"])

            fake_with_path = copy.deepcopy(fake)
            fake_with_path["catalog"]["path"] = catalog_path.name
            fake_with_path["catalog"]["_runtime_path"] = str(catalog_path)
            with self.assertRaisesRegex(
                ReplayContractError, "opened and hash-verified"
            ):
                load_recorded_episode(
                    recording,
                    config,
                    source_provenance=fake_with_path,
                )

    def test_fit_receipt_binds_physical_provenance_and_true_proof_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog_path, recording, catalog = _physical_fixture(
                root, rows=_valid_physical_rows()
            )
            config_path = _approved_physical_config(root)
            config = load_sysid_config(config_path)
            episode = load_recorded_episode(
                recording,
                config,
                source_provenance=_physical_provenance(catalog_path, catalog),
            )
            train_id = "fixture-slider-train-001"
            held_id = "fixture-slider-held-out-001"
            train_episode = replace(
                episode,
                episode_id=train_id,
                source_provenance={
                    **episode.source_provenance,
                    "episode_id": train_id,
                },
            )
            held_episode = replace(
                episode,
                episode_id=held_id,
                source_provenance={
                    **episode.source_provenance,
                    "episode_id": held_id,
                },
            )
            manifest = {
                "schema_version": "sim2claw.sysid_episode_split.v1",
                "split_id": f"{catalog['catalog_id']}:deterministic_hash",
                "frozen": True,
                "owner": "fixture_evaluator",
                "unit": "whole_episode",
                "strategy": "deterministic_hash",
                "held_out_column": None,
                "holdout_fraction": 0.5,
                "seed": "fixture",
                "source_catalog": {
                    "path": "catalog.json",
                    "sha256": sha256_file(catalog_path),
                    "catalog_id": catalog["catalog_id"],
                },
                "sysid_config": {
                    "path": "approved-sysid-config.json",
                    "sha256": sha256_file(config_path),
                    "config_id": config["config_id"],
                },
                "split_authority": _split_authority_from_config(config),
                "split_counts": {"train": 1, "held_out": 1},
                "episodes": [
                    {
                        "episode_id": held_id,
                        "source_kind": "canonical_episode",
                        "source_path": "held.json",
                        "source_samples_sha256": "b" * 64,
                        "source_square": None,
                        "destination_square": None,
                        "source_column": None,
                        "destination_column": None,
                        "assignment_fraction": _hash_fraction("fixture", held_id),
                        "split": "held_out",
                    },
                    {
                        "episode_id": train_id,
                        "source_kind": "canonical_episode",
                        "source_path": "train.json",
                        "source_samples_sha256": "a" * 64,
                        "source_square": None,
                        "destination_square": None,
                        "source_column": None,
                        "destination_column": None,
                        "assignment_fraction": _hash_fraction("fixture", train_id),
                        "split": "train",
                    },
                ],
                "leakage_guards": {
                    "episode_id_disjoint": True,
                    "source_samples_sha256_disjoint": True,
                    "row_level_split_forbidden": True,
                },
                "created_at": "2026-07-19T00:00:00+00:00",
            }
            manifest["assignment_digest_sha256"] = _split_assignment_digest(manifest)
            manifest_path = root / "split.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with patch(
                "sim2claw.system_identification.load_manifest_episodes",
                return_value={"train": [train_episode], "held_out": [held_episode]},
            ):
                receipt = run_system_identification(
                    manifest_path,
                    config_path=config_path,
                    output_directory=root / "fit",
                    backend="official",
                )
            self.assertTrue(receipt["proof"]["physical_read_only_input"])
            self.assertTrue(
                receipt["input_provenance"]["all_physical_chains_complete"]
            )
            self.assertNotIn(str(root), json.dumps(receipt["input_provenance"]))
            self.assertNotIn(str(root), json.dumps(receipt["split"]))
            self.assertNotIn(str(root), json.dumps(receipt["config"]))

    def test_fit_input_rejects_manifest_provenance_drift_from_bound_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_catalog_path, _, first_catalog = _physical_fixture(
                root,
                rows=_valid_physical_rows(),
                recording_id="recording-b",
            )
            _, _, second_catalog = _physical_fixture(
                root,
                rows=_valid_physical_rows([1.0, 0.0, 0.0, 0.0, 0.0, 20.0]),
                recording_id="recording-c",
            )
            entries = [first_catalog["episodes"][0], second_catalog["episodes"][0]]
            entries[1]["source_square"] = "c1"
            entries[1]["destination_square"] = "c2"
            for index, entry in enumerate(entries):
                entry["metadata_status"] = "reviewed_adjudicated"
                entry["column_adjudication"] = {
                    "status": "reviewed",
                    "decision_id": f"physical-fixture-{index}",
                    "reviewer": "fixture_evaluator",
                    "reviewed_at": "2026-07-19T00:00:00+00:00",
                    "evidence_sha256": f"{index + 30:064x}",
                    "source_square": entry["source_square"],
                    "destination_square": entry["destination_square"],
                }
            combined_catalog = {
                "catalog_id": "physical-provenance-fixture",
                "episodes": entries,
            }
            first_catalog_path.write_text(
                json.dumps(combined_catalog, sort_keys=True), encoding="utf-8"
            )
            config_path = _approved_physical_config(root)
            split_path = root / "configs" / "sysid" / "split.json"
            split_path.parent.mkdir(parents=True)
            manifest = freeze_episode_split(
                first_catalog_path,
                config_path,
                split_path,
                strategy="leave_one_column_out",
                held_out_column="c",
            )
            manifest.pop("manifest_path")
            manifest.pop("manifest_sha256")
            manifest["source_catalog"]["path"] = "catalog.json"
            manifest["episodes"][0]["source_receipt_sha256"] = "f" * 64
            manifest["assignment_digest_sha256"] = _split_assignment_digest(manifest)
            split_path.write_text(json.dumps(manifest), encoding="utf-8")
            loaded = load_split_manifest(
                split_path, config=load_sysid_config(config_path)
            )
            with self.assertRaisesRegex(
                SystemIdentificationError, "provenance drifted from the bound catalog"
            ):
                load_manifest_episodes(loaded, load_sysid_config(config_path))

    def test_end_to_end_receipt_does_not_claim_full_calibration_without_contact_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            train_payload = json.loads(EPISODE_PATH.read_text(encoding="utf-8"))
            held_payload = copy.deepcopy(train_payload)
            held_payload["episode_id"] = "fixture-slider-held-out-001"
            held_payload["column"] = "d"
            train_path = root / "train.json"
            held_path = root / "held.json"
            train_path.write_text(json.dumps(train_payload), encoding="utf-8")
            held_path.write_text(json.dumps(held_payload), encoding="utf-8")
            manifest = {
                "schema_version": "sim2claw.sysid_episode_split.v1",
                "split_id": "fixture:deterministic_hash",
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
                    "path": "tests/fixtures/sysid/smooth_slider_sysid_v1.json",
                    "sha256": sha256_file(CONFIG_PATH),
                    "config_id": self.config["config_id"]
                },
                "split_authority": _split_authority_from_config(self.config),
                "split_counts": {"train": 1, "held_out": 1},
                "episodes": [
                    {
                        "episode_id": held_payload["episode_id"],
                        "source_kind": "canonical_episode",
                        "source_path": str(held_path),
                        "source_samples_sha256": sha256_file(held_path),
                        "source_square": None,
                        "destination_square": None,
                        "source_column": None,
                        "destination_column": None,
                        "assignment_fraction": _hash_fraction(
                            "fixture", held_payload["episode_id"]
                        ),
                        "split": "held_out"
                    },
                    {
                        "episode_id": train_payload["episode_id"],
                        "source_kind": "canonical_episode",
                        "source_path": str(train_path),
                        "source_samples_sha256": sha256_file(train_path),
                        "source_square": None,
                        "destination_square": None,
                        "source_column": None,
                        "destination_column": None,
                        "assignment_fraction": _hash_fraction(
                            "fixture", train_payload["episode_id"]
                        ),
                        "split": "train"
                    }
                ],
                "leakage_guards": {
                    "episode_id_disjoint": True,
                    "source_samples_sha256_disjoint": True,
                    "row_level_split_forbidden": True
                },
                "created_at": "2026-07-19T00:00:00+00:00"
            }
            manifest["assignment_digest_sha256"] = _split_assignment_digest(manifest)
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
            self.assertFalse(receipt["proof"]["physical_read_only_input"])
            self.assertFalse(receipt["proof"]["physical_task"])
            self.assertTrue((root / "fit" / "fit_receipt.json").is_file())
            self.assertTrue((root / "fit" / "baseline_metrics.json").is_file())
            self.assertTrue((root / "fit" / "candidate_metrics.json").is_file())
            self.assertNotIn(str(root), json.dumps(receipt["split"]))
            self.assertNotIn(str(root), json.dumps(receipt["config"]))


if __name__ == "__main__":
    unittest.main()

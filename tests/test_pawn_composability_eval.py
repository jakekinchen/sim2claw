from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from sim2claw.pawn_composability_eval import (
    CONTRACT_PATH,
    ComposabilityEvaluationError,
    circle_intersection_fraction,
    evaluate_composability,
    fit_calibration,
    load_contract,
    square_center,
)


REPO_ROOT = Path(__file__).parents[1]
HISTORICAL_PRODUCT_CONTRACT = (
    REPO_ROOT / "configs" / "evaluations" / "pawn_rank12_bidirectional_v1.json"
)
TEMPLATE = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "pawn_rank12_bidirectional_annotations_template_v2.json"
)
INFERENCE_READINESS = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "pawn_transition_inference_readiness_v1.json"
)
REPLAY_LIMIT_AUDIT = (
    REPO_ROOT
    / "docs"
    / "reference"
    / "PHYSICAL_REPLAY_JOINT_LIMIT_AUDIT_20260719.json"
)


class PawnComposabilityEvaluationTest(unittest.TestCase):
    def test_research_readiness_overlay_is_stricter_and_non_authoritative(self) -> None:
        contract = load_contract()
        readiness = json.loads(INFERENCE_READINESS.read_text(encoding="utf-8"))
        tiers = readiness["transition_evidence_tiers"]
        calibration = readiness["pose_and_board_calibration"]
        composition = readiness["composition_claim_boundary"]

        self.assertEqual(
            readiness["applies_to"],
            "configs/evaluations/pawn_rank12_bidirectional_v2.json",
        )
        self.assertEqual(
            readiness["applies_to_sha256"],
            hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            tiers["fit_computable"]["minimum_independent_episodes"],
            contract["regression"]["minimum_episode_count"],
        )
        self.assertGreaterEqual(
            tiers["exploratory"]["minimum_independent_episodes"], 10
        )
        self.assertGreater(
            tiers["claim_eligible"]["minimum_independent_episodes"],
            tiers["exploratory"]["minimum_independent_episodes"],
        )
        self.assertTrue(tiers["claim_eligible"]["status"].startswith("disabled_"))
        self.assertIsNone(
            tiers["claim_eligible"]["minimum_independent_session_clusters"]
        )
        self.assertTrue(
            tiers["claim_eligible"]["require_stable_leave_one_session_out_predictions"]
        )
        self.assertIsNone(
            tiers["claim_eligible"]["leave_one_session_out_stability"][
                "minimum_eligible_omission_count"
            ]
        )
        self.assertIn(
            "candidate_interval_method_not_yet_authorized",
            tiers["claim_eligible"],
        )
        self.assertNotIn(
            "require_episode_bootstrap_confidence_intervals",
            tiers["claim_eligible"],
        )
        self.assertGreaterEqual(
            len(tiers["claim_eligible"]["enabling_requirements"]), 4
        )
        self.assertFalse(
            readiness["episode_independence"][
                "physical_and_simulation_episodes_may_be_pooled_in_one_transition_estimate"
            ]
        )
        self.assertFalse(
            readiness["claim_scope_and_multiplicity"][
                "family_wide_inferential_claim_allowed"
            ]
        )
        self.assertIn(
            "upper_95_percent_bound",
            readiness["operational_definitions"]["stable_uncertainty_rule"],
        )
        self.assertGreater(
            calibration["minimum_spatially_distributed_correspondences"],
            contract["pose_measurement"]["minimum_homography_correspondences"],
        )
        self.assertTrue(composition["categorical_task_or_stability_failure_is_absorbing"])
        self.assertFalse(composition["physical_execution_survival_claim_allowed"])
        point = readiness["frozen_point_thresholds"]
        regression = contract["regression"]
        self.assertEqual(
            point["a_near_zero_frobenius_max"],
            regression["a_near_zero_frobenius"],
        )
        self.assertEqual(
            point["a_near_identity_frobenius_max"],
            regression["a_near_identity_frobenius"],
        )
        self.assertEqual(point["small_bias_norm_m_max"], regression["small_bias_m"])
        self.assertEqual(
            point["large_residual_rms_m_min_exclusive"],
            regression["large_residual_rms_m"],
        )
        self.assertEqual(
            point["stabilizing_pair_spectral_radius_max"],
            contract["composition_diagnostic"]["stabilizing_spectral_radius_max"],
        )
        self.assertEqual(
            point["neutral_pair_spectral_radius_max"],
            contract["composition_diagnostic"]["neutral_spectral_radius_max"],
        )
        self.assertFalse(
            readiness["authority"]["may_change_frozen_v2_engineering_outputs"]
        )
        self.assertFalse(readiness["authority"]["may_promote_a_checkpoint"])
        self.assertFalse(readiness["authority"]["may_authorize_physical_motion"])

    def test_replay_limit_audit_binds_sources_and_internal_arithmetic(self) -> None:
        audit = json.loads(REPLAY_LIMIT_AUDIT.read_text(encoding="utf-8"))
        inputs = audit["inputs"]
        for path_key, hash_key in (
            ("catalog_path", "catalog_sha256"),
            ("legacy_replay_source_path", "legacy_replay_source_sha256"),
            ("audit_runner_path", "audit_runner_sha256"),
            ("scene_source_path", "scene_source_sha256"),
            ("so101_xml_path", "so101_xml_sha256"),
        ):
            path = REPO_ROOT / inputs[path_key]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), inputs[hash_key])

        current_lock_sha256 = hashlib.sha256(
            (REPO_ROOT / "uv.lock").read_bytes()
        ).hexdigest()
        self.assertEqual(
            inputs["lockfile_binding_scope"],
            "historical_generation_snapshot_not_current_repository_gate",
        )
        reproduction = audit["post_integration_reproduction"]
        self.assertEqual(
            current_lock_sha256,
            reproduction["current_lockfile_sha256"],
        )
        self.assertTrue(reproduction["semantic_core_matches_historical_receipt"])
        self.assertEqual(len(reproduction["runner_output_sha256"]), 64)
        control_payload = {
            "joint_order": audit["simulator_joint_order"],
            "actuator_names": audit["actuator_names"],
            "actuator_ctrlrange": audit["actuator_control_ranges_sim_units"],
        }
        control_digest = hashlib.sha256(
            json.dumps(
                control_payload, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        self.assertEqual(control_digest, audit["compiled_control_contract_sha256"])

        self.assertEqual(
            audit["violation_predicate"],
            {
                "expression": "value < lower_bound or value > upper_bound",
                "tolerance_sim_units": 0.0,
            },
        )
        for key in ("measured_trajectory", "recorded_commands"):
            metric = audit["results"][key]
            self.assertEqual(metric["row_count"], 7741)
            self.assertAlmostEqual(
                metric["violating_row_fraction"],
                metric["violating_row_count"] / metric["row_count"],
            )
        self.assertEqual(
            audit["results"]["episodes_with_out_of_range_initial_state"], 18
        )
        self.assertFalse(audit["interpretation"]["exact_recorded_action_replay_supported"])

    def test_contract_has_exact_b_to_g_product_scope_and_preserves_v1(self) -> None:
        contract = load_contract()
        self.assertEqual(len(contract["skills"]), 12)
        self.assertEqual({item["column"] for item in contract["skills"]}, set("bcdefg"))
        self.assertEqual(contract["status"], "frozen_owner_selected_product_benchmark")
        self.assertFalse(contract["authority"]["retrospective_source_episode_can_promote"])
        self.assertEqual(
            hashlib.sha256(HISTORICAL_PRODUCT_CONTRACT.read_bytes()).hexdigest(),
            "f3dac8b86cd7b0252153d25c0d5c09204079003ac9780642992fd10bc08e0d43",
        )
        project_state = json.loads(
            (REPO_ROOT / "docs" / "autonomous-workflow" / "project_state.json").read_text()
        )
        diagnostic = project_state["locked_product_evaluation"]
        self.assertEqual(
            diagnostic["sha256"], hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest()
        )
        self.assertEqual(diagnostic["evaluation_set_id"], contract["evaluation_set_id"])
        self.assertFalse(diagnostic["training_or_policy_result_proven"])

    def test_empty_template_emits_every_artifact_and_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "eval"
            summary = evaluate_composability(TEMPLATE, output)
            self.assertEqual(summary["status"], "base_center_annotations_pending_review")
            self.assertEqual(summary["episode_count"], 0)
            self.assertFalse(summary["physical_authority_created"])
            self.assertFalse(summary["policy_promoted"])
            for name in (
                "endpoint_metrics.csv",
                "per_skill_bias.json",
                "per_skill_covariance.json",
                "initial_to_final_offset_regression.json",
                "precondition_envelopes.json",
                "trajectory_repeatability.json",
                "composition_stability.json",
                "summary.json",
                "report.md",
                "board_coordinate_overlays/index.html",
            ):
                self.assertTrue((output / name).is_file(), name)

    def test_complete_synthetic_suite_measures_self_centering_and_composition(self) -> None:
        contract = load_contract()
        square_side = contract["board_coordinate_system"]["square_side_m"]
        initial_offsets = [
            (-0.004, -0.003),
            (0.004, -0.003),
            (-0.004, 0.003),
            (0.004, 0.003),
            (0.0, 0.0),
        ]
        episodes = []
        for skill in contract["skills"]:
            source = square_center(skill["source_square"], square_side)
            destination = square_center(skill["destination_square"], square_side)
            for index, initial_offset in enumerate(initial_offsets):
                initial_offset_array = np.asarray(initial_offset, dtype=np.float64)
                final_offset = 0.1 * initial_offset_array + np.asarray([0.001, -0.001])
                initial = source + initial_offset_array
                final = destination + final_offset
                episodes.append(
                    {
                        "episode_id": f"{skill['skill_id']}-{index}",
                        "skill_id": skill["skill_id"],
                        "proof_class": "synthetic_test_fixture",
                        "initial_pose": {"board_xy_m": initial.tolist()},
                        "final_pose": {"board_xy_m": final.tolist()},
                        "upright": True,
                        "stable": True,
                        "ordinary_square_success": True,
                        "pawn_base_trajectory": [
                            {"progress": 0.0, "board_xy_m": initial.tolist()},
                            {"progress": 1.0, "board_xy_m": final.tolist()},
                        ],
                    }
                )
        manifest = {
            "schema_version": "sim2claw.pawn_composability_annotations.v1",
            "annotation_set_id": "synthetic-complete-test",
            "proof_class": "synthetic_test_fixture",
            "source_catalog_is_pose_evidence": False,
            "calibrations": [],
            "episodes": episodes,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = root / "annotations.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            output = root / "eval"
            summary = evaluate_composability(manifest_path, output)
            self.assertEqual(summary["status"], "complete_descriptive_evaluation")
            self.assertEqual(summary["episode_count"], 60)
            self.assertEqual(summary["covered_skill_count"], 12)
            self.assertEqual(summary["supported_skill_regression_count"], 12)
            self.assertAlmostEqual(summary["precision_success_rate"], 1.0)
            regressions = json.loads(
                (output / "initial_to_final_offset_regression.json").read_text()
            )
            self.assertEqual(regressions["pawn_b1_to_b2"]["classification"], "self_centering")
            np.testing.assert_allclose(
                regressions["pawn_b1_to_b2"]["A"], np.eye(2) * 0.1, atol=1e-10
            )
            composition = json.loads(
                (output / "composition_stability.json").read_text()
            )
            self.assertEqual(composition["b"]["stability"], "stabilizing")
            self.assertEqual(
                sorted(composition["b"]["move_statistics"]),
                ["1", "10", "2", "20", "5"],
            )
            envelopes = json.loads((output / "precondition_envelopes.json").read_text())
            self.assertTrue(envelopes["pawn_b1_to_b2"]["established"])
            trajectories = json.loads(
                (output / "trajectory_repeatability.json").read_text()
            )
            self.assertEqual(trajectories["pawn_b1_to_b2"]["status"], "measured")

    def test_collinear_offsets_emit_no_composition_move_statistics(self) -> None:
        contract = load_contract()
        square_side = contract["board_coordinate_system"]["square_side_m"]
        episodes = []
        for skill_id, source_square, destination_square in (
            ("pawn_b1_to_b2", "b1", "b2"),
            ("pawn_b2_to_b1", "b2", "b1"),
        ):
            source = square_center(source_square, square_side)
            destination = square_center(destination_square, square_side)
            for index, horizontal in enumerate((-0.006, -0.003, 0.0, 0.003, 0.006)):
                offset = np.asarray([horizontal, 0.0], dtype=np.float64)
                episodes.append(
                    {
                        "episode_id": f"collinear-{skill_id}-{index}",
                        "skill_id": skill_id,
                        "proof_class": "synthetic_test_fixture",
                        "initial_pose": {
                            "board_xy_m": (source + offset).tolist()
                        },
                        "final_pose": {
                            "board_xy_m": (destination + 0.5 * offset).tolist()
                        },
                        "upright": True,
                        "stable": True,
                        "ordinary_square_success": True,
                    }
                )
        manifest = {
            "schema_version": "sim2claw.pawn_composability_annotations.v1",
            "annotation_set_id": "collinear-offsets",
            "proof_class": "synthetic_test_fixture",
            "source_catalog_is_pose_evidence": False,
            "calibrations": [],
            "episodes": episodes,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = root / "annotations.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            output = root / "evaluation"
            evaluate_composability(manifest_path, output)
            regressions = json.loads(
                (output / "initial_to_final_offset_regression.json").read_text()
            )
            self.assertEqual(regressions["pawn_b1_to_b2"]["design_rank"], 2)
            self.assertFalse(regressions["pawn_b1_to_b2"]["model_supported"])
            self.assertFalse(regressions["pawn_b2_to_b1"]["model_supported"])
            composition = json.loads(
                (output / "composition_stability.json").read_text()
            )
            self.assertEqual(
                composition["b"]["status"], "insufficient_regression_support"
            )
            self.assertIsNone(composition["b"]["move_statistics"])

    def test_pixel_homography_is_hash_bound_and_rejects_box_centers(self) -> None:
        contract = load_contract()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image_path = root / "calibration.png"
            self.assertTrue(cv2.imwrite(str(image_path), np.zeros((128, 128, 3), dtype=np.uint8)))
            image_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()
            side = contract["board_coordinate_system"]["playing_side_m"]
            payload = {
                "calibration_id": "fixture-camera",
                "image_path": image_path.name,
                "image_sha256": image_hash,
                "correspondences": [
                    {"pixel_xy": [10, 10], "board_xy_m": [0, 0]},
                    {"pixel_xy": [110, 10], "board_xy_m": [side, 0]},
                    {"pixel_xy": [110, 110], "board_xy_m": [side, side]},
                    {"pixel_xy": [10, 110], "board_xy_m": [0, side]},
                ],
            }
            calibration = fit_calibration(
                payload,
                contract=contract,
                manifest_path=root / "manifest.json",
                require_review_lineage=False,
            )
            self.assertLess(calibration.board_rms_m, 1e-8)
            np.testing.assert_allclose(
                calibration.pixel_to_board @ np.asarray([10, 10, 1.0]),
                [0, 0, 1],
                atol=1e-10,
            )

            manifest = {
                "schema_version": "sim2claw.pawn_composability_annotations.v1",
                "annotation_set_id": "bad-box-center",
                "proof_class": "synthetic_test_fixture",
                "source_catalog_is_pose_evidence": False,
                "calibrations": [payload],
                "episodes": [
                    {
                        "episode_id": "bad",
                        "skill_id": "pawn_b1_to_b2",
                        "proof_class": "synthetic_test_fixture",
                        "calibration_id": "fixture-camera",
                        "initial_pose": {
                            "visual_bounding_box_center_px": [20, 20],
                            "image_path": image_path.name,
                            "image_sha256": image_hash,
                        },
                        "final_pose": {
                            "base_center_px": [20, 30],
                            "image_path": image_path.name,
                            "image_sha256": image_hash,
                        },
                    }
                ],
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(
                ComposabilityEvaluationError, "forbidden visual bounding-box center"
            ):
                evaluate_composability(manifest_path, root / "output")

    def test_central_region_footprint_fraction_has_expected_limits(self) -> None:
        self.assertAlmostEqual(circle_intersection_fraction(0.0, 0.01, 0.02), 1.0)
        self.assertAlmostEqual(circle_intersection_fraction(0.03, 0.01, 0.02), 0.0)
        self.assertGreater(circle_intersection_fraction(0.015, 0.01, 0.02), 0.0)
        self.assertLess(circle_intersection_fraction(0.015, 0.01, 0.02), 1.0)

    def test_physical_proposed_pose_marker_is_rejected(self) -> None:
        contract = load_contract()
        source = square_center("b1", contract["board_coordinate_system"]["square_side_m"])
        destination = square_center(
            "b2", contract["board_coordinate_system"]["square_side_m"]
        )
        proposed_review = {
            "status": "proposed",
            "measurement": "pawn_base_contact_center_on_board_plane",
            "reviewer": "candidate-generator",
            "reviewed_at": "2026-07-19T00:00:00-05:00",
        }
        manifest = {
            "schema_version": "sim2claw.pawn_composability_annotations.v1",
            "annotation_set_id": "unaccepted-physical-marker",
            "proof_class": "physical_recording_annotations_unqualified",
            "source_catalog_is_pose_evidence": False,
            "calibrations": [],
            "episodes": [
                {
                    "episode_id": "proposed",
                    "skill_id": "pawn_b1_to_b2",
                    "proof_class": "physical_recording_annotations_unqualified",
                    "initial_pose": {
                        "board_xy_m": source.tolist(),
                        "review": proposed_review,
                    },
                    "final_pose": {
                        "board_xy_m": destination.tolist(),
                        "review": proposed_review,
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = root / "catalog.json"
            catalog.write_text(
                json.dumps(
                    {
                        "episodes": [
                            {
                                "recording_id": "recording-proposed",
                                "source_square": "b1",
                                "destination_square": "b2",
                                "metadata_status": "consistent_folder_label_and_receipt",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            manifest["source_catalog_path"] = catalog.name
            manifest["source_catalog_sha256"] = hashlib.sha256(
                catalog.read_bytes()
            ).hexdigest()
            manifest["episodes"][0]["source_recording_id"] = "recording-proposed"
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(
                ComposabilityEvaluationError, "explicitly accepted review lineage"
            ):
                evaluate_composability(path, root / "output")

    def test_physical_manifest_cannot_omit_all_catalog_provenance(self) -> None:
        contract = load_contract()
        side = contract["board_coordinate_system"]["square_side_m"]
        accepted_review = {
            "status": "accepted",
            "measurement": "pawn_base_contact_center_on_board_plane",
            "reviewer": "physical-reviewer",
            "reviewed_at": "2026-07-19T01:00:00-05:00",
        }
        manifest = {
            "schema_version": "sim2claw.pawn_composability_annotations.v1",
            "annotation_set_id": "missing-all-provenance",
            "proof_class": "physical_recording_annotations_unqualified",
            "source_catalog_is_pose_evidence": False,
            "calibrations": [],
            "episodes": [
                {
                    "episode_id": "physical-without-provenance",
                    "skill_id": "pawn_b1_to_b2",
                    "proof_class": "physical_recording_annotations_unqualified",
                    "initial_pose": {
                        "board_xy_m": square_center("b1", side).tolist(),
                        "review": accepted_review,
                    },
                    "final_pose": {
                        "board_xy_m": square_center("b2", side).tolist(),
                        "review": accepted_review,
                    },
                    "upright": True,
                    "stable": True,
                    "ordinary_square_success": True,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(
                ComposabilityEvaluationError,
                "requires source_catalog_path and source_catalog_sha256",
            ):
                evaluate_composability(path, root / "output")

    def test_physical_episode_cannot_omit_source_recording_id(self) -> None:
        contract = load_contract()
        side = contract["board_coordinate_system"]["square_side_m"]
        accepted_review = {
            "status": "accepted",
            "measurement": "pawn_base_contact_center_on_board_plane",
            "reviewer": "physical-reviewer",
            "reviewed_at": "2026-07-19T01:00:00-05:00",
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = root / "catalog.json"
            catalog.write_text('{"episodes": []}\n', encoding="utf-8")
            manifest = {
                "schema_version": "sim2claw.pawn_composability_annotations.v1",
                "annotation_set_id": "missing-recording-id",
                "proof_class": "physical_recording_annotations_unqualified",
                "source_catalog_path": catalog.name,
                "source_catalog_sha256": hashlib.sha256(
                    catalog.read_bytes()
                ).hexdigest(),
                "source_catalog_is_pose_evidence": False,
                "calibrations": [],
                "episodes": [
                    {
                        "episode_id": "missing-recording-id",
                        "skill_id": "pawn_b1_to_b2",
                        "proof_class": "physical_recording_annotations_unqualified",
                        "initial_pose": {
                            "board_xy_m": square_center("b1", side).tolist(),
                            "review": accepted_review,
                        },
                        "final_pose": {
                            "board_xy_m": square_center("b2", side).tolist(),
                            "review": accepted_review,
                        },
                        "upright": True,
                        "stable": True,
                        "ordinary_square_success": True,
                    }
                ],
            }
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(
                ComposabilityEvaluationError,
                "physical recording episode requires source_recording_id",
            ):
                evaluate_composability(path, root / "output")

    def test_unknown_proof_class_is_rejected(self) -> None:
        manifest = {
            "schema_version": "sim2claw.pawn_composability_annotations.v1",
            "annotation_set_id": "unknown-proof-class",
            "proof_class": "physical_recording_annotations_typo",
            "source_catalog_is_pose_evidence": False,
            "calibrations": [],
            "episodes": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(
                ComposabilityEvaluationError, "unsupported annotation proof_class"
            ):
                evaluate_composability(path, root / "output")

    def test_missing_ordinary_square_outcomes_prevents_descriptive_completion(self) -> None:
        contract = load_contract()
        side = contract["board_coordinate_system"]["square_side_m"]
        initial_offsets = [
            (-0.004, -0.003),
            (0.004, -0.003),
            (-0.004, 0.003),
            (0.004, 0.003),
            (0.0, 0.0),
        ]
        episodes = []
        for skill in contract["skills"]:
            source = square_center(skill["source_square"], side)
            destination = square_center(skill["destination_square"], side)
            for index, offset in enumerate(initial_offsets):
                episodes.append(
                    {
                        "episode_id": f"missing-ordinary-{skill['skill_id']}-{index}",
                        "skill_id": skill["skill_id"],
                        "proof_class": "synthetic_test_fixture",
                        "initial_pose": {
                            "board_xy_m": (source + np.asarray(offset)).tolist()
                        },
                        "final_pose": {
                            "board_xy_m": (destination + 0.1 * np.asarray(offset)).tolist()
                        },
                        "upright": True,
                        "stable": True,
                    }
                )
        manifest = {
            "schema_version": "sim2claw.pawn_composability_annotations.v1",
            "annotation_set_id": "missing-ordinary-outcomes",
            "proof_class": "synthetic_test_fixture",
            "source_catalog_is_pose_evidence": False,
            "calibrations": [],
            "episodes": episodes,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            summary = evaluate_composability(path, root / "output")
            self.assertEqual(summary["episode_count"], 60)
            self.assertEqual(summary["covered_skill_count"], 12)
            self.assertEqual(
                summary["status"], "incomplete_missing_outcome_annotations"
            )
            self.assertIsNone(summary["ordinary_square_success_rate"])
            self.assertTrue(
                any(
                    "ordinary_square_success" in gap
                    for gap in summary["evidence_gaps"]
                )
            )

    def test_physical_unreviewed_calibration_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image_path = root / "calibration.png"
            self.assertTrue(cv2.imwrite(str(image_path), np.zeros((64, 64, 3), dtype=np.uint8)))
            image_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()
            manifest = {
                "schema_version": "sim2claw.pawn_composability_annotations.v1",
                "annotation_set_id": "unreviewed-calibration",
                "proof_class": "physical_recording_annotations_unqualified",
                "source_catalog_is_pose_evidence": False,
                "calibrations": [
                    {
                        "calibration_id": "proposal",
                        "image_path": image_path.name,
                        "image_sha256": image_hash,
                        "correspondences": [
                            {"pixel_xy": [0, 0], "board_xy_m": [0, 0]},
                            {"pixel_xy": [63, 0], "board_xy_m": [0.3556, 0]},
                            {"pixel_xy": [63, 63], "board_xy_m": [0.3556, 0.3556]},
                            {"pixel_xy": [0, 63], "board_xy_m": [0, 0.3556]},
                        ],
                    }
                ],
                "episodes": [],
            }
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(
                ComposabilityEvaluationError, "explicitly accepted review lineage"
            ):
                evaluate_composability(path, root / "output")

    def test_source_catalog_hash_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = root / "catalog.json"
            catalog.write_text('{"episodes": []}\n', encoding="utf-8")
            manifest = {
                "schema_version": "sim2claw.pawn_composability_annotations.v1",
                "annotation_set_id": "drifted-catalog",
                "proof_class": "physical_recording_annotations_unqualified",
                "source_catalog_path": catalog.name,
                "source_catalog_sha256": "0" * 64,
                "source_catalog_is_pose_evidence": False,
                "calibrations": [],
                "episodes": [],
            }
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(
                ComposabilityEvaluationError, "source catalog hash does not match"
            ):
                evaluate_composability(path, root / "output")


if __name__ == "__main__":
    unittest.main()

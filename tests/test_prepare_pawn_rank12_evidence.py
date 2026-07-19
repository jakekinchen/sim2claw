from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

import numpy as np


REPO_ROOT = Path(__file__).parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "prepare_pawn_rank12_evidence.py"
SPEC = importlib.util.spec_from_file_location(
    "prepare_pawn_rank12_evidence", SCRIPT_PATH
)
assert SPEC is not None and SPEC.loader is not None
PREPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARE)


class PreparePawnRank12EvidenceTest(unittest.TestCase):
    def test_duplicate_skill_rows_and_off_scope_rows_are_preserved(self) -> None:
        rows = [
            {
                "recording_id": "recording-c2-a",
                "folder_label": "c2-to-c1",
                "source_square": "c2",
                "destination_square": "c1",
                "receipt_label": "c2 to c1",
                "metadata_status": "consistent_folder_label_and_receipt",
            },
            {
                "recording_id": "recording-c2-b",
                "folder_label": "c2-to-c1",
                "source_square": "b1",
                "destination_square": "b2",
                "receipt_label": "c2 to c1",
                "metadata_status": "conflict_folder_label_vs_receipt",
            },
            {
                "recording_id": "recording-off-scope",
                "folder_label": "b2-to-c2",
                "source_square": "e1",
                "destination_square": "f1",
                "receipt_label": "b2 to c2",
                "metadata_status": "conflict_folder_label_vs_receipt",
            },
        ]
        classified = PREPARE.classify_catalog_episodes(rows)
        self.assertEqual(len(classified), 3)
        summary = PREPARE.summarize_inventory(classified)
        self.assertEqual(
            summary["per_skill_episode_counts"]["pawn_c2_to_c1"], 2
        )
        self.assertEqual(summary["candidate_product_episode_count"], 2)
        off_scope = next(
            row
            for row in classified
            if row["recording_id"] == "recording-off-scope"
        )
        self.assertIsNone(off_scope["candidate_skill_id"])
        self.assertTrue(off_scope["adjudication_required"])
        self.assertFalse(off_scope["evaluator_admission_allowed"])

        queue = PREPARE.build_adjudication_queue(
            classified,
            catalog_sha256="1" * 64,
        )
        self.assertEqual(queue["entry_count"], 2)
        self.assertEqual(
            {entry["recording_id"] for entry in queue["entries"]},
            {"recording-c2-b", "recording-off-scope"},
        )
        self.assertIn("append_only", queue["mutation_policy"])

    def test_owner_review_accepts_only_product_markers_and_stays_nonmetric(self) -> None:
        catalog_path = (
            REPO_ROOT
            / "configs"
            / "data"
            / "physical_pawn_move_catalog_20260719.json"
        )
        owner_review_path = (
            REPO_ROOT
            / "configs"
            / "evaluations"
            / "pawn_rank12_owner_visual_review_20260719_v1.json"
        )
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        owner_review = json.loads(owner_review_path.read_text(encoding="utf-8"))
        episodes = []
        for row in PREPARE.classify_catalog_episodes(catalog["episodes"]):
            episode = {
                **row,
                "receipt_outcome_label": "success",
                "frames": [
                    {
                        "phase": "initial",
                        "path": "/tmp/initial.png",
                        "sha256": "1" * 64,
                    },
                    {
                        "phase": "final",
                        "path": "/tmp/final.png",
                        "sha256": "2" * 64,
                    },
                ],
                "visual_fiducial_proposals": {
                    "initial": {
                        "center_px": [100.0, 100.0],
                        "radius_px": 10.0,
                        "contact_center_px": [101.0, 99.0],
                        "observed_square_tone": "beige",
                        "foreground_darkness_threshold_luma": 12,
                    },
                    "final": {
                        "center_px": [100.0, 100.0],
                        "radius_px": 10.0,
                        "contact_center_px": [101.0, 99.0],
                        "observed_square_tone": "beige",
                        "foreground_darkness_threshold_luma": 12,
                    },
                },
            }
            if row["recording_id"] == "20260719T032400Z-052d5137":
                episode["visual_fiducial_proposals"]["final"].update(
                    {
                        "center_px": [462.5, 189.5],
                        "radius_px": 9.600000381469727,
                    }
                )
            episodes.append(episode)

        marker_manifest = []
        for episode in episodes:
            if episode["candidate_skill_id"] is None:
                continue
            frames = {frame["phase"]: frame for frame in episode["frames"]}
            for phase, square in (
                ("initial", episode["folder_source_square"]),
                ("final", episode["folder_destination_square"]),
            ):
                frame = frames[phase]
                fiducial = episode["visual_fiducial_proposals"][phase]
                marker_manifest.append(
                    {
                        "source_recording_id": episode["recording_id"],
                        "skill_id": episode["candidate_skill_id"],
                        "phase": phase,
                        "square": square,
                        "frame_sha256": frame["sha256"],
                        "visual_fiducial_center_px": fiducial["center_px"],
                        "visual_fiducial_radius_px": fiducial["radius_px"],
                        "inferred_contact_center_px": fiducial[
                            "contact_center_px"
                        ],
                        "square_tone": fiducial["observed_square_tone"],
                        "darkness_threshold_luma": fiducial[
                            "foreground_darkness_threshold_luma"
                        ],
                    }
                )
        owner_review["review_artifact"] = {
            "path": "/tmp/review.png",
            "panel_count": 26,
            "file_sha256": "5" * 64,
            "pixel_sha256": "6" * 64,
            "accepted_marker_manifest_sha256": PREPARE._canonical_sha256(
                marker_manifest
            ),
            "encoding_note": "test fixture",
            "banner_state": "pre_acceptance_source_artifact_preserved_for_review_lineage",
        }
        payload = PREPARE.build_owner_visual_review_payload(
            episodes,
            owner_review=owner_review,
            owner_review_config_path=owner_review_path,
            owner_review_config_sha256="3" * 64,
            catalog_path=catalog_path,
            catalog_sha256="4" * 64,
            review_sheet=Path("/tmp/review.png"),
            review_sheet_sha256="5" * 64,
            review_sheet_pixel_sha256="6" * 64,
            proposal_calibration={
                "calibration_id": PREPARE.PROPOSAL_CALIBRATION_ID,
                "matrix_sha256": PREPARE.PROPOSAL_CALIBRATION_MATRIX_SHA256,
            },
        )
        self.assertEqual(payload["accepted_product_episode_count"], 13)
        self.assertEqual(payload["accepted_visual_marker_count"], 26)
        self.assertEqual(payload["directed_skill_coverage_count"], 12)
        self.assertEqual(payload["out_of_scope_episode_count"], 5)
        self.assertEqual(payload["retrospective_operator_success_count"], 13)
        self.assertEqual(payload["metric_pose_annotation_count"], 0)
        self.assertFalse(payload["board_calibration"]["metric_use_allowed"])
        self.assertEqual(payload["research_inference_overlay_status"], "disabled")
        self.assertTrue(
            all(
                row["metric_pose_admission_allowed"] is False
                and row["simulator_or_policy_claim_allowed"] is False
                for row in payload["accepted_markers"]
            )
        )
        self.assertEqual(
            payload["accepted_marker_manifest_sha256"],
            owner_review["review_artifact"]["accepted_marker_manifest_sha256"],
        )

        episodes[0]["visual_fiducial_proposals"]["initial"]["center_px"] = [
            1.0,
            1.0,
        ]
        with self.assertRaisesRegex(RuntimeError, "marker manifest drifted"):
            PREPARE.build_owner_visual_review_payload(
                episodes,
                owner_review=owner_review,
                owner_review_config_path=owner_review_path,
                owner_review_config_sha256="3" * 64,
                catalog_path=catalog_path,
                catalog_sha256="4" * 64,
                review_sheet=Path("/tmp/review.png"),
                review_sheet_sha256="5" * 64,
                review_sheet_pixel_sha256="6" * 64,
                proposal_calibration={
                    "calibration_id": PREPARE.PROPOSAL_CALIBRATION_ID,
                    "matrix_sha256": PREPARE.PROPOSAL_CALIBRATION_MATRIX_SHA256,
                },
            )
        episodes[0]["visual_fiducial_proposals"]["initial"]["center_px"] = [
            100.0,
            100.0,
        ]
        episodes[0]["frames"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "marker manifest drifted"):
            PREPARE.build_owner_visual_review_payload(
                episodes,
                owner_review=owner_review,
                owner_review_config_path=owner_review_path,
                owner_review_config_sha256="3" * 64,
                catalog_path=catalog_path,
                catalog_sha256="4" * 64,
                review_sheet=Path("/tmp/review.png"),
                review_sheet_sha256="5" * 64,
                review_sheet_pixel_sha256="6" * 64,
                proposal_calibration={
                    "calibration_id": PREPARE.PROPOSAL_CALIBRATION_ID,
                    "matrix_sha256": PREPARE.PROPOSAL_CALIBRATION_MATRIX_SHA256,
                },
            )
        episodes[0]["frames"][0]["sha256"] = "1" * 64
        with self.assertRaisesRegex(RuntimeError, "sheet bytes drifted"):
            PREPARE.build_owner_visual_review_payload(
                episodes,
                owner_review=owner_review,
                owner_review_config_path=owner_review_path,
                owner_review_config_sha256="3" * 64,
                catalog_path=catalog_path,
                catalog_sha256="4" * 64,
                review_sheet=Path("/tmp/review.png"),
                review_sheet_sha256="7" * 64,
                review_sheet_pixel_sha256="6" * 64,
                proposal_calibration={
                    "calibration_id": PREPARE.PROPOSAL_CALIBRATION_ID,
                    "matrix_sha256": PREPARE.PROPOSAL_CALIBRATION_MATRIX_SHA256,
                },
            )

        queue = PREPARE.build_adjudication_queue(
            episodes,
            catalog_sha256="4" * 64,
        )
        reviewed = PREPARE.apply_owner_task_label_review(queue, owner_review)
        reviewed = PREPARE.apply_owner_task_label_review(reviewed, owner_review)
        self.assertEqual(reviewed["reviewed_product_correction_count"], 7)
        self.assertEqual(reviewed["deferred_out_of_scope_count"], 5)
        self.assertTrue(
            all(len(entry["review_history"]) == 1 for entry in reviewed["entries"])
        )
        self.assertEqual(
            sum(
                entry["adjudication_status"] == "reviewed_correction"
                for entry in reviewed["entries"]
            ),
            7,
        )
        self.assertEqual(
            sum(
                entry["adjudication_status"] == "deferred_out_of_scope"
                for entry in reviewed["entries"]
            ),
            5,
        )
        reviewed["entries"][0]["review_history"][0]["reviewer"] = "tampered"
        with self.assertRaisesRegex(RuntimeError, "review history drifted"):
            PREPARE.apply_owner_task_label_review(reviewed, owner_review)

    def test_centered_initial_prior_is_proposal_only_and_offset_corrected(self) -> None:
        visual_offset = np.asarray([2.0, 3.0])
        episodes = []
        for recording_id, source_square, destination_square in (
            ("recording-b", "b1", "b2"),
            ("recording-c", "c1", "c2"),
        ):
            source_nominal = np.asarray(
                PREPARE._square_center_pixel(source_square)
            )
            destination_nominal = np.asarray(
                PREPARE._square_center_pixel(destination_square)
            )
            episodes.append(
                {
                    "recording_id": recording_id,
                    "folder_source_square": source_square,
                    "folder_destination_square": destination_square,
                    "metadata_status": "consistent_folder_label_and_receipt",
                    "visual_fiducial_proposals": {
                        "initial": {
                            "center_px": (source_nominal + visual_offset).tolist()
                        },
                        "final": {
                            "center_px": (
                                destination_nominal
                                + visual_offset
                                + np.asarray([4.0, -1.0])
                            ).tolist()
                        },
                    },
                }
            )
        calibration = PREPARE.infer_contact_center_proposals(episodes)
        np.testing.assert_allclose(
            calibration["mean_visual_fiducial_minus_nominal_offset_px"],
            visual_offset,
        )
        self.assertFalse(calibration["evaluator_pose_admission_allowed"])
        self.assertIn("not_self_centering_evidence", calibration["prior_scope"])
        for episode in episodes:
            initial = episode["visual_fiducial_proposals"]["initial"]
            final = episode["visual_fiducial_proposals"]["final"]
            np.testing.assert_allclose(
                initial["signed_contact_center_offset_px"], [0.0, 0.0]
            )
            np.testing.assert_allclose(
                final["signed_contact_center_offset_px"], [4.0, -1.0]
            )
            self.assertIn(
                "signed_board_offset_mm_approximate_unreviewed", final
            )
            self.assertFalse(final["evaluator_pose_admission_allowed"])

    def test_owner_directional_retargets_remain_proposals(self) -> None:
        catalog = json.loads(
            (
                REPO_ROOT
                / "configs"
                / "data"
                / "physical_pawn_move_catalog_20260719.json"
            ).read_text(encoding="utf-8")
        )
        episodes = [
            {
                **classification,
                "visual_fiducial_proposals": {
                    "initial": {
                        "center_px": [100.0, 100.0],
                        "radius_px": 10.0,
                        "selection_method": "automatic",
                        "confidence": "medium",
                    },
                    "final": {
                        "center_px": [100.0, 100.0],
                        "radius_px": 10.0,
                        "selection_method": "automatic",
                        "confidence": "medium",
                    },
                },
            }
            for classification in PREPARE.classify_catalog_episodes(
                catalog["episodes"]
            )
        ]
        final_e2_episode = next(
            episode
            for episode in episodes
            if episode["recording_id"] == "20260719T032935Z-66894edc"
        )
        final_e2_episode["visual_fiducial_proposals"]["final"].update(
            {
                "center_px": [408.5, 213.5],
                "radius_px": 12.199999809265137,
            }
        )
        final_c2_episode = next(
            episode
            for episode in episodes
            if episode["recording_id"] == "20260719T032400Z-052d5137"
        )
        final_c2_episode["visual_fiducial_proposals"]["final"].update(
            {
                "center_px": [462.5, 190.5],
                "radius_px": 9.600000381469727,
                "observed_square_tone": "brown",
                "foreground_darkness_threshold_luma": 5,
            }
        )
        summary = PREPARE.apply_owner_visual_adjustments(episodes)
        self.assertEqual(summary["adjustment_count"], 8)
        self.assertEqual(summary["unambiguous_remap_count"], 8)
        self.assertEqual(summary["ambiguous_or_unshiftable_panel_count"], 0)
        self.assertFalse(summary["evaluator_pose_admission_allowed"])
        self.assertIn(
            "one_generated_grid_row_up_same_column",
            summary["remap_policy"],
        )
        expected_adjustments = {
            ("20260719T033023Z-fd7005f3", "initial"): ([-3.0, 3.0], 1.30),
            ("20260719T032400Z-052d5137", "final"): ([0.0, -1.0], 1.00),
            ("20260719T035317Z-2a332ab7", "final"): ([2.0, 2.0], 1.15),
            ("20260719T030206Z-af661460", "initial"): ([-3.0, 3.0], 0.80),
            ("20260719T031518Z-34bff0dd", "initial"): ([2.0, 3.0], 1.15),
            ("20260719T031518Z-34bff0dd", "final"): ([-2.0, -3.0], 1.00),
            ("20260719T032935Z-66894edc", "final"): (
                [5.0, 6.0],
                12.100000381469727 / 12.199999809265137,
            ),
            ("20260719T031615Z-0e058ca2", "final"): ([-2.0, 2.0], 1.15),
        }
        actual_adjustments = {
            (row["recording_id"], row["phase"]): (
                row["center_delta_px"],
                row["radius_scale"],
            )
            for row in summary["adjustments"]
        }
        self.assertEqual(actual_adjustments, expected_adjustments)
        final_e2_adjustment = next(
            row
            for row in summary["adjustments"]
            if row["recording_id"] == "20260719T032935Z-66894edc"
            and row["phase"] == "final"
        )
        self.assertEqual(
            final_e2_adjustment["adjusted_center_px"], [413.5, 219.5]
        )
        self.assertAlmostEqual(
            final_e2_adjustment["adjusted_radius_px"], 12.100000381469727
        )
        self.assertIn("panel_specific_redo", final_e2_adjustment)
        self.assertIn(
            "completely off",
            final_e2_adjustment["panel_specific_redo"]["reason"],
        )
        final_c2_adjustment = next(
            row
            for row in summary["adjustments"]
            if row["recording_id"] == "20260719T032400Z-052d5137"
            and row["phase"] == "final"
        )
        self.assertEqual(
            final_c2_adjustment["adjusted_center_px"], [462.5, 189.5]
        )
        self.assertAlmostEqual(
            final_c2_adjustment["adjusted_radius_px"], 9.600000381469727
        )
        self.assertEqual(
            final_c2_episode["visual_fiducial_proposals"]["final"][
                "observed_square_tone"
            ],
            "beige",
        )
        self.assertEqual(
            final_c2_episode["visual_fiducial_proposals"]["final"][
                "foreground_darkness_threshold_luma"
            ],
            12,
        )
        self.assertEqual(
            final_c2_episode["visual_fiducial_proposals"]["final"][
                "tone_selection_basis"
            ],
            "owner_corrected_chess_square_identity",
        )
        self.assertIn("panel_specific_redo", final_c2_adjustment)
        actual_grid_remap = {
            (
                row["prior_mistargeted_panel"]["recording_id"],
                row["prior_mistargeted_panel"]["phase"],
            ): (
                row["corrected_target_panel"]["recording_id"],
                row["corrected_target_panel"]["phase"],
            )
            for row in summary["adjustments"]
        }
        self.assertEqual(
            actual_grid_remap,
            {
                ("20260719T035317Z-2a332ab7", "initial"): (
                    "20260719T033023Z-fd7005f3",
                    "initial",
                ),
                ("20260719T030206Z-af661460", "final"): (
                    "20260719T032400Z-052d5137",
                    "final",
                ),
                ("20260719T031324Z-bf91502b", "final"): (
                    "20260719T035317Z-2a332ab7",
                    "final",
                ),
                ("20260719T031518Z-34bff0dd", "initial"): (
                    "20260719T030206Z-af661460",
                    "initial",
                ),
                ("20260719T035413Z-5ab5603f", "initial"): (
                    "20260719T031518Z-34bff0dd",
                    "initial",
                ),
                ("20260719T035413Z-5ab5603f", "final"): (
                    "20260719T031518Z-34bff0dd",
                    "final",
                ),
                ("20260719T032853Z-1ee203e8", "final"): (
                    "20260719T032935Z-66894edc",
                    "final",
                ),
                ("20260719T032620Z-0c7e3d86", "final"): (
                    "20260719T031615Z-0e058ca2",
                    "final",
                ),
            },
        )
        self.assertTrue(
            all(
                row["prior_mistargeted_panel"]["row"]
                == row["corrected_target_panel"]["row"] + 1
                and row["prior_mistargeted_panel"]["column"]
                == row["corrected_target_panel"]["column"]
                for row in summary["adjustments"]
            )
        )
        adjusted = [
            proposal
            for episode in episodes
            for proposal in episode["visual_fiducial_proposals"].values()
            if "owner_visual_adjustment" in proposal
        ]
        self.assertEqual(len(adjusted), 8)
        self.assertTrue(
            all(
                proposal["evaluator_pose_admission_allowed"] is False
                for proposal in adjusted
            )
        )
        self.assertTrue(
            all(
                proposal["owner_visual_adjustment"]["status"]
                == "proposed_pending_human_review"
                for proposal in adjusted
            )
        )
        self.assertTrue(
            all(
                "not_exact_coordinate_acceptance"
                in proposal["owner_visual_adjustment"]["claim_boundary"]
                for proposal in adjusted
            )
        )

    def test_proposal_homography_cannot_be_evaluator_calibration(self) -> None:
        payload = PREPARE.proposal_calibration_payload(
            reference_frame_path="frame.png",
            reference_frame_sha256="2" * 64,
        )
        self.assertEqual(payload["review_status"], "unreviewed_proposal_only")
        self.assertFalse(payload["evaluator_calibration_admission_allowed"])
        self.assertEqual(
            payload["matrix_sha256"], PREPARE.PROPOSAL_CALIBRATION_MATRIX_SHA256
        )
        self.assertEqual(
            payload["board_offset_semantics"],
            "approximate_unreviewed_mm_for_proposal_review_only",
        )


if __name__ == "__main__":
    unittest.main()

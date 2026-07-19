from __future__ import annotations

import importlib.util
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

from __future__ import annotations

import unittest

import numpy as np

from sim2claw.pawn_groot_dataset import (
    _target_index_matrix,
    load_pawn_groot_dataset_contract,
)


class PawnGrootDatasetTest(unittest.TestCase):
    def test_contract_binds_current_100mm_case_and_zero_heldout_rows(self) -> None:
        contract = load_pawn_groot_dataset_contract()
        self.assertEqual(
            contract["scene"]["workspace_pose_id"],
            "workspace_board_fiducial_robotward_100mm_20260718_v3",
        )
        self.assertEqual(
            contract["scene"]["board_pose_id"],
            "board_robotward_100mm_20260718_v3",
        )
        self.assertEqual(
            contract["scene"]["board_center_in_table_frame_xy_m"],
            [0.04, -0.065],
        )
        self.assertEqual(contract["dataset"]["episode_count"], 1)
        self.assertEqual(contract["dataset"]["frame_count"], 562)
        self.assertEqual(contract["dataset"]["held_out_rows"], 0)
        self.assertEqual(
            contract["dataset"]["relative_stats_payload"],
            "canonical_empty_json_object_for_absolute_actions",
        )
        self.assertEqual(contract["splits"]["held_out_training_rows"], 0)
        source = contract["source"]["episodes"][0]
        self.assertEqual(source["piece_id"], "tan_pawn_c8")
        self.assertEqual(source["destination_square"], "a6")
        self.assertTrue(source["strict_success_required"])
        self.assertEqual(source["assistance_frames"], 0)
        self.assertFalse(source["held_out_membership"])

    def test_action_chunks_cover_the_exact_unpadded_denominator(self) -> None:
        indices = _target_index_matrix(562, 16)
        self.assertEqual(indices.shape, (547, 16))
        self.assertEqual(indices.size, 8752)
        self.assertEqual(indices[0].tolist(), list(range(16)))
        self.assertEqual(indices[-1].tolist(), list(range(546, 562)))
        self.assertEqual(set(indices.reshape(-1).tolist()), set(range(562)))
        self.assertTrue(np.array_equal(indices[:, 0], np.arange(547)))

    def test_dataset_contract_keeps_training_and_promotion_separate(self) -> None:
        authority = load_pawn_groot_dataset_contract()["authority"]
        self.assertTrue(authority["only_evaluator_admitted_rows_may_enter"])
        self.assertFalse(authority["raw_failures_may_enter_behavior_cloning"])
        self.assertTrue(authority["dataset_builder_cannot_declare_task_success"])
        self.assertTrue(authority["training_cannot_promote"])
        self.assertTrue(authority["held_out_remains_sealed"])
        self.assertFalse(authority["physical_authority"])


if __name__ == "__main__":
    unittest.main()

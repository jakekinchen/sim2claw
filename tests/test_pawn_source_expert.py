from __future__ import annotations

import unittest

from sim2claw.pawn_source_expert import (
    DESTINATION_SQUARE,
    LIFT_CLEARANCE_M,
    PAWN_JAW_SHUT_RAD,
    PAWN_NECK_HEIGHT_M,
    SOURCE_PIECE_ID,
    expected_action_count,
    expert_phase_counts,
)
from sim2claw.source_episode import CONTRACT_PATH_V3, load_source_contract


class PawnSourceExpertTest(unittest.TestCase):
    def test_frozen_schedule_is_complete_and_bounded(self) -> None:
        counts = expert_phase_counts()
        self.assertEqual(expected_action_count(), 562)
        self.assertEqual(sum(counts.values()), 562)
        self.assertEqual(counts["transit"], 120)
        self.assertEqual(counts["lower"], 90)
        self.assertEqual(counts["vertical_extract"], 35)
        self.assertEqual(counts["open_clear"], 25)
        self.assertLessEqual(max(counts.values()), 120)

    def test_expert_uses_training_owned_current_scene_case(self) -> None:
        contract = load_source_contract(CONTRACT_PATH_V3)
        self.assertIn(SOURCE_PIECE_ID, contract["splits"]["training_source_piece_ids"])
        self.assertNotIn(SOURCE_PIECE_ID, contract["splits"]["held_out_source_piece_ids"])
        self.assertIn(DESTINATION_SQUARE, contract["scene"]["destination_squares"])
        self.assertEqual(PAWN_JAW_SHUT_RAD, -0.15)
        self.assertEqual(PAWN_NECK_HEIGHT_M, 0.038)
        self.assertEqual(SOURCE_PIECE_ID, "tan_pawn_c8")
        self.assertEqual(DESTINATION_SQUARE, "a6")
        self.assertEqual(LIFT_CLEARANCE_M, 0.09)
        self.assertEqual(
            contract["simulation_reset"]["reset_id"],
            "c8_standoff_collision_free_reset_v1",
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from sim2claw.pawn_source_expert import (
    DESTINATION_SQUARE,
    SOURCE_PIECE_ID,
    expected_action_count,
    expert_phase_counts,
)
from sim2claw.source_episode import load_source_contract


class PawnSourceExpertTest(unittest.TestCase):
    def test_frozen_schedule_is_complete_and_bounded(self) -> None:
        counts = expert_phase_counts()
        self.assertEqual(expected_action_count(), 562)
        self.assertEqual(sum(counts.values()), 562)
        self.assertEqual(counts["transit"], 120)
        self.assertEqual(counts["lower"], 90)
        self.assertLessEqual(max(counts.values()), 120)

    def test_expert_uses_training_owned_scene_v2_case(self) -> None:
        contract = load_source_contract()
        self.assertIn(SOURCE_PIECE_ID, contract["splits"]["training_source_piece_ids"])
        self.assertNotIn(SOURCE_PIECE_ID, contract["splits"]["held_out_source_piece_ids"])
        self.assertIn(DESTINATION_SQUARE, contract["scene"]["destination_squares"])


if __name__ == "__main__":
    unittest.main()

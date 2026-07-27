from __future__ import annotations

import unittest

from sim2claw.pawn_source_expert import (
    DESTINATION_SQUARE,
    LIFT_CLEARANCE_M,
    PAWN_JAW_SHUT_RAD,
    PAWN_NECK_HEIGHT_M,
    ROBUST_MARGIN_PROFILE_PATH,
    SOURCE_PIECE_ID,
    expected_action_count,
    expert_phase_counts,
    load_expert_profile,
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

    def test_robust_margin_profile_is_simulation_only_and_preregistered(self) -> None:
        payload = load_expert_profile(ROBUST_MARGIN_PROFILE_PATH)
        self.assertEqual(
            payload["profile_id"], "c8_a6_robust_margin_profile_v1"
        )
        self.assertFalse(payload["physical_authority"])
        self.assertEqual(
            payload["selection_boundary"],
            {
                "action_frozen_after_selection": True,
                "board_x_mm": 0.5,
                "board_y_mm": 0.5,
                "board_yaw_deg": 0.1,
                "joint_zero_deg": 0.1,
                "assistance_frames": 0,
            },
        )
        self.assertEqual(
            payload["profile"]["grasp_offset_xyz_m"],
            [-0.004, -0.0015, 0.0],
        )
        self.assertEqual(
            payload["profile"]["closed_jaw_joint_target_rad"], -0.17453
        )
        self.assertEqual(
            payload["profile"]["partial_release_joint_target_rad"], 0.8
        )

    def test_centered_grasp_follow_up_changes_only_preregistered_offset(self) -> None:
        baseline = load_expert_profile(ROBUST_MARGIN_PROFILE_PATH)
        candidate = load_expert_profile(
            ROBUST_MARGIN_PROFILE_PATH.with_name(
                "c8_a6_preregistered_centered_grasp_v1.json"
            )
        )
        self.assertEqual(
            candidate["profile_id"], "c8_a6_preregistered_centered_grasp_v1"
        )
        self.assertFalse(candidate["physical_authority"])
        self.assertEqual(
            candidate["selection_boundary"], baseline["selection_boundary"]
        )
        candidate_profile = dict(candidate["profile"])
        baseline_profile = dict(baseline["profile"])
        self.assertEqual(
            candidate_profile.pop("grasp_offset_xyz_m"),
            [-0.004, -0.002, 0.0015],
        )
        baseline_profile.pop("grasp_offset_xyz_m")
        self.assertEqual(candidate_profile, baseline_profile)

    def test_jaw_margin_follow_up_changes_only_closed_jaw_target(self) -> None:
        centered_path = ROBUST_MARGIN_PROFILE_PATH.with_name(
            "c8_a6_preregistered_centered_grasp_v1.json"
        )
        baseline = load_expert_profile(centered_path)
        candidate = load_expert_profile(
            centered_path.with_name("c8_a6_preregistered_jaw_margin_v1.json")
        )
        self.assertEqual(
            candidate["profile_id"], "c8_a6_preregistered_jaw_margin_v1"
        )
        self.assertFalse(candidate["physical_authority"])
        self.assertEqual(
            candidate["selection_boundary"], baseline["selection_boundary"]
        )
        candidate_profile = dict(candidate["profile"])
        baseline_profile = dict(baseline["profile"])
        self.assertEqual(
            candidate_profile.pop("closed_jaw_joint_target_rad"),
            -0.1727003294848389,
        )
        baseline_profile.pop("closed_jaw_joint_target_rad")
        self.assertEqual(candidate_profile, baseline_profile)


if __name__ == "__main__":
    unittest.main()

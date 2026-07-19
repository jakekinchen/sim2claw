from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sim2claw.sim_real_bridge import (
    inspect_sim_real_bridge,
    joint_response_metrics,
    load_bridge_contract,
)


class SimRealBridgeTest(unittest.TestCase):
    def test_contract_binds_100mm_sim_and_72mm_physical_cohort(self) -> None:
        contract = load_bridge_contract()
        self.assertEqual(
            contract["current_simulation"]["board_pose_id"],
            "board_robotward_100mm_20260718_v3",
        )
        self.assertEqual(
            contract["physical_source_cohort"]["recorded_board_pose_id"],
            "board_robotward_72mm_20260718_v2",
        )
        self.assertFalse(
            contract["policy_lineage"]["physical_source_is_a_learned_policy"]
        )
        self.assertFalse(
            contract["policy_lineage"]["historical_groot_checkpoint"][
                "pawn_authority"
            ]
        )

    def test_missing_owner_local_payloads_fail_closed_without_training_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            receipt = inspect_sim_real_bridge(
                physical_root=Path(temporary) / "missing",
                checkpoint_root=Path(temporary) / "checkpoint",
            )
        self.assertFalse(
            receipt["physical_source"]["all_raw_payloads_verified"]
        )
        self.assertEqual(len(receipt["physical_source"]["episodes"]), 5)
        self.assertEqual(receipt["training_rows_authorized"], 0)
        self.assertEqual(receipt["held_out_rows_used"], 0)
        self.assertFalse(receipt["brev_authorized_to_start"])
        self.assertIn(
            "physical_pixels_and_square_labels_bind_72mm_not_current_100mm",
            receipt["blockers"],
        )

    def test_joint_response_metrics_detect_one_sample_delay(self) -> None:
        rows = []
        for index in range(12):
            command = [float(index * (joint + 1)) for joint in range(6)]
            previous = max(0, index - 1)
            actual = [float(previous * (joint + 1)) for joint in range(6)]
            rows.append(
                {
                    "follower_command_degrees": command,
                    "follower_actual_position_degrees": actual,
                    "rate_limited": index in {3, 7},
                }
            )
        metrics = joint_response_metrics(
            rows, sample_hz=20, maximum_lag_seconds=0.5
        )
        self.assertEqual(metrics["best_lag_samples"], [1] * 6)
        self.assertEqual(metrics["rate_limited_sample_count"], 2)
        self.assertAlmostEqual(metrics["rate_limited_sample_fraction"], 1 / 6)


if __name__ == "__main__":
    unittest.main()

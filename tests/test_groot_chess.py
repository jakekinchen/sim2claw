from __future__ import annotations

import unittest

import numpy as np

from sim2claw.groot_chess import (
    collect_groot_expert_episode,
    load_groot_task_contract,
)
from sim2claw.scene import (
    board_square_center,
    registered_board_center,
    scene_geometry,
)
from sim2claw.capture import load_capture_config
from sim2claw.paths import DEFAULT_CAPTURE_CONFIG


class GrootChessContractTest(unittest.TestCase):
    def test_contract_freezes_language_conditioned_disjoint_splits(self) -> None:
        task = load_groot_task_contract()
        training_cases = {case["case_id"] for case in task["training_cases"]}
        held_out_cases = {case["case_id"] for case in task["held_out_cases"]}
        self.assertFalse(training_cases & held_out_cases)
        self.assertTrue(all(case["instruction"] for case in task["training_cases"]))
        self.assertEqual(task["model"]["embodiment_tag"], "NEW_EMBODIMENT")
        self.assertFalse(task["diagnostic_reward"]["promotion_authority"])
        self.assertTrue(task["authority"]["training_cannot_promote_itself"])

    def test_square_centers_follow_the_frozen_board_geometry(self) -> None:
        task = load_groot_task_contract()
        frozen_center = registered_board_center(task["scene"]["scene_id"])
        self.assertEqual(frozen_center, (0.04, -0.165))
        config = load_capture_config(DEFAULT_CAPTURE_CONFIG)
        config["simulation_estimates"]["board"][
            "center_in_table_frame_xy_m"
        ] = list(frozen_center)
        geometry = scene_geometry(config)
        a8 = np.asarray(
            board_square_center(
                "a8", board_center_in_table_frame_xy_m=frozen_center
            )
        )
        b8 = np.asarray(
            board_square_center(
                "b8", board_center_in_table_frame_xy_m=frozen_center
            )
        )
        self.assertAlmostEqual(
            float(np.linalg.norm(b8[:2] - a8[:2])),
            geometry.square_size,
            places=8,
        )
        with self.assertRaises(ValueError):
            board_square_center("i9")

    def test_held_out_rook_and_king_experts_pass_frozen_gates(self) -> None:
        task = load_groot_task_contract()
        episodes = [
            collect_groot_expert_episode(
                task,
                split="held_out",
                episode_index=index,
                render_frames=False,
            )
            for index in (0, 2)
        ]
        self.assertEqual({episode.piece for episode in episodes}, {
            "black_rook_a8",
            "black_king_e8",
        })
        for episode in episodes:
            self.assertTrue(episode.verdict["success"])
            self.assertEqual(episode.states.shape, (363, 6))
            self.assertEqual(episode.actions.shape, (363, 6))
            self.assertFalse(
                episode.verdict["diagnostic_reward_has_promotion_authority"]
            )
            self.assertEqual(
                episode.state_trace["schema_version"],
                "sim2claw.mujoco_body_state_trace.v1",
            )
            self.assertGreater(episode.state_trace["frame_count"], 250)


if __name__ == "__main__":
    unittest.main()

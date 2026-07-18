from __future__ import annotations

import unittest

import numpy as np

from sim2claw.groot_chess import (
    collect_groot_expert_episode,
    load_groot_task_contract,
    resolve_execution_horizon,
)
from sim2claw.scene import board_square_center, scene_geometry
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
        geometry = scene_geometry(load_capture_config(DEFAULT_CAPTURE_CONFIG))
        a8 = np.asarray(board_square_center("a8"))
        b8 = np.asarray(board_square_center("b8"))
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
            self.assertTrue(episode.verdict["task_consequence_success"])
            self.assertTrue(episode.verdict["success"])
            self.assertEqual(episode.states.shape, (363, 6))
            self.assertEqual(episode.actions.shape, (363, 6))
            self.assertFalse(
                episode.verdict["diagnostic_reward_has_promotion_authority"]
            )

    def test_execution_horizon_cannot_exceed_model_prediction(self) -> None:
        self.assertEqual(
            resolve_execution_horizon(None, model_action_horizon=16),
            16,
        )
        self.assertEqual(
            resolve_execution_horizon(8, model_action_horizon=16),
            8,
        )
        for invalid in (0, 17):
            with self.assertRaises(ValueError):
                resolve_execution_horizon(invalid, model_action_horizon=16)


if __name__ == "__main__":
    unittest.main()

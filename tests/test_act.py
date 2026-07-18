from __future__ import annotations

import unittest

import torch

from sim2claw.act_model import ACTModelConfig, ACTPolicy
from sim2claw.chess_task import collect_expert_episode, load_task_contract


class ACTContractTest(unittest.TestCase):
    def test_task_freezes_disjoint_train_and_evaluation_splits(self) -> None:
        task = load_task_contract()
        self.assertTrue(task["frozen_before_training"])
        self.assertFalse(
            set(task["training_split"]["seeds"])
            & set(task["held_out_split"]["seeds"])
        )
        self.assertEqual(task["held_out_split"]["training_rows"], 0)
        self.assertEqual(task["observation"]["n_obs_steps"], 1)
        self.assertEqual(task["act"]["n_action_steps"], 50)
        self.assertEqual(task["evaluator"]["device"], "cpu")
        self.assertEqual(task["evaluator"]["dtype"], "float32")

    def test_act_predicts_one_finite_action_chunk(self) -> None:
        task = load_task_contract()
        config = ACTModelConfig.from_task(task)
        torch.manual_seed(7)
        model = ACTPolicy(config)
        observation = torch.zeros(2, config.observation_dim)
        predicted = model.predict_action_chunk(observation)
        self.assertEqual(
            tuple(predicted.shape),
            (2, config.chunk_size, config.action_dim),
        )
        self.assertTrue(torch.isfinite(predicted).all())

    def test_default_expert_fixture_lifts_and_holds_rook(self) -> None:
        task = load_task_contract()
        episode = collect_expert_episode(
            task,
            seed=task["held_out_split"]["seeds"][0],
            piece_offset_xy_m=(0.0, 0.0),
        )
        self.assertGreaterEqual(
            episode.maximum_piece_rise_m,
            task["evaluator"]["minimum_piece_rise_m"],
        )
        self.assertGreaterEqual(
            episode.final_piece_height_m - episode.initial_piece_height_m,
            task["evaluator"]["minimum_final_piece_rise_m"],
        )
        final_window = task["evaluator"]["final_contact_window_control_steps"]
        self.assertEqual(float(episode.jaw_piece_contacts[-final_window:].mean()), 1.0)


if __name__ == "__main__":
    unittest.main()

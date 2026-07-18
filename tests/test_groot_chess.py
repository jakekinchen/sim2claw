from __future__ import annotations

import unittest

import numpy as np

from sim2claw.groot_chess import (
    collect_groot_expert_episode,
    load_groot_task_contract,
    resolve_execution_horizon,
)
from sim2claw.groot_consensus import (
    action_sha256,
    aggregate_action_proposals,
    proposal_seed,
    query_seed,
)
from sim2claw.groot_execution import physics_targets_from_waypoints, sample_phase
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


class GrootConsensusTest(unittest.TestCase):
    @staticmethod
    def _proposal(value: float) -> dict[str, np.ndarray]:
        return {
            "single_arm": np.full((1, 16, 5), value, dtype=np.float32),
            "gripper": np.full((1, 16, 1), value, dtype=np.float32),
        }

    def test_first_proposal_retains_original_query_seed(self) -> None:
        baseline = query_seed(9301, 16)
        self.assertEqual(proposal_seed(9301, 16, 0), baseline)
        self.assertEqual(proposal_seed(9301, 16, 1), proposal_seed(9301, 16, 1))
        self.assertNotEqual(proposal_seed(9301, 16, 1), baseline)
        self.assertNotEqual(
            proposal_seed(9301, 16, 1),
            proposal_seed(9301, 16, 2),
        )

    def test_medoid_selects_a_complete_model_proposal(self) -> None:
        proposals = [
            self._proposal(0.0),
            self._proposal(1.0),
            self._proposal(10.0),
        ]
        aggregate, diagnostics = aggregate_action_proposals(
            proposals,
            method="medoid",
        )
        self.assertEqual(diagnostics["selected_proposal_index"], 1)
        self.assertEqual(
            diagnostics["aggregate_action_sha256"],
            action_sha256(proposals[1]),
        )
        np.testing.assert_array_equal(aggregate["single_arm"], 1.0)

    def test_median_and_trimmed_mean_reject_outlier(self) -> None:
        proposals = [
            self._proposal(value) for value in (0.0, 1.0, 2.0, 3.0, 100.0)
        ]
        median, median_diagnostics = aggregate_action_proposals(
            proposals,
            method="median",
        )
        trimmed, trimmed_diagnostics = aggregate_action_proposals(
            proposals,
            method="trimmed_mean",
        )
        np.testing.assert_array_equal(median["gripper"], 2.0)
        np.testing.assert_array_equal(trimmed["gripper"], 2.0)
        self.assertIsNone(median_diagnostics["selected_proposal_index"])
        self.assertIsNone(trimmed_diagnostics["selected_proposal_index"])

    def test_aggregation_rejects_nonfinite_and_mismatched_actions(self) -> None:
        invalid = self._proposal(0.0)
        invalid["gripper"][0, 0, 0] = np.nan
        with self.assertRaises(ValueError):
            aggregate_action_proposals([invalid], method="mean")
        with self.assertRaises(ValueError):
            aggregate_action_proposals(
                [self._proposal(0.0), {"single_arm": np.zeros((1, 16, 5))}],
                method="mean",
            )


class GrootExecutionAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = load_groot_task_contract()

    def test_sample_phase_respects_frozen_phase_boundaries(self) -> None:
        self.assertEqual(sample_phase(self.contract, 0), "stand_off")
        self.assertEqual(sample_phase(self.contract, 41), "stand_off")
        self.assertEqual(sample_phase(self.contract, 42), "advance")
        self.assertEqual(sample_phase(self.contract, 322), "retreat")
        self.assertEqual(sample_phase(self.contract, 323), "settle")
        self.assertEqual(sample_phase(self.contract, 362), "settle")
        with self.assertRaises(ValueError):
            sample_phase(self.contract, 363)

    def test_linear_adapter_reconstructs_internal_ramp_without_reaching_next(self) -> None:
        current = np.zeros(6, dtype=np.float32)
        next_waypoint = np.full(6, 10.0, dtype=np.float32)
        targets, info = physics_targets_from_waypoints(
            self.contract,
            sample_step=0,
            current=current,
            next_waypoint=next_waypoint,
            adapter="linear_same_phase",
        )
        self.assertTrue(info["interpolated_to_next_waypoint"])
        np.testing.assert_array_equal(targets[0], 0.0)
        np.testing.assert_array_equal(targets[-1], 9.0)

    def test_linear_adapter_holds_at_phase_boundary(self) -> None:
        current = np.full(6, 2.0, dtype=np.float32)
        targets, info = physics_targets_from_waypoints(
            self.contract,
            sample_step=41,
            current=current,
            next_waypoint=np.full(6, 4.0, dtype=np.float32),
            adapter="linear_same_phase",
        )
        self.assertFalse(info["interpolated_to_next_waypoint"])
        np.testing.assert_array_equal(targets, 2.0)


if __name__ == "__main__":
    unittest.main()

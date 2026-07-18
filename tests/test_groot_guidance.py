from __future__ import annotations

import unittest

import numpy as np

from sim2claw.chess_task import ChessRookLiftEnv, _goal_vector
from sim2claw.grasp import JAW_OPEN_RAD, _solve_reach
from sim2claw.groot_chess import (
    _apply_sparse_board_curriculum,
    _case_map,
    _episode_shim,
    groot_task_contract_sha256,
    load_groot_task_contract,
)
from sim2claw.groot_guidance import (
    guidance_contract_sha256,
    guidance_score,
    load_guidance_contract,
    make_guidance_context,
    phase_for_sample_step,
    simulate_candidate,
)
from sim2claw.scene import board_square_center


class GrootGuidanceTest(unittest.TestCase):
    def test_guidance_contract_is_bound_to_base_task(self) -> None:
        contract = load_guidance_contract()
        self.assertEqual(
            contract["base_task_contract_sha256"],
            groot_task_contract_sha256(),
        )
        self.assertEqual(len(guidance_contract_sha256()), 64)
        self.assertTrue(contract["authority"]["guided_selection_counts_as_assistance"])

    def test_pre_grasp_target_disturbance_is_hard_rejected(self) -> None:
        contract = load_guidance_contract()
        safe = {
            "phase": "stand_off",
            "phase_goal_proximity": 1.0,
            "jaw_open_proximity": 1.0,
            "maximum_other_piece_displacement_m": 0.0,
            "target_planar_displacement_m": 0.0,
            "upright_cosine": 1.0,
            "piece_height_m": 0.03,
            "initial_piece_height_m": 0.03,
        }
        disturbed = dict(safe)
        disturbed["target_planar_displacement_m"] = 0.02
        disturbed["upright_cosine"] = 0.0
        safe_score = guidance_score(safe, contract, control_delta_rad=0.0)
        disturbed_score = guidance_score(disturbed, contract, control_delta_rad=0.0)
        self.assertGreater(safe_score - disturbed_score, 1000.0)

    def test_sample_phase_boundaries(self) -> None:
        contract = load_groot_task_contract()
        self.assertEqual(phase_for_sample_step(contract, 0), "stand_off")
        self.assertEqual(phase_for_sample_step(contract, 41), "stand_off")
        self.assertEqual(phase_for_sample_step(contract, 42), "advance")
        self.assertEqual(phase_for_sample_step(contract, 79), "advance")
        self.assertEqual(phase_for_sample_step(contract, 80), "close")
        self.assertEqual(phase_for_sample_step(contract, 322), "retreat")
        self.assertEqual(phase_for_sample_step(contract, 323), "settle")

    def test_simulated_expert_stand_off_beats_hold_and_restores_state(self) -> None:
        base_contract = load_groot_task_contract()
        guidance_contract = load_guidance_contract()
        row = base_contract["training_episodes"][0]
        case = _case_map(base_contract, "training")[row["case_id"]]
        env = ChessRookLiftEnv(
            _episode_shim(base_contract, case),
            seed=int(row["seed"]),
            piece_offset_xy_m=tuple(row["piece_planar_offset_m"]),
        )
        _apply_sparse_board_curriculum(env, base_contract)
        context = make_guidance_context(
            env,
            base_contract,
            np.asarray(board_square_center(case["target_square"])),
        )
        pose, residual = _solve_reach(
            env.model,
            env.data,
            env.arm,
            context.stand_off_position,
            env.pinch_local,
        )
        self.assertLess(residual, 0.003)
        expert_goal = _goal_vector(pose, JAW_OPEN_RAD)
        qpos_before = env.data.qpos.copy()
        hold = simulate_candidate(
            env,
            base_contract,
            guidance_contract,
            context,
            np.tile(env.controls(), (4, 1)),
            sample_step=0,
            execution_horizon=4,
        )
        expert = simulate_candidate(
            env,
            base_contract,
            guidance_contract,
            context,
            np.tile(expert_goal, (4, 1)),
            sample_step=0,
            execution_horizon=4,
        )
        self.assertGreater(expert["score"], hold["score"])
        np.testing.assert_array_equal(env.data.qpos, qpos_before)


if __name__ == "__main__":
    unittest.main()

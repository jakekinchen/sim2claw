from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import mujoco
import numpy as np

from sim2claw.groot_consensus import aggregate_action_proposals
from sim2claw.groot_execution import aggregate_temporal_action
from sim2claw.pawn_policy_evaluator import (
    DESTINATION_SQUARE,
    ROLLOUT_SCHEMA,
    SAMPLE_COUNT,
    TARGET_PIECE_ID,
    build_frozen_pawn_development_runtime,
    evaluate_policy_rollout,
    integration_state,
)


class PawnPolicyEvaluatorTest(unittest.TestCase):
    def test_frozen_spatial_and_temporal_aggregation(self) -> None:
        proposals = [
            {
                "single_arm": np.full((1, 16, 5), value, dtype=np.float32),
                "gripper": np.full((1, 16, 1), value, dtype=np.float32),
            }
            for value in (0.0, 1.0, 2.0, 3.0, 100.0)
        ]
        spatial, spatial_info = aggregate_action_proposals(
            proposals, method="median"
        )
        np.testing.assert_array_equal(spatial["single_arm"], 2.0)
        self.assertEqual(spatial_info["proposal_count"], 5)

        chunks = [
            (0, np.zeros((16, 6), dtype=np.float32)),
            (8, np.full((16, 6), 2.0, dtype=np.float32)),
        ]
        temporal, temporal_info = aggregate_temporal_action(
            chunks, sample_step=8, method="mean"
        )
        np.testing.assert_array_equal(temporal, 1.0)
        self.assertEqual(temporal_info["source_query_steps"], [0, 8])

    def test_frozen_reset_is_repeatable_and_has_sixteen_pawns(self) -> None:
        first = build_frozen_pawn_development_runtime()
        second = build_frozen_pawn_development_runtime()
        self.assertEqual(len(first.piece_bodies), 16)
        self.assertEqual(set(first.piece_bodies), set(second.piece_bodies))
        np.testing.assert_array_equal(first.initial_state, second.initial_state)

    def test_constant_model_chunks_replay_exactly_but_do_not_pass_task(self) -> None:
        runtime = build_frozen_pawn_development_runtime()
        action = np.asarray(
            runtime.data.ctrl[runtime.actuator_ids], dtype=np.float32
        ).copy()
        actions = np.repeat(action[None, :], SAMPLE_COUNT, axis=0)
        query_starts = np.arange(0, SAMPLE_COUNT, 8, dtype=np.int64)
        query_chunks = np.repeat(
            action[None, None, :], len(query_starts), axis=0
        )
        query_chunks = np.repeat(query_chunks, 16, axis=1)
        for row in actions:
            runtime.data.ctrl[runtime.actuator_ids] = row.astype(np.float64)
            for _ in range(10):
                mujoco.mj_step(runtime.model, runtime.data)
        final_state = integration_state(runtime.model, runtime.data)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            np.savez_compressed(
                root / "trajectory.npz",
                actions=actions,
                initial_integration_state=runtime.initial_state,
                final_integration_state=final_state,
                query_starts=query_starts,
                query_chunks=query_chunks,
            )
            (root / "rollout_receipt.json").write_text(
                json.dumps(
                    {
                        "schema_version": ROLLOUT_SCHEMA,
                        "piece_id": TARGET_PIECE_ID,
                        "destination_square": DESTINATION_SQUARE,
                        "action_owner": "learned_policy",
                        "all_actions_model_derived": True,
                        "assistance_frames": 0,
                        "render_backend": "osmesa",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            result = evaluate_policy_rollout(
                root, output_path=root / "evaluation.json"
            )

        self.assertTrue(result["exact_final_mjstate_replay"])
        self.assertFalse(result["strict_success"])
        self.assertIn("minimum_piece_rise", result["failed_gates"])
        self.assertEqual(result["sample_count"], SAMPLE_COUNT)
        self.assertEqual(result["query_count"], len(query_starts))
        self.assertEqual(result["assistance_frames"], 0)


if __name__ == "__main__":
    unittest.main()

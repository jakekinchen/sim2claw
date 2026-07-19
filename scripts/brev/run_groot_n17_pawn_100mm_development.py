#!/usr/bin/env python3
"""Run the single frozen zero-assistance pawn GR00T development rollout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from gr00t.policy.server_client import PolicyClient
from sim2claw.groot_chess import _write_video
from sim2claw.groot_execution import aggregate_temporal_action
from sim2claw.pawn_policy_evaluator import (
    DESTINATION_SQUARE,
    ROLLOUT_SCHEMA,
    SAMPLE_COUNT,
    TARGET_PIECE_ID,
    build_frozen_pawn_development_runtime,
    integration_state,
)
from sim2claw.source_episode import sha256_file


INSTRUCTION = "Pick up the tan pawn on c8 and place it upright on the empty square a6."
MODEL_HORIZON = 16
EXECUTION_HORIZON = 8
PROPOSAL_COUNT = 5
NOISE_SCALE = 0.5
INFERENCE_TIMESTEPS = 4


def _json_safe(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _array_sha256(value: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5555)
    parser.add_argument("--checkpoint-id", required=True)
    parser.add_argument("--checkpoint-manifest-sha256", required=True)
    parser.add_argument("--selector-receipt-sha256", required=True)
    parser.add_argument("--experiment-sha256", required=True)
    parser.add_argument("--inference-seed", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.inference_seed != 0:
        parser.error("the frozen rollout inference seed is exactly zero")
    if os.environ.get("MUJOCO_GL") != "osmesa":
        parser.error("the frozen rollout requires MUJOCO_GL=osmesa")
    if args.output.exists():
        parser.error("rollout output must not already exist")

    runtime = build_frozen_pawn_development_runtime()
    model, data = runtime.model, runtime.data
    renderer = mujoco.Renderer(model, height=224, width=224)
    client = PolicyClient(host=args.host, port=args.port, timeout_ms=120_000, strict=False)
    if not client.ping():
        raise RuntimeError("pawn GR00T policy server did not answer ping")
    reset_info = client.reset(
        options={
            "inference_seed": args.inference_seed,
            "proposal_count": PROPOSAL_COUNT,
            "action_aggregation": "median",
            "noise_scale": NOISE_SCALE,
            "num_inference_timesteps": INFERENCE_TIMESTEPS,
        }
    )
    expected_reset = {
        "inference_seed": 0,
        "proposal_count": PROPOSAL_COUNT,
        "action_aggregation": "median",
        "noise_scale": NOISE_SCALE,
        "num_inference_timesteps": INFERENCE_TIMESTEPS,
        "rng_reset": True,
    }
    for key, expected in expected_reset.items():
        if reset_info.get(key) != expected:
            raise RuntimeError(f"policy server acknowledged wrong {key}")

    args.output.mkdir(parents=True)
    initial_state = runtime.initial_state.copy()
    frames: list[np.ndarray] = []
    states: list[np.ndarray] = []
    actions: list[np.ndarray] = []
    query_starts: list[int] = []
    query_chunks: list[np.ndarray] = []
    query_receipts: list[dict[str, Any]] = []
    chunk_history: list[tuple[int, np.ndarray]] = []
    temporal_candidate_counts: list[int] = []
    bounds = model.actuator_ctrlrange[runtime.actuator_ids]
    clipped_coordinates = 0

    try:
        for sample_step in range(SAMPLE_COUNT):
            renderer.update_scene(data, camera="overhead")
            frame = renderer.render().copy()
            state = np.asarray(data.qpos[runtime.qpos_addresses], dtype=np.float32).copy()
            frames.append(frame)
            states.append(state)

            if sample_step % EXECUTION_HORIZON == 0:
                observation = {
                    "video": {"front": frame[None, None, ...]},
                    "state": {
                        "single_arm": state[None, None, :5],
                        "gripper": state[None, None, 5:],
                    },
                    "language": {
                        "annotation.human.task_description": [[INSTRUCTION]]
                    },
                }
                predicted, action_info = client.get_action(
                    observation,
                    options={"sample_step": sample_step},
                )
                if int(action_info.get("sample_step", -1)) != sample_step:
                    raise RuntimeError("policy server acknowledged the wrong sample step")
                if "query_seed" not in action_info:
                    raise RuntimeError("policy server omitted its query seed")
                consensus = dict(action_info.get("consensus") or {})
                if (
                    consensus.get("method") != "median"
                    or int(consensus.get("proposal_count", -1)) != PROPOSAL_COUNT
                ):
                    raise RuntimeError("policy server returned the wrong consensus")
                arm = np.asarray(predicted["single_arm"], dtype=np.float32)[0]
                gripper = np.asarray(predicted["gripper"], dtype=np.float32)[0]
                chunk = np.concatenate([arm, gripper], axis=-1)
                if chunk.shape != (MODEL_HORIZON, 6) or not np.isfinite(chunk).all():
                    raise RuntimeError(f"policy returned invalid action chunk {chunk.shape}")
                query_starts.append(sample_step)
                query_chunks.append(chunk.copy())
                chunk_history.append((sample_step, chunk.copy()))
                query_receipts.append(
                    {
                        "sample_step": sample_step,
                        "query_seed": int(action_info["query_seed"]),
                        "proposal_seeds": [
                            int(value) for value in action_info.get("proposal_seeds", [])
                        ],
                        "consensus": _json_safe(consensus),
                        "frame_sha256": _array_sha256(frame),
                        "state_sha256": _array_sha256(state),
                        "chunk_sha256": _array_sha256(chunk),
                    }
                )

            action, temporal_info = aggregate_temporal_action(
                chunk_history,
                sample_step=sample_step,
                method="mean",
            )
            temporal_candidate_counts.append(int(temporal_info["candidate_count"]))
            actions.append(action.copy())
            clipped = np.clip(action, bounds[:, 0], bounds[:, 1]).astype(np.float64)
            clipped_coordinates += int(np.count_nonzero(clipped != action))
            data.ctrl[runtime.actuator_ids] = clipped
            for _ in range(10):
                mujoco.mj_step(model, data)
    finally:
        renderer.close()

    actions_array = np.asarray(actions, dtype=np.float32)
    states_array = np.asarray(states, dtype=np.float32)
    starts_array = np.asarray(query_starts, dtype=np.int64)
    chunks_array = np.asarray(query_chunks, dtype=np.float32)
    final_state = integration_state(model, data)
    expected_starts = np.arange(0, SAMPLE_COUNT, EXECUTION_HORIZON, dtype=np.int64)
    if not np.array_equal(starts_array, expected_starts):
        raise RuntimeError("pawn rollout query schedule drifted")

    video_path = args.output / "episode.mp4"
    trajectory_path = args.output / "trajectory.npz"
    queries_path = args.output / "policy_queries.json"
    _write_video(video_path, frames, 20)
    np.savez_compressed(
        trajectory_path,
        states=states_array,
        actions=actions_array,
        initial_integration_state=initial_state,
        final_integration_state=final_state,
        query_starts=starts_array,
        query_chunks=chunks_array,
        temporal_candidate_counts=np.asarray(temporal_candidate_counts, dtype=np.int16),
    )
    queries_path.write_text(
        json.dumps(query_receipts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    receipt = {
        "schema_version": ROLLOUT_SCHEMA,
        "proof_class": "learned_policy_simulation_pending_independent_evaluation",
        "experiment_sha256": args.experiment_sha256,
        "selector_receipt_sha256": args.selector_receipt_sha256,
        "checkpoint_id": args.checkpoint_id,
        "checkpoint_manifest_sha256": args.checkpoint_manifest_sha256,
        "scene_id": "operator_updated_chess_workcell_v3",
        "workspace_pose_id": "workspace_board_fiducial_robotward_100mm_20260718_v3",
        "board_pose_id": "board_robotward_100mm_20260718_v3",
        "piece_layout": "sparse_two_sided_pawns",
        "piece_layout_id": "two_sided_sparse_pawns_rows_1_2_7_8_v1",
        "piece_id": TARGET_PIECE_ID,
        "destination_square": DESTINATION_SQUARE,
        "instruction": INSTRUCTION,
        "scene_reset_seed": 0,
        "inference_seed": args.inference_seed,
        "proposal_count": PROPOSAL_COUNT,
        "action_aggregation": "median",
        "noise_scale": NOISE_SCALE,
        "num_inference_timesteps": INFERENCE_TIMESTEPS,
        "model_action_horizon": MODEL_HORIZON,
        "execution_horizon": EXECUTION_HORIZON,
        "temporal_action_aggregation": "mean",
        "physics_action_adapter": "sample_hold_20hz_10_physics_steps",
        "render_backend": "osmesa",
        "sample_count": SAMPLE_COUNT,
        "physics_action_count": SAMPLE_COUNT * 10,
        "query_count": len(query_starts),
        "query_schedule": query_starts,
        "temporal_candidate_count_min": min(temporal_candidate_counts),
        "temporal_candidate_count_max": max(temporal_candidate_counts),
        "action_clipped_coordinate_count": clipped_coordinates,
        "action_owner": "learned_policy",
        "all_actions_model_derived": True,
        "expert_or_geometric_actions_used": False,
        "reward_guidance_used": False,
        "assistance_frames": 0,
        "policy_reset_info": _json_safe(reset_info),
        "policy_transport": f"tcp://{args.host}:{args.port}",
        "held_out_rows_used": 0,
        "physical_reach_authority": False,
        "rank_1_2_generalization_authority": False,
        "artifacts": {
            "episode.mp4": sha256_file(video_path),
            "trajectory.npz": sha256_file(trajectory_path),
            "policy_queries.json": sha256_file(queries_path),
        },
    }
    receipt_path = args.output / "rollout_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

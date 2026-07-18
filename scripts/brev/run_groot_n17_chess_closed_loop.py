#!/usr/bin/env python3
"""Run one learned GR00T policy-server episode in the frozen chess simulator."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import mujoco
import numpy as np

from gr00t.policy.server_client import PolicyClient
from sim2claw.chess_task import ChessRookLiftEnv
from sim2claw.groot_chess import (
    _apply_sparse_board_curriculum,
    _case_map,
    _episode_shim,
    _piece_bodies,
    _write_video,
    evaluate_episode,
    groot_task_contract_sha256,
    load_groot_task_contract,
    resolve_execution_horizon,
)
from sim2claw.groot_execution import (
    ACTION_EXECUTION_ADAPTERS,
    physics_targets_from_waypoints,
)
from sim2claw.scene import board_square_center


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--episode-split",
        choices=("training", "held_out"),
        default="held_out",
    )
    parser.add_argument("--episode-index", type=int, default=0)
    parser.add_argument("--rollout-replicate", type=int, default=0)
    parser.add_argument("--inference-seed", type=int, default=0)
    parser.add_argument(
        "--policy-server-mode",
        choices=("official_unseeded", "seeded_reset"),
        default="official_unseeded",
    )
    parser.add_argument("--checkpoint-id", required=True)
    parser.add_argument("--checkpoint-manifest-sha256", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5555)
    parser.add_argument("--proposal-count", type=int, default=1)
    parser.add_argument(
        "--action-aggregation",
        choices=("mean", "median", "medoid", "trimmed_mean"),
        default="medoid",
    )
    parser.add_argument("--noise-scale", type=float, default=1.0)
    parser.add_argument("--num-inference-timesteps", type=int)
    parser.add_argument(
        "--physics-action-adapter",
        choices=sorted(ACTION_EXECUTION_ADAPTERS),
        default="sample_hold",
    )
    parser.add_argument(
        "--render-cadence",
        choices=("all_samples", "policy_queries"),
        default="all_samples",
        help="Policy-query rendering is a training-development diagnostic only.",
    )
    parser.add_argument(
        "--execution-horizon",
        type=int,
        default=None,
        help=(
            "Number of predicted actions to execute before querying again. "
            "Defaults to the model action horizon."
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.proposal_count < 1:
        parser.error("--proposal-count must be positive")
    if args.action_aggregation == "trimmed_mean" and args.proposal_count < 5:
        parser.error("trimmed_mean requires --proposal-count of at least 5")
    if not 0.0 <= args.noise_scale <= 1.0:
        parser.error("--noise-scale must be between 0 and 1")
    if args.num_inference_timesteps is not None and not (
        1 <= args.num_inference_timesteps <= 16
    ):
        parser.error("--num-inference-timesteps must be between 1 and 16")
    if args.policy_server_mode == "official_unseeded" and (
        args.proposal_count != 1
        or args.action_aggregation != "medoid"
        or args.noise_scale != 1.0
        or args.num_inference_timesteps is not None
    ):
        parser.error("consensus controls require --policy-server-mode seeded_reset")

    contract = load_groot_task_contract()
    episode_rows = contract[f"{args.episode_split}_episodes"]
    if not 0 <= args.episode_index < len(episode_rows):
        parser.error(
            f"--episode-index must be between 0 and {len(episode_rows) - 1} "
            f"for split {args.episode_split}"
        )
    episode_row = episode_rows[args.episode_index]
    case = _case_map(contract, args.episode_split)[episode_row["case_id"]]
    offset = tuple(float(value) for value in episode_row["piece_planar_offset_m"])
    env = ChessRookLiftEnv(
        _episode_shim(contract, case),
        seed=int(episode_row["seed"]),
        piece_offset_xy_m=offset,
    )
    _apply_sparse_board_curriculum(env, contract)

    target = np.asarray(board_square_center(str(case["target_square"])), dtype=np.float64)
    initial_piece_position = env.piece_position()
    initial_height = float(initial_piece_position[2])
    initial_other_positions = {
        name: np.asarray(env.data.xpos[body_id], dtype=np.float64).copy()
        for name, body_id in _piece_bodies(env.model).items()
    }
    maximum_height = initial_height
    sample_stride = int(contract["episode"]["sample_every_physics_steps"])
    sample_count = (
        sum(int(value) for value in contract["episode"]["phase_physics_steps"].values())
        + int(contract["episode"]["settle_steps_after"])
    ) // sample_stride
    action_horizon = int(contract["model"]["action_horizon"])
    try:
        execution_horizon = resolve_execution_horizon(
            args.execution_horizon,
            model_action_horizon=action_horizon,
        )
    except ValueError as exc:
        parser.error(str(exc))

    args.output.mkdir(parents=True, exist_ok=True)
    renderer = mujoco.Renderer(
        env.model,
        height=int(contract["episode"]["render_height"]),
        width=int(contract["episode"]["render_width"]),
    )
    client = PolicyClient(
        host=args.host,
        port=args.port,
        timeout_ms=120_000,
        strict=False,
    )
    if not client.ping():
        raise RuntimeError("GR00T policy server did not answer ping")
    reset_options: dict[str, object] = {
        "inference_seed": args.inference_seed,
        "proposal_count": args.proposal_count,
        "action_aggregation": args.action_aggregation,
        "noise_scale": args.noise_scale,
    }
    if args.num_inference_timesteps is not None:
        reset_options["num_inference_timesteps"] = args.num_inference_timesteps
    reset_info = client.reset(options=reset_options)
    if args.policy_server_mode == "seeded_reset":
        if reset_info.get("rng_reset") is not True:
            raise RuntimeError("seeded policy server did not acknowledge RNG reset")
        if int(reset_info.get("inference_seed", -1)) != args.inference_seed:
            raise RuntimeError("seeded policy server acknowledged the wrong seed")
        expected_reset = {
            "proposal_count": args.proposal_count,
            "action_aggregation": args.action_aggregation,
            "noise_scale": args.noise_scale,
        }
        for key, expected in expected_reset.items():
            if reset_info.get(key) != expected:
                raise RuntimeError(f"seeded policy server acknowledged wrong {key}")
        if (
            args.num_inference_timesteps is not None
            and reset_info.get("num_inference_timesteps")
            != args.num_inference_timesteps
        ):
            raise RuntimeError(
                "seeded policy server acknowledged wrong num_inference_timesteps"
            )

    frames: list[np.ndarray] = []
    states: list[np.ndarray] = []
    actions: list[np.ndarray] = []
    chunks_requested = 0
    physics_actions = 0
    action_chunk = np.empty((0, 6), dtype=np.float32)
    policy_queries: list[dict[str, object]] = []
    physics_control_digest = hashlib.sha256()
    interpolated_sample_intervals = 0

    try:
        for sample_step in range(sample_count):
            needs_policy_query = sample_step % execution_horizon == 0
            frame: np.ndarray | None = None
            if args.render_cadence == "all_samples" or needs_policy_query:
                renderer.update_scene(
                    env.data,
                    camera=str(contract["scene"]["camera"]),
                )
                frame = renderer.render().copy()
                frames.append(frame)
            state = np.asarray(env.data.qpos[env.qpos_addresses], dtype=np.float32).copy()
            states.append(state)

            if needs_policy_query:
                if frame is None:
                    raise RuntimeError("policy query is missing its rendered frame")
                observation = {
                    "video": {"front": frame[None, None, ...]},
                    "state": {
                        "single_arm": state[None, None, :5],
                        "gripper": state[None, None, 5:],
                    },
                    "language": {
                        "annotation.human.task_description": [[str(case["instruction"])]]
                    },
                }
                predicted, action_info = client.get_action(
                    observation,
                    options={"sample_step": sample_step},
                )
                if args.policy_server_mode == "seeded_reset":
                    if int(action_info.get("sample_step", -1)) != sample_step:
                        raise RuntimeError("seeded policy server acknowledged wrong sample step")
                    if "query_seed" not in action_info:
                        raise RuntimeError("seeded policy server omitted query seed")
                    query_receipt = dict(action_info)
                    query_receipt.update(
                        {
                            "frame_sha256": hashlib.sha256(
                                np.ascontiguousarray(frame).tobytes()
                            ).hexdigest(),
                            "state_sha256": hashlib.sha256(
                                np.ascontiguousarray(state).tobytes()
                            ).hexdigest(),
                        }
                    )
                    policy_queries.append(query_receipt)
                arm = np.asarray(predicted["single_arm"], dtype=np.float32)[0]
                gripper = np.asarray(predicted["gripper"], dtype=np.float32)[0]
                action_chunk = np.concatenate([arm, gripper], axis=-1)
                if action_chunk.ndim != 2 or action_chunk.shape[1] != 6:
                    raise RuntimeError(f"unexpected action chunk shape: {action_chunk.shape}")
                if action_chunk.shape[0] < execution_horizon:
                    raise RuntimeError(
                        "policy returned fewer actions than the requested execution "
                        f"horizon: {action_chunk.shape[0]} < {execution_horizon}"
                    )
                if not np.isfinite(action_chunk).all():
                    raise RuntimeError("policy returned a non-finite action")
                chunks_requested += 1

            chunk_index = sample_step % execution_horizon
            action = action_chunk[chunk_index].copy()
            actions.append(action)
            next_waypoint = (
                action_chunk[chunk_index + 1]
                if chunk_index + 1 < action_chunk.shape[0]
                else None
            )
            physics_targets, adapter_info = physics_targets_from_waypoints(
                contract,
                sample_step=sample_step,
                current=action,
                next_waypoint=next_waypoint,
                adapter=args.physics_action_adapter,
            )
            interpolated_sample_intervals += int(
                bool(adapter_info["interpolated_to_next_waypoint"])
            )
            for physics_target in physics_targets:
                physics_control_digest.update(
                    np.ascontiguousarray(physics_target).tobytes()
                )
                env.step(physics_target)
                physics_actions += 1
                maximum_height = max(maximum_height, float(env.piece_position()[2]))
    finally:
        renderer.close()

    verdict = evaluate_episode(
        env,
        contract,
        target=target,
        initial_height=initial_height,
        maximum_height=maximum_height,
        initial_other_positions=initial_other_positions,
        action_count=physics_actions,
    )
    video_path = args.output / "episode.mp4"
    arrays_path = args.output / "trajectory.npz"
    video_fps = int(contract["episode"]["sample_fps"])
    if args.render_cadence == "policy_queries":
        video_fps = max(1, video_fps // execution_horizon)
    _write_video(video_path, frames, video_fps)
    np.savez_compressed(
        arrays_path,
        states=np.asarray(states, dtype=np.float32),
        actions=np.asarray(actions, dtype=np.float32),
    )
    receipt = {
        "schema_version": "sim2claw.groot_n17_closed_loop_episode.v1",
        "proof_class": "learned_policy_simulation",
        "split": args.episode_split,
        "episode_index": args.episode_index,
        "rollout_replicate": args.rollout_replicate,
        "inference_seed": args.inference_seed,
        "policy_server_mode": args.policy_server_mode,
        "policy_reset_info": reset_info,
        "action_consensus": {
            "proposal_count": args.proposal_count,
            "action_aggregation": args.action_aggregation,
            "noise_scale": args.noise_scale,
            "num_inference_timesteps": reset_info.get(
                "num_inference_timesteps"
            ),
        },
        "case_id": str(case["case_id"]),
        "instruction": str(case["instruction"]),
        "seed": int(episode_row["seed"]),
        "checkpoint_id": args.checkpoint_id,
        "checkpoint_manifest_sha256": args.checkpoint_manifest_sha256,
        "groot_source_commit": str(contract["model"]["source_commit"]),
        "task_contract_sha256": groot_task_contract_sha256(),
        "policy_transport": f"GR00T PolicyClient tcp://{args.host}:{args.port}",
        "render_backend": {
            "mujoco_gl": os.environ.get("MUJOCO_GL", "unspecified"),
            "pyopengl_platform": os.environ.get(
                "PYOPENGL_PLATFORM", "unspecified"
            ),
        },
        "model_action_horizon": action_horizon,
        "execution_horizon": execution_horizon,
        "render_cadence": {
            "method": args.render_cadence,
            "rendered_frame_count": len(frames),
            "video_fps": video_fps,
            "policy_observation_frames_omitted": False,
            "promotion_evidence_eligible": args.render_cadence == "all_samples",
        },
        "action_execution_adapter": {
            "schema_version": "sim2claw.groot_n17_action_execution_adapter.v1",
            "method": args.physics_action_adapter,
            "sample_stride_physics_steps": sample_stride,
            "linear_blend_convention": "physics_substep/sample_stride",
            "phase_boundary_behavior": "hold_current_waypoint",
            "phase_schedule_source": "frozen_base_task_contract",
            "interpolated_sample_intervals": interpolated_sample_intervals,
            "physics_controls_sha256": physics_control_digest.hexdigest(),
            "model_waypoints_only": True,
            "assistance_frames": 0,
        },
        "chunks_requested": chunks_requested,
        "policy_queries": policy_queries,
        "sampled_actions": len(actions),
        "physics_actions": physics_actions,
        "all_actions_model_owned": True,
        "assistance_frames": 0,
        "initial_piece_position_m": initial_piece_position.tolist(),
        "maximum_piece_rise_m": maximum_height - initial_height,
        "final_piece_position_m": env.piece_position().tolist(),
        "target_position_m": target.tolist(),
        "verdict": verdict,
        "diagnostic_reward_has_promotion_authority": False,
        "physical_authority": False,
        "artifacts": {
            video_path.name: sha256_file(video_path),
            arrays_path.name: sha256_file(arrays_path),
        },
    }
    receipt_path = args.output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Run one learned GR00T policy-server episode in the frozen chess simulator."""

from __future__ import annotations

import argparse
import hashlib
import json
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
    load_groot_task_contract,
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
    parser.add_argument("--episode-index", type=int, default=0)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5555)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    contract = load_groot_task_contract()
    episode_row = contract["held_out_episodes"][args.episode_index]
    case = _case_map(contract, "held_out")[episode_row["case_id"]]
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
    client.reset()

    frames: list[np.ndarray] = []
    states: list[np.ndarray] = []
    actions: list[np.ndarray] = []
    chunks_requested = 0
    physics_actions = 0
    action_chunk = np.empty((0, 6), dtype=np.float32)

    try:
        for sample_step in range(sample_count):
            renderer.update_scene(env.data, camera=str(contract["scene"]["camera"]))
            frame = renderer.render().copy()
            state = np.asarray(env.data.qpos[env.qpos_addresses], dtype=np.float32).copy()
            frames.append(frame)
            states.append(state)

            if sample_step % action_horizon == 0:
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
                predicted, _ = client.get_action(observation)
                arm = np.asarray(predicted["single_arm"], dtype=np.float32)[0]
                gripper = np.asarray(predicted["gripper"], dtype=np.float32)[0]
                action_chunk = np.concatenate([arm, gripper], axis=-1)
                if action_chunk.ndim != 2 or action_chunk.shape[1] != 6:
                    raise RuntimeError(f"unexpected action chunk shape: {action_chunk.shape}")
                if not np.isfinite(action_chunk).all():
                    raise RuntimeError("policy returned a non-finite action")
                chunks_requested += 1

            action = action_chunk[sample_step % action_horizon].copy()
            actions.append(action)
            for _ in range(sample_stride):
                env.step(action)
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
    _write_video(video_path, frames, int(contract["episode"]["sample_fps"]))
    np.savez_compressed(
        arrays_path,
        states=np.asarray(states, dtype=np.float32),
        actions=np.asarray(actions, dtype=np.float32),
    )
    receipt = {
        "schema_version": "sim2claw.groot_n17_closed_loop_episode.v1",
        "proof_class": "learned_policy_simulation",
        "split": "held_out",
        "episode_index": args.episode_index,
        "case_id": str(case["case_id"]),
        "instruction": str(case["instruction"]),
        "seed": int(episode_row["seed"]),
        "policy_transport": f"GR00T PolicyClient tcp://{args.host}:{args.port}",
        "chunks_requested": chunks_requested,
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

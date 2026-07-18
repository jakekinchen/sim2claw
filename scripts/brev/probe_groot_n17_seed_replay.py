#!/usr/bin/env python3
"""Probe same-observation GR00T action replay after evaluator-owned RNG resets."""

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
    load_groot_task_contract,
)


def array_sha256(value: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episode-index", type=int, default=0)
    parser.add_argument("--inference-seed", type=int, default=0)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5555)
    parser.add_argument(
        "--frame-input",
        type=Path,
        help="Use an evaluator-owned uint8 HWC .npy frame instead of rendering.",
    )
    parser.add_argument("--frame-output", type=Path)
    parser.add_argument("--render-warmup-count", type=int, default=1)
    parser.add_argument("--disable-gl-dither", action="store_true")
    parser.add_argument("--offsamples", type=int)
    parser.add_argument("--shadowsize", type=int)
    args = parser.parse_args()
    if args.repeats < 2:
        parser.error("--repeats must be at least 2")

    contract = load_groot_task_contract()
    episode_row = contract["held_out_episodes"][args.episode_index]
    case = _case_map(contract, "held_out")[episode_row["case_id"]]
    env = ChessRookLiftEnv(
        _episode_shim(contract, case),
        seed=int(episode_row["seed"]),
        piece_offset_xy_m=tuple(
            float(value) for value in episode_row["piece_planar_offset_m"]
        ),
    )
    _apply_sparse_board_curriculum(env, contract)
    if args.offsamples is not None:
        env.model.vis.quality.offsamples = args.offsamples
    if args.shadowsize is not None:
        env.model.vis.quality.shadowsize = args.shadowsize
    if args.frame_input is not None:
        frame = np.load(args.frame_input, allow_pickle=False)
        expected_shape = (
            int(contract["episode"]["render_height"]),
            int(contract["episode"]["render_width"]),
            3,
        )
        if frame.shape != expected_shape or frame.dtype != np.uint8:
            parser.error(
                f"--frame-input must be uint8 with shape {expected_shape}; "
                f"got {frame.dtype} {frame.shape}"
            )
        rendered_frames = [frame]
        frame_source = "npy"
    else:
        renderer = mujoco.Renderer(
            env.model,
            height=int(contract["episode"]["render_height"]),
            width=int(contract["episode"]["render_width"]),
        )
        if args.disable_gl_dither:
            from OpenGL import GL

            GL.glDisable(GL.GL_DITHER)
        if args.render_warmup_count < 1:
            parser.error("--render-warmup-count must be at least 1")
        try:
            rendered_frames = []
            for _ in range(args.render_warmup_count):
                renderer.update_scene(env.data, camera=str(contract["scene"]["camera"]))
                rendered_frames.append(renderer.render().copy())
            frame = np.median(np.stack(rendered_frames, axis=0), axis=0).astype(
                np.uint8
            )
            frame_source = "renderer"
        finally:
            renderer.close()
    state = np.asarray(env.data.qpos[env.qpos_addresses], dtype=np.float32).copy()
    if args.frame_output is not None:
        args.frame_output.parent.mkdir(parents=True, exist_ok=True)
        np.save(args.frame_output, frame, allow_pickle=False)
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

    client = PolicyClient(
        host=args.host,
        port=args.port,
        timeout_ms=120_000,
        strict=False,
    )
    if not client.ping():
        raise RuntimeError("GR00T policy server did not answer ping")

    probes = []
    for repeat in range(args.repeats):
        reset_info = client.reset(options={"inference_seed": args.inference_seed})
        predicted, action_info = client.get_action(
            observation,
            options={"sample_step": 0},
        )
        arm = np.asarray(predicted["single_arm"], dtype=np.float32)
        gripper = np.asarray(predicted["gripper"], dtype=np.float32)
        action = np.concatenate([arm, gripper], axis=-1)
        probes.append(
            {
                "repeat": repeat,
                "action_sha256": array_sha256(action),
                "first_action": action[0, 0].tolist(),
                "reset_info": reset_info,
                "action_info": action_info,
            }
        )

    unique_action_hashes = sorted({row["action_sha256"] for row in probes})
    result = {
        "schema_version": "sim2claw.groot_n17_seed_replay_probe.v1",
        "episode_index": args.episode_index,
        "inference_seed": args.inference_seed,
        "repeats": args.repeats,
        "frame_source": frame_source,
        "frame_input": str(args.frame_input.resolve()) if args.frame_input else None,
        "frame_sha256": array_sha256(frame),
        "render_frame_sha256": [array_sha256(value) for value in rendered_frames],
        "state_sha256": array_sha256(state),
        "qpos_sha256": array_sha256(np.asarray(env.data.qpos)),
        "qvel_sha256": array_sha256(np.asarray(env.data.qvel)),
        "xpos_sha256": array_sha256(np.asarray(env.data.xpos)),
        "piece_position_m": env.piece_position().tolist(),
        "unique_action_hashes": unique_action_hashes,
        "repeatable": len(unique_action_hashes) == 1,
        "probes": probes,
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

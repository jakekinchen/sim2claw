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
from sim2claw.groot_phase_language import (
    load_phase_language_contract,
    phase_for_sample_step,
    phase_language_contract_sha256,
    phase_prompt,
)
from sim2claw.paths import DEFAULT_GROOT_PHASE_LANGUAGE_CONFIG
from sim2claw.scene import board_square_center


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=("training", "held_out"), default="held_out")
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
    parser.add_argument(
        "--language-scheduler",
        choices=("fixed_instruction", "frozen_phase"),
        default="fixed_instruction",
        help=(
            "Use the original episode instruction or a receipt-visible, sample-step "
            "phase-language curriculum that never selects or modifies actions."
        ),
    )
    parser.add_argument(
        "--phase-language-contract",
        type=Path,
        default=DEFAULT_GROOT_PHASE_LANGUAGE_CONFIG,
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
    parser.add_argument(
        "--evidence-frame-cadence",
        choices=("all_samples", "policy_queries"),
        default="all_samples",
        help=(
            "Render every sample for promotion evidence, or only policy-query "
            "samples for a non-promotable development diagnostic."
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    contract = load_groot_task_contract()
    phase_language_contract = (
        load_phase_language_contract(args.phase_language_contract)
        if args.language_scheduler == "frozen_phase"
        else None
    )
    episode_row = contract[f"{args.split}_episodes"][args.episode_index]
    case = _case_map(contract, args.split)[episode_row["case_id"]]
    offset = tuple(float(value) for value in episode_row["piece_planar_offset_m"])
    env = ChessRookLiftEnv(
        _episode_shim(contract, case),
        seed=int(episode_row["seed"]),
        piece_offset_xy_m=offset,
    )
    _apply_sparse_board_curriculum(env, contract)

    target = np.asarray(
        board_square_center(str(case["target_square"])), dtype=np.float64
    )
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
    reset_info = client.reset(options={"inference_seed": args.inference_seed})
    if args.policy_server_mode == "seeded_reset":
        if reset_info.get("rng_reset") is not True:
            raise RuntimeError("seeded policy server did not acknowledge RNG reset")
        if int(reset_info.get("inference_seed", -1)) != args.inference_seed:
            raise RuntimeError("seeded policy server acknowledged the wrong seed")

    frames: list[np.ndarray] = []
    rendered_frame_sample_steps: list[int] = []
    states: list[np.ndarray] = []
    actions: list[np.ndarray] = []
    chunks_requested = 0
    physics_actions = 0
    action_chunk = np.empty((0, 6), dtype=np.float32)
    action_chunk_index = 0
    active_language_phase: str | None = None
    policy_queries: list[dict[str, object]] = []

    try:
        for sample_step in range(sample_count):
            language_phase = (
                phase_for_sample_step(contract, sample_step)
                if phase_language_contract is not None
                else None
            )
            phase_changed = (
                phase_language_contract is not None
                and active_language_phase is not None
                and language_phase != active_language_phase
            )
            is_policy_query = (
                action_chunk_index >= execution_horizon
                or len(action_chunk) == 0
                or phase_changed
            )
            render_this_sample = (
                args.evidence_frame_cadence == "all_samples" or is_policy_query
            )
            frame: np.ndarray | None = None
            if render_this_sample:
                renderer.update_scene(env.data, camera=str(contract["scene"]["camera"]))
                frame = renderer.render().copy()
                frames.append(frame)
                rendered_frame_sample_steps.append(sample_step)
            state = np.asarray(
                env.data.qpos[env.qpos_addresses], dtype=np.float32
            ).copy()
            states.append(state)

            if is_policy_query:
                if frame is None:
                    raise RuntimeError("policy query sample was not rendered")
                instruction = (
                    phase_prompt(phase_language_contract, case, str(language_phase))
                    if phase_language_contract is not None
                    else str(case["instruction"])
                )
                observation = {
                    "video": {"front": frame[None, None, ...]},
                    "state": {
                        "single_arm": state[None, None, :5],
                        "gripper": state[None, None, 5:],
                    },
                    "language": {"annotation.human.task_description": [[instruction]]},
                }
                predicted, action_info = client.get_action(
                    observation,
                    options={"sample_step": sample_step},
                )
                if args.policy_server_mode == "seeded_reset":
                    if int(action_info.get("sample_step", -1)) != sample_step:
                        raise RuntimeError(
                            "seeded policy server acknowledged wrong sample step"
                        )
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
                            "language_phase": language_phase,
                            "language_prompt_sha256": hashlib.sha256(
                                instruction.encode("utf-8")
                            ).hexdigest(),
                        }
                    )
                    policy_queries.append(query_receipt)
                arm = np.asarray(predicted["single_arm"], dtype=np.float32)[0]
                gripper = np.asarray(predicted["gripper"], dtype=np.float32)[0]
                action_chunk = np.concatenate([arm, gripper], axis=-1)
                if action_chunk.ndim != 2 or action_chunk.shape[1] != 6:
                    raise RuntimeError(
                        f"unexpected action chunk shape: {action_chunk.shape}"
                    )
                if action_chunk.shape[0] < execution_horizon:
                    raise RuntimeError(
                        "policy returned fewer actions than the requested execution "
                        f"horizon: {action_chunk.shape[0]} < {execution_horizon}"
                    )
                if not np.isfinite(action_chunk).all():
                    raise RuntimeError("policy returned a non-finite action")
                chunks_requested += 1
                action_chunk_index = 0
                active_language_phase = language_phase

            action = action_chunk[action_chunk_index].copy()
            action_chunk_index += 1
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
        "split": args.split,
        "episode_index": args.episode_index,
        "rollout_replicate": args.rollout_replicate,
        "inference_seed": args.inference_seed,
        "policy_server_mode": args.policy_server_mode,
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
            "pyopengl_platform": os.environ.get("PYOPENGL_PLATFORM", "unspecified"),
        },
        "evidence_frame_cadence": args.evidence_frame_cadence,
        "promotion_eligible_render_cadence": (
            args.evidence_frame_cadence == "all_samples"
        ),
        "rendered_frames": len(frames),
        "rendered_frame_sample_steps": rendered_frame_sample_steps,
        "model_action_horizon": action_horizon,
        "execution_horizon": execution_horizon,
        "chunks_requested": chunks_requested,
        "policy_queries": policy_queries,
        "language_scheduler": {
            "mode": args.language_scheduler,
            "phase_language_contract_sha256": (
                phase_language_contract_sha256(args.phase_language_contract)
                if phase_language_contract is not None
                else None
            ),
            "hierarchical_task_decomposition": phase_language_contract is not None,
            "single_prompt_end_to_end": phase_language_contract is None,
            "selects_or_modifies_actions": False,
            "uses_observation_geometry": False,
            "uses_reward": False,
        },
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

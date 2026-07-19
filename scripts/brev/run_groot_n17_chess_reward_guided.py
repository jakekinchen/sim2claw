#!/usr/bin/env python3
"""Run reward-guided best-of-N GR00T proposals in the chess simulator."""

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
    _write_video,
    evaluate_episode,
    groot_task_contract_sha256,
    load_groot_task_contract,
    resolve_execution_horizon,
)
from sim2claw.groot_guidance import (
    guidance_contract_sha256,
    load_guidance_contract,
    make_guidance_context,
    simulate_candidate,
)
from sim2claw.scene import board_square_center


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def array_sha256(value: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=("training", "held_out"), default="training")
    parser.add_argument("--episode-index", type=int, default=0)
    parser.add_argument("--rollout-replicate", type=int, default=0)
    parser.add_argument("--inference-seed", type=int, default=0)
    parser.add_argument("--checkpoint-id", required=True)
    parser.add_argument("--checkpoint-manifest-sha256", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5555)
    parser.add_argument("--proposal-count", type=int)
    parser.add_argument("--execution-horizon", type=int)
    parser.add_argument("--max-sample-count", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    base_contract = load_groot_task_contract()
    guidance_contract = load_guidance_contract()
    episode_rows = base_contract[f"{args.split}_episodes"]
    if not 0 <= args.episode_index < len(episode_rows):
        parser.error("episode index is out of range")
    episode_row = episode_rows[args.episode_index]
    case = _case_map(base_contract, args.split)[episode_row["case_id"]]
    offset = tuple(float(value) for value in episode_row["piece_planar_offset_m"])
    env = ChessRookLiftEnv(
        _episode_shim(base_contract, case),
        seed=int(episode_row["seed"]),
        piece_offset_xy_m=offset,
    )
    _apply_sparse_board_curriculum(env, base_contract)

    target = np.asarray(
        board_square_center(str(case["target_square"])), dtype=np.float64
    )
    context = make_guidance_context(env, base_contract, target)
    initial_height = float(context.initial_piece_position[2])
    maximum_height = initial_height
    sample_stride = int(base_contract["episode"]["sample_every_physics_steps"])
    declared_sample_count = (
        sum(
            int(value)
            for value in base_contract["episode"]["phase_physics_steps"].values()
        )
        + int(base_contract["episode"]["settle_steps_after"])
    ) // sample_stride
    sample_count = (
        declared_sample_count
        if args.max_sample_count is None
        else min(declared_sample_count, int(args.max_sample_count))
    )
    if sample_count < 1:
        parser.error("max sample count must be positive")
    action_horizon = int(base_contract["model"]["action_horizon"])
    execution_horizon = resolve_execution_horizon(
        args.execution_horizon
        if args.execution_horizon is not None
        else int(guidance_contract["selection"]["execution_horizon"]),
        model_action_horizon=action_horizon,
    )
    proposal_count = (
        int(guidance_contract["selection"]["proposal_count"])
        if args.proposal_count is None
        else int(args.proposal_count)
    )
    if proposal_count < 2:
        parser.error("proposal count must be at least two")

    args.output.mkdir(parents=True, exist_ok=True)
    selections_path = args.output / "selection_receipts.jsonl"
    selections_path.write_text("", encoding="utf-8")
    renderer = mujoco.Renderer(
        env.model,
        height=int(base_contract["episode"]["render_height"]),
        width=int(base_contract["episode"]["render_width"]),
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
    if reset_info.get("rng_reset") is not True:
        raise RuntimeError("seeded policy server did not acknowledge RNG reset")
    if int(reset_info.get("inference_seed", -1)) != args.inference_seed:
        raise RuntimeError("seeded policy server acknowledged the wrong seed")

    frames: list[np.ndarray] = []
    states: list[np.ndarray] = []
    actions: list[np.ndarray] = []
    selected_candidates: list[int] = []
    selection_receipts: list[dict[str, object]] = []
    action_chunk = np.empty((0, 6), dtype=np.float32)
    selected_candidate = -1
    physics_actions = 0

    try:
        for sample_step in range(sample_count):
            renderer.update_scene(
                env.data, camera=str(base_contract["scene"]["camera"])
            )
            frame = renderer.render().copy()
            state = np.asarray(
                env.data.qpos[env.qpos_addresses], dtype=np.float32
            ).copy()
            frames.append(frame)
            states.append(state)

            if sample_step % execution_horizon == 0:
                observation = {
                    "video": {"front": frame[None, None, ...]},
                    "state": {
                        "single_arm": state[None, None, :5],
                        "gripper": state[None, None, 5:],
                    },
                    "language": {
                        "annotation.human.task_description": [
                            [str(case["instruction"])]
                        ]
                    },
                }
                proposals: list[dict[str, object]] = []
                for candidate_index in range(proposal_count):
                    predicted, action_info = client.get_action(
                        observation,
                        options={
                            "sample_step": sample_step,
                            "candidate_index": candidate_index,
                        },
                    )
                    if int(action_info.get("sample_step", -1)) != sample_step:
                        raise RuntimeError(
                            "seeded server acknowledged wrong sample step"
                        )
                    if int(action_info.get("candidate_index", -1)) != candidate_index:
                        raise RuntimeError("seeded server acknowledged wrong candidate")
                    arm = np.asarray(predicted["single_arm"], dtype=np.float32)[0]
                    gripper = np.asarray(predicted["gripper"], dtype=np.float32)[0]
                    candidate_chunk = np.concatenate([arm, gripper], axis=-1)
                    simulation = simulate_candidate(
                        env,
                        base_contract,
                        guidance_contract,
                        context,
                        candidate_chunk,
                        sample_step=sample_step,
                        execution_horizon=execution_horizon,
                    )
                    proposals.append(
                        {
                            "candidate_index": candidate_index,
                            "query_seed": int(action_info["query_seed"]),
                            "action_sha256": array_sha256(candidate_chunk),
                            "score": simulation["score"],
                            "control_delta_rad": simulation["control_delta_rad"],
                            "metrics": simulation["metrics"],
                            "action_chunk": candidate_chunk,
                        }
                    )
                winner = max(
                    proposals,
                    key=lambda row: (float(row["score"]), -int(row["candidate_index"])),
                )
                selected_candidate = int(winner["candidate_index"])
                action_chunk = np.asarray(winner.pop("action_chunk"), dtype=np.float32)
                receipt_proposals = []
                for proposal in proposals:
                    proposal = dict(proposal)
                    proposal.pop("action_chunk", None)
                    receipt_proposals.append(proposal)
                selection_receipts.append(
                    {
                        "sample_step": sample_step,
                        "frame_sha256": array_sha256(frame),
                        "state_sha256": array_sha256(state),
                        "selected_candidate_index": selected_candidate,
                        "selected_score": float(winner["score"]),
                        "proposals": receipt_proposals,
                    }
                )
                selection_line = selection_receipts[-1]
                with selections_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(selection_line, sort_keys=True) + "\n")
                selected_metrics = winner["metrics"]
                print(
                    json.dumps(
                        {
                            "event": "guided_query",
                            "sample_step": sample_step,
                            "phase": selected_metrics["phase"],
                            "selected_candidate_index": selected_candidate,
                            "selected_score": float(winner["score"]),
                            "piece_rise_m": selected_metrics["piece_rise_m"],
                            "destination_distance_m": selected_metrics[
                                "destination_distance_m"
                            ],
                            "maximum_other_piece_displacement_m": selected_metrics[
                                "maximum_other_piece_displacement_m"
                            ],
                            "upright_cosine": selected_metrics["upright_cosine"],
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )

            action = action_chunk[sample_step % execution_horizon].copy()
            actions.append(action)
            selected_candidates.append(selected_candidate)
            for _ in range(sample_stride):
                env.step(action)
                physics_actions += 1
                maximum_height = max(maximum_height, float(env.piece_position()[2]))
    finally:
        renderer.close()

    assistance_frames = len(actions)
    verdict = evaluate_episode(
        env,
        base_contract,
        target=target,
        initial_height=initial_height,
        maximum_height=maximum_height,
        initial_other_positions=context.initial_other_positions,
        action_count=physics_actions,
        assistance_frames=assistance_frames,
    )
    video_path = args.output / "episode.mp4"
    arrays_path = args.output / "trajectory.npz"
    _write_video(video_path, frames, int(base_contract["episode"]["sample_fps"]))
    np.savez_compressed(
        arrays_path,
        states=np.asarray(states, dtype=np.float32),
        actions=np.asarray(actions, dtype=np.float32),
        selected_candidate_indices=np.asarray(selected_candidates, dtype=np.int32),
    )
    receipt = {
        "schema_version": "sim2claw.groot_n17_reward_guided_episode.v1",
        "proof_class": guidance_contract["proof_class"],
        "split": args.split,
        "episode_index": args.episode_index,
        "rollout_replicate": args.rollout_replicate,
        "inference_seed": args.inference_seed,
        "case_id": str(case["case_id"]),
        "instruction": str(case["instruction"]),
        "seed": int(episode_row["seed"]),
        "checkpoint_id": args.checkpoint_id,
        "checkpoint_manifest_sha256": args.checkpoint_manifest_sha256,
        "groot_source_commit": str(base_contract["model"]["source_commit"]),
        "task_contract_sha256": groot_task_contract_sha256(),
        "guidance_contract_sha256": guidance_contract_sha256(),
        "policy_transport": f"GR00T PolicyClient tcp://{args.host}:{args.port}",
        "render_backend": {
            "mujoco_gl": os.environ.get("MUJOCO_GL", "unspecified"),
            "pyopengl_platform": os.environ.get("PYOPENGL_PLATFORM", "unspecified"),
        },
        "model_action_horizon": action_horizon,
        "execution_horizon": execution_horizon,
        "proposal_count": proposal_count,
        "selection_receipts": selection_receipts,
        "sampled_actions": len(actions),
        "physics_actions": physics_actions,
        "all_executed_actions_model_proposed": True,
        "guided_selection_counts_as_assistance": True,
        "assistance_frames": assistance_frames,
        "initial_piece_position_m": context.initial_piece_position.tolist(),
        "maximum_piece_rise_m": maximum_height - initial_height,
        "final_piece_position_m": env.piece_position().tolist(),
        "target_position_m": target.tolist(),
        "verdict": verdict,
        "task_consequence_success": verdict["task_consequence_success"],
        "strict_unassisted_success": verdict["success"],
        "reward_has_promotion_authority": False,
        "physical_authority": False,
        "artifacts": {
            video_path.name: sha256_file(video_path),
            arrays_path.name: sha256_file(arrays_path),
            selections_path.name: sha256_file(selections_path),
        },
    }
    receipt_path = args.output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

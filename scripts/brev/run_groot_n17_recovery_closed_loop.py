#!/usr/bin/env python3
"""Run one GR00T policy-server episode through the frozen recovery evaluator."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from gr00t.policy.server_client import PolicyClient
from sim2claw.chess_task import ChessRookLiftEnv
from sim2claw.groot_chess import (
    _apply_sparse_board_curriculum,
    _episode_shim,
    _piece_bodies,
    _write_video,
    evaluate_episode,
    groot_task_contract_sha256,
    load_groot_task_contract,
)
from sim2claw.groot_chess_recovery import (
    _inject_target_slip,
    _jaw_piece_contacts,
    _place_distractor,
    _set_piece_yaw,
    finalize_recovery_verdict,
    load_recovery_task_contract,
    recovery_task_contract_sha256,
)
from sim2claw.scene import board_square_center


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_checkpoint_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "sim2claw.groot_checkpoint_manifest.v1":
        raise ValueError("unsupported checkpoint manifest")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("checkpoint manifest has no file identities")
    for name, digest in files.items():
        if not isinstance(name, str) or not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("checkpoint manifest contains an invalid file identity")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episode-index", type=int, required=True)
    parser.add_argument("--checkpoint-manifest", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5555)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    recovery = load_recovery_task_contract()
    base = load_groot_task_contract()
    if not 0 <= args.episode_index < len(recovery["held_out_episodes"]):
        raise ValueError("held-out recovery episode index is out of range")
    row = recovery["held_out_episodes"][args.episode_index]
    cases = {str(case["case_id"]): case for case in base["held_out_cases"]}
    case = cases[str(row["case_id"])]
    family = str(row["family"])
    checkpoint_manifest = load_checkpoint_manifest(args.checkpoint_manifest)

    env = ChessRookLiftEnv(
        _episode_shim(base, case),
        seed=int(row["seed"]),
        piece_offset_xy_m=tuple(float(value) for value in row["piece_planar_offset_m"]),
    )
    _apply_sparse_board_curriculum(env, base)
    _set_piece_yaw(env, float(row["piece_yaw_deg"]))
    target = np.asarray(board_square_center(str(case["target_square"])), dtype=np.float64)
    distractor = None
    if family == "distractor_proximity":
        distractor = _place_distractor(
            env,
            base,
            float(row["distractor_spacing_m"]),
            int(row["distractor_side"]),
            target[:2],
        )

    initial_piece_position = env.piece_position()
    initial_height = float(initial_piece_position[2])
    piece_bodies = _piece_bodies(env.model)
    initial_other_positions = {
        name: np.asarray(env.data.xpos[body_id], dtype=np.float64).copy()
        for name, body_id in piece_bodies.items()
    }
    maximum_other_displacements = {
        name: 0.0
        for name in base["scene"]["active_pieces"]
        if name != env.piece_name
    }

    base_steps = base["episode"]["phase_physics_steps"]
    total_physics_steps = sum(int(value) for value in base_steps.values()) + int(
        base["episode"]["settle_steps_after"]
    )
    fault_physics_step: int | None = None
    evaluation_contract = copy.deepcopy(base)
    if family == "contact_recovery":
        recovery_steps = recovery["recovery_episode"]["phase_physics_steps"]
        total_physics_steps += sum(int(value) for value in recovery_steps.values())
        total_physics_steps -= int(base_steps["close"])
        fault_physics_step = int(base_steps["stand_off"]) + int(base_steps["advance"])
        evaluation_contract["episode"]["phase_physics_steps"]["close"] = 0
        evaluation_contract["episode"]["phase_physics_steps"].update(recovery_steps)

    sample_stride = int(base["episode"]["sample_every_physics_steps"])
    if total_physics_steps % sample_stride:
        raise RuntimeError("frozen recovery duration is not sample aligned")
    if fault_physics_step is not None and fault_physics_step % sample_stride:
        raise RuntimeError("frozen recovery fault is not sample aligned")
    sample_count = total_physics_steps // sample_stride
    action_horizon = int(base["model"]["action_horizon"])
    if fault_physics_step is not None and (
        fault_physics_step // sample_stride
    ) % action_horizon:
        raise RuntimeError("frozen recovery fault is not action-chunk aligned")

    args.output.mkdir(parents=True, exist_ok=False)
    renderer = mujoco.Renderer(
        env.model,
        height=int(base["episode"]["render_height"]),
        width=int(base["episode"]["render_width"]),
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
    maximum_height = initial_height
    action_chunk = np.empty((0, 6), dtype=np.float32)
    first_piece_contact: str | None = None
    first_piece_contact_step: int | None = None
    wrong_piece_contacts: set[str] = set()
    bilateral_target_contact_observed = False
    first_bilateral_target_contact_step: int | None = None
    first_minimum_lift_step: int | None = None
    recovery_target_contact_events = 0
    fault_injection_steps: list[int] = []
    after_fault = False

    try:
        for sample_step in range(sample_count):
            if fault_physics_step == physics_actions:
                _inject_target_slip(
                    env,
                    float(row["slip_m"]),
                    int(row["slip_side"]),
                )
                fault_injection_steps.append(physics_actions)
                after_fault = True

            renderer.update_scene(env.data, camera=str(base["scene"]["camera"]))
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
                if action_chunk.shape[0] < action_horizon:
                    raise RuntimeError("policy action chunk is shorter than the frozen horizon")
                if not np.isfinite(action_chunk).all():
                    raise RuntimeError("policy returned a non-finite action")
                chunks_requested += 1

            action = action_chunk[sample_step % action_horizon].copy()
            actions.append(action)
            for _ in range(sample_stride):
                env.step(action)
                physics_actions += 1
                maximum_height = max(maximum_height, float(env.piece_position()[2]))
                names, target_jaws = _jaw_piece_contacts(env)
                if names and first_piece_contact is None:
                    first_piece_contact = sorted(names)[0]
                    first_piece_contact_step = physics_actions
                wrong_piece_contacts.update(name for name in names if name != env.piece_name)
                bilateral = len(target_jaws) == len(env.jaw_bodies) and bool(target_jaws)
                if bilateral:
                    bilateral_target_contact_observed = True
                    if first_bilateral_target_contact_step is None:
                        first_bilateral_target_contact_step = physics_actions
                if after_fault and env.piece_name in names:
                    recovery_target_contact_events += 1
                if (
                    first_minimum_lift_step is None
                    and maximum_height - initial_height
                    >= float(base["evaluator"]["minimum_piece_rise_m"])
                ):
                    first_minimum_lift_step = physics_actions
                for name in maximum_other_displacements:
                    displacement = float(
                        np.linalg.norm(
                            env.data.xpos[piece_bodies[name]] - initial_other_positions[name]
                        )
                    )
                    maximum_other_displacements[name] = max(
                        maximum_other_displacements[name], displacement
                    )
    finally:
        renderer.close()

    base_verdict = evaluate_episode(
        env,
        evaluation_contract,
        target=target,
        initial_height=initial_height,
        maximum_height=maximum_height,
        initial_other_positions=initial_other_positions,
        action_count=physics_actions,
    )
    contact_metrics = {
        "first_piece_contact": first_piece_contact,
        "wrong_piece_contacts": sorted(wrong_piece_contacts),
        "wrong_piece_contact_phases": {},
        "bilateral_target_contact_observed": bilateral_target_contact_observed,
        "recovery_target_contact_events": recovery_target_contact_events,
        "fault_injection_count": len(fault_injection_steps),
        "fault_injection_physics_steps": fault_injection_steps,
        "assistance_frames": 0,
        "maximum_other_piece_displacement_m": max(
            maximum_other_displacements.values(), default=0.0
        ),
        "maximum_other_piece_displacements_m": maximum_other_displacements,
        "distractor_piece": distractor,
        "last_phase_reached": "fixed_duration_complete",
        "phase_end_metrics": [],
        "planned_placement_offset_m": [0.0, 0.0],
    }
    verdict = finalize_recovery_verdict(
        base_verdict,
        recovery,
        perturbation_family=family,
        target_piece=env.piece_name,
        contact_metrics=contact_metrics,
    )

    video_path = args.output / "episode.mp4"
    arrays_path = args.output / "trajectory.npz"
    _write_video(video_path, frames, int(base["episode"]["sample_fps"]))
    np.savez_compressed(
        arrays_path,
        states=np.asarray(states, dtype=np.float32),
        actions=np.asarray(actions, dtype=np.float32),
    )
    receipt = {
        "schema_version": "sim2claw.groot_n17_recovery_closed_loop_episode.v2",
        "proof_class": "learned_policy_simulation_recovery",
        "split": "held_out",
        "episode_index": args.episode_index,
        "case_id": str(case["case_id"]),
        "instruction": str(case["instruction"]),
        "seed": int(row["seed"]),
        "perturbation": {
            key: row[key]
            for key in (
                "family",
                "piece_planar_offset_m",
                "piece_yaw_deg",
                "distractor_spacing_m",
                "distractor_side",
                "slip_m",
                "slip_side",
            )
        },
        "base_task_contract_sha256": groot_task_contract_sha256(),
        "recovery_task_contract_sha256": recovery_task_contract_sha256(),
        "checkpoint_manifest": checkpoint_manifest,
        "policy_transport": f"GR00T PolicyClient tcp://{args.host}:{args.port}",
        "action_horizon": action_horizon,
        "chunks_requested": chunks_requested,
        "sampled_actions": len(actions),
        "physics_actions": physics_actions,
        "all_actions_model_owned": True,
        "assistance_frames": 0,
        "declared_fault_injection_is_robot_assistance": False,
        "event_physics_steps": {
            "first_piece_contact": first_piece_contact_step,
            "first_bilateral_target_contact": first_bilateral_target_contact_step,
            "first_minimum_lift": first_minimum_lift_step,
        },
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

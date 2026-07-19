#!/usr/bin/env python3
"""Run and independently replay one fixed 100 mm pawn development episode."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

# NVIDIA's pinned training runtime is Python 3.10.  ``datetime.UTC`` is the
# same singleton as ``timezone.utc`` but was only exposed under that name in
# Python 3.11.  Install the alias before importing the evaluator modules.
if not hasattr(datetime, "UTC"):
    datetime.UTC = datetime.timezone.utc  # type: ignore[attr-defined]

from gr00t.policy.server_client import PolicyClient
from sim2claw.grasp import _jaw_body_ids, _piece_bodies, _pinch_offset, _pinch_point
from sim2claw.groot_chess import _write_video
from sim2claw.groot_execution import aggregate_temporal_action
from sim2claw.pawn_source_evaluator import (
    _integration_state,
    _jaw_piece_contact,
    _robot_piece_contact,
    load_pawn_evaluator_contract,
    pawn_evaluator_sha256,
    score_pawn_consequences,
)
from sim2claw.scene import (
    CURRENT_TASK_PIECE_LAYOUT,
    ROBOT_JOINTS,
    board_square_center,
    build_scene_spec,
    initialize_robot_poses,
    registered_board_center,
)
from sim2claw.source_episode import (
    CONTRACT_PATH_V3,
    CURRENT_SCENE_ID,
    language_instruction,
    load_source_contract,
    sha256_file,
    source_contract_sha256,
)


TARGET_PIECE = "tan_pawn_c8"
SOURCE_SQUARE = "c8"
DESTINATION_SQUARE = "a6"
SAMPLE_COUNT = 562
PHYSICS_STEPS_PER_ACTION = 10


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def load_checkpoint_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "sim2claw.groot_checkpoint_manifest.v1":
        raise ValueError("unsupported checkpoint manifest")
    if int(payload.get("checkpoint_step", -1)) != 1000:
        raise ValueError("only the predeclared checkpoint-1000 may be evaluated")
    if not isinstance(payload.get("files"), dict) or not payload["files"]:
        raise ValueError("checkpoint manifest is empty")
    return payload


def initialize_episode() -> tuple[
    mujoco.MjModel,
    mujoco.MjData,
    np.ndarray,
    np.ndarray,
    dict[str, int],
]:
    contract = load_source_contract(CONTRACT_PATH_V3)
    model = build_scene_spec(
        piece_layout=CURRENT_TASK_PIECE_LAYOUT,
        board_center_in_table_frame_xy_m=registered_board_center(CURRENT_SCENE_ID),
        include_visual_props=True,
    ).compile()
    if not np.isclose(float(model.opt.timestep), 0.005, atol=1e-12):
        raise ValueError("runtime MuJoCo timestep changed")
    data = mujoco.MjData(model)
    initialize_robot_poses(model, data)
    reset = contract["simulation_reset"]
    reset_pose = np.asarray(reset["left_arm_joint_pose_radians"], dtype=np.float64)
    actuator_ids: list[int] = []
    qpos_addresses: list[int] = []
    for joint_name, value in zip(ROBOT_JOINTS, reset_pose, strict=True):
        joint_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_JOINT, f"left_{joint_name}"
        )
        actuator_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_ACTUATOR, f"left_{joint_name}"
        )
        if min(joint_id, actuator_id) < 0:
            raise ValueError(f"runtime model is missing left_{joint_name}")
        qpos_address = int(model.jnt_qposadr[joint_id])
        data.qpos[qpos_address] = value
        data.ctrl[actuator_id] = value
        actuator_ids.append(actuator_id)
        qpos_addresses.append(qpos_address)
    mujoco.mj_forward(model, data)

    piece_bodies = _piece_bodies(model)
    initial_positions = {
        name: np.asarray(data.xpos[body_id], dtype=np.float64).copy()
        for name, body_id in piece_bodies.items()
    }
    robot_body_ids = {
        body_id
        for body_id in range(model.nbody)
        if str(
            mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id) or ""
        ).startswith(("left_", "right_"))
    }
    reset_contact = False
    for _ in range(int(reset["settle_physics_steps"])):
        mujoco.mj_step(model, data)
        reset_contact = reset_contact or _robot_piece_contact(
            model,
            data,
            robot_body_ids,
            set(piece_bodies.values()),
        )
    if reset_contact:
        raise RuntimeError("frozen reset contacted a pawn")
    displacements = [
        float(np.linalg.norm(data.xpos[body_id] - initial_positions[name]))
        for name, body_id in piece_bodies.items()
    ]
    upright = [
        float(np.asarray(data.xmat[body_id]).reshape(3, 3)[2, 2])
        for body_id in piece_bodies.values()
    ]
    if max(displacements) > float(reset["maximum_piece_displacement_after_settle_m"]):
        raise RuntimeError("frozen reset displaced a pawn")
    if min(upright) < 0.95:
        raise RuntimeError("frozen reset toppled a pawn")
    return (
        model,
        data,
        np.asarray(actuator_ids, dtype=np.int32),
        np.asarray(qpos_addresses, dtype=np.int32),
        piece_bodies,
    )


def replay_actions(
    initial_state: np.ndarray,
    actions: np.ndarray,
    expected_states: list[np.ndarray],
) -> bool:
    model, data, actuator_ids, _, _ = initialize_episode()
    mujoco.mj_setState(
        model,
        data,
        initial_state,
        mujoco.mjtState.mjSTATE_INTEGRATION,
    )
    mujoco.mj_forward(model, data)
    bounds = model.actuator_ctrlrange[actuator_ids]
    matches: list[bool] = []
    for action, expected in zip(actions, expected_states, strict=True):
        data.ctrl[actuator_ids] = np.clip(action, bounds[:, 0], bounds[:, 1])
        for _ in range(PHYSICS_STEPS_PER_ACTION):
            mujoco.mj_step(model, data)
        matches.append(np.array_equal(_integration_state(model, data), expected))
    return all(matches)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5555)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("--output must not already exist")

    checkpoint_manifest = load_checkpoint_manifest(args.checkpoint_manifest)
    checkpoint_manifest_sha256 = sha256_file(args.checkpoint_manifest)
    source_contract = load_source_contract(CONTRACT_PATH_V3)
    evaluator = load_pawn_evaluator_contract()
    model, data, actuator_ids, qpos_addresses, piece_bodies = initialize_episode()
    if TARGET_PIECE not in piece_bodies:
        raise ValueError("target pawn is missing")
    if set(piece_bodies) != set(evaluator["scene"]["protected_piece_ids"]):
        raise ValueError("runtime pawn inventory differs from the evaluator")

    target_body = piece_bodies[TARGET_PIECE]
    other_body_ids = {
        body_id for name, body_id in piece_bodies.items() if name != TARGET_PIECE
    }
    robot_body_ids = {
        body_id
        for body_id in range(model.nbody)
        if str(
            mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id) or ""
        ).startswith("left_")
    }
    jaw_bodies = _jaw_body_ids(model, "left")
    pinch_local = _pinch_offset(model, data, "left")
    initial_positions = {
        name: np.asarray(data.xpos[body_id], dtype=np.float64).copy()
        for name, body_id in piece_bodies.items()
    }
    initial_target_position = initial_positions[TARGET_PIECE]
    initial_state = _integration_state(model, data).copy()
    target_position = np.asarray(
        board_square_center(
            DESTINATION_SQUARE,
            board_center_in_table_frame_xy_m=registered_board_center(
                CURRENT_SCENE_ID
            ),
        ),
        dtype=np.float64,
    )
    instruction = language_instruction(
        TARGET_PIECE, SOURCE_SQUARE, DESTINATION_SQUARE
    )

    args.output.mkdir(parents=True)
    renderer = mujoco.Renderer(model, height=256, width=256)
    client = PolicyClient(host=args.host, port=args.port, timeout_ms=120_000, strict=False)
    if not client.ping():
        raise RuntimeError("GR00T policy server did not answer ping")
    reset_info = client.reset(
        options={
            "inference_seed": 0,
            "proposal_count": 5,
            "action_aggregation": "median",
            "noise_scale": 0.5,
            "num_inference_timesteps": 4,
        }
    )
    expected_reset = {
        "rng_reset": True,
        "inference_seed": 0,
        "proposal_count": 5,
        "action_aggregation": "median",
        "noise_scale": 0.5,
        "num_inference_timesteps": 4,
    }
    for key, expected in expected_reset.items():
        if reset_info.get(key) != expected:
            raise RuntimeError(f"policy server acknowledged the wrong {key}")

    frames: list[np.ndarray] = []
    states: list[np.ndarray] = []
    actions: list[np.ndarray] = []
    integration_states: list[np.ndarray] = []
    action_chunk_history: list[tuple[int, np.ndarray]] = []
    policy_queries: list[dict[str, Any]] = []
    next_query_step = 0
    maximum_height = float(data.xpos[target_body][2])
    maximum_other_displacement = 0.0
    wrong_piece_contact = False
    bounds = model.actuator_ctrlrange[actuator_ids]

    try:
        for sample_step in range(SAMPLE_COUNT):
            renderer.update_scene(data, camera="overhead")
            frame = renderer.render().copy()
            state = np.asarray(data.qpos[qpos_addresses], dtype=np.float32).copy()
            frames.append(frame)
            states.append(state)

            if sample_step >= next_query_step:
                observation = {
                    "video": {"front": frame[None, None, ...]},
                    "state": {
                        "single_arm": state[None, None, :5],
                        "gripper": state[None, None, 5:],
                    },
                    "language": {
                        "annotation.human.task_description": [[instruction]]
                    },
                }
                predicted, query_info = client.get_action(
                    observation,
                    options={"sample_step": sample_step},
                )
                arm = np.asarray(predicted["single_arm"], dtype=np.float32)[0]
                gripper = np.asarray(predicted["gripper"], dtype=np.float32)[0]
                action_chunk = np.concatenate([arm, gripper], axis=-1)
                if action_chunk.ndim != 2 or action_chunk.shape[1] != 6:
                    raise RuntimeError(f"unexpected action chunk: {action_chunk.shape}")
                if action_chunk.shape[0] < 16 or not np.isfinite(action_chunk).all():
                    raise RuntimeError("policy returned an invalid H16 action chunk")
                action_chunk_history.append((sample_step, action_chunk.copy()))
                policy_queries.append(dict(query_info))
                next_query_step = sample_step + 8

            action, _ = aggregate_temporal_action(
                action_chunk_history,
                sample_step=sample_step,
                method="mean",
                exponential_decay=0.5,
            )
            float32_action = np.asarray(action, dtype=np.float32)
            actions.append(float32_action.copy())
            data.ctrl[actuator_ids] = np.clip(
                float32_action, bounds[:, 0], bounds[:, 1]
            )
            for _ in range(PHYSICS_STEPS_PER_ACTION):
                mujoco.mj_step(model, data)
                wrong_piece_contact = wrong_piece_contact or _robot_piece_contact(
                    model, data, robot_body_ids, other_body_ids
                )
                maximum_height = max(maximum_height, float(data.xpos[target_body][2]))
                maximum_other_displacement = max(
                    maximum_other_displacement,
                    max(
                        float(
                            np.linalg.norm(
                                data.xpos[body_id] - initial_positions[name]
                            )
                        )
                        for name, body_id in piece_bodies.items()
                        if name != TARGET_PIECE
                    ),
                )
            integration_states.append(_integration_state(model, data).copy())
    finally:
        renderer.close()

    action_array = np.asarray(actions, dtype=np.float32)
    replay_passed = replay_actions(initial_state, action_array, integration_states)
    final_position = np.asarray(data.xpos[target_body], dtype=np.float64)
    final_rotation = np.asarray(data.xmat[target_body], dtype=np.float64).reshape(3, 3)
    measurements = {
        "selected_piece_identity": True,
        "maximum_piece_rise_m": maximum_height - float(initial_target_position[2]),
        "final_xy_error_m": float(np.linalg.norm(final_position[:2] - target_position[:2])),
        "final_height_error_m": float(abs(final_position[2] - target_position[2])),
        "final_upright_cosine": float(final_rotation[2, 2]),
        "final_linear_speed_m_s": float(
            np.linalg.norm(np.asarray(data.cvel[target_body][3:], dtype=np.float64))
        ),
        "gripper_clearance_m": float(
            np.linalg.norm(_pinch_point(model, data, "left", pinch_local) - final_position)
        ),
        "maximum_other_piece_displacement_m": maximum_other_displacement,
        "target_displacement_m": float(
            np.linalg.norm(final_position - initial_target_position)
        ),
        "wrong_piece_contact": wrong_piece_contact,
        "final_jaw_piece_contact": _jaw_piece_contact(
            model, data, jaw_bodies, set(piece_bodies.values())
        ),
        "assistance_frames": 0,
        "declared_action_owner": True,
        "executed_action_count": len(actions),
        "recorded_action_count": SAMPLE_COUNT,
        "exact_sample_hold_state_replay": replay_passed,
    }
    scored = score_pawn_consequences(measurements, evaluator)

    video_path = args.output / "episode.mp4"
    arrays_path = args.output / "trajectory.npz"
    _write_video(video_path, frames, 20)
    np.savez_compressed(
        arrays_path,
        states=np.asarray(states, dtype=np.float32),
        actions=action_array,
    )
    receipt = {
        "schema_version": "sim2claw.groot_n17_pawn_closed_loop.v1",
        "proof_class": "learned_policy_simulation_development",
        "checkpoint_id": "checkpoint-1000",
        "checkpoint_manifest_sha256": checkpoint_manifest_sha256,
        "checkpoint_manifest": checkpoint_manifest,
        "source_contract_sha256": source_contract_sha256(CONTRACT_PATH_V3),
        "evaluator_contract_sha256": pawn_evaluator_sha256(),
        "scene_id": CURRENT_SCENE_ID,
        "workspace_pose_id": source_contract["scene"]["workspace_pose_id"],
        "board_pose_id": source_contract["scene"]["board_pose_id"],
        "selected_piece_id": TARGET_PIECE,
        "source_square": SOURCE_SQUARE,
        "destination_square": DESTINATION_SQUARE,
        "instruction": instruction,
        "sample_count": SAMPLE_COUNT,
        "physics_steps_per_action": PHYSICS_STEPS_PER_ACTION,
        "model_action_horizon": 16,
        "execution_horizon": 8,
        "temporal_action_aggregation": "mean",
        "policy_reset_info": reset_info,
        "policy_queries": policy_queries,
        "all_actions_model_owned": True,
        "assistance_frames": 0,
        "reward_guidance_used": False,
        "task_geometry_used_to_select_or_modify_actions": False,
        "evaluator_device": "cpu",
        "evaluator_dtype": "float32",
        "measurements": measurements,
        "gates": scored["gates"],
        "strict_success": scored["success"],
        "terminal_outcome": (
            "pawn_released_upright_on_target"
            if scored["success"]
            else "pawn_pick_place_consequence_gate_failed"
        ),
        "training_cannot_promote": True,
        "physical_authority": False,
        "render_backend": {
            "mujoco_gl": os.environ.get("MUJOCO_GL", "unspecified"),
            "pyopengl_platform": os.environ.get("PYOPENGL_PLATFORM", "unspecified"),
        },
        "artifacts": {
            video_path.name: sha256_file(video_path),
            arrays_path.name: sha256_file(arrays_path),
        },
    }
    receipt["canonical_payload_sha256"] = canonical_sha256(receipt)
    receipt_path = args.output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

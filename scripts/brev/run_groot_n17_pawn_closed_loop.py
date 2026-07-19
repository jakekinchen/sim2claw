#!/usr/bin/env python3
"""Run one historical off-product C8-to-A6 development smoke episode."""

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
from sim2claw.groot_evaluation_identity import verify_evaluation_manifest
from sim2claw.groot_execution import aggregate_temporal_action
from sim2claw.groot_rollout_trace import (
    array_sha256,
    contact_transition_events,
    validate_rollout_trace_lengths,
)
from sim2claw.groot_server_identity import (
    load_checkpoint_manifest,
    runtime_identity_receipt_binding,
    verify_runtime_identity,
)
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
from sim2claw.paths import REPO_ROOT
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
OWNER_PRODUCT_SCOPE = "brown_pawns_b_through_g_rank1_rank2_bidirectional"


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


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
    expected_states: np.ndarray,
) -> bool:
    model, data, actuator_ids, _, _ = initialize_episode()
    mujoco.mj_setState(
        model,
        data,
        initial_state,
        mujoco.mjtState.mjSTATE_INTEGRATION,
    )
    mujoco.mj_forward(model, data)
    matches: list[bool] = []
    for action, expected in zip(actions, expected_states, strict=True):
        data.ctrl[actuator_ids] = action
        for _ in range(PHYSICS_STEPS_PER_ACTION):
            mujoco.mj_step(model, data)
        matches.append(np.array_equal(_integration_state(model, data), expected))
    return all(matches)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint-manifest", type=Path, required=True)
    parser.add_argument("--evaluation-manifest", type=Path, required=True)
    parser.add_argument("--groot-root", type=Path, required=True)
    parser.add_argument("--processor-model-path", type=Path, required=True)
    parser.add_argument("--runtime-identity", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5555)
    parser.add_argument(
        "--acknowledge-off-product-c8-a6-smoke",
        action="store_true",
        help="required because this historical runner is outside the B-G product scope",
    )
    args = parser.parse_args()
    if not args.acknowledge_off_product_c8_a6_smoke:
        parser.error(
            "this runner is an off-product C8-to-A6 smoke; the product scope is "
            "brown B-G pawns between ranks 1 and 2"
        )
    if args.output.exists():
        parser.error("--output must not already exist")

    checkpoint_manifest = load_checkpoint_manifest(args.checkpoint_manifest)
    checkpoint_manifest_sha256 = sha256_file(args.checkpoint_manifest)
    evaluation_manifest = verify_evaluation_manifest(
        args.evaluation_manifest,
        repo_root=REPO_ROOT,
        groot_root=args.groot_root,
        runtime_assets={"processor_model": args.processor_model_path},
    )
    server_runtime_identity = verify_runtime_identity(
        args.runtime_identity,
        expected_manifest_path=args.checkpoint_manifest,
        expected_evaluation_manifest_path=args.evaluation_manifest,
        expected_host=args.host,
        expected_port=args.port,
    )
    runtime_receipt_binding = runtime_identity_receipt_binding(
        args.runtime_identity,
        server_runtime_identity,
    )
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
    client = PolicyClient(
        host=args.host,
        port=args.port,
        timeout_ms=120_000,
        strict=False,
    )
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
        "checkpoint_manifest_sha256": checkpoint_manifest_sha256,
        "checkpoint_payload_sha256": server_runtime_identity["checkpoint"][
            "checkpoint_payload_sha256"
        ],
        "evaluation_manifest_sha256": runtime_receipt_binding[
            "evaluation_implementation_manifest_sha256"
        ],
        "processor_model_path": str(args.processor_model_path.resolve(strict=True)),
    }
    for key, expected in expected_reset.items():
        if reset_info.get(key) != expected:
            raise RuntimeError(f"policy server acknowledged the wrong {key}")

    frames: list[np.ndarray] = []
    states: list[np.ndarray] = []
    requested_actions: list[np.ndarray] = []
    applied_actions: list[np.ndarray] = []
    integration_states: list[np.ndarray] = []
    integration_state_digests: list[str] = []
    pawn_piece_ids = tuple(sorted(piece_bodies))
    pawn_positions: list[np.ndarray] = []
    pawn_rotations: list[np.ndarray] = []
    target_pawn_rotations: list[np.ndarray] = []
    end_effector_positions: list[np.ndarray] = []
    target_robot_contacts: list[bool] = []
    target_jaw_contacts: list[bool] = []
    wrong_piece_contacts: list[bool] = []
    physics_step_indices: list[int] = []
    physics_times_seconds: list[float] = []
    physics_target_robot_contacts: list[bool] = []
    physics_target_jaw_contacts: list[bool] = []
    physics_wrong_piece_contacts: list[bool] = []
    physics_target_pawn_positions: list[np.ndarray] = []
    physics_target_pawn_rotations: list[np.ndarray] = []
    physics_end_effector_positions: list[np.ndarray] = []
    action_chunk_history: list[tuple[int, np.ndarray]] = []
    policy_queries: list[dict[str, Any]] = []
    next_query_step = 0
    runtime_identity_verified_before_first_query = False
    maximum_height = float(data.xpos[target_body][2])
    maximum_other_displacement = 0.0
    wrong_piece_contact = False
    physics_step_index = 0
    bounds = model.actuator_ctrlrange[actuator_ids]

    try:
        for sample_step in range(SAMPLE_COUNT):
            renderer.update_scene(data, camera="overhead")
            frame = renderer.render().copy()
            state = np.asarray(data.qpos[qpos_addresses], dtype=np.float32).copy()
            frames.append(frame)
            states.append(state)

            if sample_step >= next_query_step:
                if not runtime_identity_verified_before_first_query:
                    current_evaluation_manifest = verify_evaluation_manifest(
                        args.evaluation_manifest,
                        repo_root=REPO_ROOT,
                        groot_root=args.groot_root,
                        runtime_assets={
                            "processor_model": args.processor_model_path
                        },
                    )
                    if current_evaluation_manifest != evaluation_manifest:
                        raise RuntimeError(
                            "evaluation implementation identity changed before "
                            "inference"
                        )
                    current_runtime_identity = verify_runtime_identity(
                        args.runtime_identity,
                        expected_manifest_path=args.checkpoint_manifest,
                        expected_evaluation_manifest_path=(
                            args.evaluation_manifest
                        ),
                        expected_host=args.host,
                        expected_port=args.port,
                    )
                    if current_runtime_identity != server_runtime_identity:
                        raise RuntimeError(
                            "GR00T server runtime identity changed before inference"
                        )
                    runtime_identity_verified_before_first_query = True
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
            requested_actions.append(float32_action.copy())
            applied_action = np.asarray(
                np.clip(float32_action, bounds[:, 0], bounds[:, 1]),
                dtype=np.float64,
            )
            applied_actions.append(applied_action.copy())
            data.ctrl[actuator_ids] = applied_action
            action_target_robot_contact = False
            action_target_jaw_contact = False
            action_wrong_piece_contact = False
            for _ in range(PHYSICS_STEPS_PER_ACTION):
                mujoco.mj_step(model, data)
                physics_step_index += 1
                target_robot_contact = _robot_piece_contact(
                    model,
                    data,
                    robot_body_ids,
                    {target_body},
                )
                target_jaw_contact = _jaw_piece_contact(
                    model,
                    data,
                    jaw_bodies,
                    {target_body},
                )
                current_wrong_piece_contact = _robot_piece_contact(
                    model, data, robot_body_ids, other_body_ids
                )
                action_target_robot_contact = (
                    action_target_robot_contact or target_robot_contact
                )
                action_target_jaw_contact = (
                    action_target_jaw_contact or target_jaw_contact
                )
                action_wrong_piece_contact = (
                    action_wrong_piece_contact or current_wrong_piece_contact
                )
                wrong_piece_contact = (
                    wrong_piece_contact or current_wrong_piece_contact
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
                physics_step_indices.append(physics_step_index)
                physics_times_seconds.append(float(data.time))
                physics_target_robot_contacts.append(target_robot_contact)
                physics_target_jaw_contacts.append(target_jaw_contact)
                physics_wrong_piece_contacts.append(current_wrong_piece_contact)
                physics_target_pawn_positions.append(
                    np.asarray(data.xpos[target_body], dtype=np.float64).copy()
                )
                physics_target_pawn_rotations.append(
                    np.asarray(data.xmat[target_body], dtype=np.float64)
                    .reshape(3, 3)
                    .copy()
                )
                physics_end_effector_positions.append(
                    _pinch_point(model, data, "left", pinch_local).copy()
                )
            integration_state = _integration_state(model, data).copy()
            integration_states.append(integration_state)
            integration_state_digests.append(array_sha256(integration_state))
            pawn_positions.append(
                np.asarray(
                    [data.xpos[piece_bodies[name]] for name in pawn_piece_ids],
                    dtype=np.float64,
                ).copy()
            )
            pawn_rotations.append(
                np.asarray(
                    [
                        np.asarray(
                            data.xmat[piece_bodies[name]],
                            dtype=np.float64,
                        ).reshape(3, 3)
                        for name in pawn_piece_ids
                    ],
                    dtype=np.float64,
                ).copy()
            )
            target_pawn_rotations.append(
                np.asarray(data.xmat[target_body], dtype=np.float64)
                .reshape(3, 3)
                .copy()
            )
            end_effector_positions.append(
                _pinch_point(model, data, "left", pinch_local).copy()
            )
            target_robot_contacts.append(action_target_robot_contact)
            target_jaw_contacts.append(action_target_jaw_contact)
            wrong_piece_contacts.append(action_wrong_piece_contact)
    finally:
        renderer.close()

    requested_action_array = np.asarray(requested_actions, dtype=np.float32)
    applied_action_array = np.asarray(applied_actions, dtype=np.float64)
    integration_state_array = np.asarray(integration_states, dtype=np.float64)
    integration_digest_array = np.asarray(integration_state_digests, dtype="U64")
    pawn_position_array = np.asarray(pawn_positions, dtype=np.float64)
    pawn_rotation_array = np.asarray(pawn_rotations, dtype=np.float64)
    target_pawn_rotation_array = np.asarray(
        target_pawn_rotations,
        dtype=np.float64,
    )
    end_effector_position_array = np.asarray(
        end_effector_positions,
        dtype=np.float64,
    )
    validate_rollout_trace_lengths(
        sample_count=SAMPLE_COUNT,
        requested_actions=requested_action_array,
        applied_actions=applied_action_array,
        integration_states=integration_state_array,
        integration_state_digests=integration_digest_array,
        pawn_positions=pawn_position_array,
        pawn_rotations=pawn_rotation_array,
        end_effector_positions=end_effector_position_array,
    )
    replay_passed = replay_actions(
        initial_state,
        applied_action_array,
        integration_state_array,
    )
    expected_physics_trace_count = SAMPLE_COUNT * PHYSICS_STEPS_PER_ACTION
    physics_traces = (
        physics_step_indices,
        physics_times_seconds,
        physics_target_robot_contacts,
        physics_target_jaw_contacts,
        physics_wrong_piece_contacts,
        physics_target_pawn_positions,
        physics_target_pawn_rotations,
        physics_end_effector_positions,
    )
    if any(
        len(trace) != expected_physics_trace_count for trace in physics_traces
    ):
        raise RuntimeError("per-physics-step rollout traces are misaligned")
    physics_step_array = np.asarray(physics_step_indices, dtype=np.int64)
    physics_time_array = np.asarray(physics_times_seconds, dtype=np.float64)
    jaw_contact_events = contact_transition_events(
        np.asarray(physics_target_jaw_contacts, dtype=np.bool_),
        physics_steps=physics_step_array,
        times_seconds=physics_time_array,
        contact_name="target_jaw_contact",
    )
    robot_contact_events = contact_transition_events(
        np.asarray(physics_target_robot_contacts, dtype=np.bool_),
        physics_steps=physics_step_array,
        times_seconds=physics_time_array,
        contact_name="target_robot_contact",
    )
    final_position = np.asarray(data.xpos[target_body], dtype=np.float64)
    final_rotation = np.asarray(data.xmat[target_body], dtype=np.float64).reshape(3, 3)
    measurements = {
        "selected_piece_identity": True,
        "maximum_piece_rise_m": maximum_height - float(initial_target_position[2]),
        "final_xy_error_m": float(
            np.linalg.norm(final_position[:2] - target_position[:2])
        ),
        "final_height_error_m": float(abs(final_position[2] - target_position[2])),
        "final_upright_cosine": float(final_rotation[2, 2]),
        "final_linear_speed_m_s": float(
            np.linalg.norm(np.asarray(data.cvel[target_body][3:], dtype=np.float64))
        ),
        "gripper_clearance_m": float(
            np.linalg.norm(
                _pinch_point(model, data, "left", pinch_local) - final_position
            )
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
        "executed_action_count": len(applied_actions),
        "recorded_action_count": SAMPLE_COUNT,
        "exact_sample_hold_state_replay": replay_passed,
    }
    scored = score_pawn_consequences(measurements, evaluator)

    video_path = args.output / "episode.mp4"
    arrays_path = args.output / "trajectory.npz"
    _write_video(video_path, frames, 20)
    np.savez_compressed(
        arrays_path,
        observation_joint_states_before_action=np.asarray(
            states,
            dtype=np.float32,
        ),
        requested_actions=requested_action_array,
        applied_actions=applied_action_array,
        initial_integration_state=initial_state,
        post_action_integration_states=integration_state_array,
        post_action_integration_state_sha256=integration_digest_array,
        pawn_piece_ids=np.asarray(pawn_piece_ids, dtype="U64"),
        post_action_pawn_positions=pawn_position_array,
        post_action_pawn_rotation_matrices=pawn_rotation_array,
        post_action_target_pawn_rotation_matrices=target_pawn_rotation_array,
        post_action_end_effector_positions=end_effector_position_array,
        post_action_target_robot_contact=np.asarray(
            target_robot_contacts,
            dtype=np.bool_,
        ),
        post_action_target_jaw_contact=np.asarray(
            target_jaw_contacts,
            dtype=np.bool_,
        ),
        post_action_wrong_piece_contact=np.asarray(
            wrong_piece_contacts,
            dtype=np.bool_,
        ),
        physics_step_indices=physics_step_array,
        physics_times_seconds=physics_time_array,
        physics_target_robot_contact=np.asarray(
            physics_target_robot_contacts,
            dtype=np.bool_,
        ),
        physics_target_jaw_contact=np.asarray(
            physics_target_jaw_contacts,
            dtype=np.bool_,
        ),
        physics_wrong_piece_contact=np.asarray(
            physics_wrong_piece_contacts,
            dtype=np.bool_,
        ),
        physics_target_pawn_positions=np.asarray(
            physics_target_pawn_positions,
            dtype=np.float64,
        ),
        physics_target_pawn_rotation_matrices=np.asarray(
            physics_target_pawn_rotations,
            dtype=np.float64,
        ),
        physics_end_effector_positions=np.asarray(
            physics_end_effector_positions,
            dtype=np.float64,
        ),
    )
    receipt = {
        "schema_version": "sim2claw.groot_n17_pawn_closed_loop.v3",
        "proof_class": "learned_policy_simulation_development",
        "task_scope": "historical_off_product_far_side_smoke",
        "owner_product_scope": OWNER_PRODUCT_SCOPE,
        "matches_owner_product_scope": False,
        "checkpoint_id": "checkpoint-1000",
        "checkpoint_manifest_sha256": checkpoint_manifest_sha256,
        "checkpoint_manifest": checkpoint_manifest,
        **runtime_receipt_binding,
        "evaluation_implementation_manifest": evaluation_manifest,
        "server_runtime_identity_verified_before_first_query": (
            runtime_identity_verified_before_first_query
        ),
        "checkpoint_attribution_machine_verified": True,
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
        "trace_contract": {
            "schema_version": "sim2claw.groot_rollout_trace.v1",
            "requested_and_applied_actions_retained_separately": True,
            "initial_and_post_action_integration_states_retained": True,
            "per_state_integration_digests_retained": True,
            "all_pawn_positions_retained_after_each_action": True,
            "target_pawn_pose_retained_each_physics_step": True,
            "end_effector_position_retained_each_physics_step": True,
            "target_robot_target_jaw_and_wrong_piece_contacts_retained": True,
            "grasp_release_timing_derived_from_retained_contact_trace": True,
            "npz_arrays": [
                "observation_joint_states_before_action",
                "requested_actions",
                "applied_actions",
                "initial_integration_state",
                "post_action_integration_states",
                "post_action_integration_state_sha256",
                "pawn_piece_ids",
                "post_action_pawn_positions",
                "post_action_pawn_rotation_matrices",
                "post_action_target_pawn_rotation_matrices",
                "post_action_end_effector_positions",
                "post_action_target_robot_contact",
                "post_action_target_jaw_contact",
                "post_action_wrong_piece_contact",
                "physics_step_indices",
                "physics_times_seconds",
                "physics_target_robot_contact",
                "physics_target_jaw_contact",
                "physics_wrong_piece_contact",
                "physics_target_pawn_positions",
                "physics_target_pawn_rotation_matrices",
                "physics_end_effector_positions",
            ],
        },
        "trace_identities": {
            "requested_actions_sha256": array_sha256(requested_action_array),
            "applied_actions_sha256": array_sha256(applied_action_array),
            "initial_integration_state_sha256": array_sha256(initial_state),
            "post_action_integration_states_sha256": array_sha256(
                integration_state_array
            ),
            "post_action_integration_state_digests_sha256": array_sha256(
                integration_digest_array
            ),
            "post_action_pawn_positions_sha256": array_sha256(
                pawn_position_array
            ),
            "post_action_pawn_rotation_matrices_sha256": array_sha256(
                pawn_rotation_array
            ),
            "physics_target_pawn_positions_sha256": array_sha256(
                np.asarray(physics_target_pawn_positions, dtype=np.float64)
            ),
            "physics_end_effector_positions_sha256": array_sha256(
                np.asarray(physics_end_effector_positions, dtype=np.float64)
            ),
        },
        "contact_timing_events": {
            "target_robot": robot_contact_events,
            "target_jaw_grasp_release": jaw_contact_events,
        },
        "physics_trace_step_count": len(physics_step_indices),
        "rich_exact_replay_evidence_retained": True,
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

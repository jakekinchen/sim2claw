"""Deterministic current-scene pawn source candidate under policy execution semantics.

This generator owns actions, not success.  It writes a canonical, model-agnostic
episode candidate with exact float32 20 Hz sample-hold actions, synchronized RGB,
and out-of-line MuJoCo integration state.  Only ``pawn_source_evaluator`` may
admit the resulting rows.
"""

from __future__ import annotations

import json
import platform
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from .grasp import (
    JAW_OPEN_RAD,
    _actuator_map,
    _piece_bodies,
    _pinch_offset,
    _pinch_point,
    _solve_reach,
)
from .paths import REPO_ROOT
from .render import write_rgb_png
from .scene import (
    CURRENT_TASK_LAYOUT_ID,
    CURRENT_TASK_PIECE_LAYOUT,
    ROBOT_JOINTS,
    board_square_center,
    build_scene_spec,
    initialize_robot_poses,
    registered_board_center,
)
from .source_episode import (
    CURRENT_BOARD_POSE_ID,
    CURRENT_SCENE_ID,
    EPISODE_SCHEMA,
    RECEIPT_SCHEMA,
    SAMPLE_SCHEMA,
    build_source_sample,
    language_instruction,
    load_source_contract,
    sha256_file,
    source_contract_sha256,
    tree_manifest,
)


SOURCE_PIECE_ID = "tan_pawn_c8"
SOURCE_SQUARE = "c8"
DESTINATION_SQUARE = "c6"
SAMPLE_HZ = 20
PHYSICS_STEPS_PER_ACTION = 10
SETTLE_PHYSICS_STEPS = 300
EXPERT_MECHANISM_ID = "air_recenter_partial_release_vertical_extract_v1"
PAWN_JAW_SHUT_RAD = -0.10


def expert_phase_counts() -> dict[str, int]:
    """Return the frozen number of 20 Hz source rows in each semantic phase."""

    return {
        "stand_off": 42,
        "advance": 38,
        "close": 42,
        "lift": 60,
        "transit": 120,
        "air_recenter": 20,
        "lower": 90,
        "partial_release": 30,
        "vertical_extract": 35,
        "open_clear": 25,
        "settle": 60,
    }


def expected_action_count() -> int:
    return sum(expert_phase_counts().values())


def _integration_state(model: mujoco.MjModel, data: mujoco.MjData) -> list[float]:
    size = mujoco.mj_stateSize(model, mujoco.mjtState.mjSTATE_INTEGRATION)
    state = np.empty(size, dtype=np.float64)
    mujoco.mj_getState(
        model, data, state, mujoco.mjtState.mjSTATE_INTEGRATION
    )
    return state.astype(float).tolist()


def _body_name(model: mujoco.MjModel, body_id: int) -> str:
    return (
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id)
        or ("world" if body_id == 0 else f"body-{body_id}")
    )


def _contacts_for_step(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    *,
    physics_substep: int,
    accumulated: dict[tuple[str, str], dict[str, Any]],
) -> None:
    for contact_index in range(data.ncon):
        contact = data.contact[contact_index]
        names = sorted(
            (
                _body_name(model, int(model.geom_bodyid[contact.geom1])),
                _body_name(model, int(model.geom_bodyid[contact.geom2])),
            )
        )
        key = (names[0], names[1])
        entry = accumulated.setdefault(
            key,
            {
                "body_a": names[0],
                "body_b": names[1],
                "first_physics_substep": physics_substep,
                "last_physics_substep": physics_substep,
                "physics_substep_contact_count": 0,
                "position_world": contact.pos.astype(float).tolist(),
            },
        )
        entry["last_physics_substep"] = physics_substep
        entry["physics_substep_contact_count"] += 1
        entry["position_world"] = contact.pos.astype(float).tolist()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def collect_pawn_source_expert_candidate(
    output_directory: Path,
    *,
    render_size: int = 224,
) -> dict[str, Any]:
    """Write the one mechanism-proven c8-to-c6 source candidate.

    The directory must not exist.  The returned receipt remains explicitly
    pending admission until a separate evaluator replay passes every gate.
    """

    contract = load_source_contract()
    training_sources = set(contract["splits"]["training_source_piece_ids"])
    destinations = set(contract["scene"]["destination_squares"])
    if SOURCE_PIECE_ID not in training_sources:
        raise ValueError("the frozen expert source is no longer training-owned")
    if DESTINATION_SQUARE not in destinations:
        raise ValueError("the frozen expert destination is no longer declared")
    if render_size < 64:
        raise ValueError("source RGB render size must be at least 64 pixels")

    output_directory = output_directory.resolve()
    if output_directory.exists():
        raise FileExistsError(f"source candidate already exists: {output_directory}")
    output_directory.mkdir(parents=True)
    recording_id = (
        datetime.now(UTC).strftime("pawn-source-%Y%m%dT%H%M%SZ-")
        + uuid.uuid4().hex[:8]
    )

    model = build_scene_spec(
        piece_layout=CURRENT_TASK_PIECE_LAYOUT,
        board_center_in_table_frame_xy_m=registered_board_center(CURRENT_SCENE_ID),
    ).compile()
    if not np.isclose(float(model.opt.timestep), 0.005, atol=1e-12):
        raise ValueError("runtime MuJoCo timestep changed")
    data = mujoco.MjData(model)
    initialize_robot_poses(model, data)
    for _ in range(SETTLE_PHYSICS_STEPS):
        mujoco.mj_step(model, data)

    actuators = _actuator_map(model, "left")
    actuator_ids = np.asarray(
        [actuators[joint] for joint in ROBOT_JOINTS], dtype=np.int32
    )
    bounds = model.actuator_ctrlrange[actuator_ids]
    joint_ids = np.asarray(
        [
            mujoco.mj_name2id(
                model, mujoco.mjtObj.mjOBJ_JOINT, f"left_{joint}"
            )
            for joint in ROBOT_JOINTS
        ],
        dtype=np.int32,
    )
    qpos_addresses = np.asarray(
        [model.jnt_qposadr[joint_id] for joint_id in joint_ids], dtype=np.int32
    )
    dof_addresses = np.asarray(
        [model.jnt_dofadr[joint_id] for joint_id in joint_ids], dtype=np.int32
    )
    piece_bodies = _piece_bodies(model)
    piece_body = piece_bodies[SOURCE_PIECE_ID]
    gripper_body = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, "left_gripper"
    )
    mount_body = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, "left_base"
    )
    if min(*joint_ids.tolist(), piece_body, gripper_body, mount_body) < 0:
        raise ValueError("runtime scene is missing a frozen expert body or joint")

    pinch_local = _pinch_offset(model, data, "left")
    target_position = np.asarray(
        board_square_center(
            DESTINATION_SQUARE,
            board_center_in_table_frame_xy_m=registered_board_center(
                CURRENT_SCENE_ID
            ),
        ),
        dtype=np.float64,
    )
    target_pose = np.asarray(
        [*target_position, 1.0, 0.0, 0.0, 0.0], dtype=np.float64
    )
    initial_piece_position = np.asarray(data.xpos[piece_body], dtype=np.float64).copy()
    maximum_piece_height = float(initial_piece_position[2])
    mount = np.asarray(data.xpos[mount_body], dtype=np.float64)
    away = mount[:2] - initial_piece_position[:2]
    away /= max(float(np.linalg.norm(away)), 1e-12)
    neck = np.asarray(
        [
            initial_piece_position[0],
            initial_piece_position[1],
            initial_piece_position[2] + 0.041,
        ],
        dtype=np.float64,
    )
    stand_off = neck + np.asarray([away[0] * 0.055, away[1] * 0.055, 0.03])

    initial_path = output_directory / "initial_evaluator_privileged_state.json"
    _write_json(
        initial_path,
        {
            "schema_version": "sim2claw.evaluator_initial_privileged_state.v1",
            "episode_id": recording_id,
            "policy_adapter_access": False,
            "state": {
                "available": True,
                "mj_state_spec": "mjSTATE_INTEGRATION",
                "integration_state_float64": _integration_state(model, data),
                "piece_layout": CURRENT_TASK_PIECE_LAYOUT,
                "scene_id": CURRENT_SCENE_ID,
            },
        },
    )

    samples_path = output_directory / "samples.jsonl"
    privileged_path = output_directory / "evaluator_privileged_state.jsonl"
    renderers = {
        "top": mujoco.Renderer(model, height=render_size, width=render_size),
        "wrist": mujoco.Renderer(model, height=render_size, width=render_size),
    }
    cameras = {"top": "overhead", "wrist": "left_wrist_cam"}
    rows: list[dict[str, Any]] = []
    privileged_rows: list[dict[str, Any]] = []
    phase_runs: list[dict[str, Any]] = []
    maximum_ik_residual = 0.0
    instruction = language_instruction(
        SOURCE_PIECE_ID, SOURCE_SQUARE, DESTINATION_SQUARE
    )

    def solve_goal(point: np.ndarray, jaw: float) -> np.ndarray:
        nonlocal maximum_ik_residual
        pose, residual = _solve_reach(
            model, data, "left", np.asarray(point, dtype=np.float64), pinch_local
        )
        maximum_ik_residual = max(maximum_ik_residual, float(residual))
        if residual > 0.003:
            raise RuntimeError(f"expert IK residual exceeded 3 mm: {residual}")
        return np.asarray(
            [jaw if joint == "gripper" else pose[joint] for joint in ROBOT_JOINTS],
            dtype=np.float64,
        )

    def execute_action(action: np.ndarray, phase: str) -> None:
        nonlocal maximum_piece_height
        sample_index = len(rows)
        float32_action = np.asarray(action, dtype=np.float32)
        if float32_action.shape != (6,) or not np.isfinite(float32_action).all():
            raise ValueError("expert emitted an invalid action")
        clipped = np.clip(
            float32_action, bounds[:, 0], bounds[:, 1]
        ).astype(np.float64)
        contacts: dict[tuple[str, str], dict[str, Any]] = {}
        data.ctrl[actuator_ids] = clipped
        for substep in range(PHYSICS_STEPS_PER_ACTION):
            mujoco.mj_step(model, data)
            _contacts_for_step(
                model,
                data,
                physics_substep=substep,
                accumulated=contacts,
            )
            maximum_piece_height = max(
                maximum_piece_height, float(data.xpos[piece_body][2])
            )

        timestamp = sample_index / SAMPLE_HZ
        rgb: dict[str, Any] = {}
        for stream, renderer in renderers.items():
            renderer.update_scene(data, camera=cameras[stream])
            frame = renderer.render().copy()
            relative_path = Path("rgb") / stream / f"{sample_index:06d}.png"
            frame_path = output_directory / relative_path
            write_rgb_png(frame_path, frame)
            rgb[stream] = {
                "available": True,
                "path": relative_path.as_posix(),
                "timestamp_monotonic_seconds": timestamp,
                "sha256": sha256_file(frame_path),
            }

        piece_position = data.xpos[piece_body].astype(float).tolist()
        piece_quaternion = data.xquat[piece_body].astype(float).tolist()
        end_effector_position = data.xpos[gripper_body].astype(float).tolist()
        end_effector_quaternion = data.xquat[gripper_body].astype(float).tolist()
        row = build_source_sample(
            episode_id=recording_id,
            sample_index=sample_index,
            timestamp_monotonic_seconds=timestamp,
            instruction=instruction,
            raw_sample={
                "expert_mechanism_id": EXPERT_MECHANISM_ID,
                "expert_phase": phase,
                "follower_command_rad": float32_action.astype(float).tolist(),
                "follower_actual_position_rad": data.qpos[qpos_addresses]
                .astype(float)
                .tolist(),
                "follower_actual_velocity_rad_s": data.qvel[dof_addresses]
                .astype(float)
                .tolist(),
                "selected_piece_pose_world": [*piece_position, *piece_quaternion],
                "continuous_target_pose_world": target_pose.astype(float).tolist(),
                "end_effector_pose_world": [
                    *end_effector_position,
                    *end_effector_quaternion,
                ],
                "gripper_joint_position_rad": float(data.qpos[qpos_addresses[-1]]),
                "contacts": list(contacts.values()),
                "simulator_events": [
                    {
                        "type": "expert_phase",
                        "phase": phase,
                        "phase_start": (
                            not rows or rows[-1].get("expert_phase") != phase
                        ),
                    }
                ],
            },
            rgb=rgb,
            action_owner="geometric_expert",
            assistance=False,
            intervention=False,
        )
        rows.append(row)
        privileged_rows.append(
            {
                "schema_version": "sim2claw.evaluator_privileged_state.v1",
                "episode_id": recording_id,
                "sample_index": sample_index,
                "timestamp_monotonic_seconds": timestamp,
                "policy_adapter_access": False,
                "state": {
                    "available": True,
                    "mj_state_spec": "mjSTATE_INTEGRATION",
                    "integration_state_float64": _integration_state(model, data),
                    "selected_piece_body_id": piece_body,
                    "selected_piece_pose_world": [
                        *piece_position,
                        *piece_quaternion,
                    ],
                    "all_piece_poses_world": {
                        name: [
                            *data.xpos[body_id].astype(float).tolist(),
                            *data.xquat[body_id].astype(float).tolist(),
                        ]
                        for name, body_id in sorted(piece_bodies.items())
                    },
                },
            }
        )

    def execute_phase(
        name: str, goal: np.ndarray, count: int, *, ramp: int = 16
    ) -> None:
        start_index = len(rows)
        start = data.ctrl[actuator_ids].copy()
        for phase_index in range(count):
            blend = min(1.0, float(phase_index + 1) / float(ramp))
            execute_action(start + blend * (goal - start), name)
        phase_runs.append(
            {
                "phase": name,
                "start_sample_index": start_index,
                "end_sample_index_exclusive": len(rows),
                "sample_count": count,
            }
        )

    try:
        execute_phase("stand_off", solve_goal(stand_off, JAW_OPEN_RAD), 42)
        advance = solve_goal(neck, JAW_OPEN_RAD)
        execute_phase("advance", advance, 38)
        close = advance.copy()
        close[-1] = PAWN_JAW_SHUT_RAD
        execute_phase("close", close, 42)
        execute_phase(
            "lift",
            solve_goal(
                neck + np.asarray([0.0, 0.0, 0.10]), PAWN_JAW_SHUT_RAD
            ),
            60,
        )

        held_offset = _pinch_point(model, data, "left", pinch_local) - data.xpos[
            piece_body
        ]
        start_pinch = _pinch_point(model, data, "left", pinch_local).copy()
        target_pinch = target_position + held_offset + np.asarray([0.0, 0.0, 0.10])
        transit_start = len(rows)
        for waypoint in range(1, 41):
            point = start_pinch + (waypoint / 40.0) * (target_pinch - start_pinch)
            execute_phase(
                "transit",
                solve_goal(point, PAWN_JAW_SHUT_RAD),
                3,
                ramp=3,
            )
        phase_runs[:] = [run for run in phase_runs if run["phase"] != "transit"]
        phase_runs.append(
            {
                "phase": "transit",
                "start_sample_index": transit_start,
                "end_sample_index_exclusive": len(rows),
                "sample_count": 120,
            }
        )

        correction = np.asarray(
            [
                target_position[0] - data.xpos[piece_body][0],
                target_position[1] - data.xpos[piece_body][1],
                0.0,
            ]
        )
        execute_phase(
            "air_recenter",
            solve_goal(
                _pinch_point(model, data, "left", pinch_local) + correction,
                PAWN_JAW_SHUT_RAD,
            ),
            20,
            ramp=12,
        )

        start_pinch = _pinch_point(model, data, "left", pinch_local).copy()
        held_offset = start_pinch - data.xpos[piece_body]
        target_pinch = target_position + held_offset + np.asarray([0.0, 0.0, 0.005])
        lower_start = len(rows)
        for waypoint in range(1, 31):
            point = start_pinch + (waypoint / 30.0) * (target_pinch - start_pinch)
            execute_phase(
                "lower",
                solve_goal(point, PAWN_JAW_SHUT_RAD),
                3,
                ramp=3,
            )
        phase_runs[:] = [run for run in phase_runs if run["phase"] != "lower"]
        phase_runs.append(
            {
                "phase": "lower",
                "start_sample_index": lower_start,
                "end_sample_index_exclusive": len(rows),
                "sample_count": 90,
            }
        )

        partial_release = data.ctrl[actuator_ids].copy()
        partial_release[-1] = 0.15
        execute_phase("partial_release", partial_release, 30, ramp=20)
        current_pinch = _pinch_point(model, data, "left", pinch_local)
        execute_phase(
            "vertical_extract",
            solve_goal(current_pinch + np.asarray([0.0, 0.0, 0.08]), 0.15),
            35,
            ramp=20,
        )
        open_clear = data.ctrl[actuator_ids].copy()
        open_clear[-1] = JAW_OPEN_RAD
        execute_phase("open_clear", open_clear, 25, ramp=16)
        execute_phase("settle", data.ctrl[actuator_ids].copy(), 60, ramp=1)
    finally:
        for renderer in renderers.values():
            renderer.close()

    if len(rows) != expected_action_count():
        raise RuntimeError("frozen expert schedule produced the wrong action count")
    if sum(run["sample_count"] for run in phase_runs) != len(rows):
        raise RuntimeError("expert phase receipt does not cover every source row")

    samples_path.write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )
    privileged_path.write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in privileged_rows
        ),
        encoding="utf-8",
    )

    final_position = np.asarray(data.xpos[piece_body], dtype=np.float64)
    generated_at = datetime.now(UTC).isoformat()
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "source_episode_schema": EPISODE_SCHEMA,
        "source_sample_schema": SAMPLE_SCHEMA,
        "source_contract_sha256": source_contract_sha256(),
        "recording_id": recording_id,
        "label": "tan pawn c8 to c6 scene-v3 geometric expert",
        "skill": "full_episode",
        "outcome_label": "pending_independent_evaluator",
        "task_id": contract["contract_id"],
        "mode": "simulation_geometric_expert",
        "proof_class": "simulation_geometric_expert_source_candidate",
        "piece_id": SOURCE_PIECE_ID,
        "piece_type": "pawn",
        "piece_color": "tan",
        "source_square": SOURCE_SQUARE,
        "destination_square": DESTINATION_SQUARE,
        "initial_layout_id": CURRENT_TASK_LAYOUT_ID,
        "piece_layout": CURRENT_TASK_PIECE_LAYOUT,
        "scene_id": CURRENT_SCENE_ID,
        "board_pose_id": CURRENT_BOARD_POSE_ID,
        "workcell_registration": {
            "workspace_pose_id": contract["scene"]["workspace_pose_id"],
            "board_scene_id": CURRENT_SCENE_ID,
            "board_pose_id": CURRENT_BOARD_POSE_ID,
            "board_center_in_table_frame_xy_m": contract["scene"][
                "board_center_in_table_frame_xy_m"
            ],
            "robotward_displacement_from_reference_pose_m": contract["scene"][
                "robotward_displacement_from_reference_pose_m"
            ],
            "robotward_axis_in_table_frame": "+y",
            "fiducial_pose_id": contract["scene"]["fiducial_pose_id"],
            "fiducial_center_in_table_frame_xy_m": contract["scene"][
                "fiducial_center_in_table_frame_xy_m"
            ],
        },
        "sample_hz": SAMPLE_HZ,
        "sample_count": len(rows),
        "duration_seconds": len(rows) / SAMPLE_HZ,
        "samples_path": samples_path.name,
        "samples_sha256": sha256_file(samples_path),
        "evaluator_privileged_state_path": privileged_path.name,
        "evaluator_privileged_state_sha256": sha256_file(privileged_path),
        "evaluator_privileged_state_policy_adapter_access": False,
        "initial_evaluator_privileged_state_path": initial_path.name,
        "initial_evaluator_privileged_state_sha256": sha256_file(initial_path),
        "rgb_streams": tree_manifest(output_directory / "rgb"),
        "scene_reset_seed": 0,
        "language_instruction": instruction,
        "source_identity": {
            "kind": "deterministic_geometric_expert",
            "mechanism_id": EXPERT_MECHANISM_ID,
            "generator_path": "src/sim2claw/pawn_source_expert.py",
            "generator_sha256": sha256_file(Path(__file__)),
            "source_episode_module_sha256": sha256_file(
                REPO_ROOT / "src" / "sim2claw" / "source_episode.py"
            ),
            "scene_module_sha256": sha256_file(
                REPO_ROOT / "src" / "sim2claw" / "scene.py"
            ),
            "grasp_module_sha256": sha256_file(
                REPO_ROOT / "src" / "sim2claw" / "grasp.py"
            ),
        },
        "model_identity": None,
        "checkpoint_identity": None,
        "action_owner": "geometric_expert",
        "assistance_frames": 0,
        "intervention_frames": 0,
        "lineage": {
            "parent_source_episode_id": None,
            "failed_prefix_source_episode_id": None,
            "corrective_suffix_parent_state_sha256": None,
            "collection_kind": "original_source_episode",
        },
        "execution": {
            "action_representation": "absolute_joint_position_target",
            "action_dtype": "float32",
            "sample_hold_hz": SAMPLE_HZ,
            "physics_timestep_seconds": float(model.opt.timestep),
            "physics_steps_per_action": PHYSICS_STEPS_PER_ACTION,
        },
        "expert_schedule": {
            "mechanism_id": EXPERT_MECHANISM_ID,
            "phase_counts": expert_phase_counts(),
            "phase_runs": sorted(phase_runs, key=lambda run: run["start_sample_index"]),
            "maximum_ik_residual_m": maximum_ik_residual,
            "release_clearance_m": 0.005,
            "partial_release_joint_target_rad": 0.15,
            "closed_jaw_joint_target_rad": PAWN_JAW_SHUT_RAD,
            "vertical_extract_m": 0.08,
        },
        "generator_diagnostics_not_evaluator_authority": {
            "maximum_piece_rise_m": maximum_piece_height
            - float(initial_piece_position[2]),
            "final_xy_error_m": float(
                np.linalg.norm(final_position[:2] - target_position[:2])
            ),
        },
        "runtime": {
            "mujoco_version": mujoco.mj_versionString(),
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "render_size": [render_size, render_size],
        },
        "training_admission": "pending_independent_cpu_fp32_evaluator",
        "is_training_data": False,
        "held_out_membership": False,
        "generated_artifact_ignored_by_git": True,
        "physical_authority_created": False,
        "created_at": generated_at,
    }
    _write_json(output_directory / "recording_receipt.json", receipt)
    return {
        "output_directory": str(output_directory),
        "recording_id": recording_id,
        "sample_count": len(rows),
        "duration_seconds": len(rows) / SAMPLE_HZ,
        "receipt_sha256": sha256_file(output_directory / "recording_receipt.json"),
        "samples_sha256": receipt["samples_sha256"],
        "training_admission": receipt["training_admission"],
        "strict_success": None,
    }

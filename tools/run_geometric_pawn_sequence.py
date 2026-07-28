#!/usr/bin/env python3
"""Execute one admitted pawn placement followed by a geometric grasp-return.

The first stage replays an independently admitted canonical source episode.
The second stage is compiled from exact scene geometry in the resulting live
MuJoCo state, lifts a second pawn, returns it to its starting square, releases
it, and clears the gripper.  The resulting arrays are simulation-only evidence
and grant no hardware authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from sim2claw.grasp import (
    JAW_OPEN_RAD,
    _actuator_map,
    _jaw_body_ids,
    _piece_bodies,
    _pinch_offset,
    _pinch_point,
    _solve_reach,
)
from sim2claw.learning_factory_artifacts import atomic_write_json
from sim2claw.pawn_source_evaluator import (
    _integration_state,
    _jaw_piece_contact,
    load_pawn_evaluator_contract,
    score_pawn_consequences,
)
from sim2claw.scene import (
    CURRENT_TASK_PIECE_LAYOUT,
    ROBOT_JOINTS,
    build_scene_spec,
    registered_board_center,
)
from sim2claw.source_episode import (
    CURRENT_SCENE_ID,
    load_source_episode,
    sha256_file,
)


SECOND_PIECE = "tan_pawn_e8"
SECOND_SOURCE_SQUARE = "e8"
SECOND_NECK_HEIGHT_M = 0.026
SECOND_JAW_SHUT_RAD = -0.15
SECOND_LIFT_CLEARANCE_M = 0.09
PHYSICS_STEPS_PER_ACTION = 10


def _raw_action_sha256(actions: np.ndarray) -> str:
    canonical = np.asarray(actions, dtype="<f4", order="C")
    return hashlib.sha256(canonical.tobytes(order="C")).hexdigest()


def _body_name(model: mujoco.MjModel, body_id: int) -> str:
    return (
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id)
        or ("world" if body_id == 0 else f"body-{body_id}")
    )


def _wrong_robot_piece_contacts(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    *,
    robot_bodies: set[int],
    other_piece_bodies: set[int],
) -> set[str]:
    identities: set[str] = set()
    for contact_index in range(data.ncon):
        contact = data.contact[contact_index]
        bodies = {
            int(model.geom_bodyid[contact.geom1]),
            int(model.geom_bodyid[contact.geom2]),
        }
        robot = bodies & robot_bodies
        other = bodies & other_piece_bodies
        for robot_body in robot:
            for piece_body in other:
                identities.add(
                    f"{_body_name(model, robot_body)}->{_body_name(model, piece_body)}"
                )
    return identities


def _save_array(output: Path, name: str, actions: np.ndarray) -> dict[str, Any]:
    path = output / name
    np.save(path, np.asarray(actions, dtype="<f4", order="C"), allow_pickle=False)
    return {
        "path": path.name,
        "shape": list(actions.shape),
        "dtype": "float32_little_endian",
        "raw_c_order_sha256": _raw_action_sha256(actions),
        "npy_sha256": sha256_file(path),
    }


def _execute_actions(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    *,
    actuator_ids: np.ndarray,
    bounds: np.ndarray,
    actions: np.ndarray,
    robot_bodies: set[int],
    other_piece_bodies: set[int],
    selected_piece_body: int,
    jaw_bodies: set[int],
) -> dict[str, Any]:
    wrong_contacts: set[str] = set()
    jaw_contact_substeps = 0
    clipped_rows = 0
    for raw_action in np.asarray(actions, dtype="<f4"):
        clipped = np.clip(raw_action, bounds[:, 0], bounds[:, 1]).astype(
            np.float64
        )
        clipped_rows += int(
            not np.array_equal(clipped.astype(np.float32), raw_action)
        )
        data.ctrl[actuator_ids] = clipped
        for _ in range(PHYSICS_STEPS_PER_ACTION):
            mujoco.mj_step(model, data)
            wrong_contacts.update(
                _wrong_robot_piece_contacts(
                    model,
                    data,
                    robot_bodies=robot_bodies,
                    other_piece_bodies=other_piece_bodies,
                )
            )
            jaw_contact_substeps += int(
                _jaw_piece_contact(
                    model,
                    data,
                    jaw_bodies,
                    {selected_piece_body},
                )
            )
    return {
        "wrong_contact_identities": sorted(wrong_contacts),
        "jaw_contact_substeps": jaw_contact_substeps,
        "clipped_action_rows": clipped_rows,
    }


def _compile_and_execute_grasp_return(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    *,
    piece_body: int,
    actuator_ids: np.ndarray,
    bounds: np.ndarray,
    pinch_local: np.ndarray,
    jaw_bodies: set[int],
    robot_bodies: set[int],
    other_piece_bodies: set[int],
) -> tuple[np.ndarray, dict[str, Any]]:
    mount_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, "left_base"
    )
    mount = np.asarray(data.xpos[mount_id], dtype=np.float64)
    initial_piece = np.asarray(data.xpos[piece_body], dtype=np.float64).copy()
    away = mount[:2] - initial_piece[:2]
    away /= max(float(np.linalg.norm(away)), 1e-12)
    neck = initial_piece + np.asarray([0.0, 0.0, SECOND_NECK_HEIGHT_M])
    stand_off = neck + np.asarray([away[0] * 0.055, away[1] * 0.055, 0.03])
    qpos_addresses = np.asarray(
        [
            model.jnt_qposadr[
                mujoco.mj_name2id(
                    model, mujoco.mjtObj.mjOBJ_JOINT, f"left_{joint}"
                )
            ]
            for joint in ROBOT_JOINTS
        ],
        dtype=np.int32,
    )
    actions: list[np.ndarray] = []
    phases: list[dict[str, Any]] = []
    wrong_contacts: set[str] = set()
    jaw_contact_substeps = 0
    clipped_rows = 0
    maximum_rise = 0.0
    maximum_ik_residual = 0.0

    def solve(
        target: np.ndarray,
        jaw: float,
        *,
        seed: np.ndarray | None = None,
    ) -> np.ndarray:
        nonlocal maximum_ik_residual
        seed_data = data
        if seed is not None:
            seed_data = mujoco.MjData(model)
            seed_data.qpos[:] = data.qpos
            seed_data.qvel[:] = 0.0
            seed_data.qpos[qpos_addresses] = np.asarray(seed, dtype=np.float64)
            mujoco.mj_forward(model, seed_data)
        pose, residual = _solve_reach(
            model,
            seed_data,
            "left",
            np.asarray(target, dtype=np.float64),
            pinch_local,
        )
        maximum_ik_residual = max(maximum_ik_residual, float(residual))
        if residual > 0.003:
            raise RuntimeError(f"second-stage IK residual exceeded 3 mm: {residual}")
        return np.asarray(
            [
                jaw if joint == "gripper" else pose[joint]
                for joint in ROBOT_JOINTS
            ],
            dtype=np.float64,
        )

    def execute_phase(
        name: str,
        goal: np.ndarray,
        count: int,
        *,
        ramp: int = 16,
    ) -> None:
        nonlocal jaw_contact_substeps, clipped_rows, maximum_rise
        start_index = len(actions)
        start = data.ctrl[actuator_ids].copy()
        for phase_index in range(count):
            blend = min(1.0, float(phase_index + 1) / float(ramp))
            action = np.asarray(
                start + blend * (goal - start), dtype=np.float32
            )
            clipped = np.clip(action, bounds[:, 0], bounds[:, 1]).astype(
                np.float64
            )
            clipped_rows += int(
                not np.array_equal(clipped.astype(np.float32), action)
            )
            actions.append(action)
            data.ctrl[actuator_ids] = clipped
            for _ in range(PHYSICS_STEPS_PER_ACTION):
                mujoco.mj_step(model, data)
                maximum_rise = max(
                    maximum_rise,
                    float(data.xpos[piece_body][2] - initial_piece[2]),
                )
                wrong_contacts.update(
                    _wrong_robot_piece_contacts(
                        model,
                        data,
                        robot_bodies=robot_bodies,
                        other_piece_bodies=other_piece_bodies,
                    )
                )
                jaw_contact_substeps += int(
                    _jaw_piece_contact(
                        model,
                        data,
                        jaw_bodies,
                        {piece_body},
                    )
                )
        phases.append(
            {
                "phase": name,
                "start_action_index": start_index,
                "end_action_index_exclusive": len(actions),
                "action_count": count,
            }
        )

    execute_phase("stand_off", solve(stand_off, JAW_OPEN_RAD), 42)
    advance = solve(neck, JAW_OPEN_RAD)
    execute_phase("advance", advance, 38)
    closed = advance.copy()
    closed[-1] = SECOND_JAW_SHUT_RAD
    execute_phase("close", closed, 42)
    lift = solve(
        neck + np.asarray([0.0, 0.0, SECOND_LIFT_CLEARANCE_M]),
        SECOND_JAW_SHUT_RAD,
    )
    execute_phase("lift", lift, 60)
    if float(data.xpos[piece_body][2] - initial_piece[2]) < 0.04:
        raise RuntimeError("second pawn did not remain lifted")

    start_pinch = _pinch_point(model, data, "left", pinch_local).copy()
    held_offset = start_pinch - data.xpos[piece_body]
    target_pinch = initial_piece + held_offset + np.asarray([0.0, 0.0, 0.005])
    planned = lift
    lower_start = len(actions)
    for waypoint in range(1, 31):
        point = start_pinch + (waypoint / 30.0) * (
            target_pinch - start_pinch
        )
        planned = solve(point, SECOND_JAW_SHUT_RAD, seed=planned)
        execute_phase("lower", planned, 3, ramp=3)
    phases = [phase for phase in phases if phase["phase"] != "lower"]
    phases.append(
        {
            "phase": "lower",
            "start_action_index": lower_start,
            "end_action_index_exclusive": len(actions),
            "action_count": 90,
        }
    )
    partial_release = data.ctrl[actuator_ids].copy()
    partial_release[-1] = 0.15
    execute_phase("partial_release", partial_release, 30, ramp=20)
    current_pinch = _pinch_point(model, data, "left", pinch_local)
    execute_phase(
        "vertical_extract",
        solve(
            current_pinch + np.asarray([0.0, 0.0, 0.08]),
            0.15,
            seed=planned,
        ),
        35,
        ramp=20,
    )
    open_clear = data.ctrl[actuator_ids].copy()
    open_clear[-1] = JAW_OPEN_RAD
    execute_phase("open_clear", open_clear, 25, ramp=16)
    execute_phase("settle", data.ctrl[actuator_ids].copy(), 60, ramp=1)
    return np.asarray(actions, dtype="<f4"), {
        "phases": sorted(phases, key=lambda phase: phase["start_action_index"]),
        "maximum_piece_rise_m": maximum_rise,
        "maximum_ik_residual_m": maximum_ik_residual,
        "wrong_contact_identities": sorted(wrong_contacts),
        "jaw_contact_substeps": jaw_contact_substeps,
        "clipped_action_rows": clipped_rows,
    }


def run_sequence(base_episode: Path, output: Path) -> dict[str, Any]:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    base_episode = base_episode.resolve()
    admission_path = base_episode / "admission_verdict.json"
    admission = json.loads(admission_path.read_text(encoding="utf-8"))
    if not admission.get("strict_success"):
        raise ValueError("first stage must have a strict evaluator admission")
    receipt, rows = load_source_episode(base_episode)
    if admission.get("source_samples_sha256") != receipt.get("samples_sha256"):
        raise ValueError("first-stage admission does not bind the source samples")
    first_piece = str(receipt["piece_id"])
    first_actions = np.asarray(
        [row["action"]["joint_target_rad"] for row in rows], dtype="<f4"
    )

    model = build_scene_spec(
        piece_layout=CURRENT_TASK_PIECE_LAYOUT,
        board_center_in_table_frame_xy_m=registered_board_center(
            CURRENT_SCENE_ID
        ),
        include_visual_props=True,
    ).compile()
    data = mujoco.MjData(model)
    initial_payload = json.loads(
        (
            base_episode
            / str(receipt["initial_evaluator_privileged_state_path"])
        ).read_text(encoding="utf-8")
    )
    initial_state = np.asarray(
        initial_payload["state"]["integration_state_float64"],
        dtype=np.float64,
    )
    mujoco.mj_setState(
        model, data, initial_state, mujoco.mjtState.mjSTATE_INTEGRATION
    )
    mujoco.mj_forward(model, data)

    actuators = _actuator_map(model, "left")
    actuator_ids = np.asarray(
        [actuators[joint] for joint in ROBOT_JOINTS], dtype=np.int32
    )
    bounds = model.actuator_ctrlrange[actuator_ids]
    pieces = _piece_bodies(model)
    robot_bodies = {
        body_id
        for body_id in range(model.nbody)
        if (_body_name(model, body_id)).startswith("left_")
    }
    jaw_bodies = _jaw_body_ids(model, "left")
    first_execution = _execute_actions(
        model,
        data,
        actuator_ids=actuator_ids,
        bounds=bounds,
        actions=first_actions,
        robot_bodies=robot_bodies,
        other_piece_bodies={
            body_id for name, body_id in pieces.items() if name != first_piece
        },
        selected_piece_body=pieces[first_piece],
        jaw_bodies=jaw_bodies,
    )
    final_privileged_rows = [
        json.loads(line)
        for line in (
            base_episode / str(receipt["evaluator_privileged_state_path"])
        ).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    expected_first_final_state = np.asarray(
        final_privileged_rows[-1]["state"]["integration_state_float64"],
        dtype=np.float64,
    )
    first_exact_state_match = np.array_equal(
        _integration_state(model, data), expected_first_final_state
    )
    if not first_exact_state_match:
        raise RuntimeError("first stage diverged from its admitted exact replay")

    reset_pose = np.asarray(
        receipt["simulation_reset"]["left_arm_joint_pose_radians"],
        dtype=np.float64,
    )
    transition_start = data.ctrl[actuator_ids].copy()
    transition_actions = []
    for index in range(100):
        blend = float(index + 1) / 100.0
        transition_actions.append(
            np.asarray(
                transition_start + blend * (reset_pose - transition_start),
                dtype=np.float32,
            )
        )
    transition_actions.extend(
        [np.asarray(reset_pose, dtype=np.float32)] * 100
    )
    transition_actions_array = np.asarray(transition_actions, dtype="<f4")
    transition_execution = _execute_actions(
        model,
        data,
        actuator_ids=actuator_ids,
        bounds=bounds,
        actions=transition_actions_array,
        robot_bodies=robot_bodies,
        other_piece_bodies=set(pieces.values()),
        selected_piece_body=pieces[SECOND_PIECE],
        jaw_bodies=jaw_bodies,
    )
    if (
        transition_execution["wrong_contact_identities"]
        or transition_execution["clipped_action_rows"]
    ):
        raise RuntimeError("interstage reset was not collision-free and unclipped")

    branch_state = _integration_state(model, data).copy()
    branch_piece_positions = {
        name: np.asarray(data.xpos[body_id], dtype=np.float64).copy()
        for name, body_id in pieces.items()
    }
    second_body = pieces[SECOND_PIECE]
    second_initial = branch_piece_positions[SECOND_PIECE].copy()
    pinch_local = _pinch_offset(model, data, "left")
    second_actions, second_diagnostics = _compile_and_execute_grasp_return(
        model,
        data,
        piece_body=second_body,
        actuator_ids=actuator_ids,
        bounds=bounds,
        pinch_local=pinch_local,
        jaw_bodies=jaw_bodies,
        robot_bodies=robot_bodies,
        other_piece_bodies={
            body_id for name, body_id in pieces.items() if name != SECOND_PIECE
        },
    )
    first_second_final_state = _integration_state(model, data).copy()

    replay = mujoco.MjData(model)
    mujoco.mj_setState(
        model, replay, branch_state, mujoco.mjtState.mjSTATE_INTEGRATION
    )
    mujoco.mj_forward(model, replay)
    second_replay = _execute_actions(
        model,
        replay,
        actuator_ids=actuator_ids,
        bounds=bounds,
        actions=second_actions,
        robot_bodies=robot_bodies,
        other_piece_bodies={
            body_id for name, body_id in pieces.items() if name != SECOND_PIECE
        },
        selected_piece_body=second_body,
        jaw_bodies=jaw_bodies,
    )
    exact_second_replay = np.array_equal(
        _integration_state(model, replay), first_second_final_state
    )
    final_position = np.asarray(replay.xpos[second_body], dtype=np.float64)
    final_rotation = np.asarray(
        replay.xmat[second_body], dtype=np.float64
    ).reshape(3, 3)
    displacements = {
        name: float(
            np.linalg.norm(replay.xpos[body_id] - branch_piece_positions[name])
        )
        for name, body_id in pieces.items()
        if name != SECOND_PIECE
    }
    worst_other = max(displacements, key=displacements.get)
    wrong_identities = sorted(
        set(second_diagnostics["wrong_contact_identities"])
        | set(second_replay["wrong_contact_identities"])
    )
    measurements = {
        "selected_piece_identity": True,
        "maximum_piece_rise_m": second_diagnostics["maximum_piece_rise_m"],
        "final_xy_error_m": float(
            np.linalg.norm(final_position[:2] - second_initial[:2])
        ),
        "final_height_error_m": float(
            abs(final_position[2] - second_initial[2])
        ),
        "final_upright_cosine": float(final_rotation[2, 2]),
        "final_linear_speed_m_s": float(
            np.linalg.norm(replay.cvel[second_body][3:])
        ),
        "gripper_clearance_m": float(
            np.linalg.norm(
                _pinch_point(model, replay, "left", pinch_local)
                - final_position
            )
        ),
        "maximum_other_piece_displacement_m": displacements[worst_other],
        "target_displacement_m": float(
            np.linalg.norm(final_position - second_initial)
        ),
        "wrong_piece_contact": bool(wrong_identities),
        "final_jaw_piece_contact": _jaw_piece_contact(
            model, replay, jaw_bodies, set(pieces.values())
        ),
        "assistance_frames": 0,
        "declared_action_owner": True,
        "executed_action_count": int(second_actions.shape[0]),
        "recorded_action_count": int(second_actions.shape[0]),
        "exact_sample_hold_state_replay": exact_second_replay,
    }
    scored = score_pawn_consequences(
        measurements, load_pawn_evaluator_contract()
    )
    arrays = {
        "first_stage": _save_array(
            output, "c8_to_a6_actions_float32.npy", first_actions
        ),
        "interstage_reset": _save_array(
            output,
            "interstage_reset_actions_float32.npy",
            transition_actions_array,
        ),
        "second_stage": _save_array(
            output, "e8_grasp_return_actions_float32.npy", second_actions
        ),
        "combined": _save_array(
            output,
            "combined_actions_float32.npy",
            np.concatenate(
                [first_actions, transition_actions_array, second_actions],
                axis=0,
            ),
        ),
    }
    result = {
        "schema_version": "sim2claw.geometric_pawn_sequence.v1",
        "proof_class": "simulation_geometric_sequential_manipulation",
        "physical_authority": False,
        "scene_id": CURRENT_SCENE_ID,
        "piece_layout": CURRENT_TASK_PIECE_LAYOUT,
        "joint_order": list(ROBOT_JOINTS),
        "execution": {
            "action_dtype": "float32",
            "sample_hold_hz": 20,
            "physics_timestep_seconds": float(model.opt.timestep),
            "physics_steps_per_action": PHYSICS_STEPS_PER_ACTION,
            "single_persistent_mujoco_state": True,
        },
        "first_stage": {
            "piece_id": first_piece,
            "source_square": receipt["source_square"],
            "destination_square": receipt["destination_square"],
            "task_kind": "strict_pick_place",
            "strict_success": True,
            "admission_path": str(admission_path),
            "admission_canonical_payload_sha256": admission[
                "canonical_payload_sha256"
            ],
            "measurements": admission["measurements"],
            "exact_persistent_replay_state_match": first_exact_state_match,
            "execution_diagnostics": first_execution,
        },
        "second_stage": {
            "piece_id": SECOND_PIECE,
            "source_square": SECOND_SOURCE_SQUARE,
            "destination_square": SECOND_SOURCE_SQUARE,
            "task_kind": "strict_grasp_lift_return_release",
            "strict_success": scored["success"],
            "measurements": measurements,
            "gates": scored["gates"],
            "wrong_contact_identities": wrong_identities,
            "worst_displaced_other_piece": worst_other,
            "other_piece_displacements_m": displacements,
            "diagnostics": second_diagnostics,
            "independent_replay_diagnostics": second_replay,
        },
        "interstage_reset": {
            "target_joint_pose_radians": reset_pose.astype(float).tolist(),
            "action_count": int(transition_actions_array.shape[0]),
            "execution_diagnostics": transition_execution,
        },
        "arrays": arrays,
        "sequence_success": bool(
            first_exact_state_match
            and not transition_execution["wrong_contact_identities"]
            and transition_execution["clipped_action_rows"] == 0
            and second_diagnostics["clipped_action_rows"] == 0
            and second_replay["clipped_action_rows"] == 0
            and scored["success"]
        ),
    }
    atomic_write_json(output / "sequence_receipt.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-episode", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = run_sequence(args.base_episode, args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["sequence_success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

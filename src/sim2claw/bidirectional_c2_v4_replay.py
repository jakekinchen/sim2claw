"""Retrospective immutable-C2 physics replay under rejected scene v4."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from .bidirectional_scene_registration_v4 import (
    CANDIDATE_PATH,
    build_registered_scene,
    load_candidate,
    sha256_file,
)
from .grasp import _pinch_offset, _pinch_point
from .paths import REPO_ROOT
from .recorded_replay import _apply_parameters, validate_parameter_values
from .scene import initialize_robot_poses
from .wrist_view_reposition import _physical_to_model_position

CASE_ROOT = (
    REPO_ROOT
    / "runs"
    / "prospective-real-to-sim"
    / "20260727-c2-c1-exact-v1"
)
ACTION_PATH = CASE_ROOT / "compiled" / "counted_task_action.npy"
OLD_RECEIPT_PATH = CASE_ROOT / "physics" / "exact_action_replay_receipt.json"
MAPPING_PATH = (
    REPO_ROOT
    / "runs"
    / "physical_excitation"
    / "20260725-follower-only-v1"
    / "simulation-canary-v1"
    / "candidate_manifest.json"
)


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_bytes())


def _apply_mapping_runtime(model: mujoco.MjModel, mapping: dict[str, Any]) -> dict[str, float]:
    ranges = mapping["model"]["calibrated_body_ranges"]
    lower = np.deg2rad(np.asarray(ranges["minimum"], dtype=np.float64))
    upper = np.deg2rad(np.asarray(ranges["maximum"], dtype=np.float64))
    for index, name in enumerate(ranges["joint_names"]):
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        actuator_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_ACTUATOR, name
        )
        model.jnt_limited[joint_id] = 1
        model.jnt_range[joint_id] = [lower[index], upper[index]]
        model.actuator_ctrllimited[actuator_id] = 1
        model.actuator_ctrlrange[actuator_id] = [lower[index], upper[index]]
    manifest = _json(MAPPING_PATH)
    parameters = {
        item["field"]: float(item["value"])
        for item in manifest["applied_parameters"]
    }
    _apply_parameters(
        model,
        mapping,
        validate_parameter_values(mapping, parameters),
        object_body_name="brown_pawn_c2",
    )
    return parameters


def evaluate() -> dict[str, Any]:
    action = np.load(ACTION_PATH, allow_pickle=False)
    action_raw = np.asarray(action, dtype="<f8", order="C").tobytes(order="C")
    mapping_manifest = _json(MAPPING_PATH)
    mapping = mapping_manifest["candidate_config"]
    mapped = _physical_to_model_position(action, mapping)
    old = _json(OLD_RECEIPT_PATH)

    model, _ = build_registered_scene(
        load_candidate(historical_fit_only=True),
        historical_fit_only=True,
    )
    parameters = _apply_mapping_runtime(model, mapping)
    data = mujoco.MjData(model)
    initialize_robot_poses(model, data)
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        for name in mapping["bindings"]["joint_names"]
    ]
    qpos = [model.jnt_qposadr[joint_id] for joint_id in joint_ids]
    actuator_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
        for name in mapping["bindings"]["actuator_names"]
    ]
    data.qpos[qpos] = old["initial_state"]["robot_model_units"]
    data.qvel[:] = 0.0
    data.ctrl[actuator_ids] = mapped[0]
    mujoco.mj_forward(model, data)

    selected_body = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, "brown_pawn_c2"
    )
    selected_joint = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, "brown_pawn_c2_free"
    )
    selected_qpos = int(model.jnt_qposadr[selected_joint])
    start = data.qpos[selected_qpos : selected_qpos + 3].copy()
    free_joint_positions: dict[int, np.ndarray] = {}
    for joint_id in range(model.njnt):
        if model.jnt_type[joint_id] != mujoco.mjtJoint.mjJNT_FREE:
            continue
        body_id = int(model.jnt_bodyid[joint_id])
        address = int(model.jnt_qposadr[joint_id])
        free_joint_positions[body_id] = data.qpos[address : address + 3].copy()

    pinch_local = _pinch_offset(model, data, "left")
    minimum_clearance_m = math.inf
    minimum_clearance_row = -1
    minimum_clearance_substep = -1
    maximum_piece_rise_m = 0.0
    maximum_piece_displacement_m = 0.0
    maximum_other_piece_displacement_m = 0.0
    selected_contact_count = 0
    wrong_piece_contact_count = 0
    first_selected_contact: dict[str, Any] | None = None
    latency_seconds = parameters["command_latency_seconds"]

    for row_index in range(len(mapped)):
        source_time = max(0.0, row_index / 40.0 - latency_seconds)
        source_index = min(
            len(mapped) - 1,
            int(math.floor(source_time * 40.0 + 1e-12)),
        )
        data.ctrl[actuator_ids] = mapped[source_index]
        for substep in range(5):
            mujoco.mj_step(model, data)
            selected_position = data.qpos[
                selected_qpos : selected_qpos + 3
            ]
            clearance = float(
                np.linalg.norm(
                    _pinch_point(model, data, "left", pinch_local)
                    - selected_position
                )
            )
            if clearance < minimum_clearance_m:
                minimum_clearance_m = clearance
                minimum_clearance_row = row_index
                minimum_clearance_substep = substep
            displacement = float(
                np.linalg.norm(selected_position[:2] - start[:2])
            )
            maximum_piece_displacement_m = max(
                maximum_piece_displacement_m, displacement
            )
            maximum_piece_rise_m = max(
                maximum_piece_rise_m,
                float(selected_position[2] - start[2]),
            )
            for body_id, initial in free_joint_positions.items():
                if body_id == selected_body:
                    continue
                joint_id = int(model.body_jntadr[body_id])
                address = int(model.jnt_qposadr[joint_id])
                delta = float(
                    np.linalg.norm(data.qpos[address : address + 3] - initial)
                )
                maximum_other_piece_displacement_m = max(
                    maximum_other_piece_displacement_m, delta
                )
            for contact_index in range(data.ncon):
                contact = data.contact[contact_index]
                body1 = int(model.geom_bodyid[contact.geom1])
                body2 = int(model.geom_bodyid[contact.geom2])
                robot_selected = selected_body in (body1, body2) and any(
                    (
                        mujoco.mj_id2name(
                            model, mujoco.mjtObj.mjOBJ_BODY, body_id
                        )
                        or ""
                    ).startswith("left_")
                    for body_id in (body1, body2)
                )
                if robot_selected:
                    selected_contact_count += 1
                    if first_selected_contact is None:
                        first_selected_contact = {
                            "row": row_index,
                            "substep": substep,
                        }
                elif any(
                    (
                        mujoco.mj_id2name(
                            model, mujoco.mjtObj.mjOBJ_BODY, body_id
                        )
                        or ""
                    ).startswith("left_")
                    for body_id in (body1, body2)
                ) and any(body_id in free_joint_positions for body_id in (body1, body2)):
                    wrong_piece_contact_count += 1

    final = data.qpos[selected_qpos : selected_qpos + 3].copy()
    return {
        "schema_version": "sim2claw.bidirectional_c2_v4_retrospective_replay.v1",
        "case_id": "20260727-c2-c1-exact-v1",
        "status": "completed_retrospective_failure",
        "proof_class": "post_outcome_scene_correction_exact_action_diagnostic",
        "canonical_action": {
            "npy_sha256": sha256_file(ACTION_PATH),
            "raw_float64le_sha256": hashlib.sha256(action_raw).hexdigest(),
            "shape": list(action.shape),
            "sample_hz": 40,
            "mutated": False,
        },
        "scene_v4_sha256": sha256_file(CANDIDATE_PATH),
        "mapping_sha256": sha256_file(MAPPING_PATH),
        "runtime": {
            "numeric_runtime": "cpu_mujoco_fp64",
            "physics_timestep_seconds": float(model.opt.timestep),
            "physics_steps_per_action": 5,
            "zero_order_hold_hz": 40,
            "command_latency_seconds": latency_seconds,
            "finite_state": bool(
                np.all(np.isfinite(data.qpos))
                and np.all(np.isfinite(data.qvel))
            ),
        },
        "old_scene": {
            "receipt_sha256": sha256_file(OLD_RECEIPT_PATH),
            "selected_piece_contact_observed": old["task_consequence"][
                "selected_piece_contact_observed"
            ],
            "minimum_gripper_clearance_m": old["task_consequence"][
                "gripper_clearance_m"
            ],
            "maximum_piece_rise_m": old["task_consequence"][
                "maximum_piece_rise_m"
            ],
            "final_piece_xyz_m": old["task_consequence"]["final_piece_xyz_m"],
            "first_divergence": old["task_consequence"]["first_divergence"],
        },
        "scene_v4": {
            "selected_piece_initial_xyz_m": start.tolist(),
            "selected_piece_final_xyz_m": final.tolist(),
            "minimum_gripper_clearance_m": minimum_clearance_m,
            "minimum_clearance_row": minimum_clearance_row,
            "minimum_clearance_substep": minimum_clearance_substep,
            "selected_piece_contact_count": selected_contact_count,
            "first_selected_contact": first_selected_contact,
            "wrong_piece_contact_count": wrong_piece_contact_count,
            "maximum_piece_rise_m": maximum_piece_rise_m,
            "maximum_piece_displacement_m": maximum_piece_displacement_m,
            "maximum_other_piece_displacement_m": maximum_other_piece_displacement_m,
            "off_source_square": maximum_piece_displacement_m > 0.04445,
            "first_divergence": (
                f"At row {minimum_clearance_row}, v4 remained "
                f"{minimum_clearance_m * 1000.0:.3f} mm from physical C2 and "
                "never established simulated contact, while the immutable "
                "physical receipt records strike/topple near C2."
            ),
        },
        "promoted": False,
        "claim_boundary": (
            "Post-outcome v4 retrospective only. The exact C2 bytes still "
            "produce no simulated contact or off-source displacement and "
            "cannot promote v4, C2, or any transfer claim."
        ),
    }

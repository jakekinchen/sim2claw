"""Deterministic CPU/fp64 V05 straight closed-jaw push rehearsal."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from .bidirectional_registration_v2_fit import project
from .grasp import _pinch_offset, _pinch_point, _solve_reach
from .paths import REPO_ROOT
from .physical_canary import _physical_to_model_position
from .recorded_replay import _compile_model
from .scene import board_square_center


class PushRehearsalError(RuntimeError):
    """The prospective rehearsal contract or deterministic simulation failed."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(entry: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
    path = REPO_ROOT / str(entry["path"])
    if not path.is_file() or _sha(path) != entry["sha256"]:
        raise PushRehearsalError(f"bound rehearsal input changed: {path}")
    return path, json.loads(path.read_text(encoding="utf-8"))


def _quat_multiply(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    w1, x1, y1, z1 = first
    w2, x2, y2, z2 = second
    return np.asarray(
        [
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        ],
        dtype=np.float64,
    )


def _registered_model(
    wrapper: Mapping[str, Any],
    rigid: Mapping[str, Any],
    timestep: float,
    *,
    piece_square_transform: str = "identity",
) -> tuple[mujoco.MjModel, list[int], list[int], set[int]]:
    model, _ = _compile_model(
        wrapper["candidate_config"],
        base_directory=None,
        current_scene_piece_square_transform=piece_square_transform,
    )
    base_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, "left_base"
    )
    yaw = float(rigid["robot_board_yaw_radians"])
    cosine, sine = math.cos(yaw), math.sin(yaw)
    rotation = np.asarray(
        [[cosine, -sine, 0], [sine, cosine, 0], [0, 0, 1.0]]
    )
    translation = np.asarray(
        rigid["robot_board_translation_xyz_m"], dtype=np.float64
    )
    model.body_pos[base_id] = rotation @ model.body_pos[base_id] + translation
    model.body_quat[base_id] = _quat_multiply(
        np.asarray([math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)]),
        model.body_quat[base_id].copy(),
    )
    model.opt.timestep = timestep
    data = mujoco.MjData(model)
    mujoco.mj_setConst(model, data)
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        for name in wrapper["candidate_config"]["bindings"]["joint_names"]
    ]
    actuator_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
        for name in wrapper["candidate_config"]["bindings"]["actuator_names"]
    ]
    if min(joint_ids + actuator_ids) < 0:
        raise PushRehearsalError("registered robot binding is incomplete")
    qpos = [int(model.jnt_qposadr[item]) for item in joint_ids]
    jaw_bodies = {
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)
        for name in ("left_gripper", "left_moving_jaw_so101_v1")
    }
    return model, qpos, actuator_ids, jaw_bodies


def _body_name(model: mujoco.MjModel, body_id: int) -> str:
    return (
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id)
        or f"body-{body_id}"
    )


def _contact_pairs(
    model: mujoco.MjModel, data: mujoco.MjData, jaw_bodies: set[int]
) -> set[tuple[str, str]]:
    pairs = set()
    for index in range(data.ncon):
        contact = data.contact[index]
        bodies = (
            int(model.geom_bodyid[int(contact.geom1)]),
            int(model.geom_bodyid[int(contact.geom2)]),
        )
        if set(bodies) & jaw_bodies:
            pairs.add(tuple(sorted(_body_name(model, body) for body in bodies)))
    return pairs


def _compile_action(
    *,
    model: mujoco.MjModel,
    qpos_addresses: list[int],
    seed_model: np.ndarray,
    start_xyz: np.ndarray,
    direction: np.ndarray,
    stroke_m: float,
    sample_hz: float,
    speed_m_s: float,
    closed_jaw_rad: float,
    maximum_ik_residual_m: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    data = mujoco.MjData(model)
    data.qpos[qpos_addresses] = seed_model
    data.qpos[qpos_addresses[-1]] = closed_jaw_rad
    mujoco.mj_forward(model, data)
    pinch_local = _pinch_offset(model, data, "left")
    waypoints = np.linspace(0.0, stroke_m, int(round(stroke_m / 0.01)) + 1)
    solved = []
    residuals = []
    seed = seed_model.copy()
    for progress in waypoints:
        data.qpos[qpos_addresses] = seed
        data.qpos[qpos_addresses[-1]] = closed_jaw_rad
        data.qvel[:] = 0
        mujoco.mj_forward(model, data)
        pose, residual = _solve_reach(
            model,
            data,
            "left",
            start_xyz + direction * progress,
            pinch_local,
            iterations=240,
            damping=0.015,
            step_limit=0.10,
        )
        residuals.append(float(residual))
        if residual > maximum_ik_residual_m:
            raise PushRehearsalError("rehearsal IK residual exceeded gate")
        seed = np.asarray(
            [
                pose["shoulder_pan"],
                pose["shoulder_lift"],
                pose["elbow_flex"],
                pose["wrist_flex"],
                pose["wrist_roll"],
                closed_jaw_rad,
            ]
        )
        solved.append(seed.copy())
    rows = [solved[0]]
    samples_per_segment = max(
        1, int(round((0.01 / speed_m_s) * sample_hz))
    )
    for first, second in zip(solved[:-1], solved[1:], strict=True):
        for index in range(1, samples_per_segment + 1):
            blend = index / samples_per_segment
            rows.append(first + blend * (second - first))
    action = np.asarray(rows, dtype="<f8", order="C")
    margins = []
    for joint_index, joint_id in enumerate(
        [
            mujoco.mj_name2id(
                model,
                mujoco.mjtObj.mjOBJ_JOINT,
                name,
            )
            for name in (
                "left_shoulder_pan",
                "left_shoulder_lift",
                "left_elbow_flex",
                "left_wrist_flex",
                "left_wrist_roll",
                "left_gripper",
            )
        ]
    ):
        low, high = model.jnt_range[joint_id]
        margins.append(
            float(
                min(
                    np.min(action[:, joint_index] - low),
                    np.min(high - action[:, joint_index]),
                )
            )
        )
    return action, {
        "maximum_ik_residual_m": max(residuals),
        "minimum_joint_limit_margin_rad": min(margins),
        "action_rows": len(action),
        "action_raw_float64le_sha256": hashlib.sha256(
            action.tobytes(order="C")
        ).hexdigest(),
    }


def _replay(
    *,
    model: mujoco.MjModel,
    qpos_addresses: list[int],
    actuator_ids: list[int],
    jaw_bodies: set[int],
    action: np.ndarray,
    selected_name: str,
    source_delta_m: np.ndarray,
    direction: np.ndarray,
    substeps: int,
    camera: np.ndarray,
    image_size: tuple[int, int],
) -> dict[str, Any]:
    data = mujoco.MjData(model)
    selected_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, selected_name
    )
    if selected_id < 0:
        raise PushRehearsalError(f"selected pawn missing: {selected_name}")
    selected_joint = int(model.body_jntadr[selected_id])
    selected_qpos = int(model.jnt_qposadr[selected_joint])
    data.qpos[selected_qpos : selected_qpos + 2] += source_delta_m
    data.qpos[qpos_addresses] = action[0]
    data.ctrl[actuator_ids] = action[0]
    mujoco.mj_forward(model, data)
    initial_selected = data.xpos[selected_id].copy()
    pawn_ids = {
        body_id
        for body_id in range(model.nbody)
        if "pawn" in _body_name(model, body_id)
    }
    excluded_ids = pawn_ids - {selected_id}
    initial_excluded = {
        body_id: data.xpos[body_id].copy() for body_id in excluded_ids
    }
    baseline_pairs = _contact_pairs(model, data, jaw_bodies)
    selected_contact_steps = 0
    excluded_contact_steps = 0
    new_collision_pairs: set[tuple[str, str]] = set()
    for row in action:
        data.ctrl[actuator_ids] = row
        for _ in range(substeps):
            mujoco.mj_step(model, data)
            for contact_index in range(data.ncon):
                contact = data.contact[contact_index]
                bodies = {
                    int(model.geom_bodyid[int(contact.geom1)]),
                    int(model.geom_bodyid[int(contact.geom2)]),
                }
                if bodies & jaw_bodies and selected_id in bodies:
                    selected_contact_steps += 1
                if bodies & jaw_bodies and bodies & excluded_ids:
                    excluded_contact_steps += 1
            new_collision_pairs |= (
                _contact_pairs(model, data, jaw_bodies) - baseline_pairs
            )
    mujoco.mj_forward(model, data)
    final_selected = data.xpos[selected_id].copy()
    progress_m = float(
        np.dot((final_selected - initial_selected)[:2], direction[:2])
    )
    maximum_excluded_m = max(
        float(np.linalg.norm(data.xpos[body][:2] - initial[:2]))
        for body, initial in initial_excluded.items()
    )
    allowed_selected_pair = {
        tuple(sorted((_body_name(model, jaw, ), selected_name)))
        for jaw in jaw_bodies
    }
    collision_pairs = sorted(new_collision_pairs - allowed_selected_pair)
    projected = project(
        camera, np.asarray([initial_selected, final_selected])
    )
    width, height = image_size
    camera_margin = float(
        np.min(
            np.column_stack(
                (
                    projected[:, 0],
                    width - projected[:, 0],
                    projected[:, 1],
                    height - projected[:, 1],
                )
            )
        )
    )
    return {
        "selected_initial_xyz_m": initial_selected.tolist(),
        "selected_final_xyz_m": final_selected.tolist(),
        "signed_progress_mm": progress_m * 1000.0,
        "selected_contact_steps": selected_contact_steps,
        "excluded_contact_steps": excluded_contact_steps,
        "maximum_excluded_displacement_mm": maximum_excluded_m * 1000.0,
        "new_nonselected_jaw_collision_pairs": [
            list(row) for row in collision_pairs
        ],
        "camera_margin_px": camera_margin,
    }


def evaluate(contract_path: Path, output_path: Path) -> dict[str, Any]:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    _, wrapper = _bound(contract["candidate_manifest"])
    _, rigid = _bound(contract["registration_candidate"])
    model, qpos, actuators, jaw_bodies = _registered_model(
        wrapper, rigid, float(contract["simulation"]["timestep_s"])
    )
    seed_physical = np.asarray([contract["action_synthesis"]["seed_physical"]])
    seed_model = _physical_to_model_position(
        seed_physical, wrapper["candidate_config"]
    )[0]
    camera = np.asarray(rigid["camera_matrix_3x4"], dtype=np.float64)
    image_size = tuple(contract["camera_gate"]["image_size_px"])
    variants = contract["robustness_variants"]
    grid_results = []
    for case in contract["cases"]:
        source = np.asarray(board_square_center(case["source_square"]))
        destination = np.asarray(
            board_square_center(case["destination_direction_square"])
        )
        direction = destination - source
        direction /= np.linalg.norm(direction)
        selected_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_BODY, case["selected_piece_id"]
        )
        initial_body = mujoco.MjData(model)
        mujoco.mj_forward(model, initial_body)
        source_xyz = initial_body.xpos[selected_id].copy()
        for contact_height in contract["grid"]["contact_heights_m"]:
            for stroke in contract["grid"]["stroke_lengths_m"]:
                start = source_xyz.copy()
                start[:2] -= (
                    direction[:2]
                    * contract["action_synthesis"]["contact_center_offset_m"]
                )
                start[2] += contact_height
                try:
                    action, compile_metrics = _compile_action(
                        model=model,
                        qpos_addresses=qpos,
                        seed_model=seed_model,
                        start_xyz=start,
                        direction=direction,
                        stroke_m=float(stroke),
                        sample_hz=float(
                            contract["action_synthesis"]["sample_hz"]
                        ),
                        speed_m_s=float(
                            contract["action_synthesis"]["cartesian_speed_m_s"]
                        ),
                        closed_jaw_rad=float(
                            contract["action_synthesis"]["closed_jaw_rad"]
                        ),
                        maximum_ik_residual_m=float(
                            contract["gates"]["maximum_ik_residual_m"]
                        ),
                    )
                except PushRehearsalError as error:
                    grid_results.append(
                        {
                            "case_id": case["case_id"],
                            "contact_height_m": contact_height,
                            "stroke_m": stroke,
                            "status": "compile_reject",
                            "error": str(error),
                            "passed": False,
                        }
                    )
                    continue
                replays = []
                for variant in variants:
                    longitudinal, lateral = variant["delta_m"]
                    delta = (
                        direction[:2] * longitudinal
                        + np.asarray([-direction[1], direction[0]]) * lateral
                    )
                    replay = _replay(
                        model=model,
                        qpos_addresses=qpos,
                        actuator_ids=actuators,
                        jaw_bodies=jaw_bodies,
                        action=action,
                        selected_name=case["selected_piece_id"],
                        source_delta_m=delta,
                        direction=direction,
                        substeps=int(contract["simulation"]["substeps_per_row"]),
                        camera=camera,
                        image_size=image_size,
                    )
                    checks = {
                        "fully_off_source": replay["signed_progress_mm"]
                        >= contract["gates"]["minimum_signed_progress_mm"],
                        "selected_contact": replay["selected_contact_steps"] > 0,
                        "excluded_contact": replay["excluded_contact_steps"] == 0,
                        "excluded_displacement": replay[
                            "maximum_excluded_displacement_mm"
                        ]
                        <= contract["gates"][
                            "maximum_excluded_displacement_mm"
                        ],
                        "collision": not replay[
                            "new_nonselected_jaw_collision_pairs"
                        ],
                        "camera_margin": replay["camera_margin_px"]
                        >= contract["camera_gate"]["minimum_margin_px"],
                    }
                    replays.append(
                        {
                            "variant_id": variant["variant_id"],
                            **replay,
                            "checks": checks,
                            "passed": all(checks.values()),
                        }
                    )
                static_checks = {
                    "ik": compile_metrics["maximum_ik_residual_m"]
                    <= contract["gates"]["maximum_ik_residual_m"],
                    "joint_margin": compile_metrics[
                        "minimum_joint_limit_margin_rad"
                    ]
                    >= contract["gates"]["minimum_joint_limit_margin_rad"],
                    "action_identity": len(
                        {
                            compile_metrics["action_raw_float64le_sha256"]
                            for _ in replays
                        }
                    )
                    == 1,
                }
                passed = all(static_checks.values()) and all(
                    row["passed"] for row in replays
                )
                grid_results.append(
                    {
                        "case_id": case["case_id"],
                        "contact_height_m": contact_height,
                        "stroke_m": stroke,
                        "status": "pass" if passed else "sim_reject",
                        "compile": compile_metrics,
                        "static_checks": static_checks,
                        "robustness": replays,
                        "passed": passed,
                    }
                )
    passing = [row for row in grid_results if row["passed"]]
    per_case = {}
    for case in contract["cases"]:
        rows = [row for row in passing if row["case_id"] == case["case_id"]]
        per_case[case["case_id"]] = {
            "feasible": bool(rows),
            "passing_grid_count": len(rows),
            "recommended": (
                min(
                    rows,
                    key=lambda row: (
                        row["stroke_m"],
                        abs(row["contact_height_m"] - 0.024),
                    ),
                )
                if rows
                else None
            ),
        }
    receipt = {
        "schema_version": "sim2claw.bidirectional_pawn_push_v2_sim_rehearsal_receipt.v1",
        "status": (
            "sim_rehearsal_pass"
            if sum(row["feasible"] for row in per_case.values()) >= 4
            else "sim_rehearsal_reject"
        ),
        "proof_class": "cpu_fp64_sim_only_straight_closed_jaw_push_rehearsal",
        "contract_path": str(contract_path.relative_to(REPO_ROOT)),
        "contract_sha256": _sha(contract_path),
        "registration_candidate_sha256": contract[
            "registration_candidate"
        ]["sha256"],
        "candidate_refit": False,
        "task_outcomes_used_for_design": False,
        "grid_results": grid_results,
        "per_case": per_case,
        "passing_case_ids": [
            case_id for case_id, row in per_case.items() if row["feasible"]
        ],
        "physical_motion": False,
        "physical_task_attempts": 0,
        "authority": contract["authority"],
        "claim_boundary": "Simulation-only rehearsal used to draft V06 case/evaluator freeze; no physical task, transfer, promotion, or success claim.",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt

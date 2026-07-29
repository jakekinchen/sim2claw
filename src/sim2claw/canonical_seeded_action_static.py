"""Canonical current-anchor-seeded static pawn-push action compiler."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from .bidirectional_registration_v2_fit import project
from .current_workcell import (
    build_current_workcell_spec,
    current_square_center,
)
from .grasp import _pinch_offset, _pinch_point
from .paths import REPO_ROOT
from .physical_canary import _physical_to_model_position


class CanonicalSeededActionStaticError(RuntimeError):
    """A frozen compiler input or static action invariant changed."""


ARM_JOINTS = (
    "left_shoulder_pan",
    "left_shoulder_lift",
    "left_elbow_flex",
    "left_wrist_flex",
    "left_wrist_roll",
)
ALL_JOINTS = (*ARM_JOINTS, "left_gripper")
JAW_BODIES = ("left_gripper", "left_moving_jaw_so101_v1")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(entry: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(entry["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise CanonicalSeededActionStaticError(
            "canonical compiler input escapes repository"
        ) from error
    if not path.is_file() or _sha(path) != entry["sha256"]:
        raise CanonicalSeededActionStaticError(
            f"bound canonical compiler input changed: {path}"
        )
    return path


def _json(entry: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(_bound(entry).read_text(encoding="utf-8"))


def _named_id(
    model: mujoco.MjModel,
    object_type: mujoco.mjtObj,
    name: str,
) -> int:
    result = mujoco.mj_name2id(model, object_type, name)
    if result < 0:
        raise CanonicalSeededActionStaticError(
            f"canonical model object is missing: {name}"
        )
    return int(result)


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


def _registered_current_model(
    rigid: Mapping[str, Any],
    timestep_s: float,
) -> tuple[mujoco.MjModel, list[int], set[int], set[int]]:
    model = build_current_workcell_spec().compile()
    base_id = _named_id(
        model, mujoco.mjtObj.mjOBJ_BODY, "left_base"
    )
    yaw = float(rigid["robot_board_yaw_radians"])
    cosine, sine = math.cos(yaw), math.sin(yaw)
    rotation = np.asarray(
        [[cosine, -sine, 0.0], [sine, cosine, 0.0], [0.0, 0.0, 1.0]]
    )
    translation = np.asarray(
        rigid["robot_board_translation_xyz_m"], dtype=np.float64
    )
    model.body_pos[base_id] = rotation @ model.body_pos[base_id] + translation
    model.body_quat[base_id] = _quat_multiply(
        np.asarray([math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0)]),
        model.body_quat[base_id].copy(),
    )
    model.opt.timestep = timestep_s
    mujoco.mj_setConst(model, mujoco.MjData(model))
    addresses = [
        int(
            model.jnt_qposadr[
                _named_id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            ]
        )
        for name in ALL_JOINTS
    ]
    robot_bodies = _descendants(model, "left_base")
    jaw_bodies = {
        _named_id(model, mujoco.mjtObj.mjOBJ_BODY, name)
        for name in JAW_BODIES
    }
    return model, addresses, robot_bodies, jaw_bodies


def _descendants(model: mujoco.MjModel, root_name: str) -> set[int]:
    root = _named_id(model, mujoco.mjtObj.mjOBJ_BODY, root_name)
    result = {root}
    changed = True
    while changed:
        changed = False
        for body_id in range(model.nbody):
            if body_id not in result and int(model.body_parentid[body_id]) in result:
                result.add(body_id)
                changed = True
    return result


def _body_name(model: mujoco.MjModel, body_id: int) -> str:
    return (
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id)
        or f"body-{body_id}"
    )


def _contact_pairs(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    robot_bodies: set[int],
) -> set[tuple[str, str]]:
    result: set[tuple[str, str]] = set()
    for index in range(data.ncon):
        contact = data.contact[index]
        bodies = (
            int(model.geom_bodyid[int(contact.geom1)]),
            int(model.geom_bodyid[int(contact.geom2)]),
        )
        if set(bodies) & robot_bodies:
            result.add(tuple(sorted(_body_name(model, item) for item in bodies)))
    return result


def _solve_fixed_roll(
    model: mujoco.MjModel,
    seed: np.ndarray,
    target: np.ndarray,
    pinch_local: np.ndarray,
    *,
    iterations: int,
    damping: float,
    step_limit: float,
) -> tuple[np.ndarray, float]:
    scratch = mujoco.MjData(model)
    addresses = [
        int(
            model.jnt_qposadr[
                _named_id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            ]
        )
        for name in ALL_JOINTS
    ]
    scratch.qpos[addresses] = seed
    columns = [
        int(
            model.jnt_dofadr[
                _named_id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            ]
        )
        for name in ARM_JOINTS[:4]
    ]
    joint_ids = [
        _named_id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        for name in ARM_JOINTS[:4]
    ]
    tip_geom = _named_id(
        model, mujoco.mjtObj.mjOBJ_GEOM, "left_fixed_jaw_sph_tip2"
    )
    tip_body = int(model.geom_bodyid[tip_geom])
    jacobian_full = np.zeros((3, model.nv), dtype=np.float64)
    identity = np.eye(3, dtype=np.float64)
    residual = float("inf")
    for _ in range(iterations):
        mujoco.mj_forward(model, scratch)
        tip = _pinch_point(model, scratch, "left", pinch_local)
        error = target - tip
        residual = float(np.linalg.norm(error))
        if residual < 0.0015:
            break
        mujoco.mj_jac(
            model, scratch, jacobian_full, None, tip, tip_body
        )
        jacobian = jacobian_full[:, columns]
        gain = jacobian @ jacobian.T + (damping**2) * identity
        update = jacobian.T @ np.linalg.solve(gain, error)
        update = np.clip(update, -step_limit, step_limit)
        for joint_id, delta in zip(joint_ids, update, strict=True):
            address = int(model.jnt_qposadr[joint_id])
            low, high = model.jnt_range[joint_id]
            scratch.qpos[address] = float(
                np.clip(scratch.qpos[address] + delta, low, high)
            )
    return np.asarray(scratch.qpos[addresses], dtype=np.float64), residual


def _physical_actions(
    model_actions: np.ndarray,
    candidate_config: Mapping[str, Any],
) -> np.ndarray:
    transforms = candidate_config["physical_adapter"]["joint_transform"][
        "joints"
    ]
    physical = np.empty(model_actions.shape, dtype="<f8")
    for index, transform in enumerate(transforms):
        physical[:, index] = (
            model_actions[:, index] - float(transform["zero_offset"])
        ) / (float(transform["sign"]) * float(transform["scale"]))
    return physical


def _interpolate_targets(
    targets: list[np.ndarray],
    candidate_config: Mapping[str, Any],
    *,
    sample_hz: float,
    target_rates: np.ndarray,
) -> np.ndarray:
    rows = [targets[0].copy()]
    for first, second in zip(targets[:-1], targets[1:], strict=True):
        physical = _physical_actions(
            np.asarray([first, second]), candidate_config
        )
        duration = float(
            np.max(np.abs(physical[1] - physical[0]) / target_rates)
        )
        samples = max(1, int(math.ceil(duration * sample_hz)))
        for index in range(1, samples + 1):
            blend = index / samples
            rows.append(first + blend * (second - first))
    return np.asarray(rows, dtype="<f8", order="C")


def _compile(
    model: mujoco.MjModel,
    addresses: list[int],
    seed_model: np.ndarray,
    candidate_config: Mapping[str, Any],
    *,
    source_xyz: np.ndarray,
    direction: np.ndarray,
    contact_offset_m: float,
    contact_height_m: float,
    clearance_height_m: float,
    stroke_m: float,
    closed_jaw_rad: float,
    sample_hz: float,
    target_rates: np.ndarray,
    maximum_ik_residual_m: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    closed_seed = seed_model.copy()
    closed_seed[-1] = closed_jaw_rad
    data = mujoco.MjData(model)
    data.qpos[addresses] = closed_seed
    mujoco.mj_forward(model, data)
    pinch_local = _pinch_offset(model, data, "left")
    current_pinch = _pinch_point(model, data, "left", pinch_local)
    contact = source_xyz.copy()
    contact[:2] -= direction[:2] * contact_offset_m
    contact[2] += contact_height_m
    current_lift = current_pinch.copy()
    current_lift[2] = max(
        current_pinch[2] + 0.03,
        source_xyz[2] + clearance_height_m,
    )
    clearance = contact.copy()
    clearance[2] = source_xyz[2] + clearance_height_m
    pushed = contact + direction * stroke_m
    retreat = pushed.copy()
    retreat[2] = clearance[2]
    cartesian_targets = [current_lift, clearance, contact, pushed, retreat]
    targets = [seed_model.copy(), closed_seed.copy()]
    residuals: list[float] = []
    active = closed_seed.copy()
    for target in cartesian_targets:
        active, residual = _solve_fixed_roll(
            model,
            active,
            target,
            pinch_local,
            iterations=260,
            damping=0.015,
            step_limit=0.08,
        )
        residuals.append(float(residual))
        if residual > maximum_ik_residual_m:
            raise CanonicalSeededActionStaticError(
                "canonical fixed-roll IK residual exceeded gate"
            )
        active[-1] = closed_jaw_rad
        targets.append(active.copy())
    action = _interpolate_targets(
        targets,
        candidate_config,
        sample_hz=sample_hz,
        target_rates=target_rates,
    )
    if not np.array_equal(action[0], seed_model):
        raise CanonicalSeededActionStaticError(
            "canonical action row zero changed from live seed"
        )
    margins = []
    for index, name in enumerate(ALL_JOINTS):
        joint_id = _named_id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        low, high = model.jnt_range[joint_id]
        margins.append(
            float(
                min(
                    np.min(action[:, index] - low),
                    np.min(high - action[:, index]),
                )
            )
        )
    return action, {
        "maximum_ik_residual_m": max(residuals),
        "minimum_model_joint_margin_rad": min(margins),
        "cartesian_targets_xyz_m": [
            item.tolist() for item in cartesian_targets
        ],
        "action_rows": len(action),
        "action_raw_float64le_sha256": hashlib.sha256(
            action.tobytes(order="C")
        ).hexdigest(),
    }


def _families(model: mujoco.MjModel) -> list[dict[str, str]]:
    occupied: dict[str, str] = {}
    for body_id in range(model.nbody):
        name = _body_name(model, body_id)
        if "_pawn_" in name:
            occupied[name.rsplit("_", 1)[-1]] = name
    result = []
    for source, piece_id in sorted(occupied.items()):
        file_index = ord(source[0]) - ord("a")
        rank_index = int(source[1]) - 1
        for file_delta, rank_delta in ((0, 1), (1, 0), (0, -1), (-1, 0)):
            target_file = file_index + file_delta
            target_rank = rank_index + rank_delta
            if not (0 <= target_file < 8 and 0 <= target_rank < 8):
                continue
            destination = f"{chr(ord('a') + target_file)}{target_rank + 1}"
            if destination in occupied:
                continue
            result.append(
                {
                    "case_id": f"{piece_id}__{source}_{destination}",
                    "selected_piece_id": piece_id,
                    "source_square": source,
                    "destination_square": destination,
                }
            )
    return result


def _static_audit(
    model: mujoco.MjModel,
    addresses: list[int],
    seed_model: np.ndarray,
    action: np.ndarray,
    selected_piece_id: str,
    robot_bodies: set[int],
    jaw_bodies: set[int],
) -> dict[str, Any]:
    data = mujoco.MjData(model)
    data.qpos[addresses] = seed_model
    mujoco.mj_forward(model, data)
    baseline = _contact_pairs(model, data, robot_bodies)
    allowed = {
        tuple(sorted((_body_name(model, jaw), selected_piece_id)))
        for jaw in jaw_bodies
    }
    selected_contact = False
    rejected: set[tuple[str, str]] = set()
    for row in action:
        data.qpos[addresses] = row
        data.qvel[:] = 0.0
        mujoco.mj_forward(model, data)
        current = _contact_pairs(model, data, robot_bodies)
        selected_contact = selected_contact or bool(current & allowed)
        rejected |= current - baseline - allowed
    return {
        "baseline_robot_contact_pairs": [
            list(item) for item in sorted(baseline)
        ],
        "selected_contact_observed": selected_contact,
        "new_disallowed_robot_contact_pairs": [
            list(item) for item in sorted(rejected)
        ],
        "passed": selected_contact and not rejected,
    }


def _gateway_audit(
    action: np.ndarray,
    candidate_config: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    physical = _physical_actions(action, candidate_config)
    lower = np.asarray(
        contract["live_seed"]["follower_calibrated_minimum"],
        dtype=np.float64,
    )
    upper = np.asarray(
        contract["live_seed"]["follower_calibrated_maximum"],
        dtype=np.float64,
    )
    rates = np.max(
        np.abs(np.diff(physical, axis=0))
        * float(contract["action"]["sample_hz"]),
        axis=0,
    )
    limits = np.asarray(
        contract["gates"]["gateway_rate_limits_per_joint"],
        dtype=np.float64,
    )
    return {
        "row_zero_physical": physical[0].tolist(),
        "all_rows_inside_calibrated_limits": bool(
            np.all(physical >= lower) and np.all(physical <= upper)
        ),
        "maximum_absolute_rate_per_second": rates.tolist(),
        "all_rates_within_gateway_limits": bool(np.all(rates <= limits)),
        "physical_action_raw_float64le_sha256": hashlib.sha256(
            physical.tobytes(order="C")
        ).hexdigest(),
        "mapping_review_status": candidate_config["physical_adapter"][
            "joint_transform"
        ]["review_status"],
        "mapping_calibration_approved": bool(
            candidate_config["physical_adapter"]["joint_transform"].get(
                "calibration_approved"
            )
        ),
    }


def enumerate_and_freeze(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Enumerate the frozen static grid and write immutable selected actions."""

    if output_directory.exists():
        raise CanonicalSeededActionStaticError(
            "immutable output directory already exists"
        )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if (
        contract.get("schema_version")
        != "sim2claw.canonical_seeded_action_static.v1"
    ):
        raise CanonicalSeededActionStaticError(
            "unexpected canonical seeded static contract"
        )
    _bound(contract["inputs"]["hard_cutover"])
    registration = _json(contract["inputs"]["registration_receipt"])
    closeout = _json(contract["inputs"]["readiness_closeout"])
    manifest = _json(contract["inputs"]["candidate_manifest"])
    rigid = _json(contract["inputs"]["registration_candidate"])
    _bound(contract["inputs"]["current_workcell_implementation"])
    _bound(contract["inputs"]["compiler_implementation"])
    if (
        not registration["passed"]
        or closeout["authority"]["fresh_canonical_compiler"] is not True
        or closeout["authority"]["physical_motion"] is not False
    ):
        raise CanonicalSeededActionStaticError(
            "canonical compiler authority changed"
        )

    model, addresses, robot_bodies, jaw_bodies = _registered_current_model(
        rigid, float(contract["simulation"]["timestep_s"])
    )
    candidate_config = manifest["candidate_config"]
    seed_physical = np.asarray(
        [contract["live_seed"]["follower_position_degrees"]],
        dtype=np.float64,
    )
    seed_model = _physical_to_model_position(
        seed_physical, candidate_config
    )[0]
    data = mujoco.MjData(model)
    data.qpos[addresses] = seed_model
    mujoco.mj_forward(model, data)
    camera = np.asarray(rigid["camera_matrix_3x4"], dtype=np.float64)
    image_width, image_height = contract["camera_gate"]["image_size_px"]
    minimum_camera_margin = float(
        contract["camera_gate"]["minimum_margin_px"]
    )
    target_rates = np.asarray(
        contract["action"]["target_rates_per_joint"], dtype=np.float64
    )
    rows: list[tuple[dict[str, Any], np.ndarray]] = []
    rejects = {"ik": 0, "collision": 0, "gateway": 0, "camera": 0}
    families = _families(model)

    for family_index, family in enumerate(families):
        selected_id = _named_id(
            model,
            mujoco.mjtObj.mjOBJ_BODY,
            family["selected_piece_id"],
        )
        source_xyz = data.xpos[selected_id].copy()
        source_center = np.asarray(
            current_square_center(family["source_square"]),
            dtype=np.float64,
        )
        destination_center = np.asarray(
            current_square_center(family["destination_square"]),
            dtype=np.float64,
        )
        direction = destination_center - source_center
        direction /= np.linalg.norm(direction)
        for offset_index, offset in enumerate(
            contract["grid"]["contact_offsets_m"]
        ):
            for height_index, height in enumerate(
                contract["grid"]["contact_heights_m"]
            ):
                for stroke_index, stroke in enumerate(
                    contract["grid"]["stroke_lengths_m"]
                ):
                    base = {
                        **family,
                        "family_index": family_index,
                        "contact_offset_index": offset_index,
                        "contact_offset_m": offset,
                        "contact_height_index": height_index,
                        "contact_height_m": height,
                        "stroke_index": stroke_index,
                        "stroke_m": stroke,
                    }
                    try:
                        action, compile_metrics = _compile(
                            model,
                            addresses,
                            seed_model,
                            candidate_config,
                            source_xyz=source_xyz,
                            direction=direction,
                            contact_offset_m=float(offset),
                            contact_height_m=float(height),
                            clearance_height_m=float(
                                contract["action"]["clearance_height_m"]
                            ),
                            stroke_m=float(stroke),
                            closed_jaw_rad=float(
                                contract["action"]["closed_jaw_rad"]
                            ),
                            sample_hz=float(contract["action"]["sample_hz"]),
                            target_rates=target_rates,
                            maximum_ik_residual_m=float(
                                contract["gates"]["maximum_ik_residual_m"]
                            ),
                        )
                    except CanonicalSeededActionStaticError:
                        rejects["ik"] += 1
                        continue
                    static = _static_audit(
                        model,
                        addresses,
                        seed_model,
                        action,
                        family["selected_piece_id"],
                        robot_bodies,
                        jaw_bodies,
                    )
                    gateway = _gateway_audit(
                        action, candidate_config, contract
                    )
                    terminal = source_xyz + direction * float(stroke)
                    pixels = project(
                        camera, np.asarray([source_xyz, terminal])
                    )
                    margin = float(
                        np.min(
                            np.column_stack(
                                (
                                    pixels[:, 0],
                                    image_width - pixels[:, 0],
                                    pixels[:, 1],
                                    image_height - pixels[:, 1],
                                )
                            )
                        )
                    )
                    camera_passed = margin >= minimum_camera_margin
                    if not static["passed"]:
                        rejects["collision"] += 1
                    elif not (
                        gateway["all_rows_inside_calibrated_limits"]
                        and gateway["all_rates_within_gateway_limits"]
                    ):
                        rejects["gateway"] += 1
                    elif not camera_passed:
                        rejects["camera"] += 1
                    else:
                        row = {
                            **base,
                            "compile": compile_metrics,
                            "static": static,
                            "gateway": gateway,
                            "camera": {
                                "source_and_terminal_pixels": pixels.tolist(),
                                "minimum_margin_px": margin,
                                "passed": camera_passed,
                            },
                        }
                        rows.append((row, action))

    rows.sort(
        key=lambda item: (
            -item[0]["compile"]["minimum_model_joint_margin_rad"],
            -item[0]["camera"]["minimum_margin_px"],
            item[0]["compile"]["maximum_ik_residual_m"],
            item[0]["family_index"],
            item[0]["contact_offset_index"],
            item[0]["contact_height_index"],
            item[0]["stroke_index"],
        )
    )
    winners: list[tuple[dict[str, Any], np.ndarray]] = []
    used: set[str] = set()
    for row, action in rows:
        if row["case_id"] in used:
            continue
        used.add(row["case_id"])
        winners.append((row, action))
        if len(winners) == int(contract["gates"]["selected_family_count"]):
            break

    output_directory.mkdir(parents=True)
    action_directory = output_directory / "actions"
    action_directory.mkdir()
    selected = []
    for index, (row, action) in enumerate(winners):
        path = action_directory / f"{index:02d}.f64le"
        path.write_bytes(action.tobytes(order="C"))
        try:
            public_path = str(path.relative_to(REPO_ROOT))
        except ValueError:
            public_path = str(path)
        selected.append(
            {
                **row,
                "direction": (
                    "REAL_TO_SIM" if index % 2 == 0 else "SIM_TO_REAL"
                ),
                "action_path": public_path,
                "action_sha256": _sha(path),
                "action_shape": list(action.shape),
            }
        )
    required = int(contract["gates"]["minimum_families_per_direction"])
    counts = {
        direction: sum(
            row["direction"] == direction for row in selected
        )
        for direction in ("REAL_TO_SIM", "SIM_TO_REAL")
    }
    passed = (
        len(selected) == int(contract["gates"]["selected_family_count"])
        and all(value >= required for value in counts.values())
    )
    receipt = {
        "schema_version": "sim2claw.canonical_seeded_action_static_receipt.v1",
        "status": (
            "canonical_seeded_action_static_pass"
            if passed
            else "canonical_seeded_action_static_reject"
        ),
        "proof_class": (
            "cpu_fp64_canonical_current_anchor_seeded_static_action_freeze"
        ),
        "contract_path": str(contract_path.relative_to(REPO_ROOT)),
        "contract_sha256": _sha(contract_path),
        "family_count": len(families),
        "grid_cell_count": len(families)
        * len(contract["grid"]["contact_offsets_m"])
        * len(contract["grid"]["contact_heights_m"])
        * len(contract["grid"]["stroke_lengths_m"]),
        "eligible_cell_count": len(rows),
        "reject_counts": rejects,
        "selected": selected,
        "direction_counts": counts,
        "row_zero_exact_live_anchor": all(
            np.allclose(
                row["gateway"]["row_zero_physical"],
                seed_physical[0],
                atol=1e-12,
                rtol=0.0,
            )
            for row in selected
        ),
        "mapping_calibration_approved": bool(
            candidate_config["physical_adapter"]["joint_transform"].get(
                "calibration_approved"
            )
        ),
        "dynamic_simulation_executed": False,
        "physical_motion": False,
        "task_attempts": 0,
        "passed": passed,
        "authority": contract["authority"],
        "claim_boundary": contract["claim_boundary"],
    }
    (output_directory / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = [
    "CanonicalSeededActionStaticError",
    "enumerate_and_freeze",
]

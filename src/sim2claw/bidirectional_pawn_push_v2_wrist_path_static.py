"""Prospective V05-TW wrist-orientation and precontact-path static freezer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from . import bidirectional_pawn_push_v2_action_geometry_static as _geometry
from . import bidirectional_pawn_push_v2_sim_rehearsal as _rehearsal
from . import bidirectional_pawn_push_v2_temporal_static as _static
from .grasp import _pinch_offset, _pinch_point
from .paths import REPO_ROOT
from .physical_canary import _physical_to_model_position
from .scene import board_square_center


class WristPathStaticError(RuntimeError):
    """The prospectively frozen V05-TW static search failed closed."""


ARM_JOINTS = (
    "left_shoulder_pan",
    "left_shoulder_lift",
    "left_elbow_flex",
    "left_wrist_flex",
    "left_wrist_roll",
)
SOLVED_JOINTS = ARM_JOINTS[:4]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(path: Path) -> Path:
    resolved = path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise WristPathStaticError("V05-TW path escapes repository") from error
    return resolved


def _verify(entry: Mapping[str, Any]) -> Path:
    path = _resolve(Path(str(entry["path"])))
    if not path.is_file() or _sha(path) != entry["sha256"]:
        raise WristPathStaticError(f"bound V05-TW input changed: {path}")
    return path


def _json_binding(entry: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
    path = _verify(entry)
    return path, json.loads(path.read_text(encoding="utf-8"))


def _case_id(case: Mapping[str, str]) -> str:
    return (
        f"{case['selected_piece_id']}__"
        f"{case['source_square']}_{case['destination_square']}"
    )


def _named_id(
    model: mujoco.MjModel,
    object_type: mujoco.mjtObj,
    name: str,
) -> int:
    object_id = mujoco.mj_name2id(model, object_type, name)
    if object_id < 0:
        raise WristPathStaticError(f"required V05-TW object is missing: {name}")
    return int(object_id)


def _solve_fixed_wrist_position(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    target: np.ndarray,
    pinch_local: np.ndarray,
    wrist_roll_rad: float,
    *,
    iterations: int,
    damping: float,
    step_limit: float,
) -> tuple[np.ndarray, float]:
    """Solve pinch position with wrist roll held at the frozen grid value."""

    scratch = mujoco.MjData(model)
    scratch.qpos[:] = data.qpos
    wrist_id = _named_id(
        model, mujoco.mjtObj.mjOBJ_JOINT, "left_wrist_roll"
    )
    wrist_address = int(model.jnt_qposadr[wrist_id])
    scratch.qpos[wrist_address] = wrist_roll_rad
    joint_ids = [
        _named_id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        for name in SOLVED_JOINTS
    ]
    columns = [int(model.jnt_dofadr[joint_id]) for joint_id in joint_ids]
    tip_geom = _named_id(
        model,
        mujoco.mjtObj.mjOBJ_GEOM,
        "left_fixed_jaw_sph_tip2",
    )
    tip_body = int(model.geom_bodyid[tip_geom])
    jacp = np.zeros((3, model.nv), dtype=np.float64)
    identity = np.eye(3, dtype=np.float64)
    residual = float("inf")
    for _ in range(iterations):
        mujoco.mj_forward(model, scratch)
        tip = _pinch_point(model, scratch, "left", pinch_local)
        error = target - tip
        residual = float(np.linalg.norm(error))
        if residual < 0.0015:
            break
        mujoco.mj_jac(model, scratch, jacp, None, tip, tip_body)
        jacobian = jacp[:, columns]
        gain = jacobian @ jacobian.T + (damping**2) * identity
        update = jacobian.T @ np.linalg.solve(gain, error)
        update = np.clip(update, -step_limit, step_limit)
        for joint_id, delta in zip(joint_ids, update, strict=True):
            address = int(model.jnt_qposadr[joint_id])
            low, high = model.jnt_range[joint_id]
            scratch.qpos[address] = float(
                np.clip(scratch.qpos[address] + delta, low, high)
            )
        scratch.qpos[wrist_address] = wrist_roll_rad
    pose = np.asarray(
        [
            scratch.qpos[model.jnt_qposadr[
                _named_id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            ]]
            for name in ARM_JOINTS
        ],
        dtype=np.float64,
    )
    return pose, residual


def _segment_points(
    first: np.ndarray,
    second: np.ndarray,
    maximum_step_m: float,
) -> list[np.ndarray]:
    distance = float(np.linalg.norm(second - first))
    segments = max(1, int(np.ceil(distance / maximum_step_m)))
    return [
        first + (second - first) * (index / segments)
        for index in range(segments + 1)
    ]


def _compile_action(
    *,
    model: mujoco.MjModel,
    qpos_addresses: list[int],
    seed_model: np.ndarray,
    clearance_xyz: np.ndarray,
    contact_xyz: np.ndarray,
    direction: np.ndarray,
    stroke_m: float,
    wrist_roll_rad: float,
    sample_hz: float,
    speed_m_s: float,
    closed_jaw_rad: float,
    maximum_ik_residual_m: float,
    maximum_cartesian_waypoint_spacing_m: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    data = mujoco.MjData(model)
    seed = seed_model.copy()
    seed[4] = wrist_roll_rad
    seed[5] = closed_jaw_rad
    data.qpos[qpos_addresses] = seed
    data.qvel[:] = 0.0
    mujoco.mj_forward(model, data)
    pinch_local = _pinch_offset(model, data, "left")

    descend = _segment_points(
        clearance_xyz,
        contact_xyz,
        maximum_cartesian_waypoint_spacing_m,
    )
    push = _segment_points(
        contact_xyz,
        contact_xyz + direction * stroke_m,
        maximum_cartesian_waypoint_spacing_m,
    )
    cartesian_waypoints = descend + push[1:]
    solved: list[np.ndarray] = []
    residuals: list[float] = []
    for target in cartesian_waypoints:
        data.qpos[qpos_addresses] = seed
        data.qpos[qpos_addresses[-1]] = closed_jaw_rad
        data.qvel[:] = 0.0
        mujoco.mj_forward(model, data)
        arm, residual = _solve_fixed_wrist_position(
            model,
            data,
            target,
            pinch_local,
            wrist_roll_rad,
            iterations=240,
            damping=0.015,
            step_limit=0.10,
        )
        residuals.append(float(residual))
        if residual > maximum_ik_residual_m:
            raise _rehearsal.PushRehearsalError(
                "V05-TW fixed-wrist IK residual exceeded gate"
            )
        seed = np.concatenate((arm, np.asarray([closed_jaw_rad])))
        solved.append(seed.copy())

    rows = [solved[0]]
    segment_sample_counts: list[int] = []
    for cartesian_first, cartesian_second, joint_first, joint_second in zip(
        cartesian_waypoints[:-1],
        cartesian_waypoints[1:],
        solved[:-1],
        solved[1:],
        strict=True,
    ):
        distance = float(np.linalg.norm(cartesian_second - cartesian_first))
        samples = max(1, int(round((distance / speed_m_s) * sample_hz)))
        segment_sample_counts.append(samples)
        for index in range(1, samples + 1):
            blend = index / samples
            rows.append(joint_first + blend * (joint_second - joint_first))

    action = np.asarray(rows, dtype="<f8", order="C")
    arm_margins: list[float] = []
    per_joint_margin: dict[str, float] = {}
    for joint_index, name in enumerate(ARM_JOINTS):
        joint_id = _named_id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        low, high = model.jnt_range[joint_id]
        margin = float(
            min(
                np.min(action[:, joint_index] - low),
                np.min(high - action[:, joint_index]),
            )
        )
        arm_margins.append(margin)
        per_joint_margin[name] = margin
    jaw_id = _named_id(model, mujoco.mjtObj.mjOBJ_JOINT, "left_gripper")
    jaw_low, jaw_high = model.jnt_range[jaw_id]
    return action, {
        "maximum_ik_residual_m": max(residuals),
        "minimum_arm_joint_limit_margin_rad": min(arm_margins),
        "per_arm_joint_limit_margin_rad": per_joint_margin,
        "closed_jaw_target_rad": closed_jaw_rad,
        "maximum_closed_jaw_target_error_rad": float(
            np.max(np.abs(action[:, -1] - closed_jaw_rad))
        ),
        "simulator_jaw_bounds_rad": [float(jaw_low), float(jaw_high)],
        "wrist_roll_target_rad": wrist_roll_rad,
        "maximum_wrist_roll_target_error_rad": float(
            np.max(np.abs(action[:, 4] - wrist_roll_rad))
        ),
        "precontact_clearance_xyz_m": clearance_xyz.tolist(),
        "contact_start_xyz_m": contact_xyz.tolist(),
        "cartesian_waypoint_count": len(cartesian_waypoints),
        "descent_waypoint_count": len(descend),
        "push_waypoint_count": len(push),
        "segment_sample_counts": segment_sample_counts,
        "action_rows": len(action),
        "action_raw_float64le_sha256": hashlib.sha256(
            action.tobytes(order="C")
        ).hexdigest(),
    }


def _selection_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        -float(row["compile"]["minimum_arm_joint_limit_margin_rad"]),
        -float(row["gateway_bound_fractional_margin"]),
        -float(row["gateway_rate_fractional_margin"]),
        -float(row["camera"]["minimum_margin_px"]),
        float(row["compile"]["maximum_ik_residual_m"]),
        int(row["wrist_orientation_index"]),
        int(row["contact_offset_index"]),
        int(row["contact_height_index"]),
        int(row["stroke_index"]),
        str(row["case_id"]),
    )


def enumerate_and_freeze(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    public_contract = _resolve(contract_path)
    public_output = _resolve(output_directory)
    contract = json.loads(public_contract.read_text(encoding="utf-8"))
    if (
        contract.get("schema_version")
        != "sim2claw.bidirectional_pawn_push_v2_wrist_path_static.v1"
    ):
        raise WristPathStaticError("unexpected V05-TW static contract")

    _, authorization = _json_binding(contract["authorization"])
    _json_binding(contract["predecessor_static_receipt"])
    _json_binding(contract["rehearsal_contract"])
    _json_binding(contract["temporal_plan"])
    _verify(contract["geometry_source"])
    _verify(contract["scene_implementation"])
    _verify(contract["articulated_robot_model"])
    _, wrapper = _json_binding(contract["candidate_manifest"])
    _, rigid = _json_binding(contract["registration_candidate"])
    _verify(contract["implementation"])
    if authorization["quarantine"]["case_ids"] != contract["quarantine"][
        "case_ids"
    ]:
        raise WristPathStaticError("V05-TW quarantine changed")
    quarantine = set(contract["quarantine"]["case_ids"])
    if len(quarantine) != 4:
        raise WristPathStaticError("V05-TW quarantine is not exact")

    model, qpos, _, jaw_bodies = _rehearsal._registered_model(
        wrapper,
        rigid,
        float(contract["simulation"]["timestep_s"]),
    )
    seed_physical = np.asarray(
        [contract["action_identity"]["seed_physical"]], dtype=np.float64
    )
    seed_model = _physical_to_model_position(
        seed_physical, wrapper["candidate_config"]
    )[0]
    initial = mujoco.MjData(model)
    initial.qpos[qpos] = seed_model
    mujoco.mj_forward(model, initial)
    pieces = _static._pawn_layout(model)
    complete_universe = _static.enumerate_empty_orthogonal_neighbors(
        pieces,
        excluded_squares=contract["family_grid"]["excluded_source_squares"],
    )
    if len(complete_universe) != int(
        contract["family_grid"]["expected_prequarantine_family_count"]
    ):
        raise WristPathStaticError("V05-TW reset-layout family universe changed")
    universe = [
        case for case in complete_universe if _case_id(case) not in quarantine
    ]
    if len(universe) != int(
        contract["family_grid"]["expected_postquarantine_family_count"]
    ):
        raise WristPathStaticError(
            "V05-TW post-quarantine family universe changed"
        )

    camera = np.asarray(rigid["camera_matrix_3x4"], dtype=np.float64)
    image_size = tuple(contract["camera_gate"]["image_size_px"])
    minimum_camera_margin = float(contract["camera_gate"]["minimum_margin_px"])
    robot_bodies = _static._descendants(model, "left_base")
    sample_hz = float(contract["action_identity"]["sample_hz"])
    closed_jaw = float(contract["action_identity"]["closed_jaw_rad"])
    if closed_jaw != -0.1727003294848389:
        raise WristPathStaticError("V05-TW jaw scalar changed")

    public_output.mkdir(parents=True, exist_ok=True)
    actions_directory = public_output / "actions"
    actions_directory.mkdir(parents=True, exist_ok=True)
    grid_results: list[dict[str, Any]] = []
    family_winners: list[tuple[dict[str, Any], np.ndarray]] = []
    wrist_grid = contract["parameter_grid"]["wrist_roll_targets_rad"]
    clearance_height = float(
        contract["parameter_grid"]["precontact_clearance_height_above_pawn_base_m"]
    )

    for family_index, case in enumerate(universe):
        selected_id = _named_id(
            model, mujoco.mjtObj.mjOBJ_BODY, case["selected_piece_id"]
        )
        source_xyz = initial.xpos[selected_id].copy()
        source_center = np.asarray(
            board_square_center(case["source_square"]), dtype=np.float64
        )
        destination_center = np.asarray(
            board_square_center(case["destination_square"]), dtype=np.float64
        )
        direction = destination_center - source_center
        direction /= np.linalg.norm(direction)
        case_id = _case_id(case)
        passing_cells: list[tuple[dict[str, Any], np.ndarray]] = []

        for wrist_index, wrist_roll in enumerate(wrist_grid):
            for offset_index, contact_offset in enumerate(
                contract["parameter_grid"]["contact_center_offsets_m"]
            ):
                for height_index, contact_height in enumerate(
                    contract["parameter_grid"]["contact_heights_m"]
                ):
                    for stroke_index, stroke in enumerate(
                        contract["parameter_grid"]["stroke_lengths_m"]
                    ):
                        contact = source_xyz.copy()
                        contact[:2] -= direction[:2] * float(contact_offset)
                        contact[2] += float(contact_height)
                        clearance = contact.copy()
                        clearance[2] = source_xyz[2] + clearance_height
                        base = {
                            "case_id": case_id,
                            "family_id": case_id,
                            "family_index": family_index,
                            **case,
                            "wrist_roll_target_rad": wrist_roll,
                            "wrist_orientation_index": wrist_index,
                            "precontact_clearance_height_above_pawn_base_m": (
                                clearance_height
                            ),
                            "contact_center_offset_m": contact_offset,
                            "contact_offset_index": offset_index,
                            "contact_height_m": contact_height,
                            "contact_height_index": height_index,
                            "stroke_m": stroke,
                            "stroke_index": stroke_index,
                        }
                        try:
                            action, compile_metrics = _compile_action(
                                model=model,
                                qpos_addresses=qpos,
                                seed_model=seed_model,
                                clearance_xyz=clearance,
                                contact_xyz=contact,
                                direction=direction,
                                stroke_m=float(stroke),
                                wrist_roll_rad=float(wrist_roll),
                                sample_hz=sample_hz,
                                speed_m_s=float(
                                    contract["action_identity"][
                                        "cartesian_speed_m_s"
                                    ]
                                ),
                                closed_jaw_rad=closed_jaw,
                                maximum_ik_residual_m=float(
                                    contract["static_gates"][
                                        "maximum_ik_residual_m"
                                    ]
                                ),
                                maximum_cartesian_waypoint_spacing_m=float(
                                    contract["action_identity"][
                                        "maximum_cartesian_waypoint_spacing_m"
                                    ]
                                ),
                            )
                        except _rehearsal.PushRehearsalError as error:
                            grid_results.append(
                                {
                                    **base,
                                    "status": "compile_reject",
                                    "error": str(error),
                                    "static_eligible": False,
                                }
                            )
                            continue
                        collision = _static._collision_audit(
                            model=model,
                            qpos_addresses=qpos,
                            seed_model=seed_model,
                            action=action,
                            selected_piece_id=case["selected_piece_id"],
                            robot_bodies=robot_bodies,
                            jaw_bodies=jaw_bodies,
                        )
                        camera_audit = _static._camera_audit(
                            camera,
                            source_xyz,
                            direction,
                            float(stroke),
                            image_size,
                            minimum_camera_margin,
                        )
                        gateway = _static._gateway_audit(
                            action,
                            wrapper,
                            sample_hz=sample_hz,
                        )
                        bound_margin, rate_margin = (
                            _geometry._fractional_gateway_margins(
                                action, wrapper, gateway
                            )
                        )
                        checks = {
                            "ik": compile_metrics["maximum_ik_residual_m"]
                            <= contract["static_gates"][
                                "maximum_ik_residual_m"
                            ],
                            "arm_joint_margin": compile_metrics[
                                "minimum_arm_joint_limit_margin_rad"
                            ]
                            >= contract["static_gates"][
                                "minimum_arm_joint_limit_margin_rad"
                            ],
                            "wrist_target": compile_metrics[
                                "maximum_wrist_roll_target_error_rad"
                            ]
                            <= contract["static_gates"][
                                "wrist_target_tolerance_rad"
                            ],
                            "jaw_target": compile_metrics[
                                "maximum_closed_jaw_target_error_rad"
                            ]
                            <= contract["static_gates"][
                                "jaw_target_tolerance_rad"
                            ],
                            "selected_contact": collision[
                                "static_selected_contact_observed"
                            ],
                            "collision": collision["collision_free"],
                            "camera": camera_audit["camera_gate_passed"],
                            "gateway_limits": gateway[
                                "all_rows_inside_calibrated_limits"
                            ],
                            "gateway_rates": gateway[
                                "all_rates_within_reviewed_gateway_limits"
                            ],
                            "requested_sent_identity": gateway[
                                "requested_sent_byte_identical"
                            ],
                        }
                        row = {
                            **base,
                            "compile": compile_metrics,
                            "collision": collision,
                            "camera": camera_audit,
                            "gateway": gateway,
                            "gateway_bound_fractional_margin": bound_margin,
                            "gateway_rate_fractional_margin": rate_margin,
                            "checks": checks,
                            "static_eligible": all(checks.values()),
                        }
                        row["status"] = (
                            "static_eligible"
                            if row["static_eligible"]
                            else "static_reject"
                        )
                        grid_results.append(row)
                        if row["static_eligible"]:
                            passing_cells.append((row, action))
        if passing_cells:
            family_winners.append(
                min(passing_cells, key=lambda item: _selection_key(item[0]))
            )

    selected_family_count = int(contract["selection"]["selected_family_count"])
    family_winners.sort(key=lambda item: _selection_key(item[0]))
    selected = family_winners[:selected_family_count]
    eligible_cases: list[dict[str, Any]] = []
    for selected_index, (row, action) in enumerate(selected):
        lane = "REAL_TO_SIM" if selected_index % 2 == 0 else "SIM_TO_REAL"
        action_bytes = np.asarray(action, dtype="<f8", order="C").tobytes(
            order="C"
        )
        action_path = actions_directory / f"{selected_index:02d}.f64le"
        action_path.write_bytes(action_bytes)
        eligible_cases.append(
            {
                "case_id": row["case_id"],
                "family_id": row["family_id"],
                "direction_lane": lane,
                "source_square": row["source_square"],
                "destination_square": row["destination_square"],
                "selected_piece_id": row["selected_piece_id"],
                "wrist_roll_target_rad": row["wrist_roll_target_rad"],
                "precontact_clearance_height_above_pawn_base_m": row[
                    "precontact_clearance_height_above_pawn_base_m"
                ],
                "contact_center_offset_m": row["contact_center_offset_m"],
                "contact_height_m": row["contact_height_m"],
                "stroke_m": row["stroke_m"],
                "action_path": str(action_path.relative_to(REPO_ROOT)),
                "action_sha256": hashlib.sha256(action_bytes).hexdigest(),
                "action_shape": list(action.shape),
                "action_dtype": "little_endian_float64",
                "sample_hz": sample_hz,
                "compile": row["compile"],
                "camera": row["camera"],
                "collision": row["collision"],
                "gateway": row["gateway"],
                "gateway_bound_fractional_margin": row[
                    "gateway_bound_fractional_margin"
                ],
                "gateway_rate_fractional_margin": row[
                    "gateway_rate_fractional_margin"
                ],
            }
        )

    lane_counts = {
        lane: sum(row["direction_lane"] == lane for row in eligible_cases)
        for lane in ("REAL_TO_SIM", "SIM_TO_REAL")
    }
    minimum = int(
        contract["selection"]["minimum_distinct_families_per_direction"]
    )
    passed = (
        len(family_winners) >= selected_family_count
        and len({row["family_id"] for row in eligible_cases})
        == selected_family_count
        and min(lane_counts.values(), default=0) >= minimum
    )
    receipt = {
        "schema_version": (
            "sim2claw.bidirectional_pawn_push_v2_wrist_path_static_receipt.v1"
        ),
        "status": (
            "wrist_path_static_freeze_pass"
            if passed
            else "wrist_path_static_freeze_reject"
        ),
        "proof_class": (
            "cpu_fp64_static_wrist_orientation_precontact_path_ik_collision_"
            "camera_gateway_action_freeze_only"
        ),
        "contract_path": str(public_contract.relative_to(REPO_ROOT)),
        "contract_sha256": _sha(public_contract),
        "authorization_sha256": contract["authorization"]["sha256"],
        "quarantined_case_ids": list(contract["quarantine"]["case_ids"]),
        "quarantined_case_count": len(quarantine),
        "quarantine_leaked_into_candidates": False,
        "selection_used_dynamic_outcomes": False,
        "prequarantine_family_count": len(complete_universe),
        "postquarantine_family_count": len(universe),
        "parameter_cell_count_per_family": (
            len(wrist_grid)
            * len(contract["parameter_grid"]["contact_center_offsets_m"])
            * len(contract["parameter_grid"]["contact_heights_m"])
            * len(contract["parameter_grid"]["stroke_lengths_m"])
        ),
        "grid_result_count": len(grid_results),
        "grid_results": grid_results,
        "statically_eligible_family_count": len(family_winners),
        "selected_family_count": len(eligible_cases),
        "eligible_cases": eligible_cases,
        "lane_counts": lane_counts,
        "minimum_distinct_families_per_direction": minimum,
        "dynamic_replay_executed": False,
        "physical_motion": False,
        "physical_task_attempts": 0,
        "authority": contract["authority"],
        "claim_boundary": (
            "Static-only deterministic wrist-orientation and explicit "
            "precontact-path search and exact action freeze over "
            "nonquarantined reset-layout families. No dynamic task outcome, "
            "calibrated plant, physical packet, promotion, or transfer claim."
        ),
    }
    (public_output / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = ["WristPathStaticError", "enumerate_and_freeze"]

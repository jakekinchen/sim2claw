"""V05-TY v2 slow/elevated static enumerator with exact fresh-case quarantine."""

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
from .grasp import _pinch_offset, _solve_reach
from .paths import REPO_ROOT
from .physical_canary import _physical_to_model_position
from .scene import board_square_center


class SlowElevatedStaticV2Error(RuntimeError):
    """The prospectively frozen V05-TY v2 static search failed closed."""


ARM_JOINTS = (
    "left_shoulder_pan",
    "left_shoulder_lift",
    "left_elbow_flex",
    "left_wrist_flex",
    "left_wrist_roll",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(path: Path) -> Path:
    resolved = path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise SlowElevatedStaticV2Error(
            "V05-TY v2 path escapes repository"
        ) from error
    return resolved


def _verify(entry: Mapping[str, Any]) -> Path:
    path = _resolve(Path(str(entry["path"])))
    if not path.is_file() or _sha(path) != entry["sha256"]:
        raise SlowElevatedStaticV2Error(
            f"bound V05-TY v2 input changed: {path}"
        )
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
        raise SlowElevatedStaticV2Error(
            f"required V05-TY v2 object is missing: {name}"
        )
    return int(object_id)


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


def _append_joint_segment(
    rows: list[np.ndarray],
    first: np.ndarray,
    second: np.ndarray,
    wrapper: Mapping[str, Any],
    *,
    sample_hz: float,
    speed_physical_units_s: float,
) -> int:
    endpoints = np.asarray([first, second], dtype="<f8")
    physical = _static._physical_actions(endpoints, wrapper)
    maximum_delta = float(np.max(np.abs(physical[1] - physical[0])))
    samples = max(
        1,
        int(round((maximum_delta / speed_physical_units_s) * sample_hz)),
    )
    for index in range(1, samples + 1):
        blend = index / samples
        rows.append(first + blend * (second - first))
    return samples


def _compile_action(
    *,
    model: mujoco.MjModel,
    qpos_addresses: list[int],
    wrapper: Mapping[str, Any],
    source_model: np.ndarray,
    branch_model: np.ndarray,
    cartesian_waypoints: list[np.ndarray],
    sample_hz: float,
    cartesian_speed_m_s: float,
    setup_speed_physical_units_s: float,
    closed_jaw_rad: float,
    maximum_ik_residual_m: float,
    maximum_cartesian_waypoint_spacing_m: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    source = source_model.copy()
    source[5] = closed_jaw_rad
    branch = branch_model.copy()
    branch[5] = closed_jaw_rad
    data = mujoco.MjData(model)
    data.qpos[qpos_addresses] = branch
    data.qvel[:] = 0.0
    mujoco.mj_forward(model, data)
    pinch_local = _pinch_offset(model, data, "left")

    dense_cartesian: list[np.ndarray] = []
    for first, second in zip(
        cartesian_waypoints[:-1],
        cartesian_waypoints[1:],
        strict=True,
    ):
        points = _segment_points(
            first,
            second,
            maximum_cartesian_waypoint_spacing_m,
        )
        dense_cartesian.extend(points if not dense_cartesian else points[1:])

    solved: list[np.ndarray] = []
    residuals: list[float] = []
    seed = branch.copy()
    for target in dense_cartesian:
        data.qpos[qpos_addresses] = seed
        data.qpos[qpos_addresses[-1]] = closed_jaw_rad
        data.qvel[:] = 0.0
        mujoco.mj_forward(model, data)
        pose, residual = _solve_reach(
            model,
            data,
            "left",
            target,
            pinch_local,
            iterations=240,
            damping=0.015,
            step_limit=0.10,
        )
        residuals.append(float(residual))
        if residual > maximum_ik_residual_m:
            raise _rehearsal.PushRehearsalError(
                "V05-TY v2 multi-start IK residual exceeded gate"
            )
        seed = np.asarray(
            [
                pose["shoulder_pan"],
                pose["shoulder_lift"],
                pose["elbow_flex"],
                pose["wrist_flex"],
                pose["wrist_roll"],
                closed_jaw_rad,
            ],
            dtype=np.float64,
        )
        solved.append(seed.copy())

    rows = [source.copy()]
    setup_source_to_branch_samples = _append_joint_segment(
        rows,
        source,
        branch,
        wrapper,
        sample_hz=sample_hz,
        speed_physical_units_s=setup_speed_physical_units_s,
    )
    setup_branch_to_approach_samples = _append_joint_segment(
        rows,
        branch,
        solved[0],
        wrapper,
        sample_hz=sample_hz,
        speed_physical_units_s=setup_speed_physical_units_s,
    )
    cartesian_segment_sample_counts: list[int] = []
    for cartesian_first, cartesian_second, joint_first, joint_second in zip(
        dense_cartesian[:-1],
        dense_cartesian[1:],
        solved[:-1],
        solved[1:],
        strict=True,
    ):
        distance = float(np.linalg.norm(cartesian_second - cartesian_first))
        samples = max(
            1,
            int(round((distance / cartesian_speed_m_s) * sample_hz)),
        )
        cartesian_segment_sample_counts.append(samples)
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
    physical = _static._physical_actions(action, wrapper)
    return action, {
        "maximum_ik_residual_m": max(residuals),
        "minimum_arm_joint_limit_margin_rad": min(arm_margins),
        "per_arm_joint_limit_margin_rad": per_joint_margin,
        "closed_jaw_target_rad": closed_jaw_rad,
        "maximum_closed_jaw_target_error_rad": float(
            np.max(np.abs(action[:, -1] - closed_jaw_rad))
        ),
        "source_model_rad": source.tolist(),
        "branch_model_rad": branch.tolist(),
        "first_physical_degrees_percent": physical[0].tolist(),
        "branch_physical_degrees_percent": (
            _static._physical_actions(
                np.asarray([branch], dtype="<f8"),
                wrapper,
            )[0].tolist()
        ),
        "setup_source_to_branch_samples": setup_source_to_branch_samples,
        "setup_branch_to_approach_samples": (
            setup_branch_to_approach_samples
        ),
        "cartesian_waypoint_count": len(dense_cartesian),
        "cartesian_segment_sample_counts": cartesian_segment_sample_counts,
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
        int(row["setup_branch_index"]),
        int(row["approach_azimuth_index"]),
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
        != "sim2claw.bidirectional_pawn_push_v2_slow_elevated_static.v2"
    ):
        raise SlowElevatedStaticV2Error(
            "unexpected V05-TY v2 static contract"
        )

    _, authorization = _json_binding(contract["authorization"])
    _json_binding(contract["v1_binding_failure"])
    _json_binding(contract["standing_delegation"])
    _json_binding(contract["predecessor_static_receipt"])
    _json_binding(contract["gateway_admissible_route"])
    _json_binding(contract["gateway_admissible_pose_family"])
    _json_binding(contract["physical_no_contact_route_receipt"])
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
        raise SlowElevatedStaticV2Error("V05-TY v2 quarantine changed")
    quarantine = set(contract["quarantine"]["case_ids"])
    if len(quarantine) != int(contract["quarantine"]["exact_count"]):
        raise SlowElevatedStaticV2Error(
            "V05-TY v2 quarantine count binding changed"
        )
    if len(quarantine) != 8:
        raise SlowElevatedStaticV2Error("V05-TY v2 quarantine is not exact")

    model, qpos, _, jaw_bodies = _rehearsal._registered_model(
        wrapper,
        rigid,
        float(contract["simulation"]["timestep_s"]),
    )
    source_physical = np.asarray(
        [contract["action_identity"]["source_physical_degrees_percent"]],
        dtype=np.float64,
    )
    source_model = _physical_to_model_position(
        source_physical, wrapper["candidate_config"]
    )[0]
    branch_physical = np.asarray(
        [
            row["physical_degrees_percent"]
            for row in contract["parameter_grid"]["setup_branches"]
        ],
        dtype=np.float64,
    )
    branch_models = _physical_to_model_position(
        branch_physical, wrapper["candidate_config"]
    )
    initial = mujoco.MjData(model)
    initial.qpos[qpos] = source_model
    mujoco.mj_forward(model, initial)
    pieces = _static._pawn_layout(model)
    complete_universe = _static.enumerate_empty_orthogonal_neighbors(
        pieces,
        excluded_squares=contract["family_grid"]["excluded_source_squares"],
    )
    if len(complete_universe) != int(
        contract["family_grid"]["expected_prequarantine_family_count"]
    ):
        raise SlowElevatedStaticV2Error(
            "V05-TY v2 reset-layout family universe changed"
        )
    universe = [
        case for case in complete_universe if _case_id(case) not in quarantine
    ]
    if len(universe) != int(
        contract["family_grid"]["expected_postquarantine_family_count"]
    ):
        raise SlowElevatedStaticV2Error(
            "V05-TY v2 post-quarantine family universe changed"
        )

    camera = np.asarray(rigid["camera_matrix_3x4"], dtype=np.float64)
    image_size = tuple(contract["camera_gate"]["image_size_px"])
    minimum_camera_margin = float(contract["camera_gate"]["minimum_margin_px"])
    robot_bodies = _static._descendants(model, "left_base")
    sample_hz = float(contract["action_identity"]["sample_hz"])
    closed_jaw = float(contract["action_identity"]["closed_jaw_rad"])
    if closed_jaw != -0.1727003294848389:
        raise SlowElevatedStaticV2Error("V05-TY v2 jaw scalar changed")

    public_output.mkdir(parents=True, exist_ok=True)
    actions_directory = public_output / "actions"
    actions_directory.mkdir(parents=True, exist_ok=True)
    grid_results: list[dict[str, Any]] = []
    family_winners: list[tuple[dict[str, Any], np.ndarray]] = []
    offsets = contract["parameter_grid"]["approach_lateral_offsets_m"]
    contact_offset = float(contract["endpoint_geometry"]["contact_offset_m"])
    contact_height = float(contract["endpoint_geometry"]["contact_height_m"])
    stroke = float(contract["endpoint_geometry"]["stroke_m"])
    clearance_height = float(
        contract["endpoint_geometry"][
            "precontact_clearance_height_above_pawn_base_m"
        ]
    )
    source_expected = np.asarray(
        contract["action_identity"]["source_physical_degrees_percent"],
        dtype=np.float64,
    )
    source_body_tolerance = float(
        contract["start_envelope"]["maximum_source_body_delta_degrees"]
    )
    source_gripper_tolerance = float(
        contract["start_envelope"]["maximum_source_gripper_delta_percent"]
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
        perpendicular = np.asarray(
            [-direction[1], direction[0], 0.0],
            dtype=np.float64,
        )
        contact = source_xyz.copy()
        contact[:2] -= direction[:2] * contact_offset
        contact[2] += contact_height
        overhead = contact.copy()
        overhead[2] = source_xyz[2] + clearance_height
        case_id = _case_id(case)
        passing_cells: list[tuple[dict[str, Any], np.ndarray]] = []

        for branch_index, (branch_spec, branch_model) in enumerate(
            zip(
                contract["parameter_grid"]["setup_branches"],
                branch_models,
                strict=True,
            )
        ):
            for azimuth_index, lateral_offset in enumerate(offsets):
                lateral = overhead + perpendicular * float(lateral_offset)
                cartesian_waypoints = [lateral]
                if not np.array_equal(lateral, overhead):
                    cartesian_waypoints.append(overhead)
                cartesian_waypoints.extend(
                    [contact, contact + direction * stroke]
                )
                base = {
                    "case_id": case_id,
                    "family_id": case_id,
                    "family_index": family_index,
                    **case,
                    "setup_branch_id": branch_spec["branch_id"],
                    "setup_branch_index": branch_index,
                    "approach_lateral_offset_m": lateral_offset,
                    "approach_azimuth_index": azimuth_index,
                    "contact_center_offset_m": contact_offset,
                    "contact_height_m": contact_height,
                    "stroke_m": stroke,
                    "precontact_clearance_height_above_pawn_base_m": (
                        clearance_height
                    ),
                }
                try:
                    action, compile_metrics = _compile_action(
                        model=model,
                        qpos_addresses=qpos,
                        wrapper=wrapper,
                        source_model=source_model,
                        branch_model=branch_model,
                        cartesian_waypoints=cartesian_waypoints,
                        sample_hz=sample_hz,
                        cartesian_speed_m_s=float(
                            contract["action_identity"][
                                "cartesian_speed_m_s"
                            ]
                        ),
                        setup_speed_physical_units_s=float(
                            contract["action_identity"][
                                "setup_joint_speed_physical_units_s"
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
                    seed_model=source_model,
                    action=action,
                    selected_piece_id=case["selected_piece_id"],
                    robot_bodies=robot_bodies,
                    jaw_bodies=jaw_bodies,
                )
                camera_audit = _static._camera_audit(
                    camera,
                    source_xyz,
                    direction,
                    stroke,
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
                first_physical = np.asarray(
                    compile_metrics["first_physical_degrees_percent"],
                    dtype=np.float64,
                )
                source_body_delta = float(
                    np.max(np.abs(first_physical[:5] - source_expected[:5]))
                )
                source_gripper_delta = float(
                    abs(first_physical[5] - source_expected[5])
                )
                checks = {
                    "ik": compile_metrics["maximum_ik_residual_m"]
                    <= contract["static_gates"]["maximum_ik_residual_m"],
                    "arm_joint_margin": compile_metrics[
                        "minimum_arm_joint_limit_margin_rad"
                    ]
                    >= contract["static_gates"][
                        "minimum_arm_joint_limit_margin_rad"
                    ],
                    "jaw_target": compile_metrics[
                        "maximum_closed_jaw_target_error_rad"
                    ]
                    <= contract["static_gates"]["jaw_target_tolerance_rad"],
                    "source_body_envelope": (
                        source_body_delta <= source_body_tolerance
                    ),
                    "source_gripper_envelope": (
                        source_gripper_delta <= source_gripper_tolerance
                    ),
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
                    "source_body_delta_degrees": source_body_delta,
                    "source_gripper_delta_percent": source_gripper_delta,
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
                "setup_branch_id": row["setup_branch_id"],
                "approach_lateral_offset_m": row[
                    "approach_lateral_offset_m"
                ],
                "contact_center_offset_m": contact_offset,
                "contact_height_m": contact_height,
                "stroke_m": stroke,
                "precontact_clearance_height_above_pawn_base_m": (
                    clearance_height
                ),
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
            "sim2claw."
            "bidirectional_pawn_push_v2_slow_elevated_static_receipt.v2"
        ),
        "status": (
            "slow_elevated_static_freeze_pass"
            if passed
            else "slow_elevated_static_freeze_reject"
        ),
        "proof_class": (
            "cpu_fp64_static_slow_elevated_long_stroke_multistart_"
            "approach_collision_camera_gateway_action_freeze_only_v2"
        ),
        "contract_path": str(public_contract.relative_to(REPO_ROOT)),
        "contract_sha256": _sha(public_contract),
        "authorization_sha256": contract["authorization"]["sha256"],
        "standing_delegation_sha256": contract["standing_delegation"]["sha256"],
        "quarantined_case_ids": list(contract["quarantine"]["case_ids"]),
        "quarantined_case_count": len(quarantine),
        "quarantine_leaked_into_candidates": False,
        "selection_used_dynamic_outcomes": False,
        "prequarantine_family_count": len(complete_universe),
        "postquarantine_family_count": len(universe),
        "parameter_cell_count_per_family": (
            len(contract["parameter_grid"]["setup_branches"])
            * len(offsets)
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
            "Static-only deterministic slow/elevated long-stroke multistart "
            "approach search with setup included in exact action bytes. "
            "No dynamic task outcome, calibrated plant, physical packet, "
            "promotion, or transfer claim."
        ),
    }
    (public_output / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = ["SlowElevatedStaticV2Error", "enumerate_and_freeze"]

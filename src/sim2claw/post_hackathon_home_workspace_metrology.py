"""Owner-reported home-workspace metrology and exact kinematic phase evaluation."""

from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from .exact_applied_state_schedule import build_exact_applied_state_schedule
from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .named_jaw_contact import (
    measure_named_jaw_contact,
    resolve_named_contact_geometry,
)
from .observable_contact_phase_registration import (
    _initialize_kinematic_state,
    load_contact_phase_contract,
)
from .observable_jaw_aperture_replay import _bound_json, _bound_path
from .paths import DEFAULT_EXTERNAL_ROOT, REPO_ROOT
from .realized_action_outcome_mission import _tensor, physical_to_model
from .scene import CURRENT_TASK_PIECE_LAYOUT, build_scene_spec


SCHEMA = "sim2claw.post_hackathon_home_workspace_metrology_contract.v1"
MEASUREMENT_SCHEMA = (
    "sim2claw.post_hackathon_home_workspace_manual_metrology.v1"
)
RECEIPT_SCHEMA = "sim2claw.post_hackathon_home_workspace_metrology_receipt.v1"
TRACE_SCHEMA = (
    "sim2claw.post_hackathon_home_workspace_metrology_contact_trace.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "post_hackathon_home_workspace_metrology_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT / "outputs" / "post_hackathon_home_workspace_metrology_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _rotation_2d(degrees: float) -> np.ndarray:
    angle = math.radians(float(degrees))
    return np.asarray(
        [
            [math.cos(angle), -math.sin(angle)],
            [math.sin(angle), math.cos(angle)],
        ],
        dtype=np.float64,
    )


def load_metrology_contract(
    path: Path = CONTRACT_PATH,
    *,
    root: Path = REPO_ROOT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = load_json_object(path, label="home-workspace metrology contract")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    sources = contract.get("sources")
    _require(isinstance(sources, dict) and sources, "sources are missing")
    for source_id, binding in sources.items():
        _require(isinstance(binding, dict), f"invalid source: {source_id}")
        _bound_path(binding, root=root, label=source_id)
    measurement = _bound_json(
        sources["measurement"], root=root, label="manual metrology"
    )
    _require(
        measurement.get("schema_version") == MEASUREMENT_SCHEMA,
        "unsupported manual metrology",
    )
    _require(
        measurement.get("workspace") == "post_hackathon_home_workspace",
        "workspace identity changed",
    )
    exclusions = measurement.get("fit_exclusions")
    _require(
        isinstance(exclusions, dict)
        and exclusions
        and all(exclusions.values()),
        "manual measurement fit exclusions widened",
    )
    limitations = measurement.get("limitations")
    _require(
        isinstance(limitations, dict)
        and limitations.get("base_yaw_directly_measured") is False
        and limitations.get("base_height_directly_measured") is False
        and limitations.get("global_mapping_approval_allowed") is False,
        "manual measurement limitation changed",
    )
    scene_policy = contract.get("scene_policy")
    _require(
        isinstance(scene_policy, dict)
        and scene_policy.get("baseline_scene_immutable") is True
        and scene_policy.get("left_base_yaw_fit_allowed") is False
        and scene_policy.get("left_base_z_fit_allowed") is False
        and scene_policy.get("right_robot_changed") is False
        and scene_policy.get("camera_changed") is False,
        "scene policy widened",
    )
    fit = contract.get("translation_fit")
    _require(
        isinstance(fit, dict)
        and fit.get("parameters")
        == ["base_origin_board_x_m", "base_origin_board_y_m"]
        and fit.get("fit_yaw") is False
        and fit.get("fit_z") is False
        and fit.get("task_rows_allowed") is False
        and fit.get("task_outcome_allowed") is False
        and fit.get("contact_rows_allowed") is False,
        "translation fit boundary widened",
    )
    phase = contract.get("contact_phase_gate")
    _require(
        isinstance(phase, dict)
        and phase.get("physics_integration_allowed") is False
        and phase.get("candidate_contact_samples") == [228, 232]
        and phase.get("last_definitely_separate_sample") == 224
        and phase.get("dynamics_authorized") is False,
        "contact phase boundary widened",
    )
    promotion = contract.get("promotion")
    authority = contract.get("authority")
    _require(
        isinstance(promotion, dict)
        and promotion.get("canonical_scene_replacement_allowed") is False
        and promotion.get("global_mapping_approved") is False,
        "promotion boundary widened",
    )
    _require(
        isinstance(authority, dict) and authority and not any(authority.values()),
        "authority widened",
    )
    return contract, measurement


def _mesh_outline_local_xy(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    *,
    body_name: str,
    mesh_name: str,
) -> np.ndarray:
    body_id = int(
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body_name)
    )
    _require(body_id >= 0, f"missing body: {body_name}")
    geom_id = -1
    mesh_id = -1
    for candidate in range(model.ngeom):
        candidate_mesh = int(model.geom_dataid[candidate])
        if candidate_mesh < 0:
            continue
        candidate_name = mujoco.mj_id2name(
            model, mujoco.mjtObj.mjOBJ_MESH, candidate_mesh
        )
        if (
            int(model.geom_bodyid[candidate]) == body_id
            and candidate_name == mesh_name
        ):
            geom_id = candidate
            mesh_id = candidate_mesh
            break
    _require(geom_id >= 0 and mesh_id >= 0, f"missing mesh: {mesh_name}")
    first = int(model.mesh_vertadr[mesh_id])
    count = int(model.mesh_vertnum[mesh_id])
    vertices = np.asarray(
        model.mesh_vert[first : first + count], dtype=np.float64
    )
    geom_rotation = np.asarray(data.geom_xmat[geom_id], dtype=np.float64).reshape(
        3, 3
    )
    body_rotation = np.asarray(data.xmat[body_id], dtype=np.float64).reshape(
        3, 3
    )
    world = vertices @ geom_rotation.T + data.geom_xpos[geom_id]
    body_local = (world - data.xpos[body_id]) @ body_rotation
    return np.asarray(body_local[:, :2], dtype=np.float64)


def _section_width(
    outline: np.ndarray,
    *,
    x: float,
    tolerance_m: float,
) -> float:
    selected = outline[np.abs(outline[:, 0] - float(x)) <= tolerance_m]
    _require(len(selected) >= 2, "STL cross section has too few vertices")
    return float(np.ptp(selected[:, 1]))


def _fit_translation(
    *,
    outline: np.ndarray,
    measurement: dict[str, Any],
    baseline: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    board = measurement["board"]
    placement = measurement["board_to_follower_base"]
    outside_side = float(board["outside_side_primary"]["value_m"])
    outside_uncertainty = float(
        board["outside_side_primary"]["uncertainty_m"]
    )
    baseline_board = baseline["simulation_estimates"]["board"]
    left_robot = next(
        item
        for item in baseline["simulation_estimates"]["robots"]
        if item["name"] == "left"
    )
    relative_yaw = float(left_robot["yaw_relative_to_table_degrees"]) - float(
        baseline_board["yaw_relative_to_table_degrees"]
    )
    outline_board = outline @ _rotation_2d(relative_yaw).T
    minimum_x, minimum_y = np.min(outline_board, axis=0)
    maximum_x, maximum_y = np.max(outline_board, axis=0)
    left = placement["operator_left_board_edge_to_base_left_side"]
    right = placement["base_right_side_to_operator_right_board_edge"]
    front = placement["near_board_edge_to_front_tip"]
    left_candidate = (
        float(left["value_m"]) - (outside_side / 2.0) - minimum_x
    )
    right_candidate = (
        (outside_side / 2.0) - float(right["value_m"]) - maximum_x
    )
    left_sigma = float(left["uncertainty_m"])
    right_sigma = float(right["uncertainty_m"])
    weights = np.asarray(
        [1.0 / left_sigma**2, 1.0 / right_sigma**2],
        dtype=np.float64,
    )
    board_x = float(
        np.average(
            np.asarray([left_candidate, right_candidate]),
            weights=weights,
        )
    )
    board_x_uncertainty = math.sqrt(
        (1.0 / float(np.sum(weights))) + (outside_uncertainty / 2.0) ** 2
    )
    board_y = (
        (outside_side / 2.0)
        + float(front["value_m"])
        - minimum_y
    )
    board_y_uncertainty = math.hypot(
        float(front["uncertainty_m"]), outside_uncertainty / 2.0
    )
    predicted_left = board_x + minimum_x + (outside_side / 2.0)
    predicted_right = (outside_side / 2.0) - (board_x + maximum_x)
    predicted_front = board_y + minimum_y - (outside_side / 2.0)
    residuals = {
        "operator_left_gap": {
            "observed_m": float(left["value_m"]),
            "predicted_m": predicted_left,
            "residual_m": predicted_left - float(left["value_m"]),
            "normalized_residual": (
                predicted_left - float(left["value_m"])
            )
            / left_sigma,
        },
        "operator_right_gap": {
            "observed_m": float(right["value_m"]),
            "predicted_m": predicted_right,
            "residual_m": predicted_right - float(right["value_m"]),
            "normalized_residual": (
                predicted_right - float(right["value_m"])
            )
            / right_sigma,
        },
        "front_clearance": {
            "observed_m": float(front["value_m"]),
            "predicted_m": predicted_front,
            "residual_m": predicted_front - float(front["value_m"]),
            "normalized_residual": (
                predicted_front - float(front["value_m"])
            )
            / float(front["uncertainty_m"]),
        },
    }

    board_center = np.asarray(
        baseline_board["center_in_table_frame_xy_m"], dtype=np.float64
    )
    board_to_table = _rotation_2d(
        float(baseline_board["yaw_relative_to_table_degrees"])
    )
    candidate_mount_table = board_center + board_to_table @ np.asarray(
        [board_x, board_y], dtype=np.float64
    )
    baseline_mount_table = np.asarray(
        left_robot["mount_in_table_frame_xyz_m"][:2], dtype=np.float64
    )
    baseline_board_xy = board_to_table.T @ (
        baseline_mount_table - board_center
    )
    table = baseline["roomplan_measurements"]["table"]
    table_center_world = np.asarray(
        [
            float(table["center_xyz_m"][0]),
            -float(table["center_xyz_m"][2]),
        ],
        dtype=np.float64,
    )
    table_to_world = _rotation_2d(
        float(table["yaw_degrees_after_z_up_conversion"])
    )
    candidate_world_xy = (
        table_center_world + table_to_world @ candidate_mount_table
    )
    baseline_world_xy = (
        table_center_world + table_to_world @ baseline_mount_table
    )
    world_yaw = float(table["yaw_degrees_after_z_up_conversion"]) + float(
        left_robot["yaw_relative_to_table_degrees"]
    )
    yaw_radians = math.radians(world_yaw)
    candidate_z = float(left_robot["mount_in_table_frame_xyz_m"][2])
    maximum_uncertainty = max(board_x_uncertainty, board_y_uncertainty)
    maximum_normalized_residual = max(
        abs(float(item["normalized_residual"]))
        for item in residuals.values()
    )
    admitted = bool(
        maximum_uncertainty
        <= float(
            contract["translation_fit"][
                "maximum_translation_standard_uncertainty_m"
            ]
        )
        and maximum_normalized_residual
        <= float(
            contract["translation_fit"][
                "maximum_normalized_measurement_residual"
            ]
        )
    )
    return {
        "relative_yaw_degrees_frozen": relative_yaw,
        "yaw_fit_performed": False,
        "board_outline_extents_m": {
            "minimum_x": float(minimum_x),
            "maximum_x": float(maximum_x),
            "minimum_y": float(minimum_y),
            "maximum_y": float(maximum_y),
        },
        "independent_board_x_estimates_m": {
            "from_left_gap": left_candidate,
            "from_right_gap": right_candidate,
        },
        "candidate_base_origin_board_xy_m": [board_x, board_y],
        "baseline_base_origin_board_xy_m": baseline_board_xy.tolist(),
        "candidate_mount_in_table_frame_xyz_m": [
            float(candidate_mount_table[0]),
            float(candidate_mount_table[1]),
            candidate_z,
        ],
        "baseline_mount_in_table_frame_xyz_m": [
            float(baseline_mount_table[0]),
            float(baseline_mount_table[1]),
            candidate_z,
        ],
        "candidate_world_T_left_base": {
            "translation_m": [
                float(candidate_world_xy[0]),
                float(candidate_world_xy[1]),
                candidate_z,
            ],
            "quaternion_wxyz": [
                math.cos(yaw_radians / 2.0),
                0.0,
                0.0,
                math.sin(yaw_radians / 2.0),
            ],
            "yaw_degrees_frozen_unapproved": world_yaw,
        },
        "translation_delta_board_xy_m": (
            np.asarray([board_x, board_y]) - baseline_board_xy
        ).tolist(),
        "translation_delta_table_xy_m": (
            candidate_mount_table - baseline_mount_table
        ).tolist(),
        "translation_delta_world_xy_m": (
            candidate_world_xy - baseline_world_xy
        ).tolist(),
        "standard_uncertainty_m": {
            "board_x": board_x_uncertainty,
            "board_y": board_y_uncertainty,
            "maximum": maximum_uncertainty,
        },
        "measurement_residuals": residuals,
        "maximum_absolute_normalized_residual": maximum_normalized_residual,
        "translation_gate_passed": admitted,
        "rotation_gate_passed": False,
        "global_mapping_approved": False,
    }


def _stl_checks(
    *,
    outline: np.ndarray,
    measurement: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    tolerance = float(contract["stl_outline"]["cross_section_tolerance_m"])
    minimum_x = float(np.min(outline[:, 0]))
    maximum_x = float(np.max(outline[:, 0]))
    measured = measurement["follower_base_outline"]
    observed = {
        "front_tip_to_tip_width": _section_width(
            outline, x=maximum_x, tolerance_m=tolerance
        ),
        "maximum_center_width": float(np.ptp(outline[:, 1])),
        "rear_width": _section_width(
            outline, x=minimum_x, tolerance_m=tolerance
        ),
        "front_to_rear_length": maximum_x - minimum_x,
    }
    rows: dict[str, Any] = {}
    for name, stl_value in observed.items():
        owner_value = float(measured[name]["value_m"])
        error = stl_value - owner_value
        rows[name] = {
            "owner_reported_m": owner_value,
            "stl_m": stl_value,
            "error_m": error,
            "absolute_error_m": abs(error),
            "within_owner_uncertainty": abs(error)
            <= float(measured[name]["uncertainty_m"]),
        }
    maximum_error = max(float(row["absolute_error_m"]) for row in rows.values())
    return {
        "mesh_vertex_count": int(len(outline)),
        "measurements": rows,
        "maximum_absolute_error_m": maximum_error,
        "identity_gate_passed": bool(
            all(row["within_owner_uncertainty"] for row in rows.values())
            and maximum_error
            <= float(
                contract["stl_outline"][
                    "maximum_dimension_absolute_error_m"
                ]
            )
        ),
        "scale_change_applied": False,
    }


def _derived_scene(
    *,
    baseline: dict[str, Any],
    measurement: dict[str, Any],
    fit: dict[str, Any],
) -> dict[str, Any]:
    derived = copy.deepcopy(baseline)
    board = derived["simulation_estimates"]["board"]
    measured_board = measurement["board"]
    playing_side = float(measured_board["playing_surface_side"]["value_m"])
    outside_side = float(measured_board["outside_side_primary"]["value_m"])
    frame_width = (outside_side - playing_side) / 2.0
    _require(frame_width > 0.0, "measured board frame width is not positive")
    board["side_m"] = playing_side
    board["frame_width_m"] = frame_width
    board["thickness_m"] = float(measured_board["thickness"]["value_m"])
    board["scene_id"] = "post_hackathon_home_workspace_metrology_v1"
    board["pose_id"] = "owner_manual_board_to_left_base_20260730_v1"
    board["confidence"] = (
        "owner_reported_manual_metrology_translation_only_yaw_unapproved"
    )
    left_robot = next(
        item
        for item in derived["simulation_estimates"]["robots"]
        if item["name"] == "left"
    )
    left_robot["mount_in_table_frame_xyz_m"] = list(
        fit["candidate_mount_in_table_frame_xyz_m"]
    )
    left_robot["confidence"] = (
        "owner_reported_manual_board_edge_clearances_translation_only"
    )
    derived["metrology_lineage"] = {
        "measurement_id": measurement["measurement_id"],
        "candidate_family": "left_base_translation_xy_only",
        "baseline_scene_immutable": True,
        "yaw_fit_performed": False,
        "canonical_scene_replacement_allowed": False,
    }
    return derived


def _contact_phase(
    *,
    contract: dict[str, Any],
    derived_scene_path: Path,
    measurement: dict[str, Any],
    root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    or11_path = _bound_path(
        contract["sources"]["or11_contract"],
        root=root,
        label="OR11 contract",
    )
    or11, c6 = load_contact_phase_contract(or11_path, root=root)
    source = c6["source"]
    applied_physical = _tensor(
        _bound_path(source["identified_applied"], root=root, label="applied"),
        source["identified_applied"],
    )
    timestamps = _tensor(
        _bound_path(source["timestamps"], root=root, label="timestamps"),
        source["timestamps"],
    )
    initial_measured = _tensor(
        _bound_path(
            source["initial_measured"], root=root, label="initial measured"
        ),
        source["initial_measured"],
    )
    candidate_manifest = _bound_json(
        contract["sources"]["or6_candidate"],
        root=root,
        label="OR6 candidate",
    )
    candidate = candidate_manifest["candidate_config"]
    _require(
        canonical_digest(candidate)
        == contract["sources"]["or6_candidate"]["candidate_config_sha256"],
        "OR6 candidate identity changed",
    )
    or7 = _bound_json(
        contract["sources"]["or7_receipt"], root=root, label="OR7"
    )
    endpoint = _bound_json(
        contract["sources"]["initial_endpoint_receipt"],
        root=root,
        label="initial endpoint",
    )
    initial_xy = np.asarray(
        endpoint["observations"]["initial"]["world_position_m"][:2],
        dtype=np.float64,
    )
    applied_model = physical_to_model(
        applied_physical, {"candidate_config": candidate}
    )
    initial_model = physical_to_model(
        initial_measured[:1], {"candidate_config": candidate}
    )[0]
    schedule = build_exact_applied_state_schedule(
        applied_model,
        timestamps,
        timestep_seconds=float(or11["schedule"]["timestep_seconds"]),
    )
    model = build_scene_spec(
        config_path=derived_scene_path,
        external_root=DEFAULT_EXTERNAL_ROOT,
        piece_layout=CURRENT_TASK_PIECE_LAYOUT,
    ).compile()
    thickness_delta = float(measurement["board"]["thickness"]["value_m"]) - float(
        load_json_object(
            _bound_path(
                contract["sources"]["baseline_scene"],
                root=root,
                label="baseline scene",
            ),
            label="baseline scene",
        )["simulation_estimates"]["board"]["thickness_m"]
    )
    support_z = float(or7["initialization"]["pawn_support_z_m"]) + thickness_delta
    data, qpos_addresses, dof_addresses, selected_body = (
        _initialize_kinematic_state(
            model,
            candidate,
            initial_model,
            selected_piece=str(or11["identity"]["selected_piece"]),
            initial_xy=initial_xy,
            support_z=support_z,
        )
    )
    geometry_contract = or11["geometry"]
    geometry = resolve_named_contact_geometry(
        model,
        selected_body_name=str(or11["identity"]["selected_piece"]),
        fixed_jaw_prefix=str(geometry_contract["fixed_jaw_prefix"]),
        moving_jaw_prefix=str(geometry_contract["moving_jaw_prefix"]),
        fixed_tip_names=geometry_contract["fixed_tip_geoms"],
        moving_tip_names=geometry_contract["moving_tip_geoms"],
    )
    last_sample = int(
        contract["contact_phase_gate"]["candidate_contact_samples"][1]
    )
    rows: list[dict[str, Any]] = []
    for step in schedule.rows:
        if step.source_sample_index > last_sample:
            break
        data.qpos[qpos_addresses] = np.asarray(step.qpos, dtype=np.float64)
        data.qvel[dof_addresses] = np.asarray(step.qvel, dtype=np.float64)
        mujoco.mj_forward(model, data)
        measured = measure_named_jaw_contact(
            model,
            data,
            geometry,
            distance_maximum_m=float(geometry_contract["distance_maximum_m"]),
            other_pad_tolerance_m=float(
                or11["phase_gate"]["other_pad_maximum_distance_m"]
            ),
        )
        rows.append({**step.to_dict(), **measured})
    contact_first, contact_last = contract["contact_phase_gate"][
        "candidate_contact_samples"
    ]
    phase_rows = [
        row
        for row in rows
        if contact_first <= int(row["source_sample_index"]) <= contact_last
    ]
    first_named = next(
        (
            row
            for row in phase_rows
            if row["phase_contact_geometry_pass"]
            and not row["unrelated_pawn_contact_pairs"]
        ),
        None,
    )
    sample_last = next(
        row
        for row in reversed(phase_rows)
        if int(row["source_sample_index"]) == contact_last
    )
    minimum_fixed = min(
        float(row["fixed"]["signed_distance_m"]) for row in phase_rows
    )
    minimum_moving = min(
        float(row["moving"]["signed_distance_m"]) for row in phase_rows
    )
    fixed_tip_center = np.asarray(
        sample_last["fixed_tip_center_m"], dtype=np.float64
    )
    moving_tip_center = np.asarray(
        sample_last["moving_tip_center_m"], dtype=np.float64
    )
    pawn_center = np.asarray(sample_last["pawn_center_m"], dtype=np.float64)
    jaw_midpoint = (fixed_tip_center + moving_tip_center) / 2.0
    midpoint_to_pawn = pawn_center - jaw_midpoint
    result = {
        "support_z_m": support_z,
        "trace_row_count": len(rows),
        "physics_integration_steps": 0,
        "first_named_contact_source_sample": (
            int(first_named["source_sample_index"])
            if first_named is not None
            else None
        ),
        "contact_at_expected_phase": first_named is not None,
        "minimum_phase_fixed_jaw_gap_m": minimum_fixed,
        "minimum_phase_moving_jaw_gap_m": minimum_moving,
        "sample_232": {
            "fixed_signed_distance_m": float(
                sample_last["fixed"]["signed_distance_m"]
            ),
            "moving_signed_distance_m": float(
                sample_last["moving"]["signed_distance_m"]
            ),
            "pawn_center_bracketed": bool(
                sample_last["pawn_center_bracketed"]
            ),
            "phase_contact_geometry_pass": bool(
                sample_last["phase_contact_geometry_pass"]
            ),
            "jaw_midpoint_m": jaw_midpoint.tolist(),
            "pawn_center_m": pawn_center.tolist(),
            "midpoint_to_pawn_vector_m": midpoint_to_pawn.tolist(),
            "midpoint_to_pawn_planar_distance_m": float(
                np.linalg.norm(midpoint_to_pawn[:2])
            ),
            "midpoint_to_pawn_distance_m": float(
                np.linalg.norm(midpoint_to_pawn)
            ),
        },
        "dynamic_replays": 0,
        "dynamics_authorized": False,
    }
    return result, {"schema_version": TRACE_SCHEMA, "rows": rows}


def build_metrology_receipt(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract, measurement = load_metrology_contract(contract_path, root=root)
    baseline = _bound_json(
        contract["sources"]["baseline_scene"],
        root=root,
        label="baseline scene",
    )
    baseline_model = build_scene_spec(
        config_path=_bound_path(
            contract["sources"]["baseline_scene"],
            root=root,
            label="baseline scene",
        ),
        external_root=DEFAULT_EXTERNAL_ROOT,
        piece_layout=CURRENT_TASK_PIECE_LAYOUT,
    ).compile()
    baseline_data = mujoco.MjData(baseline_model)
    mujoco.mj_forward(baseline_model, baseline_data)
    outline = _mesh_outline_local_xy(
        baseline_model,
        baseline_data,
        body_name=str(contract["stl_outline"]["body"]),
        mesh_name=str(contract["stl_outline"]["mesh"]),
    )
    stl = _stl_checks(
        outline=outline, measurement=measurement, contract=contract
    )
    fit = _fit_translation(
        outline=outline,
        measurement=measurement,
        baseline=baseline,
        contract=contract,
    )
    derived = _derived_scene(
        baseline=baseline, measurement=measurement, fit=fit
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    derived_path = output_directory / "derived_scene_config.json"
    trace_path = output_directory / "contact_phase_trace.json"
    receipt_path = output_directory / "receipt.json"
    atomic_write_json(derived_path, derived)
    phase, trace = _contact_phase(
        contract=contract,
        derived_scene_path=derived_path,
        measurement=measurement,
        root=root,
    )
    atomic_write_json(trace_path, trace)
    baseline_or11 = _bound_json(
        contract["sources"]["or11_receipt"],
        root=root,
        label="OR11 receipt",
    )
    baseline_fixed = float(
        baseline_or11["phase"]["sample_232"]["fixed_signed_distance_m"]
    )
    fixed_reduction = baseline_fixed - float(
        phase["sample_232"]["fixed_signed_distance_m"]
    )
    board = measurement["board"]
    primary_side = float(board["outside_side_primary"]["value_m"])
    orthogonal_side = float(
        board["outside_side_orthogonal_check"]["value_m"]
    )
    orthogonal_residual = orthogonal_side - primary_side
    orthogonal_consistent = abs(orthogonal_residual) <= 2.0 * float(
        board["outside_side_orthogonal_check"]["uncertainty_m"]
    )
    translation_admitted = bool(
        stl["identity_gate_passed"]
        and fit["translation_gate_passed"]
        and orthogonal_consistent
    )
    material_gap_reduction = bool(
        fixed_reduction
        >= float(
            contract["contact_phase_gate"][
                "minimum_fixed_jaw_gap_reduction_m"
            ]
        )
    )
    if translation_admitted and phase["contact_at_expected_phase"]:
        result = (
            "TRANSLATION_CANDIDATE_REACHES_NAMED_CONTACT_PHASE_"
            "NO_DYNAMICS_AUTHORITY"
        )
    elif translation_admitted and material_gap_reduction:
        result = (
            "TRANSLATION_CANDIDATE_MATERIALLY_REDUCES_GAP_"
            "NO_NAMED_CONTACT_NO_DYNAMICS"
        )
    elif translation_admitted:
        result = "TRANSLATION_CANDIDATE_ADMITTED_NO_CONTACT_ADVANCEMENT"
    else:
        result = "PROOF_LIMITED_TRANSLATION_DIAGNOSTIC_NOT_ADMITTED"
    unsigned: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "result": result,
        "contract_sha256": sha256_file(contract_path),
        "measurement_sha256": sha256_file(
            _bound_path(
                contract["sources"]["measurement"],
                root=root,
                label="manual metrology",
            )
        ),
        "board_geometry": {
            "baseline_playing_side_m": float(
                baseline["simulation_estimates"]["board"]["side_m"]
            ),
            "candidate_playing_side_m": float(
                board["playing_surface_side"]["value_m"]
            ),
            "baseline_outside_side_m": float(
                baseline["simulation_estimates"]["board"]["side_m"]
                + 2.0
                * baseline["simulation_estimates"]["board"]["frame_width_m"]
            ),
            "candidate_outside_side_m": primary_side,
            "candidate_frame_width_m": (
                primary_side
                - float(board["playing_surface_side"]["value_m"])
            )
            / 2.0,
            "baseline_thickness_m": float(
                baseline["simulation_estimates"]["board"]["thickness_m"]
            ),
            "candidate_thickness_m": float(board["thickness"]["value_m"]),
            "orthogonal_check_m": orthogonal_side,
            "orthogonal_check_residual_m": orthogonal_residual,
            "orthogonal_consistency_gate_passed": orthogonal_consistent,
        },
        "stl_identity": stl,
        "translation_fit": fit,
        "translation_candidate_admitted": translation_admitted,
        "contact_phase": {
            **phase,
            "baseline_sample_232_fixed_jaw_gap_m": baseline_fixed,
            "sample_232_fixed_jaw_gap_reduction_m": fixed_reduction,
            "material_gap_reduction_gate_passed": material_gap_reduction,
        },
        "derived_scene": {
            "path": (
                derived_path.relative_to(root).as_posix()
                if root.resolve() in derived_path.resolve().parents
                else derived_path.resolve().as_posix()
            ),
            "sha256": sha256_file(derived_path),
            "canonical_replacement_allowed": False,
        },
        "trace": {
            "path": (
                trace_path.relative_to(root).as_posix()
                if root.resolve() in trace_path.resolve().parents
                else trace_path.resolve().as_posix()
            ),
            "sha256": sha256_file(trace_path),
            "row_count": int(phase["trace_row_count"]),
        },
        "fit_evidence": {
            "task_rows_used": 0,
            "task_outcome_used": False,
            "contact_rows_used": 0,
            "camera_pixels_used": 0,
            "yaw_fit_performed": False,
            "base_scale_change_applied": False,
        },
        "proof_boundaries": {
            "translation_only_diagnostic": True,
            "yaw_approved": False,
            "base_height_approved": False,
            "global_mapping_approved": False,
            "canonical_scene_replaced": False,
            "task_outcome_proved": False,
            "transfer_proved": False,
        },
        "authority": dict(contract["authority"]),
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(receipt_path, receipt)
    return receipt


__all__ = [
    "CONTRACT_PATH",
    "OUTPUT_DIRECTORY",
    "build_metrology_receipt",
    "load_metrology_contract",
]

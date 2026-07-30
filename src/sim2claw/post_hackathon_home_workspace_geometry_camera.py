"""Static home-workspace board, pawn, and camera-center reconciliation."""

from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any

import cv2
import mujoco
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

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
from .paths import DEFAULT_EXTERNAL_ROOT, REPO_ROOT
from .realized_action_outcome_mission import _tensor, physical_to_model
from .scene import CURRENT_TASK_PIECE_LAYOUT, build_scene_spec, scene_geometry


SCHEMA = "sim2claw.post_hackathon_home_workspace_geometry_camera_contract.v2"
MEASUREMENT_SCHEMA = (
    "sim2claw.post_hackathon_home_workspace_geometry_camera_manual_metrology.v2"
)
RECEIPT_SCHEMA = (
    "sim2claw.post_hackathon_home_workspace_geometry_camera_receipt.v2"
)
TRACE_SCHEMA = (
    "sim2claw.post_hackathon_home_workspace_geometry_camera_contact_trace.v2"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "post_hackathon_home_workspace_geometry_camera_v2.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT / "outputs" / "post_hackathon_home_workspace_geometry_camera_v2"
)
PRIOR_DETAILED_PAWN_HEIGHT_M = 0.0532


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _bound_path(
    binding: dict[str, Any], *, root: Path, label: str
) -> Path:
    path = root / str(binding.get("path", ""))
    expected = str(binding.get("sha256", ""))
    _require(path.is_file(), f"{label} source is missing")
    _require(
        len(expected) == 64 and sha256_file(path) == expected,
        f"{label} hash drifted",
    )
    return path


def _bound_json(
    binding: dict[str, Any], *, root: Path, label: str
) -> dict[str, Any]:
    return load_json_object(
        _bound_path(binding, root=root, label=label),
        label=label,
    )


def load_geometry_camera_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = load_json_object(path, label="home-workspace geometry/camera contract")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    sources = contract.get("sources")
    _require(isinstance(sources, dict) and sources, "sources are missing")
    for source_id, binding in sources.items():
        _require(isinstance(binding, dict), f"invalid source: {source_id}")
        _bound_path(binding, root=root, label=source_id)
    measurement = _bound_json(
        sources["measurement"], root=root, label="manual geometry/camera metrology"
    )
    _require(
        measurement.get("schema_version") == MEASUREMENT_SCHEMA,
        "unsupported measurement",
    )
    _require(
        measurement.get("workspace") == "post_hackathon_home_workspace",
        "workspace identity changed",
    )
    _require(
        contract.get("stage_order")
        == [
            "board_and_pawn_static_geometry",
            "camera_center_from_manual_ranges",
            "camera_orientation_from_retained_nonheldout_pixels",
        ],
        "stage order changed",
    )
    exclusions = measurement.get("fit_exclusions")
    _require(
        isinstance(exclusions, dict)
        and exclusions
        and all(exclusions.values()),
        "fit exclusions widened",
    )
    authority = contract.get("authority")
    promotion = contract.get("promotion")
    _require(
        isinstance(authority, dict) and authority and not any(authority.values()),
        "authority widened",
    )
    _require(
        isinstance(promotion, dict)
        and promotion.get("canonical_scene_replacement_allowed") is False
        and promotion.get("global_mapping_approved") is False,
        "promotion boundary widened",
    )
    camera = contract.get("retained_pixel_orientation_diagnostic")
    _require(
        isinstance(camera, dict)
        and camera.get("camera_center_fixed_from_manual_metrology") is True
        and camera.get("playing_side_fixed_from_board_object_geometry") is True
        and camera.get("fit_parameters")
        == ["focal_px", "rotation_vector_board_to_camera"]
        and camera.get("exact_intrinsics_claim_allowed") is False
        and camera.get("heldout_claim_allowed") is False,
        "camera diagnostic widened",
    )
    return contract, measurement


def _board_object_scene(
    base_scene: dict[str, Any],
    measurement: dict[str, Any],
    contract: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    derived = copy.deepcopy(base_scene)
    policy = contract["board_object_geometry"]
    board_measurement = measurement["board"]
    square = float(board_measurement["square_side"]["selected_value_m"])
    outside = float(board_measurement["outside_side_source"]["value_m"])
    playing = 8.0 * square
    frame = (outside - playing) / 2.0
    _require(frame > 0.0, "derived board frame is not positive")
    board = derived["simulation_estimates"]["board"]
    prior_center = list(board["center_in_table_frame_xy_m"])
    prior_yaw = float(board["yaw_relative_to_table_degrees"])
    board["side_m"] = playing
    board["frame_width_m"] = frame
    board["thickness_m"] = float(
        board_measurement["thickness_source"]["value_m"]
    )
    board["confidence"] = (
        "owner_reported_square_and_outside_board_static_metrology"
    )
    derived["simulation_estimates"]["piece_geometry"] = {
        "detailed_pawn_height_m": float(
            measurement["pawn"]["height"]["value_m"]
        ),
        "horizontal_profile_source": "unchanged_predecessor_geometry",
        "confidence": "owner_reported_height_only",
    }
    derived["metrology_lineage"] = {
        **derived.get("metrology_lineage", {}),
        "geometry_successor": contract["experiment_id"],
        "board_square_side_m": square,
        "pawn_height_m": float(measurement["pawn"]["height"]["value_m"]),
        "camera_not_yet_applied": True,
    }
    border_residual = frame - float(
        board_measurement["border_each_side"]["value_m"]
    )
    geometry_result = {
        "outside_side_m": outside,
        "square_side_m": square,
        "playing_side_m": playing,
        "frame_width_m": frame,
        "reported_border_each_side_m": float(
            board_measurement["border_each_side"]["value_m"]
        ),
        "border_diagnostic_residual_m": border_residual,
        "border_consistency_gate_passed": abs(border_residual)
        <= float(policy["maximum_border_diagnostic_residual_m"]),
        "pawn_height_m": float(measurement["pawn"]["height"]["value_m"]),
        "prior_playing_side_m": float(base_scene["simulation_estimates"]["board"]["side_m"]),
        "prior_square_side_m": float(
            base_scene["simulation_estimates"]["board"]["side_m"]
        )
        / 8.0,
        "prior_pawn_height_m": 0.0532,
        "board_center_unchanged": list(board["center_in_table_frame_xy_m"])
        == prior_center,
        "board_yaw_unchanged": math.isclose(
            float(board["yaw_relative_to_table_degrees"]),
            prior_yaw,
            abs_tol=1e-12,
        ),
        "pawn_horizontal_profile_changed": False,
    }
    return derived, geometry_result


def _candidate_spec(
    scene_path: Path,
    *,
    pawn_height_m: float,
    workcell_camera: dict[str, Any] | None = None,
) -> mujoco.MjSpec:
    _require(pawn_height_m > 0.0, "pawn height must be positive")
    spec = build_scene_spec(
        config_path=scene_path,
        external_root=DEFAULT_EXTERNAL_ROOT,
        piece_layout=CURRENT_TASK_PIECE_LAYOUT,
    )
    z_scale = pawn_height_m / PRIOR_DETAILED_PAWN_HEIGHT_M
    pawn_body_count = 0
    for body in spec.bodies:
        if "_pawn_" not in body.name:
            continue
        pawn_body_count += 1
        for geom in body.geoms:
            geom.pos[2] = float(geom.pos[2]) * z_scale
            if geom.type == mujoco.mjtGeom.mjGEOM_CYLINDER:
                geom.size[1] = float(geom.size[1]) * z_scale
            elif geom.type == mujoco.mjtGeom.mjGEOM_ELLIPSOID:
                geom.size[2] = float(geom.size[2]) * z_scale
            elif geom.type == mujoco.mjtGeom.mjGEOM_SPHERE:
                radius = float(geom.size[0])
                geom.type = mujoco.mjtGeom.mjGEOM_ELLIPSOID
                geom.size = [radius, radius, radius * z_scale]
            else:
                raise FactoryArtifactError(
                    "unexpected detailed pawn geometry type"
                )
    _require(pawn_body_count == 16, "detailed pawn body count changed")
    if workcell_camera is not None:
        camera = spec.camera("workcell")
        _require(camera is not None, "workcell camera is missing")
        world_to_camera = np.asarray(
            workcell_camera["rotation_world_to_camera_cv"],
            dtype=np.float64,
        )
        camera_cv_to_world = world_to_camera.T
        camera_mujoco_to_world = camera_cv_to_world @ np.diag(
            [1.0, -1.0, -1.0]
        )
        quaternion_xyzw = Rotation.from_matrix(
            camera_mujoco_to_world
        ).as_quat()
        camera.pos = [
            float(value)
            for value in workcell_camera["position_world_xyz_m"]
        ]
        camera.quat = [
            float(quaternion_xyzw[3]),
            float(quaternion_xyzw[0]),
            float(quaternion_xyzw[1]),
            float(quaternion_xyzw[2]),
        ]
        camera.mode = mujoco.mjtCamLight.mjCAMLIGHT_FIXED
        camera.targetbody = ""
        camera.fovy = float(workcell_camera["vertical_fov_degrees"])
    return spec


def build_geometry_camera_model(scene_path: Path) -> mujoco.MjModel:
    """Compile a generated v2 scene with its bounded pawn and camera overrides."""

    scene = load_json_object(scene_path, label="geometry/camera derived scene")
    piece_geometry = scene["simulation_estimates"].get("piece_geometry")
    camera = scene["simulation_estimates"].get("workcell_camera")
    _require(isinstance(piece_geometry, dict), "piece geometry is missing")
    _require(isinstance(camera, dict), "workcell camera candidate is missing")
    return _candidate_spec(
        scene_path,
        pawn_height_m=float(piece_geometry["detailed_pawn_height_m"]),
        workcell_camera=camera,
    ).compile()


def _compiled_pawn_height(
    scene_path: Path, *, expected_height_m: float
) -> dict[str, Any]:
    model = _candidate_spec(
        scene_path, pawn_height_m=expected_height_m
    ).compile()
    body_id = int(
        mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_BODY, "brown_pawn_d1"
        )
    )
    _require(body_id >= 0, "selected pawn body is missing")
    low = math.inf
    high = -math.inf
    count = 0
    for geom_id in range(model.ngeom):
        if int(model.geom_bodyid[geom_id]) != body_id:
            continue
        center_z = float(model.geom_pos[geom_id, 2])
        geom_type = int(model.geom_type[geom_id])
        if geom_type == int(mujoco.mjtGeom.mjGEOM_CYLINDER):
            half_z = float(model.geom_size[geom_id, 1])
        elif geom_type == int(mujoco.mjtGeom.mjGEOM_ELLIPSOID):
            half_z = float(model.geom_size[geom_id, 2])
        elif geom_type == int(mujoco.mjtGeom.mjGEOM_SPHERE):
            half_z = float(model.geom_size[geom_id, 0])
        else:
            raise FactoryArtifactError("unexpected detailed pawn geometry type")
        low = min(low, center_z - half_z)
        high = max(high, center_z + half_z)
        count += 1
    _require(count > 0, "selected pawn has no collision geometry")
    compiled = high - low
    return {
        "body": "brown_pawn_d1",
        "geom_count": count,
        "minimum_local_z_m": low,
        "maximum_local_z_m": high,
        "compiled_height_m": compiled,
        "expected_height_m": expected_height_m,
        "absolute_error_m": abs(compiled - expected_height_m),
    }


def _contact_phase_candidate(
    *,
    contract: dict[str, Any],
    scene_path: Path,
    pawn_height_m: float,
    board_thickness_m: float,
    root: Path,
    joint_zero_overrides: dict[int, float] | None = None,
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
    candidate = copy.deepcopy(candidate_manifest["candidate_config"])
    _require(
        canonical_digest(candidate)
        == contract["sources"]["or6_candidate"]["candidate_config_sha256"],
        "OR6 candidate identity changed",
    )
    if joint_zero_overrides:
        joints = candidate["physical_adapter"]["joint_transform"]["joints"]
        for index, value in joint_zero_overrides.items():
            _require(index in range(5), "only frozen body-joint offsets are allowed")
            joints[index]["zero_offset"] = float(value)
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
    model = _candidate_spec(
        scene_path, pawn_height_m=pawn_height_m
    ).compile()
    baseline_scene = _bound_json(
        contract["sources"]["baseline_scene"],
        root=root,
        label="baseline scene",
    )
    thickness_delta = board_thickness_m - float(
        baseline_scene["simulation_estimates"]["board"]["thickness_m"]
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
    fixed_tip = np.asarray(
        sample_last["fixed_tip_center_m"], dtype=np.float64
    )
    moving_tip = np.asarray(
        sample_last["moving_tip_center_m"], dtype=np.float64
    )
    pawn_center = np.asarray(sample_last["pawn_center_m"], dtype=np.float64)
    midpoint = (fixed_tip + moving_tip) / 2.0
    delta = pawn_center - midpoint
    phase = {
        "support_z_m": support_z,
        "trace_row_count": len(rows),
        "physics_integration_steps": 0,
        "first_named_contact_source_sample": (
            int(first_named["source_sample_index"])
            if first_named is not None
            else None
        ),
        "contact_at_expected_phase": first_named is not None,
        "minimum_phase_fixed_jaw_gap_m": min(
            float(row["fixed"]["signed_distance_m"]) for row in phase_rows
        ),
        "minimum_phase_moving_jaw_gap_m": min(
            float(row["moving"]["signed_distance_m"]) for row in phase_rows
        ),
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
            "jaw_midpoint_m": midpoint.tolist(),
            "pawn_center_m": pawn_center.tolist(),
            "midpoint_to_pawn_vector_m": delta.tolist(),
            "midpoint_to_pawn_planar_distance_m": float(
                np.linalg.norm(delta[:2])
            ),
            "midpoint_to_pawn_distance_m": float(np.linalg.norm(delta)),
        },
        "dynamic_replays": 0,
        "dynamics_authorized": False,
    }
    return phase, {"schema_version": TRACE_SCHEMA, "rows": rows}


def _solve_camera_center(
    measurement: dict[str, Any],
    *,
    outside_side_m: float,
    playing_side_m: float,
) -> dict[str, Any]:
    camera = measurement["logitech_camera"]
    board = measurement["board"]
    lens_height = float(camera["lens_height_above_desk"]["value_m"])
    board_thickness = float(board["thickness_source"]["value_m"])
    vertical = lens_height - board_thickness
    left_ray = float(
        camera["ray_distance_to_front_left_outer_corner"]["value_m"]
    )
    right_ray = float(
        camera["ray_distance_to_front_right_outer_corner"]["value_m"]
    )
    _require(
        vertical > 0.0 and left_ray > vertical and right_ray > vertical,
        "camera ranges cannot intersect the board-top plane",
    )
    left_planar = math.sqrt(left_ray**2 - vertical**2)
    right_planar = math.sqrt(right_ray**2 - vertical**2)
    centered_x = (
        left_planar**2 - right_planar**2
    ) / (2.0 * outside_side_m)
    y_squared = left_planar**2 - (
        centered_x + outside_side_m / 2.0
    ) ** 2
    _require(y_squared > 0.0, "camera corner ranges do not intersect")
    centered_y = math.sqrt(y_squared)
    planar_reported = float(
        camera["planar_distance_to_board_column"]["value_m"]
    )
    planar_residual = centered_y - planar_reported
    center_playing_origin = np.asarray(
        [
            centered_x + playing_side_m / 2.0,
            centered_y + playing_side_m / 2.0,
            -vertical,
        ],
        dtype=np.float64,
    )

    input_values = np.asarray(
        [lens_height, board_thickness, left_ray, right_ray],
        dtype=np.float64,
    )
    input_sigmas = np.asarray(
        [
            camera["lens_height_above_desk"]["uncertainty_m"],
            board["thickness_source"]["uncertainty_m"],
            camera["ray_distance_to_front_left_outer_corner"]["uncertainty_m"],
            camera["ray_distance_to_front_right_outer_corner"]["uncertainty_m"],
        ],
        dtype=np.float64,
    )

    def solve(values: np.ndarray) -> np.ndarray:
        height, thickness, left, right = values
        dz = height - thickness
        left_xy = math.sqrt(left**2 - dz**2)
        right_xy = math.sqrt(right**2 - dz**2)
        x = (left_xy**2 - right_xy**2) / (2.0 * outside_side_m)
        y = math.sqrt(left_xy**2 - (x + outside_side_m / 2.0) ** 2)
        return np.asarray([x, y, height], dtype=np.float64)

    jacobian = np.zeros((3, 4), dtype=np.float64)
    for index in range(4):
        step = max(1e-7, input_sigmas[index] * 1e-3)
        plus = input_values.copy()
        minus = input_values.copy()
        plus[index] += step
        minus[index] -= step
        jacobian[:, index] = (solve(plus) - solve(minus)) / (2.0 * step)
    covariance = jacobian @ np.diag(input_sigmas**2) @ jacobian.T
    standard_uncertainty = np.sqrt(np.diag(covariance))
    return {
        "lens_height_above_desk_m": lens_height,
        "board_top_above_desk_m": board_thickness,
        "vertical_lens_to_board_top_m": vertical,
        "left_corner_ray_m": left_ray,
        "right_corner_ray_m": right_ray,
        "left_corner_planar_m": left_planar,
        "right_corner_planar_m": right_planar,
        "centered_outer_board_xy_m": [centered_x, centered_y],
        "center_in_playing_origin_board_xyz_m": center_playing_origin.tolist(),
        "reported_planar_distance_m": planar_reported,
        "derived_planar_distance_m": centered_y,
        "planar_distance_residual_m": planar_residual,
        "standard_uncertainty_centered_xyz_m": standard_uncertainty.tolist(),
        "maximum_standard_uncertainty_m": float(np.max(standard_uncertainty)),
    }


def _project_fixed_center(
    object_points: np.ndarray,
    values: np.ndarray,
    *,
    camera_center_board: np.ndarray,
    principal_point: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    rotation, _ = cv2.Rodrigues(
        np.asarray(values[1:4], dtype=np.float64)
    )
    translation = -rotation @ camera_center_board
    camera_points = object_points @ rotation.T + translation
    projected = (
        camera_points[:, :2]
        / camera_points[:, 2:3]
        * float(values[0])
        + principal_point
    )
    return projected, camera_points[:, 2]


def _fit_fixed_center_camera(
    board_xy: np.ndarray,
    image_points: np.ndarray,
    *,
    camera_center_board: np.ndarray,
    initial_values: np.ndarray,
    contract: dict[str, Any],
) -> dict[str, Any]:
    policy = contract["retained_pixel_orientation_diagnostic"]
    object_points = np.column_stack(
        (np.asarray(board_xy, dtype=np.float64), np.zeros(len(board_xy)))
    )
    image = np.asarray(image_points, dtype=np.float64)
    principal = np.asarray(policy["principal_point_px"], dtype=np.float64)

    def residual(values: np.ndarray) -> np.ndarray:
        projected, _ = _project_fixed_center(
            object_points,
            values,
            camera_center_board=camera_center_board,
            principal_point=principal,
        )
        return (projected - image).ravel()

    fit = least_squares(
        residual,
        np.asarray(initial_values, dtype=np.float64),
        bounds=(
            np.asarray(
                [float(policy["minimum_focal_px"]), -10.0, -10.0, -10.0]
            ),
            np.asarray(
                [float(policy["maximum_focal_px"]), 10.0, 10.0, 10.0]
            ),
        ),
        x_scale="jac",
        max_nfev=20_000,
        ftol=1e-13,
        xtol=1e-13,
        gtol=1e-13,
    )
    _require(bool(fit.success), "fixed-center camera fit did not converge")
    projected, depths = _project_fixed_center(
        object_points,
        fit.x,
        camera_center_board=camera_center_board,
        principal_point=principal,
    )
    errors = np.linalg.norm(projected - image, axis=1)
    singular = np.linalg.svd(fit.jac, compute_uv=False)
    return {
        "focal_px": float(fit.x[0]),
        "rotation_vector_board_to_camera": fit.x[1:4].tolist(),
        "parameter_values": fit.x.tolist(),
        "reprojection_errors_px": errors.tolist(),
        "reprojection_rms_px": float(np.sqrt(np.mean(errors**2))),
        "reprojection_max_px": float(np.max(errors)),
        "positive_depth_fraction": float(np.mean(depths > 0.0)),
        "minimum_depth_m": float(np.min(depths)),
        "solver": {
            "jacobian_rank": int(np.linalg.matrix_rank(fit.jac)),
            "jacobian_condition_number": float(singular[0] / singular[-1]),
            "active_mask": fit.active_mask.tolist(),
        },
    }


def _evaluate_fixed_center_camera(
    fit: dict[str, Any],
    board_xy: np.ndarray,
    image_points: np.ndarray,
    *,
    camera_center_board: np.ndarray,
    principal_point: np.ndarray,
) -> dict[str, Any]:
    object_points = np.column_stack(
        (np.asarray(board_xy, dtype=np.float64), np.zeros(len(board_xy)))
    )
    projected, depths = _project_fixed_center(
        object_points,
        np.asarray(fit["parameter_values"], dtype=np.float64),
        camera_center_board=camera_center_board,
        principal_point=principal_point,
    )
    errors = np.linalg.norm(
        projected - np.asarray(image_points, dtype=np.float64), axis=1
    )
    return {
        "reprojection_errors_px": errors.tolist(),
        "reprojection_rms_px": float(np.sqrt(np.mean(errors**2))),
        "reprojection_max_px": float(np.max(errors)),
        "positive_depth_fraction": float(np.mean(depths > 0.0)),
    }


def _camera_diagnostic(
    scene: dict[str, Any],
    measurement: dict[str, Any],
    contract: dict[str, Any],
    *,
    root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    geometry = scene_geometry(scene)
    outside = geometry.board_total_side
    playing = geometry.board_side
    center = _solve_camera_center(
        measurement,
        outside_side_m=outside,
        playing_side_m=playing,
    )
    gate = contract["camera_center_fit"]
    center["planar_consistency_gate_passed"] = bool(
        abs(float(center["planar_distance_residual_m"]))
        <= float(gate["maximum_planar_distance_consistency_residual_m"])
    )
    or10 = _bound_json(
        contract["sources"]["or10_receipt"], root=root, label="OR10 receipt"
    )
    cohort_ids = ["registration_fit_v3", "registration_fit_v4"]
    cohort_maps = {
        cohort_id: {
            tuple(item["index"]): item
            for item in or10["cohort_observations"][cohort_id]
        }
        for cohort_id in cohort_ids
    }
    overlap = [
        tuple(item)
        for item in or10["cross_cohort_agreement"][
            "overlap_intersection_indices"
        ]
    ]
    board_xy = np.asarray(overlap, dtype=np.float64) / 8.0 * playing
    first_points = np.asarray(
        [
            cohort_maps[cohort_ids[0]][index]["image_point_px"]
            for index in overlap
        ],
        dtype=np.float64,
    )
    second_points = np.asarray(
        [
            cohort_maps[cohort_ids[1]][index]["image_point_px"]
            for index in overlap
        ],
        dtype=np.float64,
    )
    prior = or10["pooled_board_plane_candidate"]
    initial = np.asarray(
        [prior["focal_px"], *prior["rotation_vector"]], dtype=np.float64
    )
    camera_center_board = np.asarray(
        center["center_in_playing_origin_board_xyz_m"], dtype=np.float64
    )
    fit_first = _fit_fixed_center_camera(
        board_xy,
        first_points,
        camera_center_board=camera_center_board,
        initial_values=initial,
        contract=contract,
    )
    fit_second = _fit_fixed_center_camera(
        board_xy,
        second_points,
        camera_center_board=camera_center_board,
        initial_values=initial,
        contract=contract,
    )
    pooled = _fit_fixed_center_camera(
        board_xy,
        (first_points + second_points) / 2.0,
        camera_center_board=camera_center_board,
        initial_values=initial,
        contract=contract,
    )
    principal = np.asarray(
        contract["retained_pixel_orientation_diagnostic"][
            "principal_point_px"
        ],
        dtype=np.float64,
    )
    validate_second = _evaluate_fixed_center_camera(
        fit_first,
        board_xy,
        second_points,
        camera_center_board=camera_center_board,
        principal_point=principal,
    )
    validate_first = _evaluate_fixed_center_camera(
        fit_second,
        board_xy,
        first_points,
        camera_center_board=camera_center_board,
        principal_point=principal,
    )
    mean_validation = float(
        np.mean(
            [
                validate_second["reprojection_rms_px"],
                validate_first["reprojection_rms_px"],
            ]
        )
    )
    orientation_policy = contract["retained_pixel_orientation_diagnostic"]
    orientation_gate = bool(
        mean_validation
        <= float(orientation_policy["maximum_cross_cohort_validation_rms_px"])
        and fit_first["positive_depth_fraction"] == 1.0
        and fit_second["positive_depth_fraction"] == 1.0
    )

    or1 = _bound_json(
        contract["sources"]["or1_receipt"], root=root, label="OR1 receipt"
    )
    board_to_world = np.asarray(
        or1["fit"]["board_frame"]["rotation_board_to_world"],
        dtype=np.float64,
    )
    board_center_world = np.asarray(
        [
            geometry.board_center[0],
            geometry.board_center[1],
            geometry.table_top + geometry.board_thickness,
        ],
        dtype=np.float64,
    )
    board_origin_world = (
        board_center_world
        - board_to_world[:, 0] * (playing / 2.0)
        - board_to_world[:, 1] * (playing / 2.0)
    )
    camera_position_world = (
        board_origin_world + board_to_world @ camera_center_board
    )
    board_to_camera, _ = cv2.Rodrigues(
        np.asarray(
            pooled["rotation_vector_board_to_camera"], dtype=np.float64
        )
    )
    world_to_camera = board_to_camera @ board_to_world.T
    world_translation = -world_to_camera @ camera_position_world
    vertical_fov = math.degrees(
        2.0 * math.atan(480.0 / (2.0 * float(pooled["focal_px"])))
    )
    camera_scene = copy.deepcopy(scene)
    camera_scene["simulation_estimates"]["workcell_camera"] = {
        "camera_id": "post_hackathon_logitech_c922_manual_center_v1",
        "position_world_xyz_m": camera_position_world.tolist(),
        "rotation_world_to_camera_cv": world_to_camera.tolist(),
        "translation_world_to_camera_cv_m": world_translation.tolist(),
        "vertical_fov_degrees": vertical_fov,
        "image_size_px": [640, 480],
        "position_source": "owner_reported_manual_height_and_corner_ranges",
        "orientation_source": "retrospective_or10_cross_cohort_board_pixels_with_center_fixed",
        "canonical_replacement_authority": False,
    }
    camera_scene["metrology_lineage"] = {
        **camera_scene.get("metrology_lineage", {}),
        "camera_not_yet_applied": False,
        "camera_center_measurement_id": measurement["measurement_id"],
        "camera_orientation_exact_intrinsics_approved": False,
    }
    result = {
        "center": center,
        "retained_pixel_orientation": {
            "overlap_intersection_count": len(overlap),
            "playing_side_m": playing,
            "camera_center_fixed": True,
            "principal_point_px": principal.tolist(),
            "distortion_terms": 0,
            "fit_first": fit_first,
            "validate_second": validate_second,
            "fit_second": fit_second,
            "validate_first": validate_first,
            "mean_cross_cohort_validation_rms_px": mean_validation,
            "pooled_fit": pooled,
            "vertical_fov_degrees": vertical_fov,
            "orientation_diagnostic_gate_passed": orientation_gate,
            "retrospective_nonheldout": True,
            "exact_intrinsics_approved": False,
        },
        "world_pose": {
            "board_origin_world_m": board_origin_world.tolist(),
            "camera_position_world_m": camera_position_world.tolist(),
            "rotation_world_to_camera_cv": world_to_camera.tolist(),
            "translation_world_to_camera_cv_m": world_translation.tolist(),
            "height_above_desk_m": float(
                camera_position_world[2] - geometry.table_top
            ),
        },
    }
    return camera_scene, result


def build_geometry_camera_receipt(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract, measurement = load_geometry_camera_contract(
        contract_path, root=root
    )
    or12_scene = _bound_json(
        contract["sources"]["or12_derived_scene"],
        root=root,
        label="OR12 derived scene",
    )
    or12_receipt = _bound_json(
        contract["sources"]["or12_receipt"], root=root, label="OR12 receipt"
    )
    board_scene, board_object = _board_object_scene(
        or12_scene, measurement, contract
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    board_scene_path = output_directory / "board_object_scene_config.json"
    trace_path = output_directory / "contact_phase_trace.json"
    derived_scene_path = output_directory / "derived_scene_config.json"
    receipt_path = output_directory / "receipt.json"
    atomic_write_json(board_scene_path, board_scene)
    compiled_pawn = _compiled_pawn_height(
        board_scene_path,
        expected_height_m=float(measurement["pawn"]["height"]["value_m"]),
    )
    compiled_pawn["height_gate_passed"] = bool(
        compiled_pawn["absolute_error_m"]
        <= float(
            contract["board_object_geometry"][
                "maximum_compiled_pawn_height_error_m"
            ]
        )
    )
    pawn_height_m = float(measurement["pawn"]["height"]["value_m"])
    board_thickness_m = float(
        measurement["board"]["thickness_source"]["value_m"]
    )
    phase, trace = _contact_phase_candidate(
        contract=contract,
        scene_path=board_scene_path,
        pawn_height_m=pawn_height_m,
        board_thickness_m=board_thickness_m,
        root=root,
    )
    atomic_write_json(
        trace_path, {"schema_version": TRACE_SCHEMA, "rows": trace["rows"]}
    )
    camera_scene, camera = _camera_diagnostic(
        board_scene, measurement, contract, root=root
    )
    atomic_write_json(derived_scene_path, camera_scene)
    model = _candidate_spec(
        derived_scene_path,
        pawn_height_m=pawn_height_m,
        workcell_camera=camera_scene["simulation_estimates"][
            "workcell_camera"
        ],
    ).compile()
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    camera_id = int(
        mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_CAMERA, "workcell"
        )
    )
    _require(camera_id >= 0, "derived workcell camera is missing")
    compiled_position = np.asarray(data.cam_xpos[camera_id], dtype=np.float64)
    requested_position = np.asarray(
        camera["world_pose"]["camera_position_world_m"], dtype=np.float64
    )
    camera["compiled_scene"] = {
        "camera_id": camera_id,
        "position_world_m": compiled_position.tolist(),
        "position_error_m": float(
            np.linalg.norm(compiled_position - requested_position)
        ),
        "vertical_fov_degrees": float(model.cam_fovy[camera_id]),
        "pose_gate_passed": bool(
            np.linalg.norm(compiled_position - requested_position) <= 1e-9
        ),
    }
    prior_sample = or12_receipt["contact_phase"]["sample_232"]
    current_sample = phase["sample_232"]
    board_object["compiled_pawn"] = compiled_pawn
    board_object["contact_phase_comparison"] = {
        "prior_fixed_jaw_gap_m": float(prior_sample["fixed_signed_distance_m"]),
        "current_fixed_jaw_gap_m": float(
            current_sample["fixed_signed_distance_m"]
        ),
        "fixed_jaw_gap_delta_m": float(
            current_sample["fixed_signed_distance_m"]
            - prior_sample["fixed_signed_distance_m"]
        ),
        "prior_planar_midpoint_error_m": float(
            prior_sample["midpoint_to_pawn_planar_distance_m"]
        ),
        "current_planar_midpoint_error_m": float(
            current_sample["midpoint_to_pawn_planar_distance_m"]
        ),
        "planar_midpoint_error_delta_m": float(
            current_sample["midpoint_to_pawn_planar_distance_m"]
            - prior_sample["midpoint_to_pawn_planar_distance_m"]
        ),
        "named_contact": bool(phase["contact_at_expected_phase"]),
        "physics_integration_steps": 0,
        "dynamic_replays": 0,
    }
    all_static_gates = bool(
        board_object["border_consistency_gate_passed"]
        and compiled_pawn["height_gate_passed"]
        and camera["center"]["planar_consistency_gate_passed"]
        and camera["retained_pixel_orientation"][
            "orientation_diagnostic_gate_passed"
        ]
        and camera["compiled_scene"]["pose_gate_passed"]
    )
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "contract_sha256": (
            sha256_file(contract_path)
            if contract_path.is_file()
            else canonical_digest(contract)
        ),
        "measurement_sha256": contract["sources"]["measurement"]["sha256"],
        "proof_class": contract["proof_class"],
        "stage_order": contract["stage_order"],
        "board_object_geometry": board_object,
        "contact_phase": phase,
        "camera": camera,
        "all_static_gates_passed": all_static_gates,
        "result": (
            "STATIC_GEOMETRY_AND_CAMERA_CENTER_CANDIDATE_PASS_NO_CONTACT_NO_GLOBAL_MAPPING"
            if all_static_gates
            else "STATIC_GEOMETRY_OR_CAMERA_DIAGNOSTIC_GATE_FAILED"
        ),
        "generated": {
            "board_object_scene_config": (
                str(board_scene_path.relative_to(root))
                if board_scene_path.is_relative_to(root)
                else str(board_scene_path)
            ),
            "derived_scene_config": (
                str(derived_scene_path.relative_to(root))
                if derived_scene_path.is_relative_to(root)
                else str(derived_scene_path)
            ),
            "contact_phase_trace": (
                str(trace_path.relative_to(root))
                if trace_path.is_relative_to(root)
                else str(trace_path)
            ),
        },
        "decision": {
            "board_playing_scale_candidate_admitted": bool(
                board_object["border_consistency_gate_passed"]
            ),
            "pawn_height_candidate_admitted": bool(
                compiled_pawn["height_gate_passed"]
            ),
            "camera_center_candidate_admitted": bool(
                camera["center"]["planar_consistency_gate_passed"]
            ),
            "camera_orientation_diagnostic_admitted": bool(
                camera["retained_pixel_orientation"][
                    "orientation_diagnostic_gate_passed"
                ]
            ),
            "canonical_scene_replaced": False,
            "global_mapping_approved": False,
            "dynamic_replay_authorized": False,
        },
        "limitations": [
            "The camera center uses single-pass rough manual ranges with declared uncertainty.",
            "Camera orientation and focal length use retrospective nonheldout board pixels and cannot approve exact intrinsics.",
            "Pawn width and horizontal profile were not measured and remain unchanged.",
            "No camera, robot, task outcome, heldout set, physics integration, or hardware was opened.",
        ],
        "authority": contract["authority"],
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(receipt_path, receipt)
    return receipt


__all__ = [
    "CONTRACT_PATH",
    "OUTPUT_DIRECTORY",
    "build_geometry_camera_model",
    "build_geometry_camera_receipt",
    "load_geometry_camera_contract",
]

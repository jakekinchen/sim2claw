#!/usr/bin/env python3
"""Attempt an automatic J/S/K/L-only fixed-base CAD camera anchor.

The builder deliberately separates three things:

* a frozen static edge consensus derived only from J/S/K/L;
* an exact ``left_base`` CAD edge-cloud fit against that consensus; and
* a fail-closed promotion decision with translation controls and multi-start
  ambiguity checks.

The fit may produce a useful diagnostic camera even when it cannot promote an
anchor.  A camera candidate is emitted only when every preregistered base gate
passes.  No held-out frame is opened and this module contains no hardware path.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

import cv2
import mujoco
import numpy as np
from scipy.ndimage import map_coordinates
from scipy.optimize import least_squares
from scipy.spatial import ConvexHull
from scipy.spatial.transform import Rotation

from sim2claw.physical_canary import _physical_to_model_position
from sim2claw.recorded_replay import _compile_model
from tools.evaluate_current_pi_cad_keyed_joint_mapping import (
    CadMappingEvaluationError,
    _bound,
    _json,
    canonical_sha256,
    inspect_full_cad,
    load_contract,
    load_fit_poses,
    sha256_file,
)
from tools.fit_pi_dual_link_tag_bundle import Bundle, transform


SPEC_SCHEMA = "sim2claw.current_pi_fixed_base_cad_anchor_spec.v1"
RESULT_SCHEMA = "sim2claw.current_pi_fixed_base_cad_anchor_result.v1"
FIT_POSES = ("J", "S", "K", "L")
IMAGE_WIDTH = 1536
IMAGE_HEIGHT = 864
TAG_IDS_WITH_FROZEN_MOUNTS = (0, 1, 2)


class AnchorBuildError(RuntimeError):
    """The frozen anchor inputs or algorithm contract changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AnchorBuildError(message)


def _iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for nested in value.values():
            yield from _iter_strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _iter_strings(nested)


def validate_spec(spec: dict[str, Any]) -> None:
    _require(
        spec.get("schema_version") == SPEC_SCHEMA,
        "unexpected fixed-base anchor specification",
    )
    _require(
        spec.get("status") == "frozen_J_S_K_L_only_before_automatic_fit",
        "anchor attempt was not frozen as J/S/K/L-only",
    )
    _require(
        spec.get("fit_poses") == list(FIT_POSES),
        "fixed-base fit pose split changed",
    )
    binding = spec.get("mapping_contract") or {}
    _require(
        isinstance(binding.get("path"), str)
        and isinstance(binding.get("sha256"), str)
        and len(binding["sha256"]) == 64,
        "mapping contract binding is incomplete",
    )
    roi = spec.get("admissible_roi")
    algorithm = spec.get("algorithm")
    _require(isinstance(roi, dict), "admissible ROI is absent")
    _require(isinstance(algorithm, dict), "algorithm is absent")
    _require(
        canonical_sha256(roi) == spec.get("admissible_roi_sha256"),
        "admissible ROI hash changed",
    )
    _require(
        canonical_sha256(algorithm) == spec.get("algorithm_sha256"),
        "algorithm hash changed",
    )
    bounds = [
        roi.get("x_min"),
        roi.get("y_min"),
        roi.get("x_max_exclusive"),
        roi.get("y_max_exclusive"),
    ]
    _require(
        bounds == [450, 560, 920, 864],
        "admissible fixed-base ROI changed",
    )
    camera_fit = algorithm.get("camera_fit") or {}
    starts = camera_fit.get("deterministic_start_deltas")
    _require(
        isinstance(starts, list)
        and len(starts) >= 3
        and all(
            isinstance(row, list)
            and len(row) == 6
            and np.isfinite(row).all()
            for row in starts
        ),
        "camera multi-start schedule is invalid",
    )
    authority = spec.get("authority") or {}
    _require(
        authority.get("hardware_motion") is False
        and authority.get("simulator_parameter_promotion") is False
        and authority.get("physical_task") is False
        and authority.get("policy") is False,
        "anchor authority widened",
    )
    forbidden_fragments = (
        "/pose-m-",
        "pose_m",
        "fresh_validation_packet",
        "fresh_validation_route",
    )
    # The bound mapping contract itself predates this attempt and contains the
    # held-out split.  No other specification string may address that split.
    for value in _iter_strings(
        {
            key: nested
            for key, nested in spec.items()
            if key != "mapping_contract"
        }
    ):
        lowered = value.lower()
        _require(
            not any(fragment in lowered for fragment in forbidden_fragments),
            "anchor specification references held-out data",
        )


def load_spec(path: Path) -> dict[str, Any]:
    value = _json(path, "fixed-base anchor specification")
    try:
        validate_spec(value)
    except CadMappingEvaluationError as error:
        raise AnchorBuildError(str(error)) from error
    return value


def _camera_matrix(focal: float) -> np.ndarray:
    return np.asarray(
        [
            [focal, 0.0, IMAGE_WIDTH / 2.0],
            [0.0, focal, IMAGE_HEIGHT / 2.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def _project(
    points_world: np.ndarray,
    camera_vector: np.ndarray,
    focal: float,
) -> tuple[np.ndarray, np.ndarray]:
    camera_world = transform(camera_vector[:3], camera_vector[3:6])
    homogeneous = np.column_stack(
        [points_world, np.ones(len(points_world), dtype=np.float64)]
    )
    camera = (camera_world @ homogeneous.T)[:3].T
    valid_depth = camera[:, 2] > 1e-5
    pixels = np.full((len(points_world), 2), np.nan, dtype=np.float64)
    pixels[valid_depth] = (
        focal * camera[valid_depth, :2] / camera[valid_depth, 2:3]
        + np.asarray([IMAGE_WIDTH / 2.0, IMAGE_HEIGHT / 2.0])
    )
    return pixels, valid_depth


def _tag_seed(
    poses: dict[str, dict[str, Any]],
    initialization: dict[str, Any],
    focal: float,
    algorithm: dict[str, Any],
) -> tuple[np.ndarray, dict[str, Any]]:
    parameters = initialization.get("parameters") or {}
    mounts = parameters.get("tag_mounts") or {}
    tags = initialization.get("tag_model", {}).get("tags", {})
    _require(
        sorted(int(tag_id) for tag_id in mounts)
        == list(TAG_IDS_WITH_FROZEN_MOUNTS),
        "camera initialization lacks frozen mounts for tags 0, 1, and 2",
    )
    bundle = Bundle()
    bundle.set_focal(focal)
    for tag_id in TAG_IDS_WITH_FROZEN_MOUNTS:
        body_name = tags[str(tag_id)]["body"]
        bundle.body_ids[body_name] = mujoco.mj_name2id(
            bundle.model, mujoco.mjtObj.mjOBJ_BODY, body_name
        )
    rows: list[dict[str, Any]] = []
    for pose_name in FIT_POSES:
        pose = poses[pose_name]
        for tag_id in TAG_IDS_WITH_FROZEN_MOUNTS:
            tag = pose["detected_tags"].get(str(tag_id))
            if tag is None:
                continue
            rows.append(
                {
                    "pose": pose_name,
                    "tag_id": tag_id,
                    "body": tags[str(tag_id)]["body"],
                    "joints": np.asarray(
                        pose["final_actual_degrees"], dtype=np.float64
                    ),
                    "corners": np.asarray(
                        tag["corners_pixels"], dtype=np.float64
                    ),
                }
            )
    _require(
        len(rows) >= 5
        and sorted({row["tag_id"] for row in rows})
        == list(TAG_IDS_WITH_FROZEN_MOUNTS),
        "J/S/K/L do not cover the three frozen tag mounts",
    )
    start = np.asarray(
        parameters["camera_world_rotation_vector_radians"]
        + parameters["camera_world_translation_m"],
        dtype=np.float64,
    )
    tag_points = bundle.tag_points
    zero_offsets = np.zeros(5, dtype=np.float64)

    def projected(vector: np.ndarray, row: dict[str, Any]) -> np.ndarray:
        mount = mounts[str(row["tag_id"])]
        camera_points = (
            transform(vector[:3], vector[3:6])
            @ bundle.body_pose(row["body"], row["joints"], zero_offsets)
            @ transform(
                np.asarray(
                    mount["body_tag_rotation_vector_radians"],
                    dtype=np.float64,
                ),
                np.asarray(
                    mount["body_tag_translation_m"], dtype=np.float64
                ),
            )
            @ tag_points
        )[:3]
        normalized = camera_points[:2] / camera_points[2:3]
        return np.column_stack(
            [
                focal * normalized[0] + IMAGE_WIDTH / 2.0,
                focal * normalized[1] + IMAGE_HEIGHT / 2.0,
            ]
        )

    def residual(vector: np.ndarray) -> np.ndarray:
        return np.concatenate(
            [
                (projected(vector, row) - row["corners"]).ravel()
                for row in rows
            ]
        )

    settings = algorithm["tag_camera_seed"]
    fit = least_squares(
        residual,
        start,
        bounds=(
            np.asarray([-math.pi] * 3 + [-3.0] * 3),
            np.asarray([math.pi] * 3 + [3.0] * 3),
        ),
        loss=settings["loss"],
        f_scale=float(settings["f_scale_px"]),
        max_nfev=int(settings["maximum_function_evaluations"]),
    )
    corner_errors = np.concatenate(
        [
            np.linalg.norm(projected(fit.x, row) - row["corners"], axis=1)
            for row in rows
        ]
    )
    return fit.x, {
        "role": "supplementary_initialization_only_not_base_evidence",
        "observation_count": len(rows),
        "corner_count": len(corner_errors),
        "fit_poses": list(FIT_POSES),
        "tag_ids": sorted({row["tag_id"] for row in rows}),
        "camera_vector": fit.x.tolist(),
        "corner_rmse_px": float(np.sqrt(np.mean(corner_errors**2))),
        "corner_median_px": float(np.median(corner_errors)),
        "corner_max_px": float(np.max(corner_errors)),
        "optimizer_success": bool(fit.success),
        "optimizer_message": fit.message,
    }


def _consensus_mask(
    poses: dict[str, dict[str, Any]],
    roi: dict[str, int],
    algorithm: dict[str, Any],
) -> tuple[np.ndarray, dict[str, Any]]:
    lower, upper = algorithm["canny_thresholds"]
    radius = int(algorithm["consensus_dilation_radius_px"])
    kernel = np.ones((2 * radius + 1, 2 * radius + 1), np.uint8)
    dilated: list[np.ndarray] = []
    frame_edge_counts: dict[str, int] = {}
    for name in FIT_POSES:
        image = cv2.imread(poses[name]["pi_image_path"])
        _require(
            image is not None and image.shape[:2] == (IMAGE_HEIGHT, IMAGE_WIDTH),
            f"pose {name} image became unreadable",
        )
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edge = cv2.Canny(gray, int(lower), int(upper))
        frame_edge_counts[name] = int(cv2.countNonZero(edge))
        dilated.append(cv2.dilate(edge, kernel))
    required = int(algorithm["consensus_minimum_pose_count"])
    consensus = (
        np.sum(np.stack(dilated) > 0, axis=0) >= required
    ).astype(np.uint8) * 255
    roi_mask = np.zeros_like(consensus)
    x0 = int(roi["x_min"])
    y0 = int(roi["y_min"])
    x1 = int(roi["x_max_exclusive"])
    y1 = int(roi["y_max_exclusive"])
    roi_mask[y0:y1, x0:x1] = consensus[y0:y1, x0:x1]
    return roi_mask, {
        "method": "dilated_Canny_static_pose_consensus_inside_frozen_ROI",
        "fit_poses": list(FIT_POSES),
        "canny_thresholds": [int(lower), int(upper)],
        "dilation_radius_px": radius,
        "minimum_pose_count": required,
        "per_frame_raw_edge_pixel_count": frame_edge_counts,
        "consensus_pixel_count_full_frame": int(cv2.countNonZero(consensus)),
        "consensus_pixel_count_inside_roi": int(cv2.countNonZero(roi_mask)),
    }


def _left_base_edge_cloud(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    samples_per_edge: int,
    maximum_sample_count: int,
) -> tuple[np.ndarray, list[dict[str, Any]], int]:
    mujoco.mj_forward(model, data)
    body_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, "left_base"
    )
    points: list[np.ndarray] = []
    inventory: list[dict[str, Any]] = []
    for geom_id in range(model.ngeom):
        if (
            int(model.geom_bodyid[geom_id]) != body_id
            or int(model.geom_group[geom_id]) != 2
            or int(model.geom_type[geom_id])
            != int(mujoco.mjtGeom.mjGEOM_MESH)
        ):
            continue
        mesh_id = int(model.geom_dataid[geom_id])
        start = int(model.mesh_vertadr[mesh_id])
        count = int(model.mesh_vertnum[mesh_id])
        local = np.asarray(
            model.mesh_vert[start : start + count], dtype=np.float64
        )
        world = (
            local @ data.geom_xmat[geom_id].reshape(3, 3).T
            + data.geom_xpos[geom_id]
        )
        hull = ConvexHull(world)
        edges = sorted(
            {
                tuple(sorted((int(face[a]), int(face[b]))))
                for face in hull.simplices
                for a, b in ((0, 1), (1, 2), (2, 0))
            }
        )
        t_values = np.linspace(0.0, 1.0, samples_per_edge)
        for first, second in edges:
            points.append(
                (1.0 - t_values[:, None]) * world[first]
                + t_values[:, None] * world[second]
            )
        inventory.append(
            {
                "geom_id": geom_id,
                "mesh_id": mesh_id,
                "mesh_name": mujoco.mj_id2name(
                    model, mujoco.mjtObj.mjOBJ_MESH, mesh_id
                ),
                "vertex_count": count,
                "convex_hull_edge_count": len(edges),
            }
        )
    _require(len(inventory) == 4, "expected four exact left_base visual meshes")
    cloud = np.concatenate(points)
    raw_count = len(cloud)
    _require(raw_count >= 100, "left_base edge cloud is unexpectedly sparse")
    _require(
        maximum_sample_count >= 100,
        "maximum edge sample count is unexpectedly small",
    )
    if raw_count > maximum_sample_count:
        indices = np.linspace(
            0, raw_count - 1, maximum_sample_count, dtype=np.int64
        )
        cloud = cloud[indices]
    return cloud, inventory, raw_count


def edge_metrics(
    distance: np.ndarray,
    pixels: np.ndarray,
    valid_depth: np.ndarray,
    *,
    clip_px: float,
    pixel_shift: tuple[float, float] = (0.0, 0.0),
) -> dict[str, Any]:
    shifted = pixels + np.asarray(pixel_shift, dtype=np.float64)
    in_frame = (
        valid_depth
        & np.isfinite(shifted).all(axis=1)
        & (shifted[:, 0] >= 0.0)
        & (shifted[:, 0] <= IMAGE_WIDTH - 1.0)
        & (shifted[:, 1] >= 0.0)
        & (shifted[:, 1] <= IMAGE_HEIGHT - 1.0)
    )
    values = np.full(len(shifted), clip_px, dtype=np.float64)
    if np.any(in_frame):
        values[in_frame] = map_coordinates(
            distance,
            [shifted[in_frame, 1], shifted[in_frame, 0]],
            order=1,
            mode="constant",
            cval=clip_px,
        )
    values = np.clip(values, 0.0, clip_px)
    finite_pixels = shifted[in_frame]
    bbox = (
        [
            float(np.min(finite_pixels[:, 0])),
            float(np.min(finite_pixels[:, 1])),
            float(np.max(finite_pixels[:, 0])),
            float(np.max(finite_pixels[:, 1])),
        ]
        if len(finite_pixels)
        else None
    )
    return {
        "sample_count": len(values),
        "valid_projection_count": int(np.count_nonzero(in_frame)),
        "rmse_px": float(np.sqrt(np.mean(values**2))),
        "median_px": float(np.median(values)),
        "p90_px": float(np.percentile(values, 90)),
        "within_4_px_fraction": float(np.mean(values <= 4.0)),
        "projected_bbox_xyxy": bbox,
        "_values": values,
    }


def _public_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in metrics.items() if not key.startswith("_")
    }


def _jacobian_diagnostics(jacobian: np.ndarray) -> dict[str, Any]:
    singular = np.linalg.svd(jacobian, compute_uv=False)
    tolerance = (
        np.finfo(np.float64).eps
        * max(jacobian.shape)
        * singular[0]
        if len(singular)
        else math.inf
    )
    rank = int(np.count_nonzero(singular > tolerance))
    condition = (
        float(singular[0] / singular[-1])
        if len(singular) and singular[-1] > tolerance
        else math.inf
    )
    return {
        "rank": rank,
        "condition_number": condition,
        "singular_values": singular.tolist(),
    }


def _rotation_delta_degrees(
    first: np.ndarray, second: np.ndarray
) -> float:
    relative = (
        Rotation.from_rotvec(first[:3]).inv()
        * Rotation.from_rotvec(second[:3])
    )
    return float(np.degrees(relative.magnitude()))


def _fit_base_camera(
    *,
    edge_cloud: np.ndarray,
    distance: np.ndarray,
    focal: float,
    seed: np.ndarray,
    algorithm: dict[str, Any],
) -> dict[str, Any]:
    settings = algorithm["camera_fit"]
    clip_px = float(algorithm["distance_transform_clip_px"])
    rotation_bound = float(settings["rotation_bound_about_seed_radians"])
    translation_bound = float(settings["translation_bound_about_seed_m"])
    span = np.asarray(
        [rotation_bound] * 3 + [translation_bound] * 3,
        dtype=np.float64,
    )
    lower = seed - span
    upper = seed + span

    def residual(vector: np.ndarray) -> np.ndarray:
        pixels, depth = _project(edge_cloud, vector, focal)
        return edge_metrics(
            distance, pixels, depth, clip_px=clip_px
        )["_values"]

    solutions: list[dict[str, Any]] = []
    for index, delta in enumerate(settings["deterministic_start_deltas"]):
        start = np.clip(
            seed + np.asarray(delta, dtype=np.float64),
            lower + 1e-8,
            upper - 1e-8,
        )
        fit = least_squares(
            residual,
            start,
            bounds=(lower, upper),
            loss=settings["loss"],
            f_scale=float(settings["f_scale_px"]),
            max_nfev=int(settings["maximum_function_evaluations"]),
        )
        pixels, depth = _project(edge_cloud, fit.x, focal)
        metrics = edge_metrics(
            distance, pixels, depth, clip_px=clip_px
        )
        normalized_clearance = np.minimum(
            (fit.x - lower) / (upper - lower),
            (upper - fit.x) / (upper - lower),
        )
        solutions.append(
            {
                "start_index": index,
                "start_camera_vector": start.tolist(),
                "camera_vector": fit.x.tolist(),
                "robust_cost": float(fit.cost),
                "optimality": float(fit.optimality),
                "function_evaluations": int(fit.nfev),
                "optimizer_success": bool(fit.success),
                "optimizer_message": fit.message,
                "minimum_parameter_bound_clearance_fraction": float(
                    np.min(normalized_clearance)
                ),
                "metrics": _public_metrics(metrics),
                "_jacobian": fit.jac,
                "_metrics": metrics,
            }
        )
    selected = min(solutions, key=lambda row: row["robust_cost"])
    selected_vector = np.asarray(selected["camera_vector"], dtype=np.float64)
    gates = algorithm["promotion_gates"]
    best_rmse = selected["metrics"]["rmse_px"]
    best_support = selected["metrics"]["within_4_px_fraction"]
    competitive = [
        row
        for row in solutions
        if (
            row["metrics"]["rmse_px"]
            <= best_rmse + float(gates["competitive_rmse_slack_px"])
            and row["metrics"]["within_4_px_fraction"]
            >= best_support
            - float(gates["competitive_within_4_fraction_slack"])
        )
    ]
    pairwise: list[dict[str, Any]] = []
    for first, second in itertools.combinations(competitive, 2):
        first_vector = np.asarray(first["camera_vector"], dtype=np.float64)
        second_vector = np.asarray(second["camera_vector"], dtype=np.float64)
        pairwise.append(
            {
                "start_indices": [
                    first["start_index"],
                    second["start_index"],
                ],
                "rotation_delta_degrees": _rotation_delta_degrees(
                    first_vector, second_vector
                ),
                "translation_delta_m": float(
                    np.linalg.norm(first_vector[3:6] - second_vector[3:6])
                ),
            }
        )
    local = _jacobian_diagnostics(selected["_jacobian"])
    public_solutions = [
        {key: value for key, value in row.items() if not key.startswith("_")}
        for row in solutions
    ]
    return {
        "selected_start_index": selected["start_index"],
        "selected_camera_vector": selected_vector.tolist(),
        "selected_metrics": selected["metrics"],
        "selected_bound_clearance_fraction": selected[
            "minimum_parameter_bound_clearance_fraction"
        ],
        "solutions": public_solutions,
        "competitive_start_indices": [
            row["start_index"] for row in competitive
        ],
        "competitive_pairwise_disagreement": pairwise,
        "maximum_competitive_rotation_delta_degrees": max(
            (row["rotation_delta_degrees"] for row in pairwise), default=0.0
        ),
        "maximum_competitive_translation_delta_m": max(
            (row["translation_delta_m"] for row in pairwise), default=0.0
        ),
        "local_identifiability": local,
    }


def background_shift_decision(
    selected: dict[str, Any],
    controls: list[dict[str, Any]],
    minimum_median_advantage_px: float,
    minimum_support_advantage: float,
) -> dict[str, Any]:
    median_advantages = [
        row["metrics"]["median_px"] - selected["median_px"]
        for row in controls
    ]
    support_advantages = [
        selected["within_4_px_fraction"]
        - row["metrics"]["within_4_px_fraction"]
        for row in controls
    ]
    minimum_median = min(median_advantages, default=-math.inf)
    minimum_support = min(support_advantages, default=-math.inf)
    return {
        "minimum_median_distance_advantage_px": float(minimum_median),
        "minimum_within_4_px_fraction_advantage": float(minimum_support),
        "required_median_distance_advantage_px": float(
            minimum_median_advantage_px
        ),
        "required_within_4_px_fraction_advantage": float(
            minimum_support_advantage
        ),
        "passed": bool(
            minimum_median >= minimum_median_advantage_px
            and minimum_support >= minimum_support_advantage
        ),
    }


def _moving_visual_vertices(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    config: dict[str, Any],
    physical_joints: np.ndarray,
    offsets: np.ndarray,
) -> np.ndarray:
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        for name in config["bindings"]["joint_names"]
    ]
    commanded = physical_joints.copy()
    commanded[:5] += offsets
    qpos = _physical_to_model_position(commanded[None, :], config)[0]
    for index, joint_id in enumerate(joint_ids):
        data.qpos[int(model.jnt_qposadr[joint_id])] = qpos[index]
    data.qvel[:] = 0.0
    mujoco.mj_forward(model, data)
    result: list[np.ndarray] = []
    for geom_id in range(model.ngeom):
        if (
            int(model.geom_group[geom_id]) != 2
            or int(model.geom_type[geom_id])
            != int(mujoco.mjtGeom.mjGEOM_MESH)
        ):
            continue
        body_name = mujoco.mj_id2name(
            model,
            mujoco.mjtObj.mjOBJ_BODY,
            int(model.geom_bodyid[geom_id]),
        )
        if not body_name or not body_name.startswith("left_"):
            continue
        if body_name == "left_base":
            continue
        mesh_id = int(model.geom_dataid[geom_id])
        start = int(model.mesh_vertadr[mesh_id])
        count = int(model.mesh_vertnum[mesh_id])
        local = np.asarray(
            model.mesh_vert[start : start + count], dtype=np.float64
        )
        result.append(
            local @ data.geom_xmat[geom_id].reshape(3, 3).T
            + data.geom_xpos[geom_id]
        )
    _require(result, "exact CAD has no moving left-arm visual vertices")
    return np.concatenate(result)


def _predicted_separation(
    *,
    model: mujoco.MjModel,
    data: mujoco.MjData,
    config: dict[str, Any],
    joints: np.ndarray,
    identity_offsets: np.ndarray,
    stage_d_offsets: np.ndarray,
    camera: np.ndarray,
    focal: float,
) -> dict[str, Any]:
    identity = _moving_visual_vertices(
        model, data, config, joints, identity_offsets
    )
    stage_d = _moving_visual_vertices(
        model, data, config, joints, stage_d_offsets
    )
    _require(
        identity.shape == stage_d.shape,
        "identity and Stage-D CAD vertex correspondence changed",
    )
    identity_pixels, identity_depth = _project(identity, camera, focal)
    stage_pixels, stage_depth = _project(stage_d, camera, focal)
    visible = (
        identity_depth
        & stage_depth
        & (identity_pixels[:, 0] >= 0.0)
        & (identity_pixels[:, 0] < IMAGE_WIDTH)
        & (identity_pixels[:, 1] >= 0.0)
        & (identity_pixels[:, 1] < IMAGE_HEIGHT)
        & (stage_pixels[:, 0] >= 0.0)
        & (stage_pixels[:, 0] < IMAGE_WIDTH)
        & (stage_pixels[:, 1] >= 0.0)
        & (stage_pixels[:, 1] < IMAGE_HEIGHT)
    )
    displacement = np.linalg.norm(
        identity_pixels[visible] - stage_pixels[visible], axis=1
    )
    _require(
        len(displacement) >= 4,
        "fewer than four exact CAD vertices are jointly visible",
    )
    return {
        "jointly_visible_vertex_count": len(displacement),
        "rmse_px": float(np.sqrt(np.mean(displacement**2))),
        "median_px": float(np.median(displacement)),
        "p90_px": float(np.percentile(displacement, 90)),
        "maximum_px": float(np.max(displacement)),
    }


def _future_target_rows(
    poses: dict[str, dict[str, Any]],
    algorithm: dict[str, Any],
) -> list[dict[str, Any]]:
    values = {
        name: np.asarray(
            poses[name]["final_actual_degrees"], dtype=np.float64
        )
        for name in FIT_POSES
    }
    settings = algorithm["future_target_search"]
    minimum_fit_distance = float(
        settings["minimum_distance_from_fit_pose_degrees"]
    )
    rows: list[dict[str, Any]] = []
    for first, second in itertools.combinations(FIT_POSES, 2):
        for alpha in settings["convex_pair_alphas"]:
            alpha = float(alpha)
            joints = (1.0 - alpha) * values[first] + alpha * values[second]
            nearest = min(
                float(np.linalg.norm(joints[:5] - value[:5]))
                for value in values.values()
            )
            if nearest < minimum_fit_distance:
                continue
            rows.append(
                {
                    "source_pair": [first, second],
                    "alpha_on_second": alpha,
                    "convex_weights": {
                        first: 1.0 - alpha,
                        second: alpha,
                    },
                    "joint_target_degrees": joints.tolist(),
                    "nearest_fit_pose_distance_degrees": nearest,
                }
            )
    return rows


def select_future_targets(
    rows: list[dict[str, Any]],
    minimum_between_degrees: float,
) -> list[dict[str, Any]]:
    ordered = sorted(
        rows,
        key=lambda row: (
            -float(row["predicted_separation"]["median_px"]),
            -float(row["predicted_separation"]["p90_px"]),
            row["source_pair"],
            row["alpha_on_second"],
        ),
    )
    _require(len(ordered) >= 2, "future target search is empty")
    selected = [ordered[0]]
    first = np.asarray(
        ordered[0]["joint_target_degrees"], dtype=np.float64
    )
    for row in ordered[1:]:
        candidate = np.asarray(
            row["joint_target_degrees"], dtype=np.float64
        )
        if (
            float(np.linalg.norm(candidate[:5] - first[:5]))
            >= minimum_between_degrees
        ):
            selected.append(row)
            break
    _require(
        len(selected) == 2,
        "no two future targets satisfy the frozen diversity gate",
    )
    return selected


def _promotion_gates(
    fit: dict[str, Any],
    shift: dict[str, Any],
    algorithm: dict[str, Any],
) -> dict[str, Any]:
    threshold = algorithm["promotion_gates"]
    metrics = fit["selected_metrics"]
    checks = {
        "median_reprojection": (
            metrics["median_px"]
            <= float(threshold["maximum_median_distance_px"])
        ),
        "p90_reprojection": (
            metrics["p90_px"]
            <= float(threshold["maximum_p90_distance_px"])
        ),
        "within_4_support": (
            metrics["within_4_px_fraction"]
            >= float(threshold["minimum_within_4_px_fraction"])
        ),
        "background_shift_uniqueness": shift["passed"],
        "local_jacobian_rank": (
            fit["local_identifiability"]["rank"]
            >= int(threshold["minimum_local_jacobian_rank"])
        ),
        "local_jacobian_condition": (
            fit["local_identifiability"]["condition_number"]
            <= float(
                threshold["maximum_local_jacobian_condition_number"]
            )
        ),
        "competitive_rotation_convergence": (
            fit["maximum_competitive_rotation_delta_degrees"]
            <= float(
                threshold[
                    "maximum_competitive_solution_rotation_delta_degrees"
                ]
            )
        ),
        "competitive_translation_convergence": (
            fit["maximum_competitive_translation_delta_m"]
            <= float(
                threshold[
                    "maximum_competitive_solution_translation_delta_m"
                ]
            )
        ),
        "parameter_bounds_clear": (
            fit["selected_bound_clearance_fraction"]
            >= float(threshold["minimum_parameter_bound_clearance_fraction"])
        ),
    }
    return {
        "thresholds": threshold,
        "checks": checks,
        "all_passed": all(checks.values()),
        "failed": sorted(name for name, passed in checks.items() if not passed),
    }


def build(
    spec_path: Path,
    output_directory: Path,
    *,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    root = (
        repository_root.resolve()
        if repository_root is not None
        else Path(__file__).resolve().parents[1]
    )
    _require(
        not output_directory.exists(),
        "refusing to overwrite fixed-base anchor attempt",
    )
    spec = load_spec(spec_path)
    contract_path = _bound(
        root, spec["mapping_contract"], "mapping contract"
    )
    contract = load_contract(contract_path)
    poses = load_fit_poses(root, contract)
    sources = contract["sources"]
    intrinsics_path = _bound(root, sources["intrinsics"], "Pi intrinsics")
    initialization_path = _bound(
        root,
        sources["camera_and_tag_initialization_only"],
        "camera/tag initialization",
    )
    stage_d_path = _bound(root, sources["stage_d"], "Stage-D source")
    manifest_path = _bound(
        root, sources["exact_CAD_scene"], "exact CAD scene"
    )
    intrinsics = _json(intrinsics_path, "Pi intrinsics")
    initialization = _json(
        initialization_path, "camera/tag initialization"
    )
    stage_d = _json(stage_d_path, "Stage-D source")
    manifest = _json(manifest_path, "exact CAD scene")
    inventory = inspect_full_cad(manifest)
    focal = float(
        intrinsics["output_resolution"]["camera_matrix"][0][0]
    )
    _require(
        intrinsics["output_resolution"]["size_px"]
        == [IMAGE_WIDTH, IMAGE_HEIGHT],
        "Pi intrinsics resolution changed",
    )
    declared_stage_d = np.asarray(
        contract["fixed_hypotheses"][
            "stage_d_joint_zero_offsets_degrees"
        ],
        dtype=np.float64,
    )
    source_stage_d = np.asarray(
        stage_d["stage_d"]["parameters"]["joint_zero_offsets_degrees"],
        dtype=np.float64,
    )
    _require(
        np.array_equal(declared_stage_d, source_stage_d),
        "Stage-D source no longer matches mapping contract",
    )
    algorithm = spec["algorithm"]
    roi = spec["admissible_roi"]
    seed, seed_report = _tag_seed(
        poses, initialization, focal, algorithm
    )
    consensus, consensus_report = _consensus_mask(poses, roi, algorithm)
    distance = cv2.distanceTransform(
        255 - consensus, cv2.DIST_L2, cv2.DIST_MASK_PRECISE
    )
    distance = np.clip(
        distance,
        0.0,
        float(algorithm["distance_transform_clip_px"]),
    )
    config = manifest["candidate_config"]
    model, _ = _compile_model(config, base_directory=None)
    data = mujoco.MjData(model)
    edge_cloud, base_inventory, raw_edge_sample_count = (
        _left_base_edge_cloud(
            model,
            data,
            int(algorithm["hull_samples_per_edge"]),
            int(algorithm["maximum_edge_sample_count"]),
        )
    )
    fit = _fit_base_camera(
        edge_cloud=edge_cloud,
        distance=distance,
        focal=focal,
        seed=seed,
        algorithm=algorithm,
    )
    selected_camera = np.asarray(
        fit["selected_camera_vector"], dtype=np.float64
    )
    selected_pixels, selected_depth = _project(
        edge_cloud, selected_camera, focal
    )
    clip_px = float(algorithm["distance_transform_clip_px"])
    control_rows: list[dict[str, Any]] = []
    for offset in algorithm["background_rejection"][
        "shift_control_offsets_px"
    ]:
        metrics = edge_metrics(
            distance,
            selected_pixels,
            selected_depth,
            clip_px=clip_px,
            pixel_shift=(float(offset[0]), float(offset[1])),
        )
        control_rows.append(
            {
                "offset_px": [int(offset[0]), int(offset[1])],
                "metrics": _public_metrics(metrics),
            }
        )
    rejection = algorithm["background_rejection"]
    shift_decision = background_shift_decision(
        fit["selected_metrics"],
        control_rows,
        float(rejection["minimum_median_distance_advantage_px"]),
        float(
            rejection["minimum_within_4_px_fraction_advantage"]
        ),
    )
    gates = _promotion_gates(fit, shift_decision, algorithm)

    target_rows = _future_target_rows(poses, algorithm)
    identity_offsets = np.zeros(5, dtype=np.float64)
    for row in target_rows:
        row["predicted_separation"] = _predicted_separation(
            model=model,
            data=data,
            config=config,
            joints=np.asarray(
                row["joint_target_degrees"], dtype=np.float64
            ),
            identity_offsets=identity_offsets,
            stage_d_offsets=declared_stage_d,
            camera=selected_camera,
            focal=focal,
        )
    selected_targets = select_future_targets(
        target_rows,
        float(
            algorithm["future_target_search"][
                "minimum_distance_between_selected_targets_degrees"
            ]
        ),
    )
    target_gate = float(
        algorithm["future_target_search"][
            "minimum_joint_mapping_separation_px"
        ]
    )
    labeled_targets = []
    for label, row in zip(("N", "O"), selected_targets, strict=True):
        labeled_targets.append(
            {
                **row,
                "provisional_label": label,
                "separation_gate_passed": (
                    row["predicted_separation"]["median_px"]
                    >= target_gate
                ),
                "status": (
                    "provisional_under_promoted_base_camera"
                    if gates["all_passed"]
                    else "provisional_under_rejected_diagnostic_camera"
                ),
                "requires_before_hardware": [
                    "freeze_new_route_and_packet",
                    "gateway_kinematic_preview",
                    "collision_and_limit_review",
                    "new_heldout_preregistration",
                ],
            }
        )

    output_directory.mkdir(parents=True)
    mask_path = output_directory / "consensus_mask.png"
    _require(
        cv2.imwrite(str(mask_path), consensus),
        "failed to write frozen consensus mask",
    )
    candidate = (
        {
            "schema_version": (
                "sim2claw.current_pi_fixed_base_camera_candidate.v1"
            ),
            "status": "preregistered_base_camera_candidate",
            "camera_world_rotation_vector_radians": (
                selected_camera[:3].tolist()
            ),
            "camera_world_translation_m": selected_camera[3:6].tolist(),
            "focal_pixels": focal,
            "consensus_mask_sha256": sha256_file(mask_path),
            "admissible_roi_sha256": spec["admissible_roi_sha256"],
            "algorithm_sha256": spec["algorithm_sha256"],
        }
        if gates["all_passed"]
        else None
    )
    result: dict[str, Any] = {
        "schema_version": RESULT_SCHEMA,
        "status": (
            "base_anchor_candidate_emitted"
            if candidate is not None
            else "background_latch_or_reprojection_failure_no_anchor_candidate"
        ),
        "proof_class": spec["proof_class"],
        "fit_data_access": {
            "poses_opened": list(FIT_POSES),
            "heldout_frames_opened": [],
            "hardware_motion_performed": False,
        },
        "specification": {
            "path": str(spec_path.resolve()),
            "sha256": sha256_file(spec_path),
            "admissible_roi": roi,
            "admissible_roi_sha256": spec["admissible_roi_sha256"],
            "algorithm_sha256": spec["algorithm_sha256"],
        },
        "verified_source_hashes": {
            "mapping_contract": sha256_file(contract_path),
            "intrinsics": sha256_file(intrinsics_path),
            "camera_and_tag_initialization_only": sha256_file(
                initialization_path
            ),
            "stage_d": sha256_file(stage_d_path),
            "exact_CAD_scene": sha256_file(manifest_path),
            "fit_observations": {
                name: {
                    "receipt": poses[name]["receipt_sha256"],
                    "image": poses[name]["pi_image_sha256"],
                }
                for name in FIT_POSES
            },
        },
        "full_cad_inventory": inventory,
        "left_base_visual_meshes": base_inventory,
        "left_base_raw_edge_sample_count": raw_edge_sample_count,
        "left_base_edge_sample_count": len(edge_cloud),
        "left_base_edge_sampling": (
            "deterministic_uniform_index_subsample_after_exact_per_mesh_"
            "convex_hull_edge_sampling"
        ),
        "tag_camera_seed": seed_report,
        "static_consensus": {
            **consensus_report,
            "mask_path": str(mask_path.resolve()),
            "mask_sha256": sha256_file(mask_path),
        },
        "camera_fit": fit,
        "background_shift_controls": {
            "controls": control_rows,
            "decision": shift_decision,
        },
        "camera_identifiability": {
            "local": {
                **fit["local_identifiability"],
                "gate_interpretation": (
                    "finite_local_linearization_only_not_global_uniqueness"
                ),
            },
            "global": {
                "competitive_start_indices": fit[
                    "competitive_start_indices"
                ],
                "maximum_rotation_delta_degrees": fit[
                    "maximum_competitive_rotation_delta_degrees"
                ],
                "maximum_translation_delta_m": fit[
                    "maximum_competitive_translation_delta_m"
                ],
                "interpretation": (
                    "globally_identified"
                    if (
                        gates["checks"][
                            "competitive_rotation_convergence"
                        ]
                        and gates["checks"][
                            "competitive_translation_convergence"
                        ]
                        and gates["checks"]["background_shift_uniqueness"]
                    )
                    else "multiple_background_edge_latches_or_nonunique_camera"
                ),
            },
        },
        "promotion_gates": gates,
        "candidate": candidate,
        "future_heldout_target_search": {
            "proof_status": (
                "diagnostic_prediction_not_hardware_authority"
            ),
            "candidate_count": len(target_rows),
            "hypotheses": {
                "identity_joint_zero_offsets_degrees": (
                    identity_offsets.tolist()
                ),
                "stage_d_joint_zero_offsets_degrees": (
                    declared_stage_d.tolist()
                ),
            },
            "selected_targets": labeled_targets,
        },
        "terminal_missing_datum": (
            None
            if candidate is not None
            else (
                "one metric fixed-base datum that cannot be explained by "
                "background edges: either a measured base fiducial-to-CAD "
                "transform or at least three non-collinear frozen semantic "
                "base landmark correspondences"
            )
        ),
        "authority": {
            "camera_candidate_emitted": candidate is not None,
            "joint_mapping_promoted": False,
            "simulator_parameter_promotion": False,
            "hardware_motion": False,
            "physical_task": False,
            "policy": False,
        },
    }
    # Avoid serializing optimizer Jacobians or distance vectors.
    result["camera_fit"] = {
        key: value
        for key, value in result["camera_fit"].items()
        if not key.startswith("_")
    }
    result["result_digest"] = canonical_sha256(result)
    result_path = output_directory / "result.json"
    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    arguments = parser.parse_args()
    result = build(
        arguments.spec.resolve(), arguments.output_directory.resolve()
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "candidate_emitted": result["candidate"] is not None,
                "failed_gates": result["promotion_gates"]["failed"],
                "future_targets": [
                    row["provisional_label"]
                    for row in result["future_heldout_target_search"][
                        "selected_targets"
                    ]
                ],
                "output": str(
                    (arguments.output_directory / "result.json").resolve()
                ),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

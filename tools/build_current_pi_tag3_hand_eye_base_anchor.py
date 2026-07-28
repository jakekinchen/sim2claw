#!/usr/bin/env python3
"""Resolve a tag-3 single-axis hand-eye gauge with exact base CAD edges.

Only J/S/K/L are admitted.  Tag 3 is jointly fit as one fixed camera and one
rigid ``left_shoulder`` mount.  Shoulder-pan-only excitation leaves the exact
two-dimensional centralizer of one revolute axis unobservable: rotation about
the axis and translation along it.  The static exact-base edge objective is
allowed to optimize only those two gauge coordinates.
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
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from sim2claw.recorded_replay import _compile_model
from tools.build_current_pi_fixed_base_cad_anchor import (
    AnchorBuildError,
    _consensus_mask,
    _jacobian_diagnostics,
    _left_base_edge_cloud,
    _project,
    _public_metrics,
    _rotation_delta_degrees,
    background_shift_decision,
    edge_metrics,
    load_spec as load_base_spec,
)
from tools.evaluate_current_pi_cad_keyed_joint_mapping import (
    _bound,
    _json,
    canonical_sha256,
    inspect_full_cad,
    load_contract,
    load_fit_poses,
    sha256_file,
)
from tools.fit_pi_dual_link_tag_bundle import Bundle, pose_vector, transform


SPEC_SCHEMA = "sim2claw.current_pi_tag3_hand_eye_base_anchor_spec.v1"
RESULT_SCHEMA = "sim2claw.current_pi_tag3_hand_eye_base_anchor_result.v1"
FIT_POSES = ("J", "S", "K", "L")
TAG_ID = 3
TAG_BODY = "left_shoulder"
PAN_JOINT = "left_shoulder_pan"
IMAGE_WIDTH = 1536
IMAGE_HEIGHT = 864


class HandEyeAnchorError(RuntimeError):
    """The frozen hand-eye lineage or algorithm changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HandEyeAnchorError(message)


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
        "unexpected tag3 hand-eye anchor specification",
    )
    _require(
        spec.get("status")
        == "frozen_J_S_K_L_only_before_tag3_hand_eye_gauge_fit",
        "hand-eye split was not frozen before fitting",
    )
    _require(
        spec.get("fit_poses") == list(FIT_POSES),
        "hand-eye fit poses changed",
    )
    for label in ("mapping_contract", "base_anchor_spec"):
        binding = spec.get(label) or {}
        _require(
            isinstance(binding.get("path"), str)
            and isinstance(binding.get("sha256"), str)
            and len(binding["sha256"]) == 64,
            f"{label} binding is incomplete",
        )
    algorithm = spec.get("hand_eye_algorithm")
    _require(isinstance(algorithm, dict), "hand-eye algorithm is absent")
    _require(
        canonical_sha256(algorithm)
        == spec.get("hand_eye_algorithm_sha256"),
        "hand-eye algorithm hash changed",
    )
    _require(
        algorithm.get("tag_id") == TAG_ID
        and algorithm.get("rigid_body") == TAG_BODY
        and algorithm.get("excited_joint") == PAN_JOINT,
        "tag3 rigid attachment or excited joint changed",
    )
    tag_fit = algorithm.get("tag_fit") or {}
    _require(
        tag_fit.get("expected_identifiable_rank") == 10
        and tag_fit.get("expected_gauge_nullity") == 2,
        "single-axis hand-eye gauge contract changed",
    )
    gauge = algorithm.get("gauge_search") or {}
    _require(
        gauge.get("multistart_count") == 5,
        "gauge multi-start count changed",
    )
    authority = spec.get("authority") or {}
    _require(
        authority.get("hardware_motion") is False
        and authority.get("simulator_parameter_promotion") is False
        and authority.get("physical_task") is False
        and authority.get("policy") is False,
        "hand-eye anchor authority widened",
    )
    for value in _iter_strings(
        {
            key: nested
            for key, nested in spec.items()
            if key != "mapping_contract"
        }
    ):
        lowered = value.lower()
        _require(
            "/pose-m-" not in lowered
            and "pose_m" not in lowered
            and "fresh_validation" not in lowered,
            "hand-eye specification references held-out data",
        )


def load_spec(path: Path) -> dict[str, Any]:
    spec = _json(path, "tag3 hand-eye anchor specification")
    validate_spec(spec)
    return spec


def _tag_rows(
    poses: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in FIT_POSES:
        tag = poses[name]["detected_tags"].get(str(TAG_ID))
        _require(tag is not None, f"pose {name} lacks unique tag 3")
        rows.append(
            {
                "name": name,
                "joint_degrees": np.asarray(
                    poses[name]["final_actual_degrees"], dtype=np.float64
                ),
                "corners_pixels": np.asarray(
                    tag["corners_pixels"], dtype=np.float64
                ),
            }
        )
    return rows


def _tag_projection(
    vector: np.ndarray,
    row: dict[str, Any],
    bundle: Bundle,
    focal: float,
) -> np.ndarray:
    camera_points = (
        transform(vector[:3], vector[3:6])
        @ bundle.body_pose(
            TAG_BODY,
            row["joint_degrees"],
            np.zeros(5, dtype=np.float64),
        )
        @ transform(vector[6:9], vector[9:12])
        @ bundle.tag_points
    )[:3]
    return np.column_stack(
        [
            focal * camera_points[0] / camera_points[2]
            + IMAGE_WIDTH / 2.0,
            focal * camera_points[1] / camera_points[2]
            + IMAGE_HEIGHT / 2.0,
        ]
    )


def _tag_residual(
    vector: np.ndarray,
    rows: list[dict[str, Any]],
    bundle: Bundle,
    focal: float,
) -> np.ndarray:
    return np.concatenate(
        [
            (
                _tag_projection(vector, row, bundle, focal)
                - row["corners_pixels"]
            ).ravel()
            for row in rows
        ]
    )


def _fit_tag3_hand_eye(
    *,
    poses: dict[str, dict[str, Any]],
    initialization: dict[str, Any],
    focal: float,
    algorithm: dict[str, Any],
) -> tuple[np.ndarray, Bundle, list[dict[str, Any]], dict[str, Any]]:
    rows = _tag_rows(poses)
    bundle = Bundle()
    bundle.set_focal(focal)
    bundle.body_ids[TAG_BODY] = mujoco.mj_name2id(
        bundle.model, mujoco.mjtObj.mjOBJ_BODY, TAG_BODY
    )
    parameters = initialization["parameters"]
    camera_start = np.asarray(
        parameters["camera_world_rotation_vector_radians"]
        + parameters["camera_world_translation_m"],
        dtype=np.float64,
    )
    first = rows[0]
    camera_tag = bundle.camera_tag(
        {
            "name": first["name"],
            "corners": first["corners_pixels"],
        }
    )
    world_body = bundle.body_pose(
        TAG_BODY,
        first["joint_degrees"],
        np.zeros(5, dtype=np.float64),
    )
    mount_start = np.linalg.inv(
        transform(camera_start[:3], camera_start[3:6]) @ world_body
    ) @ camera_tag
    start = np.concatenate([camera_start, pose_vector(mount_start)])
    settings = algorithm["tag_fit"]
    fit = least_squares(
        lambda value: _tag_residual(
            value, rows, bundle, focal
        ),
        start,
        loss=settings["loss"],
        max_nfev=int(settings["maximum_function_evaluations"]),
        xtol=1e-13,
        ftol=1e-13,
        gtol=1e-13,
    )
    corner_errors = np.linalg.norm(
        _tag_residual(fit.x, rows, bundle, focal).reshape(-1, 2),
        axis=1,
    )
    singular = np.linalg.svd(fit.jac, compute_uv=False)
    relative = singular / singular[0]
    cutoff = float(settings["relative_null_singular_value_max"])
    rank = int(np.count_nonzero(relative > cutoff))
    return fit.x, bundle, rows, {
        "joint_fit": "one_shared_camera_and_one_rigid_tag3_mount",
        "tag_id": TAG_ID,
        "body": TAG_BODY,
        "fit_poses": list(FIT_POSES),
        "shoulder_pan_span_degrees": float(
            np.ptp([row["joint_degrees"][0] for row in rows])
        ),
        "corner_count": len(corner_errors),
        "corner_rmse_px": float(np.sqrt(np.mean(corner_errors**2))),
        "corner_max_px": float(np.max(corner_errors)),
        "parameter_count": 12,
        "identifiable_rank": rank,
        "gauge_nullity": int(12 - rank),
        "singular_values": singular.tolist(),
        "relative_singular_values": relative.tolist(),
        "relative_null_cutoff": cutoff,
        "optimizer_success": bool(fit.success),
        "optimizer_message": fit.message,
        "_jacobian": fit.jac,
    }


def _axis_frame(
    bundle: Bundle,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    body_at_zero = bundle.body_pose(
        TAG_BODY,
        np.zeros(6, dtype=np.float64),
        np.zeros(5, dtype=np.float64),
    )
    joint_id = mujoco.mj_name2id(
        bundle.model, mujoco.mjtObj.mjOBJ_JOINT, PAN_JOINT
    )
    anchor = np.asarray(bundle.data.xanchor[joint_id], dtype=np.float64)
    axis = np.asarray(bundle.data.xaxis[joint_id], dtype=np.float64)
    axis /= np.linalg.norm(axis)
    reference = np.asarray([1.0, 0.0, 0.0])
    if abs(float(reference @ axis)) > 0.9:
        reference = np.asarray([0.0, 1.0, 0.0])
    x_axis = reference - float(reference @ axis) * axis
    x_axis /= np.linalg.norm(x_axis)
    y_axis = np.cross(axis, x_axis)
    world_axis = np.eye(4)
    world_axis[:3, :3] = np.column_stack([x_axis, y_axis, axis])
    world_axis[:3, 3] = anchor
    axis_body = np.linalg.inv(world_axis) @ body_at_zero
    return world_axis, axis_body, {
        "joint": PAN_JOINT,
        "world_anchor_m": anchor.tolist(),
        "world_axis_unit": axis.tolist(),
        "gauge_coordinates": [
            "rotation_about_shoulder_pan_axis_radians",
            "translation_along_shoulder_pan_axis_m",
        ],
        "centralizer_dimension": 2,
    }


def apply_single_axis_gauge(
    camera_world: np.ndarray,
    body_tag: np.ndarray,
    world_axis: np.ndarray,
    axis_body: np.ndarray,
    gauge: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    axis_delta = np.eye(4)
    axis_delta[:3, :3] = Rotation.from_rotvec(
        [0.0, 0.0, float(gauge[0])]
    ).as_matrix()
    axis_delta[:3, 3] = [0.0, 0.0, float(gauge[1])]
    camera = (
        camera_world
        @ world_axis
        @ np.linalg.inv(axis_delta)
        @ np.linalg.inv(world_axis)
    )
    mount = (
        np.linalg.inv(axis_body)
        @ axis_delta
        @ axis_body
        @ body_tag
    )
    return camera, mount


def _gauged_vector(
    hand_eye: np.ndarray,
    world_axis: np.ndarray,
    axis_body: np.ndarray,
    gauge: np.ndarray,
) -> np.ndarray:
    camera, mount = apply_single_axis_gauge(
        transform(hand_eye[:3], hand_eye[3:6]),
        transform(hand_eye[6:9], hand_eye[9:12]),
        world_axis,
        axis_body,
        gauge,
    )
    return np.concatenate([pose_vector(camera), pose_vector(mount)])


def _gauge_invariance(
    *,
    hand_eye: np.ndarray,
    world_axis: np.ndarray,
    axis_body: np.ndarray,
    rows: list[dict[str, Any]],
    bundle: Bundle,
    focal: float,
    checks: list[list[float]],
) -> dict[str, Any]:
    baseline = _tag_residual(hand_eye, rows, bundle, focal)
    rows_out = []
    for gauge in checks:
        vector = _gauged_vector(
            hand_eye,
            world_axis,
            axis_body,
            np.asarray(gauge, dtype=np.float64),
        )
        maximum = float(
            np.max(
                np.abs(
                    _tag_residual(vector, rows, bundle, focal)
                    - baseline
                )
            )
        )
        rows_out.append(
            {
                "gauge": [float(gauge[0]), float(gauge[1])],
                "maximum_corner_residual_delta_px": maximum,
            }
        )
    return {
        "checks": rows_out,
        "maximum_corner_residual_delta_px": max(
            row["maximum_corner_residual_delta_px"] for row in rows_out
        ),
    }


def select_diverse_grid_seeds(
    rows: list[tuple[float, float, float]],
    *,
    count: int,
    minimum_rotation_separation: float,
    minimum_translation_separation: float,
) -> list[list[float]]:
    selected: list[tuple[float, float]] = []
    for _, rotation, translation in sorted(rows):
        if all(
            min(
                abs(rotation - prior_rotation),
                2.0 * math.pi - abs(rotation - prior_rotation),
            )
            >= minimum_rotation_separation
            or abs(translation - prior_translation)
            >= minimum_translation_separation
            for prior_rotation, prior_translation in selected
        ):
            selected.append((rotation, translation))
        if len(selected) == count:
            break
    _require(len(selected) == count, "gauge grid lacks diverse starts")
    return [[float(rotation), float(translation)] for rotation, translation in selected]


def _fit_base_gauge(
    *,
    edge_cloud: np.ndarray,
    distance: np.ndarray,
    focal: float,
    hand_eye: np.ndarray,
    world_axis: np.ndarray,
    axis_body: np.ndarray,
    base_algorithm: dict[str, Any],
    hand_eye_algorithm: dict[str, Any],
) -> dict[str, Any]:
    settings = hand_eye_algorithm["gauge_search"]
    rotation_bounds = settings["rotation_about_axis_bounds_radians"]
    translation_bounds = settings["translation_along_axis_bounds_m"]
    lower = np.asarray(
        [rotation_bounds[0], translation_bounds[0]], dtype=np.float64
    )
    upper = np.asarray(
        [rotation_bounds[1], translation_bounds[1]], dtype=np.float64
    )
    clip_px = float(base_algorithm["distance_transform_clip_px"])

    def camera_vector(gauge: np.ndarray) -> np.ndarray:
        return _gauged_vector(
            hand_eye, world_axis, axis_body, gauge
        )[:6]

    def metrics(gauge: np.ndarray) -> dict[str, Any]:
        pixels, depth = _project(edge_cloud, camera_vector(gauge), focal)
        return edge_metrics(
            distance, pixels, depth, clip_px=clip_px
        )

    def residual(gauge: np.ndarray) -> np.ndarray:
        return metrics(gauge)["_values"]

    grid_rows: list[tuple[float, float, float]] = []
    for rotation in np.linspace(
        lower[0], upper[0], int(settings["rotation_grid_count"])
    ):
        for translation in np.linspace(
            lower[1],
            upper[1],
            int(settings["translation_grid_count"]),
        ):
            grid_rows.append(
                (
                    metrics(
                        np.asarray([rotation, translation])
                    )["rmse_px"],
                    float(rotation),
                    float(translation),
                )
            )
    starts = select_diverse_grid_seeds(
        grid_rows,
        count=int(settings["multistart_count"]),
        minimum_rotation_separation=float(
            settings["minimum_seed_rotation_separation_radians"]
        ),
        minimum_translation_separation=float(
            settings["minimum_seed_translation_separation_m"]
        ),
    )
    solutions: list[dict[str, Any]] = []
    for index, start in enumerate(starts):
        fit = least_squares(
            residual,
            np.asarray(start),
            bounds=(lower, upper),
            loss=settings["loss"],
            f_scale=float(settings["f_scale_px"]),
            max_nfev=int(settings["maximum_function_evaluations"]),
        )
        full_vector = _gauged_vector(
            hand_eye, world_axis, axis_body, fit.x
        )
        result_metrics = metrics(fit.x)
        clearance = np.minimum(
            (fit.x - lower) / (upper - lower),
            (upper - fit.x) / (upper - lower),
        )
        solutions.append(
            {
                "start_index": index,
                "grid_start_gauge": start,
                "gauge": fit.x.tolist(),
                "camera_vector": full_vector[:6].tolist(),
                "tag3_mount_vector": full_vector[6:12].tolist(),
                "robust_cost": float(fit.cost),
                "minimum_parameter_bound_clearance_fraction": float(
                    np.min(clearance)
                ),
                "metrics": _public_metrics(result_metrics),
                "gauge_jacobian": _jacobian_diagnostics(fit.jac),
            }
        )
    selected = min(solutions, key=lambda row: row["robust_cost"])
    gates = base_algorithm["promotion_gates"]
    competitive = [
        row
        for row in solutions
        if (
            row["metrics"]["rmse_px"]
            <= selected["metrics"]["rmse_px"]
            + float(gates["competitive_rmse_slack_px"])
            and row["metrics"]["within_4_px_fraction"]
            >= selected["metrics"]["within_4_px_fraction"]
            - float(gates["competitive_within_4_fraction_slack"])
        )
    ]
    pairwise = []
    for first, second in itertools.combinations(competitive, 2):
        first_camera = np.asarray(
            first["camera_vector"], dtype=np.float64
        )
        second_camera = np.asarray(
            second["camera_vector"], dtype=np.float64
        )
        pairwise.append(
            {
                "start_indices": [
                    first["start_index"],
                    second["start_index"],
                ],
                "rotation_delta_degrees": _rotation_delta_degrees(
                    first_camera, second_camera
                ),
                "translation_delta_m": float(
                    np.linalg.norm(
                        first_camera[3:6] - second_camera[3:6]
                    )
                ),
            }
        )
    return {
        "grid_candidate_count": len(grid_rows),
        "selected_start_index": selected["start_index"],
        "selected_gauge": selected["gauge"],
        "selected_camera_vector": selected["camera_vector"],
        "selected_tag3_mount_vector": selected["tag3_mount_vector"],
        "selected_metrics": selected["metrics"],
        "selected_bound_clearance_fraction": selected[
            "minimum_parameter_bound_clearance_fraction"
        ],
        "selected_gauge_jacobian": selected["gauge_jacobian"],
        "solutions": solutions,
        "competitive_start_indices": [
            row["start_index"] for row in competitive
        ],
        "competitive_pairwise_disagreement": pairwise,
        "maximum_competitive_rotation_delta_degrees": max(
            (row["rotation_delta_degrees"] for row in pairwise),
            default=0.0,
        ),
        "maximum_competitive_translation_delta_m": max(
            (row["translation_delta_m"] for row in pairwise),
            default=0.0,
        ),
    }


def _promotion_gates(
    *,
    hand_eye: dict[str, Any],
    invariance: dict[str, Any],
    gauge_fit: dict[str, Any],
    shift: dict[str, Any],
    base_algorithm: dict[str, Any],
    hand_eye_algorithm: dict[str, Any],
) -> dict[str, Any]:
    base = base_algorithm["promotion_gates"]
    tag = hand_eye_algorithm["tag_fit"]
    metrics = gauge_fit["selected_metrics"]
    jacobian = gauge_fit["selected_gauge_jacobian"]
    checks = {
        "tag3_corner_rmse": (
            hand_eye["corner_rmse_px"]
            <= float(tag["maximum_corner_rmse_px"])
        ),
        "tag3_corner_max": (
            hand_eye["corner_max_px"]
            <= float(tag["maximum_corner_error_px"])
        ),
        "hand_eye_rank": (
            hand_eye["identifiable_rank"]
            == int(tag["expected_identifiable_rank"])
        ),
        "single_axis_gauge_nullity": (
            hand_eye["gauge_nullity"]
            == int(tag["expected_gauge_nullity"])
        ),
        "exact_gauge_invariance": (
            invariance["maximum_corner_residual_delta_px"]
            <= float(
                hand_eye_algorithm[
                    "maximum_gauge_invariance_corner_delta_px"
                ]
            )
        ),
        "median_reprojection": (
            metrics["median_px"]
            <= float(base["maximum_median_distance_px"])
        ),
        "p90_reprojection": (
            metrics["p90_px"]
            <= float(base["maximum_p90_distance_px"])
        ),
        "within_4_support": (
            metrics["within_4_px_fraction"]
            >= float(base["minimum_within_4_px_fraction"])
        ),
        "background_shift_uniqueness": shift["passed"],
        "gauge_jacobian_rank": jacobian["rank"] == 2,
        "gauge_jacobian_condition": (
            jacobian["condition_number"]
            <= float(base["maximum_local_jacobian_condition_number"])
        ),
        "competitive_rotation_convergence": (
            gauge_fit["maximum_competitive_rotation_delta_degrees"]
            <= float(
                base[
                    "maximum_competitive_solution_rotation_delta_degrees"
                ]
            )
        ),
        "competitive_translation_convergence": (
            gauge_fit["maximum_competitive_translation_delta_m"]
            <= float(
                base[
                    "maximum_competitive_solution_translation_delta_m"
                ]
            )
        ),
        "parameter_bounds_clear": (
            gauge_fit["selected_bound_clearance_fraction"]
            >= float(base["minimum_parameter_bound_clearance_fraction"])
        ),
    }
    return {
        "checks": checks,
        "all_passed": all(checks.values()),
        "failed": sorted(name for name, passed in checks.items() if not passed),
        "inherited_global_agreement_thresholds": {
            "maximum_rotation_delta_degrees": base[
                "maximum_competitive_solution_rotation_delta_degrees"
            ],
            "maximum_translation_delta_m": base[
                "maximum_competitive_solution_translation_delta_m"
            ],
        },
        "inherited_base_reprojection_thresholds": {
            "maximum_median_distance_px": base[
                "maximum_median_distance_px"
            ],
            "maximum_p90_distance_px": base[
                "maximum_p90_distance_px"
            ],
            "minimum_within_4_px_fraction": base[
                "minimum_within_4_px_fraction"
            ],
        },
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
        "refusing to overwrite tag3 hand-eye anchor attempt",
    )
    spec = load_spec(spec_path)
    contract_path = _bound(
        root, spec["mapping_contract"], "mapping contract"
    )
    base_spec_path = _bound(
        root, spec["base_anchor_spec"], "base anchor specification"
    )
    contract = load_contract(contract_path)
    try:
        base_spec = load_base_spec(base_spec_path)
    except AnchorBuildError as error:
        raise HandEyeAnchorError(str(error)) from error
    poses = load_fit_poses(root, contract)
    sources = contract["sources"]
    intrinsics_path = _bound(root, sources["intrinsics"], "Pi intrinsics")
    initialization_path = _bound(
        root,
        sources["camera_and_tag_initialization_only"],
        "camera/tag initialization",
    )
    manifest_path = _bound(
        root, sources["exact_CAD_scene"], "exact CAD scene"
    )
    intrinsics = _json(intrinsics_path, "Pi intrinsics")
    initialization = _json(
        initialization_path, "camera/tag initialization"
    )
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
    hand_eye_algorithm = spec["hand_eye_algorithm"]
    hand_eye, bundle, rows, hand_eye_report = _fit_tag3_hand_eye(
        poses=poses,
        initialization=initialization,
        focal=focal,
        algorithm=hand_eye_algorithm,
    )
    world_axis, axis_body, axis_report = _axis_frame(bundle)
    invariance = _gauge_invariance(
        hand_eye=hand_eye,
        world_axis=world_axis,
        axis_body=axis_body,
        rows=rows,
        bundle=bundle,
        focal=focal,
        checks=hand_eye_algorithm["exact_gauge_invariance_checks"],
    )
    base_algorithm = base_spec["algorithm"]
    consensus, consensus_report = _consensus_mask(
        poses, base_spec["admissible_roi"], base_algorithm
    )
    distance = cv2.distanceTransform(
        255 - consensus, cv2.DIST_L2, cv2.DIST_MASK_PRECISE
    )
    distance = np.clip(
        distance,
        0.0,
        float(base_algorithm["distance_transform_clip_px"]),
    )
    model, _ = _compile_model(
        manifest["candidate_config"], base_directory=None
    )
    data = mujoco.MjData(model)
    edge_cloud, base_meshes, raw_edge_count = _left_base_edge_cloud(
        model,
        data,
        int(base_algorithm["hull_samples_per_edge"]),
        int(base_algorithm["maximum_edge_sample_count"]),
    )
    gauge_fit = _fit_base_gauge(
        edge_cloud=edge_cloud,
        distance=distance,
        focal=focal,
        hand_eye=hand_eye,
        world_axis=world_axis,
        axis_body=axis_body,
        base_algorithm=base_algorithm,
        hand_eye_algorithm=hand_eye_algorithm,
    )
    selected_camera = np.asarray(
        gauge_fit["selected_camera_vector"], dtype=np.float64
    )
    pixels, depth = _project(edge_cloud, selected_camera, focal)
    clip_px = float(base_algorithm["distance_transform_clip_px"])
    controls = []
    for offset in base_algorithm["background_rejection"][
        "shift_control_offsets_px"
    ]:
        controls.append(
            {
                "offset_px": [int(offset[0]), int(offset[1])],
                "metrics": _public_metrics(
                    edge_metrics(
                        distance,
                        pixels,
                        depth,
                        clip_px=clip_px,
                        pixel_shift=(
                            float(offset[0]),
                            float(offset[1]),
                        ),
                    )
                ),
            }
        )
    rejection = base_algorithm["background_rejection"]
    shift = background_shift_decision(
        gauge_fit["selected_metrics"],
        controls,
        float(rejection["minimum_median_distance_advantage_px"]),
        float(
            rejection["minimum_within_4_px_fraction_advantage"]
        ),
    )
    gates = _promotion_gates(
        hand_eye=hand_eye_report,
        invariance=invariance,
        gauge_fit=gauge_fit,
        shift=shift,
        base_algorithm=base_algorithm,
        hand_eye_algorithm=hand_eye_algorithm,
    )
    output_directory.mkdir(parents=True)
    mask_path = output_directory / "consensus_mask.png"
    _require(
        cv2.imwrite(str(mask_path), consensus),
        "failed to write tag3 hand-eye consensus mask",
    )
    candidate = (
        {
            "schema_version": (
                "sim2claw.current_pi_tag3_hand_eye_base_camera_candidate.v1"
            ),
            "status": "preregistered_before_future_heldout_selection",
            "camera_world_rotation_vector_radians": (
                selected_camera[:3].tolist()
            ),
            "camera_world_translation_m": selected_camera[3:6].tolist(),
            "tag3_body_tag_rotation_vector_radians": gauge_fit[
                "selected_tag3_mount_vector"
            ][:3],
            "tag3_body_tag_translation_m": gauge_fit[
                "selected_tag3_mount_vector"
            ][3:6],
            "focal_pixels": focal,
            "algorithm_sha256": spec["hand_eye_algorithm_sha256"],
            "base_algorithm_sha256": base_spec["algorithm_sha256"],
            "consensus_mask_sha256": sha256_file(mask_path),
        }
        if gates["all_passed"]
        else None
    )
    public_hand_eye = {
        key: value
        for key, value in hand_eye_report.items()
        if not key.startswith("_")
    }
    result: dict[str, Any] = {
        "schema_version": RESULT_SCHEMA,
        "status": (
            "tag3_hand_eye_base_anchor_candidate_frozen"
            if candidate is not None
            else "tag3_hand_eye_valid_base_gauge_unresolved_no_candidate"
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
            "hand_eye_algorithm_sha256": spec[
                "hand_eye_algorithm_sha256"
            ],
            "base_anchor_spec_path": str(base_spec_path),
            "base_anchor_spec_sha256": sha256_file(base_spec_path),
            "inherited_roi_sha256": base_spec[
                "admissible_roi_sha256"
            ],
            "inherited_base_algorithm_sha256": base_spec[
                "algorithm_sha256"
            ],
        },
        "verified_source_hashes": {
            "mapping_contract": sha256_file(contract_path),
            "intrinsics": sha256_file(intrinsics_path),
            "camera_and_tag_initialization_only": sha256_file(
                initialization_path
            ),
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
        "left_base_visual_meshes": base_meshes,
        "left_base_raw_edge_sample_count": raw_edge_count,
        "left_base_edge_sample_count": len(edge_cloud),
        "tag3_hand_eye": public_hand_eye,
        "single_axis_gauge": {
            **axis_report,
            "exact_invariance": invariance,
            "interpretation": (
                "tag3 constrains ten of twelve camera-plus-mount "
                "parameters; rotation about and translation along the "
                "only excited joint axis are exactly unobservable"
            ),
        },
        "static_consensus": {
            **consensus_report,
            "mask_path": str(mask_path.resolve()),
            "mask_sha256": sha256_file(mask_path),
        },
        "base_gauge_fit": gauge_fit,
        "background_shift_controls": {
            "controls": controls,
            "decision": shift,
        },
        "promotion_gates": gates,
        "candidate": candidate,
        "future_heldout_target_selection": {
            "status": (
                "allowed_only_after_candidate_freeze"
                if candidate is not None
                else "not_recomputed_no_promoted_camera"
            ),
            "selected_targets": [],
            "hardware_authority": False,
        },
        "residual_unobservable_dof": (
            None
            if candidate is not None
            else {
                "dimension": 2,
                "single_excitation_axis": PAN_JOINT,
                "coordinates": axis_report["gauge_coordinates"],
                "why_base_edges_did_not_resolve": (
                    "multiple globally incompatible gauge values fit the "
                    "unsegmented static edge consensus with similarly weak "
                    "reprojection; local gauge rank does not establish "
                    "global semantic correspondence"
                ),
            }
        ),
        "terminal_missing_datum": (
            None
            if candidate is not None
            else (
                "one metric fixed-base observation tied to exact CAD and "
                "not explainable by background edges, sufficient to fix "
                "rotation about and translation along the shoulder-pan axis"
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
    result["result_digest"] = canonical_sha256(result)
    (output_directory / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
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

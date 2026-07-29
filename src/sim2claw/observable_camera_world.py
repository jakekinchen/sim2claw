"""Gauge-fixed C922 camera/world evaluation from the retained board lattice."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from scipy.optimize import least_squares

from .bidirectional_registration_rigid_fit import _lattice
from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .paths import REPO_ROOT


SCHEMA = "sim2claw.observable_c922_camera_world_contract.v1"
RECEIPT_SCHEMA = "sim2claw.observable_c922_camera_world_receipt.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "observable_c922_camera_world_v1.json"
)
OUTPUT_PATH = (
    REPO_ROOT / "outputs" / "observable_c922_camera_world_v1" / "receipt.json"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _bound_path(binding: dict[str, Any], *, root: Path, label: str) -> Path:
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
    path = _bound_path(binding, root=root, label=label)
    return load_json_object(path, label=label)


def load_camera_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="observable C922 camera contract")
    _require(contract.get("schema_version") == SCHEMA, "unsupported camera contract")
    sources = contract.get("sources")
    _require(isinstance(sources, dict) and sources, "camera sources are missing")
    for source_id, binding in sources.items():
        _require(isinstance(binding, dict), f"invalid source binding: {source_id}")
        _bound_path(binding, root=root, label=source_id)
    family = contract.get("physical_pinhole_family")
    _require(isinstance(family, dict), "physical pinhole family is missing")
    _require(family.get("square_pixels") is True, "square-pixel policy changed")
    _require(float(family.get("skew_px", 1.0)) == 0.0, "skew policy changed")
    _require(
        family.get("distortion_coefficients") == [0.0] * 5,
        "distortion policy changed",
    )
    _require(
        "task_outcome" in family.get("forbidden_fit_fields", []),
        "task outcome entered camera fit",
    )
    validation = contract.get("validation_policy")
    _require(
        isinstance(validation, dict)
        and validation.get("pristine_heldout_available") is False
        and validation.get("exact_intrinsic_calibration_possible") is False
        and validation.get(
            "known_outcome_validation_reuse_allowed_for_camera_promotion"
        )
        is False,
        "camera validation ceiling changed",
    )
    boundaries = contract.get("proof_boundaries")
    authority = contract.get("authority")
    _require(
        isinstance(boundaries, dict) and boundaries and not any(boundaries.values()),
        "camera proof boundary widened",
    )
    _require(
        isinstance(authority, dict) and authority and not any(authority.values()),
        "camera authority widened",
    )
    return contract


def project_points(
    object_points: np.ndarray,
    focal_px: float,
    principal_point_px: np.ndarray,
    rotation_vector: np.ndarray,
    translation: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    rotation, _ = cv2.Rodrigues(np.asarray(rotation_vector, dtype=np.float64))
    camera_points = (
        np.asarray(object_points, dtype=np.float64) @ rotation.T
        + np.asarray(translation, dtype=np.float64)
    )
    normalized = camera_points[:, :2] / camera_points[:, 2:3]
    projected = normalized * float(focal_px) + np.asarray(
        principal_point_px, dtype=np.float64
    )
    return projected, camera_points[:, 2]


def fit_square_pixel_camera(
    board_xy_m: np.ndarray,
    image_points_px: np.ndarray,
    *,
    principal_point_px: np.ndarray,
    initial_focal_px: float,
    minimum_focal_px: float,
    maximum_focal_px: float,
) -> dict[str, Any]:
    board_xy = np.asarray(board_xy_m, dtype=np.float64)
    image = np.asarray(image_points_px, dtype=np.float64)
    _require(
        board_xy.ndim == 2
        and board_xy.shape[1] == 2
        and image.shape == board_xy.shape
        and len(board_xy) >= 6,
        "board correspondence shape changed",
    )
    _require(
        np.isfinite(board_xy).all() and np.isfinite(image).all(),
        "board correspondences are not finite",
    )
    object_points = np.column_stack((board_xy, np.zeros(len(board_xy))))
    principal = np.asarray(principal_point_px, dtype=np.float64)
    initial_camera = np.asarray(
        [
            [initial_focal_px, 0.0, principal[0]],
            [0.0, initial_focal_px, principal[1]],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    success, initial_rotation, initial_translation = cv2.solvePnP(
        object_points,
        image,
        initial_camera,
        np.zeros(5, dtype=np.float64),
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    _require(bool(success), "initial planar camera pose failed")

    def residual(values: np.ndarray) -> np.ndarray:
        projected, _ = project_points(
            object_points,
            values[0],
            principal,
            values[1:4],
            values[4:7],
        )
        return (projected - image).ravel()

    initial = np.concatenate(
        (
            [float(initial_focal_px)],
            initial_rotation.ravel(),
            initial_translation.ravel(),
        )
    )
    lower = np.asarray(
        [minimum_focal_px, -10.0, -10.0, -10.0, -5.0, -5.0, -5.0]
    )
    upper = np.asarray(
        [maximum_focal_px, 10.0, 10.0, 10.0, 5.0, 5.0, 5.0]
    )
    result = least_squares(
        residual,
        initial,
        bounds=(lower, upper),
        x_scale="jac",
        max_nfev=20_000,
        ftol=1e-13,
        xtol=1e-13,
        gtol=1e-13,
    )
    _require(bool(result.success), "bounded physical camera fit did not converge")
    focal = float(result.x[0])
    rotation_vector = result.x[1:4]
    translation = result.x[4:7]
    projected, depths = project_points(
        object_points, focal, principal, rotation_vector, translation
    )
    errors = np.linalg.norm(projected - image, axis=1)
    rotation, _ = cv2.Rodrigues(rotation_vector)
    singular = np.linalg.svd(result.jac, compute_uv=False)
    rank = int(np.linalg.matrix_rank(result.jac))
    condition = float(singular[0] / singular[-1])
    return {
        "focal_px": focal,
        "principal_point_px": principal.tolist(),
        "skew_px": 0.0,
        "focal_aspect_ratio": 1.0,
        "distortion_coefficients": [0.0] * 5,
        "rotation_board_to_camera": rotation.tolist(),
        "rotation_vector": rotation_vector.tolist(),
        "translation_board_to_camera_m": translation.tolist(),
        "camera_center_board_m": (-rotation.T @ translation).tolist(),
        "depths_m": depths.tolist(),
        "reprojection_errors_px": errors.tolist(),
        "reprojection_rms_px": float(np.sqrt(np.mean(errors**2))),
        "reprojection_max_px": float(np.max(errors)),
        "solver": {
            "success": bool(result.success),
            "cost": float(result.cost),
            "optimality": float(result.optimality),
            "jacobian_shape": list(result.jac.shape),
            "jacobian_rank": rank,
            "jacobian_singular_values": singular.tolist(),
            "jacobian_condition_number": condition,
            "active_mask": result.active_mask.tolist(),
        },
    }


def decompose_projective_camera(camera_matrix: np.ndarray) -> dict[str, Any]:
    camera = np.asarray(camera_matrix, dtype=np.float64)
    _require(camera.shape == (3, 4), "projective camera shape changed")
    intrinsic, rotation, homogeneous_center, *_ = cv2.decomposeProjectionMatrix(
        camera
    )
    _require(abs(float(intrinsic[2, 2])) > 1e-12, "projective intrinsic scale failed")
    intrinsic = intrinsic / float(intrinsic[2, 2])
    center = (homogeneous_center[:3] / homogeneous_center[3]).ravel()
    fx = float(intrinsic[0, 0])
    fy = float(intrinsic[1, 1])
    return {
        "intrinsic_matrix": intrinsic.tolist(),
        "rotation_world_to_camera": rotation.tolist(),
        "camera_center_world_m": center.tolist(),
        "fx_px": fx,
        "fy_px": fy,
        "absolute_skew_px": abs(float(intrinsic[0, 1])),
        "focal_aspect_ratio": abs(fx / fy),
        "principal_point_px": [
            float(intrinsic[0, 2]),
            float(intrinsic[1, 2]),
        ],
        "rotation_determinant": float(np.linalg.det(rotation)),
    }


def _board_frames(
    annotations: dict[str, Any], candidate_config: dict[str, Any]
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    world, image = _lattice(annotations, candidate_config)
    indices = np.asarray(
        annotations["board_lattice"]["direct_fit_intersection_indices"],
        dtype=np.float64,
    )
    playing_side = 0.3556
    board_xy = indices / 8.0 * playing_side
    by_index = {
        tuple(index.astype(int)): point
        for index, point in zip(indices, world, strict=True)
    }
    origin = np.asarray(by_index[(0, 0)], dtype=np.float64)
    axis_u = (np.asarray(by_index[(8, 0)]) - origin) / playing_side
    axis_v = (np.asarray(by_index[(0, 8)]) - origin) / playing_side
    axis_u = axis_u / np.linalg.norm(axis_u)
    axis_v = axis_v - axis_u * float(np.dot(axis_u, axis_v))
    axis_v = axis_v / np.linalg.norm(axis_v)
    normal = np.cross(axis_u, axis_v)
    normal = normal / np.linalg.norm(normal)
    board_to_world_rotation = np.column_stack((axis_u, axis_v, normal))
    return board_xy, image, {
        "origin_world_m": origin.tolist(),
        "rotation_board_to_world": board_to_world_rotation.tolist(),
    }


def evaluate_camera_world(
    contract: dict[str, Any], *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    sources = contract["sources"]
    annotations = _bound_json(
        sources["fit_annotations"], root=root, label="fit annotations"
    )
    candidate_wrapper = _bound_json(
        sources["candidate_manifest"], root=root, label="candidate manifest"
    )
    projective_candidate = _bound_json(
        sources["projective_candidate"], root=root, label="projective candidate"
    )
    prior_visual = _bound_json(
        sources["prior_visual_focal_diagnostic"],
        root=root,
        label="prior visual focal",
    )
    board_xy, board_image, board_frame = _board_frames(
        annotations, candidate_wrapper["candidate_config"]
    )
    family = contract["physical_pinhole_family"]
    physical = fit_square_pixel_camera(
        board_xy,
        board_image,
        principal_point_px=np.asarray(family["principal_point_px"]),
        initial_focal_px=float(family["initial_focal_px"]),
        minimum_focal_px=float(family["minimum_focal_px"]),
        maximum_focal_px=float(family["maximum_focal_px"]),
    )
    projective = decompose_projective_camera(
        np.asarray(projective_candidate["camera_matrix_3x4"], dtype=np.float64)
    )
    image_center = np.asarray(family["principal_point_px"], dtype=np.float64)
    projective_center = np.asarray(projective["principal_point_px"])
    projective_gates = contract["projective_plausibility_gates"]
    projective_checks = {
        "skew": projective["absolute_skew_px"]
        <= float(projective_gates["maximum_absolute_skew_px"]),
        "aspect": float(projective_gates["minimum_focal_aspect_ratio"])
        <= projective["focal_aspect_ratio"]
        <= float(projective_gates["maximum_focal_aspect_ratio"]),
        "principal_point": float(np.linalg.norm(projective_center - image_center))
        <= float(projective_gates["maximum_principal_point_center_distance_px"]),
        "proper_rotation": abs(projective["rotation_determinant"] - 1.0)
        <= float(projective_gates["proper_rotation_tolerance"]),
    }
    projective["checks"] = projective_checks
    projective["physically_plausible"] = bool(all(projective_checks.values()))

    gates = contract["physical_model_gates"]
    determinant = float(
        np.linalg.det(np.asarray(physical["rotation_board_to_camera"]))
    )
    focal = float(physical["focal_px"])
    physical_checks = {
        "board_rms": physical["reprojection_rms_px"]
        <= float(gates["maximum_board_reprojection_rms_px"]),
        "board_max": physical["reprojection_max_px"]
        <= float(gates["maximum_board_reprojection_max_px"]),
        "positive_depth": float(
            np.mean(np.asarray(physical["depths_m"]) > 0.0)
        )
        >= float(gates["minimum_positive_depth_fraction"]),
        "proper_rotation": abs(determinant - 1.0)
        <= float(gates["proper_rotation_tolerance"]),
        "jacobian_rank": int(physical["solver"]["jacobian_rank"])
        >= int(gates["minimum_jacobian_rank"]),
        "jacobian_condition": float(
            physical["solver"]["jacobian_condition_number"]
        )
        <= float(gates["maximum_jacobian_condition_number"]),
        "focal_not_at_bound": (
            focal - float(family["minimum_focal_px"])
            >= float(gates["focal_bound_margin_px"])
            and float(family["maximum_focal_px"]) - focal
            >= float(gates["focal_bound_margin_px"])
        ),
    }
    physical["rotation_determinant"] = determinant
    physical["horizontal_fov_degrees"] = float(
        2.0
        * np.degrees(
            np.arctan(float(contract["camera_identity"]["width"]) / (2.0 * focal))
        )
    )
    physical["vertical_fov_degrees"] = float(
        2.0
        * np.degrees(
            np.arctan(float(contract["camera_identity"]["height"]) / (2.0 * focal))
        )
    )
    physical["checks"] = physical_checks
    physical["bounded_model_accepted"] = bool(all(physical_checks.values()))

    rotation_board_to_world = np.asarray(
        board_frame["rotation_board_to_world"], dtype=np.float64
    )
    origin_world = np.asarray(board_frame["origin_world_m"], dtype=np.float64)
    rotation_board_to_camera = np.asarray(
        physical["rotation_board_to_camera"], dtype=np.float64
    )
    rotation_world_to_board = rotation_board_to_world.T
    rotation_world_to_camera = rotation_board_to_camera @ rotation_world_to_board
    translation_board_to_camera = np.asarray(
        physical["translation_board_to_camera_m"], dtype=np.float64
    )
    translation_world_to_camera = (
        translation_board_to_camera - rotation_world_to_camera @ origin_world
    )
    camera_center_world = (
        -rotation_world_to_camera.T @ translation_world_to_camera
    )
    physical["task_world_extrinsic"] = {
        "rotation_world_to_camera": rotation_world_to_camera.tolist(),
        "translation_world_to_camera_m": translation_world_to_camera.tolist(),
        "camera_center_world_m": camera_center_world.tolist(),
        "world_frame": "current_workcell_nominal_board_gauge",
        "metric_authority": "task_plane_nominal_only",
    }

    accepted = physical["bounded_model_accepted"]
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "contract_sha256": (
            sha256_file(CONTRACT_PATH)
            if root == REPO_ROOT and CONTRACT_PATH.is_file()
            else canonical_digest(contract)
        ),
        "camera_identity": contract["camera_identity"],
        "fit": {
            "board_correspondence_count": len(board_xy),
            "board_frame": board_frame,
            "fit_input": "frozen_v04_board_lattice_only",
            "robot_jaw_or_outcome_rows_consumed": 0,
        },
        "projective_candidate_diagnostic": projective,
        "physical_pinhole": physical,
        "prior_visual_diagnostic": {
            "focal_px": prior_visual["pinhole_angle_transfer"]["focal_length_px"],
            "difference_from_physical_fit_px": focal
            - float(
                prior_visual["pinhole_angle_transfer"]["focal_length_px"]
            ),
            "used_as_optimizer_start_only": True,
            "promotion_authority": False,
        },
        "validation": {
            **contract["validation_policy"],
            "known_outcome_validation_receipt_sha256": sources[
                "known_outcome_validation_receipt"
            ]["sha256"],
        },
        "exact_intrinsic_calibration_approved": False,
        "bounded_camera_world_model_accepted": accepted,
        "result": (
            "BOUNDED_CAMERA_WORLD_ACCEPTED_EXACT_INTRINSICS_UNIDENTIFIED"
            if accepted
            else "TERMINAL_BOUNDED_CAMERA_MODEL_NEGATIVE"
        ),
        "proof_boundaries": contract["proof_boundaries"],
        "authority": contract["authority"],
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def build_camera_world_receipt(
    contract_path: Path = CONTRACT_PATH,
    output_path: Path = OUTPUT_PATH,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_camera_contract(contract_path, root=root)
    receipt = evaluate_camera_world(contract, root=root)
    atomic_write_json(output_path, receipt)
    return receipt


__all__ = [
    "CONTRACT_PATH",
    "OUTPUT_PATH",
    "build_camera_world_receipt",
    "decompose_projective_camera",
    "evaluate_camera_world",
    "fit_square_pixel_camera",
    "load_camera_contract",
]

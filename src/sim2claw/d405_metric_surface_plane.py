"""Offline metric surface-plane diagnostic for accepted D405 artifacts.

This module reconstructs metric points from extracted depth CSVs and the
accepted capture receipt's enumerated depth intrinsics. It also reuses the
nonmetric RGB grid diagnostic to preserve the partial-grid boundary. It opens
no camera or robot and grants no board origin, registration, motion, or task
authority.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from .d405_board_grid_visibility import diagnose_board_grid_visibility
from .learning_factory_artifacts import atomic_write_json, sha256_file
from .paths import REPO_ROOT


CONTRACT_PATH = (
    REPO_ROOT / "configs" / "evaluations" / "d405_metric_surface_plane_v1.json"
)
CONTRACT_SCHEMA = "sim2claw.d405_metric_surface_plane_contract.v1"
RECEIPT_SCHEMA = "sim2claw.d405_metric_surface_plane_receipt.v1"


class D405MetricSurfacePlaneError(RuntimeError):
    """The metric-plane input lineage or evaluation is invalid."""


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise D405MetricSurfacePlaneError(
            f"cannot read metric-plane contract {path}: {error}"
        ) from error
    if value.get("schema_version") != CONTRACT_SCHEMA:
        raise D405MetricSurfacePlaneError("unexpected metric-plane contract schema")
    authority = value.get("authority")
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise D405MetricSurfacePlaneError("metric-plane authority widened")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise D405MetricSurfacePlaneError(f"cannot read JSON artifact {path}: {error}") from error
    if not isinstance(value, dict):
        raise D405MetricSurfacePlaneError(f"JSON artifact is not an object: {path}")
    return value


def _capture_artifact_hash_map(receipt: dict[str, Any]) -> dict[str, str]:
    artifacts = receipt.get("lineage", {}).get("capture_artifacts")
    if not isinstance(artifacts, list):
        raise D405MetricSurfacePlaneError("capture receipt has no artifact hash inventory")
    result: dict[str, str] = {}
    for item in artifacts:
        if isinstance(item, dict) and isinstance(item.get("path"), str):
            result[item["path"]] = str(item.get("sha256", ""))
    return result


def _validate_capture_lineage(
    capture_dir: Path,
    capture_receipt_path: Path,
    capture_receipt: dict[str, Any],
    contract: dict[str, Any],
) -> tuple[dict[str, Any], list[Path], list[Path], list[dict[str, Any]]]:
    checks = {
        "receipt_schema": capture_receipt.get("schema_version")
        == contract["required_capture_receipt_schema"],
        "receipt_proof_class": capture_receipt.get("proof_class")
        == contract["required_capture_proof_class"],
        "receipt_passed": capture_receipt.get("verdict", {}).get("passed") is True,
        "receipt_board_registration_false": capture_receipt.get("verdict", {}).get(
            "board_registration_authority"
        )
        is False,
        "receipt_task_authority_false": capture_receipt.get("verdict", {}).get(
            "task_authority"
        )
        is False,
        "receipt_camera_or_robot_access_false": capture_receipt.get(
            "camera_or_robot_accessed_by_evaluator"
        )
        is False,
        "receipt_capture_directory": Path(
            capture_receipt.get("lineage", {}).get("capture_directory", "")
        ).resolve()
        == capture_dir,
    }
    if not all(checks.values()):
        failed = [key for key, passed in checks.items() if not passed]
        raise D405MetricSurfacePlaneError(
            "accepted capture lineage failed closed: " + ", ".join(failed)
        )

    intrinsics = capture_receipt.get("calibration", {}).get("intrinsics", {}).get(
        "depth"
    )
    if not isinstance(intrinsics, dict):
        raise D405MetricSurfacePlaneError("accepted receipt has no depth intrinsics")
    coefficients = intrinsics.get("distortion_coefficients")
    if (
        intrinsics.get("width") != 848
        or intrinsics.get("height") != 480
        or intrinsics.get("distortion_model") != "Brown Conrady"
        or not isinstance(coefficients, list)
        or len(coefficients) != 5
        or any(float(value) != 0.0 for value in coefficients)
    ):
        raise D405MetricSurfacePlaneError(
            "depth deprojection requires accepted zero-distortion 848x480 intrinsics"
        )

    csv_items = capture_receipt.get("extracted", {}).get(
        "metric_depth_csv_statistics"
    )
    if (
        not isinstance(csv_items, list)
        or len(csv_items) < int(contract["minimum_depth_frame_count"])
    ):
        raise D405MetricSurfacePlaneError("too few accepted metric depth CSV frames")
    csv_paths = [capture_dir / str(item["path"]) for item in csv_items]
    color_paths = sorted((capture_dir / "extracted" / "color").glob("*.png"))
    if len(color_paths) < int(contract["minimum_depth_frame_count"]):
        raise D405MetricSurfacePlaneError("too few extracted RGB frames")

    expected_hashes = _capture_artifact_hash_map(capture_receipt)
    consumed: list[dict[str, Any]] = [
        {
            "path": str(capture_receipt_path),
            "sha256": sha256_file(capture_receipt_path),
            "role": "accepted_stationary_rgbd_receipt",
        }
    ]
    for role, paths in (("metric_depth_csv", csv_paths), ("rgb_image", color_paths)):
        for path in paths:
            if not path.is_file():
                raise D405MetricSurfacePlaneError(f"accepted artifact missing: {path}")
            relative = str(path.relative_to(capture_dir))
            actual = sha256_file(path)
            if expected_hashes.get(relative) != actual:
                raise D405MetricSurfacePlaneError(
                    f"accepted artifact hash mismatch: {relative}"
                )
            consumed.append({"path": relative, "sha256": actual, "role": role})
    return intrinsics, csv_paths, color_paths, consumed


def _deproject_depth(
    depth_m: np.ndarray,
    intrinsics: dict[str, Any],
    depth_range_m: tuple[float, float],
    *,
    stride: int = 1,
) -> tuple[np.ndarray, int]:
    if depth_m.ndim != 2:
        raise D405MetricSurfacePlaneError("depth CSV must be a two-dimensional array")
    height, width = depth_m.shape
    if [width, height] != [intrinsics["width"], intrinsics["height"]]:
        raise D405MetricSurfacePlaneError(
            f"depth shape {width}x{height} does not match accepted intrinsics"
        )
    sampled = depth_m[::stride, ::stride]
    rows, columns = np.indices(sampled.shape)
    u = columns * stride
    v = rows * stride
    low, high = depth_range_m
    valid = np.isfinite(sampled) & (sampled >= low) & (sampled <= high)
    z = sampled[valid]
    fx, fy = (float(value) for value in intrinsics["focal_length_px"])
    ppx, ppy = (float(value) for value in intrinsics["principal_point_px"])
    points = np.column_stack(
        (
            (u[valid] - ppx) * z / fx,
            (v[valid] - ppy) * z / fy,
            z,
        )
    )
    return points, int(np.count_nonzero(valid))


def _tls_plane(points: np.ndarray) -> tuple[np.ndarray, float, np.ndarray]:
    if len(points) < 3:
        raise D405MetricSurfacePlaneError("too few points to fit a plane")
    centroid = np.mean(points, axis=0)
    covariance = (points - centroid).T @ (points - centroid) / len(points)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    normal = eigenvectors[:, int(np.argmin(eigenvalues))]
    if normal[2] < 0.0:
        normal *= -1.0
    offset = -float(normal @ centroid)
    return normal, offset, centroid


def fit_metric_surface_plane(
    depth_m: np.ndarray,
    intrinsics: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    """Fit the dominant metric plane with deterministic RANSAC and TLS."""
    depth_range = tuple(float(value) for value in contract["depth_range_m"])
    full_points, valid_count = _deproject_depth(depth_m, intrinsics, depth_range)
    sample_points, _ = _deproject_depth(
        depth_m,
        intrinsics,
        depth_range,
        stride=int(contract["sample_stride_px"]),
    )
    valid_fraction = valid_count / depth_m.size
    if len(sample_points) < 3:
        raise D405MetricSurfacePlaneError("too few sampled depth points")

    rng = np.random.default_rng(int(contract["ransac_seed"]))
    threshold = float(contract["ransac_inlier_threshold_m"])
    best: tuple[int, float, np.ndarray, float] | None = None
    for _ in range(int(contract["ransac_iterations"])):
        trial = sample_points[rng.choice(len(sample_points), 3, replace=False)]
        normal = np.cross(trial[1] - trial[0], trial[2] - trial[0])
        magnitude = float(np.linalg.norm(normal))
        if magnitude <= 1e-12:
            continue
        normal /= magnitude
        offset = -float(normal @ trial[0])
        distances = np.abs(sample_points @ normal + offset)
        inlier_count = int(np.count_nonzero(distances <= threshold))
        inlier_mean = float(np.mean(distances[distances <= threshold]))
        score = (inlier_count, -inlier_mean)
        if best is None or score > (best[0], best[1]):
            best = (inlier_count, -inlier_mean, normal, offset)
    if best is None:
        raise D405MetricSurfacePlaneError("RANSAC found no nondegenerate plane")

    normal, offset = best[2], best[3]
    final_threshold = float(contract["final_inlier_threshold_m"])
    for points in (sample_points, full_points, full_points):
        inliers = np.abs(points @ normal + offset) <= final_threshold
        normal, offset, _ = _tls_plane(points[inliers])

    signed_residuals = full_points @ normal + offset
    inliers = np.abs(signed_residuals) <= final_threshold
    inlier_points = full_points[inliers]
    inlier_residuals = signed_residuals[inliers]
    normal, offset, centroid = _tls_plane(inlier_points)
    inlier_residuals = inlier_points @ normal + offset
    absolute_residuals = np.abs(inlier_residuals)
    z = inlier_points[:, 2]
    return {
        "image_shape": list(depth_m.shape),
        "valid_pixel_count": valid_count,
        "valid_pixel_fraction": valid_fraction,
        "plane_inlier_count": int(len(inlier_points)),
        "plane_inlier_fraction_of_valid": float(len(inlier_points) / valid_count),
        "plane_inlier_fraction_of_image": float(len(inlier_points) / depth_m.size),
        "centroid_camera_m": centroid.tolist(),
        "normal_camera_unit": normal.tolist(),
        "plane_equation": {
            "convention": "normal_dot_point_plus_offset_equals_zero",
            "offset_m": offset,
        },
        "camera_optical_origin_perpendicular_distance_m": abs(offset),
        "residuals_m": {
            "rms": float(np.sqrt(np.mean(inlier_residuals**2))),
            "p95_absolute": float(np.percentile(absolute_residuals, 95)),
            "maximum_absolute": float(np.max(absolute_residuals)),
        },
        "inlier_camera_z_range_m": {
            "minimum": float(np.min(z)),
            "p01": float(np.percentile(z, 1)),
            "median": float(np.median(z)),
            "p99": float(np.percentile(z, 99)),
            "maximum": float(np.max(z)),
        },
    }


def _cross_frame_stability(planes: list[dict[str, Any]]) -> dict[str, float]:
    angles: list[float] = []
    offset_drifts: list[float] = []
    for first, second in zip(planes, planes[1:]):
        first_normal = np.asarray(first["normal_camera_unit"], dtype=np.float64)
        second_normal = np.asarray(second["normal_camera_unit"], dtype=np.float64)
        dot = float(np.clip(first_normal @ second_normal, -1.0, 1.0))
        angles.append(math.degrees(math.acos(dot)))
        first_offset = float(first["plane_equation"]["offset_m"])
        second_offset = float(second["plane_equation"]["offset_m"])
        offset_drifts.append(abs(second_offset - first_offset))
    return {
        "maximum_adjacent_normal_angle_degrees": max(angles, default=0.0),
        "maximum_adjacent_plane_offset_drift_m": max(offset_drifts, default=0.0),
    }


def evaluate_d405_metric_surface_plane(
    capture_dir: Path,
    *,
    capture_receipt_path: Path | None = None,
    output_path: Path | None = None,
    contract_path: Path = CONTRACT_PATH,
) -> dict[str, Any]:
    """Evaluate existing metric depth and RGB artifacts without hardware access."""
    capture_dir = capture_dir.resolve()
    capture_receipt_path = (
        capture_dir / "evaluation" / "receipt.json"
        if capture_receipt_path is None
        else capture_receipt_path.resolve()
    )
    contract = load_contract(contract_path)
    capture_receipt = _load_json(capture_receipt_path)
    intrinsics, csv_paths, color_paths, consumed = _validate_capture_lineage(
        capture_dir, capture_receipt_path, capture_receipt, contract
    )

    frames: list[dict[str, Any]] = []
    for path in csv_paths:
        depth = np.loadtxt(path, delimiter=",", dtype=np.float64)
        frames.append(
            {
                "path": str(path.relative_to(capture_dir)),
                **fit_metric_surface_plane(depth, intrinsics, contract),
            }
        )
    stability = _cross_frame_stability(frames)

    grid_observations = []
    for path in color_paths:
        diagnostic = diagnose_board_grid_visibility(path)
        grid_observations.append(
            {
                "path": str(path.relative_to(capture_dir)),
                "input_sha256": diagnostic["input_lineage"]["sha256"],
                "classification": diagnostic["verdict"]["classification"],
                "passed": diagnostic["verdict"]["passed"],
                "direct_row_line_count": diagnostic["best_frame"]["row_axis"][
                    "directly_supported_grid_line_count"
                ],
                "direct_column_line_count": diagnostic["best_frame"]["column_axis"][
                    "directly_supported_grid_line_count"
                ],
                "outer_playing_grid_boundary_support": diagnostic[
                    "outer_playing_grid_boundary_support"
                ],
                "full_grid_registration": False,
            }
        )

    checks: dict[str, bool] = {
        "minimum_depth_frames": len(frames)
        >= int(contract["minimum_depth_frame_count"]),
        "valid_pixel_fraction": all(
            frame["valid_pixel_fraction"]
            >= float(contract["minimum_valid_pixel_fraction"])
            for frame in frames
        ),
        "plane_inlier_fraction": all(
            frame["plane_inlier_fraction_of_valid"]
            >= float(contract["minimum_plane_inlier_fraction_of_valid"])
            for frame in frames
        ),
        "plane_rms_residual": all(
            frame["residuals_m"]["rms"]
            <= float(contract["maximum_plane_rms_residual_m"])
            for frame in frames
        ),
        "plane_p95_residual": all(
            frame["residuals_m"]["p95_absolute"]
            <= float(contract["maximum_plane_p95_absolute_residual_m"])
            for frame in frames
        ),
        "cross_frame_normal_angle": stability[
            "maximum_adjacent_normal_angle_degrees"
        ]
        <= float(contract["maximum_cross_frame_normal_angle_degrees"]),
        "cross_frame_plane_offset": stability[
            "maximum_adjacent_plane_offset_drift_m"
        ]
        <= float(contract["maximum_cross_frame_plane_offset_drift_m"]),
        "camera_origin_plane_distance": all(
            float(contract["camera_origin_plane_distance_range_m"][0])
            <= frame["camera_optical_origin_perpendicular_distance_m"]
            <= float(contract["camera_origin_plane_distance_range_m"][1])
            for frame in frames
        ),
        "rgb_grid_remains_partial": all(
            item["classification"]
            == contract["required_rgb_grid_classification"]
            and item["passed"] is False
            and item["full_grid_registration"] is False
            for item in grid_observations
        ),
    }
    passed = all(checks.values())
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "proof_class": contract["proof_class"],
        "camera_or_robot_accessed": False,
        "metric": True,
        "surface_semantics": (
            "dominant_visible_surface_plane_not_semantic_board_plane"
        ),
        "authority": contract["authority"],
        "lineage": {
            "capture_directory": str(capture_dir),
            "accepted_capture_receipt": {
                "path": str(capture_receipt_path),
                "sha256": sha256_file(capture_receipt_path),
                "proof_class": capture_receipt["proof_class"],
                "verdict": capture_receipt["verdict"]["classification"],
            },
            "contract": {
                "path": str(contract_path.resolve()),
                "sha256": sha256_file(contract_path),
            },
            "consumed_artifacts": consumed,
            "depth_intrinsics_source": (
                "accepted capture receipt, enumerated D405 848x480 Z16 intrinsics"
            ),
        },
        "depth_intrinsics": intrinsics,
        "frames": frames,
        "cross_frame_stability": stability,
        "metric_height_and_range": {
            "camera_optical_origin_to_plane_distance_m": [
                frame["camera_optical_origin_perpendicular_distance_m"]
                for frame in frames
            ],
            "camera_z_ranges_m": [
                frame["inlier_camera_z_range_m"] for frame in frames
            ],
            "no_robot_or_board_height_interpretation": True,
        },
        "rgb_grid_visibility": {
            "diagnostic_reused": "d405_board_grid_visibility_v1",
            "observations": grid_observations,
            "partial_grid": all(not item["passed"] for item in grid_observations),
            "full_grid_registration": False,
        },
        "checks": checks,
        "verdict": {
            "passed": passed,
            "classification": (
                "physical_stationary_metric_surface_plane_observed"
                if passed
                else "metric_surface_plane_observation_not_accepted_fail_closed"
            ),
            "failure_reasons": [
                key for key, check_passed in checks.items() if not check_passed
            ],
            "full_grid_registration": False,
            "camera_to_robot_extrinsic": False,
            "board_origin": False,
            "task_authority": False,
            "motion_authority": False,
        },
    }
    if output_path is not None:
        atomic_write_json(output_path, receipt)
    return receipt

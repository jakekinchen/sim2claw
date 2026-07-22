"""Nominal-AprilTag-conditioned metric plausibility for the IMG_5349 scene.

This evaluator answers a narrow question: if the visible tag-0 black border
has its source PDF's nominal 80 mm side, what playing-side lengths does the
visible chessboard imply?  The tag was not measured after printing, so the
result may reject or support a scale hypothesis but cannot grant physical
metric calibration authority.

The 3DGS is bound only to prove scene identity.  Its monocular coordinates are
not used as a ruler.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT


CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "pawn_scene_metric_scale_plausibility_v1.json"
)
SCHEMA = "sim2claw.pawn_scene_metric_scale_plausibility.v1"
RECEIPT_SCHEMA = "sim2claw.pawn_scene_metric_scale_plausibility_receipt.v1"


class MetricScalePlausibilityError(RuntimeError):
    """The source evidence or fail-closed contract is invalid."""


def load_metric_scale_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MetricScalePlausibilityError(f"cannot read contract {path}: {error}") from error
    if contract.get("schema_version") != SCHEMA:
        raise MetricScalePlausibilityError("unexpected metric-scale contract schema")
    authority = contract.get("authority")
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise MetricScalePlausibilityError("metric-scale authority widened")
    tag = contract.get("tag", {})
    if tag.get("physical_print_dimension_measured") is not False:
        raise MetricScalePlausibilityError("tag dimension must remain explicitly unmeasured")
    if tag.get("family") != "tag36h11" or int(tag.get("id", -1)) != 0:
        raise MetricScalePlausibilityError("unexpected fiducial family or id")
    plane = contract.get("plane_sensitivity", {})
    heights = [float(value) for value in plane.get("board_surface_above_tag_plane_m", [])]
    interval = [float(value) for value in plane.get("candidate_height_interval_m", [])]
    if len(heights) < 3 or len(interval) != 2 or not 0.0 <= interval[0] < interval[1]:
        raise MetricScalePlausibilityError("invalid board-plane sensitivity bracket")
    if any(not math.isfinite(value) for value in heights + interval):
        raise MetricScalePlausibilityError("non-finite board-plane sensitivity value")
    candidates = contract.get("candidate_hypotheses")
    if not isinstance(candidates, list) or len(candidates) < 2:
        raise MetricScalePlausibilityError("at least two scale hypotheses are required")
    return contract


def _camera(contract: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    camera = contract["camera"]
    matrix = np.asarray(
        (
            (camera["fx_px"], 0.0, camera["cx_px"]),
            (0.0, camera["fy_px"], camera["cy_px"]),
            (0.0, 0.0, 1.0),
        ),
        dtype=np.float64,
    )
    distortion = np.asarray(camera["distortion"], dtype=np.float64)
    if matrix.shape != (3, 3) or distortion.shape not in {(4,), (5,), (8,)}:
        raise MetricScalePlausibilityError("invalid camera calibration dimensions")
    return matrix, distortion


def _detect_tag(
    image: np.ndarray, contract: dict[str, Any]
) -> tuple[np.ndarray, dict[str, Any]]:
    tag = contract["tag"]
    scale = float(tag["detector_downscale"])
    resized = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    parameters = cv2.aruco.DetectorParameters()
    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    detector = cv2.aruco.ArucoDetector(
        cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11),
        parameters,
    )
    corners, ids, _rejected = detector.detectMarkers(gray)
    if ids is None:
        raise MetricScalePlausibilityError("no AprilTag detected in the bound frame")
    target_id = int(tag["id"])
    matches = [
        np.asarray(raw, dtype=np.float64).reshape(4, 2) / scale
        for raw, raw_id in zip(corners, ids.reshape(-1), strict=True)
        if int(raw_id) == target_id
    ]
    if len(matches) != 1:
        raise MetricScalePlausibilityError(
            f"expected exactly one tag {target_id}, found {len(matches)}"
        )
    detected = matches[0]
    edge_lengths = np.linalg.norm(np.roll(detected, -1, axis=0) - detected, axis=1)
    mean_edge = float(np.mean(edge_lengths))
    if mean_edge < float(tag["minimum_mean_detected_edge_px"]):
        raise MetricScalePlausibilityError("detected tag is below the declared pixel-size gate")
    return detected, {
        "family": tag["family"],
        "id": target_id,
        "corners_px": detected.tolist(),
        "edge_lengths_px": edge_lengths.tolist(),
        "mean_edge_length_px": mean_edge,
        "detector_downscale": scale,
    }


def _segment_angle_degrees(segment: np.ndarray) -> float:
    x1, y1, x2, y2 = (float(value) for value in segment)
    angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
    while angle >= 90.0:
        angle -= 180.0
    while angle < -90.0:
        angle += 180.0
    return angle


def _fit_tls_line(points: np.ndarray) -> np.ndarray:
    if points.ndim != 2 or points.shape[1] != 2 or len(points) < 4:
        raise MetricScalePlausibilityError("too few segment endpoints for a grid line")
    center = np.mean(points, axis=0)
    _u, _s, vh = np.linalg.svd(points - center, full_matrices=False)
    direction = vh[0]
    normal = np.asarray((-direction[1], direction[0]), dtype=np.float64)
    normal /= np.linalg.norm(normal)
    line = np.asarray((normal[0], normal[1], -normal @ center), dtype=np.float64)
    if line[1] < 0.0 or (abs(line[1]) < 1e-12 and line[0] < 0.0):
        line *= -1.0
    return line


def _line_intersection(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    point = np.cross(first, second)
    if abs(float(point[2])) <= 1e-9:
        raise MetricScalePlausibilityError("board grid boundary lines are parallel")
    return point[:2] / point[2]


def _measure_board_grid(
    image: np.ndarray, contract: dict[str, Any]
) -> tuple[np.ndarray, dict[str, Any], list[np.ndarray], list[np.ndarray]]:
    settings = contract["board_grid_measurement"]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    kernel = int(settings["gaussian_kernel_px"])
    blurred = cv2.GaussianBlur(gray, (kernel, kernel), 0)
    edges = cv2.Canny(blurred, int(settings["canny_low"]), int(settings["canny_high"]))
    raw = cv2.HoughLinesP(
        edges,
        rho=float(settings["hough_rho_px"]),
        theta=math.radians(float(settings["hough_theta_degrees"])),
        threshold=int(settings["hough_threshold"]),
        minLineLength=float(settings["hough_min_line_length_px"]),
        maxLineGap=float(settings["hough_max_line_gap_px"]),
    )
    if raw is None:
        raise MetricScalePlausibilityError("Hough transform found no board segments")
    segments = np.asarray(raw, dtype=np.float64).reshape(-1, 4)
    tolerance = float(settings["segment_assignment_tolerance_px"])

    def fit_family(name: str) -> tuple[list[np.ndarray], list[int]]:
        family = settings[name]
        angle_low, angle_high = (float(value) for value in family["angle_degrees"])
        targets = [float(value) for value in family["intercept_targets_px"]]
        selected: list[tuple[np.ndarray, float]] = []
        for segment in segments:
            x1, y1, x2, y2 = segment
            angle = _segment_angle_degrees(segment)
            if not angle_low <= angle <= angle_high:
                continue
            if name == "row_family":
                if abs(x2 - x1) <= 1e-9:
                    continue
                reference = float(family["reference_x_px"])
                intercept = y1 + (y2 - y1) * (reference - x1) / (x2 - x1)
            else:
                if abs(y2 - y1) <= 1e-9:
                    continue
                reference = float(family["reference_y_px"])
                intercept = x1 + (x2 - x1) * (reference - y1) / (y2 - y1)
            selected.append((segment, float(intercept)))
        lines: list[np.ndarray] = []
        counts: list[int] = []
        for target in targets:
            matched = [segment for segment, value in selected if abs(value - target) <= tolerance]
            if len(matched) < 2:
                raise MetricScalePlausibilityError(
                    f"grid line target {target:.1f}px has only {len(matched)} matched segments"
                )
            endpoints = np.asarray(matched, dtype=np.float64).reshape(-1, 2)
            lines.append(_fit_tls_line(endpoints))
            counts.append(len(matched))
        return lines, counts

    row_lines, row_counts = fit_family("row_family")
    column_lines, column_counts = fit_family("column_family")
    expected = int(settings["expected_grid_line_count_per_axis"])
    if len(row_lines) != expected or len(column_lines) != expected:
        raise MetricScalePlausibilityError("board grid line count changed")
    corners = np.asarray(
        (
            _line_intersection(row_lines[0], column_lines[0]),
            _line_intersection(row_lines[0], column_lines[-1]),
            _line_intersection(row_lines[-1], column_lines[-1]),
            _line_intersection(row_lines[-1], column_lines[0]),
        ),
        dtype=np.float64,
    )
    return corners, {
        "method": settings["method"],
        "hough_segment_count": int(len(segments)),
        "row_segment_counts": row_counts,
        "column_segment_counts": column_counts,
        "row_lines_abc": [line.tolist() for line in row_lines],
        "column_lines_abc": [line.tolist() for line in column_lines],
        "playing_area_corners_px": corners.tolist(),
    }, row_lines, column_lines


def _solve_tag_pose(
    corners_px: np.ndarray, contract: dict[str, Any]
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    matrix, distortion = _camera(contract)
    side = float(contract["tag"]["detected_black_border_nominal_side_m"])
    half = side / 2.0
    object_points = np.asarray(
        ((-half, half, 0.0), (half, half, 0.0), (half, -half, 0.0), (-half, -half, 0.0)),
        dtype=np.float64,
    )
    success, rotation_vector, translation = cv2.solvePnP(
        object_points,
        corners_px,
        matrix,
        distortion,
        flags=cv2.SOLVEPNP_IPPE_SQUARE,
    )
    if not success:
        raise MetricScalePlausibilityError("tag pose solver failed")
    rotation, _ = cv2.Rodrigues(rotation_vector)
    projected, _ = cv2.projectPoints(
        object_points, rotation_vector, translation, matrix, distortion
    )
    residual = projected.reshape(-1, 2) - corners_px
    rms = float(np.sqrt(np.mean(np.sum(residual**2, axis=1))))
    if rms > float(contract["tag"]["maximum_pnp_reprojection_rms_px"]):
        raise MetricScalePlausibilityError(
            f"tag PnP reprojection RMS {rms:.3f}px exceeds the gate"
        )
    return rotation[:, 2], translation.reshape(3), {
        "translation_camera_m_under_nominal_tag": translation.reshape(3).tolist(),
        "plane_normal_camera": rotation[:, 2].tolist(),
        "reprojection_rms_px": rms,
    }


def intersect_image_rays_with_parallel_plane(
    image_points_px: np.ndarray,
    *,
    camera_matrix: np.ndarray,
    distortion: np.ndarray,
    plane_normal_camera: np.ndarray,
    tag_origin_camera: np.ndarray,
    board_height_above_tag_plane_m: float,
) -> np.ndarray:
    """Back-project pixels onto a plane parallel to and offset from the tag."""

    pixels = np.asarray(image_points_px, dtype=np.float64)
    normal = np.asarray(plane_normal_camera, dtype=np.float64).reshape(3)
    origin = np.asarray(tag_origin_camera, dtype=np.float64).reshape(3)
    if pixels.ndim != 2 or pixels.shape[1] != 2:
        raise MetricScalePlausibilityError("image points must be an Nx2 array")
    normal /= np.linalg.norm(normal)
    rays_xy = cv2.undistortPoints(
        pixels.reshape(-1, 1, 2), camera_matrix, distortion
    ).reshape(-1, 2)
    rays = np.column_stack((rays_xy, np.ones(len(rays_xy), dtype=np.float64)))
    plane_point = origin + float(board_height_above_tag_plane_m) * normal
    denominators = rays @ normal
    if np.any(np.abs(denominators) <= 1e-9):
        raise MetricScalePlausibilityError("camera ray is parallel to the board plane")
    distances = float(normal @ plane_point) / denominators
    if np.any(distances <= 0.0):
        raise MetricScalePlausibilityError("board plane projects behind the camera")
    return rays * distances[:, None]


def _plane_sensitivity(
    corners_px: np.ndarray,
    normal: np.ndarray,
    origin: np.ndarray,
    contract: dict[str, Any],
) -> list[dict[str, Any]]:
    matrix, distortion = _camera(contract)
    rows: list[dict[str, Any]] = []
    for height in contract["plane_sensitivity"]["board_surface_above_tag_plane_m"]:
        points = intersect_image_rays_with_parallel_plane(
            corners_px,
            camera_matrix=matrix,
            distortion=distortion,
            plane_normal_camera=normal,
            tag_origin_camera=origin,
            board_height_above_tag_plane_m=float(height),
        )
        edge_lengths = np.linalg.norm(np.roll(points, -1, axis=0) - points, axis=1)
        opposite_differences = np.abs(edge_lengths[:2] - edge_lengths[2:])
        rows.append(
            {
                "board_surface_above_tag_plane_m": float(height),
                "board_corners_camera_m": points.tolist(),
                "edge_lengths_m": edge_lengths.tolist(),
                "mean_playing_side_m": float(np.mean(edge_lengths)),
                "minimum_edge_m": float(np.min(edge_lengths)),
                "maximum_edge_m": float(np.max(edge_lengths)),
                "maximum_opposite_edge_disagreement_m": float(np.max(opposite_differences)),
            }
        )
    return rows


def _candidate_comparison(
    sensitivity: list[dict[str, Any]], contract: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    lower_height, upper_height = (
        float(value)
        for value in contract["plane_sensitivity"]["candidate_height_interval_m"]
    )
    bracket_rows = [
        row
        for row in sensitivity
        if lower_height - 1e-12 <= row["board_surface_above_tag_plane_m"] <= upper_height + 1e-12
    ]
    if len(bracket_rows) < 2:
        raise MetricScalePlausibilityError("sensitivity rows do not span the candidate height interval")
    means = [float(row["mean_playing_side_m"]) for row in bracket_rows]
    edges = [float(value) for row in bracket_rows for value in row["edge_lengths_m"]]
    nominal_tag_side = float(contract["tag"]["detected_black_border_nominal_side_m"])
    thresholds = contract["decision_thresholds"]
    consistent_limit = float(thresholds["maximum_nominal_tag_rescale_for_consistency_fraction"])
    inconsistent_limit = float(
        thresholds["minimum_nominal_tag_rescale_for_material_inconsistency_fraction"]
    )
    comparisons: list[dict[str, Any]] = []
    for candidate in contract["candidate_hypotheses"]:
        playing_side = float(candidate["playing_side_m"])
        required_tag_sides = [nominal_tag_side * playing_side / value for value in means]
        rescale_fractions = [value / nominal_tag_side - 1.0 for value in required_tag_sides]
        minimum_abs_rescale = min(abs(value) for value in rescale_fractions)
        comparisons.append(
            {
                **candidate,
                "absolute_error_to_mean_bracket_m": float(
                    0.0
                    if min(means) <= playing_side <= max(means)
                    else min(abs(playing_side - min(means)), abs(playing_side - max(means)))
                ),
                "inside_all_edge_envelope": min(edges) <= playing_side <= max(edges),
                "required_tag_black_side_range_m": [
                    float(min(required_tag_sides)),
                    float(max(required_tag_sides)),
                ],
                "required_tag_rescale_fraction_range": [
                    float(min(rescale_fractions)),
                    float(max(rescale_fractions)),
                ],
                "minimum_absolute_tag_rescale_fraction": float(minimum_abs_rescale),
                "nominal_print_consistent": minimum_abs_rescale <= consistent_limit,
                "materially_inconsistent_with_nominal_print": minimum_abs_rescale >= inconsistent_limit,
                "physical_metric_authority": False,
            }
        )
    summary = {
        "candidate_height_interval_m": [lower_height, upper_height],
        "mean_playing_side_bracket_m": [float(min(means)), float(max(means))],
        "all_edge_envelope_m": [float(min(edges)), float(max(edges))],
        "opposite_edge_disagreement_disclosed": True,
    }
    return comparisons, summary


def _draw_overlay(
    image: np.ndarray,
    *,
    tag_corners: np.ndarray,
    board_corners: np.ndarray,
    row_lines: list[np.ndarray],
    column_lines: list[np.ndarray],
    output_path: Path,
) -> None:
    overlay = image.copy()
    height, width = overlay.shape[:2]

    def line_endpoints(line: np.ndarray) -> tuple[tuple[int, int], tuple[int, int]]:
        a, b, c = (float(value) for value in line)
        if abs(b) >= abs(a):
            first = (0, int(round(-c / b)))
            last = (width - 1, int(round(-(a * (width - 1) + c) / b)))
        else:
            first = (int(round(-c / a)), 0)
            last = (int(round(-(b * (height - 1) + c) / a)), height - 1)
        return first, last

    for line in row_lines:
        cv2.line(overlay, *line_endpoints(line), (0, 220, 255), 2, cv2.LINE_AA)
    for line in column_lines:
        cv2.line(overlay, *line_endpoints(line), (255, 160, 0), 2, cv2.LINE_AA)
    cv2.polylines(
        overlay,
        [np.round(board_corners).astype(np.int32).reshape(-1, 1, 2)],
        True,
        (0, 255, 0),
        7,
        cv2.LINE_AA,
    )
    cv2.polylines(
        overlay,
        [np.round(tag_corners).astype(np.int32).reshape(-1, 1, 2)],
        True,
        (255, 0, 255),
        7,
        cv2.LINE_AA,
    )
    cv2.putText(
        overlay,
        "green=board playing area  magenta=tag0  lines=reviewed grid fit",
        (35, 70),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.1,
        (255, 255, 255),
        3,
        cv2.LINE_AA,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), overlay):
        raise MetricScalePlausibilityError(f"could not write overlay {output_path}")


def run_metric_scale_plausibility(
    *,
    frame_path: Path,
    source_video_path: Path,
    real_splat_path: Path,
    output_root: Path,
    contract_path: Path = CONTRACT_PATH,
) -> dict[str, Any]:
    """Run the source-bound conditional scale test and write its receipt."""

    contract = load_metric_scale_contract(contract_path)
    paths = {
        "frame": frame_path.resolve(),
        "source_video": source_video_path.resolve(),
        "real_splat": real_splat_path.resolve(),
    }
    expected = contract["source_bindings"]
    expected_hashes = {
        "frame": expected["frame_sha256"],
        "source_video": expected["source_video_sha256"],
        "real_splat": expected["real_splat_sha256"],
    }
    bindings: dict[str, Any] = {}
    for name, path in paths.items():
        if not path.is_file():
            raise MetricScalePlausibilityError(f"missing {name} source: {path}")
        observed = sha256_file(path)
        if observed != expected_hashes[name]:
            raise MetricScalePlausibilityError(f"{name} source digest changed")
        bindings[name] = {"path": str(path), "sha256": observed}
    image = cv2.imread(str(paths["frame"]), cv2.IMREAD_COLOR)
    if image is None:
        raise MetricScalePlausibilityError(f"could not read bound frame {paths['frame']}")
    observed_size = [int(image.shape[1]), int(image.shape[0])]
    if observed_size != [int(value) for value in expected["image_size_px"]]:
        raise MetricScalePlausibilityError("bound frame image size changed")

    tag_corners, tag_detection = _detect_tag(image, contract)
    board_corners, board_grid, row_lines, column_lines = _measure_board_grid(image, contract)
    normal, origin, pose = _solve_tag_pose(tag_corners, contract)
    sensitivity = _plane_sensitivity(board_corners, normal, origin, contract)
    comparisons, bracket = _candidate_comparison(sensitivity, contract)
    overlay_path = output_root.resolve() / "frame-000001-scale-evidence-overlay.png"
    _draw_overlay(
        image,
        tag_corners=tag_corners,
        board_corners=board_corners,
        row_lines=row_lines,
        column_lines=column_lines,
        output_path=overlay_path,
    )
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "contract": {
            "path": str(contract_path.resolve()),
            "sha256": sha256_file(contract_path),
        },
        "implementation": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "proof_class": "nominal_print_conditioned_metric_scale_plausibility",
        "source_bindings": bindings,
        "scene_identity": {
            "same_source_video_as_real_3dgs": True,
            "real_splat_used_as_metric_geometry": False,
            "real_splat_count": int(expected["real_splat_count"]),
        },
        "camera": contract["camera"],
        "tag_detection": {**tag_detection, **pose},
        "board_grid_measurement": board_grid,
        "plane_sensitivity": sensitivity,
        "candidate_bracket": bracket,
        "candidate_comparisons": comparisons,
        "decision": {
            "nominal_print_consistent_candidates": [
                row["id"] for row in comparisons if row["nominal_print_consistent"]
            ],
            "materially_inconsistent_candidates": [
                row["id"]
                for row in comparisons
                if row["materially_inconsistent_with_nominal_print"]
            ],
            "simulator_parameter_promotion_allowed": False,
            "physical_metric_scale_established": False,
            "interpretation": (
                "The result tests scale plausibility under the nominal printed tag design. "
                "It does not measure the printed tag or chessboard and cannot establish metric authority."
            ),
        },
        "artifacts": {"overlay_png": str(overlay_path)},
        "authority": contract["authority"],
        "limitations": [
            "tag_print_dimensions_are_nominal_design_values_not_post_print_measurements",
            "board_and_tag_are_assumed_parallel_with_a_declared_height_sensitivity",
            "board_boundary_fit_has_visible_opposite_edge_disagreement",
            "single_frame_lens_and_rolling_shutter_systematics_are_not_independently_bounded",
            "monocular_3dgs_is_scene_identity_evidence_not_metric_scale_evidence",
        ],
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    receipt_path = output_root.resolve() / "metric_scale_plausibility_receipt.json"
    atomic_write_json(receipt_path, receipt)
    return receipt

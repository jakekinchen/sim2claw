"""Offline, nonmetric visibility diagnostic for a D405 chessboard view.

This module never opens a camera or robot. It reports whether all four outer
playing-grid boundaries have direct Hough-segment/TLS support in adjacent
decoded frames. Missing boundaries are reported as requiring extrapolation;
the diagnostic never performs that extrapolation.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterator

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, sha256_file
from .paths import REPO_ROOT


CONTRACT_PATH = (
    REPO_ROOT / "configs" / "evaluations" / "d405_board_grid_visibility_v1.json"
)
CONTRACT_SCHEMA = "sim2claw.d405_board_grid_visibility_contract.v1"
RECEIPT_SCHEMA = "sim2claw.d405_board_grid_visibility_receipt.v1"


class BoardGridVisibilityError(RuntimeError):
    """The offline input or diagnostic contract is invalid."""


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BoardGridVisibilityError(f"cannot read contract {path}: {error}") from error
    if value.get("schema_version") != CONTRACT_SCHEMA:
        raise BoardGridVisibilityError("unexpected board-grid visibility contract schema")
    authority = value.get("authority")
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise BoardGridVisibilityError("board-grid visibility authority widened")
    if int(value.get("expected_grid_line_count_per_axis", 0)) != 9:
        raise BoardGridVisibilityError("diagnostic requires the nine lines of an 8x8 grid")
    if int(value.get("minimum_direct_segments_per_line", 0)) < 2:
        raise BoardGridVisibilityError("direct support requires multiple segments")
    if int(value.get("minimum_adjacent_settled_frames", 0)) < 2:
        raise BoardGridVisibilityError("adjacent-frame gate was weakened")
    return value


def _segment_angle_degrees(segment: np.ndarray) -> float:
    x1, y1, x2, y2 = (float(value) for value in segment)
    angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
    while angle >= 90.0:
        angle -= 180.0
    while angle < -90.0:
        angle += 180.0
    return angle


def _fit_tls_line(segments: list[np.ndarray]) -> tuple[np.ndarray, float, float]:
    points = np.asarray(segments, dtype=np.float64).reshape(-1, 2)
    if len(points) < 4:
        raise BoardGridVisibilityError("too few endpoints for direct TLS support")
    center = np.mean(points, axis=0)
    _u, _s, vh = np.linalg.svd(points - center, full_matrices=False)
    direction = vh[0]
    normal = np.asarray((-direction[1], direction[0]), dtype=np.float64)
    normal /= np.linalg.norm(normal)
    residuals = (points - center) @ normal
    line = np.asarray((normal[0], normal[1], -normal @ center), dtype=np.float64)
    if line[1] < 0.0 or (abs(float(line[1])) < 1e-12 and line[0] < 0.0):
        line *= -1.0
    return (
        line,
        float(np.sqrt(np.mean(residuals**2))),
        float(np.max(np.abs(residuals))),
    )


def _line_intersection(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    point = np.cross(first, second)
    if abs(float(point[2])) <= 1e-9:
        raise BoardGridVisibilityError("candidate outer grid lines are parallel")
    return point[:2] / point[2]


def _cluster_candidates(
    candidates: list[tuple[float, float, np.ndarray]],
    *,
    tolerance_px: float,
    minimum_segments: int,
    maximum_tls_rms_px: float,
) -> list[dict[str, Any]]:
    groups: list[list[tuple[float, float, np.ndarray]]] = []
    for candidate in sorted(candidates, key=lambda item: item[0]):
        if not groups:
            groups.append([candidate])
            continue
        weighted_center = sum(value * length for value, length, _ in groups[-1]) / sum(
            length for _, length, _ in groups[-1]
        )
        if abs(candidate[0] - weighted_center) <= tolerance_px:
            groups[-1].append(candidate)
        else:
            groups.append([candidate])

    clusters: list[dict[str, Any]] = []
    for group in groups:
        segments = [segment for _, _, segment in group]
        lengths = [length for _, length, _ in group]
        if len(segments) >= minimum_segments:
            line, rms, maximum = _fit_tls_line(segments)
            line_value: list[float] | None = line.tolist()
        else:
            rms = float("inf")
            maximum = float("inf")
            line_value = None
        intercept = sum(value * length for value, length, _ in group) / sum(lengths)
        clusters.append(
            {
                "reference_intercept_px": float(intercept),
                "segment_count": len(segments),
                "total_segment_length_px": float(sum(lengths)),
                "tls_rms_residual_px": rms if math.isfinite(rms) else None,
                "tls_maximum_residual_px": maximum if math.isfinite(maximum) else None,
                "line_abc": line_value,
                "directly_supported": (
                    len(segments) >= minimum_segments and rms <= maximum_tls_rms_px
                ),
            }
        )
    return clusters


def _measure_frame(
    image: np.ndarray, *, frame_index: int, timestamp_s: float, contract: dict[str, Any]
) -> dict[str, Any]:
    height, width = image.shape[:2]
    diagonal = math.hypot(width, height)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    kernel = int(contract["gaussian_kernel_px"])
    edges = cv2.Canny(
        cv2.GaussianBlur(gray, (kernel, kernel), 0),
        int(contract["canny_low"]),
        int(contract["canny_high"]),
    )
    raw = cv2.HoughLinesP(
        edges,
        rho=float(contract["hough_rho_px"]),
        theta=math.radians(float(contract["hough_theta_degrees"])),
        threshold=int(contract["hough_threshold"]),
        minLineLength=diagonal
        * float(contract["hough_min_line_length_diagonal_fraction"]),
        maxLineGap=diagonal * float(contract["hough_max_line_gap_diagonal_fraction"]),
    )
    segments = (
        np.empty((0, 4), dtype=np.float64)
        if raw is None
        else np.asarray(raw, dtype=np.float64).reshape(-1, 4)
    )
    row_low, row_high = (float(v) for v in contract["row_family_angle_degrees"])
    column_minimum = float(contract["column_family_minimum_absolute_angle_degrees"])
    row_candidates: list[tuple[float, float, np.ndarray]] = []
    column_candidates: list[tuple[float, float, np.ndarray]] = []
    for segment in segments:
        x1, y1, x2, y2 = segment
        angle = _segment_angle_degrees(segment)
        length = float(math.hypot(x2 - x1, y2 - y1))
        if row_low <= angle <= row_high and abs(float(x2 - x1)) > 1e-9:
            intercept = y1 + (y2 - y1) * (width / 2.0 - x1) / (x2 - x1)
            row_candidates.append((float(intercept), length, segment))
        if abs(angle) >= column_minimum and abs(float(y2 - y1)) > 1e-9:
            intercept = x1 + (x2 - x1) * (height / 2.0 - y1) / (y2 - y1)
            column_candidates.append((float(intercept), length, segment))

    cluster_tolerance = diagonal * float(contract["cluster_tolerance_diagonal_fraction"])
    maximum_tls_rms = diagonal * float(contract["maximum_tls_rms_diagonal_fraction"])
    minimum_segments = int(contract["minimum_direct_segments_per_line"])
    row_clusters = _cluster_candidates(
        row_candidates,
        tolerance_px=cluster_tolerance,
        minimum_segments=minimum_segments,
        maximum_tls_rms_px=maximum_tls_rms,
    )
    column_clusters = _cluster_candidates(
        column_candidates,
        tolerance_px=cluster_tolerance,
        minimum_segments=minimum_segments,
        maximum_tls_rms_px=maximum_tls_rms,
    )
    rows = [cluster for cluster in row_clusters if cluster["directly_supported"]]
    columns = [cluster for cluster in column_clusters if cluster["directly_supported"]]
    expected = int(contract["expected_grid_line_count_per_axis"])
    exact = len(rows) == expected and len(columns) == expected
    corners: list[list[float]] | None = None
    if exact:
        row_lines = [np.asarray(cluster["line_abc"], dtype=np.float64) for cluster in rows]
        column_lines = [
            np.asarray(cluster["line_abc"], dtype=np.float64) for cluster in columns
        ]
        corners = [
            _line_intersection(row_lines[0], column_lines[0]).tolist(),
            _line_intersection(row_lines[0], column_lines[-1]).tolist(),
            _line_intersection(row_lines[-1], column_lines[-1]).tolist(),
            _line_intersection(row_lines[-1], column_lines[0]).tolist(),
        ]

    def axis_receipt(
        clusters: list[dict[str, Any]],
        supported: list[dict[str, Any]],
        reference_span_px: int,
    ) -> dict[str, Any]:
        intercepts = [float(cluster["reference_intercept_px"]) for cluster in supported]
        return {
            "candidate_cluster_count": len(clusters),
            "directly_supported_grid_line_count": len(supported),
            "coverage_reference_axis_fraction": (
                float((max(intercepts) - min(intercepts)) / reference_span_px)
                if len(intercepts) >= 2
                else 0.0
            ),
            "clusters": clusters,
        }

    return {
        "frame_index": frame_index,
        "timestamp_s": timestamp_s,
        "hough_segment_count": int(len(segments)),
        "row_axis": axis_receipt(row_clusters, rows, height),
        "column_axis": axis_receipt(column_clusters, columns, width),
        "exact_nine_by_nine_direct_grid": exact,
        "candidate_outer_corners_px": corners,
    }


def _decoded_frames(path: Path) -> tuple[Iterator[tuple[int, float, np.ndarray]], dict[str, Any]]:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is not None:
        height, width = image.shape[:2]
        return iter(((0, 0.0, image),)), {
            "media_type": "image",
            "width_px": width,
            "height_px": height,
            "declared_frame_count": 1,
            "fps": None,
        }
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise BoardGridVisibilityError(f"cannot decode image or video {path}")
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    declared = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))

    def iterator() -> Iterator[tuple[int, float, np.ndarray]]:
        index = 0
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                timestamp = index / fps if fps > 0.0 else 0.0
                yield index, timestamp, frame
                index += 1
        finally:
            capture.release()

    return iterator(), {
        "media_type": "video",
        "width_px": width,
        "height_px": height,
        "declared_frame_count": declared,
        "fps": fps if fps > 0.0 else None,
    }


def diagnose_board_grid_visibility(
    input_path: Path,
    *,
    output_path: Path | None = None,
    contract_path: Path = CONTRACT_PATH,
) -> dict[str, Any]:
    """Diagnose direct outer-grid visibility from existing media only."""
    input_path = input_path.resolve()
    if not input_path.is_file():
        raise BoardGridVisibilityError(f"input does not exist: {input_path}")
    contract = load_contract(contract_path)
    frames, media = _decoded_frames(input_path)
    measured = [
        _measure_frame(frame, frame_index=index, timestamp_s=timestamp, contract=contract)
        for index, timestamp, frame in frames
    ]
    if not measured:
        raise BoardGridVisibilityError("input decoded zero frames")
    expected = int(contract["expected_grid_line_count_per_axis"])

    def score(frame: dict[str, Any]) -> tuple[int, int, int, int]:
        rows = int(frame["row_axis"]["directly_supported_grid_line_count"])
        columns = int(frame["column_axis"]["directly_supported_grid_line_count"])
        return (
            int(frame["exact_nine_by_nine_direct_grid"]),
            min(rows, expected) + min(columns, expected),
            -(abs(rows - expected) + abs(columns - expected)),
            frame["frame_index"],
        )

    best = max(measured, key=score)
    exact_frames = [frame for frame in measured if frame["exact_nine_by_nine_direct_grid"]]
    settled_required = int(contract["minimum_adjacent_settled_frames"])
    maximum_drift = math.hypot(media["width_px"], media["height_px"]) * float(
        contract["maximum_boundary_drift_diagonal_fraction"]
    )
    accepted_run: list[int] = []
    current_run: list[dict[str, Any]] = []
    for frame in measured:
        if not frame["exact_nine_by_nine_direct_grid"]:
            current_run = []
            continue
        if current_run:
            prior = np.asarray(current_run[-1]["candidate_outer_corners_px"], dtype=np.float64)
            current = np.asarray(frame["candidate_outer_corners_px"], dtype=np.float64)
            if float(np.max(np.linalg.norm(current - prior, axis=1))) > maximum_drift:
                current_run = []
        current_run.append(frame)
        if len(current_run) >= settled_required and len(current_run) > len(accepted_run):
            accepted_run = [int(item["frame_index"]) for item in current_run]

    passed = len(accepted_run) >= settled_required
    exact_best = bool(best["exact_nine_by_nine_direct_grid"])
    boundary_names = ("row_first", "row_last", "column_first", "column_last")
    boundary_support = {
        name: {
            "direct_multi_segment_support": exact_best,
            "extrapolation_required": not exact_best,
        }
        for name in boundary_names
    }
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "proof_class": contract["proof_class"],
        "diagnostic_only": True,
        "nonmetric": True,
        "april_tag_used": False,
        "square_size_used": False,
        "pose_solved": False,
        "camera_or_robot_accessed": False,
        "authority": contract["authority"],
        "input_lineage": {
            "path": str(input_path),
            "sha256": sha256_file(input_path),
            **media,
            "decoded_frame_count": len(measured),
        },
        "contract_lineage": {
            "path": str(contract_path.resolve()),
            "sha256": sha256_file(contract_path),
        },
        "best_frame": best,
        "per_frame": measured,
        "outer_playing_grid_boundary_support": boundary_support,
        "adjacent_settled_frame_indices": accepted_run,
        "verdict": {
            "passed": passed,
            "classification": (
                "direct_outer_grid_visible_nonmetric"
                if passed
                else "partial_grid_visibility_not_outer_quadrilateral"
            ),
            "failure_reasons": (
                []
                if passed
                else [
                    "all four outer playing-grid boundaries cannot be identified with "
                    "direct multi-segment support in the best frame"
                    if not exact_best
                    else "direct outer boundaries do not persist across enough adjacent "
                    "settled frames"
                ]
            ),
            "grants_metric_or_physical_authority": False,
        },
    }
    if output_path is not None:
        atomic_write_json(output_path, receipt)
    return receipt

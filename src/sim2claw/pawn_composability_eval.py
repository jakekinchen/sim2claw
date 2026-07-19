"""Offline product scorecard for bidirectional pawn transition quality.

This evaluator deliberately consumes reviewed pawn *base-center* annotations.
Catalog labels, operator success notes, bounding-box centers, training loss, and
nominal square centers are not pose evidence. Its outputs can describe the
frozen B-G product benchmark, but retrospective source recordings cannot
promote a checkpoint or authorize physical execution.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np

from .paths import REPO_ROOT


CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "pawn_rank12_bidirectional_v2.json"
)
CONTRACT_SCHEMA = "sim2claw.pawn_bidirectional_composability_eval.v2"
HISTORICAL_CONTRACT_SCHEMA = "sim2claw.pawn_bidirectional_composability_eval.v1"
ANNOTATION_SCHEMA = "sim2claw.pawn_composability_annotations.v1"
SUMMARY_SCHEMA = "sim2claw.pawn_composability_summary.v1"
SYNTHETIC_PROOF_CLASS = "synthetic_test_fixture"
PHYSICAL_RECORDING_PROOF_CLASSES = frozenset(
    {"physical_recording_annotations_unqualified"}
)
SUPPORTED_PROOF_CLASSES = frozenset(
    {SYNTHETIC_PROOF_CLASS, *PHYSICAL_RECORDING_PROOF_CLASSES}
)


class ComposabilityEvaluationError(ValueError):
    """Raised when evidence would otherwise be silently misinterpreted."""


@dataclass(frozen=True)
class Calibration:
    calibration_id: str
    pixel_to_board: np.ndarray
    board_to_pixel: np.ndarray
    correspondence_count: int
    board_rms_m: float


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _finite_xy(value: Any, *, label: str) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64)
    if result.shape != (2,) or not np.isfinite(result).all():
        raise ComposabilityEvaluationError(f"{label} must be a finite XY pair")
    return result


def _finite_matrix(value: Any, shape: tuple[int, int], *, label: str) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64)
    if result.shape != shape or not np.isfinite(result).all():
        raise ComposabilityEvaluationError(
            f"{label} must be a finite {shape[0]}x{shape[1]} matrix"
        )
    return result


def _resolve_evidence_path(path_text: str, *, manifest_path: Path) -> Path:
    candidate = Path(path_text).expanduser()
    if not candidate.is_absolute():
        candidate = manifest_path.parent / candidate
    return candidate.resolve()


def _verify_hash_bound_file(
    value: dict[str, Any], *, manifest_path: Path, label: str
) -> Path:
    path_text = value.get("image_path")
    expected_hash = value.get("image_sha256")
    if not isinstance(path_text, str) or not isinstance(expected_hash, str):
        raise ComposabilityEvaluationError(
            f"{label} must bind image_path and image_sha256"
        )
    path = _resolve_evidence_path(path_text, manifest_path=manifest_path)
    if not path.is_file():
        raise ComposabilityEvaluationError(f"{label} image is missing: {path}")
    if sha256_file(path) != expected_hash:
        raise ComposabilityEvaluationError(f"{label} image hash does not match")
    return path


def _require_review_lineage(
    value: dict[str, Any], *, label: str, measurement: str
) -> None:
    review = value.get("review")
    if not isinstance(review, dict) or review.get("status") != "accepted":
        raise ComposabilityEvaluationError(
            f"{label} must have explicitly accepted review lineage"
        )
    if review.get("measurement") != measurement:
        raise ComposabilityEvaluationError(
            f"{label} review must identify measurement {measurement}"
        )
    for key in ("reviewer", "reviewed_at"):
        if not isinstance(review.get(key), str) or not review[key].strip():
            raise ComposabilityEvaluationError(
                f"{label} accepted review is missing {key}"
            )


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("schema_version") not in {
        CONTRACT_SCHEMA,
        HISTORICAL_CONTRACT_SCHEMA,
    }:
        raise ComposabilityEvaluationError("unsupported composability contract")
    skills = contract.get("skills")
    if not isinstance(skills, list) or len(skills) != 12:
        raise ComposabilityEvaluationError("contract must contain 12 B-G skills")
    expected = {
        (column, source, destination)
        for column in "bcdefg"
        for source, destination in (("1", "2"), ("2", "1"))
    }
    actual = {
        (skill["column"], skill["source_square"][1], skill["destination_square"][1])
        for skill in skills
    }
    if actual != expected or len({skill["skill_id"] for skill in skills}) != 12:
        raise ComposabilityEvaluationError("contract skill coverage drifted")
    if contract["authority"].get("physical_authority") is not False:
        raise ComposabilityEvaluationError("evaluation contract cannot grant authority")
    return contract


def square_center(square: str, square_side_m: float) -> np.ndarray:
    if (
        len(square) != 2
        or square[0] not in "abcdefgh"
        or square[1] not in "12345678"
    ):
        raise ComposabilityEvaluationError(f"invalid chess square: {square}")
    return np.asarray(
        [
            (ord(square[0]) - ord("a") + 0.5) * square_side_m,
            (int(square[1]) - 0.5) * square_side_m,
        ],
        dtype=np.float64,
    )


def _project(matrix: np.ndarray, points: np.ndarray) -> np.ndarray:
    homogeneous = np.column_stack([points, np.ones(len(points), dtype=np.float64)])
    projected = homogeneous @ matrix.T
    if np.any(np.abs(projected[:, 2]) < 1e-12):
        raise ComposabilityEvaluationError("homography projects through infinity")
    return projected[:, :2] / projected[:, 2, None]


def fit_calibration(
    payload: dict[str, Any],
    *,
    contract: dict[str, Any],
    manifest_path: Path,
    require_review_lineage: bool = True,
) -> Calibration:
    calibration_id = payload.get("calibration_id")
    if not isinstance(calibration_id, str) or not calibration_id:
        raise ComposabilityEvaluationError("calibration_id is required")
    if require_review_lineage:
        _require_review_lineage(
            payload,
            label=f"calibration {calibration_id}",
            measurement="pixel_to_board_homography",
        )
    _verify_hash_bound_file(
        payload, manifest_path=manifest_path, label=f"calibration {calibration_id}"
    )
    correspondences = payload.get("correspondences")
    minimum = int(contract["pose_measurement"]["minimum_homography_correspondences"])
    if not isinstance(correspondences, list) or len(correspondences) < minimum:
        raise ComposabilityEvaluationError(
            f"calibration {calibration_id} needs at least {minimum} correspondences"
        )
    pixels = np.asarray(
        [
            _finite_xy(item.get("pixel_xy"), label="calibration pixel_xy")
            for item in correspondences
        ],
        dtype=np.float64,
    )
    board = np.asarray(
        [
            _finite_xy(item.get("board_xy_m"), label="calibration board_xy_m")
            for item in correspondences
        ],
        dtype=np.float64,
    )
    supplied = payload.get("pixel_to_board_homography")
    if supplied is None:
        matrix, _ = cv2.findHomography(pixels, board, method=0)
        if matrix is None:
            raise ComposabilityEvaluationError(
                f"calibration {calibration_id} homography could not be fit"
            )
        matrix = np.asarray(matrix, dtype=np.float64)
    else:
        matrix = _finite_matrix(
            supplied, (3, 3), label="pixel_to_board_homography"
        )
    if abs(float(np.linalg.det(matrix))) < 1e-12:
        raise ComposabilityEvaluationError(
            f"calibration {calibration_id} homography is singular"
        )
    projected = _project(matrix, pixels)
    rms = float(np.sqrt(np.mean(np.sum(np.square(projected - board), axis=1))))
    maximum = float(contract["pose_measurement"]["maximum_homography_board_rms_m"])
    if rms > maximum:
        raise ComposabilityEvaluationError(
            f"calibration {calibration_id} board RMS {rms:.6f} m exceeds {maximum:.6f} m"
        )
    inverse = np.linalg.inv(matrix)
    return Calibration(
        calibration_id=calibration_id,
        pixel_to_board=matrix,
        board_to_pixel=inverse,
        correspondence_count=len(correspondences),
        board_rms_m=rms,
    )


def _pose_xy(
    pose: dict[str, Any],
    *,
    calibration: Calibration | None,
    manifest_path: Path,
    label: str,
    require_review_lineage: bool,
) -> tuple[np.ndarray, list[float] | None]:
    if require_review_lineage:
        _require_review_lineage(
            pose,
            label=label,
            measurement="pawn_base_contact_center_on_board_plane",
        )
    if "board_xy_m" in pose:
        if "base_center_px" in pose:
            raise ComposabilityEvaluationError(
                f"{label} cannot provide both board_xy_m and base_center_px"
            )
        return _finite_xy(pose["board_xy_m"], label=f"{label} board_xy_m"), None
    if "visual_bounding_box_center_px" in pose:
        raise ComposabilityEvaluationError(
            f"{label} uses a forbidden visual bounding-box center"
        )
    pixel = _finite_xy(pose.get("base_center_px"), label=f"{label} base_center_px")
    if calibration is None:
        raise ComposabilityEvaluationError(
            f"{label} pixel pose requires a reviewed calibration"
        )
    _verify_hash_bound_file(pose, manifest_path=manifest_path, label=label)
    board = _project(calibration.pixel_to_board, pixel.reshape(1, 2))[0]
    return board, pixel.astype(float).tolist()


def circle_intersection_fraction(distance: float, radius: float, region: float) -> float:
    """Fraction of a radius-sized circular base inside a centered circular region."""
    if radius <= 0.0 or region <= 0.0 or distance < 0.0:
        raise ComposabilityEvaluationError("circle geometry must be positive")
    if distance >= radius + region:
        return 0.0
    if distance <= abs(region - radius):
        overlap = math.pi * min(radius, region) ** 2
        return overlap / (math.pi * radius**2)
    first = math.acos(
        np.clip((distance**2 + radius**2 - region**2) / (2 * distance * radius), -1, 1)
    )
    second = math.acos(
        np.clip((distance**2 + region**2 - radius**2) / (2 * distance * region), -1, 1)
    )
    radical = max(
        0.0,
        (-distance + radius + region)
        * (distance + radius - region)
        * (distance - radius + region)
        * (distance + radius + region),
    )
    overlap = radius**2 * first + region**2 * second - 0.5 * math.sqrt(radical)
    return float(overlap / (math.pi * radius**2))


def _nullable_bool(value: Any, *, label: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ComposabilityEvaluationError(f"{label} must be boolean or null")
    return value


def _trajectory_xy(
    episode: dict[str, Any],
    *,
    calibration: Calibration | None,
    manifest_path: Path,
    require_review_lineage: bool,
) -> tuple[np.ndarray, np.ndarray] | None:
    trajectory = episode.get("pawn_base_trajectory")
    if trajectory is None:
        return None
    if not isinstance(trajectory, list) or len(trajectory) < 2:
        raise ComposabilityEvaluationError(
            "pawn_base_trajectory must contain at least two points"
        )
    progress: list[float] = []
    points: list[np.ndarray] = []
    for index, point in enumerate(trajectory):
        fraction = float(point.get("progress", index / (len(trajectory) - 1)))
        if not math.isfinite(fraction) or not 0.0 <= fraction <= 1.0:
            raise ComposabilityEvaluationError("trajectory progress must be in [0, 1]")
        xy, _ = _pose_xy(
            point,
            calibration=calibration,
            manifest_path=manifest_path,
            label=f"trajectory point {index}",
            require_review_lineage=require_review_lineage,
        )
        progress.append(fraction)
        points.append(xy)
    progress_array = np.asarray(progress, dtype=np.float64)
    if np.any(np.diff(progress_array) <= 0.0):
        raise ComposabilityEvaluationError("trajectory progress must strictly increase")
    return progress_array, np.asarray(points, dtype=np.float64)


def _grade_endpoint(
    final_offset: np.ndarray,
    *,
    upright: bool | None,
    stable: bool | None,
    square_side_m: float,
    base_radius_m: float,
    composable_tolerance_m: float,
    precision_tolerance_m: float,
) -> tuple[str, bool, bool, bool]:
    secure = bool(
        np.max(np.abs(final_offset)) + base_radius_m <= square_side_m / 2.0 + 1e-12
    )
    distance = float(np.linalg.norm(final_offset))
    if upright is None or stable is None:
        return "unscored_missing_upright_or_stable", False, False, False
    if not upright or not stable or not secure:
        return "task_failure", False, False, False
    coarse = True
    composable = distance <= composable_tolerance_m
    precision = distance <= precision_tolerance_m
    if precision:
        return "precision_success", coarse, composable, precision
    if composable:
        return "composable_success", coarse, composable, precision
    return "coarse_success", coarse, composable, precision


def _catalog_index(
    manifest: dict[str, Any], *, manifest_path: Path, required: bool
) -> dict[str, dict[str, Any]]:
    path_text = manifest.get("source_catalog_path")
    if path_text is None:
        if required:
            raise ComposabilityEvaluationError(
                "physical recording evidence requires source_catalog_path and source_catalog_sha256"
            )
        return {}
    if not isinstance(path_text, str):
        raise ComposabilityEvaluationError("source_catalog_path must be a path")
    expected_hash = manifest.get("source_catalog_sha256")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise ComposabilityEvaluationError(
            "source_catalog_path requires source_catalog_sha256"
        )
    path = _resolve_evidence_path(path_text, manifest_path=manifest_path)
    if not path.is_file() and not Path(path_text).is_absolute():
        path = (REPO_ROOT / path_text).resolve()
    if not path.is_file():
        raise ComposabilityEvaluationError(f"source catalog is missing: {path}")
    if sha256_file(path) != expected_hash:
        raise ComposabilityEvaluationError("source catalog hash does not match")
    catalog = json.loads(path.read_text(encoding="utf-8"))
    return {episode["recording_id"]: episode for episode in catalog.get("episodes", [])}


def _validate_catalog_label(
    episode: dict[str, Any],
    skill: dict[str, Any],
    catalog_index: dict[str, dict[str, Any]],
    *,
    source_recording_required: bool,
) -> None:
    recording_id = episode.get("source_recording_id")
    if not isinstance(recording_id, str) or not recording_id:
        if source_recording_required:
            raise ComposabilityEvaluationError(
                "physical recording episode requires source_recording_id"
            )
        return
    catalog_episode = catalog_index.get(recording_id)
    if catalog_episode is None:
        raise ComposabilityEvaluationError(
            f"source_recording_id is absent from the bound catalog: {recording_id}"
        )
    catalog_matches = (
        catalog_episode.get("source_square") == skill["source_square"]
        and catalog_episode.get("destination_square") == skill["destination_square"]
        and catalog_episode.get("metadata_status")
        == "consistent_folder_label_and_receipt"
    )
    if catalog_matches:
        return
    review = episode.get("task_label_review")
    if not isinstance(review, dict) or review.get("status") != "reviewed_correction":
        raise ComposabilityEvaluationError(
            f"recording {recording_id} has conflicting task metadata and needs a reviewed correction"
        )
    required = ("reviewer", "reviewed_at", "source_square", "destination_square")
    if any(not review.get(key) for key in required):
        raise ComposabilityEvaluationError(
            f"recording {recording_id} correction is missing reviewer lineage"
        )
    if (
        review["source_square"] != skill["source_square"]
        or review["destination_square"] != skill["destination_square"]
    ):
        raise ComposabilityEvaluationError(
            f"recording {recording_id} reviewed correction does not match its skill"
        )


def _episode_metric(
    episode: dict[str, Any],
    *,
    skill: dict[str, Any],
    contract: dict[str, Any],
    calibration: Calibration | None,
    manifest_path: Path,
    require_review_lineage: bool,
) -> tuple[dict[str, Any], tuple[np.ndarray, np.ndarray] | None]:
    episode_id = episode.get("episode_id")
    if not isinstance(episode_id, str) or not episode_id:
        raise ComposabilityEvaluationError("every episode needs episode_id")
    proof_class = episode.get("proof_class")
    if not isinstance(proof_class, str) or not proof_class:
        raise ComposabilityEvaluationError(f"{episode_id} needs a proof_class")
    initial, initial_px = _pose_xy(
        episode.get("initial_pose") or {},
        calibration=calibration,
        manifest_path=manifest_path,
        label=f"{episode_id} initial pose",
        require_review_lineage=require_review_lineage,
    )
    final, final_px = _pose_xy(
        episode.get("final_pose") or {},
        calibration=calibration,
        manifest_path=manifest_path,
        label=f"{episode_id} final pose",
        require_review_lineage=require_review_lineage,
    )
    coordinates = contract["board_coordinate_system"]
    grading = contract["grading"]
    square_side_m = float(coordinates["square_side_m"])
    base_radius_m = float(
        episode.get("pawn_base_radius_m", coordinates["physical_pawn_base_radius_m"])
    )
    if not math.isfinite(base_radius_m) or base_radius_m <= 0.0:
        raise ComposabilityEvaluationError("pawn_base_radius_m must be positive")
    initial_offset = initial - square_center(skill["source_square"], square_side_m)
    final_offset = final - square_center(skill["destination_square"], square_side_m)
    upright = _nullable_bool(episode.get("upright"), label=f"{episode_id} upright")
    stable = _nullable_bool(episode.get("stable"), label=f"{episode_id} stable")
    ordinary = _nullable_bool(
        episode.get("ordinary_square_success"),
        label=f"{episode_id} ordinary_square_success",
    )
    grade, coarse, composable, precision = _grade_endpoint(
        final_offset,
        upright=upright,
        stable=stable,
        square_side_m=square_side_m,
        base_radius_m=base_radius_m,
        composable_tolerance_m=float(grading["composable_center_tolerance_m"]),
        precision_tolerance_m=float(grading["precision_center_tolerance_m"]),
    )
    distance = float(np.linalg.norm(final_offset))
    center_inside = bool(np.max(np.abs(final_offset)) <= square_side_m / 2.0)
    base_secure = bool(
        np.max(np.abs(final_offset)) + base_radius_m
        <= square_side_m / 2.0 + 1e-12
    )
    footprint_fraction = circle_intersection_fraction(
        distance,
        base_radius_m,
        float(grading["central_region_radius_m"]),
    )
    trajectory = _trajectory_xy(
        episode,
        calibration=calibration,
        manifest_path=manifest_path,
        require_review_lineage=require_review_lineage,
    )
    return (
        {
            "episode_id": episode_id,
            "source_recording_id": episode.get("source_recording_id"),
            "proof_class": proof_class,
            "skill_id": skill["skill_id"],
            "column": skill["column"],
            "direction": skill["direction"],
            "source_square": skill["source_square"],
            "destination_square": skill["destination_square"],
            "initial_x_m": float(initial[0]),
            "initial_y_m": float(initial[1]),
            "final_x_m": float(final[0]),
            "final_y_m": float(final[1]),
            "initial_horizontal_offset_m": float(initial_offset[0]),
            "initial_vertical_offset_m": float(initial_offset[1]),
            "final_horizontal_error_m": float(final_offset[0]),
            "final_vertical_error_m": float(final_offset[1]),
            "final_center_distance_m": distance,
            "pawn_base_inside_central_region_percent": 100.0 * footprint_fraction,
            "pawn_center_inside_destination_square": center_inside,
            "pawn_base_securely_inside_destination_square": base_secure,
            "upright": upright,
            "stable": stable,
            "ordinary_square_success": ordinary,
            "grade": grade,
            "coarse_success": coarse,
            "composable_success": composable,
            "precision_success": precision,
            "calibration_id": calibration.calibration_id if calibration else None,
            "homography_board_rms_m": calibration.board_rms_m if calibration else None,
            "trajectory_point_count": len(trajectory[0]) if trajectory else 0,
            "reverse_precondition_envelope_status": "not_evaluated",
            "_initial_px": initial_px,
            "_final_px": final_px,
        },
        trajectory,
    )


def _covariance(values: np.ndarray) -> list[list[float]] | None:
    if len(values) < 2:
        return None
    return np.cov(values, rowvar=False, ddof=1).astype(float).tolist()


def _fit_regression(
    records: list[dict[str, Any]], *, contract: dict[str, Any], group_id: str
) -> dict[str, Any]:
    regression = contract["regression"]
    initial = np.asarray(
        [
            [record["initial_horizontal_offset_m"], record["initial_vertical_offset_m"]]
            for record in records
        ],
        dtype=np.float64,
    )
    final = np.asarray(
        [
            [record["final_horizontal_error_m"], record["final_vertical_error_m"]]
            for record in records
        ],
        dtype=np.float64,
    )
    minimum = int(regression["minimum_episode_count"])
    if len(records) == 0:
        rank = 0
    else:
        design = np.column_stack([initial, np.ones(len(initial), dtype=np.float64)])
        rank = int(np.linalg.matrix_rank(design))
    base: dict[str, Any] = {
        "group_id": group_id,
        "episode_count": len(records),
        "design_rank": rank,
        "minimum_episode_count": minimum,
        "minimum_design_rank": int(regression["minimum_design_rank"]),
        "model_supported": False,
        "classification": "insufficient_offset_variation",
        "confidence": "insufficient",
        "A": None,
        "b_m": None,
        "residual_rms_m": None,
        "residual_covariance_m2": None,
        "r_squared_xy": None,
    }
    if len(records) < minimum or rank < int(regression["minimum_design_rank"]):
        return base
    design = np.column_stack([initial, np.ones(len(initial), dtype=np.float64)])
    coefficients, _, _, _ = np.linalg.lstsq(design, final, rcond=None)
    matrix = coefficients[:2].T
    bias = coefficients[2]
    residual = final - design @ coefficients
    residual_rms = float(np.sqrt(np.mean(np.sum(np.square(residual), axis=1))))
    total = np.sum(np.square(final - np.mean(final, axis=0)), axis=0)
    unexplained = np.sum(np.square(residual), axis=0)
    r_squared = [
        float(1.0 - unexplained[index] / total[index])
        if total[index] > 1e-18
        else None
        for index in range(2)
    ]
    a_zero = float(np.linalg.norm(matrix, ord="fro"))
    a_identity = float(np.linalg.norm(matrix - np.eye(2), ord="fro"))
    bias_norm = float(np.linalg.norm(bias))
    if residual_rms > float(regression["large_residual_rms_m"]):
        classification = "large_residual_stochastic_or_unmodeled"
    elif a_zero <= float(regression["a_near_zero_frobenius"]):
        classification = (
            "self_centering"
            if bias_norm <= float(regression["small_bias_m"])
            else "self_centering_with_systematic_bias"
        )
    elif a_identity <= float(regression["a_near_identity_frobenius"]):
        classification = "offset_preserving"
    else:
        classification = "mixed_state_conditioning"
    return {
        **base,
        "model_supported": True,
        "classification": classification,
        "confidence": (
            "descriptive"
            if len(records) >= int(regression["descriptive_sample_count"])
            else "limited_sample"
        ),
        "A": matrix.astype(float).tolist(),
        "b_m": bias.astype(float).tolist(),
        "a_zero_frobenius": a_zero,
        "a_identity_frobenius": a_identity,
        "bias_norm_m": bias_norm,
        "residual_rms_m": residual_rms,
        "residual_covariance_m2": _covariance(residual),
        "r_squared_xy": r_squared,
    }


def _precondition_envelopes(
    records_by_skill: dict[str, list[dict[str, Any]]],
    *,
    contract: dict[str, Any],
) -> dict[str, Any]:
    settings = contract["precondition_envelope"]
    minimum = int(settings["minimum_episode_count"])
    margin = float(settings["axis_aligned_margin_m"])
    envelopes: dict[str, Any] = {}
    for skill in contract["skills"]:
        records = records_by_skill[skill["skill_id"]]
        values = np.asarray(
            [
                [
                    record["initial_horizontal_offset_m"],
                    record["initial_vertical_offset_m"],
                ]
                for record in records
            ],
            dtype=np.float64,
        )
        support_rank = (
            int(np.linalg.matrix_rank(values - np.mean(values, axis=0)))
            if len(values) >= 2
            else 0
        )
        established = len(values) >= minimum and support_rank == 2
        envelopes[skill["skill_id"]] = {
            "skill_id": skill["skill_id"],
            "episode_count": len(values),
            "support_rank": support_rank,
            "minimum_episode_count": minimum,
            "established": established,
            "status": "measured_empirical_envelope" if established else "insufficient_support",
            "mean_initial_offset_m": (
                np.mean(values, axis=0).astype(float).tolist() if len(values) else None
            ),
            "covariance_m2": _covariance(values),
            "minimum_offset_m": (
                (np.min(values, axis=0) - margin).astype(float).tolist()
                if len(values)
                else None
            ),
            "maximum_offset_m": (
                (np.max(values, axis=0) + margin).astype(float).tolist()
                if len(values)
                else None
            ),
            "margin_m": margin,
            "physical_authority": False,
        }
    return envelopes


def _apply_reverse_envelopes(
    records: list[dict[str, Any]],
    *,
    skills: dict[str, dict[str, Any]],
    envelopes: dict[str, Any],
) -> None:
    for record in records:
        reverse_id = skills[record["skill_id"]]["reverse_skill_id"]
        envelope = envelopes[reverse_id]
        if not envelope["established"]:
            record["reverse_precondition_envelope_status"] = "unknown_insufficient_support"
            continue
        value = np.asarray(
            [record["final_horizontal_error_m"], record["final_vertical_error_m"]],
            dtype=np.float64,
        )
        lower = np.asarray(envelope["minimum_offset_m"], dtype=np.float64)
        upper = np.asarray(envelope["maximum_offset_m"], dtype=np.float64)
        record["reverse_precondition_envelope_status"] = (
            "inside_measured_reverse_envelope"
            if np.all(value >= lower) and np.all(value <= upper)
            else "outside_measured_reverse_envelope"
        )


def _trajectory_repeatability(
    trajectories: dict[str, list[tuple[str, np.ndarray, np.ndarray]]],
    *,
    contract: dict[str, Any],
) -> dict[str, Any]:
    settings = contract["trajectory_repeatability"]
    count = int(settings["normalized_sample_count"])
    minimum = int(settings["minimum_trajectory_count"])
    grid = np.linspace(0.0, 1.0, count)
    results: dict[str, Any] = {}
    for skill in contract["skills"]:
        items = trajectories[skill["skill_id"]]
        if len(items) < minimum:
            results[skill["skill_id"]] = {
                "skill_id": skill["skill_id"],
                "trajectory_count": len(items),
                "status": "insufficient_trajectories",
                "mean_episode_rms_deviation_m": None,
                "maximum_episode_rms_deviation_m": None,
                "mean_path_board_xy_m": None,
            }
            continue
        resampled = []
        ids = []
        for episode_id, progress, values in items:
            resampled.append(
                np.column_stack(
                    [
                        np.interp(grid, progress, values[:, 0]),
                        np.interp(grid, progress, values[:, 1]),
                    ]
                )
            )
            ids.append(episode_id)
        array = np.asarray(resampled, dtype=np.float64)
        mean_path = np.mean(array, axis=0)
        rms = np.sqrt(np.mean(np.sum(np.square(array - mean_path), axis=2), axis=1))
        results[skill["skill_id"]] = {
            "skill_id": skill["skill_id"],
            "trajectory_count": len(items),
            "status": "measured",
            "episode_ids": ids,
            "normalized_sample_count": count,
            "mean_episode_rms_deviation_m": float(np.mean(rms)),
            "maximum_episode_rms_deviation_m": float(np.max(rms)),
            "per_episode_rms_deviation_m": rms.astype(float).tolist(),
            "mean_path_board_xy_m": mean_path.astype(float).tolist(),
        }
    return results


def _noise_covariance(regression: dict[str, Any]) -> np.ndarray:
    value = regression.get("residual_covariance_m2")
    if value is None:
        return np.zeros((2, 2), dtype=np.float64)
    covariance = np.asarray(value, dtype=np.float64)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    return eigenvectors @ np.diag(np.maximum(eigenvalues, 0.0)) @ eigenvectors.T


def _composition_stability(
    regressions: dict[str, dict[str, Any]],
    records_by_skill: dict[str, list[dict[str, Any]]],
    envelopes: dict[str, Any],
    *,
    contract: dict[str, Any],
) -> dict[str, Any]:
    settings = contract["composition_diagnostic"]
    max_moves = max(int(value) for value in settings["move_counts"])
    report_counts = {int(value) for value in settings["move_counts"]}
    rollout_count = int(settings["monte_carlo_rollouts"])
    rng = np.random.default_rng(int(settings["seed"]))
    by_id = {skill["skill_id"]: skill for skill in contract["skills"]}
    result: dict[str, Any] = {}
    square_side = float(contract["board_coordinate_system"]["square_side_m"])
    base_radius = float(
        contract["board_coordinate_system"]["physical_pawn_base_radius_m"]
    )
    for column in "bcdefg":
        forward_id = f"pawn_{column}1_to_{column}2"
        reverse_id = by_id[forward_id]["reverse_skill_id"]
        forward = regressions[forward_id]
        reverse = regressions[reverse_id]
        if not forward["model_supported"] or not reverse["model_supported"]:
            result[column] = {
                "column": column,
                "status": "insufficient_regression_support",
                "forward_skill_id": forward_id,
                "reverse_skill_id": reverse_id,
                "D_model": None,
                "spectral_radius": None,
                "stability": "unknown",
                "move_statistics": None,
            }
            continue
        af = np.asarray(forward["A"], dtype=np.float64)
        bf = np.asarray(forward["b_m"], dtype=np.float64)
        ar = np.asarray(reverse["A"], dtype=np.float64)
        br = np.asarray(reverse["b_m"], dtype=np.float64)
        pair_matrix = ar @ af
        pair_bias = ar @ bf + br
        eigenvalues = np.linalg.eigvals(pair_matrix)
        spectral_radius = float(np.max(np.abs(eigenvalues)))
        if spectral_radius <= float(settings["stabilizing_spectral_radius_max"]):
            stability = "stabilizing"
        elif spectral_radius <= float(settings["neutral_spectral_radius_max"]):
            stability = "approximately_neutral"
        else:
            stability = "amplifying"
        fixed_matrix = np.eye(2) - pair_matrix
        fixed_point = (
            np.linalg.solve(fixed_matrix, pair_bias).astype(float).tolist()
            if abs(float(np.linalg.det(fixed_matrix))) > 1e-10
            else None
        )
        inputs = records_by_skill[forward_id]
        input_values = np.asarray(
            [
                [item["initial_horizontal_offset_m"], item["initial_vertical_offset_m"]]
                for item in inputs
            ],
            dtype=np.float64,
        )
        if len(input_values) >= 2:
            mean = np.mean(input_values, axis=0)
            covariance = np.asarray(_covariance(input_values), dtype=np.float64)
            covariance += np.eye(2) * 1e-12
            state = rng.multivariate_normal(mean, covariance, size=rollout_count)
        elif len(input_values) == 1:
            state = np.repeat(input_values, rollout_count, axis=0)
        else:
            state = np.zeros((rollout_count, 2), dtype=np.float64)
        noise = {
            forward_id: _noise_covariance(forward),
            reverse_id: _noise_covariance(reverse),
        }
        ever_left = np.zeros(rollout_count, dtype=np.bool_)
        move_statistics: dict[str, Any] = {}
        for move_index in range(1, max_moves + 1):
            skill_id = forward_id if move_index % 2 == 1 else reverse_id
            regression = forward if skill_id == forward_id else reverse
            matrix = np.asarray(regression["A"], dtype=np.float64)
            bias = np.asarray(regression["b_m"], dtype=np.float64)
            covariance = noise[skill_id]
            sampled_noise = (
                rng.multivariate_normal(np.zeros(2), covariance, size=rollout_count)
                if np.any(covariance)
                else np.zeros_like(state)
            )
            state = state @ matrix.T + bias + sampled_noise
            secure = (
                np.max(np.abs(state), axis=1) + base_radius <= square_side / 2.0
            )
            ever_left |= ~secure
            if move_index not in report_counts:
                continue
            next_skill = reverse_id if skill_id == forward_id else forward_id
            envelope = envelopes[next_skill]
            if envelope["established"]:
                lower = np.asarray(envelope["minimum_offset_m"], dtype=np.float64)
                upper = np.asarray(envelope["maximum_offset_m"], dtype=np.float64)
                inside_envelope = np.all((state >= lower) & (state <= upper), axis=1)
                envelope_probability: float | None = float(np.mean(inside_envelope))
            else:
                envelope_probability = None
            distance = np.linalg.norm(state, axis=1)
            move_statistics[str(move_index)] = {
                "move_count": move_index,
                "mean_center_offset_m": float(np.mean(distance)),
                "p95_center_offset_m": float(np.percentile(distance, 95)),
                "probability_base_securely_inside_destination": float(np.mean(secure)),
                "probability_inside_next_measured_precondition_envelope": envelope_probability,
                "probability_ever_left_destination_by_this_move": float(np.mean(ever_left)),
            }
        result[column] = {
            "column": column,
            "status": "empirical_affine_monte_carlo",
            "forward_skill_id": forward_id,
            "reverse_skill_id": reverse_id,
            "D_model": {
                "matrix_M_minus_I": (pair_matrix - np.eye(2)).astype(float).tolist(),
                "bias_m": pair_bias.astype(float).tolist(),
                "definition": "D(delta) = (M - I) * delta + bias",
            },
            "pair_transition_matrix": pair_matrix.astype(float).tolist(),
            "pair_transition_bias_m": pair_bias.astype(float).tolist(),
            "eigenvalues": [
                {"real": float(value.real), "imag": float(value.imag)}
                for value in eigenvalues
            ],
            "spectral_radius": spectral_radius,
            "stability": stability,
            "fixed_point_offset_m": fixed_point,
            "monte_carlo_rollouts": rollout_count,
            "move_statistics": move_statistics,
            "claim_boundary": settings["claim_boundary"],
        }
    return result


def _svg_overlay(
    skill: dict[str, Any], records: list[dict[str, Any]], *, contract: dict[str, Any]
) -> str:
    side = float(contract["board_coordinate_system"]["square_side_m"])
    central = float(contract["grading"]["central_region_radius_m"])
    composable = float(contract["grading"]["composable_center_tolerance_m"])
    precision = float(contract["grading"]["precision_center_tolerance_m"])
    width = 420
    center = width / 2
    scale = 340 / side

    def point(offset_x: float, offset_y: float) -> tuple[float, float]:
        return center + offset_x * scale, center - offset_y * scale

    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="420" height="470" viewBox="0 0 420 470">',
        '<rect width="420" height="470" fill="#0b1015"/>',
        f'<text x="24" y="30" fill="#f2f5f7" font-family="monospace" font-size="16">{html.escape(skill["skill_id"])}</text>',
        f'<rect x="40" y="40" width="340" height="340" fill="#141c24" stroke="#8493a1" stroke-width="2"/>',
        f'<circle cx="{center}" cy="{center}" r="{central * scale:.3f}" fill="none" stroke="#40586b" stroke-dasharray="5 5"/>',
        f'<circle cx="{center}" cy="{center}" r="{composable * scale:.3f}" fill="none" stroke="#42c7a5"/>',
        f'<circle cx="{center}" cy="{center}" r="{precision * scale:.3f}" fill="none" stroke="#f0c75e"/>',
        f'<line x1="40" y1="{center}" x2="380" y2="{center}" stroke="#2c3945"/>',
        f'<line x1="{center}" y1="40" x2="{center}" y2="380" stroke="#2c3945"/>',
    ]
    for record in records:
        ix, iy = point(
            record["initial_horizontal_offset_m"],
            record["initial_vertical_offset_m"],
        )
        fx, fy = point(
            record["final_horizontal_error_m"], record["final_vertical_error_m"]
        )
        lines.extend(
            [
                f'<line x1="{ix:.3f}" y1="{iy:.3f}" x2="{fx:.3f}" y2="{fy:.3f}" stroke="#718396" stroke-width="1"/>',
                f'<circle cx="{ix:.3f}" cy="{iy:.3f}" r="4" fill="#5ab0f2"><title>{html.escape(record["episode_id"])} initial</title></circle>',
                f'<circle cx="{fx:.3f}" cy="{fy:.3f}" r="5" fill="#f27f5a"><title>{html.escape(record["episode_id"])} final</title></circle>',
            ]
        )
    lines.extend(
        [
            '<circle cx="52" cy="414" r="4" fill="#5ab0f2"/><text x="64" y="419" fill="#c9d4dc" font-family="monospace" font-size="12">initial offset</text>',
            '<circle cx="190" cy="414" r="5" fill="#f27f5a"/><text x="202" y="419" fill="#c9d4dc" font-family="monospace" font-size="12">final offset</text>',
            f'<text x="24" y="450" fill="#8493a1" font-family="monospace" font-size="11">n={len(records)}; axes are file/rank offsets about each square center</text>',
            "</svg>",
        ]
    )
    return "\n".join(lines) + "\n"


def _write_overlays(
    output_directory: Path,
    records_by_skill: dict[str, list[dict[str, Any]]],
    *,
    contract: dict[str, Any],
) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    index_lines = [
        "<!doctype html><meta charset=\"utf-8\"><title>Pawn composability overlays</title>",
        "<style>body{background:#0b1015;color:#e9eef2;font-family:monospace}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:16px}iframe{border:0;width:420px;height:470px}</style>",
        "<h1>Pawn endpoint offsets in board coordinates</h1><main>",
    ]
    for skill in contract["skills"]:
        filename = f"{skill['skill_id']}.svg"
        (output_directory / filename).write_text(
            _svg_overlay(skill, records_by_skill[skill["skill_id"]], contract=contract),
            encoding="utf-8",
        )
        index_lines.append(f'<iframe src="{filename}" title="{filename}"></iframe>')
    index_lines.append("</main>")
    (output_directory / "index.html").write_text(
        "\n".join(index_lines) + "\n", encoding="utf-8"
    )


def _write_endpoint_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fields = [
        "episode_id",
        "source_recording_id",
        "proof_class",
        "skill_id",
        "column",
        "direction",
        "source_square",
        "destination_square",
        "initial_x_m",
        "initial_y_m",
        "final_x_m",
        "final_y_m",
        "initial_horizontal_offset_m",
        "initial_vertical_offset_m",
        "final_horizontal_error_m",
        "final_vertical_error_m",
        "final_center_distance_m",
        "pawn_base_inside_central_region_percent",
        "pawn_center_inside_destination_square",
        "pawn_base_securely_inside_destination_square",
        "upright",
        "stable",
        "ordinary_square_success",
        "grade",
        "coarse_success",
        "composable_success",
        "precision_success",
        "calibration_id",
        "homography_board_rms_m",
        "trajectory_point_count",
        "reverse_precondition_envelope_status",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def _rate(records: list[dict[str, Any]], key: str) -> float | None:
    values = [record[key] for record in records if record[key] is not None]
    return float(np.mean(values)) if values else None


def _write_report(
    path: Path,
    *,
    summary: dict[str, Any],
    contract: dict[str, Any],
    records_by_skill: dict[str, list[dict[str, Any]]],
    regressions: dict[str, dict[str, Any]],
) -> None:
    lines = [
        "# Pawn Bidirectional Composability Evaluation",
        "",
        f"Status: `{summary['status']}`",
        "",
        "This is the frozen B-G product scorecard. A run over retrospective source recordings describes those recordings only; it does not validate a learned policy, open held-outs, promote a checkpoint, or authorize physical execution.",
        "",
        "| Skill | n | Ordinary | Coarse | Composable | Precision | Mean x bias (mm) | Mean y bias (mm) | Offset model |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for skill in contract["skills"]:
        skill_id = skill["skill_id"]
        records = records_by_skill[skill_id]
        mean_x = (
            1000.0 * float(np.mean([item["final_horizontal_error_m"] for item in records]))
            if records
            else None
        )
        mean_y = (
            1000.0 * float(np.mean([item["final_vertical_error_m"] for item in records]))
            if records
            else None
        )

        def display(value: float | None, *, percent: bool = False) -> str:
            if value is None:
                return "—"
            return f"{100 * value:.1f}%" if percent else f"{value:.2f}"

        lines.append(
            "| "
            + " | ".join(
                [
                    skill_id,
                    str(len(records)),
                    display(_rate(records, "ordinary_square_success"), percent=True),
                    display(_rate(records, "coarse_success"), percent=True),
                    display(_rate(records, "composable_success"), percent=True),
                    display(_rate(records, "precision_success"), percent=True),
                    display(mean_x),
                    display(mean_y),
                    regressions[skill_id]["classification"],
                ]
            )
            + " |"
        )
    lines.extend(["", "## Evidence gaps", ""])
    for gap in summary["evidence_gaps"]:
        lines.append(f"- {gap}")
    lines.extend(
        [
            "",
            "## Artifact index",
            "",
            "- `endpoint_metrics.csv`: per-episode endpoint and grade data",
            "- `per_skill_bias.json` and `per_skill_covariance.json`: endpoint distributions",
            "- `initial_to_final_offset_regression.json`: A, b, residuals, and classifications",
            "- `precondition_envelopes.json`: measured demonstrated input support",
            "- `trajectory_repeatability.json`: normalized pawn-path repeatability",
            "- `composition_stability.json`: affine D(delta) and alternating-move diagnostic",
            "- `board_coordinate_overlays/index.html`: inspectable local-square overlays",
            "- `summary.json`: machine-readable completeness and authority boundary",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def evaluate_composability(
    manifest_path: Path,
    output_directory: Path,
    *,
    contract_path: Path = CONTRACT_PATH,
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    output_directory = output_directory.resolve()
    contract = load_contract(contract_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != ANNOTATION_SCHEMA:
        raise ComposabilityEvaluationError("unsupported annotation manifest")
    manifest_proof_class = manifest.get("proof_class")
    if not isinstance(manifest_proof_class, str) or not manifest_proof_class:
        raise ComposabilityEvaluationError("annotation manifest needs one proof_class")
    if manifest_proof_class not in SUPPORTED_PROOF_CLASSES:
        raise ComposabilityEvaluationError(
            f"unsupported annotation proof_class: {manifest_proof_class}"
        )
    if manifest.get("source_catalog_is_pose_evidence") is not False:
        raise ComposabilityEvaluationError("catalog metadata cannot be treated as pose evidence")
    synthetic_fixture_bypass = manifest_proof_class == SYNTHETIC_PROOF_CLASS
    physical_recording_evidence = (
        manifest_proof_class in PHYSICAL_RECORDING_PROOF_CLASSES
    )
    calibration_values = manifest.get("calibrations") or []
    if not isinstance(calibration_values, list):
        raise ComposabilityEvaluationError("calibrations must be a list")
    calibrations: dict[str, Calibration] = {}
    for value in calibration_values:
        calibration = fit_calibration(
            value,
            contract=contract,
            manifest_path=manifest_path,
            require_review_lineage=not synthetic_fixture_bypass,
        )
        if calibration.calibration_id in calibrations:
            raise ComposabilityEvaluationError("duplicate calibration_id")
        calibrations[calibration.calibration_id] = calibration
    catalog_index = _catalog_index(
        manifest,
        manifest_path=manifest_path,
        required=physical_recording_evidence,
    )
    skills = {skill["skill_id"]: skill for skill in contract["skills"]}
    records: list[dict[str, Any]] = []
    records_by_skill = {skill_id: [] for skill_id in skills}
    trajectories: dict[str, list[tuple[str, np.ndarray, np.ndarray]]] = {
        skill_id: [] for skill_id in skills
    }
    seen_episode_ids: set[str] = set()
    episode_values = manifest.get("episodes") or []
    if not isinstance(episode_values, list):
        raise ComposabilityEvaluationError("episodes must be a list")
    for episode in episode_values:
        if episode.get("proof_class") != manifest_proof_class:
            raise ComposabilityEvaluationError(
                "episode proof_class must match its annotation manifest"
            )
        skill_id = episode.get("skill_id")
        skill = skills.get(skill_id)
        if skill is None:
            raise ComposabilityEvaluationError(f"episode uses unknown skill: {skill_id}")
        if episode.get("source_square", skill["source_square"]) != skill["source_square"]:
            raise ComposabilityEvaluationError("episode source square conflicts with skill")
        if (
            episode.get("destination_square", skill["destination_square"])
            != skill["destination_square"]
        ):
            raise ComposabilityEvaluationError("episode destination square conflicts with skill")
        _validate_catalog_label(
            episode,
            skill,
            catalog_index,
            source_recording_required=physical_recording_evidence,
        )
        calibration_id = episode.get("calibration_id")
        calibration = calibrations.get(calibration_id) if calibration_id else None
        if calibration_id and calibration is None:
            raise ComposabilityEvaluationError(
                f"episode references unknown calibration: {calibration_id}"
            )
        record, trajectory = _episode_metric(
            episode,
            skill=skill,
            contract=contract,
            calibration=calibration,
            manifest_path=manifest_path,
            require_review_lineage=not synthetic_fixture_bypass,
        )
        if record["episode_id"] in seen_episode_ids:
            raise ComposabilityEvaluationError("duplicate episode_id")
        seen_episode_ids.add(record["episode_id"])
        records.append(record)
        records_by_skill[skill_id].append(record)
        if trajectory is not None:
            trajectories[skill_id].append((record["episode_id"], *trajectory))

    biases: dict[str, Any] = {}
    covariances: dict[str, Any] = {}
    regressions: dict[str, dict[str, Any]] = {}
    for skill_id, skill_records in records_by_skill.items():
        final = np.asarray(
            [
                [record["final_horizontal_error_m"], record["final_vertical_error_m"]]
                for record in skill_records
            ],
            dtype=np.float64,
        )
        biases[skill_id] = {
            "skill_id": skill_id,
            "episode_count": len(skill_records),
            "mean_final_offset_m": (
                np.mean(final, axis=0).astype(float).tolist() if len(final) else None
            ),
            "mean_final_distance_m": (
                float(np.mean(np.linalg.norm(final, axis=1))) if len(final) else None
            ),
        }
        covariances[skill_id] = {
            "skill_id": skill_id,
            "episode_count": len(skill_records),
            "final_offset_covariance_m2": _covariance(final),
            "status": "measured" if len(final) >= 2 else "insufficient_episodes",
        }
        regressions[skill_id] = _fit_regression(
            skill_records, contract=contract, group_id=skill_id
        )
    for direction in ("rank1_to_rank2", "rank2_to_rank1"):
        direction_records = [record for record in records if record["direction"] == direction]
        regressions[f"direction:{direction}"] = _fit_regression(
            direction_records,
            contract=contract,
            group_id=f"direction:{direction}",
        )

    envelopes = _precondition_envelopes(records_by_skill, contract=contract)
    _apply_reverse_envelopes(records, skills=skills, envelopes=envelopes)
    repeatability = _trajectory_repeatability(trajectories, contract=contract)
    composition = _composition_stability(
        regressions,
        records_by_skill,
        envelopes,
        contract=contract,
    )

    covered_skills = [skill_id for skill_id, values in records_by_skill.items() if values]
    supported_skill_regressions = [
        skill_id
        for skill_id in skills
        if regressions[skill_id]["model_supported"]
    ]
    missing_outcomes = [
        record["episode_id"]
        for record in records
        if (
            record["upright"] is None
            or record["stable"] is None
            or record["ordinary_square_success"] is None
        )
    ]
    gaps: list[str] = []
    if not records:
        gaps.append("No reviewed pawn base-center episode annotations were supplied.")
    missing_skills = sorted(set(skills) - set(covered_skills))
    if missing_skills:
        gaps.append("Missing endpoint evidence for: " + ", ".join(missing_skills) + ".")
    unsupported = sorted(set(skills) - set(supported_skill_regressions))
    if unsupported:
        gaps.append(
            "A,b regression unsupported because independent initial-offset variation is insufficient in: "
            + ", ".join(unsupported)
            + "."
        )
    if missing_outcomes:
        gaps.append(
            "Missing required upright, stable, or ordinary_square_success annotations for: "
            + ", ".join(missing_outcomes)
            + "."
        )
    missing_trajectories = [
        skill_id
        for skill_id, result in repeatability.items()
        if result["status"] != "measured"
    ]
    if missing_trajectories:
        gaps.append(
            "Trajectory repeatability is unsupported for: "
            + ", ".join(missing_trajectories)
            + "."
        )
    if not records:
        requested_empty_status = manifest.get("annotation_status")
        status = (
            "base_center_annotations_pending_review"
            if requested_empty_status == "base_center_annotations_pending_review"
            else "incomplete_no_pose_annotations"
        )
    elif missing_outcomes:
        status = "incomplete_missing_outcome_annotations"
    elif missing_skills:
        status = "partial_skill_coverage"
    elif unsupported:
        status = "insufficient_offset_variation"
    else:
        status = "complete_descriptive_evaluation"

    output_directory.mkdir(parents=True, exist_ok=True)
    clean_records = [
        {key: value for key, value in record.items() if not key.startswith("_")}
        for record in records
    ]
    _write_endpoint_csv(output_directory / "endpoint_metrics.csv", clean_records)
    _write_json(output_directory / "per_skill_bias.json", biases)
    _write_json(output_directory / "per_skill_covariance.json", covariances)
    _write_json(
        output_directory / "initial_to_final_offset_regression.json", regressions
    )
    _write_json(output_directory / "precondition_envelopes.json", envelopes)
    _write_json(output_directory / "trajectory_repeatability.json", repeatability)
    _write_json(output_directory / "composition_stability.json", composition)
    _write_overlays(
        output_directory / "board_coordinate_overlays",
        records_by_skill,
        contract=contract,
    )
    summary = {
        "schema_version": SUMMARY_SCHEMA,
        "evaluation_set_id": contract["evaluation_set_id"],
        "annotation_set_id": manifest.get("annotation_set_id"),
        "proof_class": manifest_proof_class,
        "status": status,
        "contract_sha256": sha256_file(contract_path),
        "annotation_manifest_sha256": sha256_file(manifest_path),
        "episode_count": len(records),
        "expected_skill_count": 12,
        "covered_skill_count": len(covered_skills),
        "covered_skills": sorted(covered_skills),
        "supported_skill_regression_count": len(supported_skill_regressions),
        "ordinary_square_success_rate": _rate(records, "ordinary_square_success"),
        "coarse_success_rate": _rate(records, "coarse_success"),
        "composable_success_rate": _rate(records, "composable_success"),
        "precision_success_rate": _rate(records, "precision_success"),
        "evidence_gaps": gaps,
        "artifacts": list(contract["required_outputs"]),
        "product_benchmark_version": 2,
        "product_benchmark_replaces_v1": bool(contract.get("supersession")),
        "superseded_evaluation_set_id": (
            contract.get("supersession", {}).get("supersedes_evaluation_set_id")
        ),
        "retrospective_source_score_only": physical_recording_evidence,
        "held_out_rows_opened": 0,
        "training_rows_admitted": 0,
        "policy_promoted": False,
        "physical_authority_created": False,
        "brev_used": False,
        "claim_boundary": contract["composition_diagnostic"]["claim_boundary"],
    }
    _write_json(output_directory / "summary.json", summary)
    _write_report(
        output_directory / "report.md",
        summary=summary,
        contract=contract,
        records_by_skill=records_by_skill,
        regressions=regressions,
    )
    return {**summary, "output_directory": str(output_directory)}


__all__ = [
    "ANNOTATION_SCHEMA",
    "CONTRACT_PATH",
    "CONTRACT_SCHEMA",
    "HISTORICAL_CONTRACT_SCHEMA",
    "SUMMARY_SCHEMA",
    "Calibration",
    "ComposabilityEvaluationError",
    "circle_intersection_fraction",
    "evaluate_composability",
    "fit_calibration",
    "load_contract",
    "square_center",
]

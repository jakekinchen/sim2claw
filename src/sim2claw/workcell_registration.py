"""Stationary, evaluator-owned C922 board-to-workcell registration."""

from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np

from . import metric_registration_readiness as readiness
from .c922_exact_mode_calibration import load_contract as load_c922_contract


SURVEY_SCHEMA = "sim2claw.board_to_workcell_survey_input.v1"
TRANSFORM_SCHEMA = "sim2claw.camera_to_workcell_transform_receipt.v1"
BOARD_FIT_SCHEMA = "sim2claw.board_fit_evaluation_receipt.v1"
WORKSPACE_POSE_ID = "workspace_board_fiducial_robotward_100mm_20260718_v3"
BOARD_POSE_ID = "board_robotward_100mm_20260718_v3"
MAX_REPROJECTION_RMS_PX = 2.0


class WorkcellRegistrationError(RuntimeError):
    """A physical survey or registration input failed closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WorkcellRegistrationError(message)


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WorkcellRegistrationError(f"Could not load {label}: {error}") from error
    _require(isinstance(value, dict), f"{label} must be an object.")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode()
    if path.exists():
        _require(path.read_bytes() == data, f"Existing output changed: {path}")
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def _inside(root: Path, declared: Any, label: str) -> Path:
    _require(isinstance(declared, str) and bool(declared), f"{label} path is missing.")
    path = (root / declared).resolve()
    resolved = root.resolve()
    _require(path != resolved and resolved in path.parents, f"{label} escapes root.")
    return path


def _pointer(path: Path, root: Path) -> dict[str, str]:
    resolved = path.resolve()
    _require(resolved.is_relative_to(root.resolve()), "Output escapes repository root.")
    return {
        "artifact_path": str(resolved.relative_to(root.resolve())),
        "artifact_sha256": readiness.sha256_file(resolved),
    }


def write_survey_worksheet(path: Path) -> dict[str, Any]:
    """Write a deliberately incomplete, non-authoritative operator worksheet."""

    worksheet = {
        "schema_version": SURVEY_SCHEMA,
        "status": "incomplete_operator_worksheet",
        "workspace_pose_id": WORKSPACE_POSE_ID,
        "board_pose_id": BOARD_POSE_ID,
        "board_measurement_sha256": None,
        "frame_convention": {
            "origin": "physical_board_center",
            "physical_a1_marker": None,
            "physical_h1_marker": None,
            "physical_a8_marker": None,
            "positive_x": "a1_to_h1",
            "positive_y": "a1_to_a8_robotward",
            "positive_z": "table_normal_upward",
            "handedness": "right_handed",
        },
        "transform_direction": "board_to_workcell",
        "board_to_workcell_transform_4x4": None,
        "measurement": {
            "method": None,
            "tool_id": None,
            "operator": None,
            "measured_at": None,
            "translation_uncertainty_95_m": None,
            "rotation_uncertainty_95_degrees": None,
        },
        "independent_review": {
            "reviewer": None,
            "decision": "pending",
            "reviewed_at": None,
        },
        "evidence_attachments": [],
        "nominal_values_substituted": False,
        "synthetic": None,
        "self_scored": False,
        "evaluator_owned": False,
        "physical_authority": False,
    }
    _write_json(path, worksheet)
    return worksheet


def _artifact(
    manifest: Mapping[str, Any],
    name: str,
    *,
    root: Path,
    schema: str,
) -> tuple[dict[str, Any], Path, str]:
    values = manifest.get("metric_measurements")
    _require(isinstance(values, Mapping), "Metric measurements are missing.")
    pointer = values.get(name)
    _require(isinstance(pointer, Mapping), f"{name} pointer is missing.")
    path = _inside(root, pointer.get("artifact_path"), name)
    digest = pointer.get("artifact_sha256")
    _require(
        isinstance(digest, str)
        and path.is_file()
        and readiness.sha256_file(path) == digest,
        f"{name} hash changed.",
    )
    value = _load_json(path, name)
    _require(value.get("schema_version") == schema, f"{name} schema changed.")
    return value, path, digest


def validate_survey(
    survey: Mapping[str, Any],
    *,
    root: Path,
    board_measurement_sha256: str,
) -> np.ndarray:
    """Validate the independently reviewed physical frame survey."""

    _require(survey.get("schema_version") == SURVEY_SCHEMA, "Survey schema changed.")
    _require(
        survey.get("status") == "independently_reviewed_physical_survey",
        "Survey is not independently reviewed physical evidence.",
    )
    _require(
        survey.get("workspace_pose_id") == WORKSPACE_POSE_ID
        and survey.get("board_pose_id") == BOARD_POSE_ID,
        "Survey workspace or board identity changed.",
    )
    _require(
        survey.get("board_measurement_sha256") == board_measurement_sha256,
        "Survey board-measurement hash changed.",
    )
    convention = survey.get("frame_convention")
    _require(isinstance(convention, Mapping), "Survey frame convention is missing.")
    expected = {
        "origin": "physical_board_center",
        "positive_x": "a1_to_h1",
        "positive_y": "a1_to_a8_robotward",
        "positive_z": "table_normal_upward",
        "handedness": "right_handed",
    }
    _require(
        all(convention.get(key) == value for key, value in expected.items()),
        "Survey axes are ambiguous, mirrored, or not workcell-bound.",
    )
    markers = [
        convention.get("physical_a1_marker"),
        convention.get("physical_h1_marker"),
        convention.get("physical_a8_marker"),
    ]
    _require(
        all(isinstance(value, str) and value.strip() for value in markers)
        and len(set(markers)) == 3,
        "Physical a1, h1, and a8 markers must be distinct and explicit.",
    )
    _require(
        survey.get("transform_direction") == "board_to_workcell",
        "Survey transform direction changed.",
    )
    matrix = survey.get("board_to_workcell_transform_4x4")
    _require(
        readiness._valid_rigid_transform(matrix),  # noqa: SLF001
        "Board-to-workcell transform is not rigid and right-handed.",
    )
    measurement = survey.get("measurement")
    review = survey.get("independent_review")
    _require(
        isinstance(measurement, Mapping) and isinstance(review, Mapping),
        "Survey measurement or review is missing.",
    )
    for field in ("method", "tool_id", "operator", "measured_at"):
        _require(
            isinstance(measurement.get(field), str)
            and bool(measurement[field].strip()),
            f"Survey measurement {field} is missing.",
        )
    for field in (
        "translation_uncertainty_95_m",
        "rotation_uncertainty_95_degrees",
    ):
        _require(
            readiness._finite_number(measurement.get(field), positive=True),  # noqa: SLF001
            f"Survey {field} must be positive.",
        )
    _require(
        review.get("decision") == "accepted"
        and isinstance(review.get("reviewer"), str)
        and bool(review["reviewer"].strip())
        and review["reviewer"] != measurement["operator"]
        and isinstance(review.get("reviewed_at"), str)
        and bool(review["reviewed_at"].strip()),
        "Survey lacks an independent accepting review.",
    )
    _require(
        survey.get("nominal_values_substituted") is False
        and survey.get("synthetic") is False
        and survey.get("self_scored") is False
        and survey.get("evaluator_owned") is not True,
        "Survey is nominal, synthetic, self-scored, or claims evaluator ownership.",
    )
    attachments = survey.get("evidence_attachments")
    _require(
        isinstance(attachments, list) and bool(attachments),
        "Survey measurement notes or images are missing.",
    )
    for attachment in attachments:
        _require(isinstance(attachment, Mapping), "Survey attachment is malformed.")
        _require(
            attachment.get("kind") in {"measurement_notes", "survey_image"},
            "Survey attachment kind is invalid.",
        )
        path = _inside(root, attachment.get("path"), "survey attachment")
        _require(
            path.is_file()
            and attachment.get("sha256") == readiness.sha256_file(path),
            "Survey attachment hash changed.",
        )
    return np.asarray(matrix, dtype=np.float64)


def _camera_inputs(
    manifest: Mapping[str, Any],
    *,
    root: Path,
) -> tuple[np.ndarray, np.ndarray, dict[str, str], dict[str, Any]]:
    intrinsics, _, intrinsics_sha = _artifact(
        manifest,
        "camera_intrinsics_receipt",
        root=root,
        schema="sim2claw.camera_intrinsics_receipt.v1",
    )
    distortion, _, distortion_sha = _artifact(
        manifest,
        "lens_distortion_receipt",
        root=root,
        schema="sim2claw.lens_distortion_receipt.v1",
    )
    exact_contract = load_c922_contract()["camera"]
    expected_exact_mode = {
        key: exact_contract[key]
        for key in (
            "localized_name",
            "model_id",
            "unique_id",
            "media_subtype",
            "format_index",
            "frame_rate_range_index",
            "frame_rate_fps",
            "orientation_filter",
        )
    }
    for value, label in ((intrinsics, "intrinsics"), (distortion, "distortion")):
        _require(
            value.get("camera_id") == "logitech-overhead"
            and value.get("image_size_px") == [640, 480]
            and value.get("exact_mode") == expected_exact_mode
            and value.get("evaluator_owned") is True
            and value.get("self_scored") is False,
            f"P8 {label} identity or ownership changed.",
        )
    camera_matrix = np.asarray(intrinsics.get("camera_matrix"), dtype=np.float64)
    coefficients = np.asarray(distortion.get("coefficients"), dtype=np.float64)
    _require(
        camera_matrix.shape == (3, 3)
        and np.all(np.isfinite(camera_matrix))
        and coefficients.ndim == 1
        and coefficients.size >= 4
        and np.all(np.isfinite(coefficients)),
        "P8 camera parameters are malformed.",
    )
    return (
        camera_matrix,
        coefficients,
        {"intrinsics_sha256": intrinsics_sha, "distortion_sha256": distortion_sha},
        {"intrinsics": intrinsics, "exact_mode": expected_exact_mode},
    )


def _correspondence_arrays(
    manifest: Mapping[str, Any],
    *,
    board_side_m: float,
) -> tuple[list[str], np.ndarray, np.ndarray, list[list[np.ndarray]], str]:
    source = manifest.get("physical_source")
    values = manifest.get("metric_measurements")
    _require(isinstance(source, Mapping) and isinstance(values, Mapping), "Manifest is incomplete.")
    rows = values.get("board_correspondences")
    _require(isinstance(rows, list) and len(rows) >= 8, "At least eight board points are required.")
    point_ids: list[str] = []
    object_points: list[list[float]] = []
    image_points: list[list[float]] = []
    annotations_by_point: list[list[np.ndarray]] = []
    quadrants: set[str] = set()
    seen_xy: set[tuple[float, float]] = set()
    frame_sha = source.get("source_frame_sha256")
    for row in rows:
        _require(isinstance(row, Mapping), "Board correspondence is malformed.")
        point_id = row.get("point_id")
        xy = row.get("board_xy_m")
        annotations = row.get("annotations")
        quadrant = readiness._derived_board_quadrant(  # noqa: SLF001
            xy, half_side_m=board_side_m / 2.0
        )
        _require(
            isinstance(point_id, str)
            and point_id not in point_ids
            and isinstance(xy, list)
            and len(xy) == 2
            and tuple(float(value) for value in xy) not in seen_xy
            and row.get("board_quadrant") == quadrant
            and row.get("source_frame_sha256") == frame_sha
            and row.get("synthetic") is False,
            "Board point identity, quadrant, source, or proof class changed.",
        )
        _require(isinstance(annotations, list), "Board annotations are missing.")
        by_annotator: dict[str, np.ndarray] = {}
        for annotation in annotations:
            _require(isinstance(annotation, Mapping), "Board annotation is malformed.")
            annotator = annotation.get("annotator_id")
            pixel = np.asarray(annotation.get("pixel_xy"), dtype=np.float64)
            _require(
                isinstance(annotator, str)
                and bool(annotator)
                and annotator not in by_annotator
                and pixel.shape == (2,)
                and np.all(np.isfinite(pixel)),
                "Board annotations must be independent finite points.",
            )
            by_annotator[annotator] = pixel
        _require(len(by_annotator) >= 2, "Two independent annotations per point are required.")
        point_ids.append(point_id)
        seen_xy.add(tuple(float(value) for value in xy))
        quadrants.add(str(quadrant))
        object_points.append([float(xy[0]), float(xy[1]), 0.0])
        annotations_by_point.append(list(by_annotator.values()))
        image_points.append(np.mean(list(by_annotator.values()), axis=0).tolist())
    _require(
        quadrants
        == {"north_west", "north_east", "south_west", "south_east"},
        "Board points must span all four quadrants.",
    )
    assignments = {
        point_id: {"fit": [value for value in point_ids if value != point_id], "held_out": point_id}
        for point_id in sorted(point_ids)
    }
    return (
        point_ids,
        np.asarray(object_points, dtype=np.float64),
        np.asarray(image_points, dtype=np.float64),
        annotations_by_point,
        readiness.canonical_digest(assignments),
    )


def _fit_pnp(
    object_points: np.ndarray,
    image_points: np.ndarray,
    camera_matrix: np.ndarray,
    distortion: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, float]:
    solved = cv2.solvePnPGeneric(
        object_points,
        image_points,
        camera_matrix,
        distortion,
        flags=cv2.SOLVEPNP_IPPE,
    )
    _require(bool(solved[0]), "Planar PnP failed.")
    candidates: list[tuple[float, np.ndarray, np.ndarray]] = []
    for rvec, tvec in zip(solved[1], solved[2], strict=True):
        rotation, _ = cv2.Rodrigues(np.asarray(rvec, dtype=np.float64))
        translation = np.asarray(tvec, dtype=np.float64).reshape(3)
        depths = (rotation @ object_points.T + translation[:, None])[2]
        if np.all(depths > 0.0) and np.linalg.det(rotation) > 0.0:
            projected, _ = cv2.projectPoints(
                object_points, rvec, tvec, camera_matrix, distortion
            )
            error = np.linalg.norm(projected.reshape(-1, 2) - image_points, axis=1)
            candidates.append((float(np.sqrt(np.mean(error**2))), rotation, translation))
    _require(bool(candidates), "PnP produced only mirrored or behind-camera poses.")
    candidates.sort(key=lambda value: value[0])
    if len(candidates) > 1:
        _require(
            candidates[1][0] > max(candidates[0][0] * 1.25, candidates[0][0] + 0.25),
            "Planar PnP orientation is ambiguous.",
        )
    rms, rotation, translation = candidates[0]
    return rotation, translation, rms


def _board_point_from_pixel(
    pixel: np.ndarray,
    rotation: np.ndarray,
    translation: np.ndarray,
    camera_matrix: np.ndarray,
    distortion: np.ndarray,
) -> np.ndarray:
    normalized = cv2.undistortPoints(
        pixel.reshape(1, 1, 2), camera_matrix, distortion
    ).reshape(2)
    origin = -rotation.T @ translation
    direction = rotation.T @ np.asarray([normalized[0], normalized[1], 1.0])
    _require(abs(float(direction[2])) > 1e-9, "Camera ray is parallel to board.")
    distance = -float(origin[2]) / float(direction[2])
    _require(distance > 0.0, "Board intersection is behind the camera.")
    return (origin + distance * direction)[:2]


def fit_stationary_registration(
    *,
    object_points: np.ndarray,
    image_points: np.ndarray,
    annotations_by_point: Sequence[Sequence[np.ndarray]],
    camera_matrix: np.ndarray,
    distortion: np.ndarray,
) -> dict[str, Any]:
    """Fit the full pose and independently score every leave-one-out point."""

    rotation, translation, full_rms_px = _fit_pnp(
        object_points, image_points, camera_matrix, distortion
    )
    held_out_metric: list[float] = []
    held_out_pixels: list[float] = []
    for index in range(len(object_points)):
        mask = np.arange(len(object_points)) != index
        loo_rotation, loo_translation, _ = _fit_pnp(
            object_points[mask],
            image_points[mask],
            camera_matrix,
            distortion,
        )
        estimated = _board_point_from_pixel(
            image_points[index],
            loo_rotation,
            loo_translation,
            camera_matrix,
            distortion,
        )
        held_out_metric.append(
            float(np.linalg.norm(estimated - object_points[index, :2]))
        )
        rvec, _ = cv2.Rodrigues(loo_rotation)
        projected, _ = cv2.projectPoints(
            object_points[index : index + 1],
            rvec,
            loo_translation,
            camera_matrix,
            distortion,
        )
        held_out_pixels.append(
            float(np.linalg.norm(projected.reshape(2) - image_points[index]))
        )
    disagreements: list[float] = []
    for annotations in annotations_by_point:
        board_annotations = [
            _board_point_from_pixel(
                np.asarray(pixel),
                rotation,
                translation,
                camera_matrix,
                distortion,
            )
            for pixel in annotations
        ]
        for first in range(len(board_annotations)):
            for second in range(first + 1, len(board_annotations)):
                disagreements.append(
                    float(
                        np.linalg.norm(
                            board_annotations[first] - board_annotations[second]
                        )
                    )
                )
    board_rms = float(np.sqrt(np.mean(np.square(held_out_metric))))
    reprojection_rms = float(np.sqrt(np.mean(np.square(held_out_pixels))))
    return {
        "rotation_camera_from_board": rotation,
        "translation_camera_from_board_m": translation,
        "full_fit_reprojection_rms_px": full_rms_px,
        "leave_one_out_reprojection_rms_px": reprojection_rms,
        "leave_one_out_board_rms_m": board_rms,
        "maximum_annotator_disagreement_m": max(disagreements, default=0.0),
    }


def evaluate_stationary_registration(
    *,
    survey_path: Path,
    manifest_path: Path,
    output_directory: Path,
    repo_root: Path = readiness.REPO_ROOT,
    evaluator_path: Path = Path(__file__),
) -> dict[str, Any]:
    """Validate physical inputs, fit PnP, and emit existing-schema receipts."""

    root = repo_root.resolve()
    manifest = _load_json(manifest_path, "metric registration manifest")
    _require(
        manifest.get("schema_version") == readiness.INPUT_SCHEMA,
        "Metric registration manifest schema changed.",
    )
    source = manifest.get("physical_source")
    _require(isinstance(source, Mapping), "Physical source is missing.")
    frame = _inside(root, source.get("source_frame_path"), "source frame")
    _require(
        frame.is_file()
        and source.get("source_frame_sha256") == readiness.sha256_file(frame)
        and source.get("source_frame_size_px") == [640, 480]
        and source.get("camera_id") == "logitech-overhead",
        "Stationary C922 frame identity changed.",
    )
    contract = _load_json(
        readiness.DEFAULT_CONTRACT_PATH, "metric readiness contract"
    )
    _, source_invalid = readiness._validate_source(  # noqa: SLF001
        contract, manifest, root
    )
    _require(not source_invalid, f"Stationary capture lineage is invalid: {source_invalid}")
    board, _, board_sha = _artifact(
        manifest,
        "board_playing_side",
        root=root,
        schema="sim2claw.direct_board_measurement_receipt.v1",
    )
    _require(
        board.get("measurement_method") == "direct_physical_measurement"
        and readiness._finite_number(board.get("playing_side_m"), positive=True)  # noqa: SLF001
        and readiness._finite_number(  # noqa: SLF001
            board.get("standard_uncertainty_m"), positive=True
        )
        and isinstance(board.get("measurement_tool_id"), str)
        and bool(board["measurement_tool_id"])
        and board.get("nominal_value_substituted") is False
        and board.get("synthetic") is False,
        "Board measurement is nominal, synthetic, or untraceable.",
    )
    camera_matrix, distortion, camera_hashes, camera_receipts = _camera_inputs(
        manifest, root=root
    )
    _require(
        source.get("exact_mode") == camera_receipts["exact_mode"],
        "Stationary frame exact C922 mode changed.",
    )
    survey = _load_json(survey_path, "board-to-workcell survey")
    survey_sha = readiness.sha256_file(survey_path)
    workcell_from_board = validate_survey(
        survey, root=root, board_measurement_sha256=board_sha
    )
    point_ids, object_points, image_points, annotations, assignment_digest = (
        _correspondence_arrays(
            manifest, board_side_m=float(board["playing_side_m"])
        )
    )
    fit = fit_stationary_registration(
        object_points=object_points,
        image_points=image_points,
        annotations_by_point=annotations,
        camera_matrix=camera_matrix,
        distortion=distortion,
    )
    thresholds = {
        "maximum_leave_one_out_board_rms_m": 0.0015,
        "maximum_annotator_disagreement_m": 0.0015,
        "maximum_leave_one_out_reprojection_rms_px": MAX_REPROJECTION_RMS_PX,
    }
    _require(
        fit["leave_one_out_board_rms_m"]
        <= thresholds["maximum_leave_one_out_board_rms_m"],
        "Leave-one-out metric board residual exceeded threshold.",
    )
    _require(
        fit["maximum_annotator_disagreement_m"]
        <= thresholds["maximum_annotator_disagreement_m"],
        "Independent annotation disagreement exceeded threshold.",
    )
    _require(
        fit["leave_one_out_reprojection_rms_px"]
        <= thresholds["maximum_leave_one_out_reprojection_rms_px"],
        "Leave-one-out reprojection residual exceeded threshold.",
    )
    camera_from_board = np.eye(4, dtype=np.float64)
    camera_from_board[:3, :3] = fit["rotation_camera_from_board"]
    camera_from_board[:3, 3] = fit["translation_camera_from_board_m"]
    workcell_from_camera = workcell_from_board @ np.linalg.inv(camera_from_board)
    _require(
        readiness._valid_rigid_transform(workcell_from_camera.tolist()),  # noqa: SLF001
        "Composed camera-to-workcell transform is invalid.",
    )
    measurement = survey["measurement"]
    board_rms = float(fit["leave_one_out_board_rms_m"])
    board_side = float(board["playing_side_m"])
    translation_uncertainty = (
        float(measurement["translation_uncertainty_95_m"])
        + 1.96 * float(board["standard_uncertainty_m"])
        + 1.96 * board_rms
    )
    rotation_uncertainty = (
        float(measurement["rotation_uncertainty_95_degrees"])
        + math.degrees(math.atan2(1.96 * board_rms, board_side))
    )
    evaluator = evaluator_path.resolve()
    _require(
        evaluator.is_file() and evaluator.is_relative_to(root),
        "Evaluator identity is outside repository root.",
    )
    evaluator_identity = {
        "name": "sim2claw-stationary-workcell-registration",
        "version": "1",
        "executable_path": str(evaluator.relative_to(root)),
        "executable_sha256": readiness.sha256_file(evaluator),
    }
    output = output_directory.resolve()
    _require(output.is_relative_to(root), "Registration output escapes repository.")
    output.mkdir(parents=True, exist_ok=True)
    board_fit_receipt = {
        "schema_version": BOARD_FIT_SCHEMA,
        "evaluation_method": "leave_one_out",
        "board_rms_m": board_rms,
        "max_annotator_disagreement_m": fit[
            "maximum_annotator_disagreement_m"
        ],
        "point_ids": point_ids,
        "evaluator_owned": True,
        "self_scored": False,
        "uncertainty_propagated": True,
        "evaluator_identity": evaluator_identity,
        "source_frame_sha256": source["source_frame_sha256"],
        "correspondences_digest": readiness.canonical_digest(
            manifest["metric_measurements"]["board_correspondences"]
        ),
        "thresholds_digest": readiness.canonical_digest(
            _load_json(
                readiness.DEFAULT_CONTRACT_PATH,
                "metric readiness contract",
            )["readiness_thresholds"]
        ),
        "assignment_digest": assignment_digest,
        "leave_one_out_reprojection_rms_px": fit[
            "leave_one_out_reprojection_rms_px"
        ],
    }
    board_fit_path = output / "board_fit_evaluation_receipt.json"
    _write_json(board_fit_path, board_fit_receipt)
    transform_receipt = {
        "schema_version": TRANSFORM_SCHEMA,
        "camera_id": "logitech-overhead",
        "workspace_pose_id": WORKSPACE_POSE_ID,
        "board_pose_id": BOARD_POSE_ID,
        "transform_4x4": workcell_from_camera.tolist(),
        "transform_convention": {
            "matrix_direction": "workcell_from_camera",
            "camera_axes": "opencv_x_right_y_down_z_forward",
            "workcell_axes": survey["frame_convention"],
            "composition": "workcell_from_board @ inverse(camera_from_board)",
        },
        "translation_uncertainty_95_m": translation_uncertainty,
        "rotation_uncertainty_95_degrees": rotation_uncertainty,
        "residuals": {
            key: value
            for key, value in fit.items()
            if not isinstance(value, np.ndarray)
        },
        "thresholds": thresholds,
        "assignment_digest": assignment_digest,
        "input_hashes": {
            "source_frame_sha256": source["source_frame_sha256"],
            "board_measurement_sha256": board_sha,
            "survey_sha256": survey_sha,
            **camera_hashes,
            "correspondences_digest": readiness.canonical_digest(
                manifest["metric_measurements"]["board_correspondences"]
            ),
        },
        "evaluator_identity": evaluator_identity,
        "evaluator_owned": True,
        "self_scored": False,
        "synthetic": False,
        "physical_authority": False,
        "claim_limits": [
            "stationary overhead camera to workcell registration only",
            "no wrist extrinsics, object keypoints, task success, or robot authority",
        ],
    }
    transform_path = output / "camera_to_workcell_transform_receipt.json"
    _write_json(transform_path, transform_receipt)
    updated = copy.deepcopy(manifest)
    measurements = updated["metric_measurements"]
    measurements["board_fit_evaluation"] = _pointer(board_fit_path, root)
    measurements["overhead_camera_to_workcell_transform"] = _pointer(
        transform_path, root
    )
    measurements["board_to_workcell_survey"] = _pointer(survey_path, root)
    updated_path = output / "metric_registration_inputs.json"
    _write_json(updated_path, updated)
    readiness_result = readiness.evaluate_manifest(contract, updated, repo_root=root)
    result = {
        "status": "stationary_camera_to_workcell_registration_verified",
        "proof_class": "physical_measurement_evaluator",
        "transform_receipt_path": str(transform_path),
        "transform_receipt_sha256": readiness.sha256_file(transform_path),
        "board_fit_receipt_path": str(board_fit_path),
        "board_fit_receipt_sha256": readiness.sha256_file(board_fit_path),
        "updated_manifest_path": str(updated_path),
        "updated_manifest_sha256": readiness.sha256_file(updated_path),
        "metric_readiness_verdict": readiness_result["verdict"],
        "remaining_prerequisites": readiness_result["missing_prerequisites"],
        "physical_authority": False,
    }
    _write_json(output / "registration_result.json", result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("worksheet", "evaluate"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--survey", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)
    if args.phase == "worksheet":
        _require(
            args.survey is None and args.manifest is None,
            "Worksheet phase accepts only --output.",
        )
        result = write_survey_worksheet(args.output)
    else:
        _require(
            args.survey is not None and args.manifest is not None,
            "Evaluate phase requires --survey and --manifest.",
        )
        result = evaluate_stationary_registration(
            survey_path=args.survey,
            manifest_path=args.manifest,
            output_directory=args.output,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Fail-closed readiness evaluation for metric board/object/camera registration.

This module verifies source lineage and the presence of independently owned
measurement artifacts.  It does not estimate a homography, camera model,
object pose, or robot transform, and a passing result is not calibration
evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image


CONTRACT_SCHEMA = "sim2claw.metric_registration_readiness_contract.v1"
INPUT_SCHEMA = "sim2claw.metric_registration_inputs.v1"
EVALUATION_SCHEMA = "sim2claw.metric_registration_readiness_evaluation.v1"
RECEIPT_SCHEMA = "sim2claw.metric_registration_readiness_receipt.v1"
CONTRACT_SHA256 = "dc8cbd7ee4363943512522774f2fb8e882f7bf88a192768ffdd9d210fd3c4910"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/current_100mm_metric_registration_readiness_v1.json"
)
DEFAULT_OUTPUT_ROOT = (
    REPO_ROOT / "outputs/current-100mm-metric-registration-readiness-v1"
)


class MetricRegistrationReadinessError(RuntimeError):
    """A contract, input, or output identity violated the frozen boundary."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MetricRegistrationReadinessError(
            f"Could not load {label}: {error}"
        ) from error
    if not isinstance(value, dict):
        raise MetricRegistrationReadinessError(f"{label} must be an object.")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(_canonical_bytes(value) + b"\n")
    temporary.replace(path)


def _inside_repo(repo_root: Path, declared: Any) -> Path:
    if not isinstance(declared, str) or not declared:
        raise MetricRegistrationReadinessError("Artifact path is missing.")
    candidate = (repo_root / declared).resolve()
    root = repo_root.resolve()
    if candidate != root and root not in candidate.parents:
        raise MetricRegistrationReadinessError(
            f"Artifact path escapes the repository: {declared}"
        )
    return candidate


def _finite_number(value: Any, *, positive: bool = False) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    number = float(value)
    return math.isfinite(number) and (number > 0.0 if positive else True)


def _verified_executable_identity(
    value: Any,
    *,
    repo_root: Path,
) -> bool:
    if not isinstance(value, dict):
        return False
    if (
        not isinstance(value.get("name"), str)
        or not value["name"]
        or not isinstance(value.get("version"), str)
        or not value["version"]
        or not isinstance(value.get("executable_sha256"), str)
    ):
        return False
    try:
        path = _inside_repo(repo_root, value.get("executable_path"))
    except MetricRegistrationReadinessError:
        return False
    return path.is_file() and sha256_file(path) == value["executable_sha256"]


def _valid_rigid_transform(value: Any) -> bool:
    if (
        not isinstance(value, list)
        or len(value) != 4
        or not all(isinstance(row, list) and len(row) == 4 for row in value)
        or not all(_finite_number(item) for row in value for item in row)
    ):
        return False
    matrix = [[float(item) for item in row] for row in value]
    if any(abs(matrix[3][index]) > 1e-9 for index in range(3)):
        return False
    if abs(matrix[3][3] - 1.0) > 1e-9:
        return False
    rotation = [row[:3] for row in matrix[:3]]
    for first in range(3):
        for second in range(3):
            dot = sum(
                rotation[row][first] * rotation[row][second]
                for row in range(3)
            )
            expected = 1.0 if first == second else 0.0
            if abs(dot - expected) > 1e-6:
                return False
    determinant = (
        rotation[0][0]
        * (rotation[1][1] * rotation[2][2] - rotation[1][2] * rotation[2][1])
        - rotation[0][1]
        * (rotation[1][0] * rotation[2][2] - rotation[1][2] * rotation[2][0])
        + rotation[0][2]
        * (rotation[1][0] * rotation[2][1] - rotation[1][1] * rotation[2][0])
    )
    return abs(determinant - 1.0) <= 1e-6


def _derived_board_quadrant(
    board_xy_m: Any,
    *,
    half_side_m: float,
) -> str | None:
    if (
        not isinstance(board_xy_m, list)
        or len(board_xy_m) != 2
        or not all(_finite_number(value) for value in board_xy_m)
    ):
        return None
    x, y = (float(value) for value in board_xy_m)
    if abs(x) > half_side_m or abs(y) > half_side_m:
        return None
    if abs(x) <= 1e-12 or abs(y) <= 1e-12:
        return None
    horizontal = "west" if x < 0.0 else "east"
    vertical = "north" if y > 0.0 else "south"
    return f"{vertical}_{horizontal}"


def load_contract(
    path: Path = DEFAULT_CONTRACT_PATH,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    if sha256_file(path) != CONTRACT_SHA256:
        raise MetricRegistrationReadinessError("Readiness contract identity changed.")
    contract = _load_json(path, label="readiness contract")
    if contract.get("schema_version") != CONTRACT_SCHEMA:
        raise MetricRegistrationReadinessError("Readiness contract schema changed.")
    if contract.get("status") != "preregistered":
        raise MetricRegistrationReadinessError("Readiness contract status changed.")
    manifest_path = _inside_repo(REPO_ROOT, contract.get("input_manifest_path"))
    if sha256_file(manifest_path) != contract.get("input_manifest_sha256"):
        raise MetricRegistrationReadinessError("Input manifest identity changed.")
    manifest = _load_json(manifest_path, label="metric input manifest")
    return contract, manifest, manifest_path


def _check_artifact_pointer(
    value: Any,
    *,
    repo_root: Path,
    expected_schema: str,
) -> tuple[dict[str, Any] | None, str | None]:
    if value is None:
        return None, "missing"
    if not isinstance(value, dict):
        return None, "malformed_pointer"
    try:
        path = _inside_repo(repo_root, value.get("artifact_path"))
    except MetricRegistrationReadinessError:
        return None, "invalid_path"
    expected_sha = value.get("artifact_sha256")
    if (
        not isinstance(expected_sha, str)
        or len(expected_sha) != 64
        or not path.is_file()
    ):
        return None, "unverifiable_artifact"
    if sha256_file(path) != expected_sha:
        return None, "artifact_sha256_mismatch"
    try:
        artifact = _load_json(path, label=expected_schema)
    except MetricRegistrationReadinessError:
        return None, "malformed_artifact"
    if artifact.get("schema_version") != expected_schema:
        return None, "artifact_schema_mismatch"
    return artifact, None


def _validate_source(
    contract: Mapping[str, Any],
    manifest: Mapping[str, Any],
    repo_root: Path,
) -> tuple[dict[str, Any], list[str]]:
    source = manifest.get("physical_source")
    invalid: list[str] = []
    observed: dict[str, Any] = {}
    if not isinstance(source, dict):
        return observed, ["physical_source"]
    requirements = contract["source_requirements"]
    for field in ("camera_id", "camera_name", "camera_role", "proof_class"):
        if source.get(field) != requirements.get(field):
            invalid.append(f"source:{field}")
    if source.get("capture_orientation_filter") != requirements.get(
        "capture_orientation_filter"
    ):
        invalid.append("source:capture_orientation_filter")
    if source.get("source_frame_size_px") != requirements.get("image_size_px"):
        invalid.append("source:source_frame_size_px")

    paths: dict[str, Path] = {}
    for name in ("capture_receipt", "overhead_video", "source_frame"):
        try:
            path = _inside_repo(repo_root, source.get(f"{name}_path"))
        except MetricRegistrationReadinessError:
            invalid.append(f"source:{name}_path")
            continue
        expected = source.get(f"{name}_sha256")
        if not path.is_file() or not isinstance(expected, str):
            invalid.append(f"source:{name}_unverifiable")
            continue
        actual = sha256_file(path)
        observed[f"{name}_sha256"] = actual
        if actual != expected:
            invalid.append(f"source:{name}_sha256")
            continue
        paths[name] = path

    receipt: dict[str, Any] | None = None
    if "capture_receipt" in paths:
        try:
            receipt = _load_json(paths["capture_receipt"], label="capture receipt")
        except MetricRegistrationReadinessError:
            invalid.append("source:capture_receipt_json")
    if receipt is not None:
        if receipt.get("proof_class") != requirements.get("proof_class"):
            invalid.append("source:receipt_proof_class")
        if receipt.get("promotion_authority") is not False:
            invalid.append("source:receipt_promotion_authority")
        if receipt.get("training_admission") is not False:
            invalid.append("source:receipt_training_admission")
        reports = receipt.get("camera_reports")
        matches = (
            [
                row
                for row in reports
                if isinstance(row, dict)
                and row.get("id") == requirements.get("camera_id")
            ]
            if isinstance(reports, list)
            else []
        )
        if len(matches) != 1:
            invalid.append("source:receipt_camera_match")
        else:
            report = matches[0]
            expected_report = {
                "name": requirements.get("camera_name"),
                "role": requirements.get("camera_role"),
                "filter": requirements.get("capture_orientation_filter"),
                "status": "completed_full_timestamp_coverage",
                "sha256": source.get("overhead_video_sha256"),
            }
            for field, expected in expected_report.items():
                if report.get(field) != expected:
                    invalid.append(f"source:receipt_camera_{field}")
            size = requirements.get("image_size_px")
            if report.get("size") != f"{size[0]}x{size[1]}":
                invalid.append("source:receipt_camera_size")

    if "source_frame" in paths:
        try:
            with Image.open(paths["source_frame"]) as image:
                size = [int(image.width), int(image.height)]
        except OSError:
            invalid.append("source:frame_decode")
        else:
            observed["source_frame_size_px"] = size
            if size != requirements.get("image_size_px"):
                invalid.append("source:frame_dimensions")
    return observed, sorted(set(invalid))


def _measurement_status(
    contract: Mapping[str, Any],
    manifest: Mapping[str, Any],
    repo_root: Path,
) -> tuple[dict[str, bool], list[str], list[str], dict[str, Any]]:
    thresholds = contract["readiness_thresholds"]
    values = manifest.get("metric_measurements")
    if not isinstance(values, dict):
        return {}, [], ["metric_measurements"], {}
    gates: dict[str, bool] = {}
    missing: list[str] = []
    invalid: list[str] = []
    observed: dict[str, Any] = {}

    def record(name: str, passed: bool, reason: str | None = None) -> None:
        gates[name] = passed
        if not passed:
            (missing if reason in (None, "missing") else invalid).append(
                name if reason in (None, "missing") else f"{name}:{reason}"
            )

    extraction, error = _check_artifact_pointer(
        manifest["physical_source"].get("frame_extraction_receipt"),
        repo_root=repo_root,
        expected_schema="sim2claw.frame_extraction_receipt.v1",
    )
    if extraction is not None:
        source = manifest["physical_source"]
        valid = (
            extraction.get("source_video_sha256")
            == source.get("overhead_video_sha256")
            and extraction.get("output_frame_sha256")
            == source.get("source_frame_sha256")
            and extraction.get("orientation_filter")
            == source.get("capture_orientation_filter")
            and _verified_executable_identity(
                extraction.get("decoder_identity"), repo_root=repo_root
            )
            and _finite_number(
                extraction.get("source_timestamp_seconds"), positive=False
            )
            and float(extraction["source_timestamp_seconds"]) >= 0.0
        )
        error = None if valid else "lineage_mismatch"
    record("frame_extraction_lineage", extraction is not None and error is None, error)

    board, error = _check_artifact_pointer(
        values.get("board_playing_side"),
        repo_root=repo_root,
        expected_schema="sim2claw.direct_board_measurement_receipt.v1",
    )
    if board is not None:
        valid = (
            board.get("measurement_method") == "direct_physical_measurement"
            and _finite_number(board.get("playing_side_m"), positive=True)
            and _finite_number(
                board.get("standard_uncertainty_m"), positive=True
            )
            and isinstance(board.get("measurement_tool_id"), str)
            and bool(board["measurement_tool_id"])
            and board.get("nominal_value_substituted") is False
            and board.get("synthetic") is False
        )
        error = None if valid else "not_direct_traceable_measurement"
    record("direct_board_measurement", board is not None and error is None, error)
    board_measurement_ready = board is not None and error is None

    intrinsics, error = _check_artifact_pointer(
        values.get("camera_intrinsics_receipt"),
        repo_root=repo_root,
        expected_schema="sim2claw.camera_intrinsics_receipt.v1",
    )
    if intrinsics is not None:
        matrix = intrinsics.get("camera_matrix")
        valid_matrix = (
            isinstance(matrix, list)
            and len(matrix) == 3
            and all(isinstance(row, list) and len(row) == 3 for row in matrix)
            and all(_finite_number(item) for row in matrix for item in row)
        )
        valid = (
            intrinsics.get("camera_id")
            == contract["source_requirements"]["camera_id"]
            and intrinsics.get("image_size_px")
            == contract["source_requirements"]["image_size_px"]
            and valid_matrix
            and intrinsics.get("evaluator_owned") is True
            and intrinsics.get("self_scored") is False
        )
        error = None if valid else "identity_or_matrix_invalid"
    record("exact_mode_camera_intrinsics", intrinsics is not None and error is None, error)

    distortion, error = _check_artifact_pointer(
        values.get("lens_distortion_receipt"),
        repo_root=repo_root,
        expected_schema="sim2claw.lens_distortion_receipt.v1",
    )
    if distortion is not None:
        coefficients = distortion.get("coefficients")
        valid = (
            distortion.get("camera_id")
            == contract["source_requirements"]["camera_id"]
            and distortion.get("image_size_px")
            == contract["source_requirements"]["image_size_px"]
            and isinstance(distortion.get("model"), str)
            and bool(distortion["model"])
            and isinstance(coefficients, list)
            and len(coefficients) >= 4
            and all(_finite_number(value) for value in coefficients)
            and distortion.get("evaluator_owned") is True
            and distortion.get("self_scored") is False
        )
        error = None if valid else "identity_or_model_invalid"
    record("lens_distortion_control", distortion is not None and error is None, error)

    correspondences = values.get("board_correspondences")
    correspondence_valid = isinstance(correspondences, list)
    point_ids: set[str] = set()
    board_points: set[tuple[float, float]] = set()
    quadrants: set[str] = set()
    quadrant_counts: dict[str, int] = {}
    board_side = (
        float(board["playing_side_m"])
        if board_measurement_ready
        else None
    )
    if correspondence_valid:
        for row in correspondences:
            if not isinstance(row, dict):
                correspondence_valid = False
                break
            point_id = row.get("point_id")
            annotations = row.get("annotations")
            board_xy = row.get("board_xy_m")
            derived_quadrant = (
                _derived_board_quadrant(
                    board_xy,
                    half_side_m=board_side / 2.0,
                )
                if board_side is not None
                else None
            )
            annotators = (
                {
                    item.get("annotator_id")
                    for item in annotations
                    if isinstance(item, dict)
                    and isinstance(item.get("annotator_id"), str)
                    and isinstance(item.get("pixel_xy"), list)
                    and len(item["pixel_xy"]) == 2
                    and all(_finite_number(value) for value in item["pixel_xy"])
                }
                if isinstance(annotations, list)
                else set()
            )
            valid_row = (
                isinstance(point_id, str)
                and point_id not in point_ids
                and derived_quadrant is not None
                and row.get("board_quadrant") == derived_quadrant
                and len(annotators)
                >= int(thresholds["minimum_independent_annotators_per_point"])
                and row.get("source_frame_sha256")
                == manifest["physical_source"]["source_frame_sha256"]
                and row.get("synthetic") is False
            )
            if not valid_row:
                correspondence_valid = False
                break
            point = tuple(float(value) for value in board_xy)
            if point in board_points:
                correspondence_valid = False
                break
            point_ids.add(point_id)
            board_points.add(point)
            quadrants.add(derived_quadrant)
            quadrant_counts[derived_quadrant] = (
                quadrant_counts.get(derived_quadrant, 0) + 1
            )
    minimum = int(thresholds["minimum_spatially_distributed_correspondences"])
    enough = (
        correspondence_valid
        and len(point_ids) >= minimum
        and len(board_points) == len(point_ids)
    )
    correspondence_reason: str | None
    if correspondences is None or correspondences == []:
        correspondence_reason = None
    elif not isinstance(correspondences, list) or not correspondence_valid:
        correspondence_reason = "malformed_nonindependent_or_not_spatial"
    elif len(point_ids) < minimum:
        correspondence_reason = None
    else:
        correspondence_reason = None
    record(
        "minimum_independent_board_correspondences",
        enough,
        correspondence_reason,
    )
    expected_quadrants = {
        "north_west",
        "north_east",
        "south_west",
        "south_east",
    }
    coverage = (
        enough
        and quadrants == expected_quadrants
        and all(quadrant_counts.get(name, 0) >= 2 for name in expected_quadrants)
    )
    coverage_reason = correspondence_reason
    record("all_four_board_quadrants", coverage, coverage_reason)
    observed["board_correspondence_count"] = len(point_ids)
    observed["board_quadrants"] = sorted(quadrants)

    board_fit, error = _check_artifact_pointer(
        values.get("board_fit_evaluation"),
        repo_root=repo_root,
        expected_schema="sim2claw.board_fit_evaluation_receipt.v1",
    )
    if board_fit is not None:
        evaluator_identity = board_fit.get("evaluator_identity")
        valid = (
            board_fit.get("evaluation_method") in {"held_out", "leave_one_out"}
            and _finite_number(board_fit.get("board_rms_m"))
            and 0.0
            <= float(board_fit["board_rms_m"])
            <= float(thresholds["maximum_held_out_or_leave_one_out_board_rms_m"])
            and _finite_number(board_fit.get("max_annotator_disagreement_m"))
            and 0.0
            <= float(board_fit["max_annotator_disagreement_m"])
            <= float(thresholds["maximum_pairwise_annotator_disagreement_m"])
            and set(board_fit.get("point_ids", [])) == point_ids
            and board_fit.get("evaluator_owned") is True
            and board_fit.get("self_scored") is False
            and board_fit.get("uncertainty_propagated") is True
            and _verified_executable_identity(
                evaluator_identity, repo_root=repo_root
            )
            and board_fit.get("source_frame_sha256")
            == manifest["physical_source"]["source_frame_sha256"]
            and board_fit.get("correspondences_digest")
            == canonical_digest(correspondences)
            and board_fit.get("thresholds_digest")
            == canonical_digest(thresholds)
        )
        error = None if valid else "threshold_or_ownership_invalid"
    record("independent_board_fit_evaluation", board_fit is not None and error is None, error)

    object_rows = values.get("object_keypoint_observations")
    valid_objects = isinstance(object_rows, list) and len(object_rows) > 0
    object_reason: str | None = None
    if valid_objects:
        for row in object_rows:
            valid_objects = (
                isinstance(row, dict)
                and isinstance(row.get("object_id"), str)
                and bool(row["object_id"])
                and isinstance(row.get("base_center_board_xy_m"), list)
                and len(row["base_center_board_xy_m"]) == 2
                and all(_finite_number(value) for value in row["base_center_board_xy_m"])
                and _finite_number(row.get("uncertainty_95_m"), positive=True)
                and row.get("source_frame_sha256")
                == manifest["physical_source"]["source_frame_sha256"]
                and row.get("independently_reviewed") is True
                and row.get("synthetic") is False
            )
            if not valid_objects:
                object_reason = "malformed_or_unreviewed"
                break
    elif object_rows not in (None, []):
        object_reason = "malformed_or_unreviewed"
    record(
        "metric_object_keypoints_with_uncertainty",
        valid_objects,
        object_reason,
    )
    observed["object_keypoint_count"] = len(object_rows) if isinstance(object_rows, list) else 0

    overhead, error = _check_artifact_pointer(
        values.get("overhead_camera_to_workcell_transform"),
        repo_root=repo_root,
        expected_schema="sim2claw.camera_to_workcell_transform_receipt.v1",
    )
    if overhead is not None:
        matrix = overhead.get("transform_4x4")
        valid = (
            overhead.get("camera_id")
            == contract["source_requirements"]["camera_id"]
            and _valid_rigid_transform(matrix)
            and _finite_number(
                overhead.get("translation_uncertainty_95_m"), positive=True
            )
            and _finite_number(
                overhead.get("rotation_uncertainty_95_degrees"), positive=True
            )
            and overhead.get("evaluator_owned") is True
            and overhead.get("self_scored") is False
        )
        error = None if valid else "identity_transform_or_ownership_invalid"
    record("overhead_camera_to_workcell_transform", overhead is not None and error is None, error)

    wrist, error = _check_artifact_pointer(
        values.get("wrist_camera_extrinsics"),
        repo_root=repo_root,
        expected_schema="sim2claw.wrist_camera_extrinsics_receipt.v1",
    )
    if wrist is not None:
        valid = (
            wrist.get("camera_role") == "wrist_gripper_upward"
            and _valid_rigid_transform(wrist.get("transform_4x4"))
            and _finite_number(
                wrist.get("translation_uncertainty_95_m"), positive=True
            )
            and _finite_number(
                wrist.get("rotation_uncertainty_95_degrees"), positive=True
            )
            and wrist.get("evaluator_owned") is True
            and wrist.get("self_scored") is False
        )
        error = None if valid else "transform_or_ownership_invalid"
    record("wrist_camera_extrinsics", wrist is not None and error is None, error)

    return gates, sorted(set(missing)), sorted(set(invalid)), observed


def evaluate_manifest(
    contract: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    repo_root: Path,
) -> dict[str, Any]:
    """Evaluate already-loaded values without writing or accessing devices."""

    invalid: list[str] = []
    if manifest.get("schema_version") != INPUT_SCHEMA:
        invalid.append("manifest_schema")
    authority = manifest.get("authority")
    expected_closed = {
        "nominal_board_size_is_measurement": False,
        "proposal_homography_is_metric_calibration": False,
        "synthetic_values_allowed": False,
        "training_rows_authorized": 0,
        "promotion_authority": False,
        "physical_motion_authority": False,
        "task_success_verified": False,
    }
    if authority != expected_closed:
        invalid.append("manifest_authority")

    source_observed, source_invalid = _validate_source(contract, manifest, repo_root)
    invalid.extend(source_invalid)
    gates, missing, measurement_invalid, measurement_observed = _measurement_status(
        contract, manifest, repo_root
    )
    invalid.extend(measurement_invalid)
    invalid = sorted(set(invalid))
    missing = sorted(set(missing))
    if invalid:
        verdict = contract["decision"]["invalid_verdict"]
    elif missing:
        verdict = contract["decision"]["missing_verdict"]
    else:
        verdict = contract["decision"]["ready_verdict"]
    return {
        "schema_version": EVALUATION_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": CONTRACT_SHA256,
        "input_id": manifest.get("input_id"),
        "input_manifest_sha256": contract["input_manifest_sha256"],
        "proof_class": contract["authority"]["proof_class"],
        "verdict": verdict,
        "source_valid": not source_invalid,
        "readiness_gates": gates,
        "missing_prerequisites": missing,
        "invalid_inputs": invalid,
        "observed": {**source_observed, **measurement_observed},
        "budget": {
            "readiness_evaluations_used": 1,
            "camera_sessions_used": 0,
            "frames_captured": 0,
            "robot_motions_used": 0,
            "simulator_replays_used": 0,
            "provider_calls_used": 0,
            "training_rows_used": 0,
        },
        "authority": {
            **contract["authority"],
            "readiness_passed": verdict == contract["decision"]["ready_verdict"],
            "twin_fidelity_changed": False,
        },
    }


def materialize(
    *,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Any]:
    """Materialize the sole canonical readiness result."""

    if output_root.resolve() != DEFAULT_OUTPUT_ROOT.resolve():
        raise MetricRegistrationReadinessError(
            "Readiness execution requires the canonical output root."
        )
    if output_root.exists():
        raise MetricRegistrationReadinessError(
            "Readiness output already exists; replay is forbidden."
        )
    contract, manifest, manifest_path = load_contract(contract_path)
    evaluation = evaluate_manifest(contract, manifest, repo_root=REPO_ROOT)
    output_root.mkdir(parents=True, exist_ok=False)
    evaluation_path = output_root / "evaluation.json"
    _write_json(evaluation_path, evaluation)
    evaluator_path = Path(__file__).resolve()
    unsigned_receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_path": str(contract_path.resolve()),
        "contract_sha256": sha256_file(contract_path),
        "input_manifest_path": str(manifest_path.resolve()),
        "input_manifest_sha256": sha256_file(manifest_path),
        "evaluator_path": str(evaluator_path),
        "evaluator_sha256": sha256_file(evaluator_path),
        "evaluation_path": str(evaluation_path.resolve()),
        "evaluation_sha256": sha256_file(evaluation_path),
        "evaluation_digest": canonical_digest(evaluation),
        "verdict": evaluation["verdict"],
        "missing_prerequisite_count": len(evaluation["missing_prerequisites"]),
        "invalid_input_count": len(evaluation["invalid_inputs"]),
        "budget": evaluation["budget"],
        "authority": evaluation["authority"],
    }
    receipt = {
        **unsigned_receipt,
        "receipt_digest": canonical_digest(unsigned_receipt),
    }
    _write_json(output_root / "receipt.json", receipt)
    return {"evaluation": evaluation, "receipt": receipt}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--contract",
        type=Path,
        default=DEFAULT_CONTRACT_PATH,
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
    )
    args = parser.parse_args(argv)
    result = materialize(contract_path=args.contract, output_root=args.output_root)
    print(json.dumps(result["receipt"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

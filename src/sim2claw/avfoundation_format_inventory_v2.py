"""Primitive-only AVFoundation format inventory v2."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from sim2claw.avfoundation_format_inventory import (
    AVFoundationFormatInventoryError,
    _canonical_digest,
    _load_json,
    _sha256_file,
    _validate_observed_formats,
    _write_json,
)


CONTRACT_SCHEMA = "sim2claw.avfoundation_format_inventory_contract.v2"
OBSERVATION_SCHEMA = "sim2claw.avfoundation_format_inventory_observation.v2"
PRELAUNCH_SCHEMA = "sim2claw.avfoundation_format_inventory_prelaunch.v2"
ATTEMPT_SCHEMA = "sim2claw.avfoundation_format_inventory_attempt.v2"
EVALUATION_SCHEMA = "sim2claw.avfoundation_format_inventory_evaluation.v2"
RECEIPT_SCHEMA = "sim2claw.avfoundation_format_inventory_receipt.v2"
FORBIDDEN_SOURCE_TOKENS = (
    "AVCaptureSession",
    "AVCaptureDeviceInput",
    "AVCaptureVideoDataOutput",
    "startRunning",
    "CMSampleBuffer",
    "setSampleBufferDelegate",
    "lockForConfiguration",
    "activeFormat",
    "[String: Any]",
    "JSONSerialization",
)


EXPECTED_SELECTION_RULE = {
    "target_width": 640,
    "target_height": 480,
    "target_fps": 30.0,
    "exact_dimensions_required": True,
    "maximum_fractional_fps_deviation": 0.05,
    "nearest_supported_fps": "clamp_target_to_each_closed_min_max_range",
    "media_subtype_preference": ["420v", "2vuy", "yuvs", "BGRA"],
    "rank_order": [
        "fps_deviation_ascending",
        "media_subtype_preference_index_ascending",
        "media_subtype_fourcc_ascending",
        "format_index_ascending",
        "frame_rate_range_index_ascending",
    ],
    "verdicts": [
        "supported_exact_or_fractional_rate_candidate",
        "no_supported_exact_dimension_rate_candidate",
        "prerequisite_abstention",
    ],
    "selection_does_not_authorize_stream_execution": True,
}
EXPECTED_BUDGET = {
    "inventory_observations_maximum": 1,
    "capture_sessions_maximum": 0,
    "source_samples_maximum": 0,
    "d405_lifecycle_operations_maximum": 0,
    "robot_motion_trials_maximum": 0,
    "provider_calls_maximum": 0,
}
USED_BUDGET = {
    "inventory_observations_used": 1,
    "capture_sessions_used": 0,
    "source_samples_used": 0,
    "d405_lifecycle_operations_used": 0,
    "robot_motion_trials_used": 0,
    "provider_calls_used": 0,
}


def load_format_inventory_v2_contract(path: Path) -> dict[str, Any]:
    contract = _load_json(path, label="format-inventory v2 contract")
    if contract.get("schema_version") != CONTRACT_SCHEMA:
        raise AVFoundationFormatInventoryError("V2 contract schema changed.")
    if contract.get("status") != "preregistered_before_implementation":
        raise AVFoundationFormatInventoryError("V2 contract status changed.")
    if contract.get("device") != {
        "media_type": "video",
        "exact_localized_name": "C922 Pro Stream Webcam",
        "exact_match_count_required": 1,
    }:
        raise AVFoundationFormatInventoryError("V2 device contract changed.")
    if contract.get("selection_rule") != EXPECTED_SELECTION_RULE:
        raise AVFoundationFormatInventoryError("V2 selection rule changed.")
    if contract.get("operation_budget") != EXPECTED_BUDGET:
        raise AVFoundationFormatInventoryError("V2 operation budget changed.")
    if contract.get("serialization") != {
        "encoder": "Foundation.JSONEncoder",
        "payload_contract": "Swift Codable structs only",
        "allowed_leaf_types": ["String", "Int", "Double", "Bool", "null"],
        "dictionary_any_values_allowed": False,
        "swift_value_bridge_allowed": False,
        "attempt_manifest_written_before_observer_launch": True,
        "observer_failure_must_materialize_manifest": True,
    }:
        raise AVFoundationFormatInventoryError("V2 serialization contract changed.")
    authority = contract.get("authority")
    if not isinstance(authority, dict):
        raise AVFoundationFormatInventoryError("V2 authority is missing.")
    if authority.get("device_and_format_enumeration") is not True or any(
        value is not False
        for key, value in authority.items()
        if key != "device_and_format_enumeration"
    ):
        raise AVFoundationFormatInventoryError("V2 authority widened.")
    return contract


def validate_v2_source_is_primitive_observer(source_path: Path) -> None:
    try:
        source = source_path.read_text(encoding="utf-8")
    except OSError as error:
        raise AVFoundationFormatInventoryError(
            f"Could not read v2 Swift source: {error}"
        ) from error
    found = [token for token in FORBIDDEN_SOURCE_TOKENS if token in source]
    if found:
        raise AVFoundationFormatInventoryError(
            f"V2 source contains forbidden tokens: {found}."
        )
    required = (
        "struct InventoryObservation: Codable",
        "struct FormatObservation: Codable",
        "struct FrameRateRangeObservation: Codable",
        "JSONEncoder()",
        ".map { Int($0.rawValue) }",
        "device.formats",
        "videoSupportedFrameRateRanges",
        "captureSessionCreated: false",
        "sourceSampleCount: 0",
    )
    missing = [token for token in required if token not in source]
    if missing:
        raise AVFoundationFormatInventoryError(
            f"V2 source lacks required primitive observer tokens: {missing}."
        )


def compile_format_inventory_v2(
    *,
    contract_path: Path,
    source_path: Path,
    evaluator_path: Path,
    binary_path: Path,
) -> dict[str, Any]:
    contract = load_format_inventory_v2_contract(contract_path)
    validate_v2_source_is_primitive_observer(source_path)
    runtime_contract = contract["runtime_identity"]
    if Path(runtime_contract["inventory_source_path"]) != source_path:
        raise AVFoundationFormatInventoryError("V2 source path changed.")
    if Path(runtime_contract["evaluator_path"]) != evaluator_path:
        raise AVFoundationFormatInventoryError("V2 evaluator path changed.")
    compiler = Path(runtime_contract["compiler_path"])
    if not compiler.is_file():
        raise AVFoundationFormatInventoryError("V2 compiler is missing.")
    version = subprocess.run(
        [str(compiler), "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    if version.returncode != 0 or not version.stdout.startswith(
        runtime_contract["swift_version_prefix"]
    ):
        raise AVFoundationFormatInventoryError("V2 compiler identity changed.")
    binary_path.parent.mkdir(parents=True, exist_ok=True)
    compiled = subprocess.run(
        [str(compiler), str(source_path), "-o", str(binary_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if compiled.returncode != 0:
        raise AVFoundationFormatInventoryError(
            f"V2 Swift compilation failed: {compiled.stderr.strip()}"
        )
    return {
        "contract_sha256": _sha256_file(contract_path),
        "source_sha256": _sha256_file(source_path),
        "evaluator_sha256": _sha256_file(evaluator_path),
        "compiler_path": str(compiler),
        "compiler_sha256": _sha256_file(compiler),
        "swift_version": version.stdout.strip(),
        "binary_path": "runtime/avfoundation-format-inventory-v2",
        "binary_sha256": _sha256_file(binary_path),
    }


def run_format_inventory_v2_observation(
    *,
    contract_path: Path,
    source_path: Path,
    evaluator_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    contract = load_format_inventory_v2_contract(contract_path)
    if output_root.exists():
        raise AVFoundationFormatInventoryError(
            "V2 observation output already exists; replay is forbidden."
        )
    binary_path = output_root / "runtime/avfoundation-format-inventory-v2"
    runtime = compile_format_inventory_v2(
        contract_path=contract_path,
        source_path=source_path,
        evaluator_path=evaluator_path,
        binary_path=binary_path,
    )
    raw_path = output_root / "raw/inventory.json"
    stderr_path = output_root / "raw/inventory.stderr.log"
    prelaunch = {
        "schema_version": PRELAUNCH_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": runtime["contract_sha256"],
        "proof_class": "camera_device_format_inventory",
        "status": "prepared_before_observer_launch",
        "runtime_identity": runtime,
        "raw_inventory_path": "raw/inventory.json",
        "stderr_path": "raw/inventory.stderr.log",
        "budget": USED_BUDGET,
        "authority": contract["authority"],
    }
    prelaunch_path = output_root / "attempt-prelaunch.json"
    _write_json(prelaunch_path, prelaunch)

    completed = subprocess.run(
        [
            str(binary_path),
            "--camera-name",
            contract["device"]["exact_localized_name"],
            "--contract-sha256",
            runtime["contract_sha256"],
            "--output",
            str(raw_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    attempt = {
        "schema_version": ATTEMPT_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": runtime["contract_sha256"],
        "proof_class": "camera_device_format_inventory",
        "status": (
            "observer_completed_with_raw"
            if raw_path.is_file()
            else "observer_failed_without_raw"
        ),
        "prelaunch_manifest_path": "attempt-prelaunch.json",
        "prelaunch_manifest_sha256": _sha256_file(prelaunch_path),
        "runtime_identity": runtime,
        "return_code": completed.returncode,
        "raw_inventory_path": "raw/inventory.json",
        "raw_inventory_sha256": (
            _sha256_file(raw_path) if raw_path.is_file() else None
        ),
        "stderr_path": "raw/inventory.stderr.log",
        "stderr_sha256": _sha256_file(stderr_path),
        "budget": USED_BUDGET,
        "authority": contract["authority"],
    }
    _write_json(output_root / "attempt.json", attempt)
    return attempt


def _verify_runtime(
    *,
    contract: dict[str, Any],
    contract_sha256: str,
    observation_root: Path,
    runtime: dict[str, Any],
) -> None:
    source_path = Path(contract["runtime_identity"]["inventory_source_path"])
    evaluator_path = Path(contract["runtime_identity"]["evaluator_path"])
    compiler_path = Path(contract["runtime_identity"]["compiler_path"])
    binary_relative = runtime.get("binary_path")
    if (
        not isinstance(binary_relative, str)
        or binary_relative.startswith("/")
        or ".." in binary_relative
    ):
        raise AVFoundationFormatInventoryError("V2 binary path is unsafe.")
    binary_path = observation_root / binary_relative
    if (
        runtime.get("contract_sha256") != contract_sha256
        or not source_path.is_file()
        or _sha256_file(source_path) != runtime.get("source_sha256")
        or not evaluator_path.is_file()
        or _sha256_file(evaluator_path) != runtime.get("evaluator_sha256")
        or runtime.get("compiler_path") != str(compiler_path)
        or not compiler_path.is_file()
        or _sha256_file(compiler_path) != runtime.get("compiler_sha256")
        or not binary_path.is_file()
        or _sha256_file(binary_path) != runtime.get("binary_sha256")
    ):
        raise AVFoundationFormatInventoryError("V2 runtime identity changed.")
    validate_v2_source_is_primitive_observer(source_path)


def _rank_candidates(
    formats: list[dict[str, Any]],
    rule: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    target_fps = float(rule["target_fps"])
    preference = {
        subtype: index
        for index, subtype in enumerate(rule["media_subtype_preference"])
    }
    candidates: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    for format_row in formats:
        if (
            format_row["width"] != rule["target_width"]
            or format_row["height"] != rule["target_height"]
        ):
            continue
        for range_row in format_row["frame_rate_ranges"]:
            nearest = min(
                max(target_fps, range_row["minimum_fps"]),
                range_row["maximum_fps"],
            )
            deviation = abs(target_fps - nearest)
            candidate = {
                "format_index": format_row["format_index"],
                "frame_rate_range_index": range_row["range_index"],
                "width": format_row["width"],
                "height": format_row["height"],
                "media_subtype_fourcc": format_row["media_subtype_fourcc"],
                "minimum_fps": range_row["minimum_fps"],
                "maximum_fps": range_row["maximum_fps"],
                "nearest_supported_fps": nearest,
                "fps_deviation": deviation,
                "eligible": deviation
                <= float(rule["maximum_fractional_fps_deviation"]),
                "media_subtype_preference_index": preference.get(
                    format_row["media_subtype_fourcc"],
                    len(preference),
                ),
            }
            candidates.append(candidate)
            if candidate["eligible"]:
                eligible.append(candidate)
    eligible.sort(
        key=lambda row: (
            row["fps_deviation"],
            row["media_subtype_preference_index"],
            row["media_subtype_fourcc"],
            row["format_index"],
            row["frame_rate_range_index"],
        )
    )
    return candidates, eligible


def _validate_v2_observed_formats(
    observation: dict[str, Any],
) -> list[dict[str, Any]]:
    """Reuse v1 validation while preserving macOS-unavailable FOV as null.

    AVFoundation exposes width, height, subtype, color spaces, and rate ranges
    on macOS, but marks ``videoFieldOfView`` unavailable. V2 therefore emits a
    typed null. The v1 validator predates that platform correction and requires
    a finite number, so a validation-only copy receives a finite sentinel. The
    returned rows restore null before candidate ranking; FOV is not an input to
    the frozen selection rule and is never emitted as a measured value.
    """

    raw_formats = observation.get("formats")
    if not isinstance(raw_formats, list):
        raise AVFoundationFormatInventoryError("Observed format list is empty.")
    validation_copy = dict(observation)
    copied_formats: list[dict[str, Any]] = []
    null_fov_indices: set[int] = set()
    for index, row in enumerate(raw_formats):
        if not isinstance(row, dict):
            raise AVFoundationFormatInventoryError("Format row is not an object.")
        copied = dict(row)
        field_of_view = copied.get("video_field_of_view_degrees")
        if field_of_view is None:
            copied["video_field_of_view_degrees"] = 0.0
            null_fov_indices.add(index)
        copied_formats.append(copied)
    validation_copy["formats"] = copied_formats
    validated = _validate_observed_formats(validation_copy)
    for index in null_fov_indices:
        validated[index]["video_field_of_view_degrees"] = None
    return validated


def evaluate_format_inventory_v2(
    *,
    contract_path: Path,
    observation_root: Path,
    output_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = load_format_inventory_v2_contract(contract_path)
    if output_root.exists():
        raise AVFoundationFormatInventoryError(
            "V2 evaluation output already exists; replay is forbidden."
        )
    contract_sha256 = _sha256_file(contract_path)
    prelaunch_path = observation_root / "attempt-prelaunch.json"
    attempt_path = observation_root / "attempt.json"
    prelaunch = _load_json(prelaunch_path, label="v2 prelaunch manifest")
    attempt = _load_json(attempt_path, label="v2 attempt manifest")
    if prelaunch.get("schema_version") != PRELAUNCH_SCHEMA:
        raise AVFoundationFormatInventoryError("V2 prelaunch schema changed.")
    if attempt.get("schema_version") != ATTEMPT_SCHEMA:
        raise AVFoundationFormatInventoryError("V2 attempt schema changed.")
    for label, payload in (("prelaunch", prelaunch), ("attempt", attempt)):
        if (
            payload.get("contract_id") != contract["contract_id"]
            or payload.get("contract_sha256") != contract_sha256
            or payload.get("proof_class") != "camera_device_format_inventory"
            or payload.get("budget") != USED_BUDGET
            or payload.get("authority") != contract["authority"]
        ):
            raise AVFoundationFormatInventoryError(
                f"V2 {label} identity, budget, or authority changed."
            )
    if (
        attempt.get("prelaunch_manifest_path") != "attempt-prelaunch.json"
        or attempt.get("prelaunch_manifest_sha256") != _sha256_file(prelaunch_path)
        or attempt.get("runtime_identity") != prelaunch.get("runtime_identity")
    ):
        raise AVFoundationFormatInventoryError("V2 prelaunch binding changed.")
    runtime = attempt.get("runtime_identity")
    if not isinstance(runtime, dict):
        raise AVFoundationFormatInventoryError("V2 runtime identity is missing.")
    _verify_runtime(
        contract=contract,
        contract_sha256=contract_sha256,
        observation_root=observation_root,
        runtime=runtime,
    )

    stderr_path = observation_root / "raw/inventory.stderr.log"
    if (
        attempt.get("stderr_path") != "raw/inventory.stderr.log"
        or not stderr_path.is_file()
        or _sha256_file(stderr_path) != attempt.get("stderr_sha256")
    ):
        raise AVFoundationFormatInventoryError("V2 stderr identity changed.")
    raw_path = observation_root / "raw/inventory.json"
    raw_available = raw_path.is_file()
    if raw_available != isinstance(attempt.get("raw_inventory_sha256"), str):
        raise AVFoundationFormatInventoryError("V2 raw availability changed.")
    if raw_available and (
        attempt.get("raw_inventory_path") != "raw/inventory.json"
        or _sha256_file(raw_path) != attempt.get("raw_inventory_sha256")
    ):
        raise AVFoundationFormatInventoryError("V2 raw identity changed.")

    observation: dict[str, Any] | None = None
    formats: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    selected: dict[str, Any] | None = None
    if raw_available:
        observation = _load_json(raw_path, label="v2 raw inventory")
        if observation.get("schema_version") != OBSERVATION_SCHEMA:
            raise AVFoundationFormatInventoryError("V2 observation schema changed.")
        if observation.get("contract_sha256") != contract_sha256:
            raise AVFoundationFormatInventoryError("V2 observation contract changed.")
        if observation.get("observer_role") != "device_format_enumeration_only":
            raise AVFoundationFormatInventoryError("V2 observer role changed.")
        if (
            observation.get("capture_session_created") is not False
            or observation.get("capture_session_started") is not False
            or observation.get("source_sample_count") != 0
        ):
            raise AVFoundationFormatInventoryError(
                "V2 observer widened into capture behavior."
            )
        if (
            observation.get("camera_name_requested")
            != contract["device"]["exact_localized_name"]
        ):
            raise AVFoundationFormatInventoryError("V2 camera identity changed.")
        detected = observation.get("detected_device_names")
        if (
            not isinstance(detected, list)
            or any(not isinstance(name, str) for name in detected)
            or detected != sorted(detected)
        ):
            raise AVFoundationFormatInventoryError(
                "V2 detected camera inventory is malformed."
            )

    prerequisite_available = (
        raw_available
        and attempt.get("return_code") == 0
        and observation is not None
        and observation.get("status") == "observed"
        and observation.get("device_match_count") == 1
        and observation.get("device_localized_name")
        == contract["device"]["exact_localized_name"]
    )
    if attempt.get("return_code") == 0 and not prerequisite_available:
        raise AVFoundationFormatInventoryError(
            "V2 successful attempt has inconsistent raw identity."
        )
    if prerequisite_available and observation is not None:
        formats = _validate_v2_observed_formats(observation)
        candidates, eligible = _rank_candidates(
            formats,
            contract["selection_rule"],
        )
        selected = eligible[0] if eligible else None
        verdict = (
            "supported_exact_or_fractional_rate_candidate"
            if selected is not None
            else "no_supported_exact_dimension_rate_candidate"
        )
    else:
        verdict = "prerequisite_abstention"

    evaluation = {
        "schema_version": EVALUATION_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": contract_sha256,
        "prelaunch_manifest_sha256": _sha256_file(prelaunch_path),
        "attempt_manifest_sha256": _sha256_file(attempt_path),
        "raw_inventory_sha256": (
            _sha256_file(raw_path) if raw_available else None
        ),
        "proof_class": "camera_device_format_inventory",
        "verdict": verdict,
        "observer_return_code": attempt.get("return_code"),
        "raw_inventory_available": raw_available,
        "device_match_count": (
            observation.get("device_match_count") if observation else None
        ),
        "device_localized_name": (
            observation.get("device_localized_name") if observation else None
        ),
        "device_unique_id": (
            observation.get("device_unique_id") if observation else None
        ),
        "device_model_id": (
            observation.get("device_model_id") if observation else None
        ),
        "format_count": len(formats) if prerequisite_available else None,
        "frame_rate_range_count": (
            sum(len(row["frame_rate_ranges"]) for row in formats)
            if prerequisite_available
            else None
        ),
        "exact_dimension_candidate_count": len(candidates),
        "eligible_candidate_count": len(eligible),
        "eligible_candidates": eligible,
        "selected_candidate": selected,
        "selection_does_not_authorize_stream_execution": True,
        "budget": USED_BUDGET,
        "claim_limits": {
            "capture_session_started": False,
            "source_delivery_measured": False,
            "container_timing_measured": False,
            "physical_exposure_continuity": False,
            "cross_camera_exposure_synchronization": False,
            "metric_depth": False,
            "simulator_calibration": False,
            "task_success": False,
            "future_campaign_authorized": False,
        },
    }
    output_root.mkdir(parents=True)
    _write_json(output_root / "evaluation.json", evaluation)
    receipt_without_digest = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_sha256": contract_sha256,
        "source_sha256": runtime["source_sha256"],
        "evaluator_sha256": runtime["evaluator_sha256"],
        "compiler_sha256": runtime["compiler_sha256"],
        "binary_sha256": runtime["binary_sha256"],
        "prelaunch_manifest_sha256": _sha256_file(prelaunch_path),
        "attempt_manifest_sha256": _sha256_file(attempt_path),
        "raw_inventory_sha256": (
            _sha256_file(raw_path) if raw_available else None
        ),
        "stderr_sha256": _sha256_file(stderr_path),
        "evaluation_digest": _canonical_digest(evaluation),
        "proof_class": "camera_device_format_inventory",
        "verdict": verdict,
        "budget": USED_BUDGET,
        "authority": contract["authority"],
    }
    receipt = {
        **receipt_without_digest,
        "receipt_digest": _canonical_digest(receipt_without_digest),
    }
    _write_json(output_root / "receipt.json", receipt)
    return evaluation, receipt

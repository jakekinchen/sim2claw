"""Evaluator-owned AVFoundation device-format inventory."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any


CONTRACT_SCHEMA = "sim2claw.avfoundation_format_inventory_contract.v1"
OBSERVATION_SCHEMA = "sim2claw.avfoundation_format_inventory_observation.v1"
MANIFEST_SCHEMA = "sim2claw.avfoundation_format_inventory_manifest.v1"
EVALUATION_SCHEMA = "sim2claw.avfoundation_format_inventory_evaluation.v1"
RECEIPT_SCHEMA = "sim2claw.avfoundation_format_inventory_receipt.v1"
FORBIDDEN_OBSERVER_TOKENS = (
    "AVCaptureSession",
    "AVCaptureDeviceInput",
    "AVCaptureVideoDataOutput",
    "startRunning",
    "CMSampleBuffer",
    "setSampleBufferDelegate",
    "lockForConfiguration",
    "activeFormat",
)


class AVFoundationFormatInventoryError(ValueError):
    """The format inventory or its evidence failed closed."""


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode()


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(_canonical_bytes(value))
    temporary.replace(path)


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AVFoundationFormatInventoryError(
            f"Could not load {label}: {error}"
        ) from error
    if not isinstance(value, dict):
        raise AVFoundationFormatInventoryError(f"{label} is not an object.")
    return value


def load_format_inventory_contract(path: Path) -> dict[str, Any]:
    contract = _load_json(path, label="format-inventory contract")
    if contract.get("schema_version") != CONTRACT_SCHEMA:
        raise AVFoundationFormatInventoryError("Contract schema changed.")
    if contract.get("status") != "preregistered_before_implementation":
        raise AVFoundationFormatInventoryError("Contract status changed.")
    if contract.get("device") != {
        "media_type": "video",
        "exact_localized_name": "C922 Pro Stream Webcam",
        "exact_match_count_required": 1,
    }:
        raise AVFoundationFormatInventoryError("Device contract changed.")
    rule = contract.get("selection_rule")
    if not isinstance(rule, dict):
        raise AVFoundationFormatInventoryError("Selection rule is missing.")
    expected_rule = {
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
    if rule != expected_rule:
        raise AVFoundationFormatInventoryError("Selection rule changed.")
    if contract.get("operation_budget") != {
        "inventory_observations_maximum": 1,
        "capture_sessions_maximum": 0,
        "source_samples_maximum": 0,
        "d405_lifecycle_operations_maximum": 0,
        "robot_motion_trials_maximum": 0,
        "provider_calls_maximum": 0,
    }:
        raise AVFoundationFormatInventoryError("Operation budget changed.")
    authority = contract.get("authority")
    if not isinstance(authority, dict):
        raise AVFoundationFormatInventoryError("Authority is missing.")
    if authority.get("device_and_format_enumeration") is not True or any(
        value is not False
        for key, value in authority.items()
        if key != "device_and_format_enumeration"
    ):
        raise AVFoundationFormatInventoryError("Authority widened.")
    return contract


def validate_inventory_source_is_observer_only(source_path: Path) -> None:
    try:
        source = source_path.read_text(encoding="utf-8")
    except OSError as error:
        raise AVFoundationFormatInventoryError(
            f"Could not read Swift inventory source: {error}"
        ) from error
    found = [token for token in FORBIDDEN_OBSERVER_TOKENS if token in source]
    if found:
        raise AVFoundationFormatInventoryError(
            f"Inventory source contains forbidden capture tokens: {found}."
        )
    required = (
        "AVCaptureDevice.DiscoverySession",
        "device.formats",
        "videoSupportedFrameRateRanges",
        "capture_session_created",
        "source_sample_count",
    )
    missing = [token for token in required if token not in source]
    if missing:
        raise AVFoundationFormatInventoryError(
            f"Inventory source lacks declared observer tokens: {missing}."
        )


def compile_format_inventory(
    *,
    contract_path: Path,
    source_path: Path,
    evaluator_path: Path,
    binary_path: Path,
) -> dict[str, Any]:
    contract = load_format_inventory_contract(contract_path)
    validate_inventory_source_is_observer_only(source_path)
    declared = contract["runtime_identity"]
    if Path(declared["inventory_source_path"]) != source_path:
        raise AVFoundationFormatInventoryError("Swift source path changed.")
    if Path(declared["evaluator_path"]) != evaluator_path:
        raise AVFoundationFormatInventoryError("Evaluator path changed.")
    compiler = Path(declared["compiler_path"])
    if not compiler.is_file():
        raise AVFoundationFormatInventoryError("Declared Swift compiler is missing.")
    version = subprocess.run(
        [str(compiler), "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    if version.returncode != 0 or not version.stdout.startswith(
        declared["swift_version_prefix"]
    ):
        raise AVFoundationFormatInventoryError("Swift compiler identity changed.")
    binary_path.parent.mkdir(parents=True, exist_ok=True)
    compiled = subprocess.run(
        [str(compiler), str(source_path), "-o", str(binary_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if compiled.returncode != 0:
        raise AVFoundationFormatInventoryError(
            f"Swift inventory compilation failed: {compiled.stderr.strip()}"
        )
    return {
        "contract_sha256": _sha256_file(contract_path),
        "source_sha256": _sha256_file(source_path),
        "evaluator_sha256": _sha256_file(evaluator_path),
        "compiler_path": str(compiler),
        "compiler_sha256": _sha256_file(compiler),
        "swift_version": version.stdout.strip(),
        "binary_path": "runtime/avfoundation-format-inventory",
        "binary_sha256": _sha256_file(binary_path),
    }


def run_format_inventory_observation(
    *,
    contract_path: Path,
    source_path: Path,
    evaluator_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    contract = load_format_inventory_contract(contract_path)
    if output_root.exists():
        raise AVFoundationFormatInventoryError(
            "Observation output already exists; replay is forbidden."
        )
    binary_path = output_root / "runtime/avfoundation-format-inventory"
    runtime = compile_format_inventory(
        contract_path=contract_path,
        source_path=source_path,
        evaluator_path=evaluator_path,
        binary_path=binary_path,
    )
    raw_path = output_root / "raw/inventory.json"
    stderr_path = output_root / "raw/inventory.stderr.log"
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
    if not raw_path.is_file():
        raise AVFoundationFormatInventoryError(
            "Inventory observation produced no raw artifact."
        )
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": runtime["contract_sha256"],
        "proof_class": "camera_device_format_inventory",
        "runtime_identity": runtime,
        "return_code": completed.returncode,
        "raw_inventory_path": "raw/inventory.json",
        "raw_inventory_sha256": _sha256_file(raw_path),
        "stderr_path": "raw/inventory.stderr.log",
        "stderr_sha256": _sha256_file(stderr_path),
        "budget": {
            "inventory_observations_used": 1,
            "capture_sessions_used": 0,
            "source_samples_used": 0,
            "d405_lifecycle_operations_used": 0,
            "robot_motion_trials_used": 0,
            "provider_calls_used": 0,
        },
        "authority": contract["authority"],
    }
    _write_json(output_root / "observation.json", manifest)
    return manifest


def _finite_number(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AVFoundationFormatInventoryError(f"{label} is not numeric.")
    number = float(value)
    if not math.isfinite(number):
        raise AVFoundationFormatInventoryError(f"{label} is non-finite.")
    return number


def _validate_observed_formats(
    observation: dict[str, Any],
) -> list[dict[str, Any]]:
    formats = observation.get("formats")
    if not isinstance(formats, list) or not formats:
        raise AVFoundationFormatInventoryError("Observed format list is empty.")
    rows: list[dict[str, Any]] = []
    observed_format_indices: set[int] = set()
    for expected_index, row in enumerate(formats):
        if not isinstance(row, dict):
            raise AVFoundationFormatInventoryError("Format row is not an object.")
        format_index = row.get("format_index")
        if (
            not isinstance(format_index, int)
            or isinstance(format_index, bool)
            or format_index != expected_index
            or format_index in observed_format_indices
        ):
            raise AVFoundationFormatInventoryError(
                "Format indices are duplicate or non-contiguous."
            )
        observed_format_indices.add(format_index)
        width = row.get("width")
        height = row.get("height")
        subtype = row.get("media_subtype_fourcc")
        if (
            not isinstance(width, int)
            or isinstance(width, bool)
            or width <= 0
            or not isinstance(height, int)
            or isinstance(height, bool)
            or height <= 0
            or not isinstance(subtype, str)
            or not subtype
        ):
            raise AVFoundationFormatInventoryError("Format identity is malformed.")
        binning = row.get("is_video_binned")
        if binning is not None and not isinstance(binning, bool):
            raise AVFoundationFormatInventoryError("Binning flag is malformed.")
        _finite_number(
            row.get("video_field_of_view_degrees"),
            label="video field of view",
        )
        maximum_zoom = row.get("video_max_zoom_factor")
        if maximum_zoom is not None:
            _finite_number(maximum_zoom, label="video maximum zoom")
        color_spaces = row.get("supported_color_space_raw_values")
        if (
            not isinstance(color_spaces, list)
            or any(
                not isinstance(value, int) or isinstance(value, bool)
                for value in color_spaces
            )
            or color_spaces != sorted(set(color_spaces))
        ):
            raise AVFoundationFormatInventoryError("Color spaces are malformed.")
        ranges = row.get("frame_rate_ranges")
        if not isinstance(ranges, list) or not ranges:
            raise AVFoundationFormatInventoryError("Frame-rate ranges are missing.")
        validated_ranges: list[dict[str, Any]] = []
        for expected_range_index, range_row in enumerate(ranges):
            if not isinstance(range_row, dict):
                raise AVFoundationFormatInventoryError(
                    "Frame-rate range is not an object."
                )
            if range_row.get("range_index") != expected_range_index:
                raise AVFoundationFormatInventoryError(
                    "Frame-rate range indices are duplicate or non-contiguous."
                )
            minimum_fps = _finite_number(
                range_row.get("minimum_fps"), label="minimum fps"
            )
            maximum_fps = _finite_number(
                range_row.get("maximum_fps"), label="maximum fps"
            )
            minimum_duration = _finite_number(
                range_row.get("minimum_frame_duration_seconds"),
                label="minimum frame duration",
            )
            maximum_duration = _finite_number(
                range_row.get("maximum_frame_duration_seconds"),
                label="maximum frame duration",
            )
            if (
                minimum_fps <= 0.0
                or maximum_fps < minimum_fps
                or minimum_duration <= 0.0
                or maximum_duration < minimum_duration
            ):
                raise AVFoundationFormatInventoryError(
                    "Frame-rate range bounds are invalid."
                )
            validated_ranges.append(
                {
                    "range_index": expected_range_index,
                    "minimum_fps": minimum_fps,
                    "maximum_fps": maximum_fps,
                    "minimum_frame_duration_seconds": minimum_duration,
                    "maximum_frame_duration_seconds": maximum_duration,
                }
            )
        rows.append(
            {
                "format_index": format_index,
                "width": width,
                "height": height,
                "media_subtype_fourcc": subtype,
                "is_video_binned": binning,
                "video_field_of_view_degrees": float(
                    row["video_field_of_view_degrees"]
                ),
                "video_max_zoom_factor": (
                    float(maximum_zoom) if maximum_zoom is not None else None
                ),
                "supported_color_space_raw_values": color_spaces,
                "frame_rate_ranges": validated_ranges,
            }
        )
    return rows


def evaluate_format_inventory(
    *,
    contract_path: Path,
    observation_root: Path,
    output_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = load_format_inventory_contract(contract_path)
    if output_root.exists():
        raise AVFoundationFormatInventoryError(
            "Evaluation output already exists; replay is forbidden."
        )
    manifest_path = observation_root / "observation.json"
    manifest = _load_json(manifest_path, label="inventory manifest")
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise AVFoundationFormatInventoryError("Manifest schema changed.")
    contract_sha256 = _sha256_file(contract_path)
    if (
        manifest.get("contract_id") != contract["contract_id"]
        or manifest.get("proof_class") != "camera_device_format_inventory"
    ):
        raise AVFoundationFormatInventoryError("Manifest identity changed.")
    if manifest.get("contract_sha256") != contract_sha256:
        raise AVFoundationFormatInventoryError("Manifest contract changed.")
    if manifest.get("authority") != contract["authority"]:
        raise AVFoundationFormatInventoryError("Manifest authority changed.")
    if manifest.get("budget") != {
        "inventory_observations_used": 1,
        "capture_sessions_used": 0,
        "source_samples_used": 0,
        "d405_lifecycle_operations_used": 0,
        "robot_motion_trials_used": 0,
        "provider_calls_used": 0,
    }:
        raise AVFoundationFormatInventoryError("Manifest budget changed.")
    runtime = manifest.get("runtime_identity")
    if not isinstance(runtime, dict):
        raise AVFoundationFormatInventoryError("Runtime identity is missing.")
    source_path = Path(contract["runtime_identity"]["inventory_source_path"])
    evaluator_path = Path(contract["runtime_identity"]["evaluator_path"])
    compiler_path = Path(contract["runtime_identity"]["compiler_path"])
    binary_relative = runtime.get("binary_path")
    if (
        not isinstance(binary_relative, str)
        or binary_relative.startswith("/")
        or ".." in binary_relative
    ):
        raise AVFoundationFormatInventoryError("Binary path is unsafe.")
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
        raise AVFoundationFormatInventoryError(
            "Source, evaluator, or binary identity changed."
        )
    validate_inventory_source_is_observer_only(source_path)

    raw_relative = manifest.get("raw_inventory_path")
    stderr_relative = manifest.get("stderr_path")
    if (
        not isinstance(raw_relative, str)
        or not isinstance(stderr_relative, str)
        or raw_relative.startswith("/")
        or stderr_relative.startswith("/")
        or ".." in raw_relative
        or ".." in stderr_relative
    ):
        raise AVFoundationFormatInventoryError("Artifact path is unsafe.")
    raw_path = observation_root / raw_relative
    stderr_path = observation_root / stderr_relative
    if (
        not raw_path.is_file()
        or _sha256_file(raw_path) != manifest.get("raw_inventory_sha256")
        or not stderr_path.is_file()
        or _sha256_file(stderr_path) != manifest.get("stderr_sha256")
    ):
        raise AVFoundationFormatInventoryError("Raw observation identity changed.")
    observation = _load_json(raw_path, label="raw format inventory")
    if observation.get("schema_version") != OBSERVATION_SCHEMA:
        raise AVFoundationFormatInventoryError("Observation schema changed.")
    if observation.get("contract_sha256") != contract_sha256:
        raise AVFoundationFormatInventoryError("Observation contract changed.")
    if observation.get("observer_role") != "device_format_enumeration_only":
        raise AVFoundationFormatInventoryError("Observer role changed.")
    if (
        observation.get("camera_name_requested")
        != contract["device"]["exact_localized_name"]
    ):
        raise AVFoundationFormatInventoryError("Requested camera identity changed.")
    detected_names = observation.get("detected_device_names")
    if (
        not isinstance(detected_names, list)
        or any(not isinstance(name, str) for name in detected_names)
        or detected_names != sorted(detected_names)
    ):
        raise AVFoundationFormatInventoryError("Detected camera inventory is malformed.")
    device_match_count = observation.get("device_match_count")
    if (
        not isinstance(device_match_count, int)
        or isinstance(device_match_count, bool)
        or device_match_count < 0
    ):
        raise AVFoundationFormatInventoryError("Device match count is malformed.")
    if (
        observation.get("capture_session_created") is not False
        or observation.get("capture_session_started") is not False
        or observation.get("source_sample_count") != 0
    ):
        raise AVFoundationFormatInventoryError(
            "Observation widened into capture behavior."
        )

    return_code = manifest.get("return_code")
    prerequisite_available = (
        return_code == 0
        and observation.get("status") == "observed"
        and device_match_count == 1
        and observation.get("device_localized_name")
        == contract["device"]["exact_localized_name"]
    )
    if return_code == 0 and not prerequisite_available:
        raise AVFoundationFormatInventoryError(
            "Successful observer result has inconsistent device identity."
        )
    formats: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    selected: dict[str, Any] | None = None
    if prerequisite_available:
        formats = _validate_observed_formats(observation)
        rule = contract["selection_rule"]
        target_fps = float(rule["target_fps"])
        preference = {
            subtype: index
            for index, subtype in enumerate(rule["media_subtype_preference"])
        }
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
        "observation_manifest_sha256": _sha256_file(manifest_path),
        "raw_inventory_sha256": _sha256_file(raw_path),
        "proof_class": "camera_device_format_inventory",
        "verdict": verdict,
        "device_match_count": device_match_count,
        "device_localized_name": observation.get("device_localized_name"),
        "device_unique_id": observation.get("device_unique_id"),
        "device_model_id": observation.get("device_model_id"),
        "format_count": len(formats),
        "frame_rate_range_count": sum(
            len(row["frame_rate_ranges"]) for row in formats
        ),
        "exact_dimension_candidate_count": len(candidates),
        "eligible_candidate_count": len(eligible),
        "eligible_candidates": eligible,
        "selected_candidate": selected,
        "selection_does_not_authorize_stream_execution": True,
        "budget": manifest["budget"],
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
    evaluation_path = output_root / "evaluation.json"
    _write_json(evaluation_path, evaluation)
    receipt_without_digest = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_sha256": contract_sha256,
        "source_sha256": runtime["source_sha256"],
        "evaluator_sha256": runtime["evaluator_sha256"],
        "compiler_sha256": runtime["compiler_sha256"],
        "binary_sha256": runtime["binary_sha256"],
        "observation_manifest_sha256": _sha256_file(manifest_path),
        "raw_inventory_sha256": _sha256_file(raw_path),
        "evaluation_digest": _canonical_digest(evaluation),
        "proof_class": "camera_device_format_inventory",
        "verdict": verdict,
        "budget": manifest["budget"],
        "authority": contract["authority"],
    }
    receipt = {
        **receipt_without_digest,
        "receipt_digest": _canonical_digest(receipt_without_digest),
    }
    _write_json(output_root / "receipt.json", receipt)
    return evaluation, receipt

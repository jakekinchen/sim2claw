"""Evaluator-owned C922 callback measurement with a frozen lock window."""

from __future__ import annotations

import argparse
import math
import subprocess
from pathlib import Path
from typing import Any

from sim2claw.avfoundation_format_inventory import (
    AVFoundationFormatInventoryError,
    _canonical_digest,
    _load_json,
    _sha256_file,
    _write_json,
)


CONTRACT_SCHEMA = "sim2claw.avfoundation_c922_callback_delivery_contract.v3"
OBSERVATION_SCHEMA = "sim2claw.avfoundation_c922_callback_observation.v3"
EVENT_SCHEMA = "sim2claw.avfoundation_c922_callback_event.v3"
PRELAUNCH_SCHEMA = "sim2claw.avfoundation_c922_callback_prelaunch.v3"
ATTEMPT_SCHEMA = "sim2claw.avfoundation_c922_callback_attempt.v3"
EVALUATION_SCHEMA = "sim2claw.avfoundation_c922_callback_evaluation.v3"
RECEIPT_SCHEMA = "sim2claw.avfoundation_c922_callback_receipt.v3"
BINARY_RELATIVE_PATH = "runtime/avfoundation-c922-callback-delivery-v3"


class CallbackDeliveryV3Error(AVFoundationFormatInventoryError):
    """Raised when v3 callback evidence fails closed."""


def _finite(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CallbackDeliveryV3Error(f"{label} is not numeric.")
    result = float(value)
    if not math.isfinite(result):
        raise CallbackDeliveryV3Error(f"{label} is not finite.")
    return result


def load_callback_contract(path: Path) -> dict[str, Any]:
    contract = _load_json(path, label="callback-delivery v3 contract")
    if contract.get("schema_version") != CONTRACT_SCHEMA:
        raise CallbackDeliveryV3Error("Callback v3 contract schema changed.")
    if contract.get("status") != "preregistered_before_implementation_and_observation":
        raise CallbackDeliveryV3Error("Callback v3 status changed.")
    if contract.get("baseline_commit") != (
        "56fc242dc0b28af853663cb8b1b7228181db441c"
    ):
        raise CallbackDeliveryV3Error("Callback v3 baseline changed.")
    if contract.get("device") != {
        "media_type": "video",
        "exact_localized_name": "C922 Pro Stream Webcam",
        "exact_unique_id": "0x8310000046d085c",
        "exact_model_id": "UVC Camera VendorID_1133 ProductID_2140",
        "exact_match_count_required": 1,
    }:
        raise CallbackDeliveryV3Error("Callback v3 device changed.")
    if contract.get("candidate") != {
        "format_index": 16,
        "frame_rate_range_index": 0,
        "width": 640,
        "height": 480,
        "media_subtype_fourcc": "420v",
        "supported_fps": 30.00003000003,
        "frame_duration_seconds": 0.03333330000003333,
    }:
        raise CallbackDeliveryV3Error("Callback v3 candidate changed.")
    if contract.get("changed_mechanism") != {
        "device_lock_acquired_after_input_output_association": True,
        "device_lock_held_through_commit": True,
        "device_lock_held_through_start_return_and_verification": True,
        "device_unlock_after_start_verification": True,
        "session_preset_assignment": False,
        "output_dimension_keys": False,
        "post_start_repair": False,
    }:
        raise CallbackDeliveryV3Error("Callback v3 mechanism changed.")
    if contract.get("configuration_order") != [
        "create_session",
        "begin_configuration",
        "add_exact_device_input",
        "add_video_data_output_requesting_only_420v",
        "lock_associated_device",
        "set_active_format_16",
        "set_active_min_and_max_frame_duration_from_range_0",
        "record_format_while_locked_before_commit",
        "commit_configuration_while_device_locked",
        "record_format_while_locked_after_commit",
        "start_session_while_device_locked_only_if_post_commit_format_exact",
        "record_format_while_locked_after_start",
        "unlock_device",
        "observe_delivered_sample_buffers_only_if_post_start_format_exact",
        "stop_session",
    ]:
        raise CallbackDeliveryV3Error("Callback v3 order changed.")
    if contract.get("observation") != {
        "duration_seconds": 10.0,
        "always_discards_late_video_frames": True,
        "output_pixel_format_fourcc": "420v",
        "output_width_height_conversion_keys_allowed": False,
        "post_commit_format_mismatch_starts_session": False,
        "post_start_format_mismatch_continues_session": False,
        "typed_codable_primitive_artifacts_only": True,
        "prelaunch_manifest_before_session": True,
        "raw_observer_may_score": False,
    }:
        raise CallbackDeliveryV3Error("Callback v3 observation changed.")
    if contract.get("evaluator") != {
        "minimum_output_callback_count": 240,
        "maximum_dropped_callback_count_for_verified": 0,
        "maximum_pts_interval_multiplier": 1.5,
        "require_exact_format_before_commit": True,
        "require_exact_format_after_commit": True,
        "require_exact_format_after_start": True,
        "require_lock_held_at_all_three_format_stages": True,
        "require_unlock_before_callback_window": True,
        "require_strictly_increasing_pts": True,
        "require_numeric_pts_and_duration": True,
        "require_all_output_dimensions_exact": True,
        "require_all_output_subtypes_exact": True,
        "verdicts": [
            "callback_delivery_verified",
            "callback_delivery_degraded",
            "prerequisite_abstention",
        ],
        "threshold_changes_after_observation": False,
        "observer_self_scoring": False,
    }:
        raise CallbackDeliveryV3Error("Callback v3 evaluator changed.")
    if contract.get("operation_budget") != {
        "observation_attempts_maximum": 1,
        "capture_sessions_maximum": 1,
        "capture_duration_seconds_maximum": 10.0,
        "source_callbacks_maximum": 600,
        "d405_lifecycle_operations_maximum": 0,
        "robot_motion_trials_maximum": 0,
        "simulator_replays_maximum": 0,
        "provider_calls_maximum": 0,
    }:
        raise CallbackDeliveryV3Error("Callback v3 budget changed.")
    authority = contract.get("authority")
    allowed_true = {"c922_capture_session", "camera_frame_callback_observation"}
    if not isinstance(authority, dict) or any(
        value is not (key in allowed_true) for key, value in authority.items()
    ):
        raise CallbackDeliveryV3Error("Callback v3 authority changed.")
    return contract


def _verify_inputs(contract: dict[str, Any], *, repo_root: Path) -> None:
    sealed = contract.get("sealed_inventory")
    expected_sealed = {
        "contract_path": "configs/evaluations/avfoundation_format_inventory_v2.json",
        "contract_sha256": "ec25b9443f024972a8f4f6f9d7c1b600ad1893b4e7cb3e379f5be3db4c841dcd",
        "raw_inventory_path": "outputs/avfoundation-format-inventory-v2/observed/raw/inventory.json",
        "raw_inventory_sha256": "3754a62fa643359fa1f13484bd4f86ba7c1ab13d234b2a3f7f5b5bcb60e830a2",
        "evaluation_path": "outputs/avfoundation-format-inventory-v2/evaluated/evaluation.json",
        "evaluation_sha256": "3c59915c81f9d8073f02acd4ca3eae8b9c715db9485e9e838ca4638427e05d7d",
        "receipt_path": "outputs/avfoundation-format-inventory-v2/evaluated/receipt.json",
        "receipt_sha256": "14c8f82147611854ac4ecc317426f447ac4b3fbccef9cd133e1cd4026287e98f",
        "receipt_digest": "9c42f8a55357f2508897a8515d3b7d3dba98bbe7409ba246c1c8b14ccec932ac",
        "verdict": "supported_exact_or_fractional_rate_candidate",
        "candidate_identity_reusable": True,
    }
    if sealed != expected_sealed:
        raise CallbackDeliveryV3Error("Callback v3 inventory binding changed.")
    for key in ("contract", "raw_inventory", "evaluation", "receipt"):
        candidate = repo_root / sealed[f"{key}_path"]
        if (
            not candidate.is_file()
            or _sha256_file(candidate) != sealed[f"{key}_sha256"]
        ):
            raise CallbackDeliveryV3Error(f"Callback v3 inventory {key} changed.")
    v2 = contract.get("v2_terminal_evidence")
    expected_v2 = {
        "implementation_commit": "c8d2f50100f5899d821ef5ed85750b207d97d21c",
        "raw_observation_sha256": "593c3d3e62bb49e4a08713bab63e6e699584a2ad1da91341452318362b2d4314",
        "evaluation_sha256": "a889450f94187906f745779620ed769e7e642def45e9d458a390c3064fce1935",
        "receipt_sha256": "5dd301ab462395706f6b4d505d7f41a829871542682967da795b5dab17950c2f",
        "receipt_digest": "ae6dd332ba20710bd06dff2bf3bba49d3662d2fd727eac05243a6d6bae84c4fd",
        "verdict": "callback_delivery_degraded",
        "failed_gates": [
            "exact_format_after_start",
            "minimum_output_callbacks",
            "exact_dimensions",
            "strictly_increasing_pts",
            "bounded_pts_interval",
        ],
        "format_after_commit": "640x480_420v_0.03333330000003333s",
        "session_preset_after_commit": "AVCaptureSessionPresetHigh",
        "format_after_start": "1920x1080_420v_0.0416666006945489s",
        "session_preset_after_start": "AVCaptureSessionPresetHigh",
        "sample_output_count": 1,
        "sample_dropped_count": 0,
        "retry_authorized": False,
    }
    if v2 != expected_v2:
        raise CallbackDeliveryV3Error("Callback v2 terminal binding changed.")
    paths = {
        "raw_observation": repo_root
        / "outputs/avfoundation-c922-callback-delivery-v2/observed/raw/observation.json",
        "evaluation": repo_root
        / "outputs/avfoundation-c922-callback-delivery-v2/evaluated/evaluation.json",
        "receipt": repo_root
        / "outputs/avfoundation-c922-callback-delivery-v2/evaluated/receipt.json",
    }
    for key, path in paths.items():
        if not path.is_file() or _sha256_file(path) != v2[f"{key}_sha256"]:
            raise CallbackDeliveryV3Error(f"Callback v2 {key} changed.")


def _budget() -> dict[str, Any]:
    return {
        "observation_attempts_used": 1,
        "capture_sessions_used": 1,
        "capture_duration_seconds_requested": 10.0,
        "d405_lifecycle_operations_used": 0,
        "robot_motion_trials_used": 0,
        "simulator_replays_used": 0,
        "provider_calls_used": 0,
    }


def compile_callback_observer(
    *,
    contract_path: Path,
    source_path: Path,
    evaluator_path: Path,
    binary_path: Path,
    repo_root: Path,
) -> dict[str, Any]:
    contract = load_callback_contract(contract_path)
    _verify_inputs(contract, repo_root=repo_root)
    runtime = contract["runtime_identity"]
    if (repo_root / runtime["observer_source_path"]).resolve() != source_path.resolve():
        raise CallbackDeliveryV3Error("Callback v3 source path changed.")
    if (repo_root / runtime["evaluator_path"]).resolve() != evaluator_path.resolve():
        raise CallbackDeliveryV3Error("Callback v3 evaluator path changed.")
    compiler = Path(runtime["compiler_path"])
    version = subprocess.run(
        [str(compiler), "--version"], check=False, capture_output=True, text=True
    )
    if version.returncode != 0 or not version.stdout.startswith(
        runtime["swift_version_prefix"]
    ):
        raise CallbackDeliveryV3Error("Callback v3 compiler changed.")
    source = source_path.read_text(encoding="utf-8")
    ordered = (
        "session.addInput(input)",
        "session.addOutput(output)",
        "try device.lockForConfiguration()",
        "device.activeFormat = format",
        '"format_while_locked_before_commit"',
        "session.commitConfiguration()",
        '"format_while_locked_after_commit"',
        "session.startRunning()",
        '"format_while_locked_after_start"',
        '"device_unlock_returned"',
    )
    try:
        offsets = [source.index(token) for token in ordered]
    except ValueError as error:
        raise CallbackDeliveryV3Error(
            "Callback v3 source lacks a required operation."
        ) from error
    if offsets != sorted(offsets):
        raise CallbackDeliveryV3Error("Callback v3 source order changed.")
    post_start = source[source.index("session.startRunning()") :]
    if post_start.index("device.unlockForConfiguration()") < post_start.index(
        '"format_while_locked_after_start"'
    ):
        raise CallbackDeliveryV3Error(
            "Callback v3 source unlocks before post-start verification."
        )
    if post_start.index("output.setSampleBufferDelegate") < post_start.index(
        '"device_unlock_returned"'
    ):
        raise CallbackDeliveryV3Error(
            "Callback v3 source opens its callback window before device unlock."
        )
    forbidden = (
        "JSONSerialization",
        "AVCaptureSessionPresetInputPriority",
        "[String: Any]",
        "kCVPixelBufferWidthKey",
        "kCVPixelBufferHeightKey",
        "session.sessionPreset =",
    )
    if any(token in source for token in forbidden):
        raise CallbackDeliveryV3Error("Callback v3 source contains forbidden logic.")
    binary_path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [str(compiler), str(source_path), "-o", str(binary_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise CallbackDeliveryV3Error(
            f"Callback v3 compilation failed: {completed.stderr.strip()}"
        )
    return {
        "contract_sha256": _sha256_file(contract_path),
        "source_sha256": _sha256_file(source_path),
        "evaluator_sha256": _sha256_file(evaluator_path),
        "compiler_path": str(compiler),
        "compiler_sha256": _sha256_file(compiler),
        "swift_version": version.stdout.strip(),
        "binary_path": BINARY_RELATIVE_PATH,
        "binary_sha256": _sha256_file(binary_path),
    }


def run_callback_observation(
    *,
    contract_path: Path,
    source_path: Path,
    evaluator_path: Path,
    output_root: Path,
    repo_root: Path,
) -> dict[str, Any]:
    contract = load_callback_contract(contract_path)
    if output_root.exists():
        raise CallbackDeliveryV3Error("Callback v3 output exists; retry forbidden.")
    runtime = compile_callback_observer(
        contract_path=contract_path,
        source_path=source_path,
        evaluator_path=evaluator_path,
        binary_path=output_root / BINARY_RELATIVE_PATH,
        repo_root=repo_root,
    )
    prelaunch = {
        "schema_version": PRELAUNCH_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": runtime["contract_sha256"],
        "proof_class": "camera_source_callback_delivery",
        "status": "prepared_before_capture_session",
        "runtime_identity": runtime,
        "raw_observation_path": "raw/observation.json",
        "stderr_path": "raw/observer.stderr.log",
        "budget": _budget(),
        "authority": contract["authority"],
    }
    prelaunch_path = output_root / "attempt-prelaunch.json"
    _write_json(prelaunch_path, prelaunch)
    raw_path = output_root / "raw/observation.json"
    stderr_path = output_root / "raw/observer.stderr.log"
    device = contract["device"]
    candidate = contract["candidate"]
    command = [
        str(output_root / BINARY_RELATIVE_PATH),
        "--camera-name",
        device["exact_localized_name"],
        "--camera-unique-id",
        device["exact_unique_id"],
        "--camera-model-id",
        device["exact_model_id"],
        "--format-index",
        str(candidate["format_index"]),
        "--range-index",
        str(candidate["frame_rate_range_index"]),
        "--width",
        str(candidate["width"]),
        "--height",
        str(candidate["height"]),
        "--subtype",
        candidate["media_subtype_fourcc"],
        "--supported-fps",
        str(candidate["supported_fps"]),
        "--duration-seconds",
        str(contract["observation"]["duration_seconds"]),
        "--maximum-callbacks",
        str(contract["operation_budget"]["source_callbacks_maximum"]),
        "--contract-sha256",
        runtime["contract_sha256"],
        "--output",
        str(raw_path),
    ]
    timed_out = False
    try:
        completed = subprocess.run(
            command, check=False, capture_output=True, text=True, timeout=25.0
        )
        return_code = completed.returncode
        stderr_text = completed.stderr
    except subprocess.TimeoutExpired as error:
        timed_out = True
        return_code = 124
        stderr_text = (
            (error.stderr.decode() if isinstance(error.stderr, bytes) else error.stderr)
            or ""
        ) + "observer_timeout_after_25_seconds\n"
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.write_text(stderr_text, encoding="utf-8")
    attempt = {
        "schema_version": ATTEMPT_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": runtime["contract_sha256"],
        "proof_class": "camera_source_callback_delivery",
        "status": (
            "observer_timed_out_without_retry"
            if timed_out
            else (
                "observer_completed_with_raw"
                if raw_path.is_file()
                else "observer_failed_without_raw"
            )
        ),
        "prelaunch_manifest_path": "attempt-prelaunch.json",
        "prelaunch_manifest_sha256": _sha256_file(prelaunch_path),
        "runtime_identity": runtime,
        "return_code": return_code,
        "raw_observation_path": "raw/observation.json",
        "raw_observation_sha256": (
            _sha256_file(raw_path) if raw_path.is_file() else None
        ),
        "stderr_path": "raw/observer.stderr.log",
        "stderr_sha256": _sha256_file(stderr_path),
        "budget": _budget(),
        "authority": contract["authority"],
    }
    _write_json(output_root / "attempt.json", attempt)
    return attempt


def _validate_events(
    observation: dict[str, Any], *, contract: dict[str, Any]
) -> dict[str, Any]:
    events = observation.get("events")
    if not isinstance(events, list) or not events:
        raise CallbackDeliveryV3Error("Callback v3 events are missing.")
    previous_host = -1
    for index, event in enumerate(events):
        if not isinstance(event, dict) or event.get("schemaVersion") != EVENT_SCHEMA:
            raise CallbackDeliveryV3Error("Callback v3 event schema changed.")
        if event.get("eventIndex") != index:
            raise CallbackDeliveryV3Error(
                "Callback v3 event sequence is duplicated or replayed."
            )
        host = event.get("hostContinuousNS")
        if not isinstance(host, int) or isinstance(host, bool) or host <= previous_host:
            raise CallbackDeliveryV3Error("Callback v3 host time is non-monotonic.")
        previous_host = host
    types = [event.get("eventType") for event in events]
    base = [
        "observer_started",
        "authorization_observed",
        "device_discovery_observed",
        "format_while_locked_before_commit",
        "format_while_locked_after_commit",
        "observer_finished",
    ]
    for event_type in base:
        if types.count(event_type) != 1:
            raise CallbackDeliveryV3Error(
                f"Callback v3 event count changed for {event_type}."
            )
    outputs = [event for event in events if event.get("eventType") == "sample_output"]
    drops = [event for event in events if event.get("eventType") == "sample_dropped"]
    if len(outputs) + len(drops) > contract["operation_budget"]["source_callbacks_maximum"]:
        raise CallbackDeliveryV3Error("Callback v3 callback budget exceeded.")
    return {"events": events, "types": types, "outputs": outputs, "drops": drops}


def _stage_exact(event: dict[str, Any], *, contract: dict[str, Any]) -> bool:
    candidate = contract["candidate"]
    device = contract["device"]
    expected = {
        "deviceLocalizedName": device["exact_localized_name"],
        "deviceUniqueID": device["exact_unique_id"],
        "deviceModelID": device["exact_model_id"],
        "formatIndex": candidate["format_index"],
        "frameRateRangeIndex": candidate["frame_rate_range_index"],
        "formatWidth": candidate["width"],
        "formatHeight": candidate["height"],
        "formatMediaSubtype": candidate["media_subtype_fourcc"],
        "supportedFPS": candidate["supported_fps"],
        "deviceLockHeld": True,
    }
    if any(event.get(key) != value for key, value in expected.items()):
        return False
    target = candidate["frame_duration_seconds"]
    return (
        abs(_finite(event.get("activeMinFrameDurationSeconds"), label="min duration") - target)
        < 1e-12
        and abs(
            _finite(event.get("activeMaxFrameDurationSeconds"), label="max duration")
            - target
        )
        < 1e-12
        and isinstance(event.get("sessionPresetRawValue"), str)
        and bool(event["sessionPresetRawValue"])
    )


def _stage_summary(event: dict[str, Any], *, exact: bool) -> dict[str, Any]:
    return {
        "exact": exact,
        "lock_held": event.get("deviceLockHeld"),
        "width": event.get("formatWidth"),
        "height": event.get("formatHeight"),
        "subtype": event.get("formatMediaSubtype"),
        "minimum_frame_duration_seconds": event.get(
            "activeMinFrameDurationSeconds"
        ),
        "maximum_frame_duration_seconds": event.get(
            "activeMaxFrameDurationSeconds"
        ),
        "session_preset_raw_value": event.get("sessionPresetRawValue"),
    }


def evaluate_callback_observation(
    *,
    contract_path: Path,
    observation_root: Path,
    output_root: Path,
    source_path: Path,
    evaluator_path: Path,
    repo_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = load_callback_contract(contract_path)
    _verify_inputs(contract, repo_root=repo_root)
    if output_root.exists():
        raise CallbackDeliveryV3Error("Callback v3 evaluation replay forbidden.")
    attempt_path = observation_root / "attempt.json"
    prelaunch_path = observation_root / "attempt-prelaunch.json"
    attempt = _load_json(attempt_path, label="callback v3 attempt")
    prelaunch = _load_json(prelaunch_path, label="callback v3 prelaunch")
    contract_sha = _sha256_file(contract_path)
    if (
        attempt.get("schema_version") != ATTEMPT_SCHEMA
        or prelaunch.get("schema_version") != PRELAUNCH_SCHEMA
        or attempt.get("contract_sha256") != contract_sha
        or prelaunch.get("contract_sha256") != contract_sha
    ):
        raise CallbackDeliveryV3Error("Callback v3 attempt identity changed.")
    if (
        attempt.get("authority") != contract["authority"]
        or prelaunch.get("authority") != contract["authority"]
        or attempt.get("budget") != _budget()
        or prelaunch.get("budget") != _budget()
    ):
        raise CallbackDeliveryV3Error("Callback v3 authority or budget changed.")
    if attempt.get("prelaunch_manifest_sha256") != _sha256_file(prelaunch_path):
        raise CallbackDeliveryV3Error("Callback v3 prelaunch changed.")
    runtime = attempt.get("runtime_identity")
    if runtime != prelaunch.get("runtime_identity"):
        raise CallbackDeliveryV3Error("Callback v3 runtime substitution detected.")
    expected_runtime = {
        "contract_sha256": contract_sha,
        "source_sha256": _sha256_file(source_path),
        "evaluator_sha256": _sha256_file(evaluator_path),
        "compiler_path": "/usr/bin/swiftc",
        "compiler_sha256": _sha256_file(Path("/usr/bin/swiftc")),
        "swift_version": (
            runtime.get("swift_version") if isinstance(runtime, dict) else None
        ),
        "binary_path": BINARY_RELATIVE_PATH,
        "binary_sha256": _sha256_file(observation_root / BINARY_RELATIVE_PATH),
    }
    if runtime != expected_runtime:
        raise CallbackDeliveryV3Error("Callback v3 runtime identity changed.")
    raw_path = observation_root / "raw/observation.json"
    raw_available = raw_path.is_file()
    raw_sha = _sha256_file(raw_path) if raw_available else None
    if attempt.get("raw_observation_sha256") != raw_sha:
        raise CallbackDeliveryV3Error("Callback v3 raw identity changed.")

    verdict = "prerequisite_abstention"
    failed_gates: list[str] = []
    stage_identity: dict[str, Any] = {
        "before_commit": None,
        "after_commit": None,
        "after_start": None,
    }
    statistics: dict[str, Any] = {
        "format_stage_identity": stage_identity,
        "sample_output_count": 0,
        "sample_dropped_count": 0,
        "pts_interval_count": 0,
        "maximum_pts_interval_seconds": None,
        "mean_pts_interval_seconds": None,
        "delivered_dimensions": [],
        "delivered_media_subtypes": [],
        "delivered_pixel_formats": [],
    }
    if attempt.get("return_code") == 0 and raw_available:
        observation = _load_json(raw_path, label="callback v3 observation")
        if (
            observation.get("schemaVersion") != OBSERVATION_SCHEMA
            or observation.get("contractSHA256") != contract_sha
            or observation.get("proofClass") != "camera_source_callback_delivery"
            or observation.get("observerRole") != "source_callback_observer_only"
        ):
            raise CallbackDeliveryV3Error("Callback v3 observation identity changed.")
        expected = {
            "cameraNameRequested": contract["device"]["exact_localized_name"],
            "cameraUniqueIDRequested": contract["device"]["exact_unique_id"],
            "cameraModelIDRequested": contract["device"]["exact_model_id"],
            "formatIndexRequested": 16,
            "frameRateRangeIndexRequested": 0,
            "durationSecondsRequested": 10.0,
            "maximumCallbacks": 600,
            "captureSessionsUsed": 1,
            "d405LifecycleOperationsUsed": 0,
            "robotMotionTrialsUsed": 0,
            "simulatorReplaysUsed": 0,
            "providerCallsUsed": 0,
        }
        if any(observation.get(key) != value for key, value in expected.items()):
            raise CallbackDeliveryV3Error("Callback v3 request or authority changed.")
        parsed = _validate_events(observation, contract=contract)
        events = parsed["events"]
        types = parsed["types"]
        outputs = parsed["outputs"]
        drops = parsed["drops"]
        if (
            observation.get("sampleOutputCount") != len(outputs)
            or observation.get("sampleDroppedCount") != len(drops)
        ):
            raise CallbackDeliveryV3Error("Callback v3 event counts changed.")
        authorization = next(
            event for event in events if event.get("eventType") == "authorization_observed"
        )
        discovery = next(
            event
            for event in events
            if event.get("eventType") == "device_discovery_observed"
        )
        if (
            authorization.get("authorizationStatusRawValue") != 3
            or discovery.get("exactMatchCount") != 1
        ):
            raise CallbackDeliveryV3Error("Callback v3 preconditions changed.")
        before_event = next(
            event
            for event in events
            if event.get("eventType") == "format_while_locked_before_commit"
        )
        commit_event = next(
            event
            for event in events
            if event.get("eventType") == "format_while_locked_after_commit"
        )
        before_exact = _stage_exact(before_event, contract=contract)
        commit_exact = _stage_exact(commit_event, contract=contract)
        stage_identity["before_commit"] = _stage_summary(
            before_event, exact=before_exact
        )
        stage_identity["after_commit"] = _stage_summary(
            commit_event, exact=commit_exact
        )
        if not before_exact or not commit_exact:
            if "session_start_returned" in types:
                raise CallbackDeliveryV3Error(
                    "Callback v3 started after pre-start mismatch."
                )
            failed_gates = [
                name
                for name, passed in (
                    ("exact_format_before_commit", before_exact),
                    ("exact_format_after_commit", commit_exact),
                )
                if not passed
            ]
        else:
            lifecycle = (
                "session_start_returned",
                "format_while_locked_after_start",
                "device_unlock_returned",
                "session_stop_returned",
            )
            if any(types.count(event_type) != 1 for event_type in lifecycle):
                raise CallbackDeliveryV3Error(
                    "Callback v3 running lifecycle changed."
                )
            start = next(
                event
                for event in events
                if event.get("eventType") == "session_start_returned"
            )
            start_event = next(
                event
                for event in events
                if event.get("eventType") == "format_while_locked_after_start"
            )
            unlock = next(
                event
                for event in events
                if event.get("eventType") == "device_unlock_returned"
            )
            stop = next(
                event
                for event in events
                if event.get("eventType") == "session_stop_returned"
            )
            start_exact = _stage_exact(start_event, contract=contract)
            if any(
                event.get("eventIndex", -1) <= unlock.get("eventIndex", -1)
                for event in outputs + drops
            ):
                raise CallbackDeliveryV3Error(
                    "Callback v3 source callback preceded device unlock."
                )
            stage_identity["after_start"] = _stage_summary(
                start_event, exact=start_exact
            )
            dimensions = sorted(
                {
                    (event.get("formatWidth"), event.get("formatHeight"))
                    for event in outputs
                }
            )
            subtypes = sorted(
                {event.get("formatMediaSubtype") for event in outputs}
            )
            pixels = sorted({event.get("pixelFormat") for event in outputs})
            pts: list[float] = []
            duration_numeric = True
            for event in outputs:
                pts_value = event.get("samplePTS")
                duration_value = event.get("sampleDuration")
                if not isinstance(pts_value, dict) or not isinstance(
                    duration_value, dict
                ):
                    raise CallbackDeliveryV3Error(
                        "Callback v3 timing is malformed."
                    )
                if not pts_value.get("valid") or not pts_value.get("numeric"):
                    duration_numeric = False
                else:
                    pts.append(_finite(pts_value.get("seconds"), label="PTS"))
                if not duration_value.get("valid") or not duration_value.get(
                    "numeric"
                ):
                    duration_numeric = False
                else:
                    _finite(duration_value.get("seconds"), label="duration")
            intervals = [
                right - left for left, right in zip(pts, pts[1:], strict=False)
            ]
            maximum_interval = max(intervals) if intervals else None
            maximum_allowed = (
                contract["candidate"]["frame_duration_seconds"]
                * contract["evaluator"]["maximum_pts_interval_multiplier"]
            )
            statistics.update(
                {
                    "sample_output_count": len(outputs),
                    "sample_dropped_count": len(drops),
                    "pts_interval_count": len(intervals),
                    "maximum_pts_interval_seconds": maximum_interval,
                    "mean_pts_interval_seconds": (
                        sum(intervals) / len(intervals) if intervals else None
                    ),
                    "maximum_pts_interval_allowed_seconds": maximum_allowed,
                    "delivered_dimensions": [list(item) for item in dimensions],
                    "delivered_media_subtypes": subtypes,
                    "delivered_pixel_formats": pixels,
                }
            )
            candidate = contract["candidate"]
            gates = {
                "exact_format_after_start": start_exact,
                "session_started": start.get("sessionRunning") is True,
                "device_unlocked_before_window": unlock.get("deviceLockHeld") is False,
                "session_stopped": stop.get("sessionRunning") is False,
                "minimum_output_callbacks": len(outputs) >= 240,
                "zero_dropped_callbacks": len(drops) == 0,
                "exact_dimensions": dimensions
                == [(candidate["width"], candidate["height"])],
                "exact_media_subtype": subtypes
                == [candidate["media_subtype_fourcc"]],
                "exact_pixel_format": pixels == [candidate["media_subtype_fourcc"]],
                "numeric_pts_and_duration": len(pts) == len(outputs)
                and duration_numeric,
                "strictly_increasing_pts": bool(intervals)
                and all(interval > 0 for interval in intervals),
                "bounded_pts_interval": maximum_interval is not None
                and maximum_interval <= maximum_allowed,
            }
            failed_gates = [name for name, passed in gates.items() if not passed]
            verdict = (
                "callback_delivery_verified"
                if not failed_gates
                else "callback_delivery_degraded"
            )
    else:
        failed_gates = ["observer_completed_with_raw"]

    evaluation = {
        "schema_version": EVALUATION_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": contract_sha,
        "proof_class": "camera_source_callback_delivery",
        "verdict": verdict,
        "failed_gates": failed_gates,
        "statistics": statistics,
        "observer_return_code": attempt.get("return_code"),
        "raw_observation_available": raw_available,
        "raw_observation_sha256": raw_sha,
        "budget": attempt.get("budget"),
        "claim_limits": contract["claim_limits"],
        "authority": contract["authority"],
    }
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": contract_sha,
        "proof_class": "camera_source_callback_delivery",
        "verdict": verdict,
        "evaluation_digest": _canonical_digest(evaluation),
        "attempt_sha256": _sha256_file(attempt_path),
        "prelaunch_sha256": _sha256_file(prelaunch_path),
        "raw_observation_sha256": raw_sha,
        "runtime_identity": runtime,
        "sealed_inventory_receipt_sha256": contract["sealed_inventory"][
            "receipt_sha256"
        ],
        "v2_terminal_receipt_sha256": contract["v2_terminal_evidence"][
            "receipt_sha256"
        ],
        "budget": attempt.get("budget"),
        "claim_limits": contract["claim_limits"],
        "authority": contract["authority"],
    }
    receipt["receipt_digest"] = _canonical_digest(receipt)
    output_root.mkdir(parents=True)
    _write_json(output_root / "evaluation.json", evaluation)
    receipt["evaluation_sha256"] = _sha256_file(output_root / "evaluation.json")
    receipt["receipt_digest"] = _canonical_digest(
        {key: value for key, value in receipt.items() if key != "receipt_digest"}
    )
    _write_json(output_root / "receipt.json", receipt)
    return evaluation, receipt


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    observe = commands.add_parser("observe")
    observe.add_argument("--output-root", type=Path, required=True)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--observation-root", type=Path, required=True)
    evaluate.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    root = _repo_root()
    contract = (
        root / "configs/evaluations/avfoundation_c922_callback_delivery_v3.json"
    )
    source = root / "tools/macos/AVFoundationCallbackDeliveryV3.swift"
    evaluator = root / "src/sim2claw/avfoundation_callback_delivery_v3.py"
    if args.command == "observe":
        run_callback_observation(
            contract_path=contract,
            source_path=source,
            evaluator_path=evaluator,
            output_root=args.output_root,
            repo_root=root,
        )
    else:
        evaluate_callback_observation(
            contract_path=contract,
            observation_root=args.observation_root,
            output_root=args.output_root,
            source_path=source,
            evaluator_path=evaluator,
            repo_root=root,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

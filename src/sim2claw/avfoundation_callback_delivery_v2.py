"""Evaluator-owned post-input-association C922 callback measurement."""

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


CONTRACT_SCHEMA = "sim2claw.avfoundation_c922_callback_delivery_contract.v2"
OBSERVATION_SCHEMA = "sim2claw.avfoundation_c922_callback_observation.v2"
EVENT_SCHEMA = "sim2claw.avfoundation_c922_callback_event.v2"
PRELAUNCH_SCHEMA = "sim2claw.avfoundation_c922_callback_prelaunch.v2"
ATTEMPT_SCHEMA = "sim2claw.avfoundation_c922_callback_attempt.v2"
EVALUATION_SCHEMA = "sim2claw.avfoundation_c922_callback_evaluation.v2"
RECEIPT_SCHEMA = "sim2claw.avfoundation_c922_callback_receipt.v2"
BINARY_RELATIVE_PATH = "runtime/avfoundation-c922-callback-delivery-v2"


class CallbackDeliveryV2Error(AVFoundationFormatInventoryError):
    """Raised when v2 callback evidence or authority fails closed."""


def _finite_number(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CallbackDeliveryV2Error(f"{label} is not numeric.")
    result = float(value)
    if not math.isfinite(result):
        raise CallbackDeliveryV2Error(f"{label} is not finite.")
    return result


def load_callback_contract(path: Path) -> dict[str, Any]:
    contract = _load_json(path, label="callback-delivery v2 contract")
    if contract.get("schema_version") != CONTRACT_SCHEMA:
        raise CallbackDeliveryV2Error("Callback v2 contract schema changed.")
    if contract.get("status") != "preregistered_before_implementation_and_observation":
        raise CallbackDeliveryV2Error("Callback v2 contract status changed.")
    if contract.get("baseline_commit") != (
        "5d62e15816aa4a1bd7902585a12aeb88ed2d4202"
    ):
        raise CallbackDeliveryV2Error("Callback v2 baseline changed.")
    if contract.get("device") != {
        "media_type": "video",
        "exact_localized_name": "C922 Pro Stream Webcam",
        "exact_unique_id": "0x8310000046d085c",
        "exact_model_id": "UVC Camera VendorID_1133 ProductID_2140",
        "exact_match_count_required": 1,
    }:
        raise CallbackDeliveryV2Error("Callback v2 device identity changed.")
    if contract.get("candidate") != {
        "format_index": 16,
        "frame_rate_range_index": 0,
        "width": 640,
        "height": 480,
        "media_subtype_fourcc": "420v",
        "supported_fps": 30.00003000003,
        "frame_duration_seconds": 0.03333330000003333,
    }:
        raise CallbackDeliveryV2Error("Callback v2 candidate changed.")
    expected_order = [
        "create_session",
        "begin_configuration",
        "add_exact_device_input",
        "add_video_data_output_requesting_only_420v",
        "lock_associated_device",
        "set_active_format_16",
        "set_active_min_and_max_frame_duration_from_range_0",
        "unlock_device",
        "record_format_after_input_association",
        "commit_configuration",
        "record_active_format_and_session_preset_after_commit",
        "start_session_only_if_post_commit_format_exact",
        "record_active_format_and_session_preset_after_start",
        "observe_delivered_sample_buffers",
        "stop_session",
    ]
    if contract.get("configuration_order") != expected_order:
        raise CallbackDeliveryV2Error("Callback v2 configuration order changed.")
    if contract.get("observation") != {
        "duration_seconds": 10.0,
        "always_discards_late_video_frames": True,
        "output_pixel_format_fourcc": "420v",
        "output_width_height_conversion_keys_allowed": False,
        "post_commit_format_mismatch_starts_session": False,
        "typed_codable_primitive_artifacts_only": True,
        "prelaunch_manifest_before_session": True,
        "raw_observer_may_score": False,
    }:
        raise CallbackDeliveryV2Error("Callback v2 observation rule changed.")
    if contract.get("evaluator") != {
        "minimum_output_callback_count": 240,
        "maximum_dropped_callback_count_for_verified": 0,
        "maximum_pts_interval_multiplier": 1.5,
        "require_exact_format_after_input_association": True,
        "require_exact_format_after_commit": True,
        "require_exact_format_after_start": True,
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
        raise CallbackDeliveryV2Error("Callback v2 evaluator rule changed.")
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
        raise CallbackDeliveryV2Error("Callback v2 operation budget changed.")
    authority = contract.get("authority")
    if not isinstance(authority, dict):
        raise CallbackDeliveryV2Error("Callback v2 authority is missing.")
    allowed_true = {"c922_capture_session", "camera_frame_callback_observation"}
    if any(value is not (key in allowed_true) for key, value in authority.items()):
        raise CallbackDeliveryV2Error("Callback v2 authority widened or narrowed.")
    return contract


def _verify_inputs(contract: dict[str, Any], *, repo_root: Path) -> None:
    sealed = contract["sealed_inventory"]
    expected = {
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
        "observation_reusable": False,
        "candidate_identity_reusable": True,
    }
    if sealed != expected:
        raise CallbackDeliveryV2Error("Sealed format inventory binding changed.")
    for key in ("contract", "raw_inventory", "evaluation", "receipt"):
        path = repo_root / sealed[f"{key}_path"]
        if not path.is_file() or _sha256_file(path) != sealed[f"{key}_sha256"]:
            raise CallbackDeliveryV2Error(
                f"Sealed format inventory {key} identity changed."
            )
    v1 = contract["v1_terminal_evidence"]
    expected_v1 = {
        "implementation_commit": "f00f4f11ad19e9b413482705df66e0a04e364099",
        "raw_observation_sha256": "9e3e2d574a7fa7db4a91b5d2f5e653bbc47fa88c82ee812e334993ea3a3fc671",
        "evaluation_sha256": "25827c4d318e593df3042d19ae12fa7ba9041de864600b9d991c31845e8988af",
        "receipt_sha256": "2096d836469662362e466f630fa1ede8b370412bf2e7a33592435e3c4436317b",
        "receipt_digest": "558aae78b9721dd92a4718ff9d88a9572d84d8f5fa4607c0825edf75edb21b16",
        "verdict": "callback_delivery_degraded",
        "failed_gates": ["exact_dimensions", "bounded_pts_interval"],
        "delivered_dimensions": [1920, 1080],
        "sample_output_count": 243,
        "sample_dropped_count": 0,
        "retry_authorized": False,
    }
    if v1 != expected_v1:
        raise CallbackDeliveryV2Error("Callback v1 terminal binding changed.")
    v1_paths = {
        "raw_observation": repo_root
        / "outputs/avfoundation-c922-callback-delivery-v1/observed/raw/observation.json",
        "evaluation": repo_root
        / "outputs/avfoundation-c922-callback-delivery-v1/evaluated/evaluation.json",
        "receipt": repo_root
        / "outputs/avfoundation-c922-callback-delivery-v1/evaluated/receipt.json",
    }
    for key, path in v1_paths.items():
        if not path.is_file() or _sha256_file(path) != v1[f"{key}_sha256"]:
            raise CallbackDeliveryV2Error(f"Callback v1 {key} identity changed.")


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
        raise CallbackDeliveryV2Error("Callback v2 source path changed.")
    if (repo_root / runtime["evaluator_path"]).resolve() != evaluator_path.resolve():
        raise CallbackDeliveryV2Error("Callback v2 evaluator path changed.")
    compiler = Path(runtime["compiler_path"])
    version = subprocess.run(
        [str(compiler), "--version"], check=False, capture_output=True, text=True
    )
    if version.returncode != 0 or not version.stdout.startswith(
        runtime["swift_version_prefix"]
    ):
        raise CallbackDeliveryV2Error("Swift compiler identity changed.")
    source = source_path.read_text(encoding="utf-8")
    required = (
        "struct CallbackEvent: Codable",
        "struct Observation: Codable",
        "session.addInput(input)",
        "session.addOutput(output)",
        "device.activeFormat = format",
        '"format_after_input_association"',
        "session.commitConfiguration()",
        '"format_after_commit"',
        "session.startRunning()",
        '"format_after_start"',
        "AVCaptureVideoDataOutputSampleBufferDelegate",
        "JSONEncoder()",
    )
    missing = [token for token in required if token not in source]
    if missing:
        raise CallbackDeliveryV2Error(
            f"Callback v2 source lacks required tokens: {missing}."
        )
    offsets = [source.index(token) for token in required[2:10]]
    if offsets != sorted(offsets):
        raise CallbackDeliveryV2Error("Callback v2 source order changed.")
    forbidden = (
        "JSONSerialization",
        "AVCaptureSessionPresetInputPriority",
        "[String: Any]",
        "kCVPixelBufferWidthKey",
        "kCVPixelBufferHeightKey",
    )
    found = [token for token in forbidden if token in source]
    if found:
        raise CallbackDeliveryV2Error(
            f"Callback v2 source contains forbidden tokens: {found}."
        )
    binary_path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [str(compiler), str(source_path), "-o", str(binary_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise CallbackDeliveryV2Error(
            f"Callback v2 observer compilation failed: {completed.stderr.strip()}"
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
        raise CallbackDeliveryV2Error(
            "Callback v2 observation output exists; retry forbidden."
        )
    binary = output_root / BINARY_RELATIVE_PATH
    runtime = compile_callback_observer(
        contract_path=contract_path,
        source_path=source_path,
        evaluator_path=evaluator_path,
        binary_path=binary,
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
        str(binary),
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
    completed = subprocess.run(
        command, check=False, capture_output=True, text=True, timeout=30.0
    )
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    attempt = {
        "schema_version": ATTEMPT_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": runtime["contract_sha256"],
        "proof_class": "camera_source_callback_delivery",
        "status": (
            "observer_completed_with_raw"
            if raw_path.is_file()
            else "observer_failed_without_raw"
        ),
        "prelaunch_manifest_path": "attempt-prelaunch.json",
        "prelaunch_manifest_sha256": _sha256_file(prelaunch_path),
        "runtime_identity": runtime,
        "return_code": completed.returncode,
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
        raise CallbackDeliveryV2Error("Callback v2 events are missing.")
    previous_host = -1
    for index, event in enumerate(events):
        if not isinstance(event, dict) or event.get("schemaVersion") != EVENT_SCHEMA:
            raise CallbackDeliveryV2Error("Callback v2 event schema changed.")
        if event.get("eventIndex") != index:
            raise CallbackDeliveryV2Error(
                "Callback v2 event sequence is duplicated or replayed."
            )
        host = event.get("hostContinuousNS")
        if not isinstance(host, int) or isinstance(host, bool) or host <= previous_host:
            raise CallbackDeliveryV2Error("Callback v2 host time is non-monotonic.")
        previous_host = host
    types = [event.get("eventType") for event in events]
    base_required = [
        "observer_started",
        "authorization_observed",
        "device_discovery_observed",
        "format_after_input_association",
        "format_after_commit",
        "observer_finished",
    ]
    missing = [event_type for event_type in base_required if event_type not in types]
    if missing:
        raise CallbackDeliveryV2Error(
            f"Callback v2 events lack required types: {missing}."
        )
    for event_type in base_required:
        if types.count(event_type) != 1:
            raise CallbackDeliveryV2Error(
                f"Callback v2 event count changed for {event_type}."
            )
    outputs = [event for event in events if event.get("eventType") == "sample_output"]
    drops = [event for event in events if event.get("eventType") == "sample_dropped"]
    if len(outputs) + len(drops) > contract["operation_budget"]["source_callbacks_maximum"]:
        raise CallbackDeliveryV2Error("Callback v2 source callback budget exceeded.")
    return {"events": events, "types": types, "outputs": outputs, "drops": drops}


def _format_stage_exact(
    event: dict[str, Any], *, contract: dict[str, Any]
) -> bool:
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
    }
    if any(event.get(key) != value for key, value in expected.items()):
        return False
    minimum = _finite_number(
        event.get("activeMinFrameDurationSeconds"), label="active minimum duration"
    )
    maximum = _finite_number(
        event.get("activeMaxFrameDurationSeconds"), label="active maximum duration"
    )
    target = candidate["frame_duration_seconds"]
    return (
        abs(minimum - target) < 1e-12
        and abs(maximum - target) < 1e-12
        and isinstance(event.get("sessionPresetRawValue"), str)
        and bool(event["sessionPresetRawValue"])
    )


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
        raise CallbackDeliveryV2Error(
            "Callback v2 evaluation output exists; replay forbidden."
        )
    attempt_path = observation_root / "attempt.json"
    prelaunch_path = observation_root / "attempt-prelaunch.json"
    attempt = _load_json(attempt_path, label="callback v2 attempt")
    prelaunch = _load_json(prelaunch_path, label="callback v2 prelaunch")
    contract_sha = _sha256_file(contract_path)
    if attempt.get("schema_version") != ATTEMPT_SCHEMA:
        raise CallbackDeliveryV2Error("Callback v2 attempt schema changed.")
    if prelaunch.get("schema_version") != PRELAUNCH_SCHEMA:
        raise CallbackDeliveryV2Error("Callback v2 prelaunch schema changed.")
    if (
        attempt.get("contract_sha256") != contract_sha
        or prelaunch.get("contract_sha256") != contract_sha
    ):
        raise CallbackDeliveryV2Error("Callback v2 contract identity changed.")
    if (
        attempt.get("authority") != contract["authority"]
        or prelaunch.get("authority") != contract["authority"]
    ):
        raise CallbackDeliveryV2Error("Callback v2 authority changed.")
    if attempt.get("budget") != _budget() or prelaunch.get("budget") != _budget():
        raise CallbackDeliveryV2Error("Callback v2 budget changed.")
    if attempt.get("prelaunch_manifest_sha256") != _sha256_file(prelaunch_path):
        raise CallbackDeliveryV2Error("Callback v2 prelaunch identity changed.")
    runtime = attempt.get("runtime_identity")
    if runtime != prelaunch.get("runtime_identity"):
        raise CallbackDeliveryV2Error("Callback v2 runtime substitution detected.")
    binary_path = observation_root / BINARY_RELATIVE_PATH
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
        "binary_sha256": _sha256_file(binary_path),
    }
    if runtime != expected_runtime:
        raise CallbackDeliveryV2Error("Callback v2 runtime identity drifted.")
    raw_path = observation_root / "raw/observation.json"
    raw_available = raw_path.is_file()
    raw_sha = _sha256_file(raw_path) if raw_available else None
    if attempt.get("raw_observation_sha256") != raw_sha:
        raise CallbackDeliveryV2Error("Callback v2 raw identity changed.")

    verdict = "prerequisite_abstention"
    failed_gates: list[str] = []
    stage_identity: dict[str, Any] = {
        "after_input_association": None,
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
        observation = _load_json(raw_path, label="callback v2 observation")
        if observation.get("schemaVersion") != OBSERVATION_SCHEMA:
            raise CallbackDeliveryV2Error("Callback v2 observation schema changed.")
        if (
            observation.get("contractSHA256") != contract_sha
            or observation.get("proofClass") != "camera_source_callback_delivery"
            or observation.get("observerRole") != "source_callback_observer_only"
        ):
            raise CallbackDeliveryV2Error("Callback v2 proof identity changed.")
        expected_request = {
            "cameraNameRequested": contract["device"]["exact_localized_name"],
            "cameraUniqueIDRequested": contract["device"]["exact_unique_id"],
            "cameraModelIDRequested": contract["device"]["exact_model_id"],
            "formatIndexRequested": contract["candidate"]["format_index"],
            "frameRateRangeIndexRequested": contract["candidate"][
                "frame_rate_range_index"
            ],
            "durationSecondsRequested": 10.0,
            "maximumCallbacks": 600,
            "captureSessionsUsed": 1,
            "d405LifecycleOperationsUsed": 0,
            "robotMotionTrialsUsed": 0,
            "simulatorReplaysUsed": 0,
            "providerCallsUsed": 0,
        }
        if any(
            observation.get(key) != value for key, value in expected_request.items()
        ):
            raise CallbackDeliveryV2Error(
                "Callback v2 observation request or authority changed."
            )
        parsed = _validate_events(observation, contract=contract)
        events = parsed["events"]
        types = parsed["types"]
        outputs = parsed["outputs"]
        drops = parsed["drops"]
        if (
            observation.get("sampleOutputCount") != len(outputs)
            or observation.get("sampleDroppedCount") != len(drops)
        ):
            raise CallbackDeliveryV2Error("Callback v2 event counts changed.")
        authorization = [
            event for event in events if event.get("eventType") == "authorization_observed"
        ]
        discovery = [
            event
            for event in events
            if event.get("eventType") == "device_discovery_observed"
        ]
        if (
            len(authorization) != 1
            or authorization[0].get("authorizationStatusRawValue") != 3
            or len(discovery) != 1
            or discovery[0].get("exactMatchCount") != 1
        ):
            raise CallbackDeliveryV2Error("Callback v2 precondition identity changed.")
        associated_event = next(
            event
            for event in events
            if event.get("eventType") == "format_after_input_association"
        )
        committed_event = next(
            event for event in events if event.get("eventType") == "format_after_commit"
        )
        associated_exact = _format_stage_exact(associated_event, contract=contract)
        committed_exact = _format_stage_exact(committed_event, contract=contract)
        stage_identity["after_input_association"] = {
            "exact": associated_exact,
            "width": associated_event.get("formatWidth"),
            "height": associated_event.get("formatHeight"),
            "subtype": associated_event.get("formatMediaSubtype"),
            "session_preset_raw_value": associated_event.get("sessionPresetRawValue"),
        }
        stage_identity["after_commit"] = {
            "exact": committed_exact,
            "width": committed_event.get("formatWidth"),
            "height": committed_event.get("formatHeight"),
            "subtype": committed_event.get("formatMediaSubtype"),
            "session_preset_raw_value": committed_event.get("sessionPresetRawValue"),
        }
        if not associated_exact or not committed_exact:
            if "session_start_returned" in types or "format_after_start" in types:
                raise CallbackDeliveryV2Error(
                    "Callback v2 started despite post-commit format mismatch."
                )
            failed_gates = [
                name
                for name, passed in (
                    ("exact_format_after_input_association", associated_exact),
                    ("exact_format_after_commit", committed_exact),
                )
                if not passed
            ]
        else:
            if (
                types.count("session_start_returned") != 1
                or types.count("format_after_start") != 1
                or types.count("session_stop_returned") != 1
            ):
                raise CallbackDeliveryV2Error(
                    "Callback v2 session lifecycle event count changed."
                )
            start = next(
                event
                for event in events
                if event.get("eventType") == "session_start_returned"
            )
            stop = next(
                event
                for event in events
                if event.get("eventType") == "session_stop_returned"
            )
            started_event = next(
                event
                for event in events
                if event.get("eventType") == "format_after_start"
            )
            started_exact = _format_stage_exact(started_event, contract=contract)
            stage_identity["after_start"] = {
                "exact": started_exact,
                "width": started_event.get("formatWidth"),
                "height": started_event.get("formatHeight"),
                "subtype": started_event.get("formatMediaSubtype"),
                "session_preset_raw_value": started_event.get(
                    "sessionPresetRawValue"
                ),
            }
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
                    raise CallbackDeliveryV2Error(
                        "Callback v2 sample timing is malformed."
                    )
                if not pts_value.get("valid") or not pts_value.get("numeric"):
                    duration_numeric = False
                    continue
                pts.append(
                    _finite_number(pts_value.get("seconds"), label="sample PTS")
                )
                if not duration_value.get("valid") or not duration_value.get(
                    "numeric"
                ):
                    duration_numeric = False
                else:
                    _finite_number(
                        duration_value.get("seconds"), label="sample duration"
                    )
            intervals = [
                right - left for left, right in zip(pts, pts[1:], strict=False)
            ]
            strictly_increasing = all(interval > 0 for interval in intervals)
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
                "exact_format_after_start": started_exact,
                "session_started": start.get("sessionRunning") is True,
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
                "strictly_increasing_pts": strictly_increasing and bool(intervals),
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
    evaluation_digest = _canonical_digest(evaluation)
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": contract_sha,
        "proof_class": "camera_source_callback_delivery",
        "verdict": verdict,
        "evaluation_digest": evaluation_digest,
        "attempt_sha256": _sha256_file(attempt_path),
        "prelaunch_sha256": _sha256_file(prelaunch_path),
        "raw_observation_sha256": raw_sha,
        "runtime_identity": runtime,
        "sealed_inventory_receipt_sha256": contract["sealed_inventory"][
            "receipt_sha256"
        ],
        "v1_terminal_receipt_sha256": contract["v1_terminal_evidence"][
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
    subparsers = parser.add_subparsers(dest="command", required=True)
    observe = subparsers.add_parser("observe")
    observe.add_argument("--output-root", type=Path, required=True)
    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("--observation-root", type=Path, required=True)
    evaluate.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    root = _repo_root()
    contract = (
        root / "configs/evaluations/avfoundation_c922_callback_delivery_v2.json"
    )
    source = root / "tools/macos/AVFoundationCallbackDeliveryV2.swift"
    evaluator = root / "src/sim2claw/avfoundation_callback_delivery_v2.py"
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

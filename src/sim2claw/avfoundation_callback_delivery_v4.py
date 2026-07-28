"""Evaluator-owned warm-up-bounded C922 callback measurement."""

from __future__ import annotations

import argparse
import math
import subprocess
from pathlib import Path
from typing import Any

from sim2claw.avfoundation_callback_delivery_v3 import (
    EVENT_SCHEMA,
    OBSERVATION_SCHEMA,
    _stage_exact,
    _stage_summary,
    _validate_events,
)
from sim2claw.avfoundation_format_inventory import (
    AVFoundationFormatInventoryError,
    _canonical_digest,
    _load_json,
    _sha256_file,
    _write_json,
)


CONTRACT_SCHEMA = "sim2claw.avfoundation_c922_callback_delivery_contract.v4"
PRELAUNCH_SCHEMA = "sim2claw.avfoundation_c922_callback_prelaunch.v4"
ATTEMPT_SCHEMA = "sim2claw.avfoundation_c922_callback_attempt.v4"
EVALUATION_SCHEMA = "sim2claw.avfoundation_c922_callback_evaluation.v4"
RECEIPT_SCHEMA = "sim2claw.avfoundation_c922_callback_receipt.v4"
BINARY_RELATIVE_PATH = "runtime/avfoundation-c922-callback-delivery-v4"


class CallbackDeliveryV4Error(AVFoundationFormatInventoryError):
    """Raised when v4 callback evidence fails closed."""


def _finite(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CallbackDeliveryV4Error(f"{label} is not numeric.")
    result = float(value)
    if not math.isfinite(result):
        raise CallbackDeliveryV4Error(f"{label} is not finite.")
    return result


def load_callback_contract(path: Path) -> dict[str, Any]:
    contract = _load_json(path, label="callback-delivery v4 contract")
    if contract.get("schema_version") != CONTRACT_SCHEMA:
        raise CallbackDeliveryV4Error("Callback v4 contract schema changed.")
    if contract.get("status") != "preregistered_before_observation":
        raise CallbackDeliveryV4Error("Callback v4 status changed.")
    if contract.get("baseline_commit") != "1ff887e":
        raise CallbackDeliveryV4Error("Callback v4 baseline changed.")
    if contract.get("observer_reuse") != {
        "source_path": "tools/macos/AVFoundationCallbackDeliveryV3.swift",
        "source_sha256": "79da2c743ac5e16ef90fb56dfd77802e015e8e4fd7d9763ac23e5410ea29bb53",
        "raw_observation_schema": OBSERVATION_SCHEMA,
        "raw_event_schema": EVENT_SCHEMA,
        "lock_through_start_mechanism_unchanged": True,
        "source_code_changes_authorized": False,
    }:
        raise CallbackDeliveryV4Error("Callback v4 observer reuse changed.")
    if contract.get("device") != {
        "media_type": "video",
        "exact_localized_name": "C922 Pro Stream Webcam",
        "exact_unique_id": "0x8310000046d085c",
        "exact_model_id": "UVC Camera VendorID_1133 ProductID_2140",
        "exact_match_count_required": 1,
    }:
        raise CallbackDeliveryV4Error("Callback v4 device changed.")
    if contract.get("candidate") != {
        "format_index": 16,
        "frame_rate_range_index": 0,
        "width": 640,
        "height": 480,
        "media_subtype_fourcc": "420v",
        "supported_fps": 30.00003000003,
        "frame_duration_seconds": 0.03333330000003333,
    }:
        raise CallbackDeliveryV4Error("Callback v4 candidate changed.")
    if contract.get("windowing") != {
        "session_duration_seconds": 11.0,
        "warmup_duration_source_pts_seconds": 1.0,
        "measurement_window_target_seconds": 10.0,
        "warmup_definition": (
            "callbacks_and_intervals_with_right_pts_less_than_first_pts_plus_1.0"
        ),
        "measurement_definition": (
            "callbacks_at_or_after_first_pts_plus_1.0_and_intervals_between_them"
        ),
        "warmup_cadence_scored": False,
        "warmup_format_and_drop_gates_scored": True,
        "all_warmup_metrics_reported": True,
        "post_observation_boundary_change": False,
    }:
        raise CallbackDeliveryV4Error("Callback v4 window changed.")
    if contract.get("evaluator") != {
        "minimum_measurement_output_callback_count": 240,
        "minimum_measurement_pts_span_seconds": 8.0,
        "maximum_dropped_callback_count_entire_session": 0,
        "maximum_measurement_pts_interval_multiplier": 1.5,
        "require_exact_lifecycle_format": True,
        "require_all_session_output_dimensions_exact": True,
        "require_all_session_output_subtypes_exact": True,
        "require_strictly_increasing_pts_entire_session": True,
        "require_numeric_pts_and_duration_entire_session": True,
        "verdicts": [
            "steady_callback_delivery_verified",
            "steady_callback_delivery_degraded",
            "prerequisite_abstention",
        ],
        "observer_self_scoring": False,
    }:
        raise CallbackDeliveryV4Error("Callback v4 evaluator changed.")
    if contract.get("operation_budget") != {
        "observation_attempts_maximum": 1,
        "capture_sessions_maximum": 1,
        "capture_duration_seconds_maximum": 11.0,
        "source_callbacks_maximum": 660,
        "d405_lifecycle_operations_maximum": 0,
        "robot_motion_trials_maximum": 0,
        "simulator_replays_maximum": 0,
        "provider_calls_maximum": 0,
    }:
        raise CallbackDeliveryV4Error("Callback v4 budget changed.")
    authority = contract.get("authority")
    allowed_true = {"c922_capture_session", "camera_frame_callback_observation"}
    if not isinstance(authority, dict) or any(
        value is not (key in allowed_true) for key, value in authority.items()
    ):
        raise CallbackDeliveryV4Error("Callback v4 authority changed.")
    return contract


def _verify_inputs(contract: dict[str, Any], *, repo_root: Path) -> None:
    source = repo_root / contract["observer_reuse"]["source_path"]
    if (
        not source.is_file()
        or _sha256_file(source) != contract["observer_reuse"]["source_sha256"]
    ):
        raise CallbackDeliveryV4Error("Callback v3 observer bytes changed.")
    v3 = contract.get("v3_terminal_evidence")
    expected_v3 = {
        "implementation_commit": "a779dc5ff351b61334ddcaf3e5462a624b949708",
        "raw_observation_sha256": "df6aac8d735dc1f157bbd5c76b5a333eb4abd9bca64f7997a253e06db16f3ae9",
        "evaluation_sha256": "b4cc00376001cdfc531bdc22d6adc6bf9846fd7e2171d0d8ead222e2a6445fa2",
        "receipt_sha256": "276611fd190c31ec9c7d76fa1b9c1154982974d1055b152f35d3d9ed0ff1eabe",
        "receipt_digest": "7c5965661c987807c899c7b1a4ca019bb8f1fed1b47cb9b3898d17abf81000c6",
        "verdict": "callback_delivery_degraded",
        "failed_gates": ["bounded_pts_interval"],
        "sample_output_count": 305,
        "sample_dropped_count": 0,
        "pts_interval_count": 304,
        "pts_intervals_within_gate": 303,
        "pts_intervals_above_gate": 1,
        "above_gate_interval_index": 0,
        "maximum_pts_interval_seconds": 0.0659999999916181,
        "retry_authorized": False,
    }
    if v3 != expected_v3:
        raise CallbackDeliveryV4Error("Callback v3 terminal binding changed.")
    v3_paths = {
        "raw_observation": repo_root
        / "outputs/avfoundation-c922-callback-delivery-v3/observed/raw/observation.json",
        "evaluation": repo_root
        / "outputs/avfoundation-c922-callback-delivery-v3/evaluated/evaluation.json",
        "receipt": repo_root
        / "outputs/avfoundation-c922-callback-delivery-v3/evaluated/receipt.json",
    }
    for key, path in v3_paths.items():
        if not path.is_file() or _sha256_file(path) != v3[f"{key}_sha256"]:
            raise CallbackDeliveryV4Error(f"Callback v3 {key} changed.")
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
    }
    if sealed != expected_sealed:
        raise CallbackDeliveryV4Error("Callback v4 inventory binding changed.")
    for key in ("contract", "raw_inventory", "evaluation", "receipt"):
        path = repo_root / sealed[f"{key}_path"]
        if not path.is_file() or _sha256_file(path) != sealed[f"{key}_sha256"]:
            raise CallbackDeliveryV4Error(f"Callback inventory {key} changed.")


def _budget() -> dict[str, Any]:
    return {
        "observation_attempts_used": 1,
        "capture_sessions_used": 1,
        "capture_duration_seconds_requested": 11.0,
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
        raise CallbackDeliveryV4Error("Callback v4 source path changed.")
    if (repo_root / runtime["evaluator_path"]).resolve() != evaluator_path.resolve():
        raise CallbackDeliveryV4Error("Callback v4 evaluator path changed.")
    if runtime["binary_relative_path"] != BINARY_RELATIVE_PATH:
        raise CallbackDeliveryV4Error("Callback v4 binary path changed.")
    compiler = Path(runtime["compiler_path"])
    version = subprocess.run(
        [str(compiler), "--version"], check=False, capture_output=True, text=True
    )
    if version.returncode != 0 or not version.stdout.startswith(
        runtime["swift_version_prefix"]
    ):
        raise CallbackDeliveryV4Error("Callback v4 compiler changed.")
    binary_path.parent.mkdir(parents=True, exist_ok=True)
    compiled = subprocess.run(
        [str(compiler), str(source_path), "-o", str(binary_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if compiled.returncode != 0:
        raise CallbackDeliveryV4Error(
            f"Callback v4 compilation failed: {compiled.stderr.strip()}"
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
        raise CallbackDeliveryV4Error("Callback v4 output exists; retry forbidden.")
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
        str(contract["windowing"]["session_duration_seconds"]),
        "--maximum-callbacks",
        str(contract["operation_budget"]["source_callbacks_maximum"]),
        "--contract-sha256",
        runtime["contract_sha256"],
        "--output",
        str(raw_path),
    ]
    try:
        completed = subprocess.run(
            command, check=False, capture_output=True, text=True, timeout=27.0
        )
        return_code = completed.returncode
        stderr_text = completed.stderr
        status = (
            "observer_completed_with_raw"
            if raw_path.is_file()
            else "observer_failed_without_raw"
        )
    except subprocess.TimeoutExpired as error:
        return_code = 124
        stderr_text = (
            (error.stderr.decode() if isinstance(error.stderr, bytes) else error.stderr)
            or ""
        ) + "observer_timeout_after_27_seconds\n"
        status = "observer_timed_out_without_retry"
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.write_text(stderr_text, encoding="utf-8")
    attempt = {
        "schema_version": ATTEMPT_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": runtime["contract_sha256"],
        "proof_class": "camera_source_callback_delivery",
        "status": status,
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


def _interval_stats(intervals: list[float]) -> dict[str, Any]:
    ordered = sorted(intervals)
    if not ordered:
        return {
            "count": 0,
            "minimum_seconds": None,
            "median_seconds": None,
            "mean_seconds": None,
            "maximum_seconds": None,
        }
    middle = len(ordered) // 2
    median = (
        ordered[middle]
        if len(ordered) % 2
        else (ordered[middle - 1] + ordered[middle]) / 2.0
    )
    return {
        "count": len(intervals),
        "minimum_seconds": min(intervals),
        "median_seconds": median,
        "mean_seconds": sum(intervals) / len(intervals),
        "maximum_seconds": max(intervals),
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
        raise CallbackDeliveryV4Error("Callback v4 evaluation replay forbidden.")
    attempt_path = observation_root / "attempt.json"
    prelaunch_path = observation_root / "attempt-prelaunch.json"
    attempt = _load_json(attempt_path, label="callback v4 attempt")
    prelaunch = _load_json(prelaunch_path, label="callback v4 prelaunch")
    contract_sha = _sha256_file(contract_path)
    if (
        attempt.get("schema_version") != ATTEMPT_SCHEMA
        or prelaunch.get("schema_version") != PRELAUNCH_SCHEMA
        or attempt.get("contract_sha256") != contract_sha
        or prelaunch.get("contract_sha256") != contract_sha
    ):
        raise CallbackDeliveryV4Error("Callback v4 attempt identity changed.")
    if (
        attempt.get("authority") != contract["authority"]
        or prelaunch.get("authority") != contract["authority"]
        or attempt.get("budget") != _budget()
        or prelaunch.get("budget") != _budget()
    ):
        raise CallbackDeliveryV4Error("Callback v4 authority or budget changed.")
    if attempt.get("prelaunch_manifest_sha256") != _sha256_file(prelaunch_path):
        raise CallbackDeliveryV4Error("Callback v4 prelaunch changed.")
    runtime = attempt.get("runtime_identity")
    if runtime != prelaunch.get("runtime_identity"):
        raise CallbackDeliveryV4Error("Callback v4 runtime substitution detected.")
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
        raise CallbackDeliveryV4Error("Callback v4 runtime identity changed.")
    raw_path = observation_root / "raw/observation.json"
    raw_available = raw_path.is_file()
    raw_sha = _sha256_file(raw_path) if raw_available else None
    if attempt.get("raw_observation_sha256") != raw_sha:
        raise CallbackDeliveryV4Error("Callback v4 raw identity changed.")

    verdict = "prerequisite_abstention"
    failed_gates: list[str] = []
    statistics: dict[str, Any] = {
        "format_stage_identity": {
            "before_commit": None,
            "after_commit": None,
            "after_start": None,
        },
        "full_session_output_count": 0,
        "full_session_dropped_count": 0,
        "warmup_output_count": 0,
        "measurement_output_count": 0,
        "warmup_interval_statistics": _interval_stats([]),
        "transition_interval_seconds": None,
        "measurement_interval_statistics": _interval_stats([]),
        "measurement_pts_span_seconds": None,
        "measurement_boundary_pts_seconds": None,
        "delivered_dimensions": [],
        "delivered_media_subtypes": [],
        "delivered_pixel_formats": [],
    }
    if attempt.get("return_code") == 0 and raw_available:
        observation = _load_json(raw_path, label="callback v4 raw observation")
        if (
            observation.get("schemaVersion") != OBSERVATION_SCHEMA
            or observation.get("contractSHA256") != contract_sha
            or observation.get("proofClass") != "camera_source_callback_delivery"
            or observation.get("observerRole") != "source_callback_observer_only"
        ):
            raise CallbackDeliveryV4Error("Callback v4 raw proof identity changed.")
        expected = {
            "cameraNameRequested": contract["device"]["exact_localized_name"],
            "cameraUniqueIDRequested": contract["device"]["exact_unique_id"],
            "cameraModelIDRequested": contract["device"]["exact_model_id"],
            "formatIndexRequested": 16,
            "frameRateRangeIndexRequested": 0,
            "durationSecondsRequested": 11.0,
            "maximumCallbacks": 660,
            "captureSessionsUsed": 1,
            "d405LifecycleOperationsUsed": 0,
            "robotMotionTrialsUsed": 0,
            "simulatorReplaysUsed": 0,
            "providerCallsUsed": 0,
        }
        if any(observation.get(key) != value for key, value in expected.items()):
            raise CallbackDeliveryV4Error("Callback v4 request or authority changed.")
        parsed = _validate_events(observation, contract=contract)
        events = parsed["events"]
        outputs = parsed["outputs"]
        drops = parsed["drops"]
        types = parsed["types"]
        if (
            observation.get("sampleOutputCount") != len(outputs)
            or observation.get("sampleDroppedCount") != len(drops)
        ):
            raise CallbackDeliveryV4Error("Callback v4 event counts changed.")
        required = (
            "session_start_returned",
            "format_while_locked_after_start",
            "device_unlock_returned",
            "session_stop_returned",
        )
        if any(types.count(event_type) != 1 for event_type in required):
            raise CallbackDeliveryV4Error("Callback v4 lifecycle changed.")
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
            raise CallbackDeliveryV4Error("Callback v4 preconditions changed.")
        stage_events = {
            "before_commit": next(
                event
                for event in events
                if event.get("eventType") == "format_while_locked_before_commit"
            ),
            "after_commit": next(
                event
                for event in events
                if event.get("eventType") == "format_while_locked_after_commit"
            ),
            "after_start": next(
                event
                for event in events
                if event.get("eventType") == "format_while_locked_after_start"
            ),
        }
        stage_exact = {
            key: _stage_exact(event, contract=contract)
            for key, event in stage_events.items()
        }
        statistics["format_stage_identity"] = {
            key: _stage_summary(stage_events[key], exact=stage_exact[key])
            for key in stage_events
        }
        unlock = next(
            event
            for event in events
            if event.get("eventType") == "device_unlock_returned"
        )
        if any(
            event.get("eventIndex", -1) <= unlock.get("eventIndex", -1)
            for event in outputs + drops
        ):
            raise CallbackDeliveryV4Error("Callback v4 callback preceded unlock.")
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
        durations_numeric = True
        for event in outputs:
            pts_value = event.get("samplePTS")
            duration_value = event.get("sampleDuration")
            if not isinstance(pts_value, dict) or not isinstance(duration_value, dict):
                raise CallbackDeliveryV4Error("Callback v4 timing malformed.")
            if not pts_value.get("valid") or not pts_value.get("numeric"):
                durations_numeric = False
            else:
                pts.append(_finite(pts_value.get("seconds"), label="PTS"))
            if not duration_value.get("valid") or not duration_value.get("numeric"):
                durations_numeric = False
            else:
                _finite(duration_value.get("seconds"), label="sample duration")
        full_intervals = [
            right - left for left, right in zip(pts, pts[1:], strict=False)
        ]
        strictly_increasing = bool(full_intervals) and all(
            interval > 0 for interval in full_intervals
        )
        boundary = (
            pts[0] + contract["windowing"]["warmup_duration_source_pts_seconds"]
            if pts
            else None
        )
        measurement_start_index = (
            next(
                (index for index, value in enumerate(pts) if value >= boundary),
                len(pts),
            )
            if boundary is not None
            else len(pts)
        )
        warmup_pts = pts[:measurement_start_index]
        measurement_pts = pts[measurement_start_index:]
        warmup_intervals = [
            right - left
            for left, right in zip(warmup_pts, warmup_pts[1:], strict=False)
        ]
        measurement_intervals = [
            right - left
            for left, right in zip(
                measurement_pts, measurement_pts[1:], strict=False
            )
        ]
        transition_interval = (
            measurement_pts[0] - warmup_pts[-1]
            if warmup_pts and measurement_pts
            else None
        )
        measurement_span = (
            measurement_pts[-1] - measurement_pts[0]
            if len(measurement_pts) >= 2
            else None
        )
        maximum_allowed = (
            contract["candidate"]["frame_duration_seconds"]
            * contract["evaluator"]["maximum_measurement_pts_interval_multiplier"]
        )
        statistics.update(
            {
                "full_session_output_count": len(outputs),
                "full_session_dropped_count": len(drops),
                "full_session_interval_statistics": _interval_stats(full_intervals),
                "warmup_output_count": len(warmup_pts),
                "measurement_output_count": len(measurement_pts),
                "warmup_interval_statistics": _interval_stats(warmup_intervals),
                "transition_interval_seconds": transition_interval,
                "measurement_interval_statistics": _interval_stats(
                    measurement_intervals
                ),
                "measurement_pts_span_seconds": measurement_span,
                "measurement_boundary_pts_seconds": boundary,
                "maximum_measurement_pts_interval_allowed_seconds": maximum_allowed,
                "delivered_dimensions": [list(item) for item in dimensions],
                "delivered_media_subtypes": subtypes,
                "delivered_pixel_formats": pixels,
            }
        )
        candidate = contract["candidate"]
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
        gates = {
            "exact_lifecycle_format": all(stage_exact.values()),
            "session_started": start.get("sessionRunning") is True,
            "device_unlocked_before_window": unlock.get("deviceLockHeld") is False,
            "session_stopped": stop.get("sessionRunning") is False,
            "minimum_measurement_output_callbacks": len(measurement_pts)
            >= contract["evaluator"]["minimum_measurement_output_callback_count"],
            "minimum_measurement_pts_span": measurement_span is not None
            and measurement_span
            >= contract["evaluator"]["minimum_measurement_pts_span_seconds"],
            "zero_dropped_callbacks_entire_session": len(drops) == 0,
            "exact_dimensions_entire_session": dimensions
            == [(candidate["width"], candidate["height"])],
            "exact_media_subtype_entire_session": subtypes
            == [candidate["media_subtype_fourcc"]],
            "exact_pixel_format_entire_session": pixels
            == [candidate["media_subtype_fourcc"]],
            "numeric_pts_and_duration_entire_session": len(pts) == len(outputs)
            and durations_numeric,
            "strictly_increasing_pts_entire_session": strictly_increasing,
            "bounded_measurement_pts_interval": bool(measurement_intervals)
            and max(measurement_intervals) <= maximum_allowed,
        }
        failed_gates = [name for name, passed in gates.items() if not passed]
        verdict = (
            "steady_callback_delivery_verified"
            if not failed_gates
            else "steady_callback_delivery_degraded"
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
        "v3_terminal_receipt_sha256": contract["v3_terminal_evidence"][
            "receipt_sha256"
        ],
        "sealed_inventory_receipt_sha256": contract["sealed_inventory"][
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
        root / "configs/evaluations/avfoundation_c922_callback_delivery_v4.json"
    )
    source = root / "tools/macos/AVFoundationCallbackDeliveryV3.swift"
    evaluator = root / "src/sim2claw/avfoundation_callback_delivery_v4.py"
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

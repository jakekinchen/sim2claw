from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

import pytest

from sim2claw.avfoundation_callback_delivery_v3 import EVENT_SCHEMA, OBSERVATION_SCHEMA
from sim2claw.avfoundation_callback_delivery_v4 import (
    ATTEMPT_SCHEMA,
    BINARY_RELATIVE_PATH,
    PRELAUNCH_SCHEMA,
    CallbackDeliveryV4Error,
    evaluate_callback_observation,
    load_callback_contract,
)
from sim2claw.avfoundation_format_inventory import _sha256_file, _write_json


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/evaluations/avfoundation_c922_callback_delivery_v4.json"
SOURCE = ROOT / "tools/macos/AVFoundationCallbackDeliveryV3.swift"
EVALUATOR = ROOT / "src/sim2claw/avfoundation_callback_delivery_v4.py"


def _event(index: int, event_type: str, **values: object) -> dict[str, object]:
    return {
        "schemaVersion": EVENT_SCHEMA,
        "eventIndex": index,
        "eventType": event_type,
        "hostContinuousNS": 4_000_000_000 + index * 1_000_000,
        **values,
    }


def _format_event(index: int, event_type: str):
    return _event(
        index,
        event_type,
        deviceLocalizedName="C922 Pro Stream Webcam",
        deviceUniqueID="0x8310000046d085c",
        deviceModelID="UVC Camera VendorID_1133 ProductID_2140",
        formatIndex=16,
        frameRateRangeIndex=0,
        formatWidth=640,
        formatHeight=480,
        formatMediaSubtype="420v",
        supportedFPS=30.00003000003,
        activeMinFrameDurationSeconds=0.03333330000003333,
        activeMaxFrameDurationSeconds=0.03333330000003333,
        sessionPresetRawValue="AVCaptureSessionPresetHigh",
        deviceLockHeld=True,
    )


def _runtime(observation_root: Path) -> dict[str, object]:
    binary = observation_root / BINARY_RELATIVE_PATH
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(b"synthetic callback observer v4\n")
    version = subprocess.run(
        ["/usr/bin/swiftc", "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return {
        "contract_sha256": _sha256_file(CONTRACT),
        "source_sha256": _sha256_file(SOURCE),
        "evaluator_sha256": _sha256_file(EVALUATOR),
        "compiler_path": "/usr/bin/swiftc",
        "compiler_sha256": _sha256_file(Path("/usr/bin/swiftc")),
        "swift_version": version,
        "binary_path": BINARY_RELATIVE_PATH,
        "binary_sha256": _sha256_file(binary),
    }


def _materialize(
    root: Path,
    *,
    late_gap_index: int | None = None,
    raw_available: bool = True,
) -> Path:
    observation_root = root / "observed"
    runtime = _runtime(observation_root)
    contract = load_callback_contract(CONTRACT)
    budget = {
        "observation_attempts_used": 1,
        "capture_sessions_used": 1,
        "capture_duration_seconds_requested": 11.0,
        "d405_lifecycle_operations_used": 0,
        "robot_motion_trials_used": 0,
        "simulator_replays_used": 0,
        "provider_calls_used": 0,
    }
    prelaunch = {
        "schema_version": PRELAUNCH_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": _sha256_file(CONTRACT),
        "proof_class": "camera_source_callback_delivery",
        "status": "prepared_before_capture_session",
        "runtime_identity": runtime,
        "raw_observation_path": "raw/observation.json",
        "stderr_path": "raw/observer.stderr.log",
        "budget": budget,
        "authority": contract["authority"],
    }
    prelaunch_path = observation_root / "attempt-prelaunch.json"
    _write_json(prelaunch_path, prelaunch)
    raw_path = observation_root / "raw/observation.json"
    output_count = 330 if raw_available else 0
    if raw_available:
        events = [
            _event(0, "observer_started"),
            _event(1, "authorization_observed", authorizationStatusRawValue=3),
            _event(2, "device_discovery_observed", exactMatchCount=1),
            _format_event(3, "format_while_locked_before_commit"),
            _format_event(4, "format_while_locked_after_commit"),
            _event(5, "session_start_returned", sessionRunning=True),
            _format_event(6, "format_while_locked_after_start"),
            _event(7, "device_unlock_returned", deviceLockHeld=False),
        ]
        pts = [0.0]
        for interval_index in range(output_count - 1):
            interval = (
                0.066
                if interval_index == 0 or interval_index == late_gap_index
                else 0.03333330000003333
            )
            pts.append(pts[-1] + interval)
        for sequence, value in enumerate(pts):
            events.append(
                _event(
                    len(events),
                    "sample_output",
                    localSequence=sequence + 1,
                    samplePTS={
                        "valid": True,
                        "numeric": True,
                        "value": sequence,
                        "timescale": 30,
                        "seconds": value,
                    },
                    sampleDuration={
                        "valid": True,
                        "numeric": True,
                        "value": 1,
                        "timescale": 30,
                        "seconds": 0.03333330000003333,
                    },
                    formatWidth=640,
                    formatHeight=480,
                    formatMediaSubtype="420v",
                    pixelFormat="420v",
                    connectionEnabled=True,
                    connectionActive=True,
                )
            )
        events.extend(
            [
                _event(len(events), "session_stop_returned", sessionRunning=False),
                _event(
                    len(events) + 1,
                    "observer_finished",
                    sampleOutputCount=output_count,
                    sampleDroppedCount=0,
                ),
            ]
        )
        observation = {
            "schemaVersion": OBSERVATION_SCHEMA,
            "contractSHA256": _sha256_file(CONTRACT),
            "proofClass": "camera_source_callback_delivery",
            "observerRole": "source_callback_observer_only",
            "cameraNameRequested": "C922 Pro Stream Webcam",
            "cameraUniqueIDRequested": "0x8310000046d085c",
            "cameraModelIDRequested": "UVC Camera VendorID_1133 ProductID_2140",
            "formatIndexRequested": 16,
            "frameRateRangeIndexRequested": 0,
            "durationSecondsRequested": 11.0,
            "maximumCallbacks": 660,
            "sampleOutputCount": output_count,
            "sampleDroppedCount": 0,
            "captureSessionsUsed": 1,
            "d405LifecycleOperationsUsed": 0,
            "robotMotionTrialsUsed": 0,
            "simulatorReplaysUsed": 0,
            "providerCallsUsed": 0,
            "events": events,
        }
        _write_json(raw_path, observation)
    stderr = observation_root / "raw/observer.stderr.log"
    stderr.parent.mkdir(parents=True, exist_ok=True)
    stderr.write_text("" if raw_available else "synthetic timeout\n", encoding="utf-8")
    attempt = {
        "schema_version": ATTEMPT_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": _sha256_file(CONTRACT),
        "proof_class": "camera_source_callback_delivery",
        "status": (
            "observer_completed_with_raw"
            if raw_available
            else "observer_timed_out_without_retry"
        ),
        "prelaunch_manifest_path": "attempt-prelaunch.json",
        "prelaunch_manifest_sha256": _sha256_file(prelaunch_path),
        "runtime_identity": runtime,
        "return_code": 0 if raw_available else 124,
        "raw_observation_path": "raw/observation.json",
        "raw_observation_sha256": (
            _sha256_file(raw_path) if raw_available else None
        ),
        "stderr_path": "raw/observer.stderr.log",
        "stderr_sha256": _sha256_file(stderr),
        "budget": budget,
        "authority": contract["authority"],
    }
    _write_json(observation_root / "attempt.json", attempt)
    return observation_root


def _evaluate(observation_root: Path, output_root: Path):
    return evaluate_callback_observation(
        contract_path=CONTRACT,
        observation_root=observation_root,
        output_root=output_root,
        source_path=SOURCE,
        evaluator_path=EVALUATOR,
        repo_root=ROOT,
    )


def test_contract_reuses_exact_v3_observer_and_typechecks() -> None:
    contract = load_callback_contract(CONTRACT)
    assert contract["observer_reuse"]["source_sha256"] == _sha256_file(SOURCE)
    assert contract["windowing"]["warmup_duration_source_pts_seconds"] == 1.0
    result = subprocess.run(
        ["swiftc", "-typecheck", str(SOURCE)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_startup_gap_is_reported_and_measurement_verifies_byte_identically(
    tmp_path: Path,
) -> None:
    observed = _materialize(tmp_path)
    first, _ = _evaluate(observed, tmp_path / "first")
    second, _ = _evaluate(observed, tmp_path / "second")
    assert first["verdict"] == "steady_callback_delivery_verified"
    assert first["failed_gates"] == []
    stats = first["statistics"]
    assert stats["full_session_interval_statistics"]["maximum_seconds"] == 0.066
    assert stats["warmup_interval_statistics"]["maximum_seconds"] == 0.066
    assert (
        stats["measurement_interval_statistics"]["maximum_seconds"]
        < stats["maximum_measurement_pts_interval_allowed_seconds"]
    )
    assert (tmp_path / "first/evaluation.json").read_bytes() == (
        tmp_path / "second/evaluation.json"
    ).read_bytes()
    assert (tmp_path / "first/receipt.json").read_bytes() == (
        tmp_path / "second/receipt.json"
    ).read_bytes()


def test_measurement_window_gap_remains_degraded(tmp_path: Path) -> None:
    observed = _materialize(tmp_path, late_gap_index=100)
    evaluation, _ = _evaluate(observed, tmp_path / "evaluated")
    assert evaluation["verdict"] == "steady_callback_delivery_degraded"
    assert evaluation["failed_gates"] == ["bounded_measurement_pts_interval"]
    assert evaluation["statistics"]["measurement_interval_statistics"][
        "maximum_seconds"
    ] == pytest.approx(0.066)


def test_timeout_is_prerequisite_abstention(tmp_path: Path) -> None:
    observed = _materialize(tmp_path, raw_available=False)
    evaluation, _ = _evaluate(observed, tmp_path / "evaluated")
    assert evaluation["verdict"] == "prerequisite_abstention"
    assert evaluation["observer_return_code"] == 124


def test_contract_rejects_post_hoc_window_change(tmp_path: Path) -> None:
    contract = copy.deepcopy(json.loads(CONTRACT.read_text(encoding="utf-8")))
    contract["windowing"]["warmup_duration_source_pts_seconds"] = 2.0
    path = tmp_path / "contract.json"
    _write_json(path, contract)
    with pytest.raises(CallbackDeliveryV4Error, match="window changed"):
        load_callback_contract(path)

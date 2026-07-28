from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

import pytest

from sim2claw.avfoundation_callback_delivery_v3 import (
    ATTEMPT_SCHEMA,
    BINARY_RELATIVE_PATH,
    EVENT_SCHEMA,
    OBSERVATION_SCHEMA,
    PRELAUNCH_SCHEMA,
    CallbackDeliveryV3Error,
    evaluate_callback_observation,
    load_callback_contract,
)
from sim2claw.avfoundation_format_inventory import (
    _canonical_bytes,
    _sha256_file,
    _write_json,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/evaluations/avfoundation_c922_callback_delivery_v3.json"
SOURCE = ROOT / "tools/macos/AVFoundationCallbackDeliveryV3.swift"
EVALUATOR = ROOT / "src/sim2claw/avfoundation_callback_delivery_v3.py"


def _event(index: int, event_type: str, **values: object) -> dict[str, object]:
    return {
        "schemaVersion": EVENT_SCHEMA,
        "eventIndex": index,
        "eventType": event_type,
        "hostContinuousNS": 3_000_000_000 + index * 1_000_000,
        **values,
    }


def _format_event(index: int, event_type: str, *, width: int = 640):
    return _event(
        index,
        event_type,
        deviceLocalizedName="C922 Pro Stream Webcam",
        deviceUniqueID="0x8310000046d085c",
        deviceModelID="UVC Camera VendorID_1133 ProductID_2140",
        formatIndex=16,
        frameRateRangeIndex=0,
        formatWidth=width,
        formatHeight=480 if width == 640 else 1080,
        formatMediaSubtype="420v",
        supportedFPS=30.00003000003,
        activeMinFrameDurationSeconds=(
            0.03333330000003333 if width == 640 else 0.0416666006945489
        ),
        activeMaxFrameDurationSeconds=(
            0.03333330000003333 if width == 640 else 0.0416666006945489
        ),
        sessionPresetRawValue="AVCaptureSessionPresetHigh",
        deviceLockHeld=True,
    )


def _runtime(observation_root: Path) -> dict[str, object]:
    binary = observation_root / BINARY_RELATIVE_PATH
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(b"synthetic callback observer v3\n")
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
    output_count: int = 250,
    start_width: int = 640,
    commit_width: int = 640,
    raw_available: bool = True,
) -> Path:
    observation_root = root / "observed"
    runtime = _runtime(observation_root)
    contract = load_callback_contract(CONTRACT)
    budget = {
        "observation_attempts_used": 1,
        "capture_sessions_used": 1,
        "capture_duration_seconds_requested": 10.0,
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
    actual_outputs = 0
    if raw_available:
        events = [
            _event(0, "observer_started"),
            _event(1, "authorization_observed", authorizationStatusRawValue=3),
            _event(2, "device_discovery_observed", exactMatchCount=1),
            _format_event(3, "format_while_locked_before_commit"),
            _format_event(4, "format_while_locked_after_commit", width=commit_width),
        ]
        if commit_width == 640:
            events.extend(
                [
                    _event(5, "session_start_returned", sessionRunning=True),
                    _format_event(
                        6, "format_while_locked_after_start", width=start_width
                    ),
                    _event(7, "device_unlock_returned", deviceLockHeld=False),
                ]
            )
            actual_outputs = output_count if start_width == 640 else min(output_count, 1)
            nominal = 0.03333330000003333
            for sequence in range(actual_outputs):
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
                            "seconds": sequence * nominal,
                        },
                        sampleDuration={
                            "valid": True,
                            "numeric": True,
                            "value": 1,
                            "timescale": 30,
                            "seconds": nominal,
                        },
                        formatWidth=start_width,
                        formatHeight=480 if start_width == 640 else 1080,
                        formatMediaSubtype="420v",
                        pixelFormat="420v",
                        connectionEnabled=True,
                        connectionActive=True,
                    )
                )
            events.append(
                _event(len(events), "session_stop_returned", sessionRunning=False)
            )
        events.append(
            _event(
                len(events),
                "observer_finished",
                sampleOutputCount=actual_outputs,
                sampleDroppedCount=0,
            )
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
            "durationSecondsRequested": 10.0,
            "maximumCallbacks": 600,
            "sampleOutputCount": actual_outputs,
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


def test_contract_and_observer_are_frozen_and_typecheck() -> None:
    contract = load_callback_contract(CONTRACT)
    mechanism = contract["changed_mechanism"]
    assert mechanism["device_lock_held_through_start_return_and_verification"]
    assert mechanism["session_preset_assignment"] is False
    source = SOURCE.read_text(encoding="utf-8")
    assert "session.sessionPreset =" not in source
    assert "kCVPixelBufferWidthKey" not in source
    result = subprocess.run(
        ["swiftc", "-typecheck", str(SOURCE)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_verified_evaluation_is_byte_identical(tmp_path: Path) -> None:
    observed = _materialize(tmp_path)
    first, _ = _evaluate(observed, tmp_path / "first")
    second, _ = _evaluate(observed, tmp_path / "second")
    assert first["verdict"] == "callback_delivery_verified"
    assert first["failed_gates"] == []
    assert (tmp_path / "first/evaluation.json").read_bytes() == (
        tmp_path / "second/evaluation.json"
    ).read_bytes()
    assert (tmp_path / "first/receipt.json").read_bytes() == (
        tmp_path / "second/receipt.json"
    ).read_bytes()


def test_start_time_drift_is_degraded_and_lock_is_recorded(tmp_path: Path) -> None:
    observed = _materialize(tmp_path, output_count=1, start_width=1920)
    evaluation, _ = _evaluate(observed, tmp_path / "evaluated")
    assert evaluation["verdict"] == "callback_delivery_degraded"
    assert "exact_format_after_start" in evaluation["failed_gates"]
    stages = evaluation["statistics"]["format_stage_identity"]
    assert stages["after_commit"]["exact"] is True
    assert stages["after_start"]["lock_held"] is True
    assert stages["after_start"]["width"] == 1920


def test_post_commit_drift_abstains_without_start(tmp_path: Path) -> None:
    observed = _materialize(tmp_path, commit_width=1920)
    evaluation, _ = _evaluate(observed, tmp_path / "evaluated")
    assert evaluation["verdict"] == "prerequisite_abstention"
    assert evaluation["failed_gates"] == ["exact_format_after_commit"]


def test_timeout_and_event_replay_fail_closed(tmp_path: Path) -> None:
    timeout = _materialize(tmp_path / "timeout", raw_available=False)
    evaluation, _ = _evaluate(timeout, tmp_path / "timeout-evaluation")
    assert evaluation["verdict"] == "prerequisite_abstention"
    assert evaluation["observer_return_code"] == 124

    observed = _materialize(tmp_path / "replay")
    raw_path = observed / "raw/observation.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    raw["events"][2]["eventIndex"] = 1
    raw_path.write_bytes(_canonical_bytes(raw))
    attempt_path = observed / "attempt.json"
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    attempt["raw_observation_sha256"] = _sha256_file(raw_path)
    _write_json(attempt_path, attempt)
    with pytest.raises(CallbackDeliveryV3Error, match="duplicated or replayed"):
        _evaluate(observed, tmp_path / "bad-replay")


def test_callback_before_unlock_fails_closed(tmp_path: Path) -> None:
    observed = _materialize(tmp_path)
    raw_path = observed / "raw/observation.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    unlock_index = next(
        index
        for index, event in enumerate(raw["events"])
        if event["eventType"] == "device_unlock_returned"
    )
    sample_index = next(
        index
        for index, event in enumerate(raw["events"])
        if event["eventType"] == "sample_output"
    )
    sample = raw["events"].pop(sample_index)
    raw["events"].insert(unlock_index, sample)
    for index, event in enumerate(raw["events"]):
        event["eventIndex"] = index
        event["hostContinuousNS"] = 3_000_000_000 + index * 1_000_000
    raw_path.write_bytes(_canonical_bytes(raw))
    attempt_path = observed / "attempt.json"
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    attempt["raw_observation_sha256"] = _sha256_file(raw_path)
    _write_json(attempt_path, attempt)
    with pytest.raises(CallbackDeliveryV3Error, match="preceded device unlock"):
        _evaluate(observed, tmp_path / "early-callback")


def test_contract_rejects_post_hoc_threshold_change(tmp_path: Path) -> None:
    contract = copy.deepcopy(json.loads(CONTRACT.read_text(encoding="utf-8")))
    contract["evaluator"]["minimum_output_callback_count"] = 1
    path = tmp_path / "contract.json"
    _write_json(path, contract)
    with pytest.raises(CallbackDeliveryV3Error, match="evaluator changed"):
        load_callback_contract(path)

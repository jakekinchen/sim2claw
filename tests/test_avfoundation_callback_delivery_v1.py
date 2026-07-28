from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

import pytest

from sim2claw.avfoundation_callback_delivery_v1 import (
    ATTEMPT_SCHEMA,
    EVENT_SCHEMA,
    OBSERVATION_SCHEMA,
    PRELAUNCH_SCHEMA,
    CallbackDeliveryError,
    evaluate_callback_observation,
    load_callback_contract,
)
from sim2claw.avfoundation_format_inventory import (
    _canonical_bytes,
    _sha256_file,
    _write_json,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/evaluations/avfoundation_c922_callback_delivery_v1.json"
SOURCE = ROOT / "tools/macos/AVFoundationCallbackDeliveryV1.swift"
EVALUATOR = ROOT / "src/sim2claw/avfoundation_callback_delivery_v1.py"


def _event(index: int, event_type: str, **values: object) -> dict[str, object]:
    return {
        "schemaVersion": EVENT_SCHEMA,
        "eventIndex": index,
        "eventType": event_type,
        "hostContinuousNS": 1_000_000_000 + index * 1_000_000,
        **values,
    }


def _runtime(observation_root: Path) -> dict[str, object]:
    binary = observation_root / "runtime/avfoundation-c922-callback-delivery-v1"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(b"synthetic callback observer\n")
    swift_version = subprocess.run(
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
        "swift_version": swift_version,
        "binary_path": "runtime/avfoundation-c922-callback-delivery-v1",
        "binary_sha256": _sha256_file(binary),
    }


def _materialize(
    root: Path,
    *,
    output_count: int = 250,
    dropped_count: int = 0,
    subtype: str = "420v",
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
    if raw_available:
        events = [
            _event(0, "observer_started"),
            _event(1, "authorization_observed", authorizationStatusRawValue=3),
            _event(2, "device_discovery_observed", exactMatchCount=1),
            _event(
                3,
                "format_applied",
                deviceLocalizedName="C922 Pro Stream Webcam",
                deviceUniqueID="0x8310000046d085c",
                deviceModelID="UVC Camera VendorID_1133 ProductID_2140",
                formatIndex=16,
                frameRateRangeIndex=0,
                formatWidth=640,
                formatHeight=480,
                formatMediaSubtype="420v",
                supportedFPS=30.00003000003,
                frameDurationSeconds=0.03333330000003333,
            ),
            _event(4, "session_start_returned", sessionRunning=True),
        ]
        nominal = 0.03333330000003333
        for sequence in range(output_count):
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
                    formatWidth=640,
                    formatHeight=480,
                    formatMediaSubtype=subtype,
                    pixelFormat=subtype,
                    connectionEnabled=True,
                    connectionActive=True,
                )
            )
        for sequence in range(dropped_count):
            events.append(
                _event(
                    len(events),
                    "sample_dropped",
                    localSequence=sequence + 1,
                    dropReason="DroppedFrameReason_FrameWasLate",
                )
            )
        events.extend(
            [
                _event(len(events), "session_stop_returned", sessionRunning=False),
                _event(
                    len(events) + 1,
                    "observer_finished",
                    sampleOutputCount=output_count,
                    sampleDroppedCount=dropped_count,
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
            "durationSecondsRequested": 10.0,
            "maximumCallbacks": 600,
            "sampleOutputCount": output_count,
            "sampleDroppedCount": dropped_count,
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
    stderr.write_text("" if raw_available else "synthetic failure\n", encoding="utf-8")
    attempt = {
        "schema_version": ATTEMPT_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": _sha256_file(CONTRACT),
        "proof_class": "camera_source_callback_delivery",
        "status": "observer_completed_with_raw" if raw_available else "observer_failed_without_raw",
        "prelaunch_manifest_path": "attempt-prelaunch.json",
        "prelaunch_manifest_sha256": _sha256_file(prelaunch_path),
        "runtime_identity": runtime,
        "return_code": 0 if raw_available else 2,
        "raw_observation_path": "raw/observation.json",
        "raw_observation_sha256": _sha256_file(raw_path) if raw_available else None,
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


def test_contract_and_swift_source_are_frozen_and_typecheck() -> None:
    contract = load_callback_contract(CONTRACT)
    assert contract["candidate"]["format_index"] == 16
    assert contract["operation_budget"]["capture_sessions_maximum"] == 1
    assert contract["authority"]["d405_lifecycle"] is False
    source = SOURCE.read_text(encoding="utf-8")
    assert "JSONSerialization" not in source
    assert "[String: Any]" not in source
    result = subprocess.run(
        ["swiftc", "-typecheck", str(SOURCE)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_verified_evaluation_is_byte_identical(tmp_path: Path) -> None:
    observation_root = _materialize(tmp_path)
    first, _ = _evaluate(observation_root, tmp_path / "first")
    second, _ = _evaluate(observation_root, tmp_path / "second")
    assert first["verdict"] == "callback_delivery_verified"
    assert not first["failed_gates"]
    assert (tmp_path / "first/evaluation.json").read_bytes() == (
        tmp_path / "second/evaluation.json"
    ).read_bytes()
    assert (tmp_path / "first/receipt.json").read_bytes() == (
        tmp_path / "second/receipt.json"
    ).read_bytes()


def test_wrong_delivered_subtype_and_drop_are_degraded(tmp_path: Path) -> None:
    observation_root = _materialize(
        tmp_path, subtype="yuvs", dropped_count=1
    )
    evaluation, _ = _evaluate(observation_root, tmp_path / "evaluated")
    assert evaluation["verdict"] == "callback_delivery_degraded"
    assert "exact_media_subtype" in evaluation["failed_gates"]
    assert "zero_dropped_callbacks" in evaluation["failed_gates"]


def test_missing_raw_is_prerequisite_abstention(tmp_path: Path) -> None:
    observation_root = _materialize(tmp_path, raw_available=False)
    evaluation, _ = _evaluate(observation_root, tmp_path / "evaluated")
    assert evaluation["verdict"] == "prerequisite_abstention"
    assert evaluation["statistics"]["sample_output_count"] == 0


def test_duplicate_event_and_binary_mutation_fail_closed(tmp_path: Path) -> None:
    observation_root = _materialize(tmp_path)
    raw_path = observation_root / "raw/observation.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    raw["events"][2]["eventIndex"] = 1
    raw_path.write_bytes(_canonical_bytes(raw))
    attempt_path = observation_root / "attempt.json"
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    attempt["raw_observation_sha256"] = _sha256_file(raw_path)
    _write_json(attempt_path, attempt)
    with pytest.raises(CallbackDeliveryError, match="duplicated or replayed"):
        _evaluate(observation_root, tmp_path / "bad-events")

    clean_root = _materialize(tmp_path / "binary")
    binary = clean_root / "runtime/avfoundation-c922-callback-delivery-v1"
    binary.write_bytes(b"mutated\n")
    with pytest.raises(CallbackDeliveryError, match="runtime identity drifted"):
        _evaluate(clean_root, tmp_path / "bad-binary")


def test_contract_rejects_post_hoc_threshold_change(tmp_path: Path) -> None:
    contract = copy.deepcopy(json.loads(CONTRACT.read_text(encoding="utf-8")))
    contract["evaluator"]["minimum_output_callback_count"] = 1
    path = tmp_path / "contract.json"
    _write_json(path, contract)
    with pytest.raises(CallbackDeliveryError, match="evaluator rule changed"):
        load_callback_contract(path)

from __future__ import annotations

import json
import hashlib
import subprocess
from pathlib import Path

import pytest

from sim2claw.avfoundation_dual_camera_common_session_v1 import (
    ATTEMPT_SCHEMA,
    BINARY_RELATIVE,
    PRELAUNCH_SCHEMA,
    PROOF_CLASS,
    USED_BUDGET,
    evaluate,
    load_contract,
    run_observation,
)
from sim2claw.avfoundation_format_inventory import (
    AVFoundationFormatInventoryError,
    _canonical_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "configs/evaluations/avfoundation_dual_camera_common_session_v1.json"
)
SOURCE = (
    ROOT / "tools/macos/AVFoundationDualCameraCommonSessionV1.swift"
)
EVALUATOR = (
    ROOT / "src/sim2claw/avfoundation_dual_camera_common_session_v1.py"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(payload))


def _format_state(role: str) -> dict[str, object]:
    device = load_contract(CONTRACT)["devices"][role]
    return {
        "role": role,
        "localized_name": device["exact_localized_name"],
        "unique_id": device["exact_unique_id"],
        "model_id": device["exact_model_id"],
        "format_index": device["format_index"],
        "range_index": device["frame_rate_range_index"],
        "width": device["width"],
        "height": device["height"],
        "subtype": device["media_subtype_fourcc"],
        "minimum_duration_seconds": device["frame_duration_seconds"],
        "maximum_duration_seconds": device["frame_duration_seconds"],
    }


def _events() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    specs = {"d405": (55, 0.2), "c922": (330, 1 / 30.00003000003)}
    pending: list[tuple[int, str, int, float]] = []
    for role, (count, period) in specs.items():
        for sequence in range(1, count + 1):
            pts = (sequence - 1) * period
            pending.append((int(pts * 1e9), role, sequence, pts))
    pending.sort()
    contract = load_contract(CONTRACT)
    for index, (host, role, sequence, pts) in enumerate(pending):
        device = contract["devices"][role]
        rows.append(
            {
                "event_index": index,
                "role": role,
                "kind": "output",
                "sequence": sequence,
                "host_continuous_ns": host,
                "pts_seconds": pts,
                "duration_seconds": device["frame_duration_seconds"],
                "width": device["width"],
                "height": device["height"],
                "subtype": device["media_subtype_fourcc"],
                "connection_enabled": True,
                "connection_active": True,
                "drop_reason": None,
            }
        )
    return rows


def _runtime(observed: Path) -> dict[str, object]:
    binary = observed / BINARY_RELATIVE
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(b"synthetic common-session binary\n")
    compiler = Path("/usr/bin/swiftc")
    return {
        "contract_sha256": _sha(CONTRACT),
        "source_sha256": _sha(SOURCE),
        "evaluator_sha256": _sha(EVALUATOR),
        "compiler_path": str(compiler),
        "compiler_sha256": _sha(compiler),
        "swift_version": "Apple Swift version 6.3 synthetic",
        "binary_path": BINARY_RELATIVE,
        "binary_sha256": _sha(binary),
    }


def _materialize(root: Path, *, raw: dict[str, object] | None = None) -> Path:
    observed = root / "observed"
    contract = load_contract(CONTRACT)
    runtime = _runtime(observed)
    prelaunch = {
        "schema_version": PRELAUNCH_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": _sha(CONTRACT),
        "proof_class": PROOF_CLASS,
        "status": "prepared_before_observer_launch",
        "runtime_identity": runtime,
        "raw_observation_path": "raw/observation.json",
        "stderr_path": "raw/observer.stderr.log",
        "budget": USED_BUDGET,
        "authority": contract["authority"],
    }
    prelaunch_path = observed / "attempt-prelaunch.json"
    _write(prelaunch_path, prelaunch)
    events = _events()
    payload = raw or {
        "schema_version": (
            "sim2claw.avfoundation_dual_camera_common_session_observation.v1"
        ),
        "contract_sha256": _sha(CONTRACT),
        "observer_role": "dual_camera_common_session_callback_observer_only",
        "status": "completed",
        "failure_reason": None,
        "detected_device_names": sorted(
            [
                contract["devices"]["d405"]["exact_localized_name"],
                contract["devices"]["c922"]["exact_localized_name"],
            ]
        ),
        "d405_match_count": 1,
        "c922_match_count": 1,
        "common_capture_sessions_used": 1,
        "independent_camera_sessions_used": 0,
        "robot_motion_trials_used": 0,
        "simulator_replays_used": 0,
        "provider_calls_used": 0,
        "duration_seconds_requested": 11.0,
        "maximum_callbacks": 760,
        "d405_output_count": 55,
        "d405_drop_count": 0,
        "c922_output_count": 330,
        "c922_drop_count": 0,
        "stages": [
            {
                "name": name,
                "session_running": name == "after_start",
                "d405_input_admitted": True,
                "c922_input_admitted": True,
                "d405_output_admitted": True,
                "c922_output_admitted": True,
                "d405": _format_state("d405"),
                "c922": _format_state("c922"),
            }
            for name in (
                "before_commit",
                "after_commit",
                "after_start",
                "after_stop",
            )
        ],
        "events": events,
    }
    raw_path = observed / "raw/observation.json"
    _write(raw_path, payload)
    stderr = observed / "raw/observer.stderr.log"
    stderr.write_text("", encoding="utf-8")
    attempt = {
        "schema_version": ATTEMPT_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": _sha(CONTRACT),
        "proof_class": PROOF_CLASS,
        "status": "observer_completed_with_raw",
        "prelaunch_manifest_path": "attempt-prelaunch.json",
        "prelaunch_manifest_sha256": _sha(prelaunch_path),
        "runtime_identity": runtime,
        "return_code": 0,
        "raw_observation_path": "raw/observation.json",
        "raw_observation_sha256": _sha(raw_path),
        "stderr_path": "raw/observer.stderr.log",
        "stderr_sha256": _sha(stderr),
        "budget": USED_BUDGET,
        "authority": contract["authority"],
    }
    _write(observed / "attempt.json", attempt)
    return observed


def test_contract_freezes_one_common_session_and_closed_authority() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["status"] == "preregistered_before_implementation"
    assert contract["mechanism"]["session_count"] == 1
    assert contract["mechanism"]["inputs"] == 2
    assert contract["mechanism"]["video_data_outputs"] == 2
    assert (
        contract["operation_budget"]["common_capture_sessions_maximum"] == 1
    )
    assert (
        contract["operation_budget"]["independent_camera_sessions_maximum"] == 0
    )
    assert contract["operation_budget"]["retries_maximum"] == 0
    assert contract["authority"]["robot_motion"] is False
    assert contract["authority"]["simulator_replay"] is False


def test_contract_binds_exact_evaluator_owned_candidates() -> None:
    devices = json.loads(CONTRACT.read_text(encoding="utf-8"))["devices"]
    assert devices["d405"] == {
        "exact_localized_name": "Intel(R) RealSense(TM) Depth Camera 405  Depth",
        "exact_unique_id": "0x20000080860b5b",
        "exact_model_id": "UVC Camera VendorID_32902 ProductID_2907",
        "format_index": 0,
        "frame_rate_range_index": 4,
        "width": 424,
        "height": 240,
        "media_subtype_fourcc": "2vuy",
        "supported_fps": 5.0,
        "frame_duration_seconds": 0.2,
    }
    assert devices["c922"]["format_index"] == 16
    assert devices["c922"]["media_subtype_fourcc"] == "420v"
    assert devices["c922"]["supported_fps"] == 30.00003000003


def test_observer_typechecks_and_uses_one_native_session() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    assert source.count("let session = AVCaptureSession()") == 1
    assert "AVCaptureMultiCamSession" not in source
    assert source.count("let dOutput = AVCaptureVideoDataOutput()") == 1
    assert source.count("let cOutput = AVCaptureVideoDataOutput()") == 1
    assert "session.canAddInput(dInput)" in source
    assert "session.canAddInput(cInput)" in source
    assert "d405.lockForConfiguration()" in source
    assert "c922.lockForConfiguration()" in source
    assert source.index("session.startRunning()") < source.rindex(
        "d405.unlockForConfiguration()"
    )
    result = subprocess.run(
        ["swiftc", "-typecheck", str(SOURCE)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30.0,
    )
    assert result.returncode == 0, result.stderr


def test_observer_emits_measurements_not_verdict_or_container() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    assert "observer_self_scoring" not in source
    assert '"degraded"' not in source
    assert '"verified"' not in source
    assert "AVAssetWriter" not in source
    assert "AVCaptureMovieFileOutput" not in source
    assert "let stages: [Stage]" in source
    assert "let events: [CallbackEvent]" in source


def test_contract_and_runner_reject_mutation_or_arbitrary_root(
    tmp_path: Path,
) -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    contract["evaluator"]["minimum_common_host_window_seconds"] = 0
    mutated = tmp_path / "contract.json"
    _write(mutated, contract)
    with pytest.raises(AVFoundationFormatInventoryError, match="identity"):
        load_contract(mutated)
    with pytest.raises(AVFoundationFormatInventoryError, match="not authorized"):
        run_observation(
            contract_path=CONTRACT,
            source_path=SOURCE,
            evaluator_path=EVALUATOR,
            output_root=tmp_path / "fresh-arbitrary-root",
        )


def test_runner_seals_timeout_after_prelaunch_without_raw(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(ROOT)
    output = tmp_path / "observed"
    monkeypatch.setattr(
        "sim2claw.avfoundation_dual_camera_common_session_v1."
        "CANONICAL_OBSERVATION_ROOT",
        output,
    )
    monkeypatch.setattr(
        "sim2claw.avfoundation_dual_camera_common_session_v1.compile_observer",
        lambda **_: _runtime(output),
    )

    def timeout(*args: object, **kwargs: object) -> object:
        assert (output / "attempt-prelaunch.json").is_file()
        raise subprocess.TimeoutExpired(
            cmd=args[0] if args else [],
            timeout=kwargs["timeout"],
            stderr="synthetic timeout\n",
        )

    monkeypatch.setattr(
        "sim2claw.avfoundation_dual_camera_common_session_v1.subprocess.run",
        timeout,
    )
    attempt = run_observation(
        contract_path=CONTRACT,
        source_path=SOURCE,
        evaluator_path=EVALUATOR,
        output_root=output,
    )
    assert attempt["return_code"] == -9
    assert attempt["raw_observation_sha256"] is None
    assert (output / "attempt.json").is_file()
    assert "observer_timeout" in (
        output / "raw/observer.stderr.log"
    ).read_text(encoding="utf-8")


def test_evaluator_accepts_only_exact_second_input_abstention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(ROOT)
    contract = load_contract(CONTRACT)
    raw = {
        "schema_version": (
            "sim2claw.avfoundation_dual_camera_common_session_observation.v1"
        ),
        "contract_sha256": _sha(CONTRACT),
        "observer_role": "dual_camera_common_session_callback_observer_only",
        "status": "prerequisite_unavailable",
        "failure_reason": "c922_second_video_input_not_admitted",
        "detected_device_names": sorted(
            [
                contract["devices"]["d405"]["exact_localized_name"],
                contract["devices"]["c922"]["exact_localized_name"],
            ]
        ),
        "d405_match_count": 1,
        "c922_match_count": 1,
        "common_capture_sessions_used": 0,
        "independent_camera_sessions_used": 0,
        "robot_motion_trials_used": 0,
        "simulator_replays_used": 0,
        "provider_calls_used": 0,
        "duration_seconds_requested": 11.0,
        "maximum_callbacks": 760,
        "d405_output_count": 0,
        "d405_drop_count": 0,
        "c922_output_count": 0,
        "c922_drop_count": 0,
        "stages": [],
        "events": [],
    }
    observed = _materialize(tmp_path, raw=raw)
    attempt_path = observed / "attempt.json"
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    attempt["return_code"] = 2
    _write(attempt_path, attempt)
    evaluation, _ = evaluate(
        contract_path=CONTRACT,
        observation_root=observed,
        output_root=tmp_path / "evaluated",
    )
    assert evaluation["verdict"] == "prerequisite_abstention"
    assert evaluation["metrics"] == {}


def test_evaluator_verifies_synthetic_common_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(ROOT)
    observed = _materialize(tmp_path)
    evaluation, receipt = evaluate(
        contract_path=CONTRACT,
        observation_root=observed,
        output_root=tmp_path / "evaluated",
    )
    assert evaluation["verdict"] == "common_session_callback_delivery_verified"
    assert evaluation["failed_gates"] == []
    assert evaluation["metrics"]["d405"]["measurement_output_count"] == 50
    assert evaluation["metrics"]["c922"]["measurement_output_count"] == 299
    assert evaluation["metrics"]["common_host_window_seconds"] >= 9.5
    assert receipt["verdict"] == evaluation["verdict"]


@pytest.mark.parametrize(
    "mutation",
    ["second_input", "drop", "format", "self_score", "independent_session"],
)
def test_evaluator_fails_closed_on_observer_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    monkeypatch.chdir(ROOT)
    observed = _materialize(tmp_path)
    raw_path = observed / "raw/observation.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    if mutation == "second_input":
        raw["stages"][2]["c922_input_admitted"] = False
    elif mutation == "drop":
        device = load_contract(CONTRACT)["devices"]["d405"]
        raw["events"].append(
            {
                "event_index": len(raw["events"]),
                "role": "d405",
                "kind": "drop",
                "sequence": 1,
                "host_continuous_ns": raw["events"][-1]["host_continuous_ns"] + 1,
                "pts_seconds": 11.0,
                "duration_seconds": device["frame_duration_seconds"],
                "width": device["width"],
                "height": device["height"],
                "subtype": device["media_subtype_fourcc"],
                "connection_enabled": True,
                "connection_active": True,
                "drop_reason": "FrameWasLate",
            }
        )
        raw["d405_drop_count"] = 1
    elif mutation == "format":
        raw["events"][0]["width"] = 999
    elif mutation == "self_score":
        raw["verdict"] = "verified"
    else:
        raw["independent_camera_sessions_used"] = 1
    _write(raw_path, raw)
    attempt_path = observed / "attempt.json"
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    attempt["raw_observation_sha256"] = _sha(raw_path)
    _write(attempt_path, attempt)
    if mutation in {"self_score", "independent_session"}:
        with pytest.raises(AVFoundationFormatInventoryError):
            evaluate(
                contract_path=CONTRACT,
                observation_root=observed,
                output_root=tmp_path / "evaluated",
            )
    else:
        evaluation, _ = evaluate(
            contract_path=CONTRACT,
            observation_root=observed,
            output_root=tmp_path / "evaluated",
        )
        assert evaluation["verdict"] == "common_session_callback_delivery_degraded"


def test_evaluation_is_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(ROOT)
    observed = _materialize(tmp_path)
    first = evaluate(
        contract_path=CONTRACT,
        observation_root=observed,
        output_root=tmp_path / "eval-1",
    )
    second = evaluate(
        contract_path=CONTRACT,
        observation_root=observed,
        output_root=tmp_path / "eval-2",
    )
    assert first == second
    assert (tmp_path / "eval-1/evaluation.json").read_bytes() == (
        tmp_path / "eval-2/evaluation.json"
    ).read_bytes()

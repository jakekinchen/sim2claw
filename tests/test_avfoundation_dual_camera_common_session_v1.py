from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "configs/evaluations/avfoundation_dual_camera_common_session_v1.json"
)
SOURCE = (
    ROOT / "tools/macos/AVFoundationDualCameraCommonSessionV1.swift"
)


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

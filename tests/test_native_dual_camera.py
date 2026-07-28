from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sim2claw.native_dual_camera import (
    ACTIVE_RUNTIME_CONTRACT_PATH,
    PROVEN_CONTRACT_PATH,
    READY_SCHEMA,
    REPORT_SCHEMA,
    SEALED_OBSERVATION_CONTRACT_PATH,
    NativeDualCameraRecorder,
    validate_native_report,
)
from sim2claw.overhead_video import OverheadVideoError


def _report(contract: dict[str, object]) -> dict[str, object]:
    devices = contract["devices"]

    def state(role: str, *, after_stop: bool = False) -> dict[str, object]:
        device = devices[role]
        return {
            "role": role,
            "localized_name": device["exact_localized_name"],
            "unique_id": device["exact_unique_id"],
            "model_id": device["exact_model_id"],
            "format_index": -1 if after_stop else device["format_index"],
            "width": device["width"],
            "height": device["height"],
            "subtype": device["media_subtype_fourcc"],
            "minimum_duration_seconds": device["frame_duration_seconds"],
            "maximum_duration_seconds": device["frame_duration_seconds"],
        }

    def stage(name: str, *, after_stop: bool = False) -> dict[str, object]:
        return {
            "name": name,
            "session_running": name == "after_start",
            "d405_input_admitted": True,
            "c922_input_admitted": True,
            "d405_output_admitted": True,
            "c922_output_admitted": True,
            "d405_output_bound_to_exact_input": True,
            "c922_output_bound_to_exact_input": True,
            "d405": state("d405", after_stop=after_stop),
            "c922": state("c922", after_stop=after_stop),
        }

    return {
        "schema_version": REPORT_SCHEMA,
        "status": "completed",
        "failure_reason": None,
        "session_count": 1,
        "independent_camera_sessions": 0,
        "post_stop_format_index_operational_gate": False,
        "stages": [
            stage("before_commit"),
            stage("after_commit"),
            stage("after_start"),
            stage("after_stop", after_stop=True),
        ],
        "streams": [
            {
                "role": role,
                "output_path": f"{role}.mov",
                "output_callback_count": 10,
                "apple_drop_callback_count": 0,
                "writer_append_count": 8,
                "warmup_excluded_callback_count": 2,
                "writer_backpressure_count": 0,
                "first_pts_seconds": 1.0,
                "last_pts_seconds": 2.0,
                "first_host_continuous_ns": 100,
                "last_host_continuous_ns": 200,
                "writer_status": "completed",
                "errors": [],
            }
            for role in ("c922", "d405")
        ],
    }


def test_runtime_binding_preserves_sealed_contract_and_updates_only_topology() -> None:
    sealed = json.loads(SEALED_OBSERVATION_CONTRACT_PATH.read_text(encoding="utf-8"))
    active = json.loads(ACTIVE_RUNTIME_CONTRACT_PATH.read_text(encoding="utf-8"))

    assert PROVEN_CONTRACT_PATH == ACTIVE_RUNTIME_CONTRACT_PATH
    assert sealed["devices"]["d405"]["exact_unique_id"] == "0x20000080860b5b"
    assert active["devices"]["d405"]["exact_unique_id"] == "0x812000080860b5b"
    for role in ("d405", "c922"):
        for field in (
            "exact_localized_name",
            "exact_model_id",
            "format_index",
            "frame_rate_range_index",
            "width",
            "height",
            "media_subtype_fourcc",
            "supported_fps",
            "frame_duration_seconds",
        ):
            assert active["devices"][role][field] == sealed["devices"][role][field]


def test_post_stop_object_identity_reset_is_not_an_operational_gate() -> None:
    contract = json.loads(PROVEN_CONTRACT_PATH.read_text(encoding="utf-8"))
    report = _report(contract)

    result = validate_native_report(report, devices=contract["devices"])

    assert result == {
        "active_session_exact_formats": True,
        "active_session_exact_stream_bindings": True,
        "writers_completed": True,
        "after_stop_format_index_operational_gate": False,
    }
    assert report["stages"][-1]["c922"]["format_index"] == -1
    assert report["stages"][-1]["d405"]["format_index"] == -1


def test_active_session_format_change_fails_closed() -> None:
    contract = json.loads(PROVEN_CONTRACT_PATH.read_text(encoding="utf-8"))
    report = copy.deepcopy(_report(contract))
    report["stages"][2]["c922"]["width"] = 1920

    with pytest.raises(OverheadVideoError, match="active-session identity"):
        validate_native_report(report, devices=contract["devices"])


def test_runtime_command_uses_one_process_and_exact_proven_devices(
    tmp_path: Path,
) -> None:
    recorder = NativeDualCameraRecorder(
        tmp_path,
        ffmpeg_path="/fixture/ffmpeg",
        ffprobe_path="/fixture/ffprobe",
    )
    recorder.binary_path = tmp_path / "runtime/dual-camera-recorder"

    command = recorder._command()

    assert command[0] == str(recorder.binary_path)
    assert command.count("--output-root") == 1
    assert command.count("--c922-name") == 1
    assert command.count("--d405-name") == 1
    assert "C922 Pro Stream Webcam" in command
    assert "Intel(R) RealSense(TM) Depth Camera 405  Depth" in command
    assert "640" in command
    assert "424" in command


def test_first_frame_readiness_requires_exact_active_stream_bindings(
    tmp_path: Path,
) -> None:
    contract = json.loads(PROVEN_CONTRACT_PATH.read_text(encoding="utf-8"))
    completed = _report(contract)
    ready = {
        **completed,
        "schema_version": READY_SCHEMA,
        "status": "recording",
        "common_session_running": True,
        "stages": completed["stages"][:3],
        "streams": [
            {**stream, "writer_status": "writing"}
            for stream in completed["streams"]
        ],
    }
    recorder = NativeDualCameraRecorder(
        tmp_path,
        ffmpeg_path="/fixture/ffmpeg",
        ffprobe_path="/fixture/ffprobe",
    )

    recorder._validate_ready(ready)
    ready["stages"][2]["d405_output_bound_to_exact_input"] = False

    with pytest.raises(OverheadVideoError, match="first-frame readiness"):
        recorder._validate_ready(ready)

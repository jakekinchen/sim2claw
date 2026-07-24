from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from sim2claw.overhead_video import (
    DEFAULT_WRIST_CAMERA_NAME,
    OverheadVideoRecorder,
    OverheadVideoError,
    WRIST_VIDEO_SCHEMA,
    WristVideoRecorder,
)


class _FakeStdin:
    def __init__(self) -> None:
        self.writes: list[bytes] = []

    def write(self, value: bytes) -> None:
        self.writes.append(value)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None


class _FakeProcess:
    def __init__(self, *, wait_results: list[int | str]) -> None:
        self.pid = 4242
        self.returncode: int | None = None
        self.stdin = _FakeStdin()
        self.wait_results = list(wait_results)
        self.wait_timeouts: list[float] = []
        self.terminate_calls = 0
        self.kill_calls = 0

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, *, timeout: float) -> int:
        self.wait_timeouts.append(timeout)
        result = self.wait_results.pop(0)
        if result == "timeout":
            raise subprocess.TimeoutExpired("ffmpeg", timeout)
        self.returncode = int(result)
        return self.returncode

    def terminate(self) -> None:
        self.terminate_calls += 1

    def kill(self) -> None:
        self.kill_calls += 1


def test_wrist_recorder_uses_exact_low_bandwidth_d405_contract(
    tmp_path: Path,
) -> None:
    recorder = WristVideoRecorder(tmp_path / "wrist_d405.mkv")

    assert recorder.camera_name == DEFAULT_WRIST_CAMERA_NAME
    assert recorder.schema_version == WRIST_VIDEO_SCHEMA
    assert (recorder.width, recorder.height, recorder.fps) == (424, 240, 5)
    assert recorder.source_pixel_format == "uyvy422"
    assert recorder.video_filter == ""
    assert recorder.metric_depth is False
    assert recorder.browser_output_path.name == "wrist_d405.browser.mp4"
    assert recorder.source_startup_grace_seconds == 3.0
    assert recorder.source_stall_timeout_seconds == 3.0
    assert recorder.shutdown_q_timeout_seconds == 1.0
    assert recorder.shutdown_sigint_timeout_seconds == 3.0
    assert recorder.shutdown_terminate_timeout_seconds == 2.0
    assert recorder.shutdown_kill_timeout_seconds == 2.0
    assert recorder._encoder_args() == [
        "-c:v",
        "ffv1",
        "-level",
        "3",
        "-g",
        "1",
        "-f",
        "matroska",
    ]
    assert recorder._browser_encoder_args() == [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
    ]


def test_alive_d405_process_without_source_growth_fails_during_capture(
    tmp_path: Path,
) -> None:
    now = [0.0]
    source = tmp_path / "wrist_d405.mkv"
    recorder = WristVideoRecorder(
        source,
        clock=lambda: now[0],
        source_startup_grace_seconds=1.0,
        source_stall_timeout_seconds=2.0,
    )
    recorder.process = _FakeProcess(wait_results=[0])
    recorder.started_monotonic = 0.0
    source.write_bytes(b"first-frame")

    now[0] = 0.5
    recorder.ensure_running()
    now[0] = 2.4
    recorder.ensure_running()
    now[0] = 2.6
    with pytest.raises(OverheadVideoError, match="source stopped growing"):
        recorder.ensure_running()

    assert recorder.source_stall_detected is True
    assert recorder.source_bytes_observed == len(b"first-frame")
    assert recorder.source_stall_elapsed_seconds == pytest.approx(2.1)


def test_missing_d405_source_fails_after_grace_plus_timeout(
    tmp_path: Path,
) -> None:
    now = [0.0]
    recorder = WristVideoRecorder(
        tmp_path / "missing.mkv",
        clock=lambda: now[0],
        source_startup_grace_seconds=3.0,
        source_stall_timeout_seconds=3.0,
    )
    recorder.process = _FakeProcess(wait_results=[0])
    recorder.started_monotonic = 0.0

    now[0] = 2.9
    recorder.ensure_running()
    now[0] = 5.9
    recorder.ensure_running()
    now[0] = 6.1
    with pytest.raises(OverheadVideoError, match="source stopped growing"):
        recorder.ensure_running()

    assert recorder.source_bytes_observed == 0
    assert recorder.source_stall_detected is True
    assert recorder.source_stall_elapsed_seconds == pytest.approx(3.1)


def test_source_stall_remains_failed_after_readable_partial_file(
    tmp_path: Path,
) -> None:
    now = [0.0]
    source = tmp_path / "wrist_d405.mkv"
    source.write_bytes(b"partial-readable-matroska")
    recorder = WristVideoRecorder(
        source,
        clock=lambda: now[0],
        source_startup_grace_seconds=0.0,
        source_stall_timeout_seconds=1.0,
    )
    process = _FakeProcess(wait_results=[0])
    recorder.process = process
    recorder.started_monotonic = 0.0
    recorder.discovery = {
        "camera_name": DEFAULT_WRIST_CAMERA_NAME,
        "camera_index": None,
    }
    now[0] = 0.1
    recorder.ensure_running()
    now[0] = 1.2
    with pytest.raises(OverheadVideoError):
        recorder.ensure_running()
    recorder._probe_output = lambda: {"streams": [{"codec_name": "ffv1"}]}

    report = OverheadVideoRecorder.finish(
        recorder,
        action_started_monotonic=0.0,
        action_stopped_monotonic=None,
        post_roll_seconds=0.0,
    )

    assert report["status"] == "failed"
    assert report["failure_kind"] == "source_transport_stall"
    assert report["source_stall_detected"] is True
    assert report["shutdown_terminal_stage"] == "stdin_q"
    assert report["ffmpeg_return_code"] == 0


def test_shutdown_escalates_from_q_to_process_group_sigint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "wrist_d405.mkv"
    source.write_bytes(b"complete-matroska")
    recorder = WristVideoRecorder(source, clock=lambda: 5.0)
    process = _FakeProcess(wait_results=["timeout", 255])
    recorder.process = process
    recorder.started_monotonic = 0.0
    recorder.discovery = {
        "camera_name": DEFAULT_WRIST_CAMERA_NAME,
        "camera_index": None,
    }
    recorder._probe_output = lambda: {"streams": [{"codec_name": "ffv1"}]}
    signals: list[tuple[int, int]] = []
    monkeypatch.setattr(
        "sim2claw.overhead_video.os.killpg",
        lambda pid, sent_signal: signals.append((pid, sent_signal)),
    )

    report = OverheadVideoRecorder.finish(
        recorder,
        action_started_monotonic=0.0,
        action_stopped_monotonic=None,
        post_roll_seconds=0.0,
    )

    assert report["status"] == "completed"
    assert report["shutdown_stages_attempted"] == [
        "stdin_q",
        "process_group_sigint",
    ]
    assert report["shutdown_terminal_stage"] == "process_group_sigint"
    assert signals == [(process.pid, 2)]
    assert process.terminate_calls == 0
    assert process.kill_calls == 0


def test_sigint_failure_falls_through_to_terminate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "wrist_d405.mkv"
    source.write_bytes(b"complete-matroska")
    recorder = WristVideoRecorder(source, clock=lambda: 5.0)
    process = _FakeProcess(wait_results=["timeout", "timeout", 0])
    recorder.process = process
    recorder.started_monotonic = 0.0
    recorder.discovery = {
        "camera_name": DEFAULT_WRIST_CAMERA_NAME,
        "camera_index": None,
    }
    recorder._probe_output = lambda: {"streams": [{"codec_name": "ffv1"}]}

    def _failed_sigint(_pid: int, _sent_signal: int) -> None:
        raise OSError("process group unavailable")

    monkeypatch.setattr("sim2claw.overhead_video.os.killpg", _failed_sigint)
    report = OverheadVideoRecorder.finish(
        recorder,
        action_started_monotonic=0.0,
        action_stopped_monotonic=None,
        post_roll_seconds=0.0,
    )

    assert report["status"] == "completed"
    assert report["shutdown_stages_attempted"] == [
        "stdin_q",
        "process_group_sigint",
        "terminate",
    ]
    assert report["shutdown_terminal_stage"] == "terminate"
    assert report["shutdown_errors"] == ["process_group_sigint:OSError"]
    assert process.terminate_calls == 1
    assert process.kill_calls == 0


def test_early_process_exit_and_unreadable_output_fail_closed(
    tmp_path: Path,
) -> None:
    source = tmp_path / "wrist_d405.mkv"
    source.write_bytes(b"not-readable")
    recorder = WristVideoRecorder(source, clock=lambda: 5.0)
    process = _FakeProcess(wait_results=[])
    process.returncode = 1
    recorder.process = process
    recorder.started_monotonic = 0.0
    recorder.discovery = {
        "camera_name": DEFAULT_WRIST_CAMERA_NAME,
        "camera_index": None,
    }
    recorder._probe_output = lambda: None

    with pytest.raises(OverheadVideoError, match="stopped before"):
        recorder.ensure_running()
    report = recorder.finish(
        action_started_monotonic=0.0,
        action_stopped_monotonic=None,
        post_roll_seconds=0.0,
    )

    assert report["status"] == "failed"
    assert report["failure_kind"] == "capture_process_exited"
    assert report["shutdown_stages_attempted"] == []
    assert report["shutdown_terminal_stage"] == "already_exited"

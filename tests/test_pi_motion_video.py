from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from sim2claw.pi_motion_video import (
    CONTRACT_PATH,
    MotionTricamRecorder,
    PiMotionVideoError,
    PiMotionVideoRecorder,
    load_contract,
)


class _Clock:
    def __init__(self) -> None:
        self.value = 100.0

    def now(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


class _Process:
    def __init__(
        self,
        *,
        clock: _Clock,
        stdout: Any,
        command: list[str],
    ) -> None:
        self.clock = clock
        self.command = command
        self.ready_at = clock.now() + 0.2
        self.forced_exit = False
        stdout.write(b"\x00\x00\x00\x01" * 1024)

    def poll(self) -> int | None:
        if self.forced_exit or self.clock.now() >= self.ready_at:
            return 0
        return None

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        return 0

    def terminate(self) -> None:
        self.forced_exit = True

    def kill(self) -> None:
        self.forced_exit = True


class _Run:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **kwargs: Any) -> Any:
        del kwargs
        self.commands.append(command)
        executable = Path(command[0]).name
        if executable == "scp":
            Path(command[-1]).write_text(
                "# timecode format v2\n"
                + "\n".join(str(index * 33_333.0) for index in range(60))
                + "\n",
                encoding="utf-8",
            )
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        if executable == "ffmpeg":
            Path(command[-1]).write_bytes(b"fixture-browser-video")
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        if executable == "ffprobe":
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    {
                        "streams": [
                            {
                                "codec_name": "h264",
                                "width": 1536,
                                "height": 864,
                                "avg_frame_rate": "30/1",
                                "nb_read_frames": "60",
                            }
                        ],
                        "format": {
                            "duration": "2.0",
                            "size": "12345",
                        },
                    }
                ),
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")


def test_contract_freezes_bounded_pi_observation_without_robot_authority() -> None:
    contract = load_contract()

    assert contract["duration_seconds"] == 8
    assert contract["minimum_frames"] == 60
    assert contract["authority"] == {
        "camera_observation": True,
        "camera_exposure_synchronization": False,
        "camera_intrinsics": False,
        "camera_extrinsics": False,
        "robot_gateway": False,
        "robot_motion": False,
        "policy": False,
        "task_success": False,
    }


def test_long_contract_is_bounded_for_full_geometric_stage(tmp_path: Path) -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    contract["contract_id"] = "fixture-long-motion"
    contract["duration_seconds"] = 15
    contract["minimum_frames"] = 300
    path = tmp_path / "long.json"
    path.write_text(json.dumps(contract), encoding="utf-8")

    loaded = load_contract(path)

    assert loaded["duration_seconds"] == 15
    assert loaded["minimum_frames"] == 300


def test_extended_contract_is_bounded_for_slow_roundtrip(tmp_path: Path) -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    contract["contract_id"] = "fixture-extended-roundtrip"
    contract["duration_seconds"] = 25
    contract["minimum_frames"] = 600
    path = tmp_path / "extended.json"
    path.write_text(json.dumps(contract), encoding="utf-8")

    loaded = load_contract(path)

    assert loaded["duration_seconds"] == 25
    assert loaded["minimum_frames"] == 600


def test_35_second_contract_is_bounded_for_hover_hold_roundtrip() -> None:
    path = CONTRACT_PATH.with_name("pi_imx708_motion_video_35s_v1.json")

    loaded = load_contract(path)

    assert loaded["duration_seconds"] == 35
    assert loaded["minimum_frames"] == 900


def test_120_second_contract_is_bounded_for_parking_enclosure() -> None:
    path = CONTRACT_PATH.with_name("pi_imx708_motion_video_120s_v1.json")

    loaded = load_contract(path)

    assert loaded["duration_seconds"] == 120
    assert loaded["minimum_frames"] == 3000


def test_180_second_contract_is_bounded_for_worst_case_parking() -> None:
    path = CONTRACT_PATH.with_name("pi_imx708_motion_video_180s_v1.json")

    loaded = load_contract(path)

    assert loaded["duration_seconds"] == 180
    assert loaded["minimum_frames"] == 4500


def test_fake_pi_capture_hash_binds_video_pts_and_action_interval(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    runner = _Run()
    processes: list[_Process] = []

    def popen(command: list[str], **kwargs: Any) -> _Process:
        process = _Process(
            clock=clock,
            stdout=kwargs["stdout"],
            command=command,
        )
        processes.append(process)
        return process

    recorder = PiMotionVideoRecorder(
        tmp_path / "pi",
        contract_path=CONTRACT_PATH,
        popen_factory=popen,
        run_fn=runner,
        clock=clock.now,
        sleep_fn=clock.sleep,
        token_factory=lambda: "fixturetoken",
        ssh_path="/fixture/ssh",
        scp_path="/fixture/scp",
        ffmpeg_path="/fixture/ffmpeg",
        ffprobe_path="/fixture/ffprobe",
    )
    started = recorder.start()
    receipt = recorder.finish(
        action_started_monotonic=100.05,
        action_stopped_monotonic=100.15,
        post_roll_seconds=0.5,
    )

    assert started["status"] == "recording"
    assert receipt["status"] == "completed"
    assert receipt["pts"]["count"] == receipt["observed_video"]["frame_count"] == 60
    assert receipt["action_interval_enclosed"] is True
    assert receipt["timestamp_semantics"][
        "cross_camera_exposure_synchronized"
    ] is False
    assert receipt["claim_limits"]["physical_authority"] is False
    assert processes[0].command[-2:] == ["--output", "-"]
    assert processes[0].command[
        processes[0].command.index("--codec") + 1
    ] == "mjpeg"
    assert "--save-pts" in processes[0].command
    assert any(Path(command[0]).name == "scp" for command in runner.commands)
    assert any(
        Path(command[0]).name == "ssh" and "rm" in command
        for command in runner.commands
    )


def test_pi_premature_exit_fails_closed(tmp_path: Path) -> None:
    clock = _Clock()
    runner = _Run()
    process: _Process | None = None

    def popen(command: list[str], **kwargs: Any) -> _Process:
        nonlocal process
        process = _Process(
            clock=clock,
            stdout=kwargs["stdout"],
            command=command,
        )
        return process

    recorder = PiMotionVideoRecorder(
        tmp_path / "pi",
        popen_factory=popen,
        run_fn=runner,
        clock=clock.now,
        sleep_fn=clock.sleep,
        token_factory=lambda: "fixturetoken",
        ssh_path="/fixture/ssh",
        scp_path="/fixture/scp",
        ffmpeg_path="/fixture/ffmpeg",
        ffprobe_path="/fixture/ffprobe",
    )
    recorder.start()
    assert process is not None
    process.forced_exit = True
    with pytest.raises(PiMotionVideoError, match="exited"):
        recorder.ensure_running()


class _Component:
    def __init__(self, *, fail_start: bool = False) -> None:
        self.fail_start = fail_start
        self.started = False
        self.finished = False
        self.polled = 0

    def start(self) -> dict[str, Any]:
        if self.fail_start:
            raise PiMotionVideoError("injected start failure")
        self.started = True
        return {"started": True}

    def ensure_running(self) -> None:
        self.polled += 1

    def finish(self, **kwargs: Any) -> dict[str, Any]:
        del kwargs
        self.finished = True
        return {
            "overhead": {"status": "completed"},
            "wrist": {"status": "completed"},
            "common_session": {"session_count": 1},
        }

    def _abort(self) -> None:
        self.finished = True


def test_composite_pi_start_failure_rolls_back_dual_camera(
    tmp_path: Path,
) -> None:
    dual = _Component()
    pi = _Component(fail_start=True)
    recorder = MotionTricamRecorder(
        tmp_path / "capture",
        dual_factory=lambda path: dual,
        pi_factory=lambda path, **kwargs: pi,
    )

    with pytest.raises(PiMotionVideoError, match="injected start failure"):
        recorder.start()

    assert dual.started is True
    assert dual.finished is True

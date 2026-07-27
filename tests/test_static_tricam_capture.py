from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image
import pytest

from sim2claw.cli import build_parser
from sim2claw.learning_factory_artifacts import sha256_file
from sim2claw.static_tricam_capture import (
    CONTRACT_PATH,
    StaticTricamCapture,
    StaticTricamCaptureError,
    capture_static_tricam_bundle,
    load_contract,
)


SESSION_TOKEN = "fixture-c922-session"
MOUNT_TOKEN = "fixture-fixed-mount"


class _Clock:
    def __init__(self) -> None:
        self.value = 100_000_000_000

    def now(self) -> int:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += int(seconds * 1_000_000_000)

    def sleep(self, seconds: float) -> None:
        self.advance(seconds)


class _FakeC922:
    def __init__(
        self,
        output_root: Path,
        *,
        contract: dict[str, Any],
        camera_session_token: str,
        fixed_mount_token: str,
        clock_ns_fn: Any,
        state: dict[str, Any],
    ) -> None:
        assert camera_session_token == SESSION_TOKEN
        assert fixed_mount_token == MOUNT_TOKEN
        self.output_root = output_root
        self.contract = contract
        self.clock_ns_fn = clock_ns_fn
        self.state = state

    def _identity(self) -> dict[str, Any]:
        camera = self.contract["camera"]
        return {
            "cameraName": camera["localized_name"],
            "cameraUniqueID": camera["unique_id"],
            "cameraModelID": camera["model_id"],
            "width": camera["width"],
            "height": camera["height"],
            "mediaSubtype": camera["media_subtype_fourcc"],
            "pixelFormat": camera["media_subtype_fourcc"],
        }

    def start(self) -> dict[str, Any]:
        self.output_root.mkdir(parents=True)
        self.state["c922_started"] = True
        return {
            **self._identity(),
            "status": "ready",
            "firstFrameHostContinuousNS": self.clock_ns_fn(),
        }

    def ensure_running(self) -> None:
        assert self.state["c922_started"]
        assert not self.state.get("c922_finished", False)

    def finish(self) -> dict[str, Any]:
        self.state["c922_finished"] = True
        frames = self.output_root / "frames"
        frames.mkdir(exist_ok=True)
        events = []
        start = 100_000_000_000
        for index in range(61):
            image = frames / f"frame-{index:03d}.png"
            Image.new("RGB", (640, 480), (index % 255, 20, 30)).save(image)
            events.append(
                {
                    "sequence": index,
                    "hostContinuousNS": start + index * 33_000_000,
                    "ptsSeconds": index / 30.0,
                    "durationSeconds": 1 / 30,
                    **self._identity(),
                    "pngPath": f"frames/{image.name}",
                    "pngSHA256": sha256_file(image),
                }
            )
        ledger = self.output_root / "frames.jsonl"
        ledger.write_text(
            "".join(json.dumps(item) + "\n" for item in events),
            encoding="utf-8",
        )
        return {
            **self._identity(),
            "status": "completed",
            "outputCallbackCount": len(events),
            "droppedCallbackCount": 0,
            "retainedFrameCount": len(events),
            "ledger_path": str(ledger),
            "ledger_sha256": sha256_file(ledger),
        }


class _FakeD405:
    def __init__(
        self,
        output_root: Path,
        *,
        contract: dict[str, Any],
        clock_ns_fn: Any,
        state: dict[str, Any],
        failed_gate: str | None = None,
    ) -> None:
        self.output_root = output_root
        self.contract = contract
        self.clock_ns_fn = clock_ns_fn
        self.state = state
        self.failed_gate = failed_gate

    def start(self) -> dict[str, Any]:
        self.output_root.mkdir(parents=True)
        self.state["d405_started"] = True
        return {
            "owner": "rs-record",
            "ready_observed_host_monotonic_ns": self.clock_ns_fn(),
            "identity_before": self.contract["d405"]["expected_device"],
        }

    def ensure_running(self) -> None:
        assert self.state["d405_started"]
        assert not self.state.get("d405_finished", False)

    def finish(self) -> dict[str, Any]:
        self.state["d405_finished"] = True
        checks = {
            "depth_encoding": True,
            "color_encoding": True,
            "depth_fps": True,
            "color_fps": True,
            "depth_width": True,
            "depth_height": True,
            "color_width": True,
            "color_height": True,
            "depth_frame_count": True,
            "color_frame_count": True,
            "rgb_depth_pair_delta": True,
            "depth_units": True,
        }
        if self.failed_gate is not None:
            checks[self.failed_gate] = False
        return {
            "status": "completed",
            "owner": "rs-record",
            "checks": checks,
            "depth_frame_count": 90,
            "color_frame_count": 90,
            "identity_before": self.contract["d405"]["expected_device"],
            "identity_after": self.contract["d405"]["expected_device"],
        }


def _pi_capture(
    specification: dict[str, Any],
    *,
    shot_index: int,
    output_path: Path,
    clock_ns_fn: Any,
    clock: _Clock,
    fail_index: int | None = None,
) -> dict[str, Any]:
    if shot_index == fail_index:
        raise StaticTricamCaptureError("injected Pi failure")
    start = clock_ns_fn()
    clock.advance(0.2)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(
        "RGB",
        (specification["width"], specification["height"]),
        (10 + shot_index, 20, 30),
    ).save(output_path)
    return {
        "schema_version": "sim2claw.static_tricam_pi_still.v1",
        "shot_index": shot_index,
        "status": "completed",
        "camera": specification["camera"],
        "width": specification["width"],
        "height": specification["height"],
        "horizontal_flip": True,
        "vertical_flip": True,
        "autofocus_mode": specification["autofocus_mode"],
        "lens_position_reciprocal_m": specification[
            "lens_position_reciprocal_m"
        ],
        "host_monotonic_start_ns": start,
        "host_monotonic_end_ns": clock_ns_fn(),
        "path": str(output_path),
        "sha256": sha256_file(output_path),
        "bytes": output_path.stat().st_size,
        "process_completed": True,
    }


def _run(
    tmp_path: Path,
    *,
    fail_pi_index: int | None = None,
    failed_d405_gate: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    clock = _Clock()
    state: dict[str, Any] = {}

    def c922_factory(output_root: Path, **kwargs: Any) -> _FakeC922:
        return _FakeC922(output_root, state=state, **kwargs)

    def d405_factory(output_root: Path, **kwargs: Any) -> _FakeD405:
        return _FakeD405(
            output_root,
            state=state,
            failed_gate=failed_d405_gate,
            **kwargs,
        )

    def pi_capture(specification: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return _pi_capture(
            specification,
            clock=clock,
            fail_index=fail_pi_index,
            **kwargs,
        )

    receipt = capture_static_tricam_bundle(
        output_root=tmp_path / "capture",
        operator_acknowledged=True,
        camera_session_token=SESSION_TOKEN,
        fixed_mount_token=MOUNT_TOKEN,
        c922_factory=c922_factory,
        d405_factory=d405_factory,
        pi_capture=pi_capture,
        clock_ns_fn=clock.now,
        sleep_fn=clock.sleep,
    )
    return receipt, state


def test_contract_freezes_three_separate_camera_owners() -> None:
    contract = load_contract()

    assert contract["ownership"] == {
        "c922_owner": "NativeC922StillRecorder",
        "d405_owner": "rs-record",
        "pi_owner": "ssh_rpicam-still",
        "forbid_avfoundation_d405": True,
        "forbid_native_dual_camera_recorder": True,
        "maximum_simultaneous_owner_per_device": 1,
    }
    source = (
        Path(__file__).parents[1] / "src/sim2claw/static_tricam_capture.py"
    ).read_text(encoding="utf-8")
    assert "from .native_dual_camera" not in source
    assert "physical_gateway" not in source


def test_cli_exposes_explicit_tokens_and_rigidity_acknowledgement(
    tmp_path: Path,
) -> None:
    output = tmp_path / "capture"
    args = build_parser().parse_args(
        [
            "static-tricam-capture",
            "--output",
            str(output),
            "--camera-session-token",
            SESSION_TOKEN,
            "--fixed-mount-token",
            MOUNT_TOKEN,
            "--yes",
        ]
    )

    assert args.output == output
    assert args.camera_session_token == SESSION_TOKEN
    assert args.fixed_mount_token == MOUNT_TOKEN
    assert args.yes is True
    assert args.contract == CONTRACT_PATH


def test_fake_capture_hash_binds_three_pi_stills_and_tears_down(
    tmp_path: Path,
) -> None:
    receipt, state = _run(tmp_path)

    assert receipt["status"] == "completed_static_tricam_capture"
    assert receipt["ownership"]["owners_remaining_after_teardown"] == 0
    assert receipt["teardown"] == {
        "c922_owner_completed": True,
        "d405_owner_completed": True,
        "pi_processes_completed": 3,
        "owners_remaining": 0,
    }
    assert state == {
        "c922_started": True,
        "d405_started": True,
        "d405_finished": True,
        "c922_finished": True,
    }
    assert len(receipt["pi_stills"]) == 3
    assert all(
        sha256_file(Path(item["path"])) == item["sha256"]
        for item in receipt["pi_stills"]
    )
    window = receipt["common_interior_window"]
    assert window["duration_seconds"] >= 2.0
    assert all(
        window["start_ns"] <= item["host_monotonic_start_ns"]
        <= item["host_monotonic_end_ns"] <= window["end_ns"]
        for item in receipt["pi_stills"]
    )
    assert receipt["scene_rigidity"] == {
        "operator_acknowledged": True,
        "component_robot_gateway_constructed": False,
        "component_robot_motion_commands": 0,
        "external_reviewed_gateway_hold_permitted": True,
        "independently_measured_by_component": False,
    }
    assert receipt["verdict"]["camera_transform_fitted"] is False
    assert receipt["verdict"]["simulator_parameter_promoted"] is False
    assert (tmp_path / "capture/capture_receipt.json").is_file()


def test_camera_capture_lifecycle_accepts_external_hold_bounds(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    state: dict[str, Any] = {}

    def c922_factory(output_root: Path, **kwargs: Any) -> _FakeC922:
        return _FakeC922(output_root, state=state, **kwargs)

    def d405_factory(output_root: Path, **kwargs: Any) -> _FakeD405:
        return _FakeD405(output_root, state=state, **kwargs)

    def pi_capture(specification: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return _pi_capture(specification, clock=clock, **kwargs)

    capture = StaticTricamCapture(
        tmp_path / "capture",
        operator_acknowledged=True,
        camera_session_token=SESSION_TOKEN,
        fixed_mount_token=MOUNT_TOKEN,
        c922_factory=c922_factory,
        d405_factory=d405_factory,
        pi_capture=pi_capture,
        clock_ns_fn=clock.now,
        sleep_fn=clock.sleep,
    )
    started = capture.start()
    hold_start = clock.now() / 1_000_000_000.0
    for _index in range(3):
        capture.ensure_running()
    clock.advance(1.4)
    hold_stop = clock.now() / 1_000_000_000.0
    receipt = capture.finish(
        action_started_monotonic=hold_start,
        action_stopped_monotonic=hold_stop,
        post_roll_seconds=0.0,
    )

    assert started["status"] == "recording_static_tricam"
    assert receipt["external_rigid_hold"]["start"] == hold_start
    assert receipt["external_rigid_hold"]["end"] == hold_stop
    assert receipt["external_rigid_hold"][
        "receipt_binding_required_from_caller"
    ]
    assert receipt["teardown"]["owners_remaining"] == 0


def test_pi_failure_still_tears_down_both_local_camera_owners(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    state: dict[str, Any] = {}

    def c922_factory(output_root: Path, **kwargs: Any) -> _FakeC922:
        return _FakeC922(output_root, state=state, **kwargs)

    def d405_factory(output_root: Path, **kwargs: Any) -> _FakeD405:
        return _FakeD405(output_root, state=state, **kwargs)

    def pi_capture(specification: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return _pi_capture(
            specification,
            clock=clock,
            fail_index=1,
            **kwargs,
        )

    with pytest.raises(StaticTricamCaptureError, match="injected Pi failure"):
        capture_static_tricam_bundle(
            output_root=tmp_path / "capture",
            operator_acknowledged=True,
            camera_session_token=SESSION_TOKEN,
            fixed_mount_token=MOUNT_TOKEN,
            c922_factory=c922_factory,
            d405_factory=d405_factory,
            pi_capture=pi_capture,
            clock_ns_fn=clock.now,
            sleep_fn=clock.sleep,
        )

    assert state["d405_finished"] is True
    assert state["c922_finished"] is True
    assert not (tmp_path / "capture/capture_receipt.json").exists()


def test_d405_frame_gate_rejects_only_after_both_owners_teardown(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        StaticTricamCaptureError, match="D405 capture proof is incomplete"
    ):
        _run(tmp_path, failed_d405_gate="depth_frame_count")

    assert not (tmp_path / "capture/capture_receipt.json").exists()


def test_operator_acknowledgement_is_required_without_opening_an_owner(
    tmp_path: Path,
) -> None:
    constructed = False

    def forbidden_factory(*args: Any, **kwargs: Any) -> Any:
        nonlocal constructed
        constructed = True
        raise AssertionError("owner must not be constructed")

    with pytest.raises(StaticTricamCaptureError, match="acknowledgement"):
        capture_static_tricam_bundle(
            output_root=tmp_path / "capture",
            operator_acknowledged=False,
            camera_session_token=SESSION_TOKEN,
            fixed_mount_token=MOUNT_TOKEN,
            c922_factory=forbidden_factory,
            d405_factory=forbidden_factory,
        )

    assert constructed is False
    assert not (tmp_path / "capture").exists()

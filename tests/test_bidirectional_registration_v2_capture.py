from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from sim2claw.bidirectional_registration_v2_capture import (
    RegistrationCaptureV2Error,
    execute_registration_capture,
    review_capture_plan,
)
from sim2claw.learning_factory_artifacts import sha256_file


ROOT = Path(__file__).resolve().parents[1]
PACKET = (
    ROOT
    / "configs/hardware/"
    "bidirectional_pawn_push_v2_registration_capture_v1.json"
)
RECOVERY_PACKET = (
    ROOT
    / "configs/hardware/"
    "bidirectional_pawn_push_v2_registration_capture_v2.json"
)
START = [
    -11.164835164835164,
    -71.38461538461539,
    99.47252747252747,
    -25.714285714285715,
    -102.81318681318682,
    2.494061757719715,
]
RECOVERY_START = [
    -8.263736263736265,
    -106.1978021978022,
    99.20879120879121,
    -94.02197802197803,
    -125.31868131868131,
    2.494061757719715,
]


def _preflight() -> dict[str, object]:
    return {
        "schema_version": "sim2claw.so101_physical_gateway.v2",
        "passed": True,
        "control_source": "frozen_precompiled_follower_actions",
        "real_leader_opened": False,
        "follower_port": "/dev/fake-follower",
        "follower_calibration_sha256": "1" * 64,
        "follower_start_degrees": START,
        "follower_calibrated_minimum": [
            -120.26373626373626,
            -106.63736263736264,
            -102.10989010989012,
            -107.47252747252747,
            -180.0,
            0.0,
        ],
        "follower_calibrated_maximum": [
            120.26373626373626,
            106.63736263736264,
            102.10989010989012,
            107.47252747252747,
            180.0,
            100.0,
        ],
        "physical_follower_torque_enabled": False,
        "device_configuration_rewritten": False,
    }


def _recovery_preflight() -> dict[str, object]:
    result = _preflight()
    result["follower_start_degrees"] = RECOVERY_START
    return result


class _Clock:
    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += max(0.0, seconds)


class _Process:
    def __init__(self) -> None:
        self.running = True

    def poll(self) -> int | None:
        return None if self.running else 0


class _Recorder:
    def __init__(
        self,
        output_root: Path,
        *,
        contract: dict[str, object],
        camera_session_token: str,
        fixed_mount_token: str,
        clock: _Clock,
    ) -> None:
        self.root = output_root
        self.contract = contract
        self.token = camera_session_token
        self.mount = fixed_mount_token
        self.clock = clock
        self.process = _Process()

    def _base(self) -> dict[str, object]:
        camera = self.contract["camera"]
        assert isinstance(camera, dict)
        return {
            "cameraName": camera["localized_name"],
            "cameraUniqueID": camera["unique_id"],
            "cameraModelID": camera["model_id"],
            "width": camera["width"],
            "height": camera["height"],
            "mediaSubtype": camera["media_subtype_fourcc"],
            "pixelFormat": camera["media_subtype_fourcc"],
            "cameraSessionToken": self.token,
            "fixedMountToken": self.mount,
        }

    def start(self) -> dict[str, object]:
        self.root.mkdir(parents=True)
        (self.root / "frames").mkdir()
        return {
            **self._base(),
            "firstFrameHostContinuousNS": int(self.clock() * 1e9),
        }

    def finish(self) -> dict[str, object]:
        events = []
        now = self.clock()
        for sequence, offset in enumerate((-1.5, -1.0, -0.5, 0.0)):
            path = self.root / "frames" / f"frame-{sequence:03d}.png"
            Image.new("RGB", (640, 480), (sequence * 20, 80, 120)).save(path)
            events.append(
                {
                    "schemaVersion": (
                        "sim2claw.c922_terminal_hold_frame_event.v1"
                    ),
                    "sequence": sequence,
                    "hostContinuousNS": int((now + offset) * 1e9),
                    "pngPath": str(path.relative_to(self.root)),
                    "pngSHA256": sha256_file(path),
                    **self._base(),
                }
            )
        ledger = self.root / "frames.jsonl"
        ledger.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in events),
            encoding="utf-8",
        )
        self.process.running = False
        return {
            **self._base(),
            "status": "completed",
            "droppedCallbackCount": 0,
            "outputCallbackCount": len(events),
            "retainedFrameCount": len(events),
            "ledger_path": str(ledger),
            "ledger_sha256": sha256_file(ledger),
        }


class _Gateway:
    def __init__(self, *, fail_after: int | None = None) -> None:
        self.closed = False
        self.samples = 0
        self.fail_after = fail_after

    def open(self, *, enable_motion: bool, paired_pose_confirmed: bool) -> dict:
        assert enable_motion and paired_pose_confirmed
        return {
            "follower_start_degrees": START,
            "physical_follower_torque_enabled": True,
            "device_configuration_rewritten": False,
        }

    def sample(
        self, elapsed_seconds: float, *, exact_requested_degrees: np.ndarray
    ) -> dict:
        del elapsed_seconds
        if self.fail_after is not None and self.samples >= self.fail_after:
            raise RuntimeError("synthetic tracking stop")
        self.samples += 1
        values = exact_requested_degrees.tolist()
        return {
            "follower_requested_degrees": values,
            "follower_command_degrees": values,
            "follower_actual_position_degrees": values,
            "tracking_error_limits": [6.0, 8.0, 6.0, 6.0, 8.0, 12.0],
            "rate_limited": False,
            "safety_clamped": False,
            "stalled": False,
            "stalled_joints": [],
            "assistance": False,
            "intervention": False,
        }

    def close(self) -> None:
        self.closed = True


def test_review_is_motion_free_and_binds_exact_arrays(tmp_path: Path) -> None:
    result = review_capture_plan(
        packet_path=PACKET,
        review_path=tmp_path / "review.json",
        preflight_fn=_preflight,
    )
    assert result["reviewer"]["decision"] == "CONTINUE"
    assert all(result["gates"].values())
    assert result["physical_motion_commanded"] is False
    assert result["camera_opened"] is False
    assert result["gateway_constructed"] is False
    assert result["exact_setup_arrays"]["source_egress"]["shape"] == [92, 6]
    assert result["exact_setup_arrays"]["capture_and_return"]["shape"] == [
        1541,
        6,
    ]


def test_recovery_review_binds_ten_new_targets_and_exact_arrays(
    tmp_path: Path,
) -> None:
    result = review_capture_plan(
        packet_path=RECOVERY_PACKET,
        review_path=tmp_path / "review-v2.json",
        preflight_fn=_recovery_preflight,
    )
    assert result["reviewer"]["decision"] == "CONTINUE"
    assert all(result["gates"].values())
    assert len(result["capture_slices"]) == 10
    assert result["exact_setup_arrays"]["source_egress"]["shape"] == [716, 6]
    assert result["exact_setup_arrays"]["capture_and_return"]["shape"] == [
        2596,
        6,
    ]
    assert result["physical_motion_commanded"] is False
    assert result["camera_opened"] is False
    assert result["gateway_constructed"] is False


def test_execute_captures_eight_targets_and_closes_torque(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    review = tmp_path / "review.json"
    review_capture_plan(
        packet_path=PACKET,
        review_path=review,
        preflight_fn=_preflight,
    )
    gateway = _Gateway()

    def recorder_factory(path: Path, **kwargs: object) -> _Recorder:
        return _Recorder(path, clock=clock, **kwargs)

    result = execute_registration_capture(
        packet_path=PACKET,
        review_path=review,
        output_root=tmp_path / "capture",
        operator_acknowledged=True,
        preflight_fn=_preflight,
        gateway_factory=lambda _: gateway,
        recorder_factory=recorder_factory,
        clock_fn=clock,
        sleep_fn=clock.sleep,
    )
    assert result["status"] == "completed_no_contact_registration_capture"
    assert result["source_egress"]["executed_sample_count"] == 92
    assert result["capture_and_return"]["executed_sample_count"] == 1541
    assert len(result["target_captures"]) == 8
    assert len(result["camera_sessions"]) == 9
    assert result["requested_mapped_sent_byte_identity"]
    assert result["all_target_scored_holds_pass_tracking"]
    assert result["camera_drop_count_total"] == 0
    assert result["torque_off_confirmed"]
    assert result["counted_physical_attempts"] == 0
    assert gateway.closed
    sealed = json.loads(
        (tmp_path / "capture/heldout_sealed_manifest.json").read_text()
    )
    assert all(set(row) == {"opaque_id", "image_sha256", "image_bytes", "capture_receipt_sha256"} for row in sealed["members"])


def test_execution_error_still_closes_gateway_and_records_zero_attempts(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    review = tmp_path / "review.json"
    review_capture_plan(
        packet_path=PACKET,
        review_path=review,
        preflight_fn=_preflight,
    )
    gateway = _Gateway(fail_after=5)

    def recorder_factory(path: Path, **kwargs: object) -> _Recorder:
        return _Recorder(path, clock=clock, **kwargs)

    output = tmp_path / "capture"
    with pytest.raises(RegistrationCaptureV2Error):
        execute_registration_capture(
            packet_path=PACKET,
            review_path=review,
            output_root=output,
            operator_acknowledged=True,
            preflight_fn=_preflight,
            gateway_factory=lambda _: gateway,
            recorder_factory=recorder_factory,
            clock_fn=clock,
            sleep_fn=clock.sleep,
        )
    receipt = json.loads((output / "execution_receipt.json").read_text())
    assert receipt["status"] == "stopped_safely"
    assert receipt["torque_off_confirmed"]
    assert receipt["physical_follower_torque_enabled"] is False
    assert receipt["counted_physical_attempts"] == 0
    assert gateway.closed

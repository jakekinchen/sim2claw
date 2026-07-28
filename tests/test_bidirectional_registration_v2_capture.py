from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from sim2claw.bidirectional_registration_v2_capture import (
    RegistrationCaptureV2Error,
    _scoring_window,
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
START_BRIDGE_PACKET = (
    ROOT
    / "configs/hardware/"
    "bidirectional_pawn_push_v2_registration_capture_v3.json"
)
EMPIRICAL_V3_PACKET = (
    ROOT
    / "configs/hardware/"
    "bidirectional_pawn_push_v2_registration_capture_v4.json"
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
EMPIRICAL_V3_START = [
    -8.351648351648352,
    -106.1978021978022,
    99.20879120879121,
    -93.84615384615384,
    -125.14285714285714,
    2.375296912114014,
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
    result["follower_start_degrees"] = [
        value + 0.1 for value in RECOVERY_START
    ]
    return result


def _empirical_v3_preflight() -> dict[str, object]:
    result = _preflight()
    result["follower_start_degrees"] = [
        value + 0.1 for value in EMPIRICAL_V3_START
    ]
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
    def __init__(
        self,
        *,
        fail_after: int | None = None,
        start: list[float] | None = None,
    ) -> None:
        self.closed = False
        self.samples = 0
        self.fail_after = fail_after
        self.start = list(start or START)
        self.elapsed_samples: list[float] = []

    def open(self, *, enable_motion: bool, paired_pose_confirmed: bool) -> dict:
        assert enable_motion and paired_pose_confirmed
        return {
            "follower_start_degrees": self.start,
            "follower_registration_degrees": self.start,
            "physical_follower_torque_enabled": True,
            "device_configuration_rewritten": False,
        }

    def sample(
        self, elapsed_seconds: float, *, exact_requested_degrees: np.ndarray
    ) -> dict:
        self.elapsed_samples.append(elapsed_seconds)
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


def _true_time_safety() -> dict[str, object]:
    return {
        "hold_gate_mode": "monotonic_true_time_v1",
        "hold_maximum_rows": 71,
        "hold_maximum_monotonic_seconds": 3.6,
        "hold_minimum_unscored_settle_seconds": 0.5,
        "hold_scoring_seconds": 2.0,
        "joint_hold_tracking_maximum_degrees": 2.0,
    }


def test_true_time_scoring_uses_elapsed_monotonic_time() -> None:
    records = [
        {
            "host_continuous_ns": 1_000_000_000 + index * 50_000_000,
            "tracking_error": (
                [2.5, 0, 0, 0, 0, 0]
                if index < 10
                else [1.5, 0, 0, 0, 0, 0]
            ),
        }
        for index in range(71)
    ]

    scoring, metadata = _scoring_window(
        records,
        safety=_true_time_safety(),
    )

    assert scoring[0] is records[10]
    assert scoring[-1] is records[50]
    assert metadata["unscored_settle_elapsed_seconds"] == pytest.approx(0.5)
    assert metadata["scored_hold_elapsed_seconds"] == pytest.approx(2.0)


def test_true_time_scoring_rejects_nominal_rows_with_short_elapsed_time() -> None:
    records = [
        {
            "host_continuous_ns": 1_000_000_000 + index * 20_000_000,
            "tracking_error": [1.0, 0, 0, 0, 0, 0],
        }
        for index in range(71)
    ]

    with pytest.raises(
        RegistrationCaptureV2Error,
        match="true-time scoring duration",
    ):
        _scoring_window(records, safety=_true_time_safety())


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


def test_start_bridge_review_binds_time_only_bridge_and_unchanged_arrays(
    tmp_path: Path,
) -> None:
    result = review_capture_plan(
        packet_path=START_BRIDGE_PACKET,
        review_path=tmp_path / "review-v3.json",
        preflight_fn=_recovery_preflight,
    )
    bridge = result["live_rebase_setup_bridge"]
    assert bridge == {
        "bridge_id": "v04_acquisition_v2_time_only_pre_row_bridge_v1",
        "pattern": "time_only_pre_row_bridge",
        "duration_seconds": 0.05,
        "command_count": 0,
        "first_frozen_row_elapsed_seconds": 0.05,
        "maximum_live_rebase_delta_degrees": 1.0,
        "maximum_post_hold_to_first_row_delta_degrees": 3.0,
        "sends_no_command": True,
        "changes_frozen_arrays": False,
        "excluded_from_policy_task_and_transfer_evidence": True,
    }
    assert result["exact_setup_arrays"]["source_egress"]["action_sha256"] == (
        "a2536181add1aaf901aac5b94929a5a7117974e571354a68abd94b3a361d4bab"
    )
    assert (
        result["exact_setup_arrays"]["capture_and_return"]["action_sha256"]
        == "06d531afba308c3582cb67972c735bf963c6cae35df365325e36139ba8eac1c2"
    )
    assert result["physical_motion_commanded"] is False
    assert result["camera_opened"] is False
    assert result["gateway_constructed"] is False


def test_empirical_v3_review_binds_exact_new_arrays_without_authority(
    tmp_path: Path,
) -> None:
    result = review_capture_plan(
        packet_path=EMPIRICAL_V3_PACKET,
        review_path=tmp_path / "review-v4.json",
        preflight_fn=_empirical_v3_preflight,
    )
    assert result["reviewer"]["decision"] == "CONTINUE"
    assert all(result["gates"].values())
    assert len(result["capture_slices"]) == 10
    assert result["exact_setup_arrays"]["source_egress"]["shape"] == [715, 6]
    assert result["exact_setup_arrays"]["capture_and_return"]["shape"] == [
        1771,
        6,
    ]
    assert result["physical_motion_commanded"] is False
    assert result["camera_opened"] is False
    assert result["gateway_constructed"] is False


def test_start_bridge_delays_first_exact_row_without_sending_a_prefix_command(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    review = tmp_path / "review-v3.json"
    review_capture_plan(
        packet_path=START_BRIDGE_PACKET,
        review_path=review,
        preflight_fn=_recovery_preflight,
    )
    gateway = _Gateway(
        start=[value + 0.1 for value in RECOVERY_START],
        fail_after=1,
    )

    def recorder_factory(path: Path, **kwargs: object) -> _Recorder:
        return _Recorder(path, clock=clock, **kwargs)

    output = tmp_path / "capture-v3"
    with pytest.raises(RegistrationCaptureV2Error):
        execute_registration_capture(
            packet_path=START_BRIDGE_PACKET,
            review_path=review,
            output_root=output,
            operator_acknowledged=True,
            preflight_fn=_recovery_preflight,
            gateway_factory=lambda _: gateway,
            recorder_factory=recorder_factory,
            clock_fn=clock,
            sleep_fn=clock.sleep,
        )
    receipt = json.loads((output / "execution_receipt.json").read_text())
    bridge = receipt["live_rebase_setup_bridge"]
    assert gateway.samples == 1
    assert gateway.elapsed_samples[0] == pytest.approx(0.05)
    assert bridge["actual_duration_seconds"] == pytest.approx(0.05)
    assert bridge["actual_command_count"] == 0
    assert bridge["post_hold_to_first_row_maximum_delta_degrees"] == pytest.approx(
        0.1
    )
    assert receipt["source_egress"]["executed_sample_count"] == 1
    assert receipt["capture_and_return"]["executed_sample_count"] == 0
    assert receipt["torque_off_confirmed"]


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

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from sim2claw.parking_transaction_executor import (
    ParkingTransactionExecutionError,
    _require_frozen_output_root,
    load_packet,
    run_deep_request_ladder,
    run_ladder,
)


ROOT = Path(__file__).resolve().parents[1]


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += max(0.0, seconds)


class _Camera:
    def __init__(self, *, fail_after: int | None = None) -> None:
        self.checks = 0
        self.fail_after = fail_after

    def ensure_running(self) -> None:
        self.checks += 1
        if self.fail_after is not None and self.checks > self.fail_after:
            raise RuntimeError("camera stopped")


class _Gateway:
    def __init__(
        self,
        anchor: np.ndarray,
        *,
        motion_per_sample: float,
        elbow_floor: float | None = None,
        held_drift: float = 0.0,
    ) -> None:
        self.actual = anchor.copy()
        self.motion_per_sample = motion_per_sample
        self.elbow_floor = elbow_floor
        self.held_drift = held_drift

    def sample(
        self, elapsed: float, *, exact_requested_degrees: np.ndarray
    ) -> dict[str, Any]:
        del elapsed
        delta = float(exact_requested_degrees[2] - self.actual[2])
        self.actual[2] += np.clip(
            delta, -self.motion_per_sample, self.motion_per_sample
        )
        if self.elbow_floor is not None:
            self.actual[2] = max(self.actual[2], self.elbow_floor)
        self.actual[0] += self.held_drift
        return {
            "precompiled_exact_action": True,
            "rate_limited": False,
            "safety_clamped": False,
            "physical_follower_torque_enabled": True,
            "follower_actual_position_degrees": self.actual.tolist(),
        }

    def _read_optional(self, register: str) -> dict[str, float]:
        return {"elbow_flex": 1.0, "register": float(len(register))}


def _packet() -> dict[str, Any]:
    return {
        "runtime": {
            "target_degrees": 91.0,
            "maximum_request_step_degrees": 5.0,
            "maximum_iterations": 12,
            "wait_after_request_seconds": 2.0,
            "telemetry_hz": 5.0,
            "primary_success_maximum_degrees": 92.0,
            "marginal_success_maximum_degrees": 93.0,
            "stall_minimum_progress_degrees": 0.3,
            "stall_consecutive_iterations": 2,
            "held_joint_rebase_maximum_degrees": 0.5,
            "elbow_rebase_maximum_degrees": 1.0,
            "held_joint_drift_stop_degrees": 2.0,
            "hold_seconds": 15.0,
            "maximum_hold_drift_degrees": 0.5,
            "post_torque_off_read_seconds": 60.0,
        }
    }


def test_frozen_packet_requires_separate_owner_authorization() -> None:
    packet = load_packet(
        ROOT / "configs/hardware/parking_transaction_execution_v4.json"
    )
    assert packet["physical_authority"] is False
    assert packet["owner_authorization"]["currently_bound"] is False
    assert packet["physical_task_attempt"] is False
    assert packet["retry_without_new_preregistration"] is False
    assert packet["camera"]["d405_required"] is False


def test_one_execution_latch_rejects_any_other_output_path(
    tmp_path: Path,
) -> None:
    packet = load_packet(
        ROOT / "configs/hardware/parking_transaction_execution_v4.json"
    )
    with pytest.raises(
        ParkingTransactionExecutionError, match="one-execution path"
    ):
        _require_frozen_output_root(packet, tmp_path / "alternate")


def test_read_conditioned_ladder_reaches_primary_without_task_attempt() -> None:
    anchor = np.asarray([5, -85, 99.47, -15, -103, 2], dtype=float)
    clock = _Clock()
    camera = _Camera()
    report = run_ladder(
        gateway=_Gateway(anchor, motion_per_sample=0.2),
        camera=camera,
        anchor=anchor,
        packet=_packet(),
        telemetry=io.StringIO(),
        clock=clock,
        sleep=clock.sleep,
    )
    assert report["outcome"] == "primary_success"
    assert report["final_elbow_degrees"] <= 92.0
    assert report["hold"]["passed"] is True
    assert report["terminal_above_93_degrees"] is False
    assert camera.checks > 0
    for row in report["iterations"]:
        assert row["previous_read_degrees"] - row["requested_degrees"] <= 5.0


def test_clock_compatible_successor_primes_anchor_and_spaces_new_targets() -> None:
    class _ExactGateway(_Gateway):
        def __init__(self, anchor: np.ndarray) -> None:
            super().__init__(anchor, motion_per_sample=0.5)
            self.previous_request = anchor.copy()
            self.previous_elapsed = 0.0
            self.requests: list[tuple[float, np.ndarray]] = []

        def sample(
            self, elapsed: float, *, exact_requested_degrees: np.ndarray
        ) -> dict[str, Any]:
            allowed = 60.0 * min(
                max(0.0, elapsed - self.previous_elapsed), 0.1
            )
            assert np.max(
                np.abs(exact_requested_degrees - self.previous_request)
            ) <= allowed + 1e-12
            self.requests.append((elapsed, exact_requested_degrees.copy()))
            self.previous_request = exact_requested_degrees.copy()
            self.previous_elapsed = elapsed
            return super().sample(
                elapsed, exact_requested_degrees=exact_requested_degrees
            )

    anchor = np.asarray([5, -85, 99.47, -15, -103, 2], dtype=float)
    packet = _packet()
    packet["runtime"].update(
        {
            "clock_establishing_anchor_samples": 1,
            "new_target_lead_periods": 1,
        }
    )
    clock = _Clock()
    gateway = _ExactGateway(anchor)
    report = run_ladder(
        gateway=gateway,
        camera=_Camera(),
        anchor=anchor,
        packet=packet,
        telemetry=io.StringIO(),
        clock=clock,
        sleep=clock.sleep,
    )
    assert report["outcome"] == "primary_success"
    assert gateway.requests[0][0] == 0.0
    assert np.array_equal(gateway.requests[0][1], anchor)
    assert gateway.requests[1][0] == pytest.approx(0.2)
    assert gateway.requests[1][1][2] == pytest.approx(94.47)


def test_deep_request_reaches_band_and_holds_with_bounded_bias() -> None:
    class _BiasedGateway(_Gateway):
        def sample(
            self, elapsed: float, *, exact_requested_degrees: np.ndarray
        ) -> dict[str, Any]:
            del elapsed
            equilibrium = float(exact_requested_degrees[2]) + 3.9
            self.actual[2] += 0.3 * (equilibrium - self.actual[2])
            return {
                "precompiled_exact_action": True,
                "rate_limited": False,
                "safety_clamped": False,
                "physical_follower_torque_enabled": True,
                "follower_actual_position_degrees": self.actual.tolist(),
            }

    anchor = np.asarray([5, -85, 99.47, -15, -103, 2], dtype=float)
    packet = {
        "runtime": {
            "success_minimum_degrees": 88.0,
            "success_maximum_degrees": 93.0,
            "initial_request_floor_degrees": 86.0,
            "deepened_request_floor_degrees": 82.0,
            "maximum_request_step_degrees": 5.0,
            "maximum_iterations": 16,
            "wait_after_request_seconds": 2.0,
            "telemetry_hz": 5.0,
            "stall_minimum_progress_degrees": 0.3,
            "stall_consecutive_iterations_before_deepen": 2,
            "stall_consecutive_iterations_after_deepen": 2,
            "hold_seconds": 15.0,
            "maximum_hold_drift_degrees": 0.5,
            "hold_deep_segment_seconds": 4.0,
            "hold_reset_segment_seconds": 0.2,
            "hold_reset_error_degrees": 2.9,
            "maximum_elbow_current_raw": 150.0,
            "maximum_current_duration_seconds": 1.0,
            "maximum_temperature_c": 45.0,
            "clock_establishing_anchor_samples": 1,
            "new_target_lead_periods": 1,
        }
    }
    clock = _Clock()
    report = run_deep_request_ladder(
        gateway=_BiasedGateway(anchor, motion_per_sample=0.0),
        camera=_Camera(),
        anchor=anchor,
        packet=packet,
        telemetry=io.StringIO(),
        clock=clock,
        sleep=clock.sleep,
    )
    assert report["outcome"] == "deep_request_success"
    assert 88.0 <= report["final_elbow_degrees"] <= 93.0
    assert report["hold"]["passed"] is True


def test_two_no_progress_intervals_stop_safely_above_93() -> None:
    anchor = np.asarray([5, -85, 99.47, -15, -103, 2], dtype=float)
    clock = _Clock()
    report = run_ladder(
        gateway=_Gateway(anchor, motion_per_sample=0.0),
        camera=_Camera(),
        anchor=anchor,
        packet=_packet(),
        telemetry=io.StringIO(),
        clock=clock,
        sleep=clock.sleep,
    )
    assert report["outcome"] == "stall_safe_stop"
    assert len(report["iterations"]) == 2
    assert report["terminal_above_93_degrees"] is True
    assert report["hold"] is None


def test_stall_inside_certificate_band_runs_hold_and_is_marginal() -> None:
    anchor = np.asarray([5, -85, 99.47, -15, -103, 2], dtype=float)
    clock = _Clock()
    report = run_ladder(
        gateway=_Gateway(
            anchor, motion_per_sample=0.2, elbow_floor=92.5
        ),
        camera=_Camera(),
        anchor=anchor,
        packet=_packet(),
        telemetry=io.StringIO(),
        clock=clock,
        sleep=clock.sleep,
    )
    assert report["outcome"] == "marginal_success_after_stall"
    assert report["final_elbow_degrees"] == 92.5
    assert report["hold"]["passed"] is True
    assert report["terminal_above_93_degrees"] is False


def test_held_joint_drift_stops_before_next_sample() -> None:
    anchor = np.asarray([5, -85, 99.47, -15, -103, 2], dtype=float)
    clock = _Clock()
    with pytest.raises(
        ParkingTransactionExecutionError, match="held non-elbow"
    ):
        run_ladder(
            gateway=_Gateway(
                anchor, motion_per_sample=0.2, held_drift=2.1
            ),
            camera=_Camera(),
            anchor=anchor,
            packet=_packet(),
            telemetry=io.StringIO(),
            clock=clock,
            sleep=clock.sleep,
        )


def test_camera_loss_stops_mid_ladder() -> None:
    anchor = np.asarray([5, -85, 99.47, -15, -103, 2], dtype=float)
    clock = _Clock()
    with pytest.raises(RuntimeError, match="camera stopped"):
        run_ladder(
            gateway=_Gateway(anchor, motion_per_sample=0.2),
            camera=_Camera(fail_after=3),
            anchor=anchor,
            packet=_packet(),
            telemetry=io.StringIO(),
            clock=clock,
            sleep=clock.sleep,
        )


def test_hold_drift_failure_is_fail_closed() -> None:
    class _HoldDriftGateway(_Gateway):
        def __init__(self, anchor: np.ndarray) -> None:
            super().__init__(anchor, motion_per_sample=0.0)
            self.sample_index = 0

        def sample(
            self, elapsed: float, *, exact_requested_degrees: np.ndarray
        ) -> dict[str, Any]:
            del elapsed, exact_requested_degrees
            self.sample_index += 1
            if self.sample_index <= 33:
                fraction = self.sample_index / 33.0
                self.actual[2] = 99.47 + (91.8 - 99.47) * fraction
            else:
                self.actual[2] += 0.2
            return {
                "precompiled_exact_action": True,
                "rate_limited": False,
                "safety_clamped": False,
                "physical_follower_torque_enabled": True,
                "follower_actual_position_degrees": self.actual.tolist(),
            }

    anchor = np.asarray([5, -85, 99.47, -15, -103, 2], dtype=float)
    clock = _Clock()
    with pytest.raises(
        ParkingTransactionExecutionError, match="hold drift"
    ):
        run_ladder(
            gateway=_HoldDriftGateway(anchor),
            camera=_Camera(),
            anchor=anchor,
            packet=_packet(),
            telemetry=io.StringIO(),
            clock=clock,
            sleep=clock.sleep,
        )

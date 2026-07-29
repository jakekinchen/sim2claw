from __future__ import annotations

import io
from typing import Any

import numpy as np

from pathlib import Path

from sim2claw.parking_transaction_executor import load_packet, run_ladder


ROOT = Path(__file__).resolve().parents[1]


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += max(0.0, seconds)


class _Camera:
    def __init__(self) -> None:
        self.checks = 0

    def ensure_running(self) -> None:
        self.checks += 1


class _Gateway:
    def __init__(self, anchor: np.ndarray, *, motion_per_sample: float) -> None:
        self.actual = anchor.copy()
        self.motion_per_sample = motion_per_sample

    def sample(
        self, elapsed: float, *, exact_requested_degrees: np.ndarray
    ) -> dict[str, Any]:
        del elapsed
        delta = float(exact_requested_degrees[2] - self.actual[2])
        self.actual[2] += np.clip(
            delta, -self.motion_per_sample, self.motion_per_sample
        )
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
        ROOT / "configs/hardware/parking_transaction_execution_v1.json"
    )
    assert packet["physical_authority"] is False
    assert packet["owner_authorization"]["currently_bound"] is False
    assert packet["physical_task_attempt"] is False
    assert packet["retry_without_new_preregistration"] is False
    assert packet["camera"]["d405_required"] is False


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

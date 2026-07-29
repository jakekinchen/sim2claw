from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from sim2claw.full_range_no_contact_execution import _load_packet, execute
from sim2claw.full_range_no_contact_execution_v2 import (
    _load_packet as _load_packet_v2,
    execute as execute_v2,
)


ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "configs/hardware/full_range_no_contact_execution_v1.json"
PACKET_V2 = (
    ROOT / "configs/hardware/full_range_no_contact_execution_v2.json"
)


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += max(0.0, seconds)


class FakeLeader:
    def __init__(self, target: np.ndarray) -> None:
        self.target = target.copy()

    def set_target(self, target: np.ndarray) -> None:
        self.target = target.copy()


class FakeGateway:
    def __init__(self, start: np.ndarray) -> None:
        self.leader = FakeLeader(start)
        self.actual = start.copy()
        self.closed = False

    def open(
        self, *, enable_motion: bool, paired_pose_confirmed: bool
    ) -> dict[str, Any]:
        assert enable_motion is True
        assert paired_pose_confirmed is True
        return {
            "leader_start_degrees": self.actual.tolist(),
            "follower_start_degrees": self.actual.tolist(),
        }

    def sample(self, elapsed_seconds: float) -> dict[str, Any]:
        del elapsed_seconds
        self.actual = self.leader.target.copy()
        return {
            "follower_command_degrees": self.actual.tolist(),
            "follower_actual_position_degrees": self.actual.tolist(),
            "safety_clamped": False,
        }

    def rebase_relative_origin(
        self, *, leader_origin: np.ndarray, follower_origin: np.ndarray
    ) -> dict[str, Any]:
        self.leader.target = leader_origin.copy()
        self.actual = follower_origin.copy()
        return {
            "control_mode": "fake_rebase",
            "leader_origin_degrees": leader_origin.tolist(),
            "follower_origin_degrees": follower_origin.tolist(),
        }

    def close(self) -> None:
        self.closed = True


class FakeCamera:
    def start(self) -> dict[str, Any]:
        return {"status": "started"}

    def ensure_running(self) -> None:
        return None

    def finish(
        self,
        *,
        action_started_monotonic: float | None,
        action_stopped_monotonic: float | None,
        post_roll_seconds: float,
    ) -> dict[str, Any]:
        assert action_started_monotonic is not None
        assert action_stopped_monotonic is not None
        assert post_roll_seconds == 0.0
        return {"status": "completed"}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_packet_loads_exact_full_range_route() -> None:
    packet, route = _load_packet(PACKET)
    assert route.shape == (1160, 6)
    assert packet["execution"]["segment_boundaries"] == [
        0,
        61,
        122,
        555,
        1159,
    ]
    assert packet["physical_task_attempt"] is False
    assert packet["pawn_contact"] is False


def test_synthetic_execution_runs_forward_reverse_and_torque_off(
    tmp_path: Path,
) -> None:
    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    output = tmp_path / "execution"
    packet["output_directory"] = str(output)
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    now = datetime.now(UTC)
    authorization = {
        "schema_version": "sim2claw.owner_physical_authorization.v1",
        "authorization_id": "test-rp04c",
        "operation_id": packet["operation_id"],
        "packet_sha256": _sha(packet_path),
        "issued_at": (now - timedelta(minutes=1)).isoformat(),
        "expires_at": (now + timedelta(minutes=10)).isoformat(),
        "maximum_executions": 1,
        "physical_no_contact_diagnostic": True,
        "physical_task_attempt": False,
        "pawn_contact": False,
        "autonomous_agent_supervision": True,
        "power_down_supply_on_torque_cleanup_error": True,
    }
    authorization_path = tmp_path / "authorization.json"
    authorization_path.write_text(json.dumps(authorization), encoding="utf-8")
    _, route = _load_packet(packet_path)
    start = route[0]
    preflight = {
        "passed": True,
        "physical_follower_torque_enabled": False,
        "device_configuration_rewritten": False,
        "leader_port": "/dev/test-leader",
        "follower_port": packet["hardware"]["follower_port"],
        "leader_calibration_sha256": "leader",
        "follower_calibration_sha256": packet["hardware"][
            "follower_calibration_sha256"
        ],
        "follower_start_degrees": start.tolist(),
    }
    clock = FakeClock()
    gateway = FakeGateway(start)
    receipt = execute(
        packet_path=packet_path,
        authorization_path=authorization_path,
        output_root=output,
        operator_acknowledged=True,
        preflight_fn=lambda: preflight,
        gateway_factory=lambda _identity: gateway,
        camera_factory=lambda _root, _packet: FakeCamera(),
        clock=clock,
        sleep=clock.sleep,
    )
    assert receipt["telemetry_acceptance_passed"] is True
    assert receipt["forward_source_sample_count"] == 1160
    assert receipt["minimum_observed_elbow_degrees"] <= -10.4
    assert len(receipt["boundary_reports"]) == 9
    assert receipt["physical_task_attempts"] == 0
    assert gateway.closed is True


def test_reachable_pan_packet_runs_exact_v2_denominator(
    tmp_path: Path,
) -> None:
    packet = json.loads(PACKET_V2.read_text(encoding="utf-8"))
    output = tmp_path / "execution-v2"
    packet["output_directory"] = str(output)
    packet_path = tmp_path / "packet-v2.json"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    now = datetime.now(UTC)
    authorization = {
        "schema_version": "sim2claw.owner_physical_authorization.v1",
        "authorization_id": "test-rp04c-v2",
        "operation_id": packet["operation_id"],
        "packet_sha256": _sha(packet_path),
        "issued_at": (now - timedelta(minutes=1)).isoformat(),
        "expires_at": (now + timedelta(minutes=10)).isoformat(),
        "maximum_executions": 1,
        "physical_no_contact_diagnostic": True,
        "physical_task_attempt": False,
        "pawn_contact": False,
        "autonomous_agent_supervision": True,
        "power_down_supply_on_torque_cleanup_error": True,
    }
    authorization_path = tmp_path / "authorization-v2.json"
    authorization_path.write_text(json.dumps(authorization), encoding="utf-8")
    _, route = _load_packet_v2(packet_path)
    assert route.shape == (1105, 6)
    start = route[0]
    preflight = {
        "passed": True,
        "physical_follower_torque_enabled": False,
        "device_configuration_rewritten": False,
        "leader_port": "/dev/test-leader",
        "follower_port": packet["hardware"]["follower_port"],
        "leader_calibration_sha256": "leader",
        "follower_calibration_sha256": packet["hardware"][
            "follower_calibration_sha256"
        ],
        "follower_start_degrees": start.tolist(),
    }
    clock = FakeClock()
    gateway = FakeGateway(start)
    receipt = execute_v2(
        packet_path=packet_path,
        authorization_path=authorization_path,
        output_root=output,
        operator_acknowledged=True,
        preflight_fn=lambda: preflight,
        gateway_factory=lambda _identity: gateway,
        camera_factory=lambda _root, _packet: FakeCamera(),
        clock=clock,
        sleep=clock.sleep,
    )
    assert receipt["telemetry_acceptance_passed"] is True
    assert receipt["forward_source_sample_count"] == 1105
    assert receipt["minimum_observed_elbow_degrees"] <= -10.4
    assert len(receipt["boundary_reports"]) == 9
    assert receipt["physical_task_attempts"] == 0
    assert gateway.closed is True

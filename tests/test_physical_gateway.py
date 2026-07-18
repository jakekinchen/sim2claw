from __future__ import annotations

import unittest
from typing import Any

import numpy as np

from sim2claw.physical_gateway import (
    BODY_EXCURSION_LIMIT_DEG,
    GATEWAY_SCHEMA,
    GRIPPER_EXCURSION_LIMIT,
    MAX_CONSECUTIVE_STALL_SAMPLES,
    STALL_TIMEOUT_SECONDS,
    WRIST_ROLL_EXCURSION_LIMIT_DEG,
    GatewayIdentity,
    PhysicalGatewayError,
    SO101PhysicalGateway,
    bounded_relative_target,
    inspect_physical_gateway,
    synchronize_physical_gateway,
)
from sim2claw.scene import ROBOT_JOINTS


class FakeBus:
    def __init__(self) -> None:
        self.is_connected = False
        self.torque = False
        self.disable_calls = 0
        self.disconnect_calls = 0

    def connect(self) -> None:
        self.is_connected = True

    def disable_torque(self) -> None:
        self.torque = False
        self.disable_calls += 1

    def enable_torque(self) -> None:
        self.torque = True

    def disconnect(self, _disable_torque: bool = True) -> None:
        self.torque = False
        self.is_connected = False
        self.disconnect_calls += 1

    def sync_read(self, register: str) -> dict[str, float]:
        if register == "Torque_Enable":
            return {joint: float(self.torque) for joint in ROBOT_JOINTS}
        if register == "Present_Current":
            return {joint: 0.0 for joint in ROBOT_JOINTS}
        raise KeyError(register)


def _action(values: np.ndarray) -> dict[str, float]:
    return {
        f"{joint}.pos": float(value)
        for joint, value in zip(ROBOT_JOINTS, values, strict=True)
    }


class FakeLeader:
    def __init__(self, values: np.ndarray, *, calibrated: bool = True) -> None:
        self.bus = FakeBus()
        self.values = values
        self.is_calibrated = calibrated

    def configure(self) -> None:
        self.bus.disable_torque()

    def get_action(self) -> dict[str, float]:
        return _action(self.values)


class FakeFollower:
    def __init__(self, values: np.ndarray, *, calibrated: bool = True) -> None:
        self.bus = FakeBus()
        self.values = values
        self.is_calibrated = calibrated
        self.frozen = False
        self.frozen_indices: set[int] = set()

    def configure(self) -> None:
        self.bus.disable_torque()

    def get_observation(self) -> dict[str, float]:
        return _action(self.values)

    def send_action(self, action: dict[str, float]) -> dict[str, float]:
        requested = np.asarray(
            [action[f"{joint}.pos"] for joint in ROBOT_JOINTS],
            dtype=np.float64,
        )
        step = np.clip(requested - self.values, -2.0, 2.0)
        sent = self.values + step
        if self.bus.torque and not self.frozen:
            movable = sent.copy()
            for index in self.frozen_indices:
                movable[index] = self.values[index]
            self.values = movable
        return _action(sent)


class PhysicalGatewayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.leader = FakeLeader(np.zeros(6, dtype=np.float64))
        self.follower = FakeFollower(np.asarray([5, 4, 3, 2, 1, 5], dtype=np.float64))
        self.identity = GatewayIdentity(
            leader_port="leader",
            follower_port="follower",
            leader_calibration_sha256="a" * 64,
            follower_calibration_sha256="b" * 64,
        )

    def factory(self, _identity: GatewayIdentity) -> tuple[Any, Any]:
        return self.leader, self.follower

    def test_relative_target_preserves_follower_start_and_bounds_motion(self) -> None:
        leader = np.asarray([40, -20, 4, 3, 179, 40], dtype=np.float64)
        leader_start = np.asarray([0, 0, 0, 0, -179, 10], dtype=np.float64)
        follower_start = np.asarray([5, 4, 3, 2, 1, 20], dtype=np.float64)
        target, delta = bounded_relative_target(leader, leader_start, follower_start)
        self.assertTrue(np.all(np.abs(delta[:4]) <= BODY_EXCURSION_LIMIT_DEG))
        self.assertLessEqual(abs(delta[4]), WRIST_ROLL_EXCURSION_LIMIT_DEG)
        self.assertEqual(delta[4], -2.0)
        self.assertEqual(delta[5], min(30.0, GRIPPER_EXCURSION_LIMIT))
        np.testing.assert_allclose(target, follower_start + delta)

    def test_relative_target_respects_follower_calibrated_limits(self) -> None:
        target, delta = bounded_relative_target(
            np.asarray([100, 0, 0, 0, 0, 100], dtype=np.float64),
            np.zeros(6, dtype=np.float64),
            np.zeros(6, dtype=np.float64),
            lower_limits=np.asarray([-30, -40, -50, -60, -180, 0], dtype=np.float64),
            upper_limits=np.asarray([30, 40, 50, 60, 180, 100], dtype=np.float64),
        )
        self.assertEqual(target[0], 30.0)
        self.assertEqual(delta[0], 30.0)

    def test_open_sample_and_close_own_follower_torque(self) -> None:
        gateway = SO101PhysicalGateway(self.identity, device_factory=self.factory)
        opened = gateway.open(enable_motion=True, paired_pose_confirmed=True)
        self.assertEqual(opened["schema_version"], GATEWAY_SCHEMA)
        self.assertTrue(opened["physical_follower_torque_enabled"])
        self.assertTrue(opened["paired_pose_registered_before_recording"])
        self.assertFalse(opened["start_alignment_motion_commanded"])
        self.assertTrue(self.follower.bus.torque)
        self.assertFalse(self.leader.bus.torque)
        self.leader.values[:] = [20, 0, 0, 0, 0, 0]
        sample = gateway.sample(0.1)
        self.assertTrue(sample["safety_clamped"])
        self.assertEqual(sample["leader_relative_delta"][0], 20.0)
        gateway.close()
        self.assertFalse(self.follower.bus.torque)
        self.assertFalse(self.follower.bus.is_connected)
        self.assertFalse(self.leader.bus.is_connected)

    def test_rate_limited_motion_does_not_fail_while_follower_advances(self) -> None:
        gateway = SO101PhysicalGateway(self.identity, device_factory=self.factory)
        gateway.open(enable_motion=True, paired_pose_confirmed=True)
        for index in range(MAX_CONSECUTIVE_STALL_SAMPLES + 5):
            self.leader.values[0] = 10.0 if index % 2 == 0 else -10.0
            sample = gateway.sample(index / 20)
            self.assertTrue(sample["rate_limited"])
            self.assertFalse(sample["stalled"])
        gateway.close()
        self.assertFalse(self.follower.bus.torque)

    def test_repeated_stall_samples_fail_closed(self) -> None:
        gateway = SO101PhysicalGateway(self.identity, device_factory=self.factory)
        gateway.open(enable_motion=True, paired_pose_confirmed=True)
        self.follower.frozen = True
        self.leader.values[0] = 20.0
        with self.assertRaisesRegex(PhysicalGatewayError, "no measurable progress"):
            for index in range(MAX_CONSECUTIVE_STALL_SAMPLES + 1):
                gateway.sample(index / 20)
        gateway.close()
        self.assertFalse(self.follower.bus.torque)

    def test_one_stalled_joint_is_not_hidden_by_another_advancing_joint(self) -> None:
        gateway = SO101PhysicalGateway(self.identity, device_factory=self.factory)
        gateway.open(enable_motion=True, paired_pose_confirmed=True)
        self.follower.frozen_indices.add(0)
        self.leader.values[:2] = 20.0
        with self.assertRaisesRegex(PhysicalGatewayError, "no measurable progress"):
            for index in range(MAX_CONSECUTIVE_STALL_SAMPLES + 1):
                gateway.sample(index / 20)
        gateway.close()
        self.assertFalse(self.follower.bus.torque)

    def test_torque_off_inspection_never_arms_follower(self) -> None:
        report = inspect_physical_gateway(self.identity, device_factory=self.factory)
        self.assertTrue(report["passed"])
        self.assertFalse(report["physical_follower_torque_enabled"])
        self.assertTrue(report["paired_pose_registration_ready"])
        self.assertFalse(self.follower.bus.torque)

    def test_large_starting_mismatch_blocks_registration_before_torque(self) -> None:
        self.follower.values[1] = 90.0
        gateway = SO101PhysicalGateway(self.identity, device_factory=self.factory)
        with self.assertRaisesRegex(PhysicalGatewayError, "outside the calibration-offset"):
            gateway.open(enable_motion=True, paired_pose_confirmed=True)
        self.assertFalse(self.follower.bus.torque)
        gateway.close()

    def test_paired_pose_registration_holds_follower_and_maps_relative_motion(self) -> None:
        self.leader.values[:] = [4, -3, 8, 2, 1, 5]
        self.follower.values[:] = [-4, -11, 0, -6, -7, 5]
        follower_before = self.follower.values.copy()
        gateway = SO101PhysicalGateway(self.identity, device_factory=self.factory)
        opened = gateway.open(enable_motion=True, paired_pose_confirmed=True)
        np.testing.assert_allclose(self.follower.values, follower_before)
        np.testing.assert_allclose(
            opened["leader_to_follower_zero_offset_degrees"],
            follower_before - self.leader.values,
        )
        self.leader.values[0] += 1.5
        sample = gateway.sample(0.1)
        self.assertAlmostEqual(sample["follower_requested_degrees"][0], -2.5)
        gateway.close()

    def test_calibration_mismatch_disconnects_torque_off(self) -> None:
        self.follower.is_calibrated = False
        gateway = SO101PhysicalGateway(self.identity, device_factory=self.factory)
        with self.assertRaisesRegex(PhysicalGatewayError, "Follower calibration"):
            gateway.open(enable_motion=True)
        self.assertFalse(self.follower.bus.torque)
        self.assertFalse(self.follower.bus.is_connected)

    def test_nearby_sync_ramps_follower_to_leader_and_finishes_torque_off(self) -> None:
        report = synchronize_physical_gateway(
            self.identity,
            device_factory=self.factory,
            sleep=lambda _seconds: None,
        )
        self.assertTrue(report["passed"])
        self.assertTrue(report["sync_completed_torque_off"])
        self.assertLessEqual(report["maximum_sync_residual_degrees"], 3.0)
        self.assertFalse(report["physical_follower_torque_enabled"])
        self.assertFalse(self.follower.bus.torque)

    def test_sync_refuses_large_pose_mismatch_before_torque(self) -> None:
        self.follower.values[1] = STALL_TIMEOUT_SECONDS * 10
        with self.assertRaisesRegex(PhysicalGatewayError, "roughly the same pose"):
            synchronize_physical_gateway(
                self.identity,
                device_factory=self.factory,
                sleep=lambda _seconds: None,
            )
        self.assertFalse(self.follower.bus.torque)


if __name__ == "__main__":
    unittest.main()

from unittest.mock import Mock

import pytest

from sim2claw.physical_gateway import GatewayIdentity, PhysicalGatewayError, SO101PhysicalGateway
from sim2claw.scene import ROBOT_JOINTS


def setup_probe():
    follower = Mock()
    follower.calibration = {j: {"range_min": 800, "range_max": 3100} for j in ROBOT_JOINTS}
    bus = follower.bus
    bus.sync_read.return_value = {j: 0 for j in ROBOT_JOINTS}
    bus.read.side_effect = [3022, 3022, 0]
    gateway = SO101PhysicalGateway(
        GatewayIdentity("source", "follower", "a" * 64, "b" * 64),
        device_factory=lambda _: (Mock(), follower), sleep=Mock(), configure_devices=False,
    )
    gateway.connected = True
    return gateway, bus


def test_probe_sends_exact_fresh_raw_position_only_once():
    gateway, bus = setup_probe()
    receipt = gateway.probe_stationary_joint_goal("elbow_flex")
    bus.write.assert_called_once_with("Goal_Position", "elbow_flex", 3022, normalize=False, num_retry=0)
    bus.enable_torque.assert_not_called()
    assert receipt["target_raw"] == 3022
    assert gateway.goal_write_may_have_armed
    assert not gateway.torque_enabled  # A single goal does not arm the full chain.
    with pytest.raises(PhysicalGatewayError):
        gateway.sample_read_only()


@pytest.mark.parametrize("values", [{}, {j: 1 for j in ROBOT_JOINTS}, {j: float("nan") for j in ROBOT_JOINTS}])
def test_probe_requires_complete_zero_state(values):
    gateway, bus = setup_probe()
    bus.sync_read.return_value = values
    with pytest.raises(PhysicalGatewayError):
        gateway.probe_stationary_joint_goal("elbow_flex")
    bus.write.assert_not_called()


@pytest.mark.parametrize("reads", [[3022, 3025, 0], [3022, float("nan"), 0], [3101, 3101, 0], [3022, 3022.5, 0], [3022, 3022, 1]])
def test_probe_rejects_changed_or_invalid_position_and_late_torque(reads):
    gateway, bus = setup_probe()
    bus.read.side_effect = reads
    with pytest.raises(PhysicalGatewayError):
        gateway.probe_stationary_joint_goal("elbow_flex")
    bus.write.assert_not_called()


@pytest.mark.parametrize("field,value", [("connected", False), ("torque_enabled", True)])
def test_probe_requires_off_session(field, value):
    gateway, bus = setup_probe()
    setattr(gateway, field, value)
    with pytest.raises(PhysicalGatewayError):
        gateway.probe_stationary_joint_goal("elbow_flex")
    bus.write.assert_not_called()


def test_probe_never_retries_uncertain_write():
    gateway, bus = setup_probe()
    bus.write.side_effect = ConnectionError("missing acknowledgement")
    with pytest.raises(ConnectionError):
        gateway.probe_stationary_joint_goal("elbow_flex")
    assert bus.write.call_count == 1
    bus.enable_torque.assert_not_called()
    assert gateway.goal_write_may_have_armed
    with pytest.raises(PhysicalGatewayError):
        gateway.sample_read_only()


def test_uncertain_group_goal_also_disallows_read_only_label():
    gateway, bus = setup_probe()
    gateway.position_write_mode = "acknowledged_unicast"
    bus.write.side_effect = ConnectionError("uncertain goal")
    with pytest.raises(ConnectionError):
        gateway._send_follower_action({f"{j}.pos": 0 for j in ROBOT_JOINTS})
    assert gateway.goal_write_may_have_armed
    with pytest.raises(PhysicalGatewayError):
        gateway.sample_read_only()


@pytest.mark.parametrize("offset", [-6, 6])
def test_full_chain_offset_sends_one_low_output_goal(offset):
    gateway, bus = setup_probe()
    bus.read.side_effect = [3022, 3022, 50, 0]
    r = gateway.probe_stationary_joint_goal("elbow_flex", goal_offset_raw=offset)
    bus.write.assert_called_once_with("Goal_Position", "elbow_flex", 3022+offset,
                                     normalize=False, num_retry=0)
    assert r["anchor_raw"] == 3022 and r["requested_offset_raw"] == offset
    assert gateway.goal_write_may_have_armed and not gateway.torque_enabled
    bus.enable_torque.assert_not_called()


@pytest.mark.parametrize("offset", [-7, 7, True, 0.5])
def test_full_chain_offset_rejects_unapproved_size(offset):
    gateway, bus = setup_probe()
    with pytest.raises(PhysicalGatewayError):
        gateway.probe_stationary_joint_goal("elbow_flex", goal_offset_raw=offset)
    bus.write.assert_not_called()


@pytest.mark.parametrize("reads", [[3098, 3098, 50, 0], [3022, 3022, 1000, 0], [3022, 3022, 50, 1]])
def test_full_chain_offset_rejects_boundary_high_output_and_late_activation(reads):
    gateway, bus = setup_probe()
    bus.read.side_effect = reads
    with pytest.raises(PhysicalGatewayError):
        gateway.probe_stationary_joint_goal("elbow_flex", goal_offset_raw=6)
    bus.write.assert_not_called()


def test_full_chain_offset_never_retries_uncertain_goal():
    gateway, bus = setup_probe()
    bus.read.side_effect = [3022, 3022, 50, 0]
    bus.write.side_effect = ConnectionError("missing acknowledgement")
    with pytest.raises(ConnectionError):
        gateway.probe_stationary_joint_goal("elbow_flex", goal_offset_raw=-6)
    assert bus.write.call_count == 1 and gateway.goal_write_may_have_armed
    bus.enable_torque.assert_not_called()


def test_slow_start_uses_one_vendor_layout_transaction():
    gateway, bus = setup_probe()
    bus.read.side_effect = [3022, 3022, 50, 0]
    bus.motors = {"elbow_flex": Mock(id=3)}
    bus.packet_handler.writeTxRx.return_value = (0, 0)
    r = gateway.probe_stationary_joint_goal("elbow_flex", goal_offset_raw=-6, slow_start=True)
    bus.packet_handler.writeTxRx.assert_called_once_with(bus.port_handler, 3, 41, 7,
                                                       [1, 200, 11, 0, 0, 1, 0])
    bus.write.assert_not_called()
    assert gateway.goal_write_may_have_armed and r["target_raw"] == 3016
    assert r["slow_start_profile"]["goal_velocity_raw"] == 1


@pytest.mark.parametrize("reply", [(-6, 0), (0, 1)])
def test_slow_start_uncertain_ack_is_not_retried(reply):
    gateway, bus = setup_probe()
    bus.read.side_effect = [3022, 3022, 50, 0]
    bus.motors = {"elbow_flex": Mock(id=3)}
    bus.packet_handler.writeTxRx.return_value = reply
    with pytest.raises(PhysicalGatewayError):
        gateway.probe_stationary_joint_goal("elbow_flex", goal_offset_raw=-6, slow_start=True)
    assert bus.packet_handler.writeTxRx.call_count == 1 and gateway.goal_write_may_have_armed
    bus.write.assert_not_called()


def test_slow_start_requires_nonzero_small_offset():
    gateway, bus = setup_probe()
    with pytest.raises(PhysicalGatewayError):
        gateway.probe_stationary_joint_goal("elbow_flex", slow_start=True)
    bus.write.assert_not_called()
    bus.packet_handler.writeTxRx.assert_not_called()

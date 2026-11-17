from unittest.mock import Mock

import pytest

from sim2claw.physical_gateway import GatewayIdentity, PhysicalGatewayError, SO101PhysicalGateway
from sim2claw.scene import ROBOT_JOINTS


def setup_gateway():
    follower = Mock()
    follower.bus.sync_read.return_value = {j: 0 for j in ROBOT_JOINTS}
    follower.bus.read.side_effect = [1000, 1000, 50]
    gateway = SO101PhysicalGateway(
        GatewayIdentity("source", "follower", "a" * 64, "b" * 64),
        device_factory=lambda _: (Mock(), follower), configure_devices=False,
    )
    gateway.connected = True
    gateway.close = Mock()
    return gateway, follower.bus


def test_reduction_writes_only_volatile_limit_once_and_retains_original():
    g, bus = setup_gateway()
    receipt = g.set_stopped_torque_limit("elbow_flex", 50)
    bus.write.assert_called_once_with("Torque_Limit", "elbow_flex", 50, normalize=False, num_retry=0)
    assert receipt["previous"] == 1000 and receipt["readback"] == 50
    bus.enable_torque.assert_not_called()


@pytest.mark.parametrize("value", [0, 49, 1001, True, 50.5, float("nan")])
def test_invalid_values_never_write(value):
    g, bus = setup_gateway()
    with pytest.raises(PhysicalGatewayError):
        g.set_stopped_torque_limit("elbow_flex", value)
    bus.write.assert_not_called()


@pytest.mark.parametrize("flag", ["torque_enabled", "goal_write_may_have_armed"])
def test_no_setting_in_active_or_uncertain_session(flag):
    g, bus = setup_gateway()
    setattr(g, flag, True)
    with pytest.raises(PhysicalGatewayError):
        g.set_stopped_torque_limit("elbow_flex", 50)
    bus.write.assert_not_called()


def test_hardware_maximum_cannot_be_exceeded():
    g, bus = setup_gateway()
    bus.read.side_effect = [500, 500]
    with pytest.raises(PhysicalGatewayError):
        g.set_stopped_torque_limit("elbow_flex", 1000)
    bus.write.assert_not_called()
    g.close.assert_called_once()


def test_restoration_is_verified_while_off():
    g, bus = setup_gateway()
    bus.read.side_effect = [50, 1000, 1000]
    receipt = g.set_stopped_torque_limit("elbow_flex", 1000)
    assert receipt["previous"] == 50 and receipt["readback"] == 1000
    bus.write.assert_called_once_with("Torque_Limit", "elbow_flex", 1000, normalize=False, num_retry=0)


def test_missing_preflight_data_cannot_admit_write():
    g, bus = setup_gateway()
    bus.sync_read.return_value = {}
    with pytest.raises(PhysicalGatewayError):
        g.set_stopped_torque_limit("elbow_flex", 50)
    bus.write.assert_not_called()


def test_uncertain_write_is_not_retried_and_closes():
    g, bus = setup_gateway()
    bus.write.side_effect = ConnectionError("uncertain acknowledgement")
    with pytest.raises(ConnectionError):
        g.set_stopped_torque_limit("elbow_flex", 50)
    assert bus.write.call_count == 1
    g.close.assert_called_once()


def test_failed_readback_aborts():
    g, bus = setup_gateway()
    bus.read.side_effect = [1000, 1000, 1000]
    with pytest.raises(PhysicalGatewayError):
        g.set_stopped_torque_limit("elbow_flex", 50)
    g.close.assert_called_once()


@pytest.mark.parametrize("value", [0, 10])
def test_diagnostic_low_cap_has_stopped_readback_and_no_activation(value):
    g, bus = setup_gateway()
    bus.read.side_effect = [1000, 1000, value]
    r = g.set_stopped_torque_limit("elbow_flex", value, diagnostic_low_output=True)
    assert r["readback"] == value
    bus.write.assert_called_once_with("Torque_Limit", "elbow_flex", value, normalize=False, num_retry=0)
    bus.enable_torque.assert_not_called()

@pytest.mark.parametrize("previous", [0, 10])
def test_diagnostic_low_cap_can_restore_original(previous):
    g, bus = setup_gateway()
    bus.read.side_effect = [previous, 1000, 1000]
    r = g.set_stopped_torque_limit("elbow_flex", 1000, diagnostic_low_output=True)
    assert r["previous"] == previous and r["readback"] == 1000

@pytest.mark.parametrize("value,flag", [(1, True), (49, True), (-1, True), (0, 1)])
def test_diagnostic_low_cap_rejects_unreviewed_values(value, flag):
    g, bus = setup_gateway()
    with pytest.raises(PhysicalGatewayError):
        g.set_stopped_torque_limit("elbow_flex", value, diagnostic_low_output=flag)
    bus.write.assert_not_called()

def test_diagnostic_low_cap_rejects_active_hardware():
    g, bus = setup_gateway()
    bus.sync_read.return_value = {j: int(j == "elbow_flex") for j in ROBOT_JOINTS}
    with pytest.raises(PhysicalGatewayError):
        g.set_stopped_torque_limit("elbow_flex", 0, diagnostic_low_output=True)
    bus.write.assert_not_called()

from unittest.mock import Mock

import pytest

from sim2claw.physical_gateway import GatewayIdentity, PhysicalGatewayError, SO101PhysicalGateway
from sim2claw.scene import ROBOT_JOINTS


def fixture_gateway():
    follower = Mock()
    follower.bus.sync_read.return_value = {j: 0 for j in ROBOT_JOINTS}
    follower.bus.read.side_effect = [0, 254]
    g = SO101PhysicalGateway(GatewayIdentity("source", "follower", "a"*64, "b"*64),
        device_factory=lambda _: (Mock(), follower), configure_devices=False)
    g.connected = True
    g.close = Mock()
    return g, follower.bus


def test_sets_only_acceleration_and_returns_restoration_value():
    g, bus = fixture_gateway()
    receipt = g.set_stopped_acceleration("elbow_flex", 254)
    bus.write.assert_called_once_with("Acceleration", "elbow_flex", 254, normalize=False, num_retry=0)
    assert receipt["previous"] == 0 and receipt["readback"] == 254
    g.close.assert_not_called()


def test_restoration_skips_write_when_already_restored():
    g, bus = fixture_gateway()
    bus.read.side_effect = [0, 0]
    receipt = g.set_stopped_acceleration("elbow_flex", 0)
    assert receipt["setting_writes"] == 0
    bus.write.assert_not_called()


@pytest.mark.parametrize("value", [-1, 255, 1.5, True, float("nan")])
def test_rejects_invalid_value_without_writes(value):
    g, bus = fixture_gateway()
    with pytest.raises(PhysicalGatewayError): g.set_stopped_acceleration("elbow_flex", value)
    bus.write.assert_not_called()


@pytest.mark.parametrize("flag", ["torque_enabled", "goal_write_may_have_armed"])
def test_rejects_active_or_uncertain_session(flag):
    g, bus = fixture_gateway()
    setattr(g, flag, True)
    with pytest.raises(PhysicalGatewayError): g.set_stopped_acceleration("elbow_flex", 254)
    bus.write.assert_not_called()


def test_missing_preflight_status_cannot_admit_write():
    g, bus = fixture_gateway()
    bus.sync_read.return_value = {}
    with pytest.raises(PhysicalGatewayError): g.set_stopped_acceleration("elbow_flex", 254)
    bus.write.assert_not_called()
    g.close.assert_called_once()


def test_uncertain_ack_is_not_retried_and_closes():
    g, bus = fixture_gateway()
    bus.write.side_effect = ConnectionError("uncertain")
    with pytest.raises(ConnectionError): g.set_stopped_acceleration("elbow_flex", 254)
    assert bus.write.call_count == 1
    g.close.assert_called_once()


def test_readback_mismatch_aborts_and_closes():
    g, bus = fixture_gateway()
    bus.read.side_effect = [0, 0]
    with pytest.raises(PhysicalGatewayError): g.set_stopped_acceleration("elbow_flex", 254)
    g.close.assert_called_once()


def test_unexpected_torque_after_configuration_aborts():
    g, bus = fixture_gateway()
    bus.sync_read.side_effect = [{j: 0 for j in ROBOT_JOINTS}]*4 + [{j: 1 for j in ROBOT_JOINTS}]
    with pytest.raises(PhysicalGatewayError): g.set_stopped_acceleration("elbow_flex", 254)
    g.close.assert_called_once()

from unittest.mock import Mock

import pytest

from sim2claw.physical_gateway import GatewayIdentity, PhysicalGatewayError, SO101PhysicalGateway


def setup_gateway():
    follower = Mock()
    follower.bus.motors = {"elbow_flex": Mock(id=3)}
    gateway = SO101PhysicalGateway(
        GatewayIdentity("source", "follower", "a" * 64, "b" * 64),
        device_factory=lambda _: (Mock(), follower), configure_devices=False,
        clock=Mock(side_effect=[10.0, 10.002]),
    )
    gateway.connected = True
    return gateway, follower.bus


def test_complete_feedback_retains_raw_and_decodes_signed_fields_without_writes():
    g, bus = setup_gateway()
    # Position 3022, velocity -2, load -3, 12.2 V, 32 C, status 0,
    # moving 1, and current -9. Bytes 8, 11 and 12 remain raw.
    data = [206, 11, 2, 128, 3, 4, 122, 32, 0, 0, 1, 0, 0, 9, 128]
    bus.packet_handler.readTxRx.return_value = (data, 0, 0)
    g.goal_write_may_have_armed = True
    row = g.read_motor_diagnostic_block("elbow_flex")
    assert (row["position_raw"], row["velocity_raw"], row["load_raw"], row["current_raw"]) == (3022, -2, -3, -9)
    assert row["voltage_volts"] == 12.2 and row["data"] == data
    assert row["started_monotonic"] == 10.0 and row["completed_monotonic"] == 10.002
    assert "physical_follower_torque_enabled" not in row
    bus.packet_handler.readTxRx.assert_called_once_with(bus.port_handler, 3, 56, 15)
    bus.write.assert_not_called()


@pytest.mark.parametrize("reply", [([], -3001, 0), ([0] * 14, 0, 0), ([0] * 15, 0, 1), ([256] * 15, 0, 0)])
def test_failed_reply_preserves_evidence_without_retry(reply):
    g, bus = setup_gateway()
    bus.packet_handler.readTxRx.return_value = reply
    with pytest.raises(PhysicalGatewayError) as caught:
        g.read_motor_diagnostic_block("elbow_flex")
    assert caught.value.details["data"] == reply[0]
    assert caught.value.details["communication_result"] == reply[1]
    assert bus.packet_handler.readTxRx.call_count == 1
    bus.write.assert_not_called()


def test_transport_exception_keeps_timing_without_retry():
    g, bus = setup_gateway()
    bus.packet_handler.readTxRx.side_effect = OSError("port disconnected")
    with pytest.raises(PhysicalGatewayError) as caught:
        g.read_motor_diagnostic_block("elbow_flex")
    assert caught.value.details["error"] == "port disconnected"
    assert bus.packet_handler.readTxRx.call_count == 1
    bus.write.assert_not_called()


@pytest.mark.parametrize("connected,joint", [(False, "elbow_flex"), (True, "unknown")])
def test_disconnected_or_unknown_joint_never_touches_bus(connected, joint):
    g, bus = setup_gateway()
    g.connected = connected
    with pytest.raises(PhysicalGatewayError):
        g.read_motor_diagnostic_block(joint)
    bus.packet_handler.readTxRx.assert_not_called()

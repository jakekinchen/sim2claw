from unittest.mock import Mock

import pytest

from sim2claw.physical_gateway import GatewayIdentity, PhysicalGatewayError, SO101PhysicalGateway
from sim2claw.scene import ROBOT_JOINTS


def make_gateway(spacing=0.15):
    leader, follower = Mock(), Mock()
    follower.bus.is_connected = True
    leader.bus.is_connected = False
    follower.bus.read.side_effect = lambda name, *args, **kwargs: 1 if name == "Torque_Enable" else 0
    gateway = SO101PhysicalGateway(
        GatewayIdentity("source", "follower", "a" * 64, "b" * 64),
        device_factory=lambda _: (leader, follower),
        torque_enable_spacing_seconds=spacing,
        sleep=Mock(),
    )
    return gateway, follower.bus


def test_staggered_activation_verifies_each_motor_before_next():
    gateway, bus = make_gateway()
    gateway._enable_follower_torque()
    calls = bus.mock_calls
    for index, joint in enumerate(ROBOT_JOINTS):
        block = calls[index * 3:index * 3 + 3]
        assert block[0].kwargs["motors"] == joint
        assert block[1].args == ("Torque_Enable", joint)
        assert block[2].args == ("Status", joint)
    assert gateway.sleep.call_count == 6


@pytest.mark.parametrize("failure", [ConnectionError("missing acknowledgement"), RuntimeError("device fault")])
def test_failed_acknowledgement_stops_activation_and_releases_chain(failure):
    gateway, bus = make_gateway()
    bus.enable_torque.side_effect = [None, failure]
    with pytest.raises(type(failure)):
        gateway._enable_follower_torque()
    assert bus.enable_torque.call_count == 2
    bus.disable_torque.assert_called_once()
    bus.disconnect.assert_called_once()


@pytest.mark.parametrize("torque,status", [(0, 0), (1, 2)])
def test_bad_readback_stops_before_next_joint(torque, status):
    gateway, bus = make_gateway()
    bus.read.side_effect = [torque, status]
    with pytest.raises(PhysicalGatewayError):
        gateway._enable_follower_torque()
    assert bus.enable_torque.call_count == 1
    bus.disable_torque.assert_called_once()


@pytest.mark.parametrize("spacing", [-1, 0.51, float("nan")])
def test_invalid_spacing_rejected(spacing):
    with pytest.raises(PhysicalGatewayError):
        make_gateway(spacing)


def test_custom_order_is_complete_and_honored():
    gateway, bus = make_gateway()
    gateway.torque_enable_order = ('elbow_flex', 'shoulder_pan', 'shoulder_lift', 'wrist_flex', 'wrist_roll', 'gripper')
    gateway._enable_follower_torque()
    assert [call.kwargs['motors'] for call in bus.enable_torque.call_args_list] == list(gateway.torque_enable_order)


def test_incomplete_or_unstaggered_custom_order_rejected():
    for spacing, order in [(0.15, ('elbow_flex',)), (0, tuple(ROBOT_JOINTS))]:
        with pytest.raises(PhysicalGatewayError):
            SO101PhysicalGateway(
                GatewayIdentity('source','follower','a'*64,'b'*64),
                device_factory=lambda _: (Mock(),Mock()),
                torque_enable_spacing_seconds=spacing,torque_enable_order=order)


def test_unicast_position_failure_stops_without_retry_or_later_targets():
    gateway, bus = make_gateway()
    gateway.position_write_mode = 'acknowledged_unicast'
    bus.write.side_effect = [None, ConnectionError('uncertain acknowledgement')]
    action = {f'{joint}.pos': 0.0 for joint in ROBOT_JOINTS}
    with pytest.raises(ConnectionError):
        gateway._send_follower_action(action)
    assert bus.write.call_count == 2
    assert all(call.kwargs['num_retry'] == 0 for call in bus.write.call_args_list)


def test_shutdown_releases_later_motors_and_closes_serial_despite_error():
    gateway, bus = make_gateway()
    bus.motors = {joint: None for joint in ROBOT_JOINTS}
    def disable(*, motors=None, num_retry=0):
        if motors is None or motors == 'elbow_flex':
            raise ConnectionError('missing elbow reply')
    bus.disable_torque.side_effect = disable
    with pytest.raises(PhysicalGatewayError, match='missing elbow reply'):
        gateway.close()
    assert [c.kwargs.get('motors') for c in bus.disable_torque.call_args_list] == [None,*ROBOT_JOINTS]
    bus.disconnect.assert_called_once_with(False)

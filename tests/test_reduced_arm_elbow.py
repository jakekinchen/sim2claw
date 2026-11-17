from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from test_isolated_servo_hold import HoldSerial
from test_isolated_servo_read_only import FakePort
from sim2claw.physical_gateway import PhysicalGatewayError, probe_reduced_arm_elbow


class ReducedArmSerial(HoldSerial):
    def __init__(self):
        super().__init__()
        self.memory.update({56: 208, 57: 7})
        self.memories = {peer: dict(self.memory) for peer in (1, 2, 3)}
        self.memories[1].update({5: 1, 9: 209, 10: 2, 11: 120, 12: 13,
                                 31: 70, 32: 4, 56: 90, 57: 7})
        self.memories[2].update({5: 2, 9: 132, 10: 3, 11: 235, 12: 12,
                                 31: 49, 32: 1, 56: 71, 57: 5})
        self.peer_fault = None

    def write(self, packet):
        p = list(packet)
        if p[2] in self.memories:
            self.memory, self.servo_id = self.memories[p[2]], p[2]
        try:
            result = super().write(packet)
            if p[2] == 3 and p[4:6] == [3, 42]:
                if self.peer_fault == "voltage":
                    self.memories[1][62] = 90
                elif self.peer_fault == "drift":
                    self.memories[2][56] += 8
            return result
        finally:
            self.memory, self.servo_id = self.memories[3], 3


@pytest.fixture
def reduced_adapter():
    port = FakePort()
    port.ser = ReducedArmSerial()
    port.isPacketTimeout = lambda: not port.ser.pending
    identity = SimpleNamespace(device="/dev/test-servo", serial_number="expected", vid=0x1A86, pid=0x55D3)
    with patch("serial.tools.list_ports.comports", return_value=[identity]), patch("scservo_sdk.PortHandler", return_value=port):
        yield port


def run_probe(port, **kwargs):
    now = [0.0]
    def sleep(seconds):
        now[0] += seconds
    return probe_reduced_arm_elbow(
        "/dev/test-servo", "expected", raw_limits=(818, 3026), expected_homing_offset=-1781,
        peer_calibrations=kwargs.pop("peer_calibrations", {1: ((721, 3448), 1094), 2: ((900, 3307), 305)}),
        camera_guard=kwargs.pop("camera_guard", Mock()), clock=lambda: now[0], sleep=sleep, **kwargs)


@pytest.mark.parametrize("offset", [0, -57, 114])
def test_reduced_chain_writes_only_elbow_and_monitors_real_peers(reduced_adapter, offset):
    before = {i: dict(m) for i, m in reduced_adapter.ser.memories.items()}
    result = run_probe(reduced_adapter, goal_offset_raw=offset, observation_seconds=3)
    assert result["status"] == "three_second_position_probe_completed", result
    assert result["proof_class"] == "physical_reduced_load_elbow_diagnostic"
    assert result["unloaded_sweep"] is False
    assert result["goal_writes"] == 1
    assert result["target_raw"] == 2000 + offset
    assert result["observed_final_delta_raw"] == 0  # Observation is not tracking proof.
    assert all(p[2] == 3 for p in reduced_adapter.ser.frames if p[4] == 3)
    assert set(result["passive_peers_after"]) == {1, 2}
    assert len([r for r in result["passive_peer_samples"] if r["stage"] == "hold"]) >= 100
    for peer in (1, 2):
        assert reduced_adapter.ser.memories[peer] == before[peer]
    assert result["restoration"]["torque_off"] and result["port_closed"]


@pytest.mark.parametrize("fault", ["missing_peer", "distal_present", "torque_on", "calibration", "mode", "voltage"])
def test_wrong_topology_or_peer_state_rejects_without_writes(reduced_adapter, fault):
    serial = reduced_adapter.ser
    if fault == "missing_peer": del serial.memories[1]
    if fault == "distal_present": serial.extra_ids.add(4)
    if fault == "torque_on": serial.memories[2][40] = 1
    if fault == "calibration": serial.memories[1][31] = 0
    if fault == "mode": serial.memories[2][33] = 1
    if fault == "voltage": serial.memories[1][62] = 80
    result = run_probe(reduced_adapter)
    assert result["status"] == "aborted", result
    assert result["goal_writes"] == 0 and result["port_closed"]
    assert all(p[4] in (1, 2) for p in serial.frames)


@pytest.mark.parametrize("fault", ["voltage", "drift"])
def test_passive_peer_change_aborts_and_releases_elbow(reduced_adapter, fault):
    reduced_adapter.ser.peer_fault = fault
    result = run_probe(reduced_adapter, goal_offset_raw=-57)
    assert result["status"] == "aborted" and "Passive peer guard" in result["error"]
    assert result["goal_writes"] == 1
    assert reduced_adapter.ser.memories[3][40] == 0
    assert result["restoration"]["restored"] == 1000
    assert result["port_closed"]


@pytest.mark.parametrize("fault", ["lose_goal_ack", "voltage_fault", "corrupt_feedback", "reset_limit"])
def test_elbow_fault_does_not_retry_or_activate_peers(reduced_adapter, fault):
    setattr(reduced_adapter.ser, fault, True)
    result = run_probe(reduced_adapter)
    assert result["status"] == "aborted"
    assert result["goal_writes"] == reduced_adapter.ser.goal_count == 1
    assert reduced_adapter.ser.memories[3][40] == 0
    assert all(p[2] == 3 for p in reduced_adapter.ser.frames if p[4] == 3)
    assert result["restoration"]["torque_off"] and result["port_closed"]


@pytest.mark.parametrize("arguments", [
    {"peer_calibrations": {}}, {"peer_calibrations": {1: ((721, 3448), 1094)}},
    {"peer_calibrations": {1: ((3448, 721), 1094), 2: ((900, 3307), 305)}},
    {"goal_offset_raw": 115}, {"observation_seconds": 4},
])
def test_invalid_scope_never_opens_port(reduced_adapter, arguments):
    with pytest.raises(PhysicalGatewayError):
        run_probe(reduced_adapter, **arguments)
    assert not reduced_adapter.is_open and not reduced_adapter.ser.frames

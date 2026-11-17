from types import SimpleNamespace
from unittest.mock import patch

import pytest
import scservo_sdk as scs

from sim2claw.physical_gateway import (
    PhysicalGatewayError,
    assign_isolated_servo_id,
    inspect_isolated_servo_read_only,
)


class FakeSerial:
    def __init__(self):
        self.frames = []
        self.pending = b""
        self.closed = False
        self.servo_id = 1
        self.extra_ids = set()
        self.lose_id_write_ack = False
        self.memory = {3: 9, 4: 3, 5: 1, 14: 140, 15: 40, 62: 120, 63: 25}

    @property
    def in_waiting(self):
        return len(self.pending)

    def reset_input_buffer(self):
        self.pending = b""

    def flush(self):
        pass

    def write(self, packet):
        frame = list(packet)
        self.frames.append(frame)
        if frame[2] == self.servo_id or frame[2] in self.extra_ids:
            data = []
            if frame[4] == 2:
                data = [self.memory.get(i, 0) for i in range(frame[5], frame[5] + frame[6])]
            if frame[4] == 3:
                address, value = frame[5:7]
                if address == 5:
                    assert self.memory.get(55, 0) == 0, "Cannot change ID with EEPROM locked"
                    self.servo_id = value
                    self.memory[5] = value
                    if self.lose_id_write_ack:
                        return len(frame)
                else:
                    self.memory[address] = value
            response = [255, 255, frame[2], len(data) + 2, 0, *data]
            response.append((~sum(response[2:])) & 255)
            self.pending = bytes(response)
        return len(frame)

    def read(self, count):
        value, self.pending = self.pending[:count], self.pending[count:]
        return value

    def close(self):
        self.closed = True


class FakePort(scs.PortHandler):
    def __init__(self):
        super().__init__("/dev/test-servo")
        self.ser = FakeSerial()

    def setupPort(self, _baud):
        self.is_open = True
        self.ser.closed = False
        self.tx_time_per_byte = 0.01
        return True


@pytest.fixture
def adapter():
    port = FakePort()
    identity = SimpleNamespace(
        device="/dev/test-servo", serial_number="expected", vid=0x1A86, pid=0x55D3,
    )
    def fresh_handler(_name):
        port.writePort = FakePort.writePort.__get__(port, FakePort)
        return port

    with (
        patch("serial.tools.list_ports.comports", return_value=[identity]),
        patch("scservo_sdk.PortHandler", side_effect=fresh_handler),
    ):
        yield port


def test_real_sdk_only_sends_reads_and_ping_and_preserves_torque(adapter):
    report = inspect_isolated_servo_read_only("/dev/test-servo", "expected")
    assert report["probes"][0]["model_number"] == 777
    assert report["probes"][0]["registers"]["present_telemetry"]["data"][6:8] == [120, 25]
    assert report["probes"][1]["communication_result"] != scs.COMM_SUCCESS
    assert {frame[4] for frame in adapter.ser.frames} == {1, 2}
    assert report["transmitted_packets"] == adapter.ser.frames
    assert report["register_writes_sent"] == 0
    assert report["port_closed"] and adapter.ser.closed


@pytest.mark.parametrize("instruction,address,length", [(3, 40, 1), (4, 5, 1), (2, 42, 2)])
def test_transport_rejects_writes_and_unlisted_reads_and_closes(adapter, instruction, address, length):
    protocol = scs.PacketHandler(0)

    def unsafe_ping(port, servo_id):
        packet = [255, 255, servo_id, 4, instruction, address, length]
        packet.append((~sum(packet[2:])) & 255)
        port.writePort(packet)
        raise AssertionError("An unapproved packet reached the transport")

    protocol.ping = unsafe_ping
    with patch("scservo_sdk.PacketHandler", return_value=protocol):
        with pytest.raises(PhysicalGatewayError, match="rejected a packet"):
            inspect_isolated_servo_read_only("/dev/test-servo", "expected")
    assert adapter.ser.frames == []
    assert adapter.ser.closed


def test_adapter_identity_mismatch_never_opens_port(adapter):
    with pytest.raises(PhysicalGatewayError, match="USB identity"):
        inspect_isolated_servo_read_only("/dev/test-servo", "wrong")
    assert not adapter.is_open
    assert not adapter.ser.frames


def test_configuration_inventory_preserves_memory_and_sends_only_reads(adapter):
    adapter.ser.extra_ids = {2, 3, 4, 5, 6}
    adapter.ser.memory.update({21: 16, 28: 54, 29: 1, 40: 1, 48: 50})
    before = dict(adapter.ser.memory)
    report = inspect_isolated_servo_read_only(
        "/dev/test-servo", "expected", candidate_ids=(1, 2, 3, 4, 5, 6),
        include_configuration=True,
    )
    assert len(report["probes"]) == 6
    for probe in report["probes"]:
        registers = probe["registers"]
        assert len(registers["persistent_configuration"]["data"]) == 40
        assert registers["persistent_configuration"]["data"][21] == 16
        assert registers["runtime_configuration"]["data"][0] == 1
    assert adapter.ser.memory == before
    assert all(frame[4] in (1, 2) for frame in adapter.ser.frames)
    assert report["port_closed"] and adapter.ser.closed


def test_configuration_mode_still_rejects_writes(adapter):
    protocol = scs.PacketHandler(0)
    def unsafe_ping(port, servo_id):
        return protocol.write1ByteTxRx(port, servo_id, 40, 1)
    protocol.ping = unsafe_ping
    with patch("scservo_sdk.PacketHandler", return_value=protocol):
        with pytest.raises(PhysicalGatewayError, match="rejected a packet"):
            inspect_isolated_servo_read_only(
                "/dev/test-servo", "expected", include_configuration=True,
            )
    assert not adapter.ser.frames
    assert adapter.ser.closed


@pytest.mark.parametrize("ids", [(254,), (-1,), (1, 1), (True,), ()])
def test_invalid_ids_never_open_port(adapter, ids):
    with pytest.raises(PhysicalGatewayError, match="unicast"):
        inspect_isolated_servo_read_only("/dev/test-servo", "expected", candidate_ids=ids)
    assert not adapter.is_open


@pytest.mark.parametrize("initial_lock", [0, 1])
@pytest.mark.parametrize("lose_ack", [False, True])
def test_assigns_id_once_and_preserves_lock_without_torque_writes(adapter, initial_lock, lose_ack):
    adapter.ser.memory[55] = initial_lock
    adapter.ser.lose_id_write_ack = lose_ack
    report = assign_isolated_servo_id("/dev/test-servo", "expected")
    assert report["status"] == "assigned_and_verified", report
    assert adapter.ser.servo_id == 3
    assert adapter.ser.memory[55] == initial_lock
    writes = [(f[2], f[5], f[6]) for f in adapter.ser.frames if f[4] == 3]
    expected = [(1, 5, 3)] if initial_lock == 0 else [(1, 55, 0), (1, 5, 3), (3, 55, 1)]
    assert writes == expected
    assert report["port_closed"] and adapter.ser.closed


@pytest.mark.parametrize("fault", ["torque_on", "target_occupied", "overvoltage"])
def test_assignment_rejects_unsafe_preflight_without_any_writes(adapter, fault):
    if fault == "torque_on":
        adapter.ser.memory[40] = 1
    elif fault == "target_occupied":
        adapter.ser.extra_ids.add(3)
    else:
        adapter.ser.memory[62] = 140
    with pytest.raises(PhysicalGatewayError):
        assign_isolated_servo_id("/dev/test-servo", "expected")
    assert all(f[4] in (1, 2) for f in adapter.ser.frames)
    assert adapter.ser.servo_id == 1
    assert adapter.ser.closed

"""Upstream-witness sampling for the reduced-arm elbow hold.

The passive peers are independent voltage sensors at other nodes of the shared
servo bus. Reading them between elbow feedback samples, and once more right
after the first torque-off attempt, shows whether an elbow voltage fault is a
bus-wide collapse or local to the elbow. These tests cover software guards
only; they do not certify physical motor behavior.
"""
import pytest

from test_isolated_servo_hold import run_hold
from test_reduced_arm_elbow import ReducedArmSerial, reduced_adapter, run_probe  # noqa: F401
from sim2claw.physical_gateway import PhysicalGatewayError


class CollapsingBusSerial(ReducedArmSerial):
    """After the elbow goal, selected peers report a voltage fault of their own."""

    def __init__(self, collapsed_peers=(1, 2)):
        super().__init__()
        self.collapsed_peers = set(collapsed_peers)

    def write(self, packet):
        n = super().write(packet)
        p = list(packet)
        if (self.goal_count and self.memories[3].get(40) == 1 and p[2] in self.collapsed_peers
                and p[4] == 2 and p[5] == 56 and self.pending):
            response = list(self.pending)
            response[4], response[11], response[14] = 1, 29, 1
            response[-1] = (~sum(response[2:-1])) & 255
            self.pending = bytes(response)
        return n


def witness_rows(result, stage):
    return [r for r in result["upstream_witness_samples"] if r["stage"] == stage]


def test_default_probe_takes_no_witness_samples(reduced_adapter):
    result = run_probe(reduced_adapter)
    assert result["status"] == "one_second_hold_completed", result.get("error")
    assert result["upstream_witness"] is False
    assert result["upstream_witness_samples"] == []


def test_healthy_hold_interleaves_read_only_peer_witnesses(reduced_adapter):
    before = {i: dict(m) for i, m in reduced_adapter.ser.memories.items() if i != 3}
    result = run_probe(reduced_adapter, upstream_witness=True)
    assert result["status"] == "one_second_hold_completed", result.get("error")
    assert result["upstream_witness"] is True
    hold = witness_rows(result, "hold")
    assert len(hold) >= 100
    # Nearest upstream neighbour first, then alternating, one per elbow sample.
    assert [r["servo_id"] for r in hold[:4]] == [2, 1, 2, 1]
    assert all(r["voltage_volts"] == 12.3 and r["status"] == 0 for r in hold)
    elbow_hold = [r for r in result["samples"] if r["stage"] == "hold"]
    assert len(hold) == len(elbow_hold)
    assert hold[0]["started_monotonic"] >= elbow_hold[0]["completed_monotonic"]
    # A clean first stop still records one bracketing sample from each peer.
    assert [r["servo_id"] for r in witness_rows(result, "after_first_stop")] == [2, 1]
    assert all(p[2] == 3 for p in reduced_adapter.ser.frames if p[4] == 3)
    assert {i: m for i, m in reduced_adapter.ser.memories.items() if i != 3} == before
    assert result["goal_writes"] == 1 and result["restoration"]["torque_off"]


def test_local_elbow_fault_records_healthy_upstream_voltage(reduced_adapter):
    reduced_adapter.ser.voltage_fault = True
    result = run_probe(reduced_adapter, upstream_witness=True)
    assert result["status"] == "aborted"
    assert result["error_details"]["data"][6] == 28
    after = witness_rows(result, "after_first_stop")
    assert [r["servo_id"] for r in after] == [2, 1]
    assert all(r["voltage_volts"] == 12.3 and r["status"] == 0 and "error" not in r for r in after)
    assert result["goal_writes"] == reduced_adapter.ser.goal_count == 1
    assert reduced_adapter.ser.memories[3][40] == 0
    assert result["restoration"]["torque_off"] and result["port_closed"]


def test_bus_wide_collapse_is_captured_from_the_peer_and_stops_the_elbow(reduced_adapter):
    reduced_adapter.ser.__class__ = CollapsingBusSerial
    reduced_adapter.ser.collapsed_peers = {1, 2}
    result = run_probe(reduced_adapter, upstream_witness=True)
    assert result["status"] == "aborted"
    assert result["error"] == "Isolated hold read failed."
    assert result["error_details"]["servo_id"] == 2
    faulted = [r for r in result["upstream_witness_samples"] if "error" in r]
    assert faulted and faulted[0]["stage"] == "hold" and faulted[0]["servo_id"] == 2
    # The faulting reply is retained raw: voltage byte 29 (2.9 V) with the error bit.
    assert faulted[0]["details"]["data"][6] == 29
    assert faulted[0]["details"]["packet_error"] == 1
    assert result["goal_writes"] == reduced_adapter.ser.goal_count == 1
    assert reduced_adapter.ser.memories[3][40] == 0
    assert all(p[2] == 3 for p in reduced_adapter.ser.frames if p[4] == 3)
    assert result["port_closed"]


def test_sagging_but_error_free_peer_trips_the_witness_guard(reduced_adapter):
    reduced_adapter.ser.peer_fault = "voltage"  # peer 1 reads 9.0 V after the goal
    result = run_probe(reduced_adapter, upstream_witness=True)
    assert result["status"] == "aborted"
    assert result["error"] == "Upstream witness guard tripped."
    assert result["error_details"]["servo_id"] == 1
    assert result["error_details"]["voltage_volts"] == 9.0
    # Shutdown witnesses are evidence only: a still-low peer must not block release.
    after = witness_rows(result, "after_first_stop")
    assert [r["servo_id"] for r in after] == [2, 1] and after[1]["voltage_volts"] == 9.0
    assert reduced_adapter.ser.memories[3][40] == 0
    assert result["restoration"]["restored"] == 1000 and result["port_closed"]


def test_silent_peer_is_recorded_and_never_blocks_release(reduced_adapter):
    serial = reduced_adapter.ser
    original_write = serial.write

    def write(packet):
        p = list(packet)
        if serial.goal_count and p[2] == 2 and p[4] == 2 and p[5] == 56:
            serial.frames.append(p)
            serial.pending = b""
            return len(p)
        return original_write(packet)

    serial.write = write
    result = run_probe(reduced_adapter, upstream_witness=True)
    assert result["status"] == "aborted"
    silent = [r for r in result["upstream_witness_samples"] if "error" in r]
    assert silent and all(r["servo_id"] == 2 for r in silent)
    assert any(r["stage"] == "after_first_stop" for r in silent)
    assert serial.memories[3][40] == 0
    assert result["shutdown_attempts"][0].get("torque_off_verified") is True
    assert result["restoration"]["torque_off"] and result["port_closed"]


@pytest.mark.parametrize("arguments", [
    {"upstream_witness": 1},
    {"upstream_witness": True, "goal_offset_raw": -57},
    {"upstream_witness": True, "observation_seconds": 3},
])
def test_witness_is_limited_to_the_one_second_stationary_hold(reduced_adapter, arguments):
    with pytest.raises(PhysicalGatewayError):
        run_probe(reduced_adapter, **arguments)
    assert not reduced_adapter.is_open and not reduced_adapter.ser.frames


def test_single_servo_hold_has_no_witness_option():
    with pytest.raises(TypeError):
        run_hold(None, upstream_witness=True)

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import scservo_sdk as scs

from test_isolated_servo_read_only import FakePort, FakeSerial
from sim2claw.physical_gateway import PhysicalGatewayError, probe_isolated_servo_hold


class HoldSerial(FakeSerial):
    def __init__(self):
        super().__init__()
        self.servo_id = 3
        self.memory.update({0: 3, 1: 9, 5: 3, 9: 50, 10: 3, 11: 210, 12: 11,
                            16: 232, 17: 3, 31: 245, 32: 14, 48: 232, 49: 3,
                            56: 206, 57: 11, 62: 123, 63: 30, 69: 1})
        self.goal_count = 0
        self.lose_goal_ack = False
        self.voltage_fault = False
        self.corrupt_feedback = False
        self.reset_limit = False

    def write(self, packet):
        n = super().write(packet)
        p = list(packet)
        if p[4] == 3:
            for i, value in enumerate(p[6:-1]):
                self.memory[p[5] + i] = value
            if p[5] == 42:
                self.goal_count += 1
                self.memory[40] = 1
                if self.reset_limit:
                    self.memory.update({48: 232, 49: 3})
                if self.lose_goal_ack:
                    self.pending = b""
        if p[4] == 2 and p[5] == 56 and self.memory.get(40) == 1:
            if self.voltage_fault:
                response = list(self.pending)
                response[4], response[11], response[14] = 1, 28, 1
                response[-1] = (~sum(response[2:-1])) & 255
                self.pending = bytes(response)
            if self.corrupt_feedback:
                response = list(self.pending)
                response[-1] ^= 1
                self.pending = bytes(response)
        return n


@pytest.fixture
def hold_adapter():
    port = FakePort()
    port.ser = HoldSerial()
    port.isPacketTimeout = lambda: not port.ser.pending
    identity = SimpleNamespace(device="/dev/test-servo", serial_number="expected", vid=0x1A86, pid=0x55D3)
    with patch("serial.tools.list_ports.comports", return_value=[identity]), patch("scservo_sdk.PortHandler", return_value=port):
        yield port


def run_hold(port, **kwargs):
    current_time = [0.0]
    def sleep(seconds):
        current_time[0] += seconds
    return probe_isolated_servo_hold("/dev/test-servo", "expected", raw_limits=(818, 3026),
        expected_homing_offset=-1781, camera_guard=kwargs.pop("camera_guard", Mock()),
        clock=lambda: current_time[0], sleep=sleep, **kwargs)


@pytest.mark.parametrize("limit", [50, 1000])
def test_real_packets_for_hold_release_and_restoration(hold_adapter, limit):
    r = run_hold(hold_adapter, output_limit=limit)
    assert r["status"] == "one_second_hold_completed", r.get("error")
    assert r["goal_writes"] == 1
    assert r["restoration"]["restored"] == 1000 and r["restoration"]["torque_off"]
    writes = [p for p in hold_adapter.ser.frames if p[4] == 3]
    assert [(p[5], p[6:-1]) for p in writes] == (
        [(48, [50, 0]), (42, [206, 11]), (40, [0]), (48, [232, 3])] if limit == 50 else
        [(42, [206, 11]), (40, [0])]
    )
    assert hold_adapter.ser.memory[40] == 0
    assert r["port_closed"] and hold_adapter.ser.closed


@pytest.mark.parametrize("bad_state", ["extra_motor", "torque_on", "calibration", "wrong_mode", "firmware", "voltage"])
def test_admission_failure_never_writes(hold_adapter, bad_state):
    s = hold_adapter.ser
    if bad_state == "extra_motor": s.extra_ids.add(2)
    if bad_state == "torque_on": s.memory[40] = 1
    if bad_state == "calibration": s.memory[31] = 0
    if bad_state == "wrong_mode": s.memory[33] = 1
    if bad_state == "firmware": s.memory[1] = 8
    if bad_state == "voltage": s.memory[62] = 28
    r = run_hold(hold_adapter)
    assert r["status"] == "aborted"
    assert all(p[4] in (1, 2) for p in s.frames)
    assert r["port_closed"]


@pytest.mark.parametrize("fault", ["lose_goal_ack", "voltage_fault", "corrupt_feedback", "reset_limit"])
def test_fault_never_retries_activation_and_releases(hold_adapter, fault):
    setattr(hold_adapter.ser, fault, True)
    r = run_hold(hold_adapter)
    assert r["status"] == "aborted"
    assert hold_adapter.ser.goal_count == 1
    assert hold_adapter.ser.memory[40] == 0
    assert r["port_closed"]
    assert r["restoration"]["restored"] == 1000
    if fault == "voltage_fault":
        assert r["error_details"]["data"][6] == 28
        assert r["error_details"]["packet_error"] == 1


def test_stale_camera_before_activation_releases_changed_setting(hold_adapter):
    calls = [0]
    def camera():
        calls[0] += 1
        if calls[0] > 3:
            raise RuntimeError("camera stale")
    r = run_hold(hold_adapter, camera_guard=camera)
    assert r["error"] == "camera stale" and hold_adapter.ser.goal_count == 0
    assert r["restoration"]["restored"] == 1000
    assert hold_adapter.ser.memory[40] == 0


def test_allowlist_rejects_unsolicited_torque_enable(hold_adapter):
    protocol = scs.PacketHandler(0)
    def bad_ping(handler, servo_id):
        p = [255, 255, 3, 4, 3, 40, 1]
        p.append((~sum(p[2:])) & 255)
        handler.writePort(p)
    protocol.ping = bad_ping
    with patch("scservo_sdk.PacketHandler", return_value=protocol):
        r = run_hold(hold_adapter)
    assert "unapproved packet" in r["error"]
    assert hold_adapter.ser.frames == [] and r["port_closed"]


def test_invalid_limit_never_opens_port(hold_adapter):
    with pytest.raises(PhysicalGatewayError):
        run_hold(hold_adapter, output_limit=0)
    assert not hold_adapter.is_open and not hold_adapter.ser.frames


def test_selected_shoulder_identity_limits_and_all_writes(hold_adapter):
    servo = hold_adapter.ser
    servo.servo_id = 2
    servo.memory.update({5: 2, 9: 132, 10: 3, 11: 235, 12: 12,
                         31: 49, 32: 1, 56: 89, 57: 8})
    now = [0.0]
    def sleep(seconds):
        now[0] += seconds
    result = probe_isolated_servo_hold(
        "/dev/test-servo", "expected", servo_id=2, raw_limits=(900, 3307),
        expected_homing_offset=305, output_limit=50, camera_guard=Mock(),
        sleep=sleep, clock=lambda: now[0])
    assert result["status"] == "one_second_hold_completed", result.get("error")
    assert result["target_raw"] == 2137 and result["goal_writes"] == 1
    writes = [p for p in servo.frames if p[4] == 3]
    assert all(p[2] == 2 for p in writes)
    assert [(p[5], p[6:-1]) for p in writes] == [
        (48, [50, 0]), (42, [89, 8]), (40, [0]), (48, [232, 3])]
    assert result["restoration"]["torque_off"] and result["port_closed"]


@pytest.mark.parametrize("offset", [-6, 6])
def test_six_count_probe_is_anchored_and_does_not_claim_motion(hold_adapter, offset):
    # The fake motor accepts the target but does not move. A completed
    # observation must retain that distinction instead of claiming tracking.
    hold_adapter.ser.memory.update({56: 208, 57: 7})  # Current position2000.
    r = run_hold(hold_adapter, goal_offset_raw=offset)
    assert r["status"] == "one_second_position_probe_completed", r.get("error")
    assert r["anchor_raw"] == 2000 and r["target_raw"] == 2000 + offset
    assert r["observed_final_delta_raw"] == 0
    goals = [p for p in hold_adapter.ser.frames if p[4:6] == [3, 42]]
    assert len(goals) == 1
    assert goals[0][6] | goals[0][7] << 8 == 2000 + offset
    assert r["restoration"]["torque_off"] and r["port_closed"]


def test_six_count_probe_rejects_limit_crossing_without_writes(hold_adapter):
    r = run_hold(hold_adapter, goal_offset_raw=6)  # 3022+6 is beyond3026.
    assert "exceed calibration" in r["error"]
    assert r["goal_writes"] == 0 and all(p[4] in (1, 2) for p in hold_adapter.ser.frames)
    assert r["port_closed"]


@pytest.mark.parametrize("arguments", [
    {"goal_offset_raw": 7}, {"goal_offset_raw": True},
    {"goal_offset_raw": 6, "output_limit": 1000},
])
def test_unapproved_offset_or_higher_output_never_opens(hold_adapter, arguments):
    with pytest.raises(PhysicalGatewayError):
        run_hold(hold_adapter, **arguments)
    assert not hold_adapter.is_open and not hold_adapter.ser.frames


def test_offset_goal_lost_ack_is_never_retried(hold_adapter):
    hold_adapter.ser.memory.update({56: 208, 57: 7})
    hold_adapter.ser.lose_goal_ack = True
    r = run_hold(hold_adapter, goal_offset_raw=6)
    assert r["status"] == "aborted" and r["goal_writes"] == 1
    assert hold_adapter.ser.goal_count == 1
    assert r["restoration"]["torque_off"] and r["port_closed"]


def test_offset_motion_guard_stays_relative_to_initial_position(hold_adapter):
    servo = hold_adapter.ser
    servo.memory.update({56: 208, 57: 7})
    original_write = servo.write
    def overshoot(packet):
        result = original_write(packet)
        if list(packet)[4:6] == [3, 42]:
            servo.memory.update({56: 220, 57: 7})  # +12 from anchor, +6 from target.
        return result
    servo.write = overshoot
    r = run_hold(hold_adapter, goal_offset_raw=6)
    assert r["status"] == "aborted" and "feedback guard" in r["error"]
    assert r["error_details"]["position_raw"] == 2012
    assert servo.goal_count == 1 and servo.memory[40] == 0 and r["port_closed"]
    assert r["shutdown_attempts"][0]["torque_off_verified"]


@pytest.mark.parametrize("offset", [-114, 114])
def test_unloaded_sweep_bounded_target_and_cleanup(hold_adapter, offset):
    hold_adapter.ser.memory.update({56: 208, 57: 7})
    r = run_hold(hold_adapter, goal_offset_raw=offset, unloaded_sweep=True)
    assert r["target_raw"] == 2000 + offset
    assert r["observed_final_delta_raw"] == 0
    assert r["restoration"]["torque_off"] and r["port_closed"]

@pytest.mark.parametrize("arguments", [
    {"goal_offset_raw": 115, "unloaded_sweep": True},
    {"goal_offset_raw": -115, "unloaded_sweep": True},
    {"goal_offset_raw": 100, "unloaded_sweep": True, "output_limit": 1000},
    {"goal_offset_raw": 100, "unloaded_sweep": 1},
])
def test_unloaded_sweep_rejects_out_of_scope_before_open(hold_adapter, arguments):
    with pytest.raises(PhysicalGatewayError):
        run_hold(hold_adapter, **arguments)
    assert not hold_adapter.is_open and not hold_adapter.ser.frames

def test_unloaded_sweep_wrong_direction_stops(hold_adapter):
    servo = hold_adapter.ser
    servo.memory.update({56: 208, 57: 7})
    original_write = servo.write
    def wrong_direction(packet):
        result = original_write(packet)
        if list(packet)[4:6] == [3, 42]:
            servo.memory.update({56: 202, 57: 7})
        return result
    servo.write = wrong_direction
    r = run_hold(hold_adapter, goal_offset_raw=114, unloaded_sweep=True)
    assert r["status"] == "aborted" and "feedback guard" in r["error"]
    assert servo.goal_count == 1 and servo.memory[40] == 0 and r["port_closed"]


def test_unloaded_three_second_observation_and_cleanup(hold_adapter):
    hold_adapter.ser.memory.update({56: 208, 57: 7})
    r = run_hold(hold_adapter, goal_offset_raw=-114, unloaded_sweep=True, observation_seconds=3)
    assert r["status"] == "three_second_position_probe_completed"
    assert len([s for s in r["samples"] if s["stage"] == "hold"]) >= 1000
    assert r["restoration"]["torque_off"] and r["port_closed"]

@pytest.mark.parametrize("arguments", [{"observation_seconds": 3}, {"unloaded_sweep": True, "observation_seconds": 4}])
def test_observation_duration_rejects_before_open(hold_adapter, arguments):
    with pytest.raises(PhysicalGatewayError):
        run_hold(hold_adapter, **arguments)
    assert not hold_adapter.is_open and not hold_adapter.ser.frames

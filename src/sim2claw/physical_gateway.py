"""Single reviewed SO-101 path for bounded physical teleoperation.

The gateway owns every follower torque transition and fails closed on bus,
calibration, clamp, or shutdown errors. It captures an operator-confirmed
matched physical pose as a paired leader/follower zero, so pressing Start holds
the follower where it is instead of commanding it toward the leader's distinct
calibration coordinates.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from .scene import ROBOT_JOINTS


GATEWAY_SCHEMA = "sim2claw.so101_physical_gateway.v1"
BODY_EXCURSION_LIMIT_DEG = 90.0
WRIST_ROLL_EXCURSION_LIMIT_DEG = 180.0
GRIPPER_EXCURSION_LIMIT = 100.0
BODY_STEP_LIMIT_DEG = 4.0
GRIPPER_STEP_LIMIT = 8.0
STALL_TIMEOUT_SECONDS = 5.0
STALL_WARNING_SECONDS = 1.0
MIN_PROGRESS_DEG = 0.5
# Retained in receipts for compatibility; enforcement is time-based so changing
# the recorder sample rate no longer changes the physical fault threshold.
MAX_CONSECUTIVE_STALL_SAMPLES = 100
BODY_REGISTRATION_OFFSET_LIMIT_DEG = 12.0
GRIPPER_REGISTRATION_OFFSET_LIMIT = 10.0
SYNC_BODY_DELTA_LIMIT_DEG = 20.0
SYNC_GRIPPER_DELTA_LIMIT = 20.0
SYNC_DURATION_SECONDS = 2.5
SYNC_COMMAND_HZ = 40.0
SYNC_FINAL_TOLERANCE_DEG = 3.0
SYNC_LEADER_MOTION_TOLERANCE_DEG = 3.0
HOLD_SETTLE_SECONDS = 0.1
POST_HOLD_BODY_TOLERANCE_DEG = 3.0
POST_HOLD_GRIPPER_TOLERANCE = 5.0


class PhysicalGatewayError(RuntimeError):
    """Expected fail-closed gateway error."""


def action_vector(action: dict[str, float]) -> np.ndarray:
    return np.asarray(
        [float(action[f"{joint}.pos"]) for joint in ROBOT_JOINTS],
        dtype=np.float64,
    )


def shortest_delta_degrees(current: float, start: float) -> float:
    return (current - start + 180.0) % 360.0 - 180.0


def bounded_relative_target(
    leader: np.ndarray,
    leader_start: np.ndarray,
    follower_start: np.ndarray,
    *,
    lower_limits: np.ndarray | None = None,
    upper_limits: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    if leader.shape != (6,) or leader_start.shape != (6,) or follower_start.shape != (6,):
        raise PhysicalGatewayError("SO-101 gateway requires exactly six joint values.")
    delta = leader - leader_start
    delta[4] = shortest_delta_degrees(float(leader[4]), float(leader_start[4]))
    delta[:4] = np.clip(
        delta[:4],
        -BODY_EXCURSION_LIMIT_DEG,
        BODY_EXCURSION_LIMIT_DEG,
    )
    delta[4] = np.clip(
        delta[4],
        -WRIST_ROLL_EXCURSION_LIMIT_DEG,
        WRIST_ROLL_EXCURSION_LIMIT_DEG,
    )
    delta[5] = np.clip(
        delta[5],
        -GRIPPER_EXCURSION_LIMIT,
        GRIPPER_EXCURSION_LIMIT,
    )
    target = follower_start + delta
    if lower_limits is not None or upper_limits is not None:
        if lower_limits is None or upper_limits is None:
            raise PhysicalGatewayError("Both calibrated position-limit arrays are required.")
        if lower_limits.shape != (6,) or upper_limits.shape != (6,):
            raise PhysicalGatewayError("Calibrated position limits require six joint values.")
        target = np.clip(target, lower_limits, upper_limits)
        delta = target - follower_start
    return target, delta


def paired_pose_registration_report(
    leader: np.ndarray,
    follower: np.ndarray,
) -> dict[str, Any]:
    _finite(leader, "leader position")
    _finite(follower, "follower position")
    delta = leader - follower
    delta[4] = shortest_delta_degrees(float(leader[4]), float(follower[4]))
    maximum_body = float(np.max(np.abs(delta[:5])))
    gripper_error = float(abs(delta[5]))
    return {
        "paired_pose_registration_ready": (
            maximum_body <= BODY_REGISTRATION_OFFSET_LIMIT_DEG
            and gripper_error <= GRIPPER_REGISTRATION_OFFSET_LIMIT
        ),
        "calibration_offset_leader_minus_follower": delta.tolist(),
        "maximum_body_calibration_offset_degrees": maximum_body,
        "gripper_calibration_offset": gripper_error,
        "body_registration_offset_limit_degrees": BODY_REGISTRATION_OFFSET_LIMIT_DEG,
        "gripper_registration_offset_limit": GRIPPER_REGISTRATION_OFFSET_LIMIT,
    }


def _position_dict(values: np.ndarray) -> dict[str, float]:
    return {
        f"{joint}.pos": float(value)
        for joint, value in zip(ROBOT_JOINTS, values, strict=True)
    }


def _finite(values: np.ndarray, name: str) -> None:
    if values.shape != (6,) or not np.all(np.isfinite(values)):
        raise PhysicalGatewayError(f"Invalid six-joint {name} from the motor bus.")


@dataclass(frozen=True)
class GatewayIdentity:
    leader_port: str
    follower_port: str
    leader_calibration_sha256: str
    follower_calibration_sha256: str


DeviceFactory = Callable[[GatewayIdentity], tuple[Any, Any]]
SleepFunction = Callable[[float], None]


def _lerobot_devices(identity: GatewayIdentity) -> tuple[Any, Any]:
    from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig
    from lerobot.teleoperators.so_leader import SO101Leader, SO101LeaderConfig

    leader = SO101Leader(
        SO101LeaderConfig(
            port=identity.leader_port,
            id="so101_leader",
            use_degrees=True,
        )
    )
    follower = SO101Follower(
        SO101FollowerConfig(
            port=identity.follower_port,
            id="so101_follower",
            use_degrees=True,
            max_relative_target={
                "shoulder_pan": BODY_STEP_LIMIT_DEG,
                "shoulder_lift": BODY_STEP_LIMIT_DEG,
                "elbow_flex": BODY_STEP_LIMIT_DEG,
                "wrist_flex": BODY_STEP_LIMIT_DEG,
                "wrist_roll": BODY_STEP_LIMIT_DEG,
                "gripper": GRIPPER_STEP_LIMIT,
            },
            disable_torque_on_disconnect=True,
        )
    )
    return leader, follower


class SO101PhysicalGateway:
    """Torque-owning gateway for one identified leader/follower pair."""

    def __init__(
        self,
        identity: GatewayIdentity,
        *,
        device_factory: DeviceFactory = _lerobot_devices,
        sleep: SleepFunction = time.sleep,
    ):
        if identity.leader_port == identity.follower_port:
            raise PhysicalGatewayError("Leader and follower must use distinct buses.")
        self.identity = identity
        self.leader, self.follower = device_factory(identity)
        self.sleep = sleep
        self.leader_start: np.ndarray | None = None
        self.follower_start: np.ndarray | None = None
        self.lower_limits = np.asarray([-180.0] * 5 + [0.0], dtype=np.float64)
        self.upper_limits = np.asarray([180.0] * 5 + [100.0], dtype=np.float64)
        self.previous_actual: np.ndarray | None = None
        self.previous_time: float | None = None
        self.consecutive_rate_limited = 0
        self.consecutive_stall_samples = np.zeros(6, dtype=np.int64)
        self.stall_started_at = np.full(6, np.nan, dtype=np.float64)
        self.stall_anchor_actual = np.zeros(6, dtype=np.float64)
        self.torque_enabled = False
        self.connected = False

    def _calibrated_position_limits(self) -> tuple[np.ndarray, np.ndarray]:
        calibration = getattr(self.follower, "calibration", None)
        if not calibration:
            return self.lower_limits.copy(), self.upper_limits.copy()
        lower: list[float] = []
        upper: list[float] = []
        for joint in ROBOT_JOINTS:
            if joint == "gripper":
                lower.append(0.0)
                upper.append(100.0)
                continue
            entry = calibration[joint]
            range_min = float(
                entry["range_min"] if isinstance(entry, dict) else entry.range_min
            )
            range_max = float(
                entry["range_max"] if isinstance(entry, dict) else entry.range_max
            )
            midpoint = (range_min + range_max) / 2.0
            lower.append((range_min - midpoint) * 360.0 / 4095.0)
            upper.append((range_max - midpoint) * 360.0 / 4095.0)
        return np.asarray(lower), np.asarray(upper)

    def _connect_torque_off(self) -> None:
        try:
            self.leader.bus.connect()
            self.leader.bus.disable_torque()
            self.follower.bus.connect()
            self.follower.bus.disable_torque()
            self.connected = True
            if not self.leader.is_calibrated:
                raise PhysicalGatewayError(
                    "Leader calibration does not match the connected arm."
                )
            if not self.follower.is_calibrated:
                raise PhysicalGatewayError(
                    "Follower calibration does not match the connected arm."
                )
            self.leader.configure()
            self.leader.bus.disable_torque()
            self.follower.configure()
            self.follower.bus.disable_torque()
            self.lower_limits, self.upper_limits = self._calibrated_position_limits()
        except Exception:
            self.close()
            raise

    def open(
        self,
        *,
        enable_motion: bool,
        paired_pose_confirmed: bool = False,
    ) -> dict[str, Any]:
        self._connect_torque_off()
        leader = action_vector(self.leader.get_action())
        follower = action_vector(self.follower.get_observation())
        _finite(leader, "leader position")
        _finite(follower, "follower position")
        self.leader_start = leader
        self.follower_start = follower
        self.previous_actual = follower.copy()
        self.previous_time = time.monotonic()
        registration = paired_pose_registration_report(leader, follower)

        current = self._read_optional("Present_Current")
        torque = self._read_optional("Torque_Enable")
        if torque is not None and any(float(value) != 0.0 for value in torque.values()):
            raise PhysicalGatewayError("Follower torque was not off during preflight.")

        if enable_motion:
            if not paired_pose_confirmed:
                raise PhysicalGatewayError(
                    "Confirm that the arms share the same physical pose before registration."
                )
            if not registration["paired_pose_registration_ready"]:
                raise PhysicalGatewayError(
                    "Paired-pose registration is outside the calibration-offset guard: "
                    f"maximum body offset is "
                    f"{registration['maximum_body_calibration_offset_degrees']:.1f}° "
                    f"(limit {BODY_REGISTRATION_OFFSET_LIMIT_DEG:.1f}°)."
                )
            # Set the goal to the follower's current position before torque is
            # enabled. This intentionally commands no leader-to-follower sweep.
            self.follower.send_action(_position_dict(follower))
            self.follower.bus.enable_torque()
            self.torque_enabled = True
            self.sleep(HOLD_SETTLE_SECONDS)
            actual = action_vector(self.follower.get_observation())
            registered_leader = action_vector(self.leader.get_action())
            _finite(actual, "post-hold follower position")
            _finite(registered_leader, "registered leader position")
            registration = paired_pose_registration_report(registered_leader, actual)
            if not registration["paired_pose_registration_ready"]:
                self.follower.bus.disable_torque()
                self.torque_enabled = False
                raise PhysicalGatewayError(
                    "The paired pose changed before registration completed; torque released."
                )
            hold_residual = follower - actual
            hold_residual[4] = shortest_delta_degrees(
                float(follower[4]),
                float(actual[4]),
            )
            maximum_hold_residual = float(np.max(np.abs(hold_residual[:5])))
            gripper_hold_residual = float(abs(hold_residual[5]))
            if (
                maximum_hold_residual > POST_HOLD_BODY_TOLERANCE_DEG
                or gripper_hold_residual > POST_HOLD_GRIPPER_TOLERANCE
            ):
                self.follower.bus.disable_torque()
                self.torque_enabled = False
                raise PhysicalGatewayError(
                    "Follower moved while establishing the paired-pose hold; "
                    f"maximum residual {maximum_hold_residual:.1f}°. Torque released."
                )
            self.leader_start = registered_leader
            self.follower_start = actual
            self.previous_actual = actual.copy()
            self.previous_time = time.monotonic()
            self.stall_anchor_actual = actual.copy()
            self.stall_started_at[:] = np.nan
            registration_state = {
                "paired_pose_registered_before_recording": True,
                "start_alignment_motion_commanded": False,
                "leader_registration_degrees": registered_leader.tolist(),
                "follower_registration_degrees": actual.tolist(),
                "leader_to_follower_zero_offset_degrees": (
                    actual - registered_leader
                ).tolist(),
                "maximum_post_hold_body_error_degrees": maximum_hold_residual,
                "post_hold_gripper_error": gripper_hold_residual,
            }
        else:
            registration_state = {
                "paired_pose_registered_before_recording": False,
                "start_alignment_motion_commanded": False,
            }

        return {
            "schema_version": GATEWAY_SCHEMA,
            "control_mode": "relative_bounded",
            "leader_port": self.identity.leader_port,
            "follower_port": self.identity.follower_port,
            "leader_calibration_sha256": self.identity.leader_calibration_sha256,
            "follower_calibration_sha256": self.identity.follower_calibration_sha256,
            "leader_start_degrees": leader.tolist(),
            "follower_start_degrees": follower.tolist(),
            "current_raw": current,
            "body_excursion_limit_degrees": BODY_EXCURSION_LIMIT_DEG,
            "wrist_roll_excursion_limit_degrees": WRIST_ROLL_EXCURSION_LIMIT_DEG,
            "gripper_excursion_limit": GRIPPER_EXCURSION_LIMIT,
            "body_step_limit_degrees": BODY_STEP_LIMIT_DEG,
            "gripper_step_limit": GRIPPER_STEP_LIMIT,
            "maximum_consecutive_stall_samples": MAX_CONSECUTIVE_STALL_SAMPLES,
            "stall_timeout_seconds": STALL_TIMEOUT_SECONDS,
            "follower_calibrated_minimum": self.lower_limits.tolist(),
            "follower_calibrated_maximum": self.upper_limits.tolist(),
            "physical_follower_torque_enabled": self.torque_enabled,
            **registration,
            **registration_state,
        }

    def _read_optional(self, register: str) -> dict[str, float] | None:
        try:
            return {
                name: float(value)
                for name, value in self.follower.bus.sync_read(register).items()
            }
        except (KeyError, NotImplementedError):
            return None

    def sample(self, elapsed_seconds: float) -> dict[str, Any]:
        if (
            not self.connected
            or not self.torque_enabled
            or self.leader_start is None
            or self.follower_start is None
        ):
            raise PhysicalGatewayError("Physical gateway is not armed.")
        leader = action_vector(self.leader.get_action())
        requested, relative_delta = bounded_relative_target(
            leader,
            self.leader_start,
            self.follower_start,
            lower_limits=self.lower_limits,
            upper_limits=self.upper_limits,
        )
        sent = action_vector(self.follower.send_action(_position_dict(requested)))
        actual = action_vector(self.follower.get_observation())
        _finite(leader, "leader position")
        _finite(sent, "follower command")
        _finite(actual, "follower position")

        requested_sent_delta = requested - sent
        requested_sent_delta[4] = shortest_delta_degrees(
            float(requested[4]),
            float(sent[4]),
        )
        rate_limited_joints = np.abs(requested_sent_delta) > 1e-6
        rate_limited = bool(np.any(rate_limited_joints))
        self.consecutive_rate_limited = (
            self.consecutive_rate_limited + 1 if rate_limited else 0
        )
        previous = self.previous_actual if self.previous_actual is not None else actual
        requested_actual_delta = requested - actual
        requested_actual_delta[4] = shortest_delta_degrees(
            float(requested[4]),
            float(actual[4]),
        )
        target_error_after = np.abs(requested_actual_delta)
        far_from_target = target_error_after > np.asarray(
            [BODY_STEP_LIMIT_DEG * 1.5] * 5 + [GRIPPER_STEP_LIMIT * 1.5],
            dtype=np.float64,
        )
        stall_candidates = rate_limited_joints & far_from_target
        stall_durations = np.zeros(6, dtype=np.float64)
        for index, candidate in enumerate(stall_candidates.tolist()):
            if not candidate:
                self.stall_started_at[index] = np.nan
                self.stall_anchor_actual[index] = actual[index]
                self.consecutive_stall_samples[index] = 0
                continue
            progress = abs(actual[index] - self.stall_anchor_actual[index])
            if index == 4:
                progress = abs(
                    shortest_delta_degrees(
                        float(actual[index]),
                        float(self.stall_anchor_actual[index]),
                    )
                )
            if np.isnan(self.stall_started_at[index]) or progress >= MIN_PROGRESS_DEG:
                self.stall_started_at[index] = elapsed_seconds
                self.stall_anchor_actual[index] = actual[index]
                self.consecutive_stall_samples[index] = 1
            else:
                self.consecutive_stall_samples[index] += 1
            stall_durations[index] = max(
                0.0,
                elapsed_seconds - float(self.stall_started_at[index]),
            )
        stalled_joints = stall_candidates & (stall_durations >= STALL_WARNING_SECONDS)
        stalled = bool(np.any(stalled_joints))
        if np.any(stall_durations >= STALL_TIMEOUT_SECONDS):
            raise PhysicalGatewayError(
                "Follower made no measurable progress toward a commanded joint for "
                f"{STALL_TIMEOUT_SECONDS:.1f} seconds; torque released."
            )

        now = time.monotonic()
        dt = max(now - (self.previous_time or now), 1e-6)
        actual_delta = actual - previous
        actual_delta[4] = shortest_delta_degrees(
            float(actual[4]),
            float(previous[4]),
        )
        velocity = actual_delta / dt
        sent_actual_delta = sent - actual
        sent_actual_delta[4] = shortest_delta_degrees(
            float(sent[4]),
            float(actual[4]),
        )
        self.previous_actual = actual.copy()
        self.previous_time = now
        return {
            "elapsed_seconds": elapsed_seconds,
            "leader_target_degrees": leader.tolist(),
            "leader_relative_delta": relative_delta.tolist(),
            "follower_requested_degrees": requested.tolist(),
            "follower_command_degrees": sent.tolist(),
            "follower_actual_position_degrees": actual.tolist(),
            "follower_actual_velocity_degrees_s": velocity.tolist(),
            "leader_follower_error_degrees": sent_actual_delta.tolist(),
            "selected_piece_pose_world": None,
            "continuous_target_pose_world": None,
            "pose_inputs_available": False,
            "available_motor_current_raw": self._read_optional("Present_Current"),
            "physical_follower_torque_enabled": True,
            "safety_clamped": rate_limited,
            "rate_limited": rate_limited,
            "consecutive_rate_limited_samples": self.consecutive_rate_limited,
            "stalled": stalled,
            "stalled_joints": [
                joint
                for joint, is_stalled in zip(
                    ROBOT_JOINTS,
                    stalled_joints.tolist(),
                    strict=True,
                )
                if is_stalled
            ],
            "consecutive_stall_samples_by_joint": {
                joint: int(count)
                for joint, count in zip(
                    ROBOT_JOINTS,
                    self.consecutive_stall_samples,
                    strict=True,
                )
            },
            "stall_duration_seconds_by_joint": {
                joint: float(duration)
                for joint, duration in zip(
                    ROBOT_JOINTS,
                    stall_durations,
                    strict=True,
                )
            },
        }

    def synchronize_to_leader(self) -> dict[str, Any]:
        """Ramp a nearby follower to the leader pose and finish with torque off."""

        self._connect_torque_off()
        leader = action_vector(self.leader.get_action())
        follower = action_vector(self.follower.get_observation())
        _finite(leader, "leader sync position")
        _finite(follower, "follower sync position")
        delta = leader - follower
        delta[4] = shortest_delta_degrees(float(leader[4]), float(follower[4]))
        maximum_body_delta = float(np.max(np.abs(delta[:5])))
        gripper_delta = float(abs(delta[5]))
        if (
            maximum_body_delta > SYNC_BODY_DELTA_LIMIT_DEG
            or gripper_delta > SYNC_GRIPPER_DELTA_LIMIT
        ):
            raise PhysicalGatewayError(
                "Sync requires the arms to already be in roughly the same pose: "
                f"maximum body delta {maximum_body_delta:.1f}° "
                f"(limit {SYNC_BODY_DELTA_LIMIT_DEG:.1f}°)."
            )
        target = follower + delta
        calibrated_target = np.clip(target, self.lower_limits, self.upper_limits)
        if np.any(np.abs(calibrated_target - target) > 0.5):
            raise PhysicalGatewayError(
                "Leader pose is outside the follower's calibrated range; sync was not armed."
            )

        torque = self._read_optional("Torque_Enable")
        if torque is not None and any(float(value) != 0.0 for value in torque.values()):
            raise PhysicalGatewayError("Follower torque was not off before sync.")
        self.follower.send_action(_position_dict(follower))
        self.follower.bus.enable_torque()
        self.torque_enabled = True
        self.sleep(HOLD_SETTLE_SECONDS)
        held = action_vector(self.follower.get_observation())
        hold_residual = follower - held
        hold_residual[4] = shortest_delta_degrees(
            float(follower[4]),
            float(held[4]),
        )
        if (
            float(np.max(np.abs(hold_residual[:5]))) > POST_HOLD_BODY_TOLERANCE_DEG
            or abs(float(hold_residual[5])) > POST_HOLD_GRIPPER_TOLERANCE
        ):
            raise PhysicalGatewayError(
                "Follower moved unexpectedly while establishing the sync hold."
            )

        steps = max(1, round(SYNC_DURATION_SECONDS * SYNC_COMMAND_HZ))
        for index in range(1, steps + 1):
            fraction = index / steps
            smooth = fraction * fraction * (3.0 - 2.0 * fraction)
            command = follower + smooth * delta
            self.follower.send_action(_position_dict(command))
            self.sleep(1.0 / SYNC_COMMAND_HZ)
        self.follower.send_action(_position_dict(target))
        self.sleep(0.3)

        actual = action_vector(self.follower.get_observation())
        final_leader = action_vector(self.leader.get_action())
        leader_motion = final_leader - leader
        leader_motion[4] = shortest_delta_degrees(
            float(final_leader[4]),
            float(leader[4]),
        )
        if (
            float(np.max(np.abs(leader_motion[:5]))) > SYNC_LEADER_MOTION_TOLERANCE_DEG
            or abs(float(leader_motion[5])) > POST_HOLD_GRIPPER_TOLERANCE
        ):
            raise PhysicalGatewayError(
                "Leader moved during sync; torque released before accepting the pair."
            )
        residual = target - actual
        residual[4] = shortest_delta_degrees(float(target[4]), float(actual[4]))
        maximum_residual = float(np.max(np.abs(residual[:5])))
        gripper_residual = float(abs(residual[5]))
        if (
            maximum_residual > SYNC_FINAL_TOLERANCE_DEG
            or gripper_residual > POST_HOLD_GRIPPER_TOLERANCE
        ):
            raise PhysicalGatewayError(
                "Follower did not reach the bounded sync target; torque released."
            )
        registration = paired_pose_registration_report(final_leader, actual)
        return {
            "schema_version": GATEWAY_SCHEMA,
            "control_mode": "bounded_leader_pose_sync",
            "leader_port": self.identity.leader_port,
            "follower_port": self.identity.follower_port,
            "leader_calibration_sha256": self.identity.leader_calibration_sha256,
            "follower_calibration_sha256": self.identity.follower_calibration_sha256,
            "leader_sync_target_degrees": target.tolist(),
            "follower_sync_start_degrees": follower.tolist(),
            "follower_sync_actual_degrees": actual.tolist(),
            "maximum_sync_travel_degrees": maximum_body_delta,
            "maximum_sync_residual_degrees": maximum_residual,
            "sync_duration_seconds": SYNC_DURATION_SECONDS,
            "sync_motion_commanded": maximum_body_delta > 0.25 or gripper_delta > 0.5,
            "physical_follower_torque_enabled": True,
            **registration,
        }

    def close(self) -> None:
        errors: list[Exception] = []
        for device in (self.follower, self.leader):
            bus = getattr(device, "bus", None)
            if bus is None:
                continue
            try:
                if bus.is_connected:
                    bus.disable_torque()
            except Exception as error:  # retain all shutdown attempts
                errors.append(error)
            try:
                if bus.is_connected:
                    bus.disconnect(True)
            except TypeError:
                try:
                    if bus.is_connected:
                        bus.disconnect()
                except Exception as error:
                    errors.append(error)
            except Exception as error:
                errors.append(error)
        self.torque_enabled = False
        self.connected = False
        if errors:
            raise PhysicalGatewayError(
                "Gateway shutdown reported: "
                + "; ".join(str(error) for error in errors)
            )


def inspect_physical_gateway(
    identity: GatewayIdentity,
    *,
    device_factory: DeviceFactory = _lerobot_devices,
) -> dict[str, Any]:
    gateway = SO101PhysicalGateway(identity, device_factory=device_factory)
    try:
        report = gateway.open(enable_motion=False)
        report["passed"] = True
        return report
    finally:
        gateway.close()


def synchronize_physical_gateway(
    identity: GatewayIdentity,
    *,
    device_factory: DeviceFactory = _lerobot_devices,
    sleep: SleepFunction = time.sleep,
) -> dict[str, Any]:
    gateway = SO101PhysicalGateway(
        identity,
        device_factory=device_factory,
        sleep=sleep,
    )
    report: dict[str, Any] | None = None
    try:
        report = gateway.synchronize_to_leader()
    finally:
        gateway.close()
    report["physical_follower_torque_enabled"] = False
    report["sync_completed_torque_off"] = True
    report["passed"] = True
    return report

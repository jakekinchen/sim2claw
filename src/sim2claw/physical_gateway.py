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


GATEWAY_SCHEMA = "sim2claw.so101_physical_gateway.v2"
BODY_EXCURSION_LIMIT_DEG = 90.0
WRIST_ROLL_EXCURSION_LIMIT_DEG = 180.0
GRIPPER_EXCURSION_LIMIT = 100.0
BODY_COMMAND_RATE_LIMIT_DEG_S = 60.0
WRIST_ROLL_COMMAND_RATE_LIMIT_DEG_S = 90.0
GRIPPER_COMMAND_RATE_LIMIT_S = 100.0
BODY_TRACKING_ERROR_LIMIT_DEG = 6.0
SHOULDER_LIFT_TRACKING_ERROR_LIMIT_DEG = 8.0
WRIST_ROLL_TRACKING_ERROR_LIMIT_DEG = 8.0
GRIPPER_TRACKING_ERROR_LIMIT = 12.0
BODY_STALL_ERROR_DEG = 3.0
GRIPPER_STALL_ERROR = 6.0
MAX_CONTROL_INTERVAL_SECONDS = 0.1
CURRENT_TELEMETRY_HZ = 5.0
# The Feetech bus can occasionally miss a single group-read response while the
# serial controller is otherwise healthy.  Give motion-critical reads a short,
# bounded recovery window.  A controller reset/disconnect still exhausts this
# window quickly and follows the existing torque-off shutdown path.
BUS_READ_RETRIES = 3
BUS_RETRY_DELAY_SECONDS = 0.01
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

    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details


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
    if (
        leader.shape != (6,)
        or leader_start.shape != (6,)
        or follower_start.shape != (6,)
    ):
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
            raise PhysicalGatewayError(
                "Both calibrated position-limit arrays are required."
            )
        if lower_limits.shape != (6,) or upper_limits.shape != (6,):
            raise PhysicalGatewayError(
                "Calibrated position limits require six joint values."
            )
        target = np.clip(target, lower_limits, upper_limits)
        delta = target - follower_start
    return target, delta


def slew_limited_target(
    requested: np.ndarray,
    previous_command: np.ndarray,
    previous_actual: np.ndarray,
    dt_seconds: float,
    *,
    lower_limits: np.ndarray,
    upper_limits: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Advance toward the full target without building an unsafe error backlog.

    The speed limit is based on elapsed time and the last command, rather than
    repeatedly clipping the target against the measured pose. A separate
    command-to-actual bound leaves enough shoulder-lift error to overcome its
    load while preventing a stalled joint from accumulating an arbitrary jump.
    """

    for values, name in (
        (requested, "requested target"),
        (previous_command, "previous command"),
        (previous_actual, "previous actual position"),
        (lower_limits, "lower limits"),
        (upper_limits, "upper limits"),
    ):
        _finite(values, name)
    if not np.isfinite(dt_seconds) or dt_seconds < 0.0:
        raise PhysicalGatewayError("Control interval must be finite and non-negative.")

    rate_limits = np.asarray(
        [
            BODY_COMMAND_RATE_LIMIT_DEG_S,
            BODY_COMMAND_RATE_LIMIT_DEG_S,
            BODY_COMMAND_RATE_LIMIT_DEG_S,
            BODY_COMMAND_RATE_LIMIT_DEG_S,
            WRIST_ROLL_COMMAND_RATE_LIMIT_DEG_S,
            GRIPPER_COMMAND_RATE_LIMIT_S,
        ],
        dtype=np.float64,
    )
    tracking_limits = np.asarray(
        [
            BODY_TRACKING_ERROR_LIMIT_DEG,
            SHOULDER_LIFT_TRACKING_ERROR_LIMIT_DEG,
            BODY_TRACKING_ERROR_LIMIT_DEG,
            BODY_TRACKING_ERROR_LIMIT_DEG,
            WRIST_ROLL_TRACKING_ERROR_LIMIT_DEG,
            GRIPPER_TRACKING_ERROR_LIMIT,
        ],
        dtype=np.float64,
    )
    bounded_dt = min(dt_seconds, MAX_CONTROL_INTERVAL_SECONDS)
    requested_delta = requested - previous_command
    requested_delta[4] = shortest_delta_degrees(
        float(requested[4]),
        float(previous_command[4]),
    )
    rate_limited_delta = np.clip(
        requested_delta,
        -rate_limits * bounded_dt,
        rate_limits * bounded_dt,
    )
    rate_limited = previous_command + rate_limited_delta

    tracking_delta = rate_limited - previous_actual
    tracking_delta[4] = shortest_delta_degrees(
        float(rate_limited[4]),
        float(previous_actual[4]),
    )
    bounded_tracking_delta = np.clip(
        tracking_delta,
        -tracking_limits,
        tracking_limits,
    )
    command = np.clip(
        previous_actual + bounded_tracking_delta,
        lower_limits,
        upper_limits,
    )
    return command, rate_limits, tracking_limits


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


def _pose_diagnostics(
    stage: str,
    *,
    leader: np.ndarray | None = None,
    follower: np.ndarray | None = None,
    **extra: Any,
) -> dict[str, Any]:
    details: dict[str, Any] = {"stage": stage, **extra}
    if leader is not None:
        details["leader_degrees"] = leader.tolist()
    if follower is not None:
        details["follower_degrees"] = follower.tolist()
    if leader is not None and follower is not None:
        details.update(paired_pose_registration_report(leader, follower))
    return details


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
            # The gateway owns rate and tracking-error bounds. LeRobot's
            # present-position clamp can permanently strand a loaded joint.
            max_relative_target=None,
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
        clock: Callable[[], float] = time.monotonic,
        configure_devices: bool = True,
        current_telemetry_hz: float = CURRENT_TELEMETRY_HZ,
    ):
        if identity.leader_port == identity.follower_port:
            raise PhysicalGatewayError("Leader and follower must use distinct buses.")
        self.identity = identity
        self.leader, self.follower = device_factory(identity)
        self.sleep = sleep
        self.clock = clock
        self.configure_devices = configure_devices
        if current_telemetry_hz < 0.0:
            raise PhysicalGatewayError("Current telemetry rate cannot be negative.")
        self.current_telemetry_hz = float(current_telemetry_hz)
        self.leader_start: np.ndarray | None = None
        self.follower_start: np.ndarray | None = None
        self.lower_limits = np.asarray([-180.0] * 5 + [0.0], dtype=np.float64)
        self.upper_limits = np.asarray([180.0] * 5 + [100.0], dtype=np.float64)
        self.previous_actual: np.ndarray | None = None
        self.previous_command: np.ndarray | None = None
        self.previous_elapsed_seconds = 0.0
        self.previous_time: float | None = None
        self.consecutive_rate_limited = 0
        self.consecutive_stall_samples = np.zeros(6, dtype=np.int64)
        self.stall_started_at = np.full(6, np.nan, dtype=np.float64)
        self.stall_anchor_actual = np.zeros(6, dtype=np.float64)
        self.stall_command_direction = np.zeros(6, dtype=np.float64)
        self.current_telemetry: dict[str, float] | None = None
        self.current_telemetry_elapsed: float | None = None
        self.current_telemetry_read_started_monotonic: float | None = None
        self.current_telemetry_read_completed_monotonic: float | None = None
        self.current_telemetry_missed_samples = 0
        self.current_telemetry_stale = False
        self.bus_read_retries_total = 0
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
            self.leader.bus.disable_torque(num_retry=BUS_READ_RETRIES)
            self.follower.bus.connect()
            self.follower.bus.disable_torque(num_retry=BUS_READ_RETRIES)
            self.connected = True
            if not self.leader.is_calibrated:
                raise PhysicalGatewayError(
                    "Leader calibration does not match the connected arm."
                )
            if not self.follower.is_calibrated:
                raise PhysicalGatewayError(
                    "Follower calibration does not match the connected arm."
                )
            if self.configure_devices:
                self.leader.configure()
                self.leader.bus.disable_torque(num_retry=BUS_READ_RETRIES)
                self.follower.configure()
                self.follower.bus.disable_torque(num_retry=BUS_READ_RETRIES)
            else:
                operating_modes = self.follower.bus.sync_read(
                    "Operating_Mode",
                    normalize=False,
                    num_retry=BUS_READ_RETRIES,
                )
                if any(int(value) != 0 for value in operating_modes.values()):
                    raise PhysicalGatewayError(
                        "Follower replay requires every motor to remain in position mode."
                    )
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
        # Startup pose reads are motion-critical too.  Route them through the
        # same bounded retry path used during sampling instead of allowing one
        # missed status packet to abort an otherwise healthy replay.
        leader = self._motion_read("initial leader position", self.leader.get_action)
        follower = self._motion_read(
            "initial follower position", self.follower.get_observation
        )
        self.leader_start = leader
        self.follower_start = follower
        self.previous_actual = follower.copy()
        self.previous_command = follower.copy()
        self.previous_elapsed_seconds = 0.0
        self.previous_time = self.clock()
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
                    f"(limit {BODY_REGISTRATION_OFFSET_LIMIT_DEG:.1f}°).",
                    details=_pose_diagnostics(
                        "initial_paired_pose_registration",
                        leader=leader,
                        follower=follower,
                    ),
                )
            # Set the goal to the follower's current position before torque is
            # enabled. This intentionally commands no leader-to-follower sweep.
            self.follower.send_action(_position_dict(follower))
            self.follower.bus.enable_torque(num_retry=BUS_READ_RETRIES)
            self.torque_enabled = True
            self.sleep(HOLD_SETTLE_SECONDS)
            actual = self._motion_read(
                "post-hold follower position", self.follower.get_observation
            )
            registered_leader = self._motion_read(
                "registered leader position", self.leader.get_action
            )
            registration = paired_pose_registration_report(registered_leader, actual)
            if not registration["paired_pose_registration_ready"]:
                self.follower.bus.disable_torque(num_retry=BUS_READ_RETRIES)
                self.torque_enabled = False
                raise PhysicalGatewayError(
                    "The paired pose changed before registration completed; torque released.",
                    details=_pose_diagnostics(
                        "post_hold_paired_pose_registration",
                        leader=registered_leader,
                        follower=actual,
                    ),
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
                self.follower.bus.disable_torque(num_retry=BUS_READ_RETRIES)
                self.torque_enabled = False
                raise PhysicalGatewayError(
                    "Follower moved while establishing the paired-pose hold; "
                    f"maximum residual {maximum_hold_residual:.1f}°. Torque released.",
                    details=_pose_diagnostics(
                        "post_hold_follower_drift",
                        leader=registered_leader,
                        follower=actual,
                        follower_hold_start_degrees=follower.tolist(),
                        follower_hold_residual_degrees=hold_residual.tolist(),
                    ),
                )
            self.leader_start = registered_leader
            self.follower_start = actual
            self.previous_actual = actual.copy()
            self.previous_command = actual.copy()
            self.previous_elapsed_seconds = 0.0
            self.previous_time = self.clock()
            self.stall_anchor_actual = actual.copy()
            self.stall_started_at[:] = np.nan
            self.stall_command_direction[:] = 0.0
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
            "control_mode": "relative_time_slew_bounded_tracking",
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
            "body_command_rate_limit_degrees_s": BODY_COMMAND_RATE_LIMIT_DEG_S,
            "wrist_roll_command_rate_limit_degrees_s": WRIST_ROLL_COMMAND_RATE_LIMIT_DEG_S,
            "gripper_command_rate_limit_s": GRIPPER_COMMAND_RATE_LIMIT_S,
            "body_tracking_error_limit_degrees": BODY_TRACKING_ERROR_LIMIT_DEG,
            "shoulder_lift_tracking_error_limit_degrees": (
                SHOULDER_LIFT_TRACKING_ERROR_LIMIT_DEG
            ),
            "wrist_roll_tracking_error_limit_degrees": (
                WRIST_ROLL_TRACKING_ERROR_LIMIT_DEG
            ),
            "gripper_tracking_error_limit": GRIPPER_TRACKING_ERROR_LIMIT,
            "maximum_consecutive_stall_samples": MAX_CONSECUTIVE_STALL_SAMPLES,
            "stall_timeout_seconds": STALL_TIMEOUT_SECONDS,
            "follower_calibrated_minimum": self.lower_limits.tolist(),
            "follower_calibrated_maximum": self.upper_limits.tolist(),
            "physical_follower_torque_enabled": self.torque_enabled,
            "device_configuration_rewritten": self.configure_devices,
            **registration,
            **registration_state,
        }

    def _read_optional(self, register: str) -> dict[str, float] | None:
        try:
            return {
                name: float(value)
                for name, value in self.follower.bus.sync_read(
                    register,
                    num_retry=BUS_READ_RETRIES,
                ).items()
            }
        except (KeyError, NotImplementedError):
            return None

    def sample_read_only(self) -> dict[str, Any]:
        """Read both calibrated poses while preserving the torque-off contract."""

        if not self.connected or self.torque_enabled:
            raise PhysicalGatewayError(
                "Read-only telemetry requires one connected, torque-off gateway session."
            )
        torque = self._read_optional("Torque_Enable")
        if torque is not None and any(float(value) != 0.0 for value in torque.values()):
            raise PhysicalGatewayError(
                "Follower torque changed during read-only telemetry; the session was stopped."
            )
        leader = self._motion_read("read-only leader position", self.leader.get_action)
        follower = self._motion_read(
            "read-only follower position", self.follower.get_observation
        )
        return {
            "schema_version": "sim2claw.so101_read_only_telemetry.v1",
            "leader_degrees": leader.tolist(),
            "follower_degrees": follower.tolist(),
            "available_motor_current_raw": self._read_optional("Present_Current"),
            "physical_follower_torque_enabled": False,
            "physical_motion_commanded": False,
            **paired_pose_registration_report(leader, follower),
        }

    def rebase_relative_origin(
        self,
        *,
        leader_origin: np.ndarray,
        follower_origin: np.ndarray,
    ) -> dict[str, Any]:
        """Admit a reached replay start as the unchanged excursion origin.

        A guarded replay may begin a few degrees away from its saved first
        command. After the normal rate-limited pre-roll reaches that command,
        rebase the 90-degree envelope to the episode's own start pose. This
        does not widen calibrated limits or excursion bounds.
        """

        if (
            not self.connected
            or not self.torque_enabled
            or self.previous_command is None
            or self.previous_actual is None
        ):
            raise PhysicalGatewayError("Replay-origin rebase requires an armed gateway.")
        _finite(leader_origin, "replay leader origin")
        _finite(follower_origin, "replay follower origin")
        calibrated_origin = np.clip(
            follower_origin,
            self.lower_limits,
            self.upper_limits,
        )
        if np.any(np.abs(calibrated_origin - follower_origin) > 0.5):
            raise PhysicalGatewayError(
                "Replay start pose is outside the follower calibration envelope."
            )
        actual = self._motion_read(
            "replay-origin follower position",
            self.follower.get_observation,
        )
        residual = follower_origin - actual
        residual[4] = shortest_delta_degrees(
            float(follower_origin[4]),
            float(actual[4]),
        )
        maximum_body_residual = float(np.max(np.abs(residual[:4])))
        wrist_roll_residual = abs(float(residual[4]))
        gripper_residual = abs(float(residual[5]))
        if (
            maximum_body_residual > SHOULDER_LIFT_TRACKING_ERROR_LIMIT_DEG
            or wrist_roll_residual > WRIST_ROLL_TRACKING_ERROR_LIMIT_DEG
            or gripper_residual > GRIPPER_TRACKING_ERROR_LIMIT
        ):
            raise PhysicalGatewayError(
                "Follower did not reach the guarded replay start closely enough to "
                "rebase the excursion envelope.",
                details={
                    "stage": "replay_origin_rebase",
                    "requested_follower_origin_degrees": follower_origin.tolist(),
                    "actual_follower_degrees": actual.tolist(),
                    "residual_degrees": residual.tolist(),
                },
            )
        self.leader_start = leader_origin.copy()
        self.follower_start = follower_origin.copy()
        self.previous_actual = actual.copy()
        self.stall_anchor_actual = actual.copy()
        self.stall_started_at[:] = np.nan
        self.stall_command_direction[:] = 0.0
        self.consecutive_stall_samples[:] = 0
        return {
            "schema_version": GATEWAY_SCHEMA,
            "control_mode": "guarded_replay_episode_origin_rebase",
            "leader_origin_degrees": leader_origin.tolist(),
            "follower_origin_degrees": follower_origin.tolist(),
            "actual_follower_degrees": actual.tolist(),
            "origin_residual_degrees": residual.tolist(),
            "body_excursion_limit_degrees": BODY_EXCURSION_LIMIT_DEG,
            "wrist_roll_excursion_limit_degrees": WRIST_ROLL_EXCURSION_LIMIT_DEG,
            "gripper_excursion_limit": GRIPPER_EXCURSION_LIMIT,
            "physical_follower_torque_enabled": True,
        }

    def _runtime_current(
        self, elapsed_seconds: float
    ) -> tuple[dict[str, float] | None, bool, bool]:
        if self.current_telemetry_hz == 0.0:
            return None, True, False
        period = 1.0 / self.current_telemetry_hz
        due = (
            self.current_telemetry_elapsed is None
            or elapsed_seconds - self.current_telemetry_elapsed >= period
        )
        if not due:
            return self.current_telemetry, self.current_telemetry_stale, False
        self.current_telemetry_read_started_monotonic = self.clock()
        try:
            self.current_telemetry = self._read_optional("Present_Current")
            self.current_telemetry_read_completed_monotonic = self.clock()
            self.current_telemetry_elapsed = elapsed_seconds
            self.current_telemetry_missed_samples = 0
            self.current_telemetry_stale = False
            return self.current_telemetry, False, True
        except (ConnectionError, OSError):
            # Current is diagnostic telemetry. Motion-critical position reads
            # still fail closed, but one missing current packet must not end an
            # otherwise healthy recording.
            self.current_telemetry_elapsed = elapsed_seconds
            self.current_telemetry_read_completed_monotonic = self.clock()
            self.current_telemetry_missed_samples += 1
            self.current_telemetry_stale = True
            return self.current_telemetry, True, True

    def _motion_read(
        self,
        name: str,
        operation: Callable[[], dict[str, float]],
    ) -> np.ndarray:
        last_error: ConnectionError | OSError | None = None
        for attempt in range(BUS_READ_RETRIES + 1):
            try:
                values = action_vector(operation())
                _finite(values, name)
                return values
            except (ConnectionError, OSError) as error:
                last_error = error
                if attempt >= BUS_READ_RETRIES:
                    raise PhysicalGatewayError(
                        f"Motor-bus read for {name} failed after "
                        f"{BUS_READ_RETRIES + 1} gateway attempts. The follower "
                        "USB controller may have reset or disconnected; motion was "
                        "stopped and the gateway will release torque.",
                        details={
                            "stage": "motor_bus_read",
                            "read_name": name,
                            "gateway_attempts": BUS_READ_RETRIES + 1,
                            "follower_port": self.identity.follower_port,
                            "underlying_error_type": type(error).__name__,
                            "underlying_error": str(error),
                        },
                    ) from error
                self.bus_read_retries_total += 1
                self.sleep(BUS_RETRY_DELAY_SECONDS)
        assert last_error is not None
        raise last_error

    def sample(self, elapsed_seconds: float) -> dict[str, Any]:
        if (
            not self.connected
            or not self.torque_enabled
            or self.leader_start is None
            or self.follower_start is None
            or self.previous_command is None
            or self.previous_actual is None
        ):
            raise PhysicalGatewayError("Physical gateway is not armed.")
        sample_started_monotonic = self.clock()
        retries_before = self.bus_read_retries_total
        leader = self._motion_read("leader position", self.leader.get_action)
        leader_read_completed_monotonic = self.clock()
        requested, relative_delta = bounded_relative_target(
            leader,
            self.leader_start,
            self.follower_start,
            lower_limits=self.lower_limits,
            upper_limits=self.upper_limits,
        )
        control_dt = max(0.0, elapsed_seconds - self.previous_elapsed_seconds)
        command, rate_limits, tracking_limits = slew_limited_target(
            requested,
            self.previous_command,
            self.previous_actual,
            control_dt,
            lower_limits=self.lower_limits,
            upper_limits=self.upper_limits,
        )
        command_call_started_monotonic = self.clock()
        sent = action_vector(self.follower.send_action(_position_dict(command)))
        command_call_completed_monotonic = self.clock()
        actual = self._motion_read("follower position", self.follower.get_observation)
        position_read_completed_monotonic = self.clock()
        _finite(sent, "follower command")

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
        previous = self.previous_actual
        sent_actual_delta = sent - actual
        sent_actual_delta[4] = shortest_delta_degrees(
            float(sent[4]),
            float(actual[4]),
        )
        stall_thresholds = np.asarray(
            [BODY_STALL_ERROR_DEG] * 5 + [GRIPPER_STALL_ERROR],
            dtype=np.float64,
        )
        stall_candidates = np.abs(sent_actual_delta) > stall_thresholds
        # A position-controlled gripper is expected to retain an object at a
        # steady offset from its requested closed position. Treating that
        # contact deflection as a motion stall releases every joint and drops
        # the grasp even while the arm is tracking normally. Keep the
        # deflection observable, but reserve the torque-off stall guard for
        # body joints; bus-read and tracking-error guards still fail closed for
        # the gripper.
        gripper_contact_hold = bool(stall_candidates[5])
        stall_candidates[5] = False
        stall_directions = np.sign(sent_actual_delta)
        stall_durations = np.zeros(6, dtype=np.float64)
        for index, candidate in enumerate(stall_candidates.tolist()):
            if not candidate:
                self.stall_started_at[index] = np.nan
                self.stall_anchor_actual[index] = actual[index]
                self.stall_command_direction[index] = 0.0
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
            direction_changed = (
                self.stall_command_direction[index] != 0.0
                and stall_directions[index] != self.stall_command_direction[index]
            )
            if (
                np.isnan(self.stall_started_at[index])
                or direction_changed
                or progress >= MIN_PROGRESS_DEG
            ):
                self.stall_started_at[index] = elapsed_seconds
                self.stall_anchor_actual[index] = actual[index]
                self.stall_command_direction[index] = stall_directions[index]
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

        now = self.clock()
        dt = max(now - (self.previous_time or now), 1e-6)
        actual_delta = actual - previous
        actual_delta[4] = shortest_delta_degrees(
            float(actual[4]),
            float(previous[4]),
        )
        velocity = actual_delta / dt
        current, current_stale, current_refreshed = self._runtime_current(
            elapsed_seconds
        )
        sample_completed_monotonic = self.clock()
        self.previous_actual = actual.copy()
        self.previous_command = sent.copy()
        self.previous_elapsed_seconds = elapsed_seconds
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
            "available_motor_current_raw": current,
            "current_telemetry_hz": self.current_telemetry_hz,
            "current_telemetry_elapsed_seconds": self.current_telemetry_elapsed,
            "current_telemetry_sample_age_seconds": (
                None
                if self.current_telemetry_elapsed is None
                else max(0.0, elapsed_seconds - self.current_telemetry_elapsed)
            ),
            "current_telemetry_stale": current_stale,
            "current_telemetry_refreshed_this_sample": current_refreshed,
            "current_telemetry_missed_samples": self.current_telemetry_missed_samples,
            "observability_timestamps": {
                "clock_source": "python_time_monotonic_same_host_process",
                "sample_started_monotonic_seconds": sample_started_monotonic,
                "leader_read_completed_monotonic_seconds": (
                    leader_read_completed_monotonic
                ),
                "follower_command_call_started_monotonic_seconds": (
                    command_call_started_monotonic
                ),
                "follower_command_call_completed_monotonic_seconds": (
                    command_call_completed_monotonic
                ),
                "follower_position_read_completed_monotonic_seconds": (
                    position_read_completed_monotonic
                ),
                "current_read_started_monotonic_seconds": (
                    self.current_telemetry_read_started_monotonic
                    if current_refreshed
                    else None
                ),
                "current_read_completed_monotonic_seconds": (
                    self.current_telemetry_read_completed_monotonic
                    if current_refreshed
                    else None
                ),
                "sample_completed_monotonic_seconds": sample_completed_monotonic,
                "actuator_application_or_ack_timestamp_available": False,
                "device_clock_synchronized": False,
            },
            "bus_read_retries_this_sample": (
                self.bus_read_retries_total - retries_before
            ),
            "bus_read_retries_total": self.bus_read_retries_total,
            "physical_follower_torque_enabled": True,
            "safety_clamped": rate_limited,
            "rate_limited": rate_limited,
            "consecutive_rate_limited_samples": self.consecutive_rate_limited,
            "command_rate_limits_per_second": rate_limits.tolist(),
            "tracking_error_limits": tracking_limits.tolist(),
            "control_dt_seconds": min(control_dt, MAX_CONTROL_INTERVAL_SECONDS),
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
            "gripper_contact_hold": gripper_contact_hold,
            "gripper_contact_deflection": float(abs(sent_actual_delta[5])),
        }

    def synchronize_to_leader(self) -> dict[str, Any]:
        """Ramp a nearby follower to the leader pose while retaining torque ownership."""

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
            if maximum_body_delta > SYNC_BODY_DELTA_LIMIT_DEG:
                limiting_index = int(np.argmax(np.abs(delta[:5])))
                limiting_joint = ROBOT_JOINTS[limiting_index]
                mismatch = (
                    f"{limiting_joint} delta {abs(float(delta[limiting_index])):.1f}° "
                    f"(limit {SYNC_BODY_DELTA_LIMIT_DEG:.1f}°; "
                    f"leader {leader[limiting_index]:.1f}°, "
                    f"follower {follower[limiting_index]:.1f}°)"
                )
            else:
                limiting_joint = ROBOT_JOINTS[5]
                mismatch = (
                    f"gripper delta {gripper_delta:.1f} "
                    f"(limit {SYNC_GRIPPER_DELTA_LIMIT:.1f}; "
                    f"leader {leader[5]:.1f}, follower {follower[5]:.1f})"
                )
            raise PhysicalGatewayError(
                "Sync requires the arms to already be in roughly the same pose: "
                f"{mismatch}. Keep follower torque off, physically match "
                f"{limiting_joint}, then retry Sync.",
                details=_pose_diagnostics(
                    "sync_initial_pose",
                    leader=leader,
                    follower=follower,
                    limiting_joint=limiting_joint,
                ),
            )
        target = follower + delta
        calibrated_target = np.clip(target, self.lower_limits, self.upper_limits)
        if np.any(np.abs(calibrated_target - target) > 0.5):
            raise PhysicalGatewayError(
                "Leader pose is outside the follower's calibrated range; sync was not armed.",
                details=_pose_diagnostics(
                    "sync_calibrated_range",
                    leader=leader,
                    follower=follower,
                    requested_target_degrees=target.tolist(),
                    calibrated_target_degrees=calibrated_target.tolist(),
                ),
            )

        torque = self._read_optional("Torque_Enable")
        if torque is not None and any(float(value) != 0.0 for value in torque.values()):
            raise PhysicalGatewayError("Follower torque was not off before sync.")
        self.follower.send_action(_position_dict(follower))
        self.follower.bus.enable_torque(num_retry=BUS_READ_RETRIES)
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
                "Follower moved unexpectedly while establishing the sync hold.",
                details=_pose_diagnostics(
                    "sync_initial_hold",
                    leader=leader,
                    follower=held,
                    follower_hold_start_degrees=follower.tolist(),
                    follower_hold_residual_degrees=hold_residual.tolist(),
                ),
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
                "Leader moved during sync; torque released before accepting the pair.",
                details=_pose_diagnostics(
                    "sync_leader_motion",
                    leader=final_leader,
                    follower=actual,
                    leader_sync_start_degrees=leader.tolist(),
                    leader_motion_degrees=leader_motion.tolist(),
                ),
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
                "Follower did not reach the bounded sync target; torque released.",
                details=_pose_diagnostics(
                    "sync_final_residual",
                    leader=final_leader,
                    follower=actual,
                    follower_sync_target_degrees=target.tolist(),
                    follower_sync_residual_degrees=residual.tolist(),
                ),
            )
        registration = paired_pose_registration_report(final_leader, actual)
        return {
            "schema_version": GATEWAY_SCHEMA,
            "control_mode": "bounded_leader_pose_sync",
            "leader_port": self.identity.leader_port,
            "follower_port": self.identity.follower_port,
            "leader_calibration_sha256": self.identity.leader_calibration_sha256,
            "follower_calibration_sha256": self.identity.follower_calibration_sha256,
            "leader_sync_start_degrees": leader.tolist(),
            "leader_sync_final_degrees": final_leader.tolist(),
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

    def synchronize_and_arm(self, *, countdown_seconds: float = 3.0) -> dict[str, Any]:
        """Sync, hold, count down, and register relative zero in one bus session."""

        if countdown_seconds < 0.0:
            raise PhysicalGatewayError("Countdown duration cannot be negative.")
        sync = self.synchronize_to_leader()
        sync_leader = np.asarray(sync["leader_sync_final_degrees"], dtype=np.float64)
        sync_follower = np.asarray(
            sync["follower_sync_actual_degrees"], dtype=np.float64
        )
        hold_target = np.asarray(sync["leader_sync_target_degrees"], dtype=np.float64)

        countdown_checks: list[dict[str, Any]] = []
        remaining = float(countdown_seconds)
        while remaining > 0.0:
            wait_seconds = min(1.0, remaining)
            self.sleep(wait_seconds)
            remaining -= wait_seconds
            leader = self._motion_read(
                "countdown leader position", self.leader.get_action
            )
            follower = self._motion_read(
                "countdown follower position", self.follower.get_observation
            )
            leader_motion = leader - sync_leader
            leader_motion[4] = shortest_delta_degrees(
                float(leader[4]), float(sync_leader[4])
            )
            follower_drift = sync_follower - follower
            follower_drift[4] = shortest_delta_degrees(
                float(sync_follower[4]), float(follower[4])
            )
            check = {
                "remaining_seconds": remaining,
                "leader_degrees": leader.tolist(),
                "follower_degrees": follower.tolist(),
                "leader_motion_degrees": leader_motion.tolist(),
                "follower_hold_drift_degrees": follower_drift.tolist(),
            }
            countdown_checks.append(check)
            if (
                float(np.max(np.abs(leader_motion[:5])))
                > SYNC_LEADER_MOTION_TOLERANCE_DEG
                or abs(float(leader_motion[5])) > POST_HOLD_GRIPPER_TOLERANCE
            ):
                raise PhysicalGatewayError(
                    "Leader moved during the torque-held countdown; recording was not armed.",
                    details=_pose_diagnostics(
                        "countdown_leader_motion",
                        leader=leader,
                        follower=follower,
                        leader_sync_final_degrees=sync_leader.tolist(),
                        leader_motion_degrees=leader_motion.tolist(),
                        countdown_checks=countdown_checks,
                    ),
                )
            if (
                float(np.max(np.abs(follower_drift[:5])))
                > POST_HOLD_BODY_TOLERANCE_DEG
                or abs(float(follower_drift[5])) > POST_HOLD_GRIPPER_TOLERANCE
            ):
                raise PhysicalGatewayError(
                    "Follower drifted during the torque-held countdown; recording was not armed.",
                    details=_pose_diagnostics(
                        "countdown_follower_drift",
                        leader=leader,
                        follower=follower,
                        follower_sync_final_degrees=sync_follower.tolist(),
                        follower_hold_drift_degrees=follower_drift.tolist(),
                        countdown_checks=countdown_checks,
                    ),
                )
            self.follower.send_action(_position_dict(hold_target))

        registered_leader = self._motion_read(
            "pre-record leader position", self.leader.get_action
        )
        registered_follower = self._motion_read(
            "pre-record follower position", self.follower.get_observation
        )
        registration = paired_pose_registration_report(
            registered_leader, registered_follower
        )
        if not registration["paired_pose_registration_ready"]:
            raise PhysicalGatewayError(
                "Paired-pose registration changed during the torque-held countdown; "
                "recording was not armed.",
                details=_pose_diagnostics(
                    "pre_record_paired_pose_registration",
                    leader=registered_leader,
                    follower=registered_follower,
                    leader_sync_final_degrees=sync_leader.tolist(),
                    follower_sync_final_degrees=sync_follower.tolist(),
                    countdown_checks=countdown_checks,
                ),
            )

        self.leader_start = registered_leader
        self.follower_start = registered_follower
        self.previous_actual = registered_follower.copy()
        self.previous_command = registered_follower.copy()
        self.previous_elapsed_seconds = 0.0
        self.previous_time = self.clock()
        self.stall_anchor_actual = registered_follower.copy()
        self.stall_started_at[:] = np.nan
        self.stall_command_direction[:] = 0.0
        return {
            **sync,
            "control_mode": "continuous_sync_countdown_relative_teleoperation",
            "server_owned_prestart_sequence": True,
            "single_gateway_session": True,
            "countdown_seconds": float(countdown_seconds),
            "countdown_checks": countdown_checks,
            "leader_registration_degrees": registered_leader.tolist(),
            "follower_registration_degrees": registered_follower.tolist(),
            "leader_to_follower_zero_offset_degrees": (
                registered_follower - registered_leader
            ).tolist(),
            "paired_pose_registered_before_recording": True,
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
                    bus.disable_torque(num_retry=BUS_READ_RETRIES)
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
    gateway = SO101PhysicalGateway(
        identity,
        device_factory=device_factory,
        configure_devices=False,
    )
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

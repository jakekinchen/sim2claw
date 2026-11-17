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
SO101_FOLLOWER_ID = "so101_follower"
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
SETUP_OBSERVED_POSE_ELBOW_TRACKING_ERROR_LIMIT_DEG = (
    SYNC_BODY_DELTA_LIMIT_DEG
)
SYNC_GRIPPER_DELTA_LIMIT = 20.0
SYNC_DURATION_SECONDS = 2.5
SYNC_COMMAND_HZ = 40.0
SYNC_FINAL_TOLERANCE_DEG = 3.0
SYNC_LEADER_MOTION_TOLERANCE_DEG = 3.0
HOLD_SETTLE_SECONDS = 0.1
POST_HOLD_BODY_TOLERANCE_DEG = 3.0
POST_HOLD_GRIPPER_TOLERANCE = 5.0
LIVE_ANCHOR_SETTLE_SAMPLES = 4
LIVE_ANCHOR_SETTLE_INTERVAL_SECONDS = 0.1
LIVE_ANCHOR_MAX_BODY_EXCURSION_DEG = 15.0
SETUP_ONLY_ELBOW_TRACKING_ERROR_LIMIT_DEG = (
    LIVE_ANCHOR_MAX_BODY_EXCURSION_DEG
)
LIVE_ANCHOR_MAX_GRIPPER_EXCURSION = 10.0
LIVE_ANCHOR_FINAL_BODY_DRIFT_DEG = 1.5
LIVE_ANCHOR_FINAL_GRIPPER_DRIFT = 3.0
LIVE_SETUP_ELBOW_ANCHOR_SNAP_LIMIT_DEG = 3.0


class PhysicalGatewayError(RuntimeError):
    """Expected fail-closed gateway error."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details


def _live_setup_command_anchor(
    observed: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    command = np.clip(observed, lower, upper)
    snap = command - observed
    disallowed = np.abs(snap) > 0.0
    disallowed[2] = False
    if np.any(disallowed) or abs(float(snap[2])) > LIVE_SETUP_ELBOW_ANCHOR_SNAP_LIMIT_DEG:
        raise PhysicalGatewayError(
            "Live setup anchor exceeds calibrated limits outside the bounded "
            "3 degree elbow-only analytical snap."
        )
    return command, snap


def action_vector(action: dict[str, float]) -> np.ndarray:
    return np.asarray(
        [float(action[f"{joint}.pos"]) for joint in ROBOT_JOINTS],
        dtype=np.float64,
    )


def _same_float64_bytes(left: np.ndarray, right: np.ndarray) -> bool:
    return np.asarray(left, dtype="<f8").tobytes() == np.asarray(
        right, dtype="<f8"
    ).tobytes()


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
    elbow_tracking_error_limit_degrees: float = BODY_TRACKING_ERROR_LIMIT_DEG,
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
            elbow_tracking_error_limit_degrees,
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
            id=SO101_FOLLOWER_ID,
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
        require_initial_follower_torque_off: bool = False,
        torque_enable_spacing_seconds: float = 0.0,
        torque_enable_order: tuple[str, ...] | None = None,
        verify_arm_goal_readback: bool = False,
        position_write_mode: str = "sync",
    ):
        if identity.leader_port == identity.follower_port:
            raise PhysicalGatewayError("Leader and follower must use distinct buses.")
        self.identity = identity
        self.leader, self.follower = device_factory(identity)
        self.sleep = sleep
        self.clock = clock
        self.configure_devices = configure_devices
        self.require_initial_follower_torque_off = (
            require_initial_follower_torque_off
        )
        if (
            not np.isfinite(torque_enable_spacing_seconds)
            or not 0.0 <= torque_enable_spacing_seconds <= 0.5
        ):
            raise PhysicalGatewayError("Torque-enable spacing must be between zero and 0.5 seconds.")
        self.torque_enable_spacing_seconds = float(torque_enable_spacing_seconds)
        self.verify_arm_goal_readback = bool(verify_arm_goal_readback)
        self.arm_goal_readback: dict[str, Any] | None = None
        if position_write_mode not in {"sync", "acknowledged_unicast"}:
            raise PhysicalGatewayError("Unknown follower position-write mode.")
        self.position_write_mode = position_write_mode
        self.torque_enable_order = (
            tuple(ROBOT_JOINTS) if torque_enable_order is None else tuple(torque_enable_order)
        )
        if (
            len(self.torque_enable_order) != len(ROBOT_JOINTS)
            or set(self.torque_enable_order) != set(ROBOT_JOINTS)
        ):
            raise PhysicalGatewayError("Torque-enable order must contain each follower joint exactly once.")
        if torque_enable_order is not None and self.torque_enable_spacing_seconds == 0.0:
            raise PhysicalGatewayError("A custom activation order requires staggered activation.")
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
        # Observed STS3215 firmware may enable torque on a Goal_Position write.
        # Keep uncertain/partial activation separate from a fully armed chain.
        self.goal_write_may_have_armed = False
        self.connected = False
        self.zero_displacement_arm_target: np.ndarray | None = None
        self.live_anchored_setup_only = False

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

    def _enable_follower_torque(self) -> None:
        """Optionally stagger activation, retaining acknowledgements and readback."""
        if self.torque_enable_spacing_seconds == 0.0:
            self.follower.bus.enable_torque(num_retry=BUS_READ_RETRIES)
            return
        try:
            for joint in self.torque_enable_order:
                self.follower.bus.enable_torque(motors=joint, num_retry=BUS_READ_RETRIES)
                self.sleep(self.torque_enable_spacing_seconds)
                torque = self.follower.bus.read(
                    "Torque_Enable", joint, normalize=False, num_retry=BUS_READ_RETRIES
                )
                status = self.follower.bus.read(
                    "Status", joint, normalize=False, num_retry=BUS_READ_RETRIES
                )
                if int(torque) != 1 or int(status) != 0:
                    raise PhysicalGatewayError(
                        f"Staggered activation failed readback for {joint}: "
                        f"torque={torque}, status={status}."
                    )
        except Exception:
            # A partially armed chain must be released before propagating failure.
            try:
                self.close()
            except Exception:
                pass  # caller still performs and records its final shutdown attempt
            raise

    def _send_follower_action(self, action: dict[str, float]) -> dict[str, float]:
        self.goal_write_may_have_armed = True
        if self.position_write_mode == "sync":
            return self.follower.send_action(action)
        # Diagnostic transport: same absolute targets, acknowledged separately.
        # A failed write aborts the sequence; subsequent joints are not sent.
        for joint in ROBOT_JOINTS:
            self.follower.bus.write(
                "Goal_Position", joint, action[f"{joint}.pos"],
                normalize=True, num_retry=0,
            )
        return dict(action)

    def _connect_torque_off(self) -> None:
        try:
            self.leader.bus.connect()
            self.leader.bus.disable_torque(num_retry=BUS_READ_RETRIES)
            self.follower.bus.connect()
            if self.require_initial_follower_torque_off:
                torque = self.follower.bus.sync_read(
                    "Torque_Enable",
                    normalize=False,
                    num_retry=BUS_READ_RETRIES,
                )
                if any(int(value) != 0 for value in torque.values()):
                    raise PhysicalGatewayError(
                        "Follower torque must already be off before excitation preflight."
                    )
            self.follower.bus.disable_torque(num_retry=BUS_READ_RETRIES)
            self.goal_write_may_have_armed = False
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
        setup_command_anchor_degrees: np.ndarray | None = None,
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
            hold_target = follower.copy()
            if setup_command_anchor_degrees is not None:
                hold_target = np.asarray(
                    setup_command_anchor_degrees, dtype=np.float64
                )
                if (
                    hold_target.shape != (6,)
                    or not np.all(np.isfinite(hold_target))
                    or np.any(hold_target < self.lower_limits)
                    or np.any(hold_target > self.upper_limits)
                ):
                    raise PhysicalGatewayError(
                        "Reviewed setup command anchor is invalid or out of range."
                    )
            # A goal write itself may activate STS3215 torque. Normal execution
            # therefore starts with the observed follower pose. Explicit
            # setup-recovery execution instead uses its separately reviewed,
            # in-range clipped anchor before torque enable.
            self.zero_displacement_arm_target = hold_target.copy()
            self._send_follower_action(_position_dict(hold_target))
            if self.verify_arm_goal_readback:
                goals = self.follower.bus.sync_read(
                    "Goal_Position", normalize=True, num_retry=BUS_READ_RETRIES
                )
                goal_vector = np.asarray([float(goals[joint]) for joint in ROBOT_JOINTS])
                delta = goal_vector - hold_target
                delta[4] = shortest_delta_degrees(float(goal_vector[4]), float(hold_target[4]))
                self.arm_goal_readback = {
                    "requested": hold_target.tolist(), "readback": goal_vector.tolist(),
                    "residual": delta.tolist(),
                }
                if not np.all(np.isfinite(goal_vector)) or np.any(np.abs(delta) > 0.2):
                    raise PhysicalGatewayError(
                        "Hold goal did not match motor readback before activation.",
                        details=self.arm_goal_readback,
                    )
            self._enable_follower_torque()
            self.torque_enabled = True
            if setup_command_anchor_degrees is not None:
                self._send_follower_action(_position_dict(hold_target))
            self.sleep(
                0.35
                if setup_command_anchor_degrees is not None
                else HOLD_SETTLE_SECONDS
            )
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
            hold_residual = hold_target - actual
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
                        follower_hold_start_degrees=hold_target.tolist(),
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
            "torque_enable_spacing_seconds": self.torque_enable_spacing_seconds,
            "torque_enable_order": list(self.torque_enable_order),
            "arm_goal_readback": self.arm_goal_readback,
            "position_write_mode": self.position_write_mode,
            **registration,
            **registration_state,
        }

    def open_live_anchored_setup(self) -> dict[str, Any]:
        """Arm once and rebase setup motion to the settled torque-on pose.

        This is deliberately distinct from paired-pose or exact-replay
        registration.  It accepts a bounded gravity-induced settle, follows
        that settle with zero-displacement goals, and exposes the final live
        pose as the only admissible start for a subsequently previewed
        setup-only trajectory.
        """

        self._connect_torque_off()
        initial = self._motion_read(
            "live-anchor torque-off follower position",
            self.follower.get_observation,
        )
        initial_command_anchor, initial_anchor_snap = _live_setup_command_anchor(
            initial,
            self.lower_limits,
            self.upper_limits,
        )
        torque = self._read_optional("Torque_Enable")
        if torque is not None and any(float(value) != 0.0 for value in torque.values()):
            raise PhysicalGatewayError(
                "Follower torque was not off before live-anchor setup."
            )

        self._send_follower_action(_position_dict(initial_command_anchor))
        self._enable_follower_torque()
        self.torque_enabled = True
        settled_samples: list[np.ndarray] = []
        current_samples: list[dict[str, float] | None] = []
        for index in range(LIVE_ANCHOR_SETTLE_SAMPLES):
            self.sleep(LIVE_ANCHOR_SETTLE_INTERVAL_SECONDS)
            actual = self._motion_read(
                f"live-anchor settle position {index + 1}",
                self.follower.get_observation,
            )
            excursion = actual - initial
            excursion[4] = shortest_delta_degrees(
                float(actual[4]),
                float(initial[4]),
            )
            if (
                float(np.max(np.abs(excursion[:5])))
                > LIVE_ANCHOR_MAX_BODY_EXCURSION_DEG
                or abs(float(excursion[5])) > LIVE_ANCHOR_MAX_GRIPPER_EXCURSION
            ):
                raise PhysicalGatewayError(
                    "Follower exceeded the bounded passive live-anchor settle.",
                    details=_pose_diagnostics(
                        "live_anchor_settle_excursion",
                        follower=actual,
                        torque_off_start_degrees=initial.tolist(),
                        settle_excursion_degrees=excursion.tolist(),
                    ),
                )
            # Follow only the observed settle. No route target exists yet.
            self._send_follower_action(_position_dict(actual))
            settled_samples.append(actual)
            current_samples.append(self._read_optional("Present_Current"))

        settled = settled_samples[-1]
        final_drift = settled - settled_samples[-2]
        final_drift[4] = shortest_delta_degrees(
            float(settled[4]),
            float(settled_samples[-2][4]),
        )
        if (
            float(np.max(np.abs(final_drift[:5])))
            > LIVE_ANCHOR_FINAL_BODY_DRIFT_DEG
            or abs(float(final_drift[5])) > LIVE_ANCHOR_FINAL_GRIPPER_DRIFT
        ):
            raise PhysicalGatewayError(
                "Follower did not settle to a stable live torque-on anchor.",
                details=_pose_diagnostics(
                    "live_anchor_unstable",
                    follower=settled,
                    final_settle_drift_degrees=final_drift.tolist(),
                    settle_samples_degrees=[
                        sample.tolist() for sample in settled_samples
                    ],
                ),
            )

        settled_command_anchor, settled_anchor_snap = _live_setup_command_anchor(
            settled,
            self.lower_limits,
            self.upper_limits,
        )
        self.zero_displacement_arm_target = settled_command_anchor.copy()
        self.leader_start = settled.copy()
        self.follower_start = settled.copy()
        self.previous_actual = settled.copy()
        self.previous_command = settled_command_anchor.copy()
        self.previous_elapsed_seconds = 0.0
        self.previous_time = self.clock()
        self.stall_anchor_actual = settled.copy()
        self.stall_started_at[:] = np.nan
        self.stall_command_direction[:] = 0.0
        self.consecutive_stall_samples[:] = 0
        self.live_anchored_setup_only = True
        settle_excursion = settled - initial
        settle_excursion[4] = shortest_delta_degrees(
            float(settled[4]),
            float(initial[4]),
        )
        return {
            "schema_version": GATEWAY_SCHEMA,
            "control_mode": "live_anchored_setup_only",
            "follower_port": self.identity.follower_port,
            "follower_calibration_sha256": (
                self.identity.follower_calibration_sha256
            ),
            "follower_calibrated_minimum": self.lower_limits.tolist(),
            "follower_calibrated_maximum": self.upper_limits.tolist(),
            "torque_off_start_degrees": initial.tolist(),
            "settle_samples_degrees": [
                sample.tolist() for sample in settled_samples
            ],
            "settled_torque_on_anchor_degrees": settled.tolist(),
            "setup_command_anchor_degrees": settled_command_anchor.tolist(),
            "setup_anchor_snap_delta_degrees": settled_anchor_snap.tolist(),
            "setup_anchor_snap_limit_degrees": (
                LIVE_SETUP_ELBOW_ANCHOR_SNAP_LIMIT_DEG
            ),
            "torque_off_setup_command_anchor_degrees": (
                initial_command_anchor.tolist()
            ),
            "torque_off_anchor_snap_delta_degrees": (
                initial_anchor_snap.tolist()
            ),
            "settle_excursion_degrees": settle_excursion.tolist(),
            "final_settle_drift_degrees": final_drift.tolist(),
            "available_motor_current_raw": current_samples,
            "settle_sample_count": LIVE_ANCHOR_SETTLE_SAMPLES,
            "settle_interval_seconds": LIVE_ANCHOR_SETTLE_INTERVAL_SECONDS,
            "maximum_body_settle_excursion_degrees": (
                LIVE_ANCHOR_MAX_BODY_EXCURSION_DEG
            ),
            "maximum_gripper_settle_excursion": (
                LIVE_ANCHOR_MAX_GRIPPER_EXCURSION
            ),
            "route_target_known_during_settle": False,
            "physical_motion_commanded_during_settle": False,
            "passive_settle_observed": bool(
                np.max(np.abs(settle_excursion[:5])) > 0.25
                or abs(float(settle_excursion[5])) > 0.5
            ),
            "physical_follower_torque_enabled": True,
            "setup_only": True,
            "evaluator_admission": False,
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

    def read_motor_diagnostic_block(self, joint: str) -> dict[str, Any]:
        """Read STS3215 feedback in one transaction, with no retries or writes.

        This is also allowed after a possibly activating goal write. It makes
        no torque-off claim. Host timestamps bound the transaction, not the
        servo's undocumented ADC sampling time. The caller must close on error.
        Register offsets and sign bits follow Feetech's SMS_STS feedback API.
        """
        if not self.connected or joint not in ROBOT_JOINTS:
            raise PhysicalGatewayError("Motor diagnostics require a connected gateway and known joint.")
        bus = self.follower.bus
        row = {"joint": joint, "servo_id": bus.motors[joint].id,
               "started_monotonic": self.clock()}
        try:
            data, result, error = bus.packet_handler.readTxRx(
                bus.port_handler, row["servo_id"], 56, 15,
            )
        except Exception as exc:
            row.update(completed_monotonic=self.clock(), error=str(exc))
            raise PhysicalGatewayError("Motor diagnostic transaction failed.", details=row) from exc
        row.update(completed_monotonic=self.clock(), data=list(data),
                   communication_result=result, packet_error=error)
        if result != 0 or error != 0 or len(data) != 15 or any(
            type(value) is not int or not 0 <= value <= 255 for value in data
        ):
            raise PhysicalGatewayError("Motor diagnostic reply is missing or invalid.", details=row)

        def signed_word(offset: int, sign_bit: int) -> int:
            value = data[offset] | (data[offset + 1] << 8)
            return -(value & ~(1 << sign_bit)) if value & (1 << sign_bit) else value

        row.update(position_raw=signed_word(0, 15), velocity_raw=signed_word(2, 15),
                   load_raw=signed_word(4, 10), voltage_raw=data[6],
                   voltage_volts=data[6] / 10.0, temperature_c=data[7],
                   status=data[9], moving=data[10], current_raw=signed_word(13, 15))
        return row

    def set_stopped_acceleration(self, joint: str, value: int) -> dict[str, Any]:
        """Change only a volatile acceleration byte on a verified stopped arm.

        The caller can use the returned previous value for restoration. A failed
        acknowledgement or readback aborts and closes this gateway, without
        retrying the setting write or sending a position target.
        """
        if (
            joint not in ROBOT_JOINTS or not self.connected
            or self.torque_enabled or self.goal_write_may_have_armed
            or type(value) is not int or not 0 <= value <= 254
        ):
            raise PhysicalGatewayError("Acceleration change requires a stopped session and byte 0..254.")
        bus = self.follower.bus
        try:
            for register in ("Torque_Enable", "Status", "Moving", "Operating_Mode"):
                values = bus.sync_read(register, normalize=False, num_retry=0)
                if set(values) != set(ROBOT_JOINTS) or any(v != 0 for v in values.values()):
                    raise PhysicalGatewayError(f"Acceleration change rejected {register} readback.")
            previous = bus.read("Acceleration", joint, normalize=False, num_retry=0)
            if not np.isfinite(previous) or previous != int(previous) or not 0 <= previous <= 254:
                raise PhysicalGatewayError("Invalid previous acceleration value.")
            if previous != value:
                bus.write("Acceleration", joint, value, normalize=False, num_retry=0)
            actual = bus.read("Acceleration", joint, normalize=False, num_retry=0)
            for register in ("Torque_Enable", "Status", "Moving"):
                values = bus.sync_read(register, normalize=False, num_retry=0)
                if set(values) != set(ROBOT_JOINTS) or any(v != 0 for v in values.values()):
                    raise PhysicalGatewayError(f"Acceleration change altered {register}.")
            if actual != value:
                raise PhysicalGatewayError("Acceleration write did not match readback.")
            return {"joint": joint, "previous": int(previous), "requested": value,
                    "readback": int(actual), "setting_writes": int(previous != value),
                    "position_writes": 0, "explicit_torque_enable_writes": 0}
        except Exception:
            self.close()
            raise

    def set_stopped_torque_limit(
        self, joint: str, value: int, *, diagnostic_low_output: bool = False,
    ) -> dict[str, Any]:
        """Set the volatile output limit only while all joints are stopped.

        Values 50..1000 follow Waveshare's ST_TORQUE_MIN/MAX control range.
        A diagnostic-only opt-in additionally permits 0 and 10, within the
        manufacturer's register48 range0..1000, for bounded stationary
        activation comparisons. This does not itself authorize a goal.
        This is an output limit, not a calibrated electrical current limit.
        The caller records the previous value and restores it after shutdown.
        """
        if (
            joint not in ROBOT_JOINTS or not self.connected
            or self.torque_enabled or self.goal_write_may_have_armed
            or type(diagnostic_low_output) is not bool
            or type(value) is not int
            or not (50 <= value <= 1000 or (diagnostic_low_output and value in (0, 10)))
        ):
            raise PhysicalGatewayError("Torque limit change requires a stopped session and value 50..1000.")
        bus = self.follower.bus
        try:
            for register in ("Torque_Enable", "Status", "Moving", "Operating_Mode"):
                values = bus.sync_read(register, normalize=False, num_retry=0)
                if set(values) != set(ROBOT_JOINTS) or any(v != 0 for v in values.values()):
                    raise PhysicalGatewayError(f"Torque limit change rejected {register} readback.")
            previous = bus.read("Torque_Limit", joint, normalize=False, num_retry=0)
            maximum = bus.read("Max_Torque_Limit", joint, normalize=False, num_retry=0)
            if (not np.isfinite(maximum) or maximum != int(maximum) or not 50 <= maximum <= 1000
                or not np.isfinite(previous) or previous != int(previous)
                or not (50 <= previous <= 1000 or (diagnostic_low_output and previous in (0, 10)))):
                raise PhysicalGatewayError("Invalid existing torque limit.")
            if value > maximum:
                raise PhysicalGatewayError("Requested output limit exceeds the persistent maximum.")
            if previous != value:
                bus.write("Torque_Limit", joint, value, normalize=False, num_retry=0)
            actual = bus.read("Torque_Limit", joint, normalize=False, num_retry=0)
            for register in ("Torque_Enable", "Status", "Moving"):
                values = bus.sync_read(register, normalize=False, num_retry=0)
                if set(values) != set(ROBOT_JOINTS) or any(v != 0 for v in values.values()):
                    raise PhysicalGatewayError(f"Torque limit change altered {register}.")
            if actual != value:
                raise PhysicalGatewayError("Torque limit write did not match readback.")
            return {"joint": joint, "previous": int(previous), "persistent_maximum": int(maximum),
                    "requested": value, "readback": int(actual), "setting_writes": int(previous != value),
                    "position_writes": 0, "explicit_torque_enable_writes": 0}
        except Exception:
            self.close()
            raise

    def probe_stationary_joint_goal(
        self, joint: str, *, goal_offset_raw: int = 0, slow_start: bool = False,
    ) -> dict[str, Any]:
        """Write one raw target after verifying the whole follower torque-off.

        The target write may itself activate the selected servo. This diagnostic
        isolates that transaction from explicit torque-enable and other goal
        writes. The caller records feedback and closes the gateway on failure.
        An uncertain write is never retried here.
        The optional six-count offset is confined to output limit50. It permits
        a small position diagnostic without weakening the stationary default.
        Slow start uses the vendor WritePosEx layout: acceleration1, goal,
        time0, speed1 in a single transaction. Its temporary profile is reported
        and not automatically rewritten after stopping.
        """
        if (
            joint not in ROBOT_JOINTS or not self.connected
            or self.torque_enabled or self.goal_write_may_have_armed
            or type(goal_offset_raw) is not int or goal_offset_raw not in (-6, 0, 6)
            or type(slow_start) is not bool or (slow_start and goal_offset_raw == 0)
        ):
            raise PhysicalGatewayError("Stationary goal probe requires a known joint and torque-off session.")
        bus = self.follower.bus
        for register in ("Torque_Enable", "Status", "Moving", "Operating_Mode"):
            values = bus.sync_read(register, normalize=False, num_retry=0)
            if set(values) != set(ROBOT_JOINTS) or any(value != 0 for value in values.values()):
                raise PhysicalGatewayError(f"Stationary goal probe rejected {register} readback.")
        calibration = getattr(self.follower, "calibration", None)
        if not calibration or joint not in calibration:
            raise PhysicalGatewayError("Stationary goal probe requires calibrated raw limits.")
        entry = calibration[joint]
        minimum = entry["range_min"] if isinstance(entry, dict) else entry.range_min
        maximum = entry["range_max"] if isinstance(entry, dict) else entry.range_max
        first = bus.read("Present_Position", joint, normalize=False, num_retry=0)
        self.sleep(0.05)
        anchor = bus.read("Present_Position", joint, normalize=False, num_retry=0)
        if (
            not np.all(np.isfinite([first, anchor, minimum, maximum]))
            or anchor != int(anchor)
            or abs(anchor - first) > 1
            or not 0 <= minimum <= anchor <= maximum <= 4095
        ):
            raise PhysicalGatewayError("Stationary goal probe position is moving, invalid, or out of range.")
        target = int(anchor) + goal_offset_raw
        if not minimum <= target <= maximum:
            raise PhysicalGatewayError("Small goal offset exceeds calibrated limits.")
        if goal_offset_raw and bus.read("Torque_Limit", joint, normalize=False, num_retry=0) != 50:
            raise PhysicalGatewayError("Small goal offset requires verified output limit50.")
        # Recheck the selected joint immediately before the only goal write.
        if bus.read("Torque_Enable", joint, normalize=False, num_retry=0) != 0:
            raise PhysicalGatewayError("Torque changed before stationary goal probe.")
        self.goal_write_may_have_armed = True
        profile = None
        if slow_start:
            payload = [1, target & 255, target >> 8, 0, 0, 1, 0]
            result, error = bus.packet_handler.writeTxRx(
                bus.port_handler, bus.motors[joint].id, 41, len(payload), payload,
            )
            if result != 0 or error != 0:
                raise PhysicalGatewayError("Slow-start goal acknowledgement failed.", details={
                    "communication_result": result, "packet_error": error, "payload": payload})
            profile = {"acceleration_raw": 1, "goal_time_raw": 0, "goal_velocity_raw": 1,
                       "address": 41, "payload": payload}
        else:
            bus.write("Goal_Position", joint, int(target), normalize=False, num_retry=0)
        return {"joint": joint, "anchor_raw": int(anchor), "target_raw": int(target),
                "requested_offset_raw": goal_offset_raw, "goal_writes": 1,
                "slow_start_profile": profile,
                "explicit_torque_enable_writes": 0, "gain_writes": 0,
                "goal_write_may_have_armed": True}

    def sample_read_only(self) -> dict[str, Any]:
        """Read both calibrated poses while preserving the torque-off contract."""

        if not self.connected or self.torque_enabled or self.goal_write_may_have_armed:
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

    def sample(
        self,
        elapsed_seconds: float,
        *,
        zero_displacement_hold: bool = False,
        exact_requested_degrees: np.ndarray | None = None,
        setup_elbow_tracking_error_limit_degrees: float | None = None,
    ) -> dict[str, Any]:
        if zero_displacement_hold and exact_requested_degrees is not None:
            raise PhysicalGatewayError(
                "Choose either the runtime hold target or one precompiled target."
            )
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
        exact_precompiled = exact_requested_degrees is not None
        if setup_elbow_tracking_error_limit_degrees is not None:
            if (
                not self.live_anchored_setup_only
                or not exact_precompiled
                or setup_elbow_tracking_error_limit_degrees
                not in {
                    7.0,
                    BODY_REGISTRATION_OFFSET_LIMIT_DEG,
                    SETUP_ONLY_ELBOW_TRACKING_ERROR_LIMIT_DEG,
                    SETUP_OBSERVED_POSE_ELBOW_TRACKING_ERROR_LIMIT_DEG,
                }
            ):
                raise PhysicalGatewayError(
                    "The 7, 12, 15, or 20 degree elbow tracking envelope is restricted to "
                    "exact live-anchored setup-only samples."
                )
        elbow_tracking_limit = (
            setup_elbow_tracking_error_limit_degrees
            if setup_elbow_tracking_error_limit_degrees is not None
            else BODY_TRACKING_ERROR_LIMIT_DEG
        )
        if zero_displacement_hold or exact_precompiled:
            if self.zero_displacement_arm_target is None:
                raise PhysicalGatewayError(
                    "Exact physical execution lacks a fresh pre-arm follower anchor."
                )
            registration = paired_pose_registration_report(
                leader,
                self.previous_actual,
            )
            if not registration["paired_pose_registration_ready"]:
                raise PhysicalGatewayError(
                    "Paired pose left the existing registration limits during "
                    "exact physical execution."
                )
            if exact_precompiled:
                requested = np.asarray(
                    exact_requested_degrees, dtype=np.float64
                ).copy()
                _finite(requested, "precompiled requested target")
                relative_delta = requested - self.zero_displacement_arm_target
                relative_delta[4] = shortest_delta_degrees(
                    float(requested[4]),
                    float(self.zero_displacement_arm_target[4]),
                )
                limits = np.asarray(
                    [BODY_EXCURSION_LIMIT_DEG] * 4
                    + [WRIST_ROLL_EXCURSION_LIMIT_DEG, GRIPPER_EXCURSION_LIMIT],
                    dtype=np.float64,
                )
                if np.any(np.abs(relative_delta) > limits):
                    raise PhysicalGatewayError(
                        "Precompiled target exceeds the reviewed excursion envelope."
                    )
                if not np.array_equal(
                    np.clip(requested, self.lower_limits, self.upper_limits),
                    requested,
                ):
                    raise PhysicalGatewayError(
                        "Precompiled target exceeds calibrated follower limits."
                    )
            else:
                requested = self.zero_displacement_arm_target.copy()
                relative_delta = np.zeros(len(ROBOT_JOINTS), dtype=np.float64)
        else:
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
            elbow_tracking_error_limit_degrees=elbow_tracking_limit,
        )
        if exact_precompiled and not _same_float64_bytes(command, requested):
            requested_command_delta = requested - self.previous_command
            requested_command_delta[4] = shortest_delta_degrees(
                float(requested[4]), float(self.previous_command[4])
            )
            requested_tracking_delta = requested - self.previous_actual
            requested_tracking_delta[4] = shortest_delta_degrees(
                float(requested[4]), float(self.previous_actual[4])
            )
            exact_target_is_safe = (
                np.all(
                    np.abs(requested_command_delta)
                    <= rate_limits
                    * min(control_dt, MAX_CONTROL_INTERVAL_SECONDS)
                )
                and np.all(np.abs(requested_tracking_delta) <= tracking_limits)
                and np.array_equal(
                    np.clip(requested, self.lower_limits, self.upper_limits),
                    requested,
                )
            )
            if exact_target_is_safe:
                # Reuse the preregistered bytes after independently confirming
                # every rate, tracking, and calibrated-position constraint.
                command = requested.copy()
        if (zero_displacement_hold or exact_precompiled) and not _same_float64_bytes(
            command, requested
        ):
            raise PhysicalGatewayError(
                (
                    "Zero-displacement hold"
                    if zero_displacement_hold
                    else "Precompiled exact target"
                )
                + " would require rate limiting, clamping, or correction; "
                "the current sample was not sent."
            )
        command_call_started_monotonic = self.clock()
        sent = action_vector(self._send_follower_action(_position_dict(command)))
        command_call_completed_monotonic = self.clock()
        if (zero_displacement_hold or exact_precompiled) and not _same_float64_bytes(
            sent, requested
        ):
            raise PhysicalGatewayError(
                "Gateway did not report the exact "
                + ("hold target" if zero_displacement_hold else "precompiled target")
                + " as sent; torque will be released."
            )
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
            "zero_displacement_hold": zero_displacement_hold,
            "precompiled_exact_action": exact_precompiled,
            "zero_displacement_target_source": (
                "fresh_torque_off_follower_read_immediately_before_arming"
                if zero_displacement_hold
                else None
            ),
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
        self._send_follower_action(_position_dict(follower))
        self._enable_follower_torque()
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
            self._send_follower_action(_position_dict(command))
            self.sleep(1.0 / SYNC_COMMAND_HZ)
        self._send_follower_action(_position_dict(target))
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
            self._send_follower_action(_position_dict(hold_target))

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
                # A per-motor failure in LeRobot's bulk helper stops its loop.
                # Still attempt release on every known motor before closing serial.
                motors = getattr(bus, "motors", {})
                if isinstance(motors, dict):
                    for joint in motors:
                        try:
                            bus.disable_torque(motors=joint, num_retry=BUS_READ_RETRIES)
                        except Exception as motor_error:
                            errors.append(motor_error)
            try:
                if bus.is_connected:
                    bus.disconnect(False)
            except TypeError:
                try:
                    if bus.is_connected:
                        bus.disconnect()
                except Exception as error:
                    errors.append(error)
            except Exception as error:
                errors.append(error)
        self.torque_enabled = False
        self.goal_write_may_have_armed = False
        self.connected = False
        self.zero_displacement_arm_target = None
        self.live_anchored_setup_only = False
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


def inspect_isolated_servo_read_only(
    port: str,
    expected_serial_number: str,
    *,
    candidate_ids: tuple[int, ...] = (1, 3),
    include_configuration: bool = False,
) -> dict[str, Any]:
    """Identify an operator-isolated replacement without any register writes.

    Requires current operator authority for serial inspection. Uses the existing
    LeRobot dependency's public Feetech SDK only for PING/READ framing. Unlike
    whole-arm preflight, this does not connect either robot, configure devices,
    or change torque, including during cleanup. A transport allowlist rejects
    writes, broadcasts, and reads outside the identity/health register ranges.
    Model 777 identifies the STS3215 family, not its physical voltage variant.
    """
    import scservo_sdk as scs
    from serial.tools import list_ports

    if type(include_configuration) is not bool:
        raise PhysicalGatewayError("Configuration inspection flag must be boolean.")

    if (
        not candidate_ids
        or len(candidate_ids) > 254
        or len(set(candidate_ids)) != len(candidate_ids)
        or any(type(item) is not int or not 0 <= item <= 253 for item in candidate_ids)
    ):
        raise PhysicalGatewayError("Require distinct unicast servo IDs from 0 to 253.")
    matches = [
        item for item in list_ports.comports()
        if item.device == port
        and item.serial_number == expected_serial_number
        and item.vid == 0x1A86 and item.pid == 0x55D3
    ]
    if not expected_serial_number or len(matches) != 1:
        raise PhysicalGatewayError("Servo adapter USB identity does not match.")

    handler = scs.PortHandler(port)
    protocol = scs.PacketHandler(0)
    sent: list[list[int]] = []
    write_port = handler.writePort
    allowed_reads = {(3, 2), (0, 16), (40, 1), (56, 15)}
    if include_configuration:
        allowed_reads.update({(0, 40), (40, 10)})

    def guarded_transmit(packet: Any) -> int:
        frame = list(packet)
        valid_frame = (
            len(frame) >= 6
            and frame[:2] == [255, 255]
            and frame[2] in candidate_ids
            and len(frame) == frame[3] + 4
            and (sum(frame[2:]) & 255) == 255
        )
        allowed_ping = len(frame) == 6 and frame[4] == 1 and frame[3] == 2
        allowed_read = (
            len(frame) == 8 and frame[4] == 2 and frame[3] == 4
            and tuple(frame[5:7]) in allowed_reads
        )
        if not valid_frame or not (allowed_ping or allowed_read):
            raise PhysicalGatewayError("Read-only servo gateway rejected a packet.")
        sent.append(frame)
        return write_port(packet)

    handler.writePort = guarded_transmit
    report: dict[str, Any] = {
        "schema_version": "sim2claw.isolated_servo_read_only.v1",
        "proof_class": "physical_read_only_servo_identity_and_health",
        "port": port,
        "adapter_serial_number": expected_serial_number,
        "baudrate": 1_000_000,
        "candidate_ids": list(candidate_ids),
        "probes": [],
        "register_writes_sent": 0,
        "motion_commands_sent": 0,
    }
    try:
        if not handler.setBaudRate(1_000_000):
            raise PhysicalGatewayError("Could not open servo adapter at 1 Mbps.")
        for servo_id in candidate_ids:
            model, result, error = protocol.ping(handler, servo_id)
            probe: dict[str, Any] = {
                "id": servo_id, "model_number": model,
                "communication_result": result, "device_error": error,
                "communication_message": protocol.getTxRxResult(result),
                "device_error_message": protocol.getRxPacketError(error),
            }
            report["probes"].append(probe)
            if result != scs.COMM_SUCCESS or model != 777:
                continue
            registers = {}
            read_ranges = (
                ("identity_and_limits", 0, 16),
                ("torque_enable", 40, 1),
                ("present_telemetry", 56, 15),
            )
            if include_configuration:
                read_ranges += (("persistent_configuration", 0, 40), ("runtime_configuration", 40, 10))
            for name, address, length in read_ranges:
                data, result, error = protocol.readTxRx(handler, servo_id, address, length)
                registers[name] = {
                    "address": address, "data": list(data),
                    "communication_result": result, "device_error": error,
                    "complete": result == scs.COMM_SUCCESS and len(data) == length,
                }
            probe["registers"] = registers
    finally:
        if handler.is_open:
            handler.closePort()
    report["transmitted_packets"] = sent
    report["port_closed"] = not handler.is_open
    return report


def probe_isolated_servo_hold(
    port: str,
    expected_serial_number: str,
    *,
    raw_limits: tuple[int, int],
    expected_homing_offset: int,
    camera_guard: Callable[[], None],
    output_limit: int = 50,
    servo_id: int = 3,
    goal_offset_raw: int = 0,
    unloaded_sweep: bool = False,
    observation_seconds: int = 1,
    sleep: SleepFunction = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Probe exactly one connected servo; other arm IDs must be absent."""
    return _probe_bounded_servo_position(
        port, expected_serial_number, raw_limits=raw_limits,
        expected_homing_offset=expected_homing_offset, camera_guard=camera_guard,
        output_limit=output_limit, servo_id=servo_id, goal_offset_raw=goal_offset_raw,
        unloaded_sweep=unloaded_sweep, observation_seconds=observation_seconds,
        sleep=sleep, clock=clock,
    )


def probe_reduced_arm_elbow(
    port: str,
    expected_serial_number: str,
    *,
    raw_limits: tuple[int, int],
    expected_homing_offset: int,
    peer_calibrations: dict[int, tuple[tuple[int, int], int]],
    camera_guard: Callable[[], None],
    goal_offset_raw: int = 0,
    observation_seconds: int = 1,
    sleep: SleepFunction = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Probe elbow 3 with passive peers 1/2 and distal assembly 4–6 removed.

    Only elbow 3 may receive writes. Peers must remain torque off, stationary,
    and healthy. The caller confirms reduced mechanical load and clearance
    using the recorded camera view. This does not assert a fully unloaded motor.
    """
    if not isinstance(peer_calibrations, dict) or set(peer_calibrations) != {1, 2}:
        raise PhysicalGatewayError("Reduced arm requires explicit calibration for peers 1 and 2.")
    for peer, calibration in peer_calibrations.items():
        if (type(peer) is not int or not isinstance(calibration, tuple) or len(calibration) != 2
            or not isinstance(calibration[0], tuple) or len(calibration[0]) != 2
            or any(type(v) is not int for v in (*calibration[0], calibration[1]))
            or not 0 <= calibration[0][0] < calibration[0][1] <= 4095
            or not -2047 <= calibration[1] <= 2047):
            raise PhysicalGatewayError("Invalid reduced-arm peer calibration.")
    return _probe_bounded_servo_position(
        port, expected_serial_number, raw_limits=raw_limits,
        expected_homing_offset=expected_homing_offset, camera_guard=camera_guard,
        output_limit=50, servo_id=3, goal_offset_raw=goal_offset_raw,
        passive_peer_calibrations=dict(peer_calibrations),
        observation_seconds=observation_seconds, sleep=sleep, clock=clock,
    )


def _probe_bounded_servo_position(
    port: str,
    expected_serial_number: str,
    *,
    raw_limits: tuple[int, int],
    expected_homing_offset: int,
    camera_guard: Callable[[], None],
    output_limit: int = 50,
    servo_id: int = 3,
    goal_offset_raw: int = 0,
    unloaded_sweep: bool = False,
    passive_peer_calibrations: dict[int, tuple[tuple[int, int], int]] | None = None,
    observation_seconds: int = 1,
    sleep: SleepFunction = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """One bounded position goal with explicit topology and transport scope.

    This diagnostic owns its port and every write. Only the selected ID and
    explicitly declared passive peers may respond among the six known arm IDs.
    It never emulates missing joints, rewrites calibration, or retries an activation. The caller records
    video and supplies a live camera guard. A torque output cap is not a
    calibrated electrical current limiter. Returns failures and raw evidence.
    A nonzero offset normally permits only a six-count diagnostic at output limit 50.
    Explicit unloaded_sweep or the reduced-arm wrapper permits up to 114 counts
    (about 10 degrees), with the same output cap and bounded feedback envelope;
    zero preserves the existing stationary-hold behavior. Completion means
    healthy observation, not that the motor reached the requested position.
    """
    import scservo_sdk as scs
    from serial.tools import list_ports
    from lerobot.motors.feetech.feetech import patch_setPacketTimeout

    peers = passive_peer_calibrations or {}
    bounded_sweep = unloaded_sweep or bool(peers)
    if (
        type(servo_id) is not int or servo_id not in range(1, 7)
        or type(output_limit) is not int or output_limit not in (50, 1000)
        or type(observation_seconds) is not int
        or observation_seconds not in ((1, 3) if bounded_sweep else (1,))
        or type(unloaded_sweep) is not bool
        or type(goal_offset_raw) is not int
        or (abs(goal_offset_raw) > 114 if bounded_sweep else goal_offset_raw not in (-6, 0, 6))
        or (bounded_sweep and output_limit != 50)
        or (goal_offset_raw != 0 and output_limit != 50)
        or len(raw_limits) != 2 or any(type(v) is not int for v in raw_limits)
        or not 0 <= raw_limits[0] < raw_limits[1] <= 4095
        or type(expected_homing_offset) is not int or not -2047 <= expected_homing_offset <= 2047
        or not callable(camera_guard)
    ):
        raise PhysicalGatewayError("Invalid isolated hold identity, limits, or camera guard.")
    matches = [p for p in list_ports.comports() if p.device == port
               and p.serial_number == expected_serial_number and p.vid == 0x1A86 and p.pid == 0x55D3]
    if not expected_serial_number or len(matches) != 1:
        raise PhysicalGatewayError("Isolated hold USB identity does not match.")
    handler = scs.PortHandler(port)
    handler.setPacketTimeout = patch_setPacketTimeout.__get__(handler, type(handler))
    protocol = scs.PacketHandler(0)
    original_write, original_read = handler.writePort, handler.readPort
    pending_write: tuple[int, tuple[int, ...]] | None = None
    stage = "admission"
    report: dict[str, Any] = {"schema_version": "sim2claw.isolated_stationary_hold.v1",
        "proof_class": "physical_single_servo_stationary_hold_diagnostic", "servo_id": servo_id,
        "output_limit_requested": output_limit, "status": "aborted", "samples": [],
        "serial_trace": [], "goal_writes": 0, "setting_writes": [], "shutdown_attempts": []}
    if goal_offset_raw:
        report.update(schema_version="sim2claw.isolated_position_probe.v1",
                      proof_class=("physical_single_servo_unloaded_position_diagnostic" if unloaded_sweep
                                   else "physical_single_servo_six_count_position_diagnostic"))
    if peers:
        report.update(schema_version="sim2claw.reduced_arm_elbow_probe.v1",
                      proof_class="physical_reduced_load_elbow_diagnostic",
                      expected_connected_ids=[1, 2, 3], passive_peer_samples=[],
                      passive_peers_before={}, passive_peers_after={})
    report["requested_offset_raw"] = goal_offset_raw
    report["unloaded_sweep"] = unloaded_sweep
    report["observation_seconds"] = observation_seconds
    allowed_reads = {(3, 2), (0, 40), (40, 10), (40, 1), (48, 2), (56, 15)}
    touched = False
    original_limit = None
    target = None
    anchor = None
    peer_anchors: dict[int, int] = {}
    peer_baselines: dict[int, float] = {}

    def transmit(packet: Any) -> int:
        nonlocal pending_write
        frame = list(packet)
        valid = (len(frame) >= 6 and frame[:2] == [255, 255]
                 and len(frame) == frame[3] + 4 and (sum(frame[2:]) & 255) == 255)
        ping = len(frame) == 6 and frame[2] in range(1, 7) and frame[4] == 1
        read = (len(frame) == 8 and frame[2] in range(1, 7) and frame[4] == 2
                and tuple(frame[5:7]) in allowed_reads
                and (frame[2] == servo_id or frame[2] in peers or tuple(frame[5:7]) == (3, 2)))
        write = (len(frame) in (8, 9) and frame[2] == servo_id and frame[4] == 3
                 and pending_write is not None and (frame[5], tuple(frame[6:-1])) == pending_write)
        if not valid or not (ping or read or write):
            raise PhysicalGatewayError("Isolated hold rejected an unapproved packet.")
        if write:
            pending_write = None
        report["serial_trace"].append({"t": clock(), "stage": stage, "tx": frame})
        return original_write(packet)

    def receive(count: int) -> Any:
        data = original_read(count)
        if data:
            report["serial_trace"].append({"t": clock(), "stage": stage, "rx": list(data)})
        return data

    handler.writePort, handler.readPort = transmit, receive

    def read_bytes(address: int, length: int, selected_id: int = servo_id) -> list[int]:
        started = clock()
        data, result, error = protocol.readTxRx(handler, selected_id, address, length)
        details = {"servo_id": selected_id, "address": address, "data": list(data), "communication_result": result,
                   "packet_error": error, "started_monotonic": started, "completed_monotonic": clock()}
        if result != scs.COMM_SUCCESS or error or len(data) != length:
            raise PhysicalGatewayError("Isolated hold read failed.", details=details)
        return list(data)

    def word(data: list[int], offset: int = 0) -> int:
        return data[offset] | data[offset + 1] << 8

    def signed(value: int, bit: int) -> int:
        return -(value & ~(1 << bit)) if value & (1 << bit) else value

    def write_value(address: int, value: int) -> None:
        nonlocal pending_write, touched
        if address == 40 and value == 0:
            values = (0,)
        elif address == 42 and value == target and report["goal_writes"] == 0:
            values = (value & 255, value >> 8)
            report["goal_writes"] += 1  # Consume before an uncertain transmission.
        elif address == 48 and value in (output_limit, original_limit):
            values = (value & 255, value >> 8)
            report["setting_writes"].append(value)
        else:
            raise PhysicalGatewayError("Isolated hold write is outside its scope.")
        touched = True
        pending_write = (address, values)
        try:
            if len(values) == 1:
                result, error = protocol.write1ByteTxRx(handler, servo_id, address, value)
            else:
                result, error = protocol.write2ByteTxRx(handler, servo_id, address, value)
        finally:
            pending_write = None
        if result != scs.COMM_SUCCESS or error:
            raise PhysicalGatewayError("Isolated hold write acknowledgement failed.", details={
                "address": address, "value": value, "communication_result": result, "packet_error": error})

    def feedback(label: str, baseline_voltage: float | None = None) -> dict[str, Any]:
        started = clock()
        try:
            data = read_bytes(56, 15)
        except PhysicalGatewayError as exc:
            report["samples"].append({"stage": label, "error": str(exc), "details": exc.details})
            raise
        row = {"stage": label, "started_monotonic": started, "completed_monotonic": clock(),
               "data": data, "position_raw": signed(word(data), 15), "voltage_volts": data[6] / 10,
               "current_raw": signed(word(data, 13), 15), "status": data[9], "moving": data[10]}
        report["samples"].append(row)
        if (row["status"] or abs(row["current_raw"]) > 50 or not 10.5 <= row["voltage_volts"] <= 12.6
            or (anchor is not None and (
                not min(anchor, anchor + goal_offset_raw) - 5 <= row["position_raw"] <= max(anchor, anchor + goal_offset_raw) + 5
                if bounded_sweep else abs(row["position_raw"] - anchor) > 11))
            or not raw_limits[0] <= row["position_raw"] <= raw_limits[1]
            or (baseline_voltage is not None and row["voltage_volts"] <= baseline_voltage - 0.5)):
            raise PhysicalGatewayError("Isolated hold feedback guard tripped.", details=row)
        return row

    def check_peer(peer: int, label: str, *, verify_persistent: bool = False) -> dict[str, Any]:
        data = read_bytes(56, 15, peer)
        control = read_bytes(40, 10, peer)
        row = {"servo_id": peer, "stage": label, "t": clock(), "data": data, "control": control,
               "position_raw": signed(word(data), 15), "voltage_volts": data[6] / 10,
               "current_raw": signed(word(data, 13), 15), "status": data[9], "moving": data[10]}
        report["passive_peer_samples"].append(row)
        limits, offset = peers[peer]
        if (control[0] != 0 or word(control, 8) != 1000 or row["status"] or row["moving"]
            or abs(row["current_raw"]) > 50 or not 10.5 <= row["voltage_volts"] <= 12.6
            or not limits[0] <= row["position_raw"] <= limits[1]
            or (peer in peer_anchors and abs(row["position_raw"] - peer_anchors[peer]) > 3)
            or (peer in peer_baselines and row["voltage_volts"] <= peer_baselines[peer] - 0.5)):
            raise PhysicalGatewayError("Passive peer guard tripped.", details=row)
        if verify_persistent:
            configuration = read_bytes(0, 40, peer)
            if (configuration[:2] != [3, 9] or word(configuration, 3) != 777
                or configuration[5] != peer or configuration[33] != 0
                or (word(configuration, 9), word(configuration, 11)) != limits
                or signed(word(configuration, 31), 11) != offset or word(configuration, 16) != 1000):
                raise PhysicalGatewayError("Passive peer identity/calibration/mode mismatch.")
            row["persistent"] = configuration
        return row

    try:
        camera_guard()
        if not handler.setBaudRate(1_000_000):
            raise PhysicalGatewayError("Could not open isolated hold adapter.")
        report["pings"] = {}
        for candidate in range(1, 7):
            reply = protocol.ping(handler, candidate)
            report["pings"][candidate] = list(reply)
            expected_present = candidate == servo_id or candidate in peers
            if ((expected_present and reply != (777, scs.COMM_SUCCESS, 0))
                or (not expected_present and reply[1] != scs.COMM_RX_TIMEOUT)):
                raise PhysicalGatewayError("Probe requires exactly the declared connected arm IDs.")
        for peer in peers:
            peer_row = check_peer(peer, "admission", verify_persistent=True)
            report["passive_peers_before"][peer] = peer_row
            peer_anchors[peer] = peer_row["position_raw"]
            peer_baselines[peer] = peer_row["voltage_volts"]
        persistent = read_bytes(0, 40)
        report["persistent_before"] = persistent
        if (persistent[:2] != [3, 9] or word(persistent, 3) != 777 or persistent[5] != servo_id
            or (word(persistent, 9), word(persistent, 11)) != raw_limits
            or signed(word(persistent, 31), 11) != expected_homing_offset or persistent[33] != 0):
            raise PhysicalGatewayError("Isolated hold identity/calibration/mode mismatch.")
        control = read_bytes(40, 10)
        report["control_before"] = control
        original_limit = word(control, 8)
        if control[0] != 0 or original_limit != 1000 or word(persistent, 16) != 1000:
            raise PhysicalGatewayError("Isolated hold requires torque off and original limits 1000.")
        first = feedback("stationary_check")
        sleep(0.05)
        second = feedback("stationary_check")
        if first["moving"] or second["moving"] or abs(second["position_raw"] - first["position_raw"]) > 1:
            raise PhysicalGatewayError("Isolated servo is not stationary.")
        anchor = second["position_raw"]
        target = anchor + goal_offset_raw
        if not raw_limits[0] <= target <= raw_limits[1]:
            raise PhysicalGatewayError("Isolated probe offset would exceed calibration.")
        report["anchor_raw"] = anchor
        report["target_raw"] = target
        stage = "setting"
        if output_limit != original_limit:
            write_value(48, output_limit)
        configured = read_bytes(40, 10)
        expected = control[:8] + [output_limit & 255, output_limit >> 8]
        if configured != expected or read_bytes(0, 40) != persistent:
            raise PhysicalGatewayError("Isolated hold setting verification failed.")
        report["control_configured"] = configured
        stage = "baseline"
        for sample_index in range(100):
            camera_guard()
            row = feedback("baseline")
            if row["moving"] or abs(row["position_raw"] - anchor) > 1:
                raise PhysicalGatewayError("Isolated hold baseline drifted.")
            if sample_index % 10 == 0:
                for peer in peers:
                    check_peer(peer, "baseline")
            sleep(max(0.0, row["started_monotonic"] + 0.002 - clock()))
        baseline_voltage = min(r["voltage_volts"] for r in report["samples"] if r["stage"] == "baseline")
        camera_guard()
        control = read_bytes(40, 10)
        fresh = feedback("pre_goal")
        if control[0] != 0 or word(control, 8) != output_limit or fresh["position_raw"] != anchor or fresh["moving"]:
            raise PhysicalGatewayError("Isolated hold state changed before goal.")
        for peer in peers:
            check_peer(peer, "pre_goal")
        stage = "goal"
        report["goal_started_monotonic"] = clock()
        write_value(42, target)
        report["goal_ack_monotonic"] = clock()
        stage = "hold"
        report["hold_control_checks"] = []
        hold_samples = 0
        while clock() - report["goal_ack_monotonic"] < observation_seconds:
            row = feedback("hold", baseline_voltage)
            hold_samples += 1
            if hold_samples % 10 == 0:
                camera_guard()
                control = read_bytes(40, 10)
                report["hold_control_checks"].append({"t": clock(), "data": control})
                if control[0] != 1 or word(control, 2) != target or word(control, 8) != output_limit:
                    raise PhysicalGatewayError("Isolated hold torque/goal/limit readback changed.")
                for peer in peers:
                    check_peer(peer, "hold")
            sleep(max(0.0, row["started_monotonic"] + 0.002 - clock()))
        if hold_samples < 100:
            raise PhysicalGatewayError("Insufficient hold feedback.")
        control = read_bytes(40, 10)
        if control[0] != 1 or word(control, 2) != target or word(control, 8) != output_limit:
            raise PhysicalGatewayError("Final isolated hold state mismatch.")
        report["observed_final_delta_raw"] = row["position_raw"] - anchor
        report["status"] = ("three_second_position_probe_completed" if observation_seconds == 3
                            else "one_second_position_probe_completed" if goal_offset_raw else "one_second_hold_completed")
    except Exception as exc:
        report.update(error=str(exc), error_details=getattr(exc, "details", None), error_monotonic=clock())
    finally:
        stage = "shutdown"
        report["shutdown_started_monotonic"] = clock()
        if handler.is_open and touched:
            for delay in (0.0, 0.05, 0.2):
                sleep(delay)
                attempt: dict[str, Any] = {"t": clock()}
                report["shutdown_attempts"].append(attempt)
                try:
                    write_value(40, 0)
                    if read_bytes(40, 1) != [0]:
                        raise PhysicalGatewayError("Isolated shutdown did not verify torque off.")
                    attempt["torque_off_verified"] = True
                    break
                except Exception as exc:
                    attempt["error"] = str(exc)
            stage = "restoration"
            sleep(0.5)
            try:
                if read_bytes(40, 1) != [0]:
                    raise PhysicalGatewayError("Restoration requires verified torque off.")
                health = feedback("after_stop")
                if health["moving"]:
                    raise PhysicalGatewayError("Restoration requires stationary servo.")
                before_restore = word(read_bytes(48, 2))
                if before_restore != original_limit:
                    write_value(48, original_limit)
                if word(read_bytes(48, 2)) != original_limit or read_bytes(40, 1) != [0]:
                    raise PhysicalGatewayError("Isolated hold restoration failed.")
                if read_bytes(0, 40) != persistent:
                    raise PhysicalGatewayError("Persistent settings changed during isolated hold.")
                report["restoration"] = {"previous": before_restore, "restored": original_limit,
                                         "write_sent": before_restore != original_limit, "torque_off": True}
            except Exception as exc:
                report["restoration_error"] = str(exc)
            for peer in peers:
                try:
                    peer_row = check_peer(peer, "after_stop", verify_persistent=True)
                    if peer_row["persistent"] != report["passive_peers_before"][peer]["persistent"]:
                        raise PhysicalGatewayError("Passive peer persistent settings changed.")
                    report["passive_peers_after"][peer] = peer_row
                except Exception as exc:
                    report.setdefault("passive_peer_restoration_errors", {})[peer] = {
                        "error": str(exc), "details": getattr(exc, "details", None)}
        if handler.is_open:
            handler.closePort()
        report["port_closed"] = not handler.is_open
    return report


def assign_isolated_servo_id(
    port: str,
    expected_serial_number: str,
    *,
    source_id: int = 1,
    target_id: int = 3,
) -> dict[str, Any]:
    """Assign an explicitly authorized ID with torque already off, without motion.

    The only permitted writes are the requested ID byte and, when needed,
    temporarily unlocking and restoring the EEPROM lock. No baud, calibration,
    torque, or position setting is written. Never retry the ID write after an
    uncertain acknowledgement; determine the outcome through reads instead.
    """
    import scservo_sdk as scs

    if (
        type(source_id) is not int or type(target_id) is not int
        or source_id == target_id
        or not 0 <= source_id <= 253 or not 0 <= target_id <= 253
    ):
        raise PhysicalGatewayError("Require distinct source and target unicast IDs.")
    candidates = tuple(sorted({*range(1, 7), source_id, target_id}))
    before = inspect_isolated_servo_read_only(
        port, expected_serial_number, candidate_ids=candidates,
    )
    responding = [p for p in before["probes"] if p["communication_result"] == 0]
    if len(responding) != 1 or responding[0]["id"] != source_id:
        raise PhysicalGatewayError("Expected only the isolated source motor to respond.")
    source = responding[0]
    registers = source.get("registers", {})
    if (
        source["model_number"] != 777 or source["device_error"] != 0
        or len(registers) != 3
        or any(not r["complete"] or r["device_error"] for r in registers.values())
        or registers["torque_enable"]["data"] != [0]
        or not 60 <= registers["present_telemetry"]["data"][6] <= 126
        or registers["present_telemetry"]["data"][9:11] != [0, 0]
    ):
        raise PhysicalGatewayError("Require a fault-free stationary STS3215 with torque off.")

    handler = scs.PortHandler(port)
    protocol = scs.PacketHandler(0)
    write_port = handler.writePort
    sent: list[list[int]] = []
    pending_write: tuple[int, int, int] | None = None
    allowed_reads = {(3, 2), (5, 1), (40, 1), (55, 1), (62, 2), (65, 2)}

    def guarded_transmit(packet: Any) -> int:
        nonlocal pending_write
        frame = list(packet)
        valid = (
            len(frame) >= 6 and frame[:2] == [255, 255]
            and frame[2] in (source_id, target_id)
            and len(frame) == frame[3] + 4 and sum(frame[2:]) & 255 == 255
        )
        ping = len(frame) == 6 and frame[3:5] == [2, 1]
        read = len(frame) == 8 and frame[3:5] == [4, 2] and tuple(frame[5:7]) in allowed_reads
        write = (
            len(frame) == 8 and frame[3:5] == [4, 3]
            and pending_write is not None
            and (frame[2], frame[5], frame[6]) == pending_write
        )
        if not valid or not (ping or read or write):
            raise PhysicalGatewayError("Servo ID gateway rejected an unapproved packet.")
        if write:
            pending_write = None  # Consume before sending: no implicit write retries.
        sent.append(frame)
        return write_port(packet)

    def read_bytes(servo_id: int, address: int, length: int) -> list[int]:
        data, result, error = protocol.readTxRx(handler, servo_id, address, length)
        if result != scs.COMM_SUCCESS or error or len(data) != length:
            raise PhysicalGatewayError(f"Could not verify register {address} at ID {servo_id}.")
        return list(data)

    def write_byte(servo_id: int, address: int, value: int) -> tuple[int, int]:
        nonlocal pending_write
        if not (
            (servo_id == source_id and address == 5 and value == target_id)
            or (address == 55 and value in (0, 1))
        ):
            raise PhysicalGatewayError("Only the requested ID and EEPROM lock may be written.")
        pending_write = (servo_id, address, value)
        try:
            return protocol.write1ByteTxRx(handler, servo_id, address, value)
        finally:
            pending_write = None

    handler.writePort = guarded_transmit
    report: dict[str, Any] = {
        "schema_version": "sim2claw.isolated_servo_id_assignment.v1",
        "proof_class": "physical_servo_configuration_no_motion",
        "source_id": source_id, "target_id": target_id, "before": before,
        "status": "failed", "motion_commands_sent": 0, "torque_writes_sent": 0,
    }
    original_lock = None
    lock_restore_needed = False
    current_id = source_id
    try:
        if not handler.setBaudRate(1_000_000):
            raise PhysicalGatewayError("Could not open the verified servo adapter.")
        if protocol.ping(handler, source_id) != (777, scs.COMM_SUCCESS, 0):
            raise PhysicalGatewayError("Source identity changed before ID assignment.")
        if protocol.ping(handler, target_id)[1] != scs.COMM_RX_TIMEOUT:
            raise PhysicalGatewayError("Target ID is occupied or could not be checked.")
        if read_bytes(source_id, 40, 1) != [0] or read_bytes(source_id, 65, 2) != [0, 0]:
            raise PhysicalGatewayError("Motor must remain stationary, fault-free, and torque off.")
        if not 60 <= read_bytes(source_id, 62, 2)[0] <= 126:
            raise PhysicalGatewayError("Supply voltage is outside the replacement specification.")
        original_lock = read_bytes(source_id, 55, 1)[0]
        if original_lock not in (0, 1):
            raise PhysicalGatewayError("Unexpected EEPROM lock value.")
        report["original_eeprom_lock"] = original_lock
        if original_lock == 1:
            lock_restore_needed = True
            write_byte(source_id, 55, 0)
            if read_bytes(source_id, 55, 1) != [0]:
                raise PhysicalGatewayError("EEPROM unlock did not verify.")
        report["id_write_acknowledgement"] = list(write_byte(source_id, 5, target_id))
        time.sleep(0.02)
        if protocol.ping(handler, target_id) != (777, scs.COMM_SUCCESS, 0):
            raise PhysicalGatewayError("New ID did not verify; the ID write was not retried.")
        current_id = target_id
        if read_bytes(target_id, 5, 1) != [target_id]:
            raise PhysicalGatewayError("ID register readback did not match.")
        if protocol.ping(handler, source_id)[1] != scs.COMM_RX_TIMEOUT:
            raise PhysicalGatewayError("Old ID still responds or absence could not be verified.")
        if lock_restore_needed:
            write_byte(target_id, 55, original_lock)
            if read_bytes(target_id, 55, 1) != [original_lock]:
                raise PhysicalGatewayError("EEPROM lock restoration did not verify.")
            lock_restore_needed = False
        if read_bytes(target_id, 40, 1) != [0] or read_bytes(target_id, 65, 2) != [0, 0]:
            raise PhysicalGatewayError("Post-change torque/status verification failed.")
        report["status"] = "assigned_and_verified"
        report["verified_id"] = target_id
        report["torque_enable"] = 0
    except Exception as error:
        report["error"] = str(error)
    finally:
        if handler.is_open and lock_restore_needed:
            # Recover only the lock state, never retry an uncertain ID write.
            try:
                if protocol.ping(handler, target_id) == (777, scs.COMM_SUCCESS, 0):
                    current_id = target_id
                write_byte(current_id, 55, original_lock)
                report["cleanup_lock_restored"] = read_bytes(current_id, 55, 1) == [original_lock]
            except Exception as error:
                report["cleanup_error"] = str(error)
        if handler.is_open:
            handler.closePort()
    report["transmitted_packets"] = sent
    report["port_closed"] = not handler.is_open
    return report


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
        configure_devices=False,
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

"""Guarded playback of a saved physical follower command trace.

The source commands remain an unqualified physical recording. Completing this
playback proves only that the reviewed gateway delivered the saved trajectory
without tripping its motion guards; it does not establish chess-task success.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Protocol

import numpy as np

from .paths import REPO_ROOT
from .physical_gateway import (
    BODY_EXCURSION_LIMIT_DEG,
    GRIPPER_EXCURSION_LIMIT,
    WRIST_ROLL_EXCURSION_LIMIT_DEG,
    GatewayIdentity,
    SO101PhysicalGateway,
    bounded_relative_target,
    shortest_delta_degrees,
)
from .scene import ROBOT_JOINTS
from .teleop_recording import RECEIPT_SCHEMA, recorder_preflight


PHYSICAL_TRACE_REPLAY_SCHEMA = "sim2claw.physical_trace_replay_attempt.v1"
MAX_REPLAY_SECONDS = 120.0
MAX_REPLAY_SAMPLES = 5_000
MAX_SOURCE_BODY_STEP_DEG = 8.0
MAX_SOURCE_WRIST_ROLL_STEP_DEG = 12.0
MAX_SOURCE_GRIPPER_STEP = 15.0
START_BODY_DELTA_LIMIT_DEG = 45.0
START_WRIST_ROLL_DELTA_LIMIT_DEG = 60.0
START_GRIPPER_DELTA_LIMIT = 20.0
START_BODY_RATE_DEG_S = 10.0
START_WRIST_ROLL_RATE_DEG_S = 15.0
START_GRIPPER_RATE_S = 20.0
START_COMMAND_HZ = 20.0


class PhysicalTraceReplayError(RuntimeError):
    """A physical replay was rejected or stopped by a fail-closed guard."""

    def __init__(self, message: str, *, run_directory: Path | None = None):
        super().__init__(message)
        self.run_directory = run_directory


@dataclass(frozen=True)
class PhysicalTraceSource:
    recording_directory: Path
    receipt: dict[str, Any]
    rows: tuple[dict[str, Any], ...]
    commands: np.ndarray
    elapsed_seconds: np.ndarray


class ReplayGateway(Protocol):
    leader: Any
    lower_limits: np.ndarray
    upper_limits: np.ndarray

    def open(
        self,
        *,
        enable_motion: bool,
        paired_pose_confirmed: bool = False,
    ) -> dict[str, Any]: ...

    def sample(self, elapsed_seconds: float) -> dict[str, Any]: ...

    def close(self) -> None: ...


ProgressCallback = Callable[[dict[str, Any]], None]
GatewayFactory = Callable[[GatewayIdentity], ReplayGateway]
Clock = Callable[[], float]
Sleep = Callable[[float], None]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _position_dict(values: np.ndarray) -> dict[str, float]:
    return {
        f"{joint}.pos": float(value)
        for joint, value in zip(ROBOT_JOINTS, values, strict=True)
    }


def load_physical_trace_source(
    recording_directory: Path,
    *,
    allowed_root: Path | None = None,
) -> PhysicalTraceSource:
    recording_directory = recording_directory.resolve()
    source_root = (
        allowed_root or REPO_ROOT / "datasets" / "act_source_recordings"
    ).resolve()
    if not recording_directory.is_relative_to(source_root):
        raise PhysicalTraceReplayError(
            "Physical replay is limited to finalized ACT source recordings."
        )
    receipt_path = recording_directory / "recording_receipt.json"
    samples_path = recording_directory / "samples.jsonl"
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        lines = samples_path.read_text(encoding="utf-8").splitlines()
    except (OSError, json.JSONDecodeError) as error:
        raise PhysicalTraceReplayError(
            f"Physical replay source is unreadable: {error}"
        ) from error
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise PhysicalTraceReplayError("Recording receipt schema is not supported.")
    if receipt.get("mode") != "physical_follower":
        raise PhysicalTraceReplayError("Only physical-follower recordings can move the follower.")
    if _sha256(samples_path) != receipt.get("samples_sha256"):
        raise PhysicalTraceReplayError("Recorded samples do not match their finalized receipt.")
    rows: list[dict[str, Any]] = []
    try:
        rows = [json.loads(line) for line in lines if line.strip()]
        commands = np.asarray(
            [row["follower_command_degrees"] for row in rows],
            dtype=np.float64,
        )
        timestamps = np.asarray(
            [row["timestamp_monotonic_seconds"] for row in rows],
            dtype=np.float64,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise PhysicalTraceReplayError(
            f"Recorded command trace is malformed: {error}"
        ) from error
    if not rows or len(rows) > MAX_REPLAY_SAMPLES:
        raise PhysicalTraceReplayError("Recorded command count is outside the replay guard.")
    if commands.shape != (len(rows), 6) or not np.all(np.isfinite(commands)):
        raise PhysicalTraceReplayError("Replay requires finite six-joint commands.")
    if timestamps.shape != (len(rows),) or not np.all(np.isfinite(timestamps)):
        raise PhysicalTraceReplayError("Replay timestamps are invalid.")
    elapsed = timestamps - timestamps[0]
    if np.any(np.diff(elapsed) <= 0.0):
        raise PhysicalTraceReplayError("Replay timestamps must be strictly increasing.")
    if float(elapsed[-1]) > MAX_REPLAY_SECONDS:
        raise PhysicalTraceReplayError("Recorded episode is longer than the replay guard.")
    if len(rows) != int(receipt.get("sample_count") or -1):
        raise PhysicalTraceReplayError("Receipt sample count does not match the command trace.")
    if len(rows) > 1:
        steps = np.diff(commands, axis=0)
        steps[:, 4] = [
            shortest_delta_degrees(float(current), float(previous))
            for previous, current in zip(commands[:-1, 4], commands[1:, 4], strict=True)
        ]
        maximums = np.max(np.abs(steps), axis=0)
        if float(np.max(maximums[:4])) > MAX_SOURCE_BODY_STEP_DEG:
            raise PhysicalTraceReplayError("Recorded body-joint step exceeds the replay guard.")
        if float(maximums[4]) > MAX_SOURCE_WRIST_ROLL_STEP_DEG:
            raise PhysicalTraceReplayError("Recorded wrist-roll step exceeds the replay guard.")
        if float(maximums[5]) > MAX_SOURCE_GRIPPER_STEP:
            raise PhysicalTraceReplayError("Recorded gripper step exceeds the replay guard.")
    return PhysicalTraceSource(
        recording_directory=recording_directory,
        receipt=receipt,
        rows=tuple(rows),
        commands=commands,
        elapsed_seconds=elapsed,
    )


def validate_replay_envelope(
    commands: np.ndarray,
    live_start: np.ndarray,
    *,
    lower_limits: np.ndarray,
    upper_limits: np.ndarray,
) -> dict[str, Any]:
    if commands.ndim != 2 or commands.shape[1:] != (6,):
        raise PhysicalTraceReplayError("Replay envelope requires six-joint commands.")
    first_delta = commands[0] - live_start
    first_delta[4] = shortest_delta_degrees(
        float(commands[0, 4]),
        float(live_start[4]),
    )
    maximum_start_body = float(np.max(np.abs(first_delta[:5])))
    if maximum_start_body > START_BODY_DELTA_LIMIT_DEG:
        raise PhysicalTraceReplayError(
            "Follower is too far from the episode start pose: "
            f"{maximum_start_body:.1f}° (limit {START_BODY_DELTA_LIMIT_DEG:.1f}°)."
        )
    if abs(float(first_delta[4])) > START_WRIST_ROLL_DELTA_LIMIT_DEG:
        raise PhysicalTraceReplayError("Follower wrist roll is too far from the replay start.")
    if abs(float(first_delta[5])) > START_GRIPPER_DELTA_LIMIT:
        raise PhysicalTraceReplayError("Follower gripper is too far from the replay start.")
    maximum_excursion = np.zeros(6, dtype=np.float64)
    for command in commands:
        bounded, delta = bounded_relative_target(
            command.copy(),
            live_start.copy(),
            live_start.copy(),
            lower_limits=lower_limits,
            upper_limits=upper_limits,
        )
        if np.any(np.abs(bounded - command) > 0.5):
            raise PhysicalTraceReplayError(
                "Recorded command leaves the follower calibration or excursion envelope."
            )
        maximum_excursion = np.maximum(maximum_excursion, np.abs(delta))
    if float(np.max(maximum_excursion[:4])) > BODY_EXCURSION_LIMIT_DEG:
        raise PhysicalTraceReplayError("Replay body excursion exceeds the gateway limit.")
    if float(maximum_excursion[4]) > WRIST_ROLL_EXCURSION_LIMIT_DEG:
        raise PhysicalTraceReplayError("Replay wrist excursion exceeds the gateway limit.")
    if float(maximum_excursion[5]) > GRIPPER_EXCURSION_LIMIT:
        raise PhysicalTraceReplayError("Replay gripper excursion exceeds the gateway limit.")
    return {
        "live_start_degrees": live_start.tolist(),
        "first_command_degrees": commands[0].tolist(),
        "first_command_delta_degrees": first_delta.tolist(),
        "maximum_start_body_delta_degrees": maximum_start_body,
        "maximum_replay_excursion_degrees": maximum_excursion.tolist(),
    }


class _SyntheticBus:
    def __init__(self) -> None:
        self.is_connected = False

    def connect(self) -> None:
        self.is_connected = True

    def disable_torque(self) -> None:
        return None

    def disconnect(self, _disable_torque: bool = True) -> None:
        self.is_connected = False


class _RecordedCommandLeader:
    """Feeds recorded follower targets into the gateway's leader input."""

    def __init__(self, follower: Any):
        self.bus = _SyntheticBus()
        self.follower = follower
        self.is_calibrated = True
        self.target: np.ndarray | None = None

    def configure(self) -> None:
        return None

    def set_target(self, values: np.ndarray) -> None:
        self.target = values.copy()

    def get_action(self) -> dict[str, float]:
        if self.target is None:
            return self.follower.get_observation()
        return _position_dict(self.target)


def _physical_replay_devices(identity: GatewayIdentity) -> tuple[Any, Any]:
    from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

    follower = SO101Follower(
        SO101FollowerConfig(
            port=identity.follower_port,
            id="so101_follower",
            use_degrees=True,
            max_relative_target=None,
            disable_torque_on_disconnect=True,
        )
    )
    return _RecordedCommandLeader(follower), follower


def _default_gateway_factory(identity: GatewayIdentity) -> ReplayGateway:
    return SO101PhysicalGateway(
        identity,
        device_factory=_physical_replay_devices,
        configure_devices=False,
    )


def _gateway_identity() -> GatewayIdentity:
    preflight = recorder_preflight()
    if not preflight["modes"]["physical_follower"]["ready"]:
        raise PhysicalTraceReplayError(
            str(preflight["modes"]["physical_follower"]["reason"])
        )
    return GatewayIdentity(
        leader_port=str(preflight["devices"]["leader"]["port"]),
        follower_port=str(preflight["devices"]["follower"]["port"]),
        leader_calibration_sha256=str(
            preflight["calibrations"]["leader"]["sha256"]
        ),
        follower_calibration_sha256=str(
            preflight["calibrations"]["follower"]["sha256"]
        ),
    )


def _mapped_leader_target(
    follower_target: np.ndarray,
    leader_start: np.ndarray,
    follower_start: np.ndarray,
) -> np.ndarray:
    target = leader_start + (follower_target - follower_start)
    target[4] = leader_start[4] + shortest_delta_degrees(
        float(follower_target[4]),
        float(follower_start[4]),
    )
    return target


def run_physical_trace_replay(
    recording_directory: Path,
    *,
    operator_acknowledged: bool,
    output_root: Path | None = None,
    identity: GatewayIdentity | None = None,
    gateway_factory: GatewayFactory = _default_gateway_factory,
    clock: Clock = time.monotonic,
    sleep: Sleep = time.sleep,
    progress: ProgressCallback | None = None,
    allowed_source_root: Path | None = None,
) -> dict[str, Any]:
    if not operator_acknowledged:
        raise PhysicalTraceReplayError(
            "Physical replay requires an explicit operator acknowledgement."
        )
    source = load_physical_trace_source(
        recording_directory,
        allowed_root=allowed_source_root,
    )
    gateway_identity = identity or _gateway_identity()
    destination_root = (output_root or REPO_ROOT / "runs" / "physical_replays").resolve()
    run_id = (
        datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + str(source.receipt["recording_id"])
        + "-"
        + uuid.uuid4().hex[:8]
    )
    run_directory = destination_root / run_id
    run_directory.mkdir(parents=True, exist_ok=False)
    samples_path = run_directory / "replay_samples.jsonl"
    receipt_path = run_directory / "replay_receipt.json"
    gateway = gateway_factory(gateway_identity)
    completed_samples = 0
    clamped_samples = 0
    exact_samples = 0
    opened: dict[str, Any] | None = None
    envelope: dict[str, Any] | None = None
    started_at = datetime.now(UTC).isoformat()
    wall_started: float | None = None
    error: Exception | None = None
    shutdown_error: Exception | None = None

    def emit(event: str, **values: Any) -> None:
        if progress is not None:
            progress({"event": event, **values})

    try:
        emit("opening_gateway", label=source.receipt.get("label"))
        opened = gateway.open(enable_motion=True, paired_pose_confirmed=True)
        leader_start = np.asarray(opened["leader_start_degrees"], dtype=np.float64)
        follower_start = np.asarray(opened["follower_start_degrees"], dtype=np.float64)
        envelope = validate_replay_envelope(
            source.commands,
            follower_start,
            lower_limits=gateway.lower_limits,
            upper_limits=gateway.upper_limits,
        )
        first_delta = np.asarray(
            envelope["first_command_delta_degrees"],
            dtype=np.float64,
        )
        pre_roll_seconds = max(
            0.5,
            float(np.max(np.abs(first_delta[:4]))) / START_BODY_RATE_DEG_S,
            abs(float(first_delta[4])) / START_WRIST_ROLL_RATE_DEG_S,
            abs(float(first_delta[5])) / START_GRIPPER_RATE_S,
        )
        pre_roll_steps = max(1, math.ceil(pre_roll_seconds * START_COMMAND_HZ))
        emit(
            "pre_roll_started",
            duration_seconds=pre_roll_seconds,
            maximum_body_delta_degrees=envelope[
                "maximum_start_body_delta_degrees"
            ],
        )
        wall_started = clock()
        with samples_path.open("w", encoding="utf-8") as sample_handle:
            for index in range(1, pre_roll_steps + 1):
                deadline = wall_started + index / START_COMMAND_HZ
                delay = deadline - clock()
                if delay > 0:
                    sleep(delay)
                fraction = index / pre_roll_steps
                smooth = fraction * fraction * (3.0 - 2.0 * fraction)
                follower_target = follower_start + smooth * first_delta
                gateway.leader.set_target(
                    _mapped_leader_target(
                        follower_target,
                        leader_start,
                        follower_start,
                    )
                )
                gateway.sample(clock() - wall_started)
                if index == pre_roll_steps or index % int(START_COMMAND_HZ) == 0:
                    emit(
                        "pre_roll_progress",
                        current=index,
                        total=pre_roll_steps,
                    )

            trace_started = clock()
            emit(
                "trace_started",
                samples=len(source.rows),
                duration_seconds=float(source.elapsed_seconds[-1]),
            )
            for index, (source_row, follower_target, source_elapsed) in enumerate(
                zip(
                    source.rows,
                    source.commands,
                    source.elapsed_seconds,
                    strict=True,
                )
            ):
                deadline = trace_started + float(source_elapsed)
                delay = deadline - clock()
                if delay > 0:
                    sleep(delay)
                gateway.leader.set_target(
                    _mapped_leader_target(
                        follower_target,
                        leader_start,
                        follower_start,
                    )
                )
                sample = gateway.sample(clock() - wall_started)
                sent = np.asarray(
                    sample["follower_command_degrees"],
                    dtype=np.float64,
                )
                is_exact = bool(np.all(np.abs(sent - follower_target) <= 0.25))
                exact_samples += int(is_exact)
                clamped_samples += int(bool(sample.get("safety_clamped")))
                completed_samples += 1
                replay_row = {
                    **sample,
                    "schema_version": PHYSICAL_TRACE_REPLAY_SCHEMA,
                    "source_recording_id": source.receipt["recording_id"],
                    "source_sample_index": source_row["sample_index"],
                    "source_elapsed_seconds": float(source_elapsed),
                    "requested_source_command_degrees": follower_target.tolist(),
                    "source_command_sent_exactly": is_exact,
                    "replay_elapsed_seconds": clock() - trace_started,
                }
                sample_handle.write(
                    json.dumps(replay_row, separators=(",", ":"), sort_keys=True)
                    + "\n"
                )
                sample_handle.flush()
                if completed_samples == 1 or completed_samples % 25 == 0:
                    emit(
                        "trace_progress",
                        current=completed_samples,
                        total=len(source.rows),
                        source_elapsed_seconds=float(source_elapsed),
                    )
            emit("trace_completed", samples=completed_samples)
    except Exception as caught:
        error = caught
    finally:
        try:
            gateway.close()
        except Exception as caught:
            shutdown_error = caught

    completed_at = datetime.now(UTC).isoformat()
    receipt = {
        "schema_version": PHYSICAL_TRACE_REPLAY_SCHEMA,
        "run_id": run_id,
        "status": "completed" if error is None and shutdown_error is None else "failed",
        "source_recording_id": source.receipt["recording_id"],
        "source_label": source.receipt.get("label"),
        "source_samples_sha256": source.receipt["samples_sha256"],
        "source_sample_count": len(source.rows),
        "completed_sample_count": completed_samples,
        "exact_command_sample_count": exact_samples,
        "safety_clamped_sample_count": clamped_samples,
        "started_at": started_at,
        "completed_at": completed_at,
        "wall_duration_seconds": (
            None if wall_started is None else max(0.0, clock() - wall_started)
        ),
        "gateway_open_report": opened,
        "replay_envelope": envelope,
        "replay_samples_path": samples_path.name,
        "replay_samples_sha256": _sha256(samples_path) if samples_path.is_file() else None,
        "physical_follower_torque_enabled": False,
        "commands_requested_from_source_trace": True,
        "task_success_verified": False,
        "learned_policy_verified": False,
        "physical_task_evaluator_result": None,
        "failure_type": type(error).__name__ if error is not None else None,
        "failure_message": str(error) if error is not None else None,
        "shutdown_failure_type": (
            type(shutdown_error).__name__ if shutdown_error is not None else None
        ),
        "shutdown_failure_message": (
            str(shutdown_error) if shutdown_error is not None else None
        ),
    }
    _atomic_json(receipt_path, receipt)
    emit(
        "torque_released",
        status=receipt["status"],
        run_directory=str(run_directory),
    )
    if error is not None or shutdown_error is not None:
        failure = error or shutdown_error
        assert failure is not None
        raise PhysicalTraceReplayError(
            f"Physical replay stopped safely: {type(failure).__name__}: {failure}",
            run_directory=run_directory,
        ) from failure
    return {**receipt, "run_directory": str(run_directory)}

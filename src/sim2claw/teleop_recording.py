"""Leader-arm source recording for the goal-conditioned ACT data pipeline.

Raw recordings are not ACT training rows.  They remain pending deterministic
replay and separately owned evaluator admission.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Protocol

import mujoco
import numpy as np

from .act_pick_place import (
    load_act_pick_place_task_contract,
    resolve_structured_goal,
    task_contract_sha256,
)
from .paths import REPO_ROOT
from .physical_gateway import (
    GATEWAY_SCHEMA,
    GatewayIdentity,
    SO101PhysicalGateway,
    inspect_physical_gateway,
    synchronize_physical_gateway,
)
from .physical_sim_replay import replay_physical_recording
from .scene import (
    CURRENT_TASK_LAYOUT_ID,
    CURRENT_TASK_PIECE_LAYOUT,
    ROBOT_JOINTS,
    TELEOP_PAWN_SOURCE_SQUARES,
    build_scene_spec,
    initialize_robot_poses,
)


SOURCE_SCHEMA = "sim2claw.act_source_episode.v1"
RECEIPT_SCHEMA = "sim2claw.act_source_recording_receipt.v1"
DEFAULT_LEADER_SERIAL_SUFFIX = "0448141"
DEFAULT_FOLLOWER_SERIAL_SUFFIX = "0406411"
DEFAULT_SAMPLE_HZ = 20
LABEL_PATTERN = re.compile(r"[^a-z0-9]+")
TELEOP_DESTINATION_SQUARES = tuple(
    f"{file_name}{rank}" for rank in "1234" for file_name in "abcdefgh"
)


class RecorderError(RuntimeError):
    """Expected operator-facing recording error."""


class RecorderConflict(RecorderError):
    """The requested transition conflicts with the current recorder state."""


class RecorderBackend(Protocol):
    def open(self) -> dict[str, Any]: ...

    def sample(self, elapsed_seconds: float) -> dict[str, Any]: ...

    def close(self) -> None: ...


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _slug(value: str) -> str:
    normalized = LABEL_PATTERN.sub("-", value.strip().lower()).strip("-")
    if not normalized:
        raise RecorderError("A recording label is required before saving.")
    return normalized[:72]


def _port_for_suffix(ports: list[str], suffix: str) -> str | None:
    return next((port for port in ports if suffix in Path(port).name), None)


def discover_so101_devices(dev_root: Path = Path("/dev")) -> dict[str, Any]:
    ports = sorted(str(path) for path in dev_root.glob("cu.usbmodem*"))
    leader = _port_for_suffix(ports, DEFAULT_LEADER_SERIAL_SUFFIX)
    follower = _port_for_suffix(ports, DEFAULT_FOLLOWER_SERIAL_SUFFIX)
    billboard = [port for port in ports if "SN23456789" in Path(port).name]
    unknown = [port for port in ports if port not in {leader, follower} and port not in billboard]
    return {
        "leader": {
            "role": "so101_leader",
            "port": leader,
            "serial_suffix": DEFAULT_LEADER_SERIAL_SUFFIX,
            "connected": leader is not None,
        },
        "follower": {
            "role": "so101_follower",
            "port": follower,
            "serial_suffix": DEFAULT_FOLLOWER_SERIAL_SUFFIX,
            "connected": follower is not None,
        },
        "ignored_billboard_ports": billboard,
        "unknown_serial_ports": unknown,
    }


def _calibration_paths(calibration_root: Path | None = None) -> dict[str, Path]:
    root = calibration_root or Path.home() / ".cache" / "huggingface" / "lerobot" / "calibration"
    return {
        "leader": root / "teleoperators" / "so_leader" / "so101_leader.json",
        "follower": root / "robots" / "so_follower" / "so101_follower.json",
    }


def recorder_preflight(
    *,
    dev_root: Path = Path("/dev"),
    calibration_root: Path | None = None,
) -> dict[str, Any]:
    devices = discover_so101_devices(dev_root)
    calibrations: dict[str, Any] = {}
    for role, path in _calibration_paths(calibration_root).items():
        calibrations[role] = {
            "path": str(path),
            "present": path.is_file(),
            "sha256": _sha256(path) if path.is_file() else None,
        }
    try:
        import lerobot

        lerobot_version = str(lerobot.__version__)
    except (ImportError, AttributeError):
        lerobot_version = None
    leader_ready = bool(
        devices["leader"]["connected"]
        and calibrations["leader"]["present"]
        and lerobot_version
    )
    follower_ready = bool(
        devices["follower"]["connected"]
        and calibrations["follower"]["present"]
        and lerobot_version
    )
    return {
        "schema_version": "sim2claw.teleop_preflight.v1",
        "checked_at": _utc_now(),
        "devices": devices,
        "calibrations": calibrations,
        "runtime": {
            "lerobot_version": lerobot_version,
            "required_lerobot_version": "0.6.0",
            "task_contract_sha256": task_contract_sha256(),
        },
        "modes": {
            "simulation_follower": {
                "ready": leader_ready,
                "physical_motion": False,
                "reason": (
                    None
                    if leader_ready
                    else "Leader bus, calibration, or LeRobot runtime is missing."
                ),
            },
            "physical_follower": {
                "ready": leader_ready and follower_ready,
                "device_ready": leader_ready and follower_ready,
                "physical_motion": True,
                "reason": (
                    None
                    if leader_ready and follower_ready
                    else "Both identified buses, calibrations, and LeRobot are required."
                ),
            },
        },
        "physical_enable_environment": None,
        "required_physical_path": GATEWAY_SCHEMA,
        "physical_motion_requires_operator_acknowledgement": True,
        "billboard_is_not_motor_bus": True,
    }


def _gateway_identity(preflight: dict[str, Any]) -> GatewayIdentity:
    leader_port = preflight["devices"]["leader"]["port"]
    follower_port = preflight["devices"]["follower"]["port"]
    leader_sha = preflight["calibrations"]["leader"]["sha256"]
    follower_sha = preflight["calibrations"]["follower"]["sha256"]
    if not all((leader_port, follower_port, leader_sha, follower_sha)):
        raise RecorderError("Physical gateway identity is incomplete.")
    return GatewayIdentity(
        leader_port=str(leader_port),
        follower_port=str(follower_port),
        leader_calibration_sha256=str(leader_sha),
        follower_calibration_sha256=str(follower_sha),
    )


def physical_gateway_preflight(
    *,
    dev_root: Path = Path("/dev"),
    calibration_root: Path | None = None,
) -> dict[str, Any]:
    preflight = recorder_preflight(
        dev_root=dev_root,
        calibration_root=calibration_root,
    )
    if not preflight["modes"]["physical_follower"]["ready"]:
        raise RecorderError(str(preflight["modes"]["physical_follower"]["reason"]))
    return inspect_physical_gateway(_gateway_identity(preflight))


def physical_gateway_sync(
    *,
    dev_root: Path = Path("/dev"),
    calibration_root: Path | None = None,
) -> dict[str, Any]:
    preflight = recorder_preflight(
        dev_root=dev_root,
        calibration_root=calibration_root,
    )
    if not preflight["modes"]["physical_follower"]["ready"]:
        raise RecorderError(str(preflight["modes"]["physical_follower"]["reason"]))
    return synchronize_physical_gateway(_gateway_identity(preflight))


def _leader_action_vector(action: dict[str, float]) -> np.ndarray:
    return np.asarray([float(action[f"{joint}.pos"]) for joint in ROBOT_JOINTS], dtype=np.float64)


class LeRobotLeader:
    def __init__(self, port: str):
        self.port = port
        self.device: Any = None

    def open(self) -> None:
        from lerobot.teleoperators.so_leader import SO101Leader, SO101LeaderConfig

        self.device = SO101Leader(
            SO101LeaderConfig(port=self.port, id="so101_leader", use_degrees=True)
        )
        self.device.connect(calibrate=False)
        self.device.disable_torque()
        if not self.device.is_calibrated:
            raise RecorderError("Leader calibration does not match the connected physical arm.")

    def read(self) -> dict[str, float]:
        if self.device is None:
            raise RecorderError("Leader is not open.")
        return self.device.get_action()

    def close(self) -> None:
        if self.device is None:
            return
        try:
            self.device.disable_torque()
        finally:
            if self.device.is_connected:
                self.device.disconnect()
            self.device = None


class SimulationFollowerBackend:
    proof_class = "simulation_teleoperation_source"

    def __init__(self, request: dict[str, Any], preflight: dict[str, Any]):
        self.request = request
        self.preflight = preflight
        leader_port = preflight["devices"]["leader"]["port"]
        if not leader_port:
            raise RecorderError("The expected SO-101 leader bus is not connected.")
        self.leader = LeRobotLeader(str(leader_port))
        self.model: mujoco.MjModel | None = None
        self.data: mujoco.MjData | None = None
        self.actuator_ids: list[int] = []
        self.joint_qpos_addresses: list[int] = []
        self.joint_dof_addresses: list[int] = []
        self.piece_body_id = -1
        self.target_pose = resolve_structured_goal(
            str(request["piece_id"]), str(request["target_square"])
        )["target_pose"]
        self.sample_hz = int(request.get("sample_hz") or DEFAULT_SAMPLE_HZ)

    def _command_from_leader(self, leader_values: np.ndarray) -> np.ndarray:
        if self.model is None:
            raise RecorderError("Simulator is not open.")
        command = np.empty(6, dtype=np.float64)
        command[:5] = np.deg2rad(leader_values[:5])
        gripper_low, gripper_high = self.model.actuator_ctrlrange[self.actuator_ids[-1]]
        command[-1] = gripper_low + np.clip(leader_values[-1], 0.0, 100.0) / 100.0 * (
            gripper_high - gripper_low
        )
        bounds = self.model.actuator_ctrlrange[self.actuator_ids]
        return np.clip(command, bounds[:, 0], bounds[:, 1])

    def open(self) -> dict[str, Any]:
        self.leader.open()
        self.model = build_scene_spec(piece_layout=CURRENT_TASK_PIECE_LAYOUT).compile()
        self.data = mujoco.MjData(self.model)
        initialize_robot_poses(self.model, self.data)
        for joint in ROBOT_JOINTS:
            name = f"left_{joint}"
            actuator_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
            joint_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, name)
            if actuator_id < 0 or joint_id < 0:
                raise RecorderError(f"Simulator is missing {name} control.")
            self.actuator_ids.append(actuator_id)
            self.joint_qpos_addresses.append(int(self.model.jnt_qposadr[joint_id]))
            self.joint_dof_addresses.append(int(self.model.jnt_dofadr[joint_id]))
        self.piece_body_id = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_BODY, str(self.request["piece_id"])
        )
        if self.piece_body_id < 0:
            raise RecorderError(f"Unknown simulated piece: {self.request['piece_id']}")
        leader_values = _leader_action_vector(self.leader.read())
        command = self._command_from_leader(leader_values)
        self.data.qpos[self.joint_qpos_addresses] = command
        self.data.ctrl[self.actuator_ids] = command
        mujoco.mj_forward(self.model, self.data)
        return {
            "proof_class": self.proof_class,
            "leader_port": self.leader.port,
            "follower": "mujoco:left_so101",
            "physical_follower_torque_enabled": False,
            "physical_gateway_preflight": None,
            "sim_replay": None,
            "pose_inputs_available": True,
        }

    def sample(self, elapsed_seconds: float) -> dict[str, Any]:
        if self.model is None or self.data is None:
            raise RecorderError("Simulator is not open.")
        leader_action = self.leader.read()
        leader_values = _leader_action_vector(leader_action)
        command = self._command_from_leader(leader_values)
        self.data.ctrl[self.actuator_ids] = command
        steps = max(1, round((1.0 / self.sample_hz) / float(self.model.opt.timestep)))
        mujoco.mj_step(self.model, self.data, nstep=steps)
        piece_position = self.data.xpos[self.piece_body_id].astype(float).tolist()
        piece_quaternion = self.data.xquat[self.piece_body_id].astype(float).tolist()
        return {
            "elapsed_seconds": elapsed_seconds,
            "leader_target_degrees": leader_values.tolist(),
            "follower_command_rad": command.tolist(),
            "follower_actual_position_rad": self.data.qpos[
                self.joint_qpos_addresses
            ].astype(float).tolist(),
            "follower_actual_velocity_rad_s": self.data.qvel[
                self.joint_dof_addresses
            ].astype(float).tolist(),
            "leader_follower_error_rad": (
                command - self.data.qpos[self.joint_qpos_addresses]
            ).astype(float).tolist(),
            "selected_piece_pose_world": [*piece_position, *piece_quaternion],
            "continuous_target_pose_world": self.target_pose,
            "pose_inputs_available": True,
            "available_motor_current": None,
            "physical_follower_torque_enabled": False,
        }

    def close(self) -> None:
        self.leader.close()
        self.data = None
        self.model = None


class PhysicalFollowerBackend:
    proof_class = "physical_teleoperation_source_unqualified"

    def __init__(self, request: dict[str, Any], preflight: dict[str, Any]):
        self.request = request
        self.gateway = SO101PhysicalGateway(_gateway_identity(preflight))

    def open(self) -> dict[str, Any]:
        if not self.request.get("physical_safety_acknowledged"):
            raise RecorderError("Physical safety acknowledgement is required.")
        if not self.request.get("physical_pose_match_acknowledged"):
            raise RecorderError("Paired physical-pose acknowledgement is required.")
        gateway = self.gateway.open(
            enable_motion=True,
            paired_pose_confirmed=True,
        )
        return {
            **gateway,
            "proof_class": self.proof_class,
            "pose_inputs_available": False,
            "physical_follower_torque_enabled": True,
        }

    def sample(self, elapsed_seconds: float) -> dict[str, Any]:
        return self.gateway.sample(elapsed_seconds)

    def close(self) -> None:
        self.gateway.close()


BackendFactory = Callable[[dict[str, Any], dict[str, Any]], RecorderBackend]


def _default_backend_factory(request: dict[str, Any], preflight: dict[str, Any]) -> RecorderBackend:
    mode = request["mode"]
    if mode == "simulation_follower":
        return SimulationFollowerBackend(request, preflight)
    if mode == "physical_follower":
        return PhysicalFollowerBackend(request, preflight)
    raise RecorderError(f"Unsupported recording mode: {mode}")


@dataclass
class RecorderPaths:
    repo_root: Path = REPO_ROOT

    @property
    def drafts(self) -> Path:
        return self.repo_root / "runs" / "teleop_recordings" / "drafts"

    @property
    def recordings(self) -> Path:
        return self.repo_root / "datasets" / "act_source_recordings"

    @property
    def failures(self) -> Path:
        return self.repo_root / "runs" / "teleop_recordings" / "failed_attempts"


class TeleopRecordingManager:
    def __init__(
        self,
        *,
        repo_root: Path = REPO_ROOT,
        backend_factory: BackendFactory = _default_backend_factory,
        dev_root: Path = Path("/dev"),
        calibration_root: Path | None = None,
    ):
        self.paths = RecorderPaths(repo_root.resolve())
        self.backend_factory = backend_factory
        self.dev_root = dev_root
        self.calibration_root = calibration_root
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.ready_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.backend: RecorderBackend | None = None
        self.state: dict[str, Any] = self._recover_existing_state()

    def _idle_state(self) -> dict[str, Any]:
        return {
            "schema_version": "sim2claw.teleop_recorder_state.v1",
            "status": "idle",
            "recording_id": None,
            "mode": None,
            "sample_count": 0,
            "started_at": None,
            "stopped_at": None,
            "duration_seconds": 0.0,
            "last_sample": None,
            "draft_path": None,
            "saved_path": None,
            "error": None,
            "last_error": None,
            "last_failed_recording_id": None,
            "last_failed_attempt_path": None,
            "training_admission": "not_applicable",
            "physical_follower_torque_enabled": False,
        }

    def _archive_failed_draft(self, failed_state: dict[str, Any]) -> str | None:
        draft_path = failed_state.get("draft_path")
        recording_id = str(failed_state.get("recording_id") or "unknown-attempt")
        if not draft_path:
            return None
        draft = (self.paths.repo_root / str(draft_path)).resolve()
        if not draft.is_relative_to(self.paths.drafts.resolve()) or not draft.exists():
            return None
        destination = self.paths.failures / recording_id
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            return str(destination.relative_to(self.paths.repo_root))
        shutil.move(str(draft), str(destination))
        archived_state = {
            **failed_state,
            "status": "failed_attempt_archived",
            "physical_follower_torque_enabled": False,
            "archived_at": _utc_now(),
        }
        _atomic_json(destination / "draft_state.json", archived_state)
        return str(destination.relative_to(self.paths.repo_root))

    def _recover_existing_state(self) -> dict[str, Any]:
        recovered: dict[str, Any] | None = None
        last_failure: dict[str, Any] | None = None
        state_paths = sorted(
            self.paths.drafts.glob("*/draft_state.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for state_path in state_paths:
            try:
                candidate = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            status = candidate.get("status")
            if status == "awaiting_label" and recovered is None:
                recovered = {
                    **candidate,
                    "physical_follower_torque_enabled": False,
                    "recovered_after_server_restart": True,
                }
            elif status == "error":
                archived_path = self._archive_failed_draft(candidate)
                if last_failure is None:
                    last_failure = {
                        "last_error": candidate.get("error"),
                        "last_failed_recording_id": candidate.get("recording_id"),
                        "last_failed_attempt_path": archived_path,
                    }
        if recovered is not None:
            return recovered
        return {**self._idle_state(), **(last_failure or {})}

    def _return_failed_attempt_to_ready(self) -> None:
        with self.lock:
            if self.state.get("status") != "error":
                return
            failed_state = json.loads(json.dumps(self.state))
        archived_path = self._archive_failed_draft(failed_state)
        with self.lock:
            self.state = {
                **self._idle_state(),
                "last_error": failed_state.get("error"),
                "last_failed_recording_id": failed_state.get("recording_id"),
                "last_failed_attempt_path": archived_path,
            }

    def preflight(self) -> dict[str, Any]:
        return recorder_preflight(
            dev_root=self.dev_root,
            calibration_root=self.calibration_root,
        )

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            snapshot = json.loads(json.dumps(self.state))
        snapshot["preflight"] = self.preflight()
        return snapshot

    def verify_physical_gateway(self) -> dict[str, Any]:
        with self.lock:
            if self.state["status"] in {"starting", "recording"}:
                raise RecorderConflict("Stop the active recording before bus preflight.")
        report = physical_gateway_preflight(
            dev_root=self.dev_root,
            calibration_root=self.calibration_root,
        )
        with self.lock:
            self.state["physical_gateway_preflight"] = report
        return self.snapshot()

    def synchronize_physical_gateway(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        if not request.get("physical_safety_acknowledged"):
            raise RecorderError("Physical safety acknowledgement is required before Sync.")
        self._return_failed_attempt_to_ready()
        with self.lock:
            if self.state["status"] in {"starting", "recording", "awaiting_label"}:
                raise RecorderConflict("Stop and label the current recording before Sync.")
        report = physical_gateway_sync(
            dev_root=self.dev_root,
            calibration_root=self.calibration_root,
        )
        with self.lock:
            self.state["physical_gateway_sync"] = report
            self.state["physical_gateway_preflight"] = report
            self.state["last_error"] = None
        return self.snapshot()

    def start(self, request: dict[str, Any], *, timeout_seconds: float = 20.0) -> dict[str, Any]:
        self._return_failed_attempt_to_ready()
        contract = load_act_pick_place_task_contract()
        mode = str(request.get("mode") or "simulation_follower")
        if mode not in {"simulation_follower", "physical_follower"}:
            raise RecorderError("Choose a simulator or physical follower.")
        source_square = str(request.get("source_square") or "").lower()
        if source_square not in TELEOP_PAWN_SOURCE_SQUARES:
            raise RecorderError("Choose one of the eight declared pawn source squares.")
        piece_id = f"brown_pawn_{source_square}"
        target_square = str(request.get("target_square") or "").lower()
        if target_square not in TELEOP_DESTINATION_SQUARES:
            raise RecorderError("Choose a destination square in rows 1 through 4.")
        if target_square in TELEOP_PAWN_SOURCE_SQUARES:
            raise RecorderError("Choose an unoccupied destination square.")
        resolve_structured_goal(piece_id, target_square)
        sample_hz = int(request.get("sample_hz") or DEFAULT_SAMPLE_HZ)
        if not 5 <= sample_hz <= 60:
            raise RecorderError("Sample rate must be between 5 and 60 Hz.")
        preflight = self.preflight()
        mode_status = preflight["modes"][mode]
        if not mode_status["ready"]:
            raise RecorderError(str(mode_status["reason"]))
        request = {
            "mode": mode,
            "piece_id": piece_id,
            "source_square": source_square,
            "target_square": target_square,
            "sample_hz": sample_hz,
            "physical_safety_acknowledged": bool(request.get("physical_safety_acknowledged")),
            "physical_pose_match_acknowledged": bool(
                request.get("physical_pose_match_acknowledged")
            ),
            "prestart_countdown_completed": bool(request.get("prestart_countdown_completed")),
            "task_id": contract["task_id"],
        }
        if mode == "physical_follower" and not request["physical_safety_acknowledged"]:
            raise RecorderError("Physical safety acknowledgement is required.")
        if mode == "physical_follower" and not request["physical_pose_match_acknowledged"]:
            raise RecorderError("Paired physical-pose acknowledgement is required.")
        if mode == "physical_follower" and not request["prestart_countdown_completed"]:
            raise RecorderError("Physical pre-start countdown is required.")
        with self.lock:
            if self.state["status"] not in {"idle", "saved", "discarded"}:
                raise RecorderConflict("Stop, label, or discard the current recording first.")
            recording_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
            draft = self.paths.drafts / recording_id
            draft.mkdir(parents=True, exist_ok=False)
            self.stop_event.clear()
            self.ready_event.clear()
            self.state = {
                **self._idle_state(),
                "status": "starting",
                "recording_id": recording_id,
                "mode": mode,
                "piece_id": piece_id,
                "source_square": source_square,
                "target_square": target_square,
                "sample_hz": sample_hz,
                "started_at": _utc_now(),
                "draft_path": str(draft.relative_to(self.paths.repo_root)),
                "training_admission": "pending_replay_and_separate_evaluator",
                "task_id": contract["task_id"],
                "task_contract_sha256": task_contract_sha256(),
            }
            self.thread = threading.Thread(
                target=self._record_loop,
                args=(request, preflight, draft),
                name=f"sim2claw-recorder-{recording_id}",
                daemon=True,
            )
            self.thread.start()
        if not self.ready_event.wait(timeout_seconds):
            self.stop_event.set()
            raise RecorderError("Recorder startup timed out; no recording was admitted.")
        with self.lock:
            if self.state["status"] != "recording":
                raise RecorderError(
                    str(
                        self.state.get("last_error")
                        or self.state.get("error")
                        or "Recorder did not enter the recording state."
                    )
                )
        return self.snapshot()

    def _record_loop(
        self,
        request: dict[str, Any],
        preflight: dict[str, Any],
        draft: Path,
    ) -> None:
        started = time.monotonic()
        samples_path = draft / "samples.jsonl"
        try:
            self.backend = self.backend_factory(request, preflight)
            backend_state = self.backend.open()
            with self.lock:
                self.state.update(
                    status="recording",
                    backend=backend_state,
                    physical_follower_torque_enabled=bool(
                        backend_state.get("physical_follower_torque_enabled")
                    ),
                )
            self.ready_event.set()
            interval = 1.0 / int(request["sample_hz"])
            next_tick = time.monotonic()
            with samples_path.open("w", encoding="utf-8") as handle:
                while not self.stop_event.is_set():
                    tick = time.monotonic()
                    sample = self.backend.sample(tick - started)
                    with self.lock:
                        index = int(self.state["sample_count"])
                    row = {
                        "schema_version": SOURCE_SCHEMA,
                        "recording_id": self.state["recording_id"],
                        "sample_index": index,
                        "timestamp_monotonic_seconds": sample.pop(
                            "elapsed_seconds", tick - started
                        ),
                        **sample,
                    }
                    handle.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")
                    handle.flush()
                    with self.lock:
                        self.state["sample_count"] = index + 1
                        self.state["duration_seconds"] = float(row["timestamp_monotonic_seconds"])
                        self.state["last_sample"] = row
                    next_tick += interval
                    self.stop_event.wait(max(0.0, next_tick - time.monotonic()))
            with self.lock:
                self.state.update(
                    status="awaiting_label",
                    stopped_at=_utc_now(),
                    physical_follower_torque_enabled=False,
                )
            _atomic_json(draft / "draft_state.json", self.state)
        except Exception as error:  # hardware/runtime errors must fail closed
            with self.lock:
                self.state.update(
                    status="error",
                    error=f"{type(error).__name__}: {error}",
                    stopped_at=_utc_now(),
                    physical_follower_torque_enabled=False,
                )
            _atomic_json(draft / "draft_state.json", self.state)
        finally:
            close_error: Exception | None = None
            if self.backend is not None:
                try:
                    self.backend.close()
                except Exception as error:
                    close_error = error
                    with self.lock:
                        existing = str(self.state.get("error") or "").strip()
                        suffix = f"close error: {error}"
                        self.state["status"] = "error"
                        self.state["error"] = f"{existing}; {suffix}" if existing else suffix
                finally:
                    self.backend = None
            with self.lock:
                self.state["physical_follower_torque_enabled"] = False
                failed = self.state.get("status") == "error"
                failed_state = json.loads(json.dumps(self.state)) if failed else None
            if failed_state is not None:
                archived_path = self._archive_failed_draft(failed_state)
                with self.lock:
                    self.state = {
                        **self._idle_state(),
                        "last_error": failed_state.get("error"),
                        "last_failed_recording_id": failed_state.get("recording_id"),
                        "last_failed_attempt_path": archived_path,
                        "gateway_close_confirmed": close_error is None,
                    }
            self.ready_event.set()

    def stop(self, *, timeout_seconds: float = 12.0) -> dict[str, Any]:
        with self.lock:
            if self.state["status"] not in {"starting", "recording"}:
                raise RecorderConflict("There is no active recording to stop.")
            thread = self.thread
            self.stop_event.set()
        if thread is not None:
            thread.join(timeout_seconds)
            if thread.is_alive():
                raise RecorderError("Recorder did not stop within the safety timeout.")
        return self.snapshot()

    def finalize(self, labels: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            if self.state["status"] != "awaiting_label":
                raise RecorderConflict("Stop the recording before labeling it.")
            draft = self.paths.repo_root / str(self.state["draft_path"])
            label = str(labels.get("label") or "").strip()
            skill = str(labels.get("skill") or "").strip()
            outcome = str(labels.get("outcome") or "unreviewed").strip()
            if skill not in {
                "pregrasp",
                "grasp_lift",
                "transport",
                "place_release",
                "retreat",
                "recovery",
                "full_episode",
            }:
                raise RecorderError("Choose a declared ACT skill label.")
            if outcome not in {"success", "failure", "correction", "unreviewed"}:
                raise RecorderError("Choose a valid outcome label.")
            destination = self.paths.recordings / f"{_slug(label)}__{self.state['recording_id']}"
            if destination.exists():
                raise RecorderConflict("A recording with this identity already exists.")
            destination.parent.mkdir(parents=True, exist_ok=True)
            samples = draft / "samples.jsonl"
            if not samples.is_file() or self.state["sample_count"] < 1:
                raise RecorderError("An empty recording cannot be saved.")
            shutil.move(str(draft), str(destination))
            receipt = {
                "schema_version": RECEIPT_SCHEMA,
                "source_episode_schema": SOURCE_SCHEMA,
                "recording_id": self.state["recording_id"],
                "label": label,
                "skill": skill,
                "outcome_label": outcome,
                "notes": str(labels.get("notes") or "").strip(),
                "task_id": self.state["task_id"],
                "task_contract_sha256": self.state["task_contract_sha256"],
                "mode": self.state["mode"],
                "proof_class": self.state.get("backend", {}).get("proof_class"),
                "piece_id": self.state["piece_id"],
                "piece_type": "pawn",
                "piece_color": "brown",
                "source_square": self.state["source_square"],
                "destination_square": self.state["target_square"],
                "initial_layout_id": CURRENT_TASK_LAYOUT_ID,
                "target_square_operator_metadata": self.state["target_square"],
                "sample_hz": self.state["sample_hz"],
                "sample_count": self.state["sample_count"],
                "started_at": self.state["started_at"],
                "stopped_at": self.state["stopped_at"],
                "duration_seconds": self.state["duration_seconds"],
                "samples_path": "samples.jsonl",
                "samples_sha256": _sha256(destination / "samples.jsonl"),
                "backend": self.state.get("backend"),
                "training_admission": "pending_deterministic_replay_and_separate_evaluator",
                "is_training_data": False,
                "held_out_membership": False,
                "generated_artifact_ignored_by_git": True,
                "physical_authority_created": False,
                "physical_motion_recorded": self.state["mode"] == "physical_follower",
                "saved_at": _utc_now(),
            }
            _atomic_json(destination / "recording_receipt.json", receipt)
            self.state.update(
                status="saved",
                saved_path=str(destination.relative_to(self.paths.repo_root)),
                draft_path=None,
                labels={
                    "label": label,
                    "skill": skill,
                    "outcome": outcome,
                },
            )
        return self.snapshot()

    def discard(self) -> dict[str, Any]:
        with self.lock:
            failed = self.state["status"] == "error"
        if failed:
            self._return_failed_attempt_to_ready()
            return self.snapshot()
        with self.lock:
            if self.state["status"] != "awaiting_label":
                raise RecorderConflict("Only a stopped draft can be discarded.")
            draft_path = self.state.get("draft_path")
            if draft_path:
                draft = (self.paths.repo_root / str(draft_path)).resolve()
                if not draft.is_relative_to(self.paths.drafts.resolve()):
                    raise RecorderError("Refusing to discard a path outside recorder drafts.")
                if draft.exists():
                    shutil.rmtree(draft)
            self.state = {**self._idle_state(), "status": "discarded"}
        return self.snapshot()

    def replay_saved_in_simulator(self) -> dict[str, Any]:
        with self.lock:
            if self.state["status"] != "saved":
                raise RecorderConflict("Save a physical recording before simulator replay.")
            if self.state.get("mode") != "physical_follower":
                raise RecorderError("Simulator accuracy replay requires a physical recording.")
            saved_path = self.state.get("saved_path")
        recording = (self.paths.repo_root / str(saved_path)).resolve()
        if not recording.is_relative_to(self.paths.recordings.resolve()):
            raise RecorderError("Refusing to replay a path outside source recordings.")
        report = replay_physical_recording(recording)
        with self.lock:
            self.state["sim_replay"] = report
        return self.snapshot()

    def shutdown(self) -> None:
        with self.lock:
            active = self.state["status"] in {"starting", "recording"}
        if active:
            try:
                self.stop(timeout_seconds=5.0)
            except RecorderError:
                self.stop_event.set()

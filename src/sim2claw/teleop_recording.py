"""Leader-arm recording for the canonical manipulation source-data pipeline.

Raw recordings are model-agnostic and are not ACT or GR00T training rows. They
remain pending exact sample-hold replay and separately owned evaluator
admission; downstream model-specific adapters are the only format boundary.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import mujoco
import numpy as np

from .act_pick_place import (
    resolve_structured_goal,
)
from .native_dual_camera import NativeDualCameraRecorder
from .overhead_video import (
    OverheadVideoError,
    OverheadVideoRecorder,
    WristVideoRecorder,
)
from .paths import REPO_ROOT
from .physical_gateway import (
    BODY_COMMAND_RATE_LIMIT_DEG_S,
    GATEWAY_SCHEMA,
    GatewayIdentity,
    POST_HOLD_BODY_TOLERANCE_DEG,
    POST_HOLD_GRIPPER_TOLERANCE,
    SO101PhysicalGateway,
    inspect_physical_gateway,
    shortest_delta_degrees,
    synchronize_physical_gateway,
)
from .physical_sim_replay import replay_physical_recording
from .render import write_rgb_png
from .scene import (
    CURRENT_TASK_LAYOUT_ID,
    CURRENT_TASK_PIECE_LAYOUT,
    ROBOT_JOINTS,
    build_scene_spec,
    initialize_robot_poses,
    scene_summary,
)
from .source_episode import (
    CONTRACT_PATH_V4,
    EPISODE_SCHEMA,
    RECEIPT_SCHEMA,
    SAMPLE_SCHEMA,
    build_source_sample,
    language_instruction,
    load_source_contract,
    source_contract_sha256,
    tree_manifest,
    validate_source_sample,
)
from .state_trace import EpisodeStateTraceRecorder


SOURCE_SCHEMA = SAMPLE_SCHEMA
PHYSICAL_SAMPLE_SCHEMA = "sim2claw.physical_teleoperation_sample.v1"
DEFAULT_LEADER_SERIAL_SUFFIX = "0448141"
DEFAULT_FOLLOWER_SERIAL_SUFFIX = "0406411"
EXCITATION_CONTROL_SOURCE = "frozen_precompiled_follower_actions"
EXCITATION_SOURCE_PROOF_CLASS = (
    "physical_precompiled_follower_excitation_source_unqualified"
)
_EXCITATION_COMMAND_SOURCE_PORT = "in-process://frozen-precompiled-actions"
_EXCITATION_COMMAND_SOURCE_SHA256 = hashlib.sha256(
    EXCITATION_CONTROL_SOURCE.encode()
).hexdigest()
DEFAULT_SAMPLE_HZ = 20
LIVE_SIMULATION_SCHEMA = "sim2claw.live_simulation_recorder.v1"
LABEL_PATTERN = re.compile(r"[^a-z0-9]+")
RECORDER_SOURCE_CONTRACT_PATH = CONTRACT_PATH_V4
LOWER_TWO_ROW_SQUARES = tuple(
    f"{file_name}{rank}"
    for file_name in "abcdefgh"
    for rank in ("1", "2")
)


class RecorderError(RuntimeError):
    """Expected operator-facing recording error."""


class RecorderConflict(RecorderError):
    """The requested transition conflicts with the current recorder state."""


class RecorderBackend(Protocol):
    def open(self) -> dict[str, Any]: ...

    def sample(self, elapsed_seconds: float) -> dict[str, Any]: ...

    def close(self) -> None: ...


class DiagnosticVideoRecorder(Protocol):
    started_monotonic: float | None

    def start(self) -> dict[str, Any]: ...

    def ensure_running(self) -> None: ...

    def finish(
        self,
        *,
        action_started_monotonic: float | None,
        action_stopped_monotonic: float | None,
        post_roll_seconds: float,
    ) -> dict[str, Any]: ...


class DualDiagnosticVideoRecorder(Protocol):
    started_monotonic: float | None

    def start(self) -> dict[str, Any]: ...

    def ensure_running(self) -> None: ...

    def finish(
        self,
        *,
        action_started_monotonic: float | None,
        action_stopped_monotonic: float | None,
        post_roll_seconds: float,
    ) -> dict[str, Any]: ...


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


def _canonical_source_row(
    *,
    episode_id: str,
    sample_index: int,
    timestamp_monotonic_seconds: float,
    instruction: str,
    raw_sample: dict[str, Any],
    rgb: dict[str, Any],
    action_owner: str,
    assistance: bool,
    intervention: bool,
) -> dict[str, Any]:
    return build_source_sample(
        episode_id=episode_id,
        sample_index=sample_index,
        timestamp_monotonic_seconds=timestamp_monotonic_seconds,
        instruction=instruction,
        raw_sample=raw_sample,
        rgb=rgb,
        action_owner=action_owner,
        assistance=assistance,
        intervention=intervention,
    )


def _physical_source_row(
    *,
    episode_id: str,
    sample_index: int,
    timestamp_monotonic_seconds: float,
    instruction: str,
    raw_sample: dict[str, Any],
    action_owner: str,
    assistance: bool,
    intervention: bool,
    visual_streams: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a physical command trace without claiming simulator observations."""

    streams = visual_streams or {
        "overhead_workspace": "overhead_c922.mp4",
        "wrist_gripper_upward": "wrist_d405.mkv",
    }
    row = {
        **raw_sample,
        "schema_version": PHYSICAL_SAMPLE_SCHEMA,
        "episode_id": episode_id,
        "recording_id": episode_id,
        "sample_index": sample_index,
        "timestamp_monotonic_seconds": timestamp_monotonic_seconds,
        "language_instruction": instruction,
        "action_owner": action_owner,
        "assistance": int(assistance),
        "intervention": int(intervention),
        "visual_observation": (
            {
                "kind": "dual_diagnostic_video",
                "streams": streams,
                "training_data": False,
                "metric_depth": False,
            }
            if raw_sample.get("wrist_video_time_seconds") is not None
            else {
                "kind": "overhead_diagnostic_video_only",
                "path": streams["overhead_workspace"],
                "training_data": False,
            }
        ),
    }
    if len(row.get("follower_command_degrees") or []) != 6:
        raise ValueError(
            "physical teleoperation sample requires six follower command joints"
        )
    if len(row.get("follower_actual_position_degrees") or []) != 6:
        raise ValueError(
            "physical teleoperation sample requires six follower position joints"
        )
    for field in ("follower_command_degrees", "follower_actual_position_degrees"):
        values = np.asarray(row[field], dtype=np.float64)
        if not np.all(np.isfinite(values)):
            raise ValueError(f"physical teleoperation sample has invalid {field}")
    if not np.isfinite(float(timestamp_monotonic_seconds)) or timestamp_monotonic_seconds < 0:
        raise ValueError("physical teleoperation sample timestamp is invalid")
    return row


def _validate_physical_source_row(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("schema_version") != PHYSICAL_SAMPLE_SCHEMA:
        raise ValueError("unsupported physical teleoperation sample schema")
    if int(row.get("sample_index", -1)) < 0:
        raise ValueError("physical teleoperation sample index must be non-negative")
    if not str(row.get("language_instruction") or "").strip():
        raise ValueError("physical teleoperation sample language instruction is required")
    visual_observation = row.get("visual_observation")
    if (
        not isinstance(visual_observation, dict)
        or visual_observation.get("kind")
        not in {"overhead_diagnostic_video_only", "dual_diagnostic_video"}
    ):
        raise ValueError("physical teleoperation sample visual evidence is invalid")
    return _physical_source_row(
        episode_id=str(row.get("episode_id") or ""),
        sample_index=int(row["sample_index"]),
        timestamp_monotonic_seconds=float(row["timestamp_monotonic_seconds"]),
        instruction=str(row["language_instruction"]),
        raw_sample=row,
        action_owner=str(row.get("action_owner") or ""),
        assistance=bool(row.get("assistance", False)),
        intervention=bool(row.get("intervention", False)),
    )


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
            "source_contract_sha256": source_contract_sha256(
                RECORDER_SOURCE_CONTRACT_PATH
            ),
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


class _ExcitationCommandBus:
    """In-process command source; it never opens a physical leader bus."""

    def __init__(self) -> None:
        self.is_connected = False

    def connect(self) -> None:
        self.is_connected = True

    def disable_torque(self, *, num_retry: int = 0) -> None:
        del num_retry

    def disconnect(self, _disable_torque: bool = True) -> None:
        self.is_connected = False


class _ExcitationCommandSource:
    def __init__(self, follower: Any):
        self.bus = _ExcitationCommandBus()
        self.follower = follower
        self.is_calibrated = True

    def get_action(self) -> dict[str, float]:
        return self.follower.get_observation()


def _physical_excitation_devices(identity: GatewayIdentity) -> tuple[Any, Any]:
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
    return _ExcitationCommandSource(follower), follower


def _physical_excitation_identity(preflight: dict[str, Any]) -> GatewayIdentity:
    follower_port = preflight["devices"]["follower"]["port"]
    follower_sha = preflight["calibrations"]["follower"]["sha256"]
    if not all((follower_port, follower_sha)):
        raise RecorderError("Physical excitation follower identity is incomplete.")
    return GatewayIdentity(
        leader_port=_EXCITATION_COMMAND_SOURCE_PORT,
        follower_port=str(follower_port),
        leader_calibration_sha256=_EXCITATION_COMMAND_SOURCE_SHA256,
        follower_calibration_sha256=str(follower_sha),
    )


def _physical_excitation_gateway(
    identity: GatewayIdentity,
) -> SO101PhysicalGateway:
    return SO101PhysicalGateway(
        identity,
        device_factory=_physical_excitation_devices,
        configure_devices=False,
        require_initial_follower_torque_off=True,
    )


def physical_excitation_follower_preflight(
    *,
    dev_root: Path = Path("/dev"),
    calibration_root: Path | None = None,
    gateway_factory: Callable[[GatewayIdentity], SO101PhysicalGateway] = (
        _physical_excitation_gateway
    ),
) -> dict[str, Any]:
    """Inspect only the expected follower and leave it torque-off."""

    inventory = recorder_preflight(
        dev_root=dev_root,
        calibration_root=calibration_root,
    )
    follower = inventory["devices"]["follower"]
    calibration = inventory["calibrations"]["follower"]
    if not (
        follower.get("connected")
        and calibration.get("present")
        and inventory["runtime"].get("lerobot_version")
    ):
        raise RecorderError(
            "The expected follower bus, calibration, and LeRobot runtime are required."
        )
    identity = _physical_excitation_identity(inventory)
    gateway = gateway_factory(identity)
    try:
        opened = gateway.open(enable_motion=False)
        return {
            "schema_version": opened["schema_version"],
            "passed": True,
            "control_source": EXCITATION_CONTROL_SOURCE,
            "real_leader_opened": False,
            "follower_port": identity.follower_port,
            "follower_calibration_sha256": identity.follower_calibration_sha256,
            "follower_start_degrees": opened["follower_start_degrees"],
            "follower_calibrated_minimum": opened[
                "follower_calibrated_minimum"
            ],
            "follower_calibrated_maximum": opened[
                "follower_calibrated_maximum"
            ],
            "physical_follower_torque_enabled": opened[
                "physical_follower_torque_enabled"
            ],
            "device_configuration_rewritten": opened[
                "device_configuration_rewritten"
            ],
        }
    finally:
        gateway.close()


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
        self.end_effector_body_id = -1
        self.target_pose = resolve_structured_goal(
            str(request["piece_id"]), str(request["target_square"])
        )["target_pose"]
        self.sample_hz = int(request.get("sample_hz") or DEFAULT_SAMPLE_HZ)
        self.trace: EpisodeStateTraceRecorder | None = None
        self.rgb_renderers: dict[str, mujoco.Renderer] = {}

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
        # Execute the exact float32 row that the canonical source artifact
        # records. This keeps source collection and deployed sample-hold replay
        # mechanically identical instead of repeating the old ramp/label gap.
        return np.clip(command, bounds[:, 0], bounds[:, 1]).astype(np.float32).astype(
            np.float64
        )

    def _integration_state_payload(self) -> dict[str, Any]:
        if self.model is None or self.data is None:
            raise RecorderError("Simulator is not open.")
        state_size = mujoco.mj_stateSize(
            self.model, mujoco.mjtState.mjSTATE_INTEGRATION
        )
        integration_state = np.empty(state_size, dtype=np.float64)
        mujoco.mj_getState(
            self.model,
            self.data,
            integration_state,
            mujoco.mjtState.mjSTATE_INTEGRATION,
        )
        return {
            "available": True,
            "mj_state_spec": "mjSTATE_INTEGRATION",
            "integration_state_float64": integration_state.astype(float).tolist(),
            "simulation_time_seconds": float(self.data.time),
        }

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
        self.end_effector_body_id = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_BODY, "left_gripper"
        )
        if self.end_effector_body_id < 0:
            raise RecorderError("Simulator is missing the left gripper body.")
        leader_values = _leader_action_vector(self.leader.read())
        command = self._command_from_leader(leader_values)
        self.data.qpos[self.joint_qpos_addresses] = command
        self.data.ctrl[self.actuator_ids] = command
        mujoco.mj_forward(self.model, self.data)
        self.trace = EpisodeStateTraceRecorder(
            self.model,
            piece_layout=CURRENT_TASK_PIECE_LAYOUT,
            fps=self.sample_hz,
            proof_class="simulation_teleoperation_source_state_trace",
        )
        self.trace.capture(self.data, phase="teleoperation", force=True)
        self.rgb_renderers = {
            "top": mujoco.Renderer(self.model, height=256, width=256),
            "wrist": mujoco.Renderer(self.model, height=256, width=256),
        }
        return {
            "proof_class": self.proof_class,
            "leader_port": self.leader.port,
            "follower": "mujoco:left_so101",
            "physical_follower_torque_enabled": False,
            "physical_gateway_preflight": None,
            "sim_replay": None,
            "pose_inputs_available": True,
            "_initial_evaluator_privileged_state": self._integration_state_payload(),
            "_live_simulation": self.trace.live_snapshot(),
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
        if self.trace is not None:
            self.trace.capture(self.data, phase="teleoperation")
        piece_position = self.data.xpos[self.piece_body_id].astype(float).tolist()
        piece_quaternion = self.data.xquat[self.piece_body_id].astype(float).tolist()
        end_effector_position = self.data.xpos[self.end_effector_body_id].astype(float).tolist()
        end_effector_quaternion = self.data.xquat[self.end_effector_body_id].astype(float).tolist()
        rgb_frames: dict[str, np.ndarray] = {}
        for stream, camera in (("top", "overhead"), ("wrist", "left_wrist_cam")):
            renderer = self.rgb_renderers.get(stream)
            if renderer is None:
                raise RecorderError(f"Simulator RGB renderer is missing: {stream}")
            renderer.update_scene(self.data, camera=camera)
            rgb_frames[stream] = renderer.render().copy()

        contacts: list[dict[str, Any]] = []
        for contact_index in range(self.data.ncon):
            contact = self.data.contact[contact_index]
            body_ids = (
                int(self.model.geom_bodyid[contact.geom1]),
                int(self.model.geom_bodyid[contact.geom2]),
            )
            body_names = [
                mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_BODY, body_id)
                or ("world" if body_id == 0 else f"body-{body_id}")
                for body_id in body_ids
            ]
            contacts.append(
                {
                    "body_a": body_names[0],
                    "body_b": body_names[1],
                    "position_world": contact.pos.astype(float).tolist(),
                }
            )
            if len(contacts) >= 64:
                break

        integration_state = self._integration_state_payload()
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
            "end_effector_pose_world": [
                *end_effector_position,
                *end_effector_quaternion,
            ],
            "gripper_joint_position_rad": float(
                self.data.qpos[self.joint_qpos_addresses[-1]]
            ),
            "contacts": contacts,
            "simulator_events": [],
            "pose_inputs_available": True,
            "available_motor_current": None,
            "physical_follower_torque_enabled": False,
            "_rgb_frames": rgb_frames,
            "_evaluator_privileged_state": {
                **integration_state,
                "selected_piece_body_id": self.piece_body_id,
                "selected_piece_pose_world": [*piece_position, *piece_quaternion],
            },
            "_live_simulation_frame": (
                {
                    "frame_index": len(self.trace.frames) - 1,
                    "frame": self.trace.frames[-1],
                }
                if self.trace is not None and self.trace.frames
                else None
            ),
        }

    def write_state_trace(self, path: Path) -> dict[str, Any]:
        if self.trace is None or self.data is None:
            raise RecorderError("Simulator trace is not available.")
        self.trace.capture(self.data, phase="teleoperation", force=True)
        return self.trace.write(path)

    def close(self) -> None:
        try:
            for renderer in self.rgb_renderers.values():
                renderer.close()
        finally:
            self.rgb_renderers = {}
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
        if not self.request.get("server_owned_prestart_sequence"):
            raise RecorderError("Server-owned physical pre-start sequence is required.")
        gateway = self.gateway.synchronize_and_arm(countdown_seconds=3.0)
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


class ZeroDisplacementHoldBackend:
    proof_class = "physical_teleoperation_source_unqualified"

    def __init__(self, request: dict[str, Any], preflight: dict[str, Any]):
        self.request = request
        self.gateway = SO101PhysicalGateway(_gateway_identity(preflight))

    def open(self) -> dict[str, Any]:
        report = self.gateway.open(
            enable_motion=True,
            paired_pose_confirmed=True,
        )
        return {
            **report,
            "proof_class": self.proof_class,
            "pose_inputs_available": False,
            "physical_follower_torque_enabled": True,
        }

    def sample(self, elapsed_seconds: float) -> dict[str, Any]:
        return self.gateway.sample(
            elapsed_seconds,
            zero_displacement_hold=True,
        )

    def close(self) -> None:
        self.gateway.close()


HOLD_PACKET_KIND = "sim2claw.zero_displacement_hold_packet.v1"
EXCITATION_PACKET_KIND = "sim2claw.precompiled_physical_excitation_packet.v2"
EXCITATION_EPISODE_COUNT = 5
EXCITATION_SAMPLE_HZ = 20
EXCITATION_AMPLITUDE_DEGREES = 3.0
EXCITATION_SLEW_DEGREES_S = 10.0
REPOSITION_SAMPLE_HZ = 20
REPOSITION_SLEW_DEGREES_S = 5.0
REPOSITION_SHOULDER_DELTA_DEGREES = 1.5
REPOSITION_ELBOW_DELTA_DEGREES = -1.5
REPOSITION_MARGIN_DEGREES = 3.0
REPOSITION_SCHEMA = "sim2claw.physical_follower_reposition.v1"
REPOSITION_PLAN_KIND = "sim2claw.follower_reposition_plan.v1"
REPOSITION_REVIEW_FIELDS = (
    "reviewer",
    "reviewed_at",
    "decision_id",
    "bounded_reposition_reviewed",
    "collision_contact_free_workspace_confirmed",
)


def run_zero_displacement_hold_packet(
    packet_path: Path,
    *,
    repo_root: Path = REPO_ROOT,
    operator_acknowledged: bool = False,
    preflight_fn: Callable[[], dict[str, Any]] = physical_gateway_preflight,
    manager_factory: Callable[..., Any] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Run one independently admitted hold through the production recorder."""

    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    constraints = packet.get("constraints") or {}
    recording = packet.get("recording") or {}
    if (
        packet.get("kind") != HOLD_PACKET_KIND
        or packet.get("packet_id") != "P6-ZERO-DISPLACEMENT-HOLD-01"
        or packet.get("duration_seconds") != 1.0
        or recording != {"label": "p6-zero-displacement-hold-01", "square": "a1"}
        or not packet.get("single_use")
    ):
        raise RecorderError("Unsupported or reusable zero-displacement packet.")
    if (
        packet.get("physical_packet_execution_admitted") is not True
        or not all(
            (packet.get("independent_review") or {}).get(field)
            for field in ("reviewer", "reviewed_at", "decision_id")
        )
    ):
        raise RecorderError(
            "This packet is not independently reviewed and admitted; no devices were opened."
        )
    if not operator_acknowledged:
        raise RecorderError("Fresh operator acknowledgement is required.")
    required_constraints = {
        "runtime_target": "fresh_torque_off_follower_read_immediately_before_arming",
        "requested_equals_gateway_sent": True,
        "zero_displacement_only": True,
        "allow_gripper_closure": False,
        "allow_ik_offsets_clipping_suffix_or_assistance": False,
        "allow_device_configuration_rewrite": False,
        "paired_pose_body_limit_degrees": 12.0,
    }
    if any(constraints.get(key) != value for key, value in required_constraints.items()):
        raise RecorderError("Zero-displacement packet constraints changed.")

    _motion_authority(repo_root)

    label = str(packet["recording"]["label"])
    for receipt_path in (
        repo_root / "datasets/manipulation_source_recordings"
    ).glob("*/recording_receipt.json"):
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("label") == label:
            raise RecorderError("Single-use hold packet already has a finalized recording.")

    hardware = packet["hardware_identity"]
    if hardware.get("gateway_schema") != GATEWAY_SCHEMA:
        raise RecorderError("Hold packet gateway contract changed.")
    preflight = preflight_fn()
    for key in (
        "leader_port",
        "follower_port",
        "leader_calibration_sha256",
        "follower_calibration_sha256",
    ):
        if preflight.get(key) != hardware.get(key):
            raise RecorderError(f"Hold packet hardware identity mismatch: {key}.")
    if not (
        preflight.get("passed") is True
        and preflight.get("paired_pose_registration_ready") is True
        and preflight.get("physical_follower_torque_enabled") is False
        and preflight.get("device_configuration_rewritten") is False
    ):
        raise RecorderError("Fresh torque-off paired-pose preflight did not pass.")

    manager = (manager_factory or TeleopRecordingManager)(
        repo_root=repo_root,
        backend_factory=lambda request, status: ZeroDisplacementHoldBackend(
            request, status
        ),
    )
    manager.start(
        {
            "mode": "physical_follower",
            "source_square": recording["square"],
            "target_square": recording["square"],
            "sample_hz": 20,
            "physical_safety_acknowledged": True,
            "server_owned_prestart_sequence": True,
            "action_owner": "independently_reviewed_zero_displacement_hold_packet",
        }
    )
    try:
        sleep_fn(float(packet["duration_seconds"]))
    finally:
        manager.stop()
    saved = manager.finalize(
        {
            "label": label,
            "skill": "recovery",
            "outcome": "unreviewed",
            "notes": f"single-use {packet['packet_id']}; exact hold enforced per sample",
        }
    )
    return {
        "packet_id": packet["packet_id"],
        "saved_path": saved["saved_path"],
        "requested_equals_gateway_sent": True,
        "physical_authority_created": False,
        "proof_class": "physical_teleoperation_source_unqualified",
    }


def _float64_sha256(values: Any) -> str:
    array = np.asarray(values, dtype="<f8", order="C")
    return hashlib.sha256(array.tobytes(order="C")).hexdigest()


def _canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def _motion_authority(repo_root: Path) -> None:
    state = json.loads(
        (repo_root / "docs/autonomous-workflow/project_state.json").read_text(
            encoding="utf-8"
        )
    )
    authority = state["twin_fidelity_closure_transaction"]["authority"]
    if not (
        authority.get("owner_authorized_bounded_robot_motion") is True
        and authority.get("owner_workspace_clear_assertion") is True
    ):
        raise RecorderError("Current owner motion/workspace authority is closed.")


def _triangle_profile(direction: float) -> np.ndarray:
    outward = np.arange(0.0, 3.0 + 0.5, 0.5)
    across = np.arange(2.5, -3.0 - 0.5, -0.5)
    home = np.arange(-2.5, 0.0 + 0.5, 0.5)
    return direction * np.concatenate((outward, across, home)).astype(np.float64)


def _validate_excitation_plan(packet: dict[str, Any]) -> dict[str, Any]:
    if (
        packet.get("kind") != EXCITATION_PACKET_KIND
        or packet.get("single_use") is not True
        or not isinstance(packet.get("plan"), dict)
    ):
        raise RecorderError("Unsupported physical excitation packet.")
    plan = packet["plan"]
    if packet.get("plan_sha256") != _canonical_sha256(plan):
        raise RecorderError("Physical excitation plan digest changed.")
    if packet.get("packet_id") != f"P10-{packet['plan_sha256'][:16]}":
        raise RecorderError("Physical excitation packet identity changed.")
    required_plan = {
        "control_source": EXCITATION_CONTROL_SOURCE,
        "sample_hz": EXCITATION_SAMPLE_HZ,
        "anchor_source": "fresh_torque_off_follower_read",
        "amplitude_degrees": EXCITATION_AMPLITUDE_DEGREES,
        "compiled_slew_degrees_s": EXCITATION_SLEW_DEGREES_S,
        "gateway_body_slew_limit_degrees_s": BODY_COMMAND_RATE_LIMIT_DEG_S,
        "gripper_fixed": True,
        "no_ik_offset_clip_resample_suffix_or_assistance": True,
    }
    if any(plan.get(key) != value for key, value in required_plan.items()):
        raise RecorderError("Physical excitation family or safety contract changed.")
    expected_tolerance = [
        POST_HOLD_BODY_TOLERANCE_DEG,
        POST_HOLD_BODY_TOLERANCE_DEG,
        POST_HOLD_BODY_TOLERANCE_DEG,
        POST_HOLD_BODY_TOLERANCE_DEG,
        POST_HOLD_BODY_TOLERANCE_DEG,
        POST_HOLD_GRIPPER_TOLERANCE,
    ]
    if plan.get("anchor_tolerance_degrees") != expected_tolerance:
        raise RecorderError("Physical excitation anchor tolerance changed.")
    hardware = plan.get("hardware_identity")
    if (
        not isinstance(hardware, dict)
        or set(hardware)
        != {
            "gateway_schema",
            "follower_port",
            "follower_calibration_sha256",
            "real_leader_identity_bound",
        }
        or hardware.get("gateway_schema") != GATEWAY_SCHEMA
        or not str(hardware.get("follower_port") or "")
        or not re.fullmatch(
            r"[0-9a-f]{64}",
            str(hardware.get("follower_calibration_sha256") or ""),
        )
        or hardware.get("real_leader_identity_bound") is not False
    ):
        raise RecorderError("Physical excitation gateway identity changed.")
    episodes = plan.get("episodes")
    if not isinstance(episodes, list) or len(episodes) != EXCITATION_EPISODE_COUNT:
        raise RecorderError("Physical excitation requires exactly five episodes.")
    anchor = np.asarray(plan.get("anchor_degrees"), dtype=np.float64)
    lower = np.asarray(plan.get("calibrated_minimum_degrees"), dtype=np.float64)
    upper = np.asarray(plan.get("calibrated_maximum_degrees"), dtype=np.float64)
    if any(values.shape != (6,) for values in (anchor, lower, upper)):
        raise RecorderError("Excitation anchor and calibrated limits require six joints.")
    if not all(np.all(np.isfinite(values)) for values in (anchor, lower, upper)):
        raise RecorderError("Excitation anchor or calibrated limits are invalid.")
    seen: set[str] = set()
    covered: set[int] = set()
    action_tensors: list[np.ndarray] = []
    assignments = ((0, 1.0), (1, 1.0), (2, 1.0), (0, -1.0), (1, -1.0))
    expected_timestamps = (
        np.arange(25, dtype=np.float64) / EXCITATION_SAMPLE_HZ
    )
    for episode_index, (episode, assignment) in enumerate(
        zip(episodes, assignments, strict=True), start=1
    ):
        episode_id = str(episode.get("episode_id") or "")
        if episode_id != f"excitation-{episode_index:02d}" or episode_id in seen:
            raise RecorderError("Excitation episode identities must be unique.")
        seen.add(episode_id)
        timestamps = np.asarray(episode.get("timestamps_seconds"), dtype=np.float64)
        actions = np.asarray(episode.get("actions_degrees"), dtype=np.float64)
        if (
            timestamps.ndim != 1
            or timestamps.size < 4
            or actions.shape != (timestamps.size, 6)
            or not np.all(np.isfinite(timestamps))
            or not np.all(np.isfinite(actions))
            or not np.all(np.diff(timestamps) > 0.0)
            or timestamps[0] != 0.0
            or timestamps[-1] < 1.0
        ):
            raise RecorderError("Excitation episode timing/action shape changed.")
        joint_index, direction = assignment
        expected_actions = np.repeat(anchor[None, :], timestamps.size, axis=0)
        expected_actions[:, joint_index] += _triangle_profile(direction)
        if (
            not np.array_equal(timestamps, expected_timestamps)
            or not np.array_equal(actions, expected_actions)
            or episode.get("body_joint") != ROBOT_JOINTS[joint_index]
            or episode.get("direction")
            != ("positive_first" if direction > 0 else "negative_first")
        ):
            raise RecorderError("Physical excitation trajectory family changed.")
        if episode.get("gateway_action_degrees_sha256") != _float64_sha256(actions):
            raise RecorderError(
                f"Excitation gateway-degree action hash changed: {episode_id}."
            )
        if episode.get("canonical_action_radians_sha256") != _float64_sha256(
            np.deg2rad(actions)
        ):
            raise RecorderError(
                f"Excitation canonical-radian action hash changed: {episode_id}."
            )
        if episode.get("timestamp_sha256") != _float64_sha256(timestamps):
            raise RecorderError(f"Excitation timestamp hash changed: {episode_id}.")
        if not np.array_equal(actions[0], anchor) or not np.array_equal(
            actions[-1], anchor
        ):
            raise RecorderError("Every excitation must begin and end at its anchor.")
        if not np.array_equal(actions[:, 5], np.full(timestamps.size, anchor[5])):
            raise RecorderError("Excitation packet changed the gripper target.")
        if np.any(actions < lower) or np.any(actions > upper):
            raise RecorderError("Excitation packet exceeds calibrated joint limits.")
        slew = np.abs(np.diff(actions, axis=0) / np.diff(timestamps)[:, None])
        if float(np.max(slew)) > EXCITATION_SLEW_DEGREES_S + 1e-12:
            raise RecorderError("Excitation packet exceeds its conservative slew.")
        ranges = np.ptp(actions[:, :5], axis=0)
        active = np.flatnonzero(ranges >= 5.0)
        if active.size != 1 or np.count_nonzero(ranges) != 1:
            raise RecorderError("Each excitation must vary exactly one body joint.")
        covered.add(int(active[0]))
        action_tensors.append(actions)
    if len(covered) < 3:
        raise RecorderError("Excitation cohort covers fewer than three body joints.")
    aggregate_actions = np.concatenate(action_tensors, axis=0)
    if plan.get("aggregate_gateway_action_degrees_sha256") != _float64_sha256(
        aggregate_actions
    ):
        raise RecorderError("Aggregate excitation action digest changed.")
    return {
        "plan": plan,
        "anchor": anchor,
        "lower": lower,
        "upper": upper,
        "covered_body_joint_indices": sorted(covered),
    }


def compile_physical_excitation_packet(
    packet_path: Path,
    *,
    preflight_fn: Callable[[], dict[str, Any]] = (
        physical_excitation_follower_preflight
    ),
) -> dict[str, Any]:
    """Read one torque-off pose and freeze five conservative exact trajectories."""

    preflight = preflight_fn()
    if not (
        preflight.get("passed") is True
        and preflight.get("control_source") == EXCITATION_CONTROL_SOURCE
        and preflight.get("real_leader_opened") is False
        and preflight.get("physical_follower_torque_enabled") is False
        and preflight.get("device_configuration_rewritten") is False
    ):
        raise RecorderError("Fresh torque-off paired-pose preflight did not pass.")
    anchor = np.asarray(preflight.get("follower_start_degrees"), dtype=np.float64)
    lower = np.asarray(
        preflight.get("follower_calibrated_minimum"), dtype=np.float64
    )
    upper = np.asarray(
        preflight.get("follower_calibrated_maximum"), dtype=np.float64
    )
    if any(values.shape != (6,) for values in (anchor, lower, upper)):
        raise RecorderError("Fresh follower pose or calibrated limits are incomplete.")
    for joint_index in (0, 1, 2):
        if (
            anchor[joint_index] - EXCITATION_AMPLITUDE_DEGREES
            < lower[joint_index]
            or anchor[joint_index] + EXCITATION_AMPLITUDE_DEGREES
            > upper[joint_index]
        ):
            raise RecorderError(
                f"Fresh pose lacks ±3 degree calibrated margin on "
                f"{ROBOT_JOINTS[joint_index]}."
            )
    timestamps = np.arange(25, dtype=np.float64) / EXCITATION_SAMPLE_HZ
    assignments = ((0, 1.0), (1, 1.0), (2, 1.0), (0, -1.0), (1, -1.0))
    episodes: list[dict[str, Any]] = []
    for index, (joint_index, direction) in enumerate(assignments, start=1):
        actions = np.repeat(anchor[None, :], timestamps.size, axis=0)
        actions[:, joint_index] += _triangle_profile(direction)
        episodes.append(
            {
                "episode_id": f"excitation-{index:02d}",
                "body_joint": ROBOT_JOINTS[joint_index],
                "direction": "positive_first" if direction > 0 else "negative_first",
                "timestamps_seconds": timestamps.tolist(),
                "actions_degrees": actions.tolist(),
                "timestamp_sha256": _float64_sha256(timestamps),
                "gateway_action_degrees_sha256": _float64_sha256(actions),
                "canonical_action_radians_sha256": _float64_sha256(
                    np.deg2rad(actions)
                ),
            }
        )
    plan = {
        "control_source": EXCITATION_CONTROL_SOURCE,
        "sample_hz": EXCITATION_SAMPLE_HZ,
        "anchor_source": "fresh_torque_off_follower_read",
        "anchor_degrees": anchor.tolist(),
        "anchor_tolerance_degrees": [
            POST_HOLD_BODY_TOLERANCE_DEG,
            POST_HOLD_BODY_TOLERANCE_DEG,
            POST_HOLD_BODY_TOLERANCE_DEG,
            POST_HOLD_BODY_TOLERANCE_DEG,
            POST_HOLD_BODY_TOLERANCE_DEG,
            POST_HOLD_GRIPPER_TOLERANCE,
        ],
        "calibrated_minimum_degrees": lower.tolist(),
        "calibrated_maximum_degrees": upper.tolist(),
        "amplitude_degrees": EXCITATION_AMPLITUDE_DEGREES,
        "compiled_slew_degrees_s": EXCITATION_SLEW_DEGREES_S,
        "gateway_body_slew_limit_degrees_s": BODY_COMMAND_RATE_LIMIT_DEG_S,
        "gripper_fixed": True,
        "no_ik_offset_clip_resample_suffix_or_assistance": True,
        "hardware_identity": {
            "gateway_schema": preflight["schema_version"],
            "follower_port": preflight["follower_port"],
            "follower_calibration_sha256": preflight[
                "follower_calibration_sha256"
            ],
            "real_leader_identity_bound": False,
        },
        "aggregate_gateway_action_degrees_sha256": _float64_sha256(
            np.concatenate(
                [
                    np.asarray(episode["actions_degrees"], dtype=np.float64)
                    for episode in episodes
                ],
                axis=0,
            )
        ),
        "episodes": episodes,
    }
    plan_sha256 = _canonical_sha256(plan)
    packet = {
        "kind": EXCITATION_PACKET_KIND,
        "packet_id": f"P10-{plan_sha256[:16]}",
        "single_use": True,
        "physical_packet_execution_admitted": False,
        "independent_review": {
            "reviewer": None,
            "reviewed_at": None,
            "decision_id": None,
            "bounded_excitation_reviewed": False,
            "collision_contact_free_workspace_confirmed": False,
        },
        "plan_sha256": plan_sha256,
        "plan": plan,
    }
    _validate_excitation_plan(packet)
    _atomic_json(packet_path, packet)
    return packet


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise RecorderError(f"Refusing to overwrite existing output: {path}.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _build_reposition_plan(preflight: dict[str, Any]) -> dict[str, Any]:
    if not (
        preflight.get("passed") is True
        and preflight.get("control_source") == EXCITATION_CONTROL_SOURCE
        and preflight.get("real_leader_opened") is False
        and preflight.get("physical_follower_torque_enabled") is False
        and preflight.get("device_configuration_rewritten") is False
    ):
        raise RecorderError("Follower-only reposition preflight did not pass.")
    anchor = np.asarray(preflight["follower_start_degrees"], dtype=np.float64)
    lower = np.asarray(
        preflight["follower_calibrated_minimum"], dtype=np.float64
    )
    upper = np.asarray(
        preflight["follower_calibrated_maximum"], dtype=np.float64
    )
    if anchor.shape != (6,) or not np.all(np.isfinite(anchor)):
        raise RecorderError("Follower reposition start requires six finite joints.")
    if any(
        values.shape != (6,) or not np.all(np.isfinite(values))
        for values in (lower, upper)
    ):
        raise RecorderError("Follower reposition limits require six finite joints.")
    target = anchor.copy()
    target[1] += REPOSITION_SHOULDER_DELTA_DEGREES
    target[2] += REPOSITION_ELBOW_DELTA_DEGREES
    delta = target - anchor
    if np.any(target < lower) or np.any(target > upper):
        raise RecorderError("Follower reposition target exceeds calibrated limits.")
    for index in (1, 2):
        if (
            target[index] - REPOSITION_MARGIN_DEGREES < lower[index]
            or target[index] + REPOSITION_MARGIN_DEGREES > upper[index]
        ):
            raise RecorderError(
                "Follower reposition target lacks the required ±3 degree margin."
            )
    steps = max(
        1,
        int(
            np.ceil(
                float(np.max(np.abs(delta[[1, 2]])))
                / REPOSITION_SLEW_DEGREES_S
                * REPOSITION_SAMPLE_HZ
            )
        ),
    )
    fractions = np.arange(steps + 1, dtype=np.float64) / float(steps)
    actions = anchor[None, :] + fractions[:, None] * delta[None, :]
    timestamps = np.arange(steps + 1, dtype=np.float64) / REPOSITION_SAMPLE_HZ
    plan = {
        "schema_version": REPOSITION_SCHEMA,
        "control_source": EXCITATION_CONTROL_SOURCE,
        "gateway_schema": GATEWAY_SCHEMA,
        "follower_port": preflight["follower_port"],
        "follower_calibration_sha256": preflight["follower_calibration_sha256"],
        "real_leader_identity_bound": False,
        "anchor_degrees": anchor.tolist(),
        "target_degrees": target.tolist(),
        "relative_target_delta_degrees": delta.tolist(),
        "changed_joints": ["shoulder_lift", "elbow_flex"],
        "unchanged_joint_indices": [0, 3, 4, 5],
        "sample_hz": REPOSITION_SAMPLE_HZ,
        "slew_degrees_s": REPOSITION_SLEW_DEGREES_S,
        "maximum_delta_degrees": float(np.max(np.abs(delta[[1, 2]]))),
        "anchor_tolerance_degrees": [
            POST_HOLD_BODY_TOLERANCE_DEG,
            POST_HOLD_BODY_TOLERANCE_DEG,
            POST_HOLD_BODY_TOLERANCE_DEG,
            POST_HOLD_BODY_TOLERANCE_DEG,
            POST_HOLD_BODY_TOLERANCE_DEG,
            POST_HOLD_GRIPPER_TOLERANCE,
        ],
        "calibrated_minimum_degrees": lower.tolist(),
        "calibrated_maximum_degrees": upper.tolist(),
        "timestamps_seconds": timestamps.tolist(),
        "actions_degrees": actions.tolist(),
        "action_sha256": _float64_sha256(actions),
        "dry_run": True,
        "physical_authority": False,
    }
    plan["hardware_identity"] = {
        "gateway_schema": GATEWAY_SCHEMA,
        "follower_port": plan["follower_port"],
        "follower_calibration_sha256": plan["follower_calibration_sha256"],
        "real_leader_identity_bound": False,
    }
    return plan


def _reposition_receipt(plan: dict[str, Any]) -> dict[str, Any]:
    plan_sha256 = _canonical_sha256(plan)
    return {
        "kind": REPOSITION_PLAN_KIND,
        "schema_version": REPOSITION_SCHEMA,
        "packet_id": f"P18-{plan_sha256[:16]}",
        "single_use": True,
        "physical_packet_execution_admitted": False,
        "independent_review": {
            "reviewer": None,
            "reviewed_at": None,
            "decision_id": None,
            "bounded_reposition_reviewed": False,
            "collision_contact_free_workspace_confirmed": False,
        },
        "plan_sha256": plan_sha256,
        "plan": plan,
        "dry_run": True,
        "physical_motion_commanded": False,
        "physical_authority": False,
    }


def _validate_reposition_receipt(packet: dict[str, Any]) -> dict[str, Any]:
    if (
        packet.get("kind") != REPOSITION_PLAN_KIND
        or packet.get("schema_version") != REPOSITION_SCHEMA
        or packet.get("single_use") is not True
        or not isinstance(packet.get("plan"), dict)
    ):
        raise RecorderError("Unsupported follower reposition plan.")
    plan = packet["plan"]
    if packet.get("plan_sha256") != _canonical_sha256(plan):
        raise RecorderError("Follower reposition plan digest changed.")
    if packet.get("packet_id") != f"P18-{packet['plan_sha256'][:16]}":
        raise RecorderError("Follower reposition plan identity changed.")
    if plan.get("control_source") != EXCITATION_CONTROL_SOURCE:
        raise RecorderError("Follower reposition control source changed.")
    hardware = plan.get("hardware_identity")
    if (
        not isinstance(hardware, dict)
        or set(hardware)
        != {
            "gateway_schema",
            "follower_port",
            "follower_calibration_sha256",
            "real_leader_identity_bound",
        }
        or hardware.get("gateway_schema") != GATEWAY_SCHEMA
        or hardware.get("real_leader_identity_bound") is not False
        or hardware.get("follower_port") != plan.get("follower_port")
        or hardware.get("follower_calibration_sha256")
        != plan.get("follower_calibration_sha256")
        or not re.fullmatch(
            r"[0-9a-f]{64}", str(hardware.get("follower_calibration_sha256") or "")
        )
    ):
        raise RecorderError("Follower reposition hardware identity changed.")
    anchor = np.asarray(plan.get("anchor_degrees"), dtype=np.float64)
    target = np.asarray(plan.get("target_degrees"), dtype=np.float64)
    lower = np.asarray(plan.get("calibrated_minimum_degrees"), dtype=np.float64)
    upper = np.asarray(plan.get("calibrated_maximum_degrees"), dtype=np.float64)
    actions = np.asarray(plan.get("actions_degrees"), dtype=np.float64)
    timestamps = np.asarray(plan.get("timestamps_seconds"), dtype=np.float64)
    if any(
        values.shape != (6,) or not np.all(np.isfinite(values))
        for values in (anchor, target, lower, upper)
    ) or (
        actions.ndim != 2
        or actions.shape[1:] != (6,)
        or timestamps.shape != (actions.shape[0],)
        or actions.shape[0] < 2
        or not np.all(np.isfinite(actions))
        or not np.all(np.isfinite(timestamps))
        or not np.all(np.diff(timestamps) > 0.0)
        or timestamps[0] != 0.0
    ):
        raise RecorderError("Follower reposition trajectory is malformed.")
    expected_delta = np.zeros(6, dtype=np.float64)
    expected_delta[1] = REPOSITION_SHOULDER_DELTA_DEGREES
    expected_delta[2] = REPOSITION_ELBOW_DELTA_DEGREES
    if not np.array_equal(target - anchor, expected_delta):
        raise RecorderError("Follower reposition target delta changed.")
    if not np.array_equal(actions[0], anchor) or not np.array_equal(
        actions[-1], target
    ):
        raise RecorderError("Follower reposition must start at anchor and end at target.")
    if not np.all(
        actions[:, [0, 3, 4, 5]] == anchor[[0, 3, 4, 5]][None, :]
    ):
        raise RecorderError("Follower reposition changed an uncommanded joint.")
    expected_timestamps = (
        np.arange(actions.shape[0], dtype=np.float64) / REPOSITION_SAMPLE_HZ
    )
    if plan.get("sample_hz") != REPOSITION_SAMPLE_HZ or not np.array_equal(
        timestamps, expected_timestamps
    ):
        raise RecorderError("Follower reposition timestamps or sample rate changed.")
    if np.max(
        np.abs(np.diff(actions, axis=0) / np.diff(timestamps)[:, None])
    ) > REPOSITION_SLEW_DEGREES_S + 1e-12:
        raise RecorderError("Follower reposition interpolation exceeds its slew bound.")
    if np.any(target < lower) or np.any(target > upper):
        raise RecorderError("Follower reposition target exceeds calibrated limits.")
    for index in (1, 2):
        if (
            target[index] - REPOSITION_MARGIN_DEGREES < lower[index]
            or target[index] + REPOSITION_MARGIN_DEGREES > upper[index]
        ):
            raise RecorderError(
                "Follower reposition target lacks the required ±3 degree margin."
            )
    if plan.get("action_sha256") != _float64_sha256(actions):
        raise RecorderError("Follower reposition action hash changed.")
    return {
        "plan": plan,
        "anchor": anchor,
        "target": target,
        "actions": actions,
        "timestamps": timestamps,
        "hardware": hardware,
    }


def reposition_physical_follower(
    packet_path: Path,
    *,
    output_path: Path | None = None,
    dry_run: bool = False,
    operator_acknowledged: bool = False,
    preflight_fn: Callable[[], dict[str, Any]] = (
        physical_excitation_follower_preflight
    ),
    gateway_factory: Callable[[GatewayIdentity], SO101PhysicalGateway] = (
        _physical_excitation_gateway
    ),
    clock_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Move only the follower through a bounded interpolated target."""

    if dry_run:
        if output_path is not None:
            raise RecorderError("--output is not valid during reposition dry-run.")
        preflight = preflight_fn()
        receipt = _reposition_receipt(_build_reposition_plan(preflight))
        _write_once(packet_path, receipt)
        return receipt
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    validated = _validate_reposition_receipt(packet)
    if not operator_acknowledged:
        raise RecorderError("Fresh operator acknowledgement is required.")
    if packet.get("physical_packet_execution_admitted") is not True or not all(
        (packet.get("independent_review") or {}).get(field)
        for field in REPOSITION_REVIEW_FIELDS
    ):
        raise RecorderError(
            "Follower reposition requires the independently admitted packet."
        )
    if output_path is not None and output_path.exists():
        raise RecorderError(f"Refusing to overwrite existing output: {output_path}.")
    preflight = preflight_fn()
    hardware = validated["hardware"]
    for key in ("gateway_schema", "follower_port", "follower_calibration_sha256"):
        observed = (
            preflight.get("schema_version")
            if key == "gateway_schema"
            else preflight.get(key)
        )
        if observed != hardware[key]:
            raise RecorderError(f"Reposition hardware identity mismatch: {key}.")
    if not (
        preflight.get("passed") is True
        and preflight.get("control_source") == EXCITATION_CONTROL_SOURCE
        and preflight.get("real_leader_opened") is False
        and preflight.get("physical_follower_torque_enabled") is False
        and preflight.get("device_configuration_rewritten") is False
    ):
        raise RecorderError("Follower-only reposition preflight did not pass.")
    current = np.asarray(preflight["follower_start_degrees"], dtype=np.float64)
    anchor = validated["anchor"]
    anchor_delta = current - anchor
    anchor_delta[4] = shortest_delta_degrees(float(current[4]), float(anchor[4]))
    if np.any(
        np.abs(anchor_delta)
        > np.asarray(validated["plan"]["anchor_tolerance_degrees"])
    ):
        raise RecorderError("Fresh follower pose does not match the packet anchor.")

    identity = GatewayIdentity(
        leader_port=_EXCITATION_COMMAND_SOURCE_PORT,
        follower_port=str(hardware["follower_port"]),
        leader_calibration_sha256=_EXCITATION_COMMAND_SOURCE_SHA256,
        follower_calibration_sha256=str(hardware["follower_calibration_sha256"]),
    )
    gateway = gateway_factory(identity)
    completed = 0
    actual: np.ndarray | None = None
    started = clock_fn()
    try:
        opened = gateway.open(enable_motion=True, paired_pose_confirmed=True)
        opened_start = np.asarray(opened["follower_start_degrees"], dtype=np.float64)
        opened_delta = opened_start - anchor
        opened_delta[4] = shortest_delta_degrees(
            float(opened_start[4]), float(anchor[4])
        )
        if np.any(
            np.abs(opened_delta)
            > np.asarray(packet["plan"]["anchor_tolerance_degrees"])
        ):
            raise RecorderError("Follower anchor drifted before reposition hold.")
        for timestamp, action in zip(
            validated["timestamps"], validated["actions"], strict=True
        ):
            delay = started + float(timestamp) - clock_fn()
            if delay > 0.0:
                sleep_fn(delay)
            sample = gateway.sample(
                float(timestamp),
                exact_requested_degrees=np.asarray(action, dtype=np.float64),
            )
            if (
                _float64_sha256([sample["follower_requested_degrees"]])
                != _float64_sha256([action])
                or _float64_sha256([sample["follower_command_degrees"]])
                != _float64_sha256([action])
                or sample.get("rate_limited")
                or sample.get("safety_clamped")
            ):
                raise RecorderError("Follower reposition action was modified.")
            actual = np.asarray(
                sample["follower_actual_position_degrees"], dtype=np.float64
            )
            completed += 1
        if actual is None:
            raise RecorderError("Follower reposition produced no samples.")
        residual = actual - validated["target"]
        residual[4] = shortest_delta_degrees(
            float(actual[4]), float(validated["target"][4])
        )
        if np.any(np.abs(residual[:5]) > POST_HOLD_BODY_TOLERANCE_DEG) or abs(
            float(residual[5])
        ) > POST_HOLD_GRIPPER_TOLERANCE:
            raise RecorderError("Follower did not reach the reposition target.")
    finally:
        gateway.close()
    report = {
        **packet,
        "status": "completed_follower_reposition",
        "dry_run": False,
        "completed_samples": completed,
        "final_actual_degrees": actual.tolist(),
        "final_residual_degrees": residual.tolist(),
        "physical_follower_torque_enabled": False,
        "physical_motion_commanded": True,
        "physical_authority": False,
        "wall_duration_seconds": max(0.0, clock_fn() - started),
    }
    if output_path is not None:
        _write_once(output_path, report)
    return report


class PrecompiledExcitationBackend:
    proof_class = EXCITATION_SOURCE_PROOF_CLASS

    def __init__(
        self,
        request: dict[str, Any],
        preflight: dict[str, Any],
        *,
        plan: dict[str, Any],
        episode: dict[str, Any],
        gateway_factory: Callable[[GatewayIdentity], SO101PhysicalGateway] = (
            _physical_excitation_gateway
        ),
    ):
        self.request = request
        self.plan = plan
        self.episode = episode
        del preflight
        hardware = plan["hardware_identity"]
        identity = GatewayIdentity(
            leader_port=_EXCITATION_COMMAND_SOURCE_PORT,
            follower_port=str(hardware["follower_port"]),
            leader_calibration_sha256=_EXCITATION_COMMAND_SOURCE_SHA256,
            follower_calibration_sha256=str(
                hardware["follower_calibration_sha256"]
            ),
        )
        self.gateway = gateway_factory(identity)
        self.index = 0
        self.actions = np.asarray(episode["actions_degrees"], dtype=np.float64)
        self.timestamps = np.asarray(
            episode["timestamps_seconds"], dtype=np.float64
        )

    @property
    def recording_complete(self) -> bool:
        return self.index == len(self.timestamps)

    def open(self) -> dict[str, Any]:
        report = self.gateway.open(enable_motion=True, paired_pose_confirmed=True)
        current = np.asarray(report["follower_registration_degrees"])
        anchor = np.asarray(self.plan["anchor_degrees"])
        delta = current - anchor
        delta[4] = shortest_delta_degrees(float(current[4]), float(anchor[4]))
        tolerance = np.asarray(self.plan["anchor_tolerance_degrees"])
        if np.any(np.abs(delta) > tolerance):
            self.gateway.close()
            raise RecorderError(
                "Fresh follower pose no longer matches the compiled anchor; "
                "torque released."
            )
        return {
            **report,
            "proof_class": self.proof_class,
            "control_source": EXCITATION_CONTROL_SOURCE,
            "real_leader_opened": False,
            "pose_inputs_available": False,
            "physical_follower_torque_enabled": True,
            "precompiled_gateway_action_degrees_sha256": self.episode[
                "gateway_action_degrees_sha256"
            ],
        }

    def sample(self, _elapsed_seconds: float) -> dict[str, Any]:
        if self.recording_complete:
            raise RecorderError("Precompiled excitation was sampled after completion.")
        target = self.actions[self.index]
        sample = self.gateway.sample(
            float(self.timestamps[self.index]),
            exact_requested_degrees=target,
        )
        if (
            _float64_sha256([sample["follower_requested_degrees"]])
            != _float64_sha256(target[None, :])
            or _float64_sha256([sample["follower_command_degrees"]])
            != _float64_sha256(target[None, :])
            or sample.get("rate_limited")
            or sample.get("safety_clamped")
        ):
            raise RecorderError(
                "Gateway did not preserve the precompiled float64 action bytes."
            )
        sample["elapsed_seconds"] = float(self.timestamps[self.index])
        self.index += 1
        return sample

    def close(self) -> None:
        self.gateway.close()


def _wait_for_excitation_recording(
    manager: Any,
    *,
    timeout_seconds: float,
    clock_fn: Callable[[], float],
    sleep_fn: Callable[[float], None],
) -> None:
    deadline = clock_fn() + timeout_seconds
    while True:
        state = manager.snapshot()
        status = state.get("status")
        if status == "awaiting_label":
            return
        if status == "error" or state.get("last_error"):
            raise RecorderError(str(state.get("error") or state.get("last_error")))
        if clock_fn() >= deadline:
            raise RecorderError("Precompiled excitation recording timed out.")
        sleep_fn(0.01)


def execute_physical_excitation_packet(
    packet_path: Path,
    output_directory: Path,
    *,
    repo_root: Path = REPO_ROOT,
    operator_acknowledged: bool = False,
    preflight_fn: Callable[[], dict[str, Any]] = (
        physical_excitation_follower_preflight
    ),
    manager_factory: Callable[..., Any] | None = None,
    materialize_fn: Callable[..., dict[str, Any]] | None = None,
    clock_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Execute one admitted immutable five-episode packet and wire P4/P9."""

    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    if (
        packet.get("physical_packet_execution_admitted") is not True
        or not all(
            (packet.get("independent_review") or {}).get(field)
            for field in (
                "reviewer",
                "reviewed_at",
                "decision_id",
                "bounded_excitation_reviewed",
                "collision_contact_free_workspace_confirmed",
            )
        )
    ):
        raise RecorderError(
            "This excitation packet is pending independent admission; "
            "no devices were opened."
        )
    if not operator_acknowledged:
        raise RecorderError("Fresh operator acknowledgement is required.")
    validated = _validate_excitation_plan(packet)
    _motion_authority(repo_root)
    plan = validated["plan"]
    preflight = preflight_fn()
    hardware = plan["hardware_identity"]
    for key in (
        "gateway_schema",
        "follower_port",
        "follower_calibration_sha256",
    ):
        expected = hardware[key]
        observed = (
            preflight.get("schema_version")
            if key == "gateway_schema"
            else preflight.get(key)
        )
        if observed != expected:
            raise RecorderError(f"Excitation hardware identity mismatch: {key}.")
    if not (
        preflight.get("passed") is True
        and preflight.get("control_source") == EXCITATION_CONTROL_SOURCE
        and preflight.get("real_leader_opened") is False
        and preflight.get("physical_follower_torque_enabled") is False
        and preflight.get("device_configuration_rewritten") is False
    ):
        raise RecorderError("Fresh torque-off execution preflight did not pass.")
    current = np.asarray(preflight["follower_start_degrees"], dtype=np.float64)
    anchor = validated["anchor"]
    delta = current - anchor
    delta[4] = shortest_delta_degrees(float(current[4]), float(anchor[4]))
    if np.any(np.abs(delta) > np.asarray(plan["anchor_tolerance_degrees"])):
        raise RecorderError("Fresh follower pose does not match the packet anchor.")

    output_directory = output_directory.resolve()
    p4_root = output_directory / "p4"
    cohort_entries: list[dict[str, str]] = []
    completed: list[dict[str, Any]] = []
    manager_type = manager_factory or TeleopRecordingManager
    if materialize_fn is None:
        from .replay_eligibility import materialize_physical_recording_exact_replay

        materialize_fn = materialize_physical_recording_exact_replay
    try:
        for index, episode in enumerate(plan["episodes"], start=1):
            label = f"{packet['packet_id'].lower()}-{episode['episode_id']}"
            for receipt_path in (
                repo_root / "datasets/manipulation_source_recordings"
            ).glob("*/recording_receipt.json"):
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                if receipt.get("label") == label:
                    raise RecorderError(
                        f"Single-use excitation already finalized: {episode['episode_id']}."
                    )
            manager = manager_type(
                repo_root=repo_root,
                backend_factory=lambda request, status, episode=episode: (
                    PrecompiledExcitationBackend(
                        request,
                        status,
                        plan=plan,
                        episode=episode,
                    )
                ),
                **(
                    {
                        "preflight_provider": lambda preflight=preflight: {
                            "schema_version": "sim2claw.teleop_preflight.v1",
                            "checked_at": _utc_now(),
                            "devices": {
                                "follower": {
                                    "role": "so101_follower",
                                    "port": preflight["follower_port"],
                                    "connected": True,
                                }
                            },
                            "calibrations": {
                                "follower": {
                                    "present": True,
                                    "sha256": preflight[
                                        "follower_calibration_sha256"
                                    ],
                                }
                            },
                            "runtime": {"lerobot_version": "preflight-verified"},
                            "modes": {
                                "physical_follower": {
                                    "ready": True,
                                    "device_ready": True,
                                    "physical_motion": True,
                                    "reason": None,
                                }
                            },
                            "control_source": EXCITATION_CONTROL_SOURCE,
                        }
                    }
                    if manager_factory is None
                    else {}
                ),
            )
            manager.start(
                {
                    "mode": "physical_follower",
                    "source_square": "a1",
                    "target_square": "a1",
                    "sample_hz": EXCITATION_SAMPLE_HZ,
                    "physical_safety_acknowledged": True,
                    "server_owned_prestart_sequence": True,
                    "action_owner": (
                        "independently_reviewed_precompiled_excitation_packet"
                    ),
                    "source_identity_kind": EXCITATION_CONTROL_SOURCE,
                }
            )
            _wait_for_excitation_recording(
                manager,
                timeout_seconds=10.0,
                clock_fn=clock_fn,
                sleep_fn=sleep_fn,
            )
            saved = manager.finalize(
                {
                    "label": label,
                    "skill": "recovery",
                    "outcome": "unreviewed",
                    "notes": (
                        f"single-use {packet['packet_id']} "
                        f"{episode['episode_id']}; exact packet bytes"
                    ),
                }
            )
            recording_path = repo_root / str(saved["saved_path"])
            episode_root = p4_root / episode["episode_id"]
            manifest_path = episode_root / "exact_replay_manifest.json"
            report_path = episode_root / "exact_replay_report.json"
            p4 = materialize_fn(recording_path, manifest_path, report_path)
            if (
                p4.get("exact_replay_eligible") is not True
                or p4.get("applied_action_sha256")
                != episode["canonical_action_radians_sha256"]
            ):
                raise RecorderError(
                    f"P4 rejected or action hash changed: {episode['episode_id']}."
                )
            completed.append(
                {
                    "episode_id": episode["episode_id"],
                    "recording": str(recording_path),
                    "gateway_action_degrees_sha256": episode[
                        "gateway_action_degrees_sha256"
                    ],
                    "canonical_action_radians_sha256": episode[
                        "canonical_action_radians_sha256"
                    ],
                }
            )
            cohort_entries.append(
                {
                    "recording": os.path.relpath(recording_path, output_directory),
                    "exact_replay_manifest": os.path.relpath(
                        manifest_path, output_directory
                    ),
                }
            )
    except Exception as error:
        _atomic_json(
            output_directory / "execution_report.json",
            {
                "status": "partial_failed_closed",
                "packet_id": packet.get("packet_id"),
                "completed": completed,
                "cohort_emitted": False,
                "error": f"{type(error).__name__}: {error}",
                "physical_authority": False,
            },
        )
        raise
    cohort = {
        "schema_version": "sim2claw.physical_timing_actuation_cohort.v1",
        "episodes": cohort_entries,
    }
    cohort_path = output_directory / "p9_cohort.json"
    _atomic_json(cohort_path, cohort)
    result = {
        "status": "five_recordings_finalized_and_p4_eligible",
        "packet_id": packet["packet_id"],
        "plan_sha256": packet["plan_sha256"],
        "completed": completed,
        "cohort_path": cohort_path.name,
        "cohort_sha256": _sha256(cohort_path),
        "physical_authority": False,
        "evaluator_admission": False,
    }
    _atomic_json(output_directory / "execution_report.json", result)
    return result


BackendFactory = Callable[[dict[str, Any], dict[str, Any]], RecorderBackend]
VideoRecorderFactory = Callable[[Path], DiagnosticVideoRecorder]
DualVideoRecorderFactory = Callable[[Path], DualDiagnosticVideoRecorder]
_DEFAULT_WRIST_FACTORY = object()
_DEFAULT_DUAL_FACTORY = object()


def _default_backend_factory(request: dict[str, Any], preflight: dict[str, Any]) -> RecorderBackend:
    mode = request["mode"]
    if mode == "simulation_follower":
        return SimulationFollowerBackend(request, preflight)
    if mode == "physical_follower":
        return PhysicalFollowerBackend(request, preflight)
    raise RecorderError(f"Unsupported recording mode: {mode}")


def _default_video_recorder_factory(draft: Path) -> DiagnosticVideoRecorder:
    return OverheadVideoRecorder(draft / "overhead_c922.mp4")


def _default_wrist_video_recorder_factory(draft: Path) -> DiagnosticVideoRecorder:
    return WristVideoRecorder(draft / "wrist_d405.mkv")


def _default_dual_video_recorder_factory(draft: Path) -> DualDiagnosticVideoRecorder:
    return NativeDualCameraRecorder(draft)


@dataclass
class RecorderPaths:
    repo_root: Path = REPO_ROOT

    @property
    def drafts(self) -> Path:
        return self.repo_root / "runs" / "teleop_recordings" / "drafts"

    @property
    def recordings(self) -> Path:
        return self.repo_root / "datasets" / "manipulation_source_recordings"

    @property
    def failures(self) -> Path:
        return self.repo_root / "runs" / "teleop_recordings" / "failed_attempts"


class TeleopRecordingManager:
    def __init__(
        self,
        *,
        repo_root: Path = REPO_ROOT,
        backend_factory: BackendFactory = _default_backend_factory,
        video_recorder_factory: VideoRecorderFactory = _default_video_recorder_factory,
        wrist_video_recorder_factory: VideoRecorderFactory | None | object = (
            _DEFAULT_WRIST_FACTORY
        ),
        dual_video_recorder_factory: DualVideoRecorderFactory | None | object = (
            _DEFAULT_DUAL_FACTORY
        ),
        dev_root: Path = Path("/dev"),
        calibration_root: Path | None = None,
        preflight_provider: Callable[[], dict[str, Any]] | None = None,
    ):
        self.paths = RecorderPaths(repo_root.resolve())
        self.backend_factory = backend_factory
        self.video_recorder_factory = video_recorder_factory
        self.wrist_video_recorder_factory = (
            _default_wrist_video_recorder_factory
            if wrist_video_recorder_factory is _DEFAULT_WRIST_FACTORY
            and video_recorder_factory is _default_video_recorder_factory
            else None
            if wrist_video_recorder_factory is _DEFAULT_WRIST_FACTORY
            else wrist_video_recorder_factory
        )
        self.dual_video_recorder_factory = (
            _default_dual_video_recorder_factory
            if dual_video_recorder_factory is _DEFAULT_DUAL_FACTORY
            and video_recorder_factory is _default_video_recorder_factory
            and wrist_video_recorder_factory is _DEFAULT_WRIST_FACTORY
            else None
            if dual_video_recorder_factory is _DEFAULT_DUAL_FACTORY
            else dual_video_recorder_factory
        )
        self.dev_root = dev_root
        self.calibration_root = calibration_root
        self.preflight_provider = preflight_provider
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.ready_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.backend: RecorderBackend | None = None
        self.video_recorder: DiagnosticVideoRecorder | None = None
        self.wrist_video_recorder: DiagnosticVideoRecorder | None = None
        self.dual_video_recorder: DualDiagnosticVideoRecorder | None = None
        self.live_simulation: dict[str, Any] = self._empty_live_simulation()
        self.state: dict[str, Any] = self._recover_existing_state()

    def _empty_live_simulation(self) -> dict[str, Any]:
        return {
            "schema_version": LIVE_SIMULATION_SCHEMA,
            "mode": None,
            "recording_id": None,
            "active": False,
            "scene_url": f"/api/scene?layout={CURRENT_TASK_PIECE_LAYOUT}",
            "manifest_revision_sha256": None,
            "body_names": [],
            "frame_index": None,
            "frame": None,
            "authority": {
                "pose_source": "mujoco.MjData.xpos+xquat",
                "browser_renderer": "inspection_only",
                "physical_authority": False,
            },
        }

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
            "last_error_details": None,
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
                        "last_error_details": candidate.get("error_details"),
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
                "last_error_details": failed_state.get("error_details"),
                "last_failed_recording_id": failed_state.get("recording_id"),
                "last_failed_attempt_path": archived_path,
            }

    def preflight(self) -> dict[str, Any]:
        if self.preflight_provider is not None:
            return self.preflight_provider()
        return recorder_preflight(
            dev_root=self.dev_root,
            calibration_root=self.calibration_root,
        )

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            snapshot = json.loads(json.dumps(self.state))
        snapshot["preflight"] = self.preflight()
        return snapshot

    def live_simulation_snapshot(self) -> dict[str, Any]:
        """Return the latest simulator pose without touching either arm bus."""

        with self.lock:
            return json.loads(json.dumps(self.live_simulation))

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

    def start(self, request: dict[str, Any], *, timeout_seconds: float = 40.0) -> dict[str, Any]:
        self._return_failed_attempt_to_ready()
        contract = load_source_contract(RECORDER_SOURCE_CONTRACT_PATH)
        mode = str(request.get("mode") or "simulation_follower")
        if mode not in {"simulation_follower", "physical_follower"}:
            raise RecorderError("Choose a simulator or physical follower.")
        source_square = str(request.get("source_square") or "").lower()
        source_pieces_by_square = {
            str(piece_id).rsplit("_", 1)[-1]: str(piece_id)
            for piece_id in contract["scene"]["source_piece_ids"]
        }
        if mode == "physical_follower":
            if source_square not in LOWER_TWO_ROW_SQUARES:
                raise RecorderError(
                    "Choose a source square in lower rows 1 or 2."
                )
            # Physical command traces keep the operator's square as metadata;
            # the physical backend does not require a MuJoCo body at that square.
            piece_id = source_pieces_by_square.get(
                source_square, f"brown_pawn_{source_square}"
            )
        else:
            if source_square not in source_pieces_by_square:
                raise RecorderError(
                    "Choose one of the brown pawns present in the simulator scene."
                )
            piece_id = source_pieces_by_square[source_square]
        target_square = str(request.get("target_square") or "").lower()
        allowed_destinations = (
            set(LOWER_TWO_ROW_SQUARES)
            if mode == "physical_follower"
            else set(contract["scene"]["destination_squares"])
        )
        if target_square not in allowed_destinations:
            raise RecorderError(
                "Choose a destination square in the supported lower-board area."
            )
        resolve_structured_goal(piece_id, target_square)
        sample_hz = int(request.get("sample_hz") or DEFAULT_SAMPLE_HZ)
        if sample_hz != int(contract["episode"]["required_sample_hz"]):
            raise RecorderError(
                "Canonical source recording is frozen at exact 20 Hz sample-hold."
            )
        preflight = self.preflight()
        mode_status = preflight["modes"][mode]
        if not mode_status["ready"]:
            raise RecorderError(str(mode_status["reason"]))
        source_identity_kind = str(
            request.get("source_identity_kind") or "leader_teleoperation"
        )
        if source_identity_kind not in {
            "leader_teleoperation",
            EXCITATION_CONTROL_SOURCE,
        }:
            raise RecorderError("Physical source identity kind is unsupported.")
        if (
            source_identity_kind == EXCITATION_CONTROL_SOURCE
            and (
                mode != "physical_follower"
                or preflight.get("control_source") != EXCITATION_CONTROL_SOURCE
                or request.get("action_owner")
                != "independently_reviewed_precompiled_excitation_packet"
            )
        ):
            raise RecorderError(
                "Precompiled follower source identity lacks its P10 control boundary."
            )
        scene_registration = scene_summary(piece_layout=CURRENT_TASK_PIECE_LAYOUT)
        board_registration = scene_registration["board"]
        fiducial_registration = scene_registration["fiducial"]
        workcell_registration = {
            "workspace_pose_id": scene_registration["workspace_pose"]["pose_id"],
            "board_scene_id": board_registration["scene_id"],
            "board_pose_id": board_registration["pose_id"],
            "board_center_in_table_frame_xy_m": board_registration[
                "center_in_table_frame_xy_m"
            ],
            "robotward_displacement_from_previous_pose_m": board_registration[
                "robotward_displacement_from_previous_pose_m"
            ],
            "robotward_axis_in_table_frame": board_registration[
                "robotward_axis_in_table_frame"
            ],
            "fiducial_pose_id": fiducial_registration["pose_id"],
            "fiducial_center_in_table_frame_xy_m": fiducial_registration[
                "center_in_table_frame_xy_m"
            ],
            "fiducial_robotward_displacement_from_previous_pose_m": (
                fiducial_registration[
                    "robotward_displacement_from_previous_pose_m"
                ]
            ),
            "fiducial_robotward_axis_in_table_frame": fiducial_registration[
                "robotward_axis_in_table_frame"
            ],
        }
        request = {
            "mode": mode,
            "piece_id": piece_id,
            "source_square": source_square,
            "target_square": target_square,
            "sample_hz": sample_hz,
            "physical_safety_acknowledged": bool(request.get("physical_safety_acknowledged")),
            "server_owned_prestart_sequence": bool(
                request.get("server_owned_prestart_sequence")
            ),
            "task_id": contract["contract_id"],
            "scene_reset_seed": int(request.get("scene_reset_seed") or 0),
            "action_owner": str(request.get("action_owner") or "human_teleoperator"),
            "source_identity_kind": source_identity_kind,
        }
        if mode == "physical_follower" and not request["physical_safety_acknowledged"]:
            raise RecorderError("Physical safety acknowledgement is required.")
        if mode == "physical_follower" and not request["server_owned_prestart_sequence"]:
            raise RecorderError("Server-owned physical pre-start sequence is required.")
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
                "task_id": contract["contract_id"],
                "source_contract_sha256": source_contract_sha256(
                    RECORDER_SOURCE_CONTRACT_PATH
                ),
                "workcell_registration": workcell_registration,
                "scene_reset_seed": request["scene_reset_seed"],
                "language_instruction": language_instruction(
                    piece_id, source_square, target_square
                ),
                "source_identity": {
                    "kind": request["source_identity_kind"],
                    "proof_class": (
                        "simulation_teleoperation_source"
                        if mode == "simulation_follower"
                        else (
                            EXCITATION_SOURCE_PROOF_CLASS
                            if request["source_identity_kind"]
                            == EXCITATION_CONTROL_SOURCE
                            else "physical_teleoperation_source_unqualified"
                        )
                    ),
                },
                "model_identity": None,
                "checkpoint_identity": None,
                "action_owner": request["action_owner"],
                "assistance_frames": 0,
                "intervention_frames": 0,
                "lineage": {
                    "parent_source_episode_id": None,
                    "failed_prefix_source_episode_id": None,
                    "corrective_suffix_parent_state_sha256": None,
                    "collection_kind": "original_source_episode",
                },
            }
            self.live_simulation = {
                **self._empty_live_simulation(),
                "mode": mode,
                "recording_id": recording_id,
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
        samples_path = draft / "samples.jsonl"
        privileged_path = draft / "evaluator_privileged_state.jsonl"
        sequence_started_monotonic: float | None = None
        sequence_stopped_monotonic: float | None = None
        action_started_monotonic: float | None = None
        action_stopped_monotonic: float | None = None
        action_stopped_at: str | None = None
        video_started_monotonic: float | None = None
        wrist_video_started_monotonic: float | None = None
        visual_streams = {
            "overhead_workspace": "overhead_c922.mp4",
            "wrist_gripper_upward": "wrist_d405.mkv",
        }
        errors: list[str] = []
        try:
            wrist_video_state: dict[str, Any] | None = None
            common_camera_state: dict[str, Any] | None = None
            if request["mode"] == "physical_follower" and callable(
                self.dual_video_recorder_factory
            ):
                self.dual_video_recorder = self.dual_video_recorder_factory(draft)
                common_camera_state = self.dual_video_recorder.start()
                video_state = dict(common_camera_state["overhead"])
                wrist_video_state = dict(common_camera_state["wrist"])
                video_started_monotonic = self.dual_video_recorder.started_monotonic
                wrist_video_started_monotonic = video_started_monotonic
                if video_started_monotonic is None:
                    raise OverheadVideoError(
                        "Native dual-camera capture did not publish its start clock."
                    )
            else:
                self.video_recorder = self.video_recorder_factory(draft)
            if self.dual_video_recorder is None and (
                request["mode"] == "physical_follower"
                and callable(self.wrist_video_recorder_factory)
            ):
                self.wrist_video_recorder = self.wrist_video_recorder_factory(draft)
                wrist_video_state = self.wrist_video_recorder.start()
                wrist_video_started_monotonic = (
                    self.wrist_video_recorder.started_monotonic
                )
                if wrist_video_started_monotonic is None:
                    raise OverheadVideoError(
                        "D405 wrist capture did not publish its start clock."
                    )
            if self.dual_video_recorder is None:
                # Retained only for injected/legacy recorders. The production
                # physical path uses one native session and no nested lifecycle.
                assert self.video_recorder is not None
                video_state = self.video_recorder.start()
                video_started_monotonic = self.video_recorder.started_monotonic
            sequence_started_monotonic = time.monotonic()
            if video_started_monotonic is None:
                raise OverheadVideoError("C922 video capture did not publish its start clock.")
            visual_streams = {
                "overhead_workspace": str(
                    video_state.get("video_path") or "overhead_c922.mp4"
                ),
                "wrist_gripper_upward": str(
                    (wrist_video_state or {}).get("video_path") or "wrist_d405.mkv"
                ),
            }
            with self.lock:
                self.live_simulation["active"] = False
                self.state.update(
                    overhead_video=video_state,
                    wrist_video=wrist_video_state,
                    wrist_video_required=wrist_video_state is not None,
                    native_common_camera_session=common_camera_state,
                    prestart_sequence_started_at=_utc_now(),
                    prestart_sequence_start_video_offset_seconds=(
                        sequence_started_monotonic - video_started_monotonic
                    ),
                )
            self.backend = self.backend_factory(request, preflight)
            backend_state = self.backend.open()
            live_start = backend_state.pop("_live_simulation", None)
            initial_privileged_state = backend_state.pop(
                "_initial_evaluator_privileged_state", None
            )
            _atomic_json(
                draft / "initial_evaluator_privileged_state.json",
                {
                    "schema_version": "sim2claw.evaluator_initial_privileged_state.v1",
                    "episode_id": self.state["recording_id"],
                    "policy_adapter_access": False,
                    "state": initial_privileged_state
                    if isinstance(initial_privileged_state, dict)
                    else {"available": False},
                },
            )
            action_started_monotonic = time.monotonic()
            with self.lock:
                self.state.update(
                    status="recording",
                    backend=backend_state,
                    action_started_at=_utc_now(),
                    action_start_video_offset_seconds=(
                        action_started_monotonic - video_started_monotonic
                    ),
                    physical_follower_torque_enabled=bool(
                        backend_state.get("physical_follower_torque_enabled")
                    ),
                )
                if isinstance(live_start, dict):
                    live_scene = dict(live_start.get("scene") or {})
                    self.live_simulation = {
                        **self._empty_live_simulation(),
                        "mode": request["mode"],
                        "recording_id": self.state["recording_id"],
                        "active": True,
                        "scene_url": live_scene.get("manifest_url"),
                        "manifest_revision_sha256": live_scene.get(
                            "manifest_revision_sha256"
                        ),
                        "body_names": list(live_start.get("body_names") or []),
                        "frame_index": live_start.get("frame_index"),
                        "frame": live_start.get("frame"),
                    }
            self.ready_event.set()
            interval = 1.0 / int(request["sample_hz"])
            next_tick = time.monotonic()
            with (
                samples_path.open("w", encoding="utf-8") as handle,
                privileged_path.open("w", encoding="utf-8") as privileged_handle,
            ):
                while not self.stop_event.is_set():
                    tick = time.monotonic()
                    if self.dual_video_recorder is not None:
                        self.dual_video_recorder.ensure_running()
                    elif self.video_recorder is not None:
                        self.video_recorder.ensure_running()
                    if (
                        self.dual_video_recorder is None
                        and self.wrist_video_recorder is not None
                    ):
                        self.wrist_video_recorder.ensure_running()
                    sample = self.backend.sample(tick - action_started_monotonic)
                    live_frame = sample.pop("_live_simulation_frame", None)
                    rgb_frames = sample.pop("_rgb_frames", None)
                    privileged_state = sample.pop(
                        "_evaluator_privileged_state", None
                    )
                    with self.lock:
                        index = int(self.state["sample_count"])
                    timestamp = float(
                        sample.pop(
                            "elapsed_seconds", tick - action_started_monotonic
                        )
                    )
                    raw_sample = {
                        "overhead_video_time_seconds": tick
                        - video_started_monotonic,
                        "wrist_video_time_seconds": (
                            tick - wrist_video_started_monotonic
                            if wrist_video_started_monotonic is not None
                            else None
                        ),
                        **sample,
                    }
                    if request["mode"] == "physical_follower":
                        row = _physical_source_row(
                            episode_id=str(self.state["recording_id"]),
                            sample_index=index,
                            timestamp_monotonic_seconds=timestamp,
                            instruction=str(self.state["language_instruction"]),
                            raw_sample=raw_sample,
                            action_owner=str(self.state["action_owner"]),
                            assistance=False,
                            intervention=False,
                            visual_streams=visual_streams,
                        )
                    else:
                        rgb_references: dict[str, Any] = {}
                        for stream in ("top", "wrist"):
                            frame = (
                                rgb_frames.get(stream)
                                if isinstance(rgb_frames, dict)
                                else None
                            )
                            relative_path = Path("rgb") / stream / f"{index:06d}.png"
                            frame_path = draft / relative_path
                            if frame is None:
                                rgb_references[stream] = {
                                    "available": False,
                                    "path": relative_path.as_posix(),
                                    "timestamp_monotonic_seconds": timestamp,
                                    "sha256": None,
                                }
                            else:
                                write_rgb_png(
                                    frame_path,
                                    np.asarray(frame, dtype=np.uint8),
                                )
                                rgb_references[stream] = {
                                    "available": True,
                                    "path": relative_path.as_posix(),
                                    "timestamp_monotonic_seconds": timestamp,
                                    "sha256": _sha256(frame_path),
                                }
                        row = _canonical_source_row(
                            episode_id=str(self.state["recording_id"]),
                            sample_index=index,
                            timestamp_monotonic_seconds=timestamp,
                            instruction=str(self.state["language_instruction"]),
                            raw_sample=raw_sample,
                            rgb=rgb_references,
                            action_owner=str(self.state["action_owner"]),
                            assistance=False,
                            intervention=False,
                        )
                    handle.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")
                    handle.flush()
                    privileged_handle.write(
                        json.dumps(
                            {
                                "schema_version": "sim2claw.evaluator_privileged_state.v1",
                                "episode_id": self.state["recording_id"],
                                "sample_index": index,
                                "timestamp_monotonic_seconds": timestamp,
                                "policy_adapter_access": False,
                                "state": privileged_state
                                if isinstance(privileged_state, dict)
                                else {"available": False},
                            },
                            separators=(",", ":"),
                            sort_keys=True,
                        )
                        + "\n"
                    )
                    privileged_handle.flush()
                    with self.lock:
                        self.state["sample_count"] = index + 1
                        self.state["duration_seconds"] = float(row["timestamp_monotonic_seconds"])
                        self.state["last_sample"] = row
                        if isinstance(live_frame, dict):
                            self.live_simulation.update(
                                active=True,
                                frame_index=live_frame.get("frame_index"),
                                frame=live_frame.get("frame"),
                            )
                    if bool(getattr(self.backend, "recording_complete", False)):
                        self.stop_event.set()
                    next_tick += interval
                    self.stop_event.wait(max(0.0, next_tick - time.monotonic()))
            action_stopped_monotonic = time.monotonic()
            sequence_stopped_monotonic = action_stopped_monotonic
            action_stopped_at = _utc_now()
            with self.lock:
                self.live_simulation["active"] = False
                self.state.update(
                    status="stopping",
                    action_stopped_at=action_stopped_at,
                    action_stop_video_offset_seconds=(
                        action_stopped_monotonic - video_started_monotonic
                    ),
                )
            export_trace = getattr(self.backend, "write_state_trace", None)
            if callable(export_trace):
                trace_result = export_trace(draft / "state_trace.json")
                with self.lock:
                    self.state["backend"]["state_trace_path"] = "state_trace.json"
                    self.state["backend"]["state_trace_sha256"] = trace_result["sha256"]
        except Exception as error:  # hardware/runtime errors must fail closed
            errors.append(f"{type(error).__name__}: {error}")
            error_details = getattr(error, "details", None)
            if error_details is not None:
                with self.lock:
                    self.state["error_details"] = error_details
            if sequence_started_monotonic is not None:
                sequence_stopped_monotonic = time.monotonic()
            if action_started_monotonic is not None and action_stopped_monotonic is None:
                action_stopped_monotonic = sequence_stopped_monotonic
                action_stopped_at = _utc_now()
        finally:
            if self.backend is not None:
                try:
                    self.backend.close()
                except Exception as error:
                    errors.append(f"backend close error: {type(error).__name__}: {error}")
                finally:
                    self.backend = None

            video_metadata: dict[str, Any] | None = None
            wrist_video_metadata: dict[str, Any] | None = None
            if self.dual_video_recorder is not None:
                try:
                    video_stop_anchor = (
                        action_stopped_monotonic or sequence_stopped_monotonic
                    )
                    common_result = self.dual_video_recorder.finish(
                        action_started_monotonic=action_started_monotonic,
                        action_stopped_monotonic=video_stop_anchor,
                        post_roll_seconds=(
                            1.0 if video_stop_anchor is not None else 0.0
                        ),
                    )
                    video_metadata = dict(common_result["overhead"])
                    wrist_video_metadata = dict(common_result["wrist"])
                    common_started = self.dual_video_recorder.started_monotonic
                    if common_started is not None:
                        for metadata in (video_metadata, wrist_video_metadata):
                            metadata.update(
                                prestart_sequence_start_video_offset_seconds=(
                                    sequence_started_monotonic - common_started
                                    if sequence_started_monotonic is not None
                                    else None
                                ),
                                prestart_sequence_stop_video_offset_seconds=(
                                    sequence_stopped_monotonic - common_started
                                    if sequence_stopped_monotonic is not None
                                    else None
                                ),
                                teleoperation_start_video_offset_seconds=(
                                    action_started_monotonic - common_started
                                    if action_started_monotonic is not None
                                    else None
                                ),
                                teleoperation_stop_video_offset_seconds=(
                                    action_stopped_monotonic - common_started
                                    if action_stopped_monotonic is not None
                                    else None
                                ),
                            )
                    _atomic_json(draft / "overhead_video.json", video_metadata)
                    _atomic_json(draft / "wrist_video.json", wrist_video_metadata)
                    if (
                        video_metadata.get("status") != "completed"
                        or wrist_video_metadata.get("status") != "completed"
                    ):
                        errors.append(
                            "OverheadVideoError: native common-session capture "
                            "did not complete both attributed streams."
                        )
                    with self.lock:
                        self.state["native_common_camera_session"] = common_result[
                            "common_session"
                        ]
                except Exception as error:
                    errors.append(
                        f"dual video close error: {type(error).__name__}: {error}"
                    )
                finally:
                    self.dual_video_recorder = None
            if self.dual_video_recorder is None and self.video_recorder is not None:
                try:
                    video_stop_anchor = (
                        action_stopped_monotonic or sequence_stopped_monotonic
                    )
                    video_metadata = self.video_recorder.finish(
                        action_started_monotonic=action_started_monotonic,
                        action_stopped_monotonic=video_stop_anchor,
                        post_roll_seconds=(
                            1.0 if video_stop_anchor is not None else 0.0
                        ),
                    )
                    video_started_monotonic = self.video_recorder.started_monotonic
                    if video_started_monotonic is not None:
                        video_metadata.update(
                            prestart_sequence_start_video_offset_seconds=(
                                sequence_started_monotonic - video_started_monotonic
                                if sequence_started_monotonic is not None
                                else None
                            ),
                            prestart_sequence_stop_video_offset_seconds=(
                                sequence_stopped_monotonic - video_started_monotonic
                                if sequence_stopped_monotonic is not None
                                else None
                            ),
                            teleoperation_start_video_offset_seconds=(
                                action_started_monotonic - video_started_monotonic
                                if action_started_monotonic is not None
                                else None
                            ),
                            teleoperation_stop_video_offset_seconds=(
                                action_stopped_monotonic - video_started_monotonic
                                if action_stopped_monotonic is not None
                                else None
                            ),
                            action_start_video_offset_seconds=(
                                action_started_monotonic - video_started_monotonic
                                if action_started_monotonic is not None
                                else None
                            ),
                            action_stop_video_offset_seconds=(
                                action_stopped_monotonic - video_started_monotonic
                                if action_stopped_monotonic is not None
                                else None
                            ),
                        )
                    _atomic_json(draft / "overhead_video.json", video_metadata)
                    if video_metadata.get("status") != "completed":
                        detail = str(video_metadata.get("error_log_tail") or "").strip()
                        errors.append(
                            "OverheadVideoError: C922 video capture did not complete"
                            + (f": {detail}" if detail else ".")
                        )
                except Exception as error:
                    errors.append(f"video close error: {type(error).__name__}: {error}")
                finally:
                    self.video_recorder = None
            if self.wrist_video_recorder is not None:
                try:
                    video_stop_anchor = (
                        action_stopped_monotonic or sequence_stopped_monotonic
                    )
                    wrist_video_metadata = self.wrist_video_recorder.finish(
                        action_started_monotonic=action_started_monotonic,
                        action_stopped_monotonic=video_stop_anchor,
                        post_roll_seconds=(
                            1.0 if video_stop_anchor is not None else 0.0
                        ),
                    )
                    wrist_started = self.wrist_video_recorder.started_monotonic
                    if wrist_started is not None:
                        wrist_video_metadata.update(
                            prestart_sequence_start_video_offset_seconds=(
                                sequence_started_monotonic - wrist_started
                                if sequence_started_monotonic is not None
                                else None
                            ),
                            prestart_sequence_stop_video_offset_seconds=(
                                sequence_stopped_monotonic - wrist_started
                                if sequence_stopped_monotonic is not None
                                else None
                            ),
                            teleoperation_start_video_offset_seconds=(
                                action_started_monotonic - wrist_started
                                if action_started_monotonic is not None
                                else None
                            ),
                            teleoperation_stop_video_offset_seconds=(
                                action_stopped_monotonic - wrist_started
                                if action_stopped_monotonic is not None
                                else None
                            ),
                        )
                    _atomic_json(draft / "wrist_video.json", wrist_video_metadata)
                    if wrist_video_metadata.get("status") != "completed":
                        detail = str(
                            wrist_video_metadata.get("error_log_tail")
                            or wrist_video_metadata.get("browser_derivative_error")
                            or ""
                        ).strip()
                        errors.append(
                            "OverheadVideoError: D405 wrist capture did not complete"
                            + (f": {detail}" if detail else ".")
                        )
                except Exception as error:
                    errors.append(
                        f"wrist video close error: {type(error).__name__}: {error}"
                    )
                finally:
                    self.wrist_video_recorder = None

            with self.lock:
                self.state.update(
                    status="error" if errors else "awaiting_label",
                    error="; ".join(errors) if errors else None,
                    stopped_at=action_stopped_at or _utc_now(),
                    physical_follower_torque_enabled=False,
                )
                if video_metadata is not None:
                    self.state["overhead_video"] = video_metadata
                if wrist_video_metadata is not None:
                    self.state["wrist_video"] = wrist_video_metadata
                failed = bool(errors)
                failed_state = json.loads(json.dumps(self.state)) if failed else None
                draft_state = json.loads(json.dumps(self.state))
            _atomic_json(draft / "draft_state.json", draft_state)
            if failed_state is not None:
                archived_path = self._archive_failed_draft(failed_state)
                with self.lock:
                    self.state = {
                        **self._idle_state(),
                        "last_error": failed_state.get("error"),
                        "last_error_details": failed_state.get("error_details"),
                        "last_failed_recording_id": failed_state.get("recording_id"),
                        "last_failed_attempt_path": archived_path,
                        "gateway_close_confirmed": not any(
                            row.startswith("backend close error:") for row in errors
                        ),
                    }
            self.ready_event.set()

    def stop(self, *, timeout_seconds: float = 45.0) -> dict[str, Any]:
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
                raise RecorderError("Choose a declared manipulation skill label.")
            if outcome not in {"success", "failure", "correction", "unreviewed"}:
                raise RecorderError("Choose a valid outcome label.")
            destination = self.paths.recordings / f"{_slug(label)}__{self.state['recording_id']}"
            if destination.exists():
                raise RecorderConflict("A recording with this identity already exists.")
            destination.parent.mkdir(parents=True, exist_ok=True)
            samples = draft / "samples.jsonl"
            if not samples.is_file() or self.state["sample_count"] < 1:
                raise RecorderError("An empty recording cannot be saved.")
            privileged_state = draft / "evaluator_privileged_state.jsonl"
            if not privileged_state.is_file():
                raise RecorderError(
                    "The required evaluator-only state stream is incomplete."
                )
            initial_privileged_state = (
                draft / "initial_evaluator_privileged_state.json"
            )
            if not initial_privileged_state.is_file():
                raise RecorderError(
                    "The required initial evaluator-only state is incomplete."
                )
            try:
                source_rows = [
                    json.loads(line)
                    for line in samples.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
                if len(source_rows) != int(self.state["sample_count"]):
                    raise ValueError("sample count changed before finalization")
                for expected_index, row in enumerate(source_rows):
                    if self.state["mode"] == "physical_follower":
                        _validate_physical_source_row(row)
                    else:
                        validate_source_sample(row)
                    if int(row["sample_index"]) != expected_index:
                        raise ValueError("sample indices are not contiguous")
                    if self.state["mode"] != "physical_follower":
                        for stream in ("top", "wrist"):
                            reference = row["rgb"][stream]
                            frame_path = draft / str(reference["path"])
                            if not frame_path.is_file():
                                raise ValueError(f"missing {stream} RGB frame")
                            if _sha256(frame_path) != reference["sha256"]:
                                raise ValueError(f"{stream} RGB frame hash mismatch")
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                raise RecorderError(
                    f"Source recording validation failed; draft retained: {error}"
                ) from error
            overhead_state = dict(self.state.get("overhead_video") or {})
            overhead_video_name = str(
                overhead_state.get("video_path") or "overhead_c922.mp4"
            )
            overhead_browser_name = str(
                overhead_state.get("browser_video_path") or overhead_video_name
            )
            overhead_video = draft / overhead_video_name
            overhead_browser_video = draft / overhead_browser_name
            overhead_metadata = draft / "overhead_video.json"
            if not all(
                path.is_file()
                for path in (
                    overhead_video,
                    overhead_browser_video,
                    overhead_metadata,
                )
            ):
                raise RecorderError(
                    "The required C922 diagnostic video is incomplete; the draft was retained."
                )
            wrist_required = bool(self.state.get("wrist_video_required"))
            wrist_state = dict(self.state.get("wrist_video") or {})
            wrist_video_name = str(
                wrist_state.get("video_path") or "wrist_d405.mkv"
            )
            wrist_browser_name = str(
                wrist_state.get("browser_video_path") or "wrist_d405.browser.mp4"
            )
            wrist_video = draft / wrist_video_name
            wrist_browser_video = draft / wrist_browser_name
            wrist_metadata = draft / "wrist_video.json"
            if wrist_required and not all(
                path.is_file()
                for path in (wrist_video, wrist_browser_video, wrist_metadata)
            ):
                raise RecorderError(
                    "The required D405 wrist video is incomplete; the draft was retained."
                )
            shutil.move(str(draft), str(destination))
            video_receipt = {
                **overhead_state,
                "video_path": overhead_video_name,
                "video_sha256": _sha256(destination / overhead_video_name),
                "browser_video_path": overhead_browser_name,
                "browser_video_sha256": _sha256(
                    destination / overhead_browser_name
                ),
                "metadata_path": "overhead_video.json",
                "metadata_sha256": _sha256(destination / "overhead_video.json"),
                "ffmpeg_log_path": (
                    "overhead_c922.ffmpeg.log"
                    if (destination / "overhead_c922.ffmpeg.log").is_file()
                    else None
                ),
                "ffmpeg_log_sha256": (
                    _sha256(destination / "overhead_c922.ffmpeg.log")
                    if (destination / "overhead_c922.ffmpeg.log").is_file()
                    else None
                ),
                "diagnostic_only": True,
                "is_training_data": False,
            }
            wrist_video_receipt = (
                {
                    **wrist_state,
                    "video_path": wrist_video_name,
                    "video_sha256": _sha256(destination / wrist_video_name),
                    "browser_video_path": wrist_browser_name,
                    "browser_video_sha256": _sha256(
                        destination / wrist_browser_name
                    ),
                    "metadata_path": "wrist_video.json",
                    "metadata_sha256": _sha256(destination / "wrist_video.json"),
                    "ffmpeg_log_path": (
                        "wrist_d405.ffmpeg.log"
                        if (destination / "wrist_d405.ffmpeg.log").is_file()
                        else None
                    ),
                    "ffmpeg_log_sha256": (
                        _sha256(destination / "wrist_d405.ffmpeg.log")
                        if (destination / "wrist_d405.ffmpeg.log").is_file()
                        else None
                    ),
                    "diagnostic_only": True,
                    "metric_depth": False,
                    "is_training_data": False,
                }
                if wrist_required
                else None
            )
            receipt = {
                "schema_version": RECEIPT_SCHEMA,
                "source_episode_schema": EPISODE_SCHEMA,
                "source_sample_schema": (
                    PHYSICAL_SAMPLE_SCHEMA
                    if self.state["mode"] == "physical_follower"
                    else SAMPLE_SCHEMA
                ),
                "source_contract_sha256": self.state["source_contract_sha256"],
                "recording_id": self.state["recording_id"],
                "label": label,
                "skill": skill,
                "outcome_label": outcome,
                "notes": str(labels.get("notes") or "").strip(),
                "task_id": self.state["task_id"],
                "mode": self.state["mode"],
                "proof_class": self.state.get("backend", {}).get("proof_class"),
                "piece_id": self.state["piece_id"],
                "piece_type": "pawn",
                "piece_color": str(self.state["piece_id"]).split("_", 1)[0],
                "source_square": self.state["source_square"],
                "destination_square": self.state["target_square"],
                "initial_layout_id": CURRENT_TASK_LAYOUT_ID,
                "piece_layout": CURRENT_TASK_PIECE_LAYOUT,
                "scene_id": self.state["workcell_registration"][
                    "board_scene_id"
                ],
                "board_pose_id": self.state["workcell_registration"][
                    "board_pose_id"
                ],
                "workcell_registration": self.state["workcell_registration"],
                "target_square_operator_metadata": self.state["target_square"],
                "sample_hz": self.state["sample_hz"],
                "sample_count": self.state["sample_count"],
                "started_at": self.state["started_at"],
                "stopped_at": self.state["stopped_at"],
                "duration_seconds": self.state["duration_seconds"],
                "samples_path": "samples.jsonl",
                "samples_sha256": _sha256(destination / "samples.jsonl"),
                "evaluator_privileged_state_path": "evaluator_privileged_state.jsonl",
                "evaluator_privileged_state_sha256": _sha256(
                    destination / "evaluator_privileged_state.jsonl"
                ),
                "evaluator_privileged_state_policy_adapter_access": False,
                "initial_evaluator_privileged_state_path": "initial_evaluator_privileged_state.json",
                "initial_evaluator_privileged_state_sha256": _sha256(
                    destination / "initial_evaluator_privileged_state.json"
                ),
                "rgb_streams": (
                    None
                    if self.state["mode"] == "physical_follower"
                    else tree_manifest(destination / "rgb")
                ),
                "state_trace_path": (
                    "state_trace.json" if (destination / "state_trace.json").is_file() else None
                ),
                "state_trace_sha256": (
                    _sha256(destination / "state_trace.json")
                    if (destination / "state_trace.json").is_file()
                    else None
                ),
                "overhead_video": video_receipt,
                "wrist_video": wrist_video_receipt,
                "diagnostic_video_streams": {
                    "overhead_workspace": {
                        "receipt_field": "overhead_video",
                        "available": True,
                        "source_path": overhead_video_name,
                        "browser_path": overhead_browser_name,
                    },
                    "wrist_gripper_upward": {
                        "receipt_field": "wrist_video",
                        "available": wrist_video_receipt is not None,
                        "source_path": (
                            wrist_video_name
                            if wrist_video_receipt is not None
                            else None
                        ),
                        "browser_path": (
                            wrist_browser_name
                            if wrist_video_receipt is not None
                            else None
                        ),
                    },
                },
                "native_common_camera_session": self.state.get(
                    "native_common_camera_session"
                ),
                "backend": self.state.get("backend"),
                "scene_reset_seed": self.state["scene_reset_seed"],
                "language_instruction": self.state["language_instruction"],
                "source_identity": self.state["source_identity"],
                "model_identity": self.state["model_identity"],
                "checkpoint_identity": self.state["checkpoint_identity"],
                "action_owner": self.state["action_owner"],
                "assistance_frames": self.state["assistance_frames"],
                "intervention_frames": self.state["intervention_frames"],
                "lineage": self.state["lineage"],
                "execution": {
                    "action_representation": "absolute_joint_position_target",
                    "action_dtype": "float32_replay_required",
                    "sample_hold_hz": 20,
                    "physics_timestep_seconds": 0.005,
                    "physics_steps_per_action": 10,
                },
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
                self.stop(timeout_seconds=45.0)
            except RecorderError:
                self.stop_event.set()
        with self.lock:
            self.live_simulation["active"] = False

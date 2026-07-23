"""Leased, loopback-only live inspection for Studio.

The service owns no task or promotion authority. Camera processes exist only
while a browser consumes their HTTP responses. Physical joint observations use
the reviewed gateway in torque-off mode unless the recorder already owns the
bus, then project those joints through MuJoCo forward kinematics for display.
"""

from __future__ import annotations

import json
import secrets
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable

import mujoco
import numpy as np

from .overhead_video import OverheadVideoError, list_avfoundation_cameras
from .physical_gateway import GatewayIdentity, SO101PhysicalGateway
from .physical_sim_replay import physical_values_to_sim
from .scene import (
    CURRENT_TASK_PIECE_LAYOUT,
    ROBOT_JOINTS,
    build_scene_spec,
    initialize_robot_poses,
)
from .state_trace import build_scene_manifest


LIVE_WORKSPACE_SCHEMA = "sim2claw.live_workspace.v1"
LIVE_ARM_SCHEMA = "sim2claw.live_arm_observation.v1"
LIVE_CAMERA_SCHEMA = "sim2claw.live_camera_inventory.v1"
LIVE_SESSION_TTL_SECONDS = 5.0
CAMERA_DISCOVERY_TTL_SECONDS = 10.0
MJPEG_BOUNDARY = "sim2claw"


class LiveWorkspaceError(RuntimeError):
    """Expected operator-facing live-inspection failure."""


@dataclass(frozen=True)
class LiveCameraSpec:
    id: str
    label: str
    role: str
    name_contains: str
    detail: str
    pixel_format: str
    input_fps: int
    input_size: str
    video_filter: str
    metric_depth: bool = False

    def matches(self, name: str) -> bool:
        return self.name_contains.casefold() in name.casefold()


LIVE_CAMERAS = (
    LiveCameraSpec(
        id="d405-wrist",
        label="D405 wrist",
        role="wrist_depth_display",
        name_contains="RealSense(TM) Depth Camera 405  Depth",
        detail="Wrist-mounted AVFoundation display stream",
        pixel_format="uyvy422",
        input_fps=30,
        input_size="640x480",
        video_filter="fps=10,scale=640:-2",
        # This browser preview is a display stream. It does not expose or prove
        # metric depth, intrinsics, or the camera-to-gripper transform.
        metric_depth=False,
    ),
    LiveCameraSpec(
        id="logitech-overhead",
        label="Logitech overhead",
        role="overhead_workspace",
        name_contains="C922 Pro Stream Webcam",
        detail="Board and arm overview · operator-requested orientation",
        pixel_format="nv12",
        input_fps=30,
        input_size="640x480",
        # The prior preview used hflip+vflip. The operator requested another
        # 180-degree turn, so this path now preserves the native orientation.
        video_filter="fps=10,scale=640:-2",
    ),
    LiveCameraSpec(
        id="logitech-workspace",
        label="Logitech workspace",
        role="side_workspace",
        name_contains="USB Camera VID:1133 PID:2075",
        detail="Wide workcell context",
        pixel_format="uyvy422",
        input_fps=30,
        input_size="640x480",
        video_filter="fps=10,scale=640:-2",
    ),
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _camera_rows(
    detected: list[dict[str, Any]],
    *,
    error: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in LIVE_CAMERAS:
        selected = next(
            (camera for camera in detected if spec.matches(str(camera.get("name") or ""))),
            None,
        )
        rows.append(
            {
                "id": spec.id,
                "label": spec.label,
                "role": spec.role,
                "detail": spec.detail,
                "available": selected is not None,
                "device_name": selected.get("name") if selected else None,
                "device_index": int(selected["index"]) if selected else None,
                "preview_fps": 10,
                "metric_depth": spec.metric_depth,
                "stream_on_demand": True,
                "error": None if selected else error or "Expected camera was not detected.",
            }
        )
    return rows


def discover_live_cameras(*, ffmpeg_path: str | None = None) -> dict[str, Any]:
    """Map the three expected physical cameras to current AVFoundation indexes."""

    try:
        discovery = list_avfoundation_cameras(ffmpeg_path=ffmpeg_path)
    except OverheadVideoError as error:
        return {
            "schema_version": LIVE_CAMERA_SCHEMA,
            "checked_at": _utc_now(),
            "ffmpeg_path": ffmpeg_path or shutil.which("ffmpeg"),
            "cameras": _camera_rows([], error=str(error)),
            "error": str(error),
        }
    return {
        "schema_version": LIVE_CAMERA_SCHEMA,
        "checked_at": _utc_now(),
        "ffmpeg_path": discovery["ffmpeg_path"],
        "cameras": _camera_rows(discovery["cameras"]),
        "error": None,
    }


class PhysicalPoseMirror:
    """Project observed follower joints into the current MuJoCo visual scene."""

    def __init__(self) -> None:
        self.model = build_scene_spec(piece_layout=CURRENT_TASK_PIECE_LAYOUT).compile()
        self.data = mujoco.MjData(self.model)
        initialize_robot_poses(self.model, self.data)
        mujoco.mj_forward(self.model, self.data)
        self.manifest = build_scene_manifest(
            piece_layout=CURRENT_TASK_PIECE_LAYOUT,
            model=self.model,
        )
        self.body_names = [
            mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_BODY, body_id)
            or ("world" if body_id == 0 else f"body-{body_id}")
            for body_id in range(self.model.nbody)
        ]
        self.actuator_ids: list[int] = []
        self.qpos_addresses: list[int] = []
        for joint in ROBOT_JOINTS:
            name = f"left_{joint}"
            actuator_id = mujoco.mj_name2id(
                self.model, mujoco.mjtObj.mjOBJ_ACTUATOR, name
            )
            joint_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, name)
            if actuator_id < 0 or joint_id < 0:
                raise LiveWorkspaceError(f"Current simulator is missing {name}.")
            self.actuator_ids.append(actuator_id)
            self.qpos_addresses.append(int(self.model.jnt_qposadr[joint_id]))
        self.bounds = self.model.actuator_ctrlrange[self.actuator_ids].copy()
        self.frame_index = -1
        self.started = time.monotonic()

    def snapshot(
        self,
        follower_degrees: list[float],
        *,
        pose_source: str,
    ) -> dict[str, Any]:
        converted = physical_values_to_sim(follower_degrees, self.bounds[-1])
        clipped = np.clip(converted, self.bounds[:, 0], self.bounds[:, 1])
        self.data.qpos[self.qpos_addresses] = clipped
        self.data.ctrl[self.actuator_ids] = clipped
        self.data.time = max(0.0, time.monotonic() - self.started)
        mujoco.mj_forward(self.model, self.data)
        self.frame_index += 1
        revision = self.manifest["revision_sha256"]
        return {
            "active": True,
            "scene_url": (
                f"/api/scene?layout={CURRENT_TASK_PIECE_LAYOUT}&revision={revision}"
            ),
            "manifest_revision_sha256": revision,
            "body_names": self.body_names,
            "frame_index": self.frame_index,
            "frame": {
                "t": round(float(self.data.time), 6),
                "phase": "physical_joint_mirror",
                "p": np.asarray(self.data.xpos, dtype=np.float64)
                .reshape(-1)
                .astype(float)
                .tolist(),
                "q": np.asarray(self.data.xquat, dtype=np.float64)
                .reshape(-1)
                .astype(float)
                .tolist(),
                # Forward kinematics does not establish physical contact state.
                "c": [],
            },
            "joint_projection_clamped": bool(np.any(np.abs(converted - clipped) > 1e-9)),
            "authority": {
                "pose_source": pose_source,
                "projection": "observed_physical_joints_through_mujoco_forward_kinematics",
                "browser_renderer": "inspection_only",
                "physical_contact_state": "not_observed",
                "physical_authority": False,
            },
        }


GatewayFactory = Callable[..., SO101PhysicalGateway]
PopenFactory = Callable[..., subprocess.Popen[bytes]]
RunFactory = Callable[..., subprocess.CompletedProcess[bytes]]


class LiveWorkspaceService:
    """Own leased camera processes and one torque-off telemetry session."""

    def __init__(
        self,
        recorder: Any,
        *,
        camera_discovery: Callable[[], dict[str, Any]] = discover_live_cameras,
        gateway_factory: GatewayFactory = SO101PhysicalGateway,
        popen_factory: PopenFactory = subprocess.Popen,
        run_factory: RunFactory = subprocess.run,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.recorder = recorder
        self.camera_discovery = camera_discovery
        self.gateway_factory = gateway_factory
        self.popen_factory = popen_factory
        self.run_factory = run_factory
        self.clock = clock
        self.lock = threading.RLock()
        self.leases: dict[str, float] = {}
        self.gateway: SO101PhysicalGateway | None = None
        self.gateway_report: dict[str, Any] | None = None
        self.gateway_error: str | None = None
        self.mirror: PhysicalPoseMirror | None = None
        self.last_arm_sample: dict[str, Any] | None = None
        self.last_arm_sample_monotonic: float | None = None
        self.camera_cache: dict[str, Any] | None = None
        self.camera_cache_monotonic: float | None = None
        self.camera_processes: dict[int, subprocess.Popen[bytes]] = {}
        self.camera_process_ids: dict[int, str] = {}
        self.snapshot_camera_ids: set[str] = set()
        self.stop_event = threading.Event()
        self.reaper = threading.Thread(
            target=self._reap_loop,
            name="sim2claw-live-workspace-reaper",
            daemon=True,
        )
        self.reaper.start()

    def _recorder_state(self) -> dict[str, Any]:
        with self.recorder.lock:
            return json.loads(json.dumps(self.recorder.state))

    def _preflight(self) -> dict[str, Any]:
        return self.recorder.preflight()

    def _camera_inventory(self, *, refresh: bool = False) -> dict[str, Any]:
        now = self.clock()
        cache_ttl = CAMERA_DISCOVERY_TTL_SECONDS
        if self.camera_cache is not None:
            cameras = self.camera_cache.get("cameras") or []
            if self.camera_cache.get("error") or not any(
                bool(camera.get("available")) for camera in cameras
            ):
                cache_ttl = 2.0
        stale = (
            self.camera_cache is None
            or self.camera_cache_monotonic is None
            or now - self.camera_cache_monotonic >= cache_ttl
        )
        if refresh or stale:
            self.camera_cache = self.camera_discovery()
            # Discovery can take several seconds on AVFoundation. Age the
            # inventory from completion, not from before the ffmpeg probe.
            self.camera_cache_monotonic = self.clock()
        return json.loads(json.dumps(self.camera_cache))

    @staticmethod
    def _identity(preflight: dict[str, Any]) -> GatewayIdentity:
        devices = preflight["devices"]
        calibrations = preflight["calibrations"]
        values = (
            devices["leader"].get("port"),
            devices["follower"].get("port"),
            calibrations["leader"].get("sha256"),
            calibrations["follower"].get("sha256"),
        )
        if not all(values):
            raise LiveWorkspaceError("Physical gateway identity is incomplete.")
        return GatewayIdentity(*[str(value) for value in values])

    def _close_gateway(self) -> None:
        gateway = self.gateway
        self.gateway = None
        self.gateway_report = None
        if gateway is None:
            return
        try:
            gateway.close()
        except Exception as error:
            self.gateway_error = f"Telemetry shutdown reported: {error}"

    def _ensure_gateway(self, preflight: dict[str, Any]) -> None:
        if self.gateway is not None:
            return
        if not preflight["modes"]["physical_follower"]["ready"]:
            return
        recorder_state = self._recorder_state()
        if recorder_state.get("status") in {"starting", "recording", "stopping"}:
            return
        gateway: SO101PhysicalGateway | None = None
        try:
            gateway = self.gateway_factory(
                self._identity(preflight),
                configure_devices=False,
            )
            report = gateway.open(enable_motion=False)
        except Exception as error:
            if gateway is not None:
                try:
                    gateway.close()
                except Exception:
                    pass
            self.gateway_error = str(error)
            return
        self.gateway = gateway
        self.gateway_report = report
        self.gateway_error = None

    def _cleanup_expired(self) -> None:
        now = self.clock()
        self.leases = {
            token: expires for token, expires in self.leases.items() if expires > now
        }
        if not self.leases:
            processes = list(self.camera_processes.values())
            self.camera_processes.clear()
            self.camera_process_ids.clear()
            self._close_gateway()
            for process in processes:
                self._stop_process(process)

    def _reap_loop(self) -> None:
        while not self.stop_event.wait(0.5):
            with self.lock:
                self._cleanup_expired()

    def start_session(self) -> dict[str, Any]:
        with self.lock:
            self._cleanup_expired()
            token = secrets.token_urlsafe(24)
            self.leases[token] = self.clock() + LIVE_SESSION_TTL_SECONDS
            preflight = self._preflight()
            self._ensure_gateway(preflight)
            # A cold serial gateway handshake can itself exceed the nominal
            # lease. Begin the browser-facing lease after that handshake.
            self.leases[token] = self.clock() + LIVE_SESSION_TTL_SECONDS
            payload = self._snapshot_locked(token, preflight=preflight, sample=True)
            payload["session_id"] = token
            payload["lease_ttl_seconds"] = LIVE_SESSION_TTL_SECONDS
            return payload

    def _renew(self, token: str) -> None:
        if token not in self.leases:
            raise LiveWorkspaceError("The live workspace lease expired; reopen Live.")
        self.leases[token] = self.clock() + LIVE_SESSION_TTL_SECONDS

    def end_session(self, token: str) -> dict[str, Any]:
        with self.lock:
            self.leases.pop(token, None)
            if not self.leases:
                self.release_hardware(clear_sessions=False)
            return {
                "schema_version": LIVE_WORKSPACE_SCHEMA,
                "active": False,
                "physical_authority": False,
            }

    def _sample_arm(self, recorder_state: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        last_sample = recorder_state.get("last_sample") or {}
        active_physical = (
            recorder_state.get("mode") == "physical_follower"
            and recorder_state.get("status") in {"starting", "recording", "stopping"}
            and last_sample.get("follower_actual_position_degrees") is not None
        )
        if active_physical:
            return (
                {
                    "schema_version": LIVE_ARM_SCHEMA,
                    "leader_degrees": last_sample.get("leader_target_degrees"),
                    "follower_degrees": last_sample["follower_actual_position_degrees"],
                    "physical_follower_torque_enabled": bool(
                        last_sample.get("physical_follower_torque_enabled")
                    ),
                    "physical_motion_commanded": True,
                },
                "physical_recorder_follower_observation",
            )
        if self.gateway is None:
            return None, "no_fresh_physical_joint_observation"
        try:
            return (
                self.gateway.sample_read_only(),
                "physical_gateway_torque_off_joint_observation",
            )
        except Exception as error:
            self.gateway_error = str(error)
            self._close_gateway()
            return None, "physical_gateway_read_failed"

    def _snapshot_locked(
        self,
        token: str | None,
        *,
        preflight: dict[str, Any] | None = None,
        sample: bool,
    ) -> dict[str, Any]:
        self._cleanup_expired()
        if token is not None:
            self._renew(token)
        preflight = preflight or self._preflight()
        recorder_state = self._recorder_state()
        connected = bool(preflight["modes"]["physical_follower"]["ready"])
        pose_source = "no_fresh_physical_joint_observation"
        if token is not None and sample and connected:
            if self.gateway is None:
                self._ensure_gateway(preflight)
            arm_sample, pose_source = self._sample_arm(recorder_state)
            if arm_sample is not None:
                self.last_arm_sample = arm_sample
                self.last_arm_sample_monotonic = self.clock()

        age = (
            self.clock() - self.last_arm_sample_monotonic
            if self.last_arm_sample_monotonic is not None
            else None
        )
        fresh = bool(token and self.last_arm_sample is not None and age is not None and age < 1.0)
        status = (
            "live"
            if fresh
            else "error"
            if connected and self.gateway_error
            else "connected"
            if connected
            else "offline"
        )
        arm = {
            "schema_version": LIVE_ARM_SCHEMA,
            "status": status,
            "connected": connected,
            "fresh": fresh,
            "sample_age_seconds": round(age, 3) if age is not None else None,
            "pose_source": pose_source,
            "joint_names": list(ROBOT_JOINTS),
            "leader_port": preflight["devices"]["leader"].get("port"),
            "follower_port": preflight["devices"]["follower"].get("port"),
            "follower_degrees": (
                self.last_arm_sample.get("follower_degrees")
                if fresh and self.last_arm_sample
                else None
            ),
            "leader_degrees": (
                self.last_arm_sample.get("leader_degrees")
                if fresh and self.last_arm_sample
                else None
            ),
            "physical_follower_torque_enabled": (
                bool(self.last_arm_sample.get("physical_follower_torque_enabled"))
                if fresh and self.last_arm_sample
                else False
            ),
            "physical_motion_commanded": (
                bool(self.last_arm_sample.get("physical_motion_commanded"))
                if fresh and self.last_arm_sample
                else False
            ),
            "error": self.gateway_error,
        }
        simulator = None
        if fresh and arm["follower_degrees"] is not None:
            if self.mirror is None:
                self.mirror = PhysicalPoseMirror()
            simulator = self.mirror.snapshot(
                arm["follower_degrees"],
                pose_source=pose_source,
            )
        inventory = self._camera_inventory()
        active_counts: dict[str, int] = {}
        for camera_id in self.camera_process_ids.values():
            active_counts[camera_id] = active_counts.get(camera_id, 0) + 1
        for camera in inventory["cameras"]:
            camera["active_streams"] = active_counts.get(camera["id"], 0)
        if token is not None:
            # Gateway reads, first-time MuJoCo compilation, and AVFoundation
            # discovery can together exceed one lease window. Renew from the
            # completed observation so the browser receives a usable token.
            self.leases[token] = self.clock() + LIVE_SESSION_TTL_SECONDS
        return {
            "schema_version": LIVE_WORKSPACE_SCHEMA,
            "checked_at": _utc_now(),
            "active": token is not None,
            "arm": arm,
            "simulator": simulator,
            "cameras": inventory,
            "recorder": {
                "status": recorder_state.get("status"),
                "mode": recorder_state.get("mode"),
                "owns_c922": recorder_state.get("overhead_video", {}).get("status")
                == "recording",
            },
            "authority": {
                "inspection_only": True,
                "physical_motion_endpoint": False,
                "physical_authority": False,
            },
        }

    def snapshot(self, token: str | None = None, *, sample: bool = False) -> dict[str, Any]:
        with self.lock:
            return self._snapshot_locked(token, sample=sample)

    def _camera_spec_and_row(
        self, camera_id: str
    ) -> tuple[LiveCameraSpec, dict[str, Any], dict[str, Any]]:
        spec = next((item for item in LIVE_CAMERAS if item.id == camera_id), None)
        if spec is None:
            raise LiveWorkspaceError("Unknown live camera.")
        # Re-enumerate only when the short cache is stale. A single Live Feed
        # click opens three HTTP requests; forcing discovery per request would
        # serialize three ffmpeg probes before any preview could appear.
        inventory = self._camera_inventory()
        row = next(item for item in inventory["cameras"] if item["id"] == camera_id)
        if not row["available"] or row["device_index"] is None:
            raise LiveWorkspaceError(row["error"] or "The requested camera is unavailable.")
        return spec, row, inventory

    def camera_source_status(self, camera_id: str) -> dict[str, Any]:
        """Return a bounded source preflight without opening a camera stream."""

        with self.lock:
            try:
                _spec, row, _inventory = self._camera_spec_and_row(camera_id)
            except LiveWorkspaceError as error:
                return {
                    "camera_id": camera_id,
                    "ready": False,
                    "available": False,
                    "reason": str(error),
                    "physical_authority": False,
                }
            recorder_state = self._recorder_state()
            recorder_owns_source = (
                camera_id == "logitech-overhead"
                and recorder_state.get("overhead_video", {}).get("status") == "recording"
            )
            stream_owns_source = camera_id in self.camera_process_ids.values()
            snapshot_active = camera_id in self.snapshot_camera_ids
            busy = recorder_owns_source or stream_owns_source or snapshot_active
            return {
                "camera_id": camera_id,
                "label": row["label"],
                "role": row["role"],
                "ready": bool(row["available"] and not busy),
                "available": bool(row["available"]),
                "device_name": row.get("device_name"),
                "device_index": row.get("device_index"),
                "busy": busy,
                "busy_owner": (
                    "recorder"
                    if recorder_owns_source
                    else "live_preview"
                    if stream_owns_source
                    else "orchestrator_snapshot"
                    if snapshot_active
                    else None
                ),
                "reason": (
                    "The overhead camera is currently owned by another Studio surface."
                    if busy
                    else row.get("error")
                ),
                "physical_authority": False,
            }

    def orchestrator_inventory(self) -> dict[str, Any]:
        """Expose only the hardware this orchestrator is allowed to consume."""

        with self.lock:
            preflight = self._preflight()
            inventory = self._camera_inventory()
            overhead = next(
                (
                    row
                    for row in inventory.get("cameras", [])
                    if row.get("id") == "logitech-overhead"
                ),
                {
                    "id": "logitech-overhead",
                    "label": "Logitech overhead",
                    "role": "overhead_workspace",
                },
            )
            source = self.camera_source_status("logitech-overhead")
            devices = preflight.get("devices") or {}
            return {
                "schema_version": "sim2claw.orchestrator_workcell_inventory.v1",
                "checked_at": inventory.get("checked_at"),
                "arms": [
                    {
                        "id": "so101-follower",
                        "role": "follower",
                        **dict(devices.get("follower") or {}),
                        "motion_authority": False,
                    },
                ],
                "cameras": [
                    {
                        **overhead,
                        **source,
                        "primary_for_orchestrator": True,
                    }
                ],
                "primary_camera_id": "logitech-overhead",
                "physical_authority": False,
            }

    def capture_camera_snapshot(self, camera_id: str) -> dict[str, Any]:
        """Capture one JPEG through the same stable AVFoundation camera role."""

        with self.lock:
            source = self.camera_source_status(camera_id)
            if not source["ready"]:
                raise LiveWorkspaceError(source.get("reason") or "Camera source is unavailable.")
            spec, row, inventory = self._camera_spec_and_row(camera_id)
            ffmpeg = inventory.get("ffmpeg_path") or shutil.which("ffmpeg")
            if not ffmpeg:
                raise LiveWorkspaceError("ffmpeg is unavailable for overhead snapshots.")
            self.snapshot_camera_ids.add(camera_id)
            command = [
                str(ffmpeg),
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "avfoundation",
                "-pixel_format",
                spec.pixel_format,
                "-framerate",
                str(spec.input_fps),
                "-video_size",
                spec.input_size,
                "-i",
                f"{row['device_index']}:none",
                "-an",
                "-frames:v",
                "1",
                "-c:v",
                "mjpeg",
                "-q:v",
                "3",
                "-f",
                "image2pipe",
                "pipe:1",
            ]
        started = self.clock()
        try:
            result = self.run_factory(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise LiveWorkspaceError(f"Overhead snapshot failed: {error}") from error
        finally:
            with self.lock:
                self.snapshot_camera_ids.discard(camera_id)
        if result.returncode != 0 or not result.stdout:
            detail = result.stderr.decode("utf-8", errors="replace").strip()[-500:]
            raise LiveWorkspaceError(
                f"Overhead snapshot process failed{': ' + detail if detail else '.'}"
            )
        return {
            "schema_version": "sim2claw.local_camera_snapshot.v1",
            "camera_id": camera_id,
            "camera_role": spec.role,
            "device_name": row.get("device_name"),
            "device_index": row.get("device_index"),
            "captured_at": _utc_now(),
            "fetch_duration_ms": round((self.clock() - started) * 1000.0, 3),
            "content_type": "image/jpeg",
            "body": bytes(result.stdout),
            "physical_authority": False,
        }

    def open_camera(
        self,
        camera_id: str,
        token: str,
    ) -> subprocess.Popen[bytes]:
        with self.lock:
            self._cleanup_expired()
            self._renew(token)
            if camera_id in self.snapshot_camera_ids:
                raise LiveWorkspaceError(
                    "The orchestrator currently owns this camera for one snapshot."
                )
            recorder_state = self._recorder_state()
            if (
                camera_id == "logitech-overhead"
                and recorder_state.get("overhead_video", {}).get("status") == "recording"
            ):
                raise LiveWorkspaceError(
                    "The recorder currently owns the overhead C922 capture."
                )
            spec, row, inventory = self._camera_spec_and_row(camera_id)
            ffmpeg = inventory.get("ffmpeg_path") or shutil.which("ffmpeg")
            if not ffmpeg:
                raise LiveWorkspaceError("ffmpeg is unavailable for live preview.")
            command = [
                str(ffmpeg),
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "avfoundation",
                "-pixel_format",
                spec.pixel_format,
                "-framerate",
                str(spec.input_fps),
                "-video_size",
                spec.input_size,
                "-i",
                f"{row['device_index']}:none",
                "-an",
                "-vf",
                spec.video_filter,
                "-c:v",
                "mjpeg",
                "-q:v",
                "5",
                "-f",
                "mpjpeg",
                "-boundary_tag",
                MJPEG_BOUNDARY,
                "pipe:1",
            ]
            process = self.popen_factory(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            self.camera_processes[id(process)] = process
            self.camera_process_ids[id(process)] = camera_id
            self.leases[token] = self.clock() + LIVE_SESSION_TTL_SECONDS
            return process

    def close_camera(self, process: subprocess.Popen[bytes]) -> None:
        with self.lock:
            self.camera_processes.pop(id(process), None)
            self.camera_process_ids.pop(id(process), None)
        self._stop_process(process)

    @staticmethod
    def _stop_process(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1.0)

    def release_hardware(self, *, clear_sessions: bool = True) -> None:
        with self.lock:
            processes = list(self.camera_processes.values())
            self.camera_processes.clear()
            self.camera_process_ids.clear()
            self._close_gateway()
            if clear_sessions:
                self.leases.clear()
        for process in processes:
            self._stop_process(process)

    def shutdown(self) -> None:
        self.stop_event.set()
        self.release_hardware(clear_sessions=True)
        if self.reaper.is_alive():
            self.reaper.join(timeout=1.0)

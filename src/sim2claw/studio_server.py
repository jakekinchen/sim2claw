"""Dependency-free, loopback-first HTTP server for the sim2claw studio."""

from __future__ import annotations

import ipaddress
import hashlib
import json
import mimetypes
import re
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from .paths import REPO_ROOT
from .demo_loop_controller import DemoLoopController
from .owner_directed_base_loop import OwnerDirectedLoopError
from .learning_factory import LearningFactoryError
from .learning_factory_studio import DEFAULT_FACTORY_PROJECT, build_factory_navigation
from .orchestrator_frames import LocalOverheadSnapshotAdapter
from .physical_gateway import PhysicalGatewayError
from .studio_catalog import build_catalog, open_media_token
from .studio_live import LiveWorkspaceError, LiveWorkspaceService, MJPEG_BOUNDARY
from .studio_project_map import StudioProjectMapError, build_project_map
from .studio_twin_fidelity import load_twin_fidelity_projection
from .twin_fidelity_closure import (
    TwinFidelityClosureError,
    evaluate_twin_fidelity_closure,
)
from .state_trace import build_scene_manifest
from .task_orchestrator import TaskOrchestratorError, TaskOrchestratorService
from .teleop_recording import (
    RECEIPT_SCHEMA as TELEOP_RECEIPT_SCHEMA,
    RecorderConflict,
    RecorderError,
    TeleopRecordingManager,
)
from .scene import CURRENT_TASK_PIECE_LAYOUT
from .paths import SO101_MODEL_PATH
from .sail.studio import (
    StudioObservatoryError,
    load_studio_observatory,
    open_studio_figure,
)


STATIC_ROOT = Path(__file__).with_name("studio_web")
SCENE_ASSET_ROOT = SO101_MODEL_PATH.parent / "assets"
RANGE_PATTERN = re.compile(r"bytes=(\d*)-(\d*)$")
SCENE_SYNTHESIS_API_SCHEMA = "sim2claw.studio_scene_synthesis_proposal.v1"
DEFAULT_SCENE_SYNTHESIS_CONFIG = (
    REPO_ROOT / "configs" / "scenes" / "robo_scanner_llm_workcell_v1.json"
)
SUPERVISED_REPLAY_RECORDING_ID = "20260719T032315Z-d3c3cf0b"


def latest_supervised_replay(repo_root: Path) -> dict[str, Any] | None:
    """Expose the newest fully bound historical replay without promoting it."""

    source_root = (repo_root / "datasets" / "manipulation_source_recordings").resolve()
    source_bindings: dict[str, str] = {}
    for source_receipt_path in sorted(source_root.glob("*/recording_receipt.json")):
        try:
            source_receipt = json.loads(source_receipt_path.read_text(encoding="utf-8"))
            source_samples = source_receipt_path.with_name("samples.jsonl")
            source_samples_sha256 = hashlib.sha256(source_samples.read_bytes()).hexdigest()
        except (OSError, json.JSONDecodeError):
            continue
        if (
            source_receipt.get("schema_version") != TELEOP_RECEIPT_SCHEMA
            or source_receipt.get("samples_sha256") != source_samples_sha256
        ):
            continue
        source_bindings[str(source_receipt.get("recording_id") or "")] = (
            source_samples_sha256
        )

    receipt_paths = sorted(
        (repo_root / "runs" / "physical_replays").glob("*/replay_receipt.json"),
        reverse=True,
    )
    for receipt_path in receipt_paths:
        try:
            receipt_bytes = receipt_path.read_bytes()
            receipt = json.loads(receipt_bytes)
        except (OSError, json.JSONDecodeError):
            continue
        recording_id = str(receipt.get("source_recording_id") or "")
        replay_samples_path = (
            receipt_path.parent / str(receipt.get("replay_samples_path") or "")
        ).resolve()
        try:
            replay_samples_sha256 = hashlib.sha256(
                replay_samples_path.read_bytes()
            ).hexdigest()
        except OSError:
            continue
        if (
            receipt.get("schema_version")
            != "sim2claw.physical_trace_replay_attempt.v1"
            or recording_id != SUPERVISED_REPLAY_RECORDING_ID
            or receipt.get("commands_requested_from_source_trace") is not True
            or receipt.get("task_success_verified") is not False
            or receipt.get("learned_policy_verified") is not False
            or receipt.get("physical_follower_torque_enabled") is not False
            or not replay_samples_path.is_relative_to(receipt_path.parent.resolve())
            or replay_samples_sha256 != receipt.get("replay_samples_sha256")
            or source_bindings.get(recording_id)
            != receipt.get("source_samples_sha256")
        ):
            continue
        return {
            "proof_class": "unqualified_physical_command_replay",
            "skill_id": "pawn_b2_to_b1",
            "source_square": "b2",
            "destination_square": "b1",
            "run_id": receipt.get("run_id"),
            "status": receipt.get("status"),
            "completed_at": receipt.get("completed_at"),
            "completed_sample_count": receipt.get("completed_sample_count"),
            "source_sample_count": receipt.get("source_sample_count"),
            "exact_command_sample_count": receipt.get("exact_command_sample_count"),
            "rate_limited_sample_count": receipt.get("safety_clamped_sample_count"),
            "torque_enabled_after": receipt.get(
                "physical_follower_torque_enabled"
            ),
            "task_success_verified": receipt.get("task_success_verified"),
            "learned_policy_verified": receipt.get("learned_policy_verified"),
            "failure_message": receipt.get("failure_message"),
            "receipt_path": receipt_path.relative_to(repo_root).as_posix(),
            "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
            "source_samples_sha256": receipt.get("source_samples_sha256"),
            "replay_samples_sha256": replay_samples_sha256,
            "physical_authority": False,
        }
    return None


def load_scene_synthesis_proposal(
    path: Path = DEFAULT_SCENE_SYNTHESIS_CONFIG,
) -> dict[str, Any]:
    """Load display-only scene analysis without changing MuJoCo identity."""

    raw = path.read_bytes()
    proposal = json.loads(raw)
    return {
        "schema_version": SCENE_SYNTHESIS_API_SCHEMA,
        "proposal_sha256": hashlib.sha256(raw).hexdigest(),
        "proposal": proposal,
        "authority": {
            "display_only": True,
            "included_in_mujoco_manifest_revision": False,
            "accepted_geometry_source": "mujoco_scene_manifest",
            "physical_authority": False,
        },
    }


class StudioServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        address: tuple[str, int],
        repo_root: Path = REPO_ROOT,
        *,
        read_only: bool = False,
        enable_physical_demo: bool = False,
    ):
        self.repo_root = repo_root.resolve()
        self.read_only = read_only
        try:
            self.recorder_control_enabled = (
                ipaddress.ip_address(address[0]).is_loopback and not read_only
            )
        except ValueError:
            self.recorder_control_enabled = address[0] == "localhost" and not read_only
        if enable_physical_demo and not self.recorder_control_enabled:
            raise ValueError(
                "The physical demo requires an interactive loopback Studio server."
            )
        self.physical_demo_enabled = bool(
            enable_physical_demo and self.recorder_control_enabled
        )
        self.recorder: TeleopRecordingManager | None = None
        self.live_workspace: LiveWorkspaceService | None = None
        self.task_orchestrator: TaskOrchestratorService | None = None
        self.demo_loop_controller: DemoLoopController | None = None
        if not read_only:
            self.recorder = TeleopRecordingManager(repo_root=self.repo_root)
            self.live_workspace = LiveWorkspaceService(self.recorder)
            if self.recorder_control_enabled:
                if self.physical_demo_enabled:
                    self.demo_loop_controller = DemoLoopController(
                        self.repo_root,
                        camera_capture=self.live_workspace.capture_camera_snapshot,
                    )
                self.task_orchestrator = TaskOrchestratorService(
                    repo_root=self.repo_root,
                    frame_adapter_factory=lambda: LocalOverheadSnapshotAdapter(
                        self.live_workspace.capture_camera_snapshot,
                        status=self.live_workspace.camera_source_status,
                        demo_visual_feedback=True,
                    ),
                    frame_source_metadata={
                        "adapter_id": LocalOverheadSnapshotAdapter.adapter_id,
                        "label": "Logitech overhead",
                        "host": "local-avfoundation",
                        "camera_id": LocalOverheadSnapshotAdapter.camera_id,
                        "camera_role": LocalOverheadSnapshotAdapter.camera_role,
                        "roi_contract_id": "local_overhead_demo_visual_v1",
                        "registration_state": "demo_visual_feedback",
                    },
                    frame_source_status=lambda: self.live_workspace.camera_source_status(
                        LocalOverheadSnapshotAdapter.camera_id
                    ),
                    workcell_status=self.live_workspace.orchestrator_inventory,
                    demo_loop_start=(
                        self.demo_loop_controller.start
                        if self.demo_loop_controller is not None
                        else None
                    ),
                    demo_loop_status=(
                        self.demo_loop_controller.snapshot
                        if self.demo_loop_controller is not None
                        else None
                    ),
                    demo_loop_stop=(
                        self.demo_loop_controller.request_stop
                        if self.demo_loop_controller is not None
                        else None
                    ),
                )
        self.scene_manifests: dict[str, dict[str, Any]] = {}
        self.scene_synthesis_proposal: dict[str, Any] | None = None
        super().__init__(address, StudioRequestHandler)

    def server_close(self) -> None:
        if self.task_orchestrator is not None:
            self.task_orchestrator.shutdown()
        if self.demo_loop_controller is not None:
            self.demo_loop_controller.shutdown()
        if self.live_workspace is not None:
            self.live_workspace.shutdown()
        if self.recorder is not None:
            self.recorder.shutdown()
        super().server_close()


class StudioRequestHandler(BaseHTTPRequestHandler):
    server: StudioServer
    protocol_version = "HTTP/1.1"

    def handle_one_request(self) -> None:
        """Treat an abandoned browser poll as a normal loopback disconnect."""

        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        request = urlsplit(self.path)
        path = unquote(request.path)
        if path == "/api/sail-observatory":
            try:
                self._send_json(
                    load_studio_observatory(repo_root=self.server.repo_root)
                )
            except (StudioObservatoryError, OSError, ValueError, json.JSONDecodeError) as error:
                self._send_json(
                    {
                        "available": False,
                        "read_only": True,
                        "physical_authority": False,
                        "error": str(error),
                    },
                    HTTPStatus.SERVICE_UNAVAILABLE,
                )
            return
        if path.startswith("/api/sail-observatory/figures/"):
            name = path.removeprefix("/api/sail-observatory/figures/")
            try:
                _, payload, digest = open_studio_figure(
                    name, repo_root=self.server.repo_root
                )
            except (StudioObservatoryError, OSError, ValueError, json.JSONDecodeError):
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self.send_response(HTTPStatus.OK)
            self._security_headers()
            self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("ETag", f'"{digest}"')
            self.send_header("Content-Disposition", f'inline; filename="{name}"')
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        if path == "/api/twin-fidelity":
            episode_id = parse_qs(request.query).get("episode_id", [""])[0]
            catalog = build_catalog(self.server.repo_root)
            episode = next(
                (
                    row
                    for row in catalog.get("episodes", [])
                    if isinstance(row, dict) and row.get("id") == episode_id
                ),
                None,
            )
            if episode is None:
                self._send_json(
                    {
                        "available": False,
                        "read_only": True,
                        "physical_authority": False,
                        "reason": "selected_episode_not_found",
                    },
                    HTTPStatus.NOT_FOUND,
                )
                return
            projection = load_twin_fidelity_projection(
                episode,
                repo_root=self.server.repo_root,
            )
            try:
                projection["closure"] = evaluate_twin_fidelity_closure(
                    repo_root=self.server.repo_root
                )
            except (
                TwinFidelityClosureError,
                OSError,
                ValueError,
                json.JSONDecodeError,
            ) as error:
                projection["closure"] = {
                    "schema_version": "sim2claw.twin_fidelity_closure_report.v1",
                    "available": False,
                    "status": "unavailable",
                    "perfect": False,
                    "detail": str(error),
                    "closure": {
                        "passed_required_domains": 0,
                        "required_domain_count": 6,
                        "weighted_percentage": None,
                        "unknown_counted_as_zero": False,
                    },
                    "domains": [],
                }
            self._send_json(projection)
            return
        if path == "/api/catalog":
            self._send_json(build_catalog(self.server.repo_root))
            return
        if path == "/api/project-map":
            try:
                self._send_json(
                    build_project_map(
                        repo_root=self.server.repo_root,
                        read_only=self.server.read_only,
                        recorder_control_enabled=self.server.recorder_control_enabled,
                        orchestrator_available=self.server.task_orchestrator is not None,
                    )
                )
            except (
                StudioProjectMapError,
                OSError,
                ValueError,
                json.JSONDecodeError,
            ) as error:
                self._send_json(
                    {
                        "schema_version": "sim2claw.studio_project_map.v1",
                        "available": False,
                        "read_only": True,
                        "physical_authority": False,
                        "error": str(error),
                    },
                    HTTPStatus.SERVICE_UNAVAILABLE,
                )
            return
        if path == "/api/learning-factory":
            declared_project = parse_qs(request.query).get(
                "project", [DEFAULT_FACTORY_PROJECT.as_posix()]
            )[0]
            try:
                self._send_json(
                    build_factory_navigation(
                        repo_root=self.server.repo_root,
                        project_path=Path(declared_project),
                    )
                )
            except (LearningFactoryError, OSError, ValueError) as error:
                self._send_json(
                    {"ok": False, "error": str(error)}, HTTPStatus.BAD_REQUEST
                )
            return
        if path == "/api/learning-factory/artifact":
            declared = parse_qs(request.query).get("path", [""])[0]
            try:
                candidate = (self.server.repo_root / declared).resolve()
                allowed_root = (
                    self.server.repo_root / "runs/learning-factory"
                ).resolve()
                if (
                    not declared
                    or Path(declared).is_absolute()
                    or ".." in Path(declared).parts
                    or not candidate.is_relative_to(allowed_root)
                    or candidate.suffix != ".json"
                    or not candidate.is_file()
                    or candidate.stat().st_size > 2 * 1024 * 1024
                ):
                    raise ValueError("artifact path is not an allowed factory JSON receipt")
                payload = json.loads(candidate.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("factory artifact is not a JSON object")
                self._send_json(
                    {
                        "schema_version": "sim2claw.studio_factory_artifact.v1",
                        "read_only": True,
                        "path": candidate.relative_to(self.server.repo_root).as_posix(),
                        "byte_count": candidate.stat().st_size,
                        "artifact": payload,
                    }
                )
            except (OSError, ValueError, json.JSONDecodeError) as error:
                self._send_json(
                    {"ok": False, "error": str(error)}, HTTPStatus.BAD_REQUEST
                )
            return
        if path == "/api/scene-synthesis":
            if self.server.scene_synthesis_proposal is None:
                self.server.scene_synthesis_proposal = load_scene_synthesis_proposal()
            self._send_json(self.server.scene_synthesis_proposal)
            return
        if path == "/api/orchestrator":
            if self.server.task_orchestrator is None:
                self._send_json(
                    {
                        "schema_version": "sim2claw.task_orchestrator_state.v1",
                        "available": False,
                        "reason": "Task Orchestrator control is available only on interactive loopback Studio.",
                        "physical_authority": False,
                    }
                )
                return
            payload = self.server.task_orchestrator.snapshot()
            payload["supervised_replay"] = latest_supervised_replay(
                self.server.repo_root
            )
            payload["available"] = True
            self._send_json(payload)
            return
        if path == "/api/orchestrator/frame":
            if self.server.task_orchestrator is None:
                self._send_json(
                    {"ok": False, "error": "Task Orchestrator is not available."},
                    HTTPStatus.NOT_FOUND,
                )
                return
            frame = self.server.task_orchestrator.frame_payload()
            if frame is None:
                self._send_json(
                    {"ok": False, "error": "No accepted orchestrator frame is available."},
                    HTTPStatus.NOT_FOUND,
                )
                return
            body, content_type, digest = frame
            self.send_response(HTTPStatus.OK)
            self._security_headers()
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("ETag", f'"{digest}"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        if path == "/api/scene":
            layout = parse_qs(request.query).get("layout", ["standard"])[0]
            if layout not in {"standard", CURRENT_TASK_PIECE_LAYOUT}:
                self._send_json(
                    {"ok": False, "error": "Unknown scene layout."},
                    HTTPStatus.BAD_REQUEST,
                )
                return
            if layout not in self.server.scene_manifests:
                self.server.scene_manifests[layout] = build_scene_manifest(
                    piece_layout=layout
                )
            self._send_json(self.server.scene_manifests[layout])
            return
        if path == "/api/recorder":
            if not self.server.recorder_control_enabled:
                self._send_json(
                    {"ok": False, "error": "Recorder state is available only on loopback."},
                    HTTPStatus.FORBIDDEN,
                )
                return
            self._send_json(self.server.recorder.snapshot())
            return
        if path == "/api/recorder/live-simulation":
            if not self.server.recorder_control_enabled:
                self._send_json(
                    {"ok": False, "error": "Live simulator state is available only on loopback."},
                    HTTPStatus.FORBIDDEN,
                )
                return
            self._send_json(self.server.recorder.live_simulation_snapshot())
            return
        if path == "/api/live/status":
            if not self.server.recorder_control_enabled:
                self._send_json(
                    {"ok": False, "error": "Live device state is available only on loopback."},
                    HTTPStatus.FORBIDDEN,
                )
                return
            self._send_json(self.server.live_workspace.snapshot())
            return
        if path == "/api/live/state":
            if not self.server.recorder_control_enabled:
                self._send_json(
                    {"ok": False, "error": "Live device state is available only on loopback."},
                    HTTPStatus.FORBIDDEN,
                )
                return
            token = parse_qs(request.query).get("session", [""])[0]
            try:
                self._send_json(
                    self.server.live_workspace.snapshot(token, sample=True)
                )
            except LiveWorkspaceError as error:
                self._send_json(
                    {"ok": False, "error": str(error)},
                    HTTPStatus.GONE,
                )
            return
        if path.startswith("/api/live/cameras/") and path.endswith(".mjpeg"):
            if not self.server.recorder_control_enabled:
                self._send_json(
                    {"ok": False, "error": "Live camera feeds are available only on loopback."},
                    HTTPStatus.FORBIDDEN,
                )
                return
            camera_id = path.removeprefix("/api/live/cameras/").removesuffix(".mjpeg")
            token = parse_qs(request.query).get("session", [""])[0]
            self._send_camera_stream(camera_id, token)
            return
        if path == "/api/health":
            self._send_json(
                {
                    "ok": True,
                    "service": "sim2claw-studio",
                    "mode": "read_only_evidence" if self.server.read_only else "interactive",
                    "read_only": self.server.read_only,
                    "physical_authority": False,
                    "physical_motion_endpoint": (
                        "operator_gated_relative_time_slew_bounded_tracking"
                    ),
                    "recorder_control": (
                        "loopback_only" if self.server.recorder_control_enabled else "disabled"
                    ),
                    "live_workspace": (
                        "loopback_on_demand"
                        if self.server.recorder_control_enabled
                        else "disabled"
                    ),
                }
            )
            return
        if path.startswith("/media/"):
            self._send_media(path.removeprefix("/media/"))
            return
        if path.startswith("/scene-assets/"):
            self._send_scene_asset(path.removeprefix("/scene-assets/"))
            return
        self._send_static(path)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = unquote(urlsplit(self.path).path)
        if not self.server.recorder_control_enabled:
            self._send_json(
                {"ok": False, "error": "Recorder control is available only on loopback."},
                HTTPStatus.FORBIDDEN,
                close_connection=True,
            )
            return
        if self.headers.get_content_type() != "application/json":
            self._send_json(
                {"ok": False, "error": "Recorder requests require application/json."},
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            )
            return
        try:
            payload = self._read_json_body()
            if path.startswith("/api/orchestrator"):
                orchestrator = self.server.task_orchestrator
                if orchestrator is None:
                    raise TaskOrchestratorError(
                        "Task Orchestrator is available only on interactive loopback Studio."
                    )
                if path == "/api/orchestrator/session":
                    action = str(payload.get("action") or "")
                    if action == "start":
                        result = orchestrator.start(payload)
                    elif action == "pause":
                        result = orchestrator.pause()
                    elif action == "resume":
                        result = orchestrator.resume()
                    elif action == "stop":
                        result = orchestrator.stop()
                    elif action == "configure":
                        result = orchestrator.configure(payload)
                    elif action == "acknowledge":
                        result = orchestrator.acknowledge(
                            str(payload.get("message") or "operator acknowledgement")
                        )
                    else:
                        raise TaskOrchestratorError("Unknown orchestrator session action.")
                elif path == "/api/orchestrator/chat":
                    result = orchestrator.chat(str(payload.get("message") or ""))
                elif path == "/api/orchestrator/demo":
                    controller = self.server.demo_loop_controller
                    if controller is None:
                        raise TaskOrchestratorError("The fixed demo controller is unavailable.")
                    current = orchestrator.snapshot()
                    if current.get("state") in {"STOPPED", "PAUSED", "PAUSING", "FAULTED"}:
                        raise TaskOrchestratorError(
                            "Power on a Demo Physical session before starting motion."
                        )
                    action = str(payload.get("action") or "")
                    if action == "stop":
                        controller.request_stop()
                    else:
                        controller.start_action(action)
                    result = orchestrator.snapshot()
                elif path == "/api/orchestrator/refresh":
                    result = orchestrator.refresh()
                elif path == "/api/orchestrator/preview":
                    result = orchestrator.preview_source()
                elif path == "/api/orchestrator/shadow-choice":
                    result = orchestrator.shadow_choice(
                        skill_id=(
                            str(payload.get("skill_id"))
                            if payload.get("skill_id") is not None
                            else None
                        ),
                        operator_identity=str(payload.get("operator_identity") or ""),
                        note=str(payload.get("note") or ""),
                    )
                else:
                    self._send_json(
                        {"ok": False, "error": "Unknown orchestrator endpoint."},
                        HTTPStatus.NOT_FOUND,
                    )
                    return
                self._send_json({"ok": True, "orchestrator": result})
                return
            if path == "/api/live/session":
                action = str(payload.get("action") or "start")
                if action == "start":
                    result = self.server.live_workspace.start_session()
                elif action == "stop":
                    result = self.server.live_workspace.end_session(
                        str(payload.get("session_id") or "")
                    )
                else:
                    raise LiveWorkspaceError("Unknown live workspace session action.")
                self._send_json({"ok": True, "live": result})
                return
            if path in {
                "/api/recorder/gateway-preflight",
                "/api/recorder/gateway-sync",
                "/api/recorder/start",
            }:
                # The recorder/gateway becomes the sole camera and bus owner.
                self.server.live_workspace.release_hardware(clear_sessions=True)
            if path == "/api/recorder/preflight":
                result = self.server.recorder.snapshot()
            elif path == "/api/recorder/gateway-preflight":
                result = self.server.recorder.verify_physical_gateway()
            elif path == "/api/recorder/gateway-sync":
                result = self.server.recorder.synchronize_physical_gateway(payload)
            elif path == "/api/recorder/start":
                result = self.server.recorder.start(payload)
            elif path == "/api/recorder/stop":
                result = self.server.recorder.stop()
            elif path == "/api/recorder/finalize":
                result = self.server.recorder.finalize(payload)
            elif path == "/api/recorder/discard":
                result = self.server.recorder.discard()
            elif path == "/api/recorder/sim-replay":
                result = self.server.recorder.replay_saved_in_simulator()
            else:
                self._send_json(
                    {"ok": False, "error": "Unknown recorder endpoint."},
                    HTTPStatus.NOT_FOUND,
                )
                return
        except RecorderConflict as error:
            self._send_json({"ok": False, "error": str(error)}, HTTPStatus.CONFLICT)
            return
        except (
            RecorderError,
            PhysicalGatewayError,
            LiveWorkspaceError,
            TaskOrchestratorError,
            OwnerDirectedLoopError,
            ConnectionError,
            OSError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            self._send_json({"ok": False, "error": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        except Exception as error:  # keep loopback UI requests intact on unexpected faults
            self._send_json(
                {
                    "ok": False,
                    "error": f"Unexpected recorder error: {type(error).__name__}: {error}",
                },
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return
        self._send_json({"ok": True, "recorder": result})

    def _send_camera_stream(self, camera_id: str, token: str) -> None:
        try:
            process = self.server.live_workspace.open_camera(camera_id, token)
        except (LiveWorkspaceError, OSError) as error:
            self._send_json(
                {"ok": False, "error": str(error)},
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return
        self.send_response(HTTPStatus.OK)
        self._security_headers()
        self.send_header(
            "Content-Type",
            f"multipart/x-mixed-replace; boundary={MJPEG_BOUNDARY}",
        )
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            if process.stdout is None:
                raise LiveWorkspaceError("Live camera process did not expose a stream.")
            while True:
                block = process.stdout.read(64 * 1024)
                if not block:
                    break
                self.wfile.write(block)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, LiveWorkspaceError):
            pass
        finally:
            self.server.live_workspace.close_camera(process)

    def _read_json_body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        length = int(raw_length)
        if length < 0 or length > 64 * 1024:
            raise RecorderError("Recorder request body is too large.")
        if not length:
            return {}
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise RecorderError("Recorder request must be a JSON object.")
        return payload

    def _send_json(
        self,
        payload: dict[str, Any],
        status: HTTPStatus = HTTPStatus.OK,
        *,
        close_connection: bool = False,
    ) -> None:
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if close_connection:
            self.close_connection = True
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        if close_connection:
            self.send_header("Connection", "close")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        try:
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError):
            # A browser reload or request watchdog must not take down Studio.
            pass

    def _send_static(self, request_path: str) -> None:
        relative = "index.html" if request_path in {"", "/"} else request_path.lstrip("/")
        candidate = (STATIC_ROOT / relative).resolve()
        if not candidate.is_relative_to(STATIC_ROOT.resolve()) or not candidate.is_file():
            candidate = STATIC_ROOT / "index.html"
        try:
            payload = candidate.read_bytes()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        mime, _ = mimetypes.guess_type(candidate.name)
        self.send_response(HTTPStatus.OK)
        self._security_headers()
        self.send_header("Content-Type", f"{mime or 'application/octet-stream'}; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_media(self, token: str) -> None:
        try:
            path, handle, file_stat = open_media_token(token, self.server.repo_root)
        except (OSError, ValueError):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        with handle:
            size = file_stat.st_size
            start = 0
            end = size - 1
            status = HTTPStatus.OK
            range_header = self.headers.get("Range")
            if range_header:
                match = RANGE_PATTERN.fullmatch(range_header.strip())
                if not match:
                    self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    return
                raw_start, raw_end = match.groups()
                if raw_start:
                    start = int(raw_start)
                    end = int(raw_end) if raw_end else end
                elif raw_end:
                    suffix_length = int(raw_end)
                    start = max(0, size - suffix_length)
                if start >= size or end < start:
                    self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                end = min(end, size - 1)
                status = HTTPStatus.PARTIAL_CONTENT
            length = end - start + 1
            mime, _ = mimetypes.guess_type(path.name)
            self.send_response(status)
            self._security_headers()
            self.send_header("Content-Type", mime or "application/octet-stream")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "private, max-age=5")
            self.send_header("Content-Length", str(length))
            if status == HTTPStatus.PARTIAL_CONTENT:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            try:
                handle.seek(start)
                remaining = length
                while remaining:
                    block = handle.read(min(1024 * 256, remaining))
                    if not block:
                        break
                    self.wfile.write(block)
                    remaining -= len(block)
            except (BrokenPipeError, ConnectionResetError):
                return

    def _send_scene_asset(self, name: str) -> None:
        candidate = (SCENE_ASSET_ROOT / name).resolve()
        if (
            not candidate.is_relative_to(SCENE_ASSET_ROOT.resolve())
            or candidate.suffix.lower() != ".stl"
            or not candidate.is_file()
        ):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        payload = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self._security_headers()
        self.send_header("Content-Type", "model/stl")
        self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; media-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'wasm-unsafe-eval'; connect-src 'self' data:; "
            "worker-src 'self' blob:",
        )

    def log_message(self, format: str, *args: object) -> None:
        if args and str(args[1]).startswith("4"):
            super().log_message(format, *args)


def create_server(
    host: str = "127.0.0.1",
    port: int = 4173,
    *,
    repo_root: Path = REPO_ROOT,
    read_only: bool = False,
    enable_physical_demo: bool = False,
) -> StudioServer:
    return StudioServer(
        (host, port),
        repo_root=repo_root,
        read_only=read_only,
        enable_physical_demo=enable_physical_demo,
    )


def serve_studio(
    host: str = "127.0.0.1",
    port: int = 4173,
    *,
    open_browser: bool = True,
    read_only: bool = False,
    enable_physical_demo: bool = False,
) -> None:
    server = create_server(
        host,
        port,
        read_only=read_only,
        enable_physical_demo=enable_physical_demo,
    )
    actual_port = int(server.server_address[1])
    url = f"http://{host}:{actual_port}"
    print(f"sim2claw studio: {url}", flush=True)
    if read_only:
        print("read-only evidence mode; recorder and live-device controls disabled", flush=True)
    else:
        print(
            "loopback recorder enabled; physical demo "
            + ("explicitly enabled" if enable_physical_demo else "closed by default")
            + "; promotion remains closed",
            flush=True,
        )
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nstudio stopped", flush=True)
    finally:
        server.server_close()

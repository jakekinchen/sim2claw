"""Dependency-free, loopback-first HTTP server for the sim2claw studio."""

from __future__ import annotations

import ipaddress
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
from .physical_gateway import PhysicalGatewayError
from .studio_catalog import build_catalog, resolve_media_token
from .studio_live import LiveWorkspaceError, LiveWorkspaceService, MJPEG_BOUNDARY
from .state_trace import build_scene_manifest
from .teleop_recording import RecorderConflict, RecorderError, TeleopRecordingManager
from .scene import CURRENT_TASK_PIECE_LAYOUT
from .paths import SO101_MODEL_PATH


STATIC_ROOT = Path(__file__).with_name("studio_web")
SCENE_ASSET_ROOT = SO101_MODEL_PATH.parent / "assets"
RANGE_PATTERN = re.compile(r"bytes=(\d*)-(\d*)$")


class StudioServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], repo_root: Path = REPO_ROOT):
        self.repo_root = repo_root.resolve()
        try:
            self.recorder_control_enabled = ipaddress.ip_address(address[0]).is_loopback
        except ValueError:
            self.recorder_control_enabled = address[0] == "localhost"
        self.recorder = TeleopRecordingManager(repo_root=self.repo_root)
        self.live_workspace = LiveWorkspaceService(self.recorder)
        self.scene_manifests: dict[str, dict[str, Any]] = {}
        super().__init__(address, StudioRequestHandler)

    def server_close(self) -> None:
        self.live_workspace.shutdown()
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
        if path == "/api/catalog":
            self._send_json(build_catalog(self.server.repo_root))
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
    ) -> None:
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
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
            path = resolve_media_token(token, self.server.repo_root)
        except ValueError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        size = path.stat().st_size
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
            with path.open("rb") as handle:
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
            "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'",
        )

    def log_message(self, format: str, *args: object) -> None:
        if args and str(args[1]).startswith("4"):
            super().log_message(format, *args)


def create_server(
    host: str = "127.0.0.1",
    port: int = 4173,
    *,
    repo_root: Path = REPO_ROOT,
) -> StudioServer:
    return StudioServer((host, port), repo_root=repo_root)


def serve_studio(
    host: str = "127.0.0.1",
    port: int = 4173,
    *,
    open_browser: bool = True,
) -> None:
    server = create_server(host, port)
    actual_port = int(server.server_address[1])
    url = f"http://{host}:{actual_port}"
    print(f"sim2claw studio: {url}", flush=True)
    print(
        "loopback recorder enabled; physical motion is operator-gated and promotion remains closed",
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

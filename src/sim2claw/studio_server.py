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
from urllib.parse import unquote, urlsplit

from .paths import REPO_ROOT
from .physical_gateway import PhysicalGatewayError
from .studio_catalog import build_catalog, resolve_media_token
from .teleop_recording import RecorderConflict, RecorderError, TeleopRecordingManager


STATIC_ROOT = Path(__file__).with_name("studio_web")
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
        super().__init__(address, StudioRequestHandler)

    def server_close(self) -> None:
        self.recorder.shutdown()
        super().server_close()


class StudioRequestHandler(BaseHTTPRequestHandler):
    server: StudioServer
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = unquote(urlsplit(self.path).path)
        if path == "/api/catalog":
            self._send_json(build_catalog(self.server.repo_root))
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
        if path == "/api/health":
            self._send_json(
                {
                    "ok": True,
                    "service": "sim2claw-studio",
                    "physical_authority": False,
                    "physical_motion_endpoint": "operator_gated_relative_bounded",
                    "recorder_control": (
                        "loopback_only" if self.server.recorder_control_enabled else "disabled"
                    ),
                }
            )
            return
        if path.startswith("/media/"):
            self._send_media(path.removeprefix("/media/"))
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
        self.wfile.write(encoded)

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

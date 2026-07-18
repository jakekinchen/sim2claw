"""Isolated overhead-camera recording for teleoperation diagnostics.

The camera process is deliberately separate from the arm control loop.  Its
output is diagnostic evidence only and is not admitted as ACT training data.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


OVERHEAD_VIDEO_SCHEMA = "sim2claw.overhead_diagnostic_video.v1"
DEFAULT_CAMERA_NAME = "C922 Pro Stream Webcam"
# The C922's current AVFoundation path exposes 720p NV12 at only 10 fps.  The
# 640x480 NV12 mode accepts 30 fps without a fallback, which better preserves
# temporal evidence while the arms share this Mac's USB topology.
DEFAULT_WIDTH = 640
DEFAULT_HEIGHT = 480
DEFAULT_FPS = 30
DEVICE_PATTERN = re.compile(r"\[(\d+)\]\s+(.+?)\s*$")


class OverheadVideoError(RuntimeError):
    """The required overhead diagnostic video could not be recorded."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _compact_log_tail(path: Path, *, lines: int = 8) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return " | ".join(row.strip() for row in content[-lines:] if row.strip())


def discover_avfoundation_camera(
    camera_name: str = DEFAULT_CAMERA_NAME,
    *,
    ffmpeg_path: str | None = None,
) -> dict[str, Any]:
    """Resolve an AVFoundation video index by camera name, not index order."""

    ffmpeg = ffmpeg_path or shutil.which("ffmpeg")
    if not ffmpeg:
        raise OverheadVideoError("ffmpeg is required for overhead camera recording.")
    try:
        result = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-f",
                "avfoundation",
                "-list_devices",
                "true",
                "-i",
                "",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=8.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise OverheadVideoError(f"Could not enumerate AVFoundation cameras: {error}") from error

    cameras: list[dict[str, Any]] = []
    in_video_section = False
    for raw_line in result.stderr.splitlines():
        if "AVFoundation video devices:" in raw_line:
            in_video_section = True
            continue
        if "AVFoundation audio devices:" in raw_line:
            in_video_section = False
            continue
        if not in_video_section:
            continue
        match = DEVICE_PATTERN.search(raw_line)
        if match:
            cameras.append({"index": int(match.group(1)), "name": match.group(2)})

    exact = next((row for row in cameras if row["name"] == camera_name), None)
    selected = exact or next(
        (row for row in cameras if camera_name.lower() in row["name"].lower()),
        None,
    )
    if selected is None:
        found = ", ".join(row["name"] for row in cameras) or "none"
        raise OverheadVideoError(
            f"Required overhead camera '{camera_name}' was not found; detected: {found}."
        )
    return {
        "camera_name": selected["name"],
        "camera_index": selected["index"],
        "ffmpeg_path": ffmpeg,
        "detected_cameras": cameras,
    }


class OverheadVideoRecorder:
    """Own one ffmpeg process and expose nonblocking health checks."""

    def __init__(
        self,
        output_path: Path,
        *,
        camera_name: str = DEFAULT_CAMERA_NAME,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        fps: int = DEFAULT_FPS,
        ffmpeg_path: str | None = None,
        ffprobe_path: str | None = None,
    ):
        self.output_path = output_path
        self.log_path = output_path.with_suffix(".ffmpeg.log")
        self.camera_name = camera_name
        self.width = int(width)
        self.height = int(height)
        self.fps = int(fps)
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path or shutil.which("ffprobe")
        self.process: subprocess.Popen[bytes] | None = None
        self.log_handle: Any = None
        self.started_at: str | None = None
        self.started_monotonic: float | None = None
        self.discovery: dict[str, Any] | None = None

    def start(self) -> dict[str, Any]:
        if self.process is not None:
            raise OverheadVideoError("Overhead video recorder is already started.")
        ffmpeg = self.ffmpeg_path or shutil.which("ffmpeg")
        if not ffmpeg:
            raise OverheadVideoError("ffmpeg is required for overhead camera recording.")
        # AVFoundation accepts the exact device name in its input specifier.
        # Opening by name avoids a separate enumeration call, which can block
        # during USB camera re-enumeration, and avoids unstable numeric indexes.
        self.discovery = {
            "camera_name": self.camera_name,
            "camera_index": None,
            "ffmpeg_path": ffmpeg,
        }
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_handle = self.log_path.open("wb")
        command = [
            str(self.discovery["ffmpeg_path"]),
            "-hide_banner",
            "-loglevel",
            "warning",
            "-f",
            "avfoundation",
            "-pixel_format",
            "nv12",
            "-framerate",
            str(self.fps),
            "-video_size",
            f"{self.width}x{self.height}",
            "-i",
            f"{self.discovery['camera_name']}:none",
            "-an",
            "-vf",
            "hflip,vflip",
            "-c:v",
            "h264_videotoolbox",
            "-b:v",
            "4M",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-y",
            str(self.output_path),
        ]
        self.started_at = _utc_now()
        self.started_monotonic = time.monotonic()
        try:
            self.process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=self.log_handle,
                start_new_session=True,
            )
        except OSError as error:
            self._close_log()
            raise OverheadVideoError(f"Could not start overhead video capture: {error}") from error

        startup_deadline = time.monotonic() + 1.0
        while time.monotonic() < startup_deadline:
            if self.process.poll() is not None:
                self._close_log()
                detail = _compact_log_tail(self.log_path)
                raise OverheadVideoError(
                    "C922 video capture exited during startup"
                    + (f": {detail}" if detail else ".")
                )
            time.sleep(0.05)
        return {
            "schema_version": OVERHEAD_VIDEO_SCHEMA,
            "status": "recording",
            "camera_name": self.discovery["camera_name"],
            "camera_index": self.discovery["camera_index"],
            "configured_width": self.width,
            "configured_height": self.height,
            "configured_fps": self.fps,
            "configured_pixel_format": "nv12",
            "orientation_rotation_degrees": 180,
            "video_path": self.output_path.name,
            "ffmpeg_log_path": self.log_path.name,
            "video_started_at": self.started_at,
            "diagnostic_only": True,
            "is_training_data": False,
        }

    def ensure_running(self) -> None:
        if self.process is None or self.process.poll() is None:
            return
        detail = _compact_log_tail(self.log_path)
        raise OverheadVideoError(
            "C922 video capture stopped before the episode ended"
            + (f": {detail}" if detail else ".")
        )

    def finish(
        self,
        *,
        action_started_monotonic: float | None,
        action_stopped_monotonic: float | None,
        post_roll_seconds: float,
    ) -> dict[str, Any]:
        process = self.process
        start = self.started_monotonic
        if process is None or start is None:
            raise OverheadVideoError("Overhead video recorder was not started.")

        was_running = process.poll() is None
        if was_running and action_stopped_monotonic is not None:
            deadline = action_stopped_monotonic + max(0.0, post_roll_seconds)
            while time.monotonic() < deadline and process.poll() is None:
                time.sleep(min(0.05, deadline - time.monotonic()))
        capture_stop_requested_monotonic = time.monotonic()
        if process.poll() is None:
            try:
                if process.stdin is not None:
                    process.stdin.write(b"q\n")
                    process.stdin.flush()
                    process.stdin.close()
                process.wait(timeout=8.0)
            except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2.0)
        self._close_log()

        completed_at_monotonic = time.monotonic()
        observed = self._probe_output()
        return_code = process.returncode
        status = (
            "completed"
            if (
                was_running
                and return_code in {0, 255}
                and self.output_path.is_file()
                and observed is not None
            )
            else "failed"
        )
        action_start_offset = (
            action_started_monotonic - start
            if action_started_monotonic is not None
            else None
        )
        action_stop_offset = (
            action_stopped_monotonic - start
            if action_stopped_monotonic is not None
            else None
        )
        actual_post_roll = (
            max(0.0, capture_stop_requested_monotonic - action_stopped_monotonic)
            if action_stopped_monotonic is not None
            else None
        )
        return {
            "schema_version": OVERHEAD_VIDEO_SCHEMA,
            "status": status,
            "camera_name": self.discovery["camera_name"] if self.discovery else self.camera_name,
            "camera_index": self.discovery["camera_index"] if self.discovery else None,
            "configured_width": self.width,
            "configured_height": self.height,
            "configured_fps": self.fps,
            "configured_pixel_format": "nv12",
            "orientation_rotation_degrees": 180,
            "video_path": self.output_path.name,
            "ffmpeg_log_path": self.log_path.name,
            "video_started_at": self.started_at,
            "video_finished_at": _utc_now(),
            "action_start_video_offset_seconds": action_start_offset,
            "action_stop_video_offset_seconds": action_stop_offset,
            "post_roll_seconds_configured": float(post_roll_seconds),
            "post_roll_seconds_observed": actual_post_roll,
            "video_finalization_seconds": max(
                0.0, completed_at_monotonic - capture_stop_requested_monotonic
            ),
            "ffmpeg_return_code": return_code,
            "observed_video": observed,
            "diagnostic_only": True,
            "is_training_data": False,
            "error_log_tail": _compact_log_tail(self.log_path) if status == "failed" else None,
        }

    def _probe_output(self) -> dict[str, Any] | None:
        if not self.ffprobe_path or not self.output_path.is_file():
            return None
        try:
            result = subprocess.run(
                [
                    self.ffprobe_path,
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=codec_name,width,height,avg_frame_rate,nb_frames:format=duration,size",
                    "-of",
                    "json",
                    str(self.output_path),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=8.0,
                check=False,
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            pass
        return None

    def _close_log(self) -> None:
        if self.log_handle is not None:
            self.log_handle.close()
            self.log_handle = None

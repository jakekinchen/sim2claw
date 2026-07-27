"""Bounded Pi IMX708 video sidecar for a reviewed physical motion.

The Pi recorder owns only one fixed SSH-launched ``rpicam-vid`` process.  Its
eight-second timeout is frozen before capture, so a lost client cannot leave an
unbounded remote camera process behind.  The sidecar composes with the existing
native C922/D405 recorder but never constructs or commands a robot gateway.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

from .native_dual_camera import NativeDualCameraRecorder
from .paths import REPO_ROOT


CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "acquisition"
    / "pi_imx708_motion_video_v1.json"
)
CONTRACT_SCHEMA = "sim2claw.pi_motion_video_contract.v1"
RECEIPT_SCHEMA = "sim2claw.pi_motion_video_capture.v1"


class PiMotionVideoError(RuntimeError):
    """The Pi sidecar contract, transport, or artifact failed closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PiMotionVideoError(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PiMotionVideoError(f"cannot read {label}: {error}") from error
    _require(isinstance(value, dict), f"{label} must be a JSON object")
    return value


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = _load_json(path, "Pi motion-video contract")
    authority = contract.get("authority", {})
    _require(
        contract.get("schema_version") == CONTRACT_SCHEMA
        and contract.get("status") == "preregistered_before_capture"
        and contract.get("camera") == "imx708_wide"
        and contract.get("width") == 1536
        and contract.get("height") == 864
        and contract.get("framerate") == 30
        and contract.get("duration_seconds") == 8
        and contract.get("minimum_frames") == 60
        and contract.get("horizontal_flip") is True
        and contract.get("vertical_flip") is True
        and contract.get("autofocus_mode") == "manual"
        and contract.get("codec") == "mjpeg"
        and contract.get("jpeg_quality") == 70,
        "Pi motion-video mode changed",
    )
    host = str(contract.get("ssh_host") or "")
    _require(
        host
        and all(character.isalnum() or character in "@._-" for character in host),
        "Pi SSH host is invalid",
    )
    _require(
        authority.get("camera_observation") is True
        and all(
            authority.get(key) is False
            for key in (
                "camera_exposure_synchronization",
                "camera_intrinsics",
                "camera_extrinsics",
                "robot_gateway",
                "robot_motion",
                "policy",
                "task_success",
            )
        ),
        "Pi motion-video authority widened",
    )
    for key in (
        "startup_timeout_seconds",
        "source_stall_timeout_seconds",
        "shutdown_grace_seconds",
        "lens_position_reciprocal_m",
    ):
        value = float(contract.get(key, math.nan))
        _require(math.isfinite(value) and value > 0.0, f"invalid Pi {key}")
    return contract


class PiMotionVideoRecorder:
    """Stream one bounded raw H.264 recording from the Pi to local storage."""

    def __init__(
        self,
        output_root: Path,
        *,
        contract_path: Path = CONTRACT_PATH,
        popen_factory: Callable[..., Any] = subprocess.Popen,
        run_fn: Callable[..., Any] = subprocess.run,
        clock: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
        token_factory: Callable[[], str] | None = None,
        ssh_path: str | None = None,
        scp_path: str | None = None,
        ffmpeg_path: str | None = None,
        ffprobe_path: str | None = None,
    ) -> None:
        self.output_root = output_root.resolve()
        self.contract_path = contract_path.resolve()
        self.contract = load_contract(self.contract_path)
        self.popen_factory = popen_factory
        self.run_fn = run_fn
        self.clock = clock
        self.sleep_fn = sleep_fn
        self.token_factory = token_factory or (lambda: uuid.uuid4().hex)
        self.ssh_path = ssh_path or shutil.which("ssh")
        self.scp_path = scp_path or shutil.which("scp")
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg")
        self.ffprobe_path = ffprobe_path or shutil.which("ffprobe")
        _require(
            all(
                value
                for value in (
                    self.ssh_path,
                    self.scp_path,
                    self.ffmpeg_path,
                    self.ffprobe_path,
                )
            ),
            "Pi motion-video requires ssh, scp, ffmpeg, and ffprobe",
        )
        self.raw_path = self.output_root / "pi_imx708.mjpeg"
        self.pts_path = self.output_root / "pi_imx708.pts"
        self.browser_path = self.output_root / "pi_imx708.browser.mp4"
        self.stderr_path = self.output_root / "pi_imx708.stderr.log"
        self.process: Any = None
        self.raw_handle: Any = None
        self.stderr_handle: Any = None
        self.started_monotonic: float | None = None
        self.completed_monotonic: float | None = None
        self.last_growth_monotonic: float | None = None
        self.bytes_observed = 0
        self.remote_pts_path: str | None = None

    def _ssh_prefix(self) -> list[str]:
        return [
            str(self.ssh_path),
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=5",
            str(self.contract["ssh_host"]),
        ]

    def _command(self) -> list[str]:
        assert self.remote_pts_path is not None
        return [
            *self._ssh_prefix(),
            "rpicam-vid",
            "--nopreview",
            "--timeout",
            f"{int(self.contract['duration_seconds'])}sec",
            "--width",
            str(self.contract["width"]),
            "--height",
            str(self.contract["height"]),
            "--framerate",
            str(self.contract["framerate"]),
            "--codec",
            str(self.contract["codec"]),
            "--quality",
            str(self.contract["jpeg_quality"]),
            "--flush",
            "--hflip",
            "--vflip",
            "--autofocus-mode",
            str(self.contract["autofocus_mode"]),
            "--lens-position",
            str(self.contract["lens_position_reciprocal_m"]),
            "--save-pts",
            self.remote_pts_path,
            "--output",
            "-",
        ]

    def start(self) -> dict[str, Any]:
        _require(self.process is None, "Pi motion-video is already started")
        _require(
            not self.output_root.exists(),
            f"refusing to overwrite Pi motion-video output: {self.output_root}",
        )
        token = self.token_factory()
        _require(
            token
            and len(token) <= 64
            and all(character.isalnum() or character in "_-" for character in token),
            "Pi motion-video token is invalid",
        )
        self.remote_pts_path = f"/tmp/sim2claw-pi-motion-{token}.pts"
        self.output_root.mkdir(parents=True)
        self.raw_handle = self.raw_path.open("xb")
        self.stderr_handle = self.stderr_path.open("xb")
        self.started_monotonic = self.clock()
        try:
            self.process = self.popen_factory(
                self._command(),
                stdin=subprocess.DEVNULL,
                stdout=self.raw_handle,
                stderr=self.stderr_handle,
                start_new_session=True,
            )
            deadline = self.started_monotonic + float(
                self.contract["startup_timeout_seconds"]
            )
            while self.clock() < deadline:
                self._flush_outputs()
                if self.process.poll() is not None:
                    break
                size = self.raw_path.stat().st_size
                if size > 1024:
                    self.bytes_observed = size
                    self.last_growth_monotonic = self.clock()
                    return {
                        "schema_version": "sim2claw.pi_motion_video_started.v1",
                        "status": "recording",
                        "camera": self.contract["camera"],
                        "configured_width": self.contract["width"],
                        "configured_height": self.contract["height"],
                        "configured_framerate": self.contract["framerate"],
                        "host_monotonic_start": self.started_monotonic,
                        "bounded_duration_seconds": self.contract[
                            "duration_seconds"
                        ],
                    }
                self.sleep_fn(0.02)
            raise PiMotionVideoError(
                "Pi rpicam-vid did not produce a live MJPEG stream"
                + self._stderr_suffix()
            )
        except Exception:
            self._abort()
            raise

    def _flush_outputs(self) -> None:
        if self.raw_handle is not None and not self.raw_handle.closed:
            self.raw_handle.flush()
        if self.stderr_handle is not None and not self.stderr_handle.closed:
            self.stderr_handle.flush()

    def _stderr_suffix(self) -> str:
        self._flush_outputs()
        try:
            rows = self.stderr_path.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
        except OSError:
            return ""
        tail = " | ".join(row.strip() for row in rows[-6:] if row.strip())
        return f": {tail}" if tail else ""

    def ensure_running(self) -> None:
        _require(self.process is not None, "Pi motion-video was not started")
        if self.process.poll() is not None:
            raise PiMotionVideoError(
                "Pi rpicam-vid exited before the action finished"
                + self._stderr_suffix()
            )
        self._flush_outputs()
        size = self.raw_path.stat().st_size
        now = self.clock()
        if size > self.bytes_observed:
            self.bytes_observed = size
            self.last_growth_monotonic = now
            return
        last = self.last_growth_monotonic or self.started_monotonic
        if last is not None and now - last > float(
            self.contract["source_stall_timeout_seconds"]
        ):
            raise PiMotionVideoError("Pi MJPEG stream stopped growing")

    def _copy_pts(self) -> None:
        assert self.remote_pts_path is not None
        copied = self.run_fn(
            [
                str(self.scp_path),
                "-q",
                f"{self.contract['ssh_host']}:{self.remote_pts_path}",
                str(self.pts_path),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            timeout=10.0,
        )
        _require(
            copied.returncode == 0 and self.pts_path.is_file(),
            "could not copy the Pi PTS ledger",
        )

    def _cleanup_remote(self) -> None:
        if self.remote_pts_path is None:
            return
        try:
            self.run_fn(
                [*self._ssh_prefix(), "rm", "-f", self.remote_pts_path],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
                timeout=8.0,
            )
        except Exception:
            pass

    def _make_browser_video(self) -> None:
        converted = self.run_fn(
            [
                str(self.ffmpeg_path),
                "-hide_banner",
                "-loglevel",
                "warning",
                "-fflags",
                "+genpts",
                "-f",
                "mjpeg",
                "-r",
                str(self.contract["framerate"]),
                "-i",
                str(self.raw_path),
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-y",
                str(self.browser_path),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            timeout=30.0,
        )
        _require(
            converted.returncode == 0 and self.browser_path.is_file(),
            "could not create the Pi browser video",
        )

    def _probe(self) -> dict[str, Any]:
        probed = self.run_fn(
            [
                str(self.ffprobe_path),
                "-v",
                "error",
                "-count_frames",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name,width,height,avg_frame_rate,nb_read_frames:format=duration,size",
                "-of",
                "json",
                str(self.browser_path),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=15.0,
        )
        _require(probed.returncode == 0, "could not probe the Pi browser video")
        try:
            value = json.loads(probed.stdout)
            stream = value["streams"][0]
            frame_count = int(stream["nb_read_frames"])
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise PiMotionVideoError("Pi ffprobe output is invalid") from error
        _require(
            stream.get("codec_name") == "h264"
            and stream.get("width") == self.contract["width"]
            and stream.get("height") == self.contract["height"]
            and frame_count >= self.contract["minimum_frames"],
            "Pi video mode or frame count changed",
        )
        return {
            "frame_count": frame_count,
            "codec_name": stream["codec_name"],
            "width": stream["width"],
            "height": stream["height"],
            "avg_frame_rate": stream.get("avg_frame_rate"),
            "duration_seconds": float(value["format"]["duration"]),
            "bytes": int(value["format"]["size"]),
        }

    def _parse_pts(self) -> dict[str, Any]:
        values: list[float] = []
        for row in self.pts_path.read_text(
            encoding="utf-8", errors="strict"
        ).splitlines():
            stripped = row.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                values.append(float(stripped))
            except ValueError as error:
                raise PiMotionVideoError("Pi PTS ledger is invalid") from error
        _require(
            len(values) >= self.contract["minimum_frames"]
            and all(math.isfinite(value) for value in values)
            and all(right > left for left, right in zip(values, values[1:])),
            "Pi PTS ledger is incomplete or non-monotonic",
        )
        return {
            "count": len(values),
            "first": values[0],
            "last": values[-1],
        }

    def finish(
        self,
        *,
        action_started_monotonic: float | None,
        action_stopped_monotonic: float | None,
        post_roll_seconds: float,
    ) -> dict[str, Any]:
        _require(
            self.process is not None and self.started_monotonic is not None,
            "Pi motion-video was not started",
        )
        process = self.process
        deadline = (
            self.started_monotonic
            + float(self.contract["duration_seconds"])
            + float(self.contract["shutdown_grace_seconds"])
        )
        try:
            while process.poll() is None and self.clock() < deadline:
                self._flush_outputs()
                self.sleep_fn(0.05)
            if process.poll() is None:
                raise PiMotionVideoError("Pi rpicam-vid exceeded its bounded duration")
            return_code = process.wait(timeout=1.0)
            self.completed_monotonic = self.clock()
            self._close_handles()
            _require(
                return_code == 0 and self.raw_path.stat().st_size > 1024,
                "Pi rpicam-vid did not finalize" + self._stderr_suffix(),
            )
            self._copy_pts()
            self._make_browser_video()
            probe = self._probe()
            pts = self._parse_pts()
            _require(
                pts["count"] == probe["frame_count"],
                "Pi PTS and container frame counts differ",
            )
            _require(
                action_started_monotonic is not None
                and action_stopped_monotonic is not None
                and self.started_monotonic <= action_started_monotonic
                <= action_stopped_monotonic
                <= self.completed_monotonic,
                "physical action interval is not enclosed by the Pi capture",
            )
            return {
                "schema_version": RECEIPT_SCHEMA,
                "status": "completed",
                "camera": self.contract["camera"],
                "configured_width": self.contract["width"],
                "configured_height": self.contract["height"],
                "configured_framerate": self.contract["framerate"],
                "raw_video_path": str(self.raw_path),
                "raw_video_sha256": _sha256(self.raw_path),
                "browser_video_path": str(self.browser_path),
                "browser_video_sha256": _sha256(self.browser_path),
                "pts_path": str(self.pts_path),
                "pts_sha256": _sha256(self.pts_path),
                "pts": pts,
                "observed_video": probe,
                "host_monotonic_start": self.started_monotonic,
                "host_monotonic_end": self.completed_monotonic,
                "action_interval_enclosed": True,
                "post_roll_seconds_requested": float(post_roll_seconds),
                "timestamp_semantics": {
                    "pi_pts": "rpicam_vid_save_pts",
                    "host_bounds_only": True,
                    "camera_exposure_synchronized": False,
                    "cross_camera_exposure_synchronized": False,
                },
                "claim_limits": {
                    "camera_intrinsics": False,
                    "camera_extrinsics": False,
                    "metric_registration": False,
                    "task_success": False,
                    "physical_authority": False,
                },
            }
        finally:
            self._cleanup_remote()
            self._close_handles()

    def _close_handles(self) -> None:
        for name in ("raw_handle", "stderr_handle"):
            handle = getattr(self, name)
            if handle is not None and not handle.closed:
                handle.close()

    def _abort(self) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2.0)
        self._close_handles()
        self._cleanup_remote()


class MotionTricamRecorder:
    """Compose native C922/D405 motion video with the bounded Pi sidecar."""

    def __init__(
        self,
        output_root: Path,
        *,
        pi_contract_path: Path = CONTRACT_PATH,
        dual_factory: Callable[[Path], Any] = NativeDualCameraRecorder,
        pi_factory: Callable[..., Any] = PiMotionVideoRecorder,
    ) -> None:
        self.output_root = output_root
        self.dual = dual_factory(output_root)
        self.pi = pi_factory(
            output_root / "pi_motion",
            contract_path=pi_contract_path,
        )
        self.dual_started = False
        self.pi_started = False

    def start(self) -> dict[str, Any]:
        try:
            dual = self.dual.start()
            self.dual_started = True
            pi = self.pi.start()
            self.pi_started = True
            self.ensure_running()
            return {
                "schema_version": "sim2claw.motion_tricam_started.v1",
                "dual_camera": dual,
                "pi": pi,
            }
        except Exception as error:
            cleanup_errors: list[str] = []
            if self.pi_started:
                try:
                    self.pi._abort()
                except Exception as cleanup:
                    cleanup_errors.append(f"Pi cleanup: {cleanup}")
            if self.dual_started:
                try:
                    self.dual.finish(
                        action_started_monotonic=None,
                        action_stopped_monotonic=None,
                        post_roll_seconds=0.0,
                    )
                except Exception as cleanup:
                    cleanup_errors.append(f"dual-camera cleanup: {cleanup}")
            detail = str(error)
            if cleanup_errors:
                detail += "; " + "; ".join(cleanup_errors)
            raise PiMotionVideoError(detail) from error

    def ensure_running(self) -> None:
        self.dual.ensure_running()
        self.pi.ensure_running()

    def finish(
        self,
        *,
        action_started_monotonic: float | None,
        action_stopped_monotonic: float | None,
        post_roll_seconds: float,
    ) -> dict[str, Any]:
        dual_result: dict[str, Any] | None = None
        pi_result: dict[str, Any] | None = None
        errors: list[str] = []
        try:
            dual_result = self.dual.finish(
                action_started_monotonic=action_started_monotonic,
                action_stopped_monotonic=action_stopped_monotonic,
                post_roll_seconds=post_roll_seconds,
            )
        except Exception as error:
            errors.append(f"dual-camera: {error}")
        try:
            pi_result = self.pi.finish(
                action_started_monotonic=action_started_monotonic,
                action_stopped_monotonic=action_stopped_monotonic,
                post_roll_seconds=post_roll_seconds,
            )
        except Exception as error:
            errors.append(f"Pi: {error}")
        if errors:
            raise PiMotionVideoError("; ".join(errors))
        assert dual_result is not None and pi_result is not None
        return {**dual_result, "pi": pi_result}


__all__ = [
    "CONTRACT_PATH",
    "CONTRACT_SCHEMA",
    "RECEIPT_SCHEMA",
    "MotionTricamRecorder",
    "PiMotionVideoError",
    "PiMotionVideoRecorder",
    "load_contract",
]

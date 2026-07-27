"""Production dual-camera recording through one native AVFoundation session.

The native helper uses the exact active-session device and format mechanism
already demonstrated by the sealed common-session observation. It writes one
source container and one callback timestamp ledger per stream, then creates
browser derivatives only after the common capture session has stopped.

These artifacts are diagnostic physical observations. Their timestamps are
not exposure synchronization, the D405 stream is not metric depth, and this
recorder creates no robot or task authority.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import signal
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .overhead_video import (
    OVERHEAD_VIDEO_SCHEMA,
    WRIST_VIDEO_SCHEMA,
    OverheadVideoError,
)
from .video_timing import VideoTimingError, probe_video_container_timing

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = REPO_ROOT / "tools/macos/AVFoundationDualCameraRecorder.swift"
SEALED_OBSERVATION_CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/avfoundation_dual_camera_common_session_v1.json"
)
ACTIVE_RUNTIME_CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/avfoundation_dual_camera_runtime_binding_v2.json"
)
# Backwards-compatible public name. Production capture now uses the explicit
# live runtime binding; the sealed observation contract remains immutable.
PROVEN_CONTRACT_PATH = ACTIVE_RUNTIME_CONTRACT_PATH
READY_SCHEMA = "sim2claw.native_dual_camera_recorder_ready.v1"
REPORT_SCHEMA = "sim2claw.native_dual_camera_recorder_report.v1"
RUNTIME_SCHEMA = "sim2claw.native_dual_camera_recorder_runtime.v1"
COMMON_SESSION_SCHEMA = "sim2claw.native_dual_camera_capture.v1"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise OverheadVideoError(f"{label} is unavailable or invalid: {error}") from error
    if not isinstance(payload, dict):
        raise OverheadVideoError(f"{label} must be a JSON object.")
    return payload


def _stage(report: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [
        row
        for row in report.get("stages") or []
        if isinstance(row, dict) and row.get("name") == name
    ]
    if len(matches) != 1:
        raise OverheadVideoError(f"Native recorder report has no unique {name} stage.")
    return matches[0]


def _stream(report: dict[str, Any], role: str) -> dict[str, Any]:
    matches = [
        row
        for row in report.get("streams") or []
        if isinstance(row, dict) and row.get("role") == role
    ]
    if len(matches) != 1:
        raise OverheadVideoError(f"Native recorder report has no unique {role} stream.")
    return matches[0]


def validate_native_report(
    report: dict[str, Any],
    *,
    devices: dict[str, Any],
) -> dict[str, Any]:
    """Validate production-relevant native capture facts.

    The historical after-stop object-identity lookup is intentionally retained
    in the report but is not an operational gate. Active-session exact format,
    connection binding, callback delivery, writer completion, and separate
    stream attribution are the production gates.
    """

    if (
        report.get("schema_version") != REPORT_SCHEMA
        or report.get("status") != "completed"
        or report.get("session_count") != 1
        or report.get("independent_camera_sessions") != 0
        or report.get("post_stop_format_index_operational_gate") is not False
    ):
        raise OverheadVideoError("Native common-session report did not complete.")
    after_start = _stage(report, "after_start")
    if after_start.get("session_running") is not True:
        raise OverheadVideoError("Native common session was not running at admission.")
    for role in ("c922", "d405"):
        expected = devices[role]
        state = after_start.get(role)
        if not isinstance(state, dict):
            raise OverheadVideoError(f"Native {role} active-session state is missing.")
        exact = (
            state.get("localized_name") == expected["exact_localized_name"]
            and state.get("unique_id") == expected["exact_unique_id"]
            and state.get("model_id") == expected["exact_model_id"]
            and state.get("format_index") == expected["format_index"]
            and state.get("width") == expected["width"]
            and state.get("height") == expected["height"]
            and state.get("subtype") == expected["media_subtype_fourcc"]
            and math.isclose(
                float(state.get("minimum_duration_seconds")),
                float(expected["frame_duration_seconds"]),
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            and after_start.get(f"{role}_input_admitted") is True
            and after_start.get(f"{role}_output_admitted") is True
            and after_start.get(f"{role}_output_bound_to_exact_input") is True
        )
        if not exact:
            raise OverheadVideoError(
                f"Native {role} active-session identity or connection changed."
            )
        stream = _stream(report, role)
        callbacks = stream.get("output_callback_count")
        appended = stream.get("writer_append_count")
        warmup = stream.get("warmup_excluded_callback_count")
        if (
            not isinstance(callbacks, int)
            or callbacks < 2
            or not isinstance(appended, int)
            or appended < 2
            or not isinstance(warmup, int)
            or warmup < 1
            or appended + warmup != callbacks
            or stream.get("apple_drop_callback_count") != 0
            or stream.get("writer_backpressure_count") != 0
            or stream.get("writer_status") != "completed"
            or stream.get("errors") != []
            or not isinstance(stream.get("first_pts_seconds"), (int, float))
            or not isinstance(stream.get("last_pts_seconds"), (int, float))
            or float(stream["last_pts_seconds"]) <= float(stream["first_pts_seconds"])
        ):
            raise OverheadVideoError(f"Native {role} writer evidence is incomplete.")
    return {
        "active_session_exact_formats": True,
        "active_session_exact_stream_bindings": True,
        "writers_completed": True,
        "after_stop_format_index_operational_gate": False,
    }


class NativeDualCameraRecorder:
    """Own one native process, one AVCaptureSession, and two attributed writers."""

    def __init__(
        self,
        draft: Path,
        *,
        source_path: Path = SOURCE_PATH,
        proven_contract_path: Path = PROVEN_CONTRACT_PATH,
        compiler_path: str = "/usr/bin/swiftc",
        ffmpeg_path: str | None = None,
        ffprobe_path: str | None = None,
        clock: Callable[[], float] = time.monotonic,
        startup_timeout_seconds: float = 10.0,
        source_stall_timeout_seconds: float = 3.0,
        shutdown_timeout_seconds: float = 18.0,
    ):
        self.draft = draft
        self.source_path = source_path
        self.proven_contract_path = proven_contract_path
        self.compiler_path = compiler_path
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg")
        self.ffprobe_path = ffprobe_path or shutil.which("ffprobe")
        self._clock = clock
        self.startup_timeout_seconds = float(startup_timeout_seconds)
        self.source_stall_timeout_seconds = float(source_stall_timeout_seconds)
        self.shutdown_timeout_seconds = float(shutdown_timeout_seconds)
        self.runtime_root = draft / "native_dual_camera"
        self.binary_path = self.runtime_root / "runtime/dual-camera-recorder"
        self.ready_path = self.runtime_root / "native_camera_ready.json"
        self.report_path = self.runtime_root / "native_camera_report.json"
        self.events_path = self.runtime_root / "camera_callback_timestamps.jsonl"
        self.stderr_path = self.runtime_root / "native_camera.stderr.log"
        self.overhead_source_path = self.runtime_root / "overhead_c922.native.mov"
        self.wrist_source_path = self.runtime_root / "wrist_d405.native.mov"
        self.overhead_browser_path = draft / "overhead_c922.mp4"
        self.wrist_browser_path = draft / "wrist_d405.browser.mp4"
        self.process: subprocess.Popen[bytes] | None = None
        self.log_handle: Any = None
        self.started_monotonic: float | None = None
        self.started_at: str | None = None
        self.last_event_growth_monotonic: float | None = None
        self.event_bytes_observed = 0
        self.runtime_identity: dict[str, Any] | None = None
        self.contract = _load_json(proven_contract_path, label="proven common-session contract")
        if (
            self.contract.get("schema_version")
            != "sim2claw.avfoundation_dual_camera_common_session_contract.v1"
        ):
            raise OverheadVideoError("Proven common-session device contract changed.")

    def _compile(self) -> dict[str, Any]:
        compiler = Path(self.compiler_path)
        if not compiler.is_file() or not self.source_path.is_file():
            raise OverheadVideoError("Native dual-camera compiler or source is unavailable.")
        version = subprocess.run(
            [str(compiler), "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10.0,
        )
        if version.returncode != 0:
            raise OverheadVideoError("Could not identify the Swift compiler.")
        self.binary_path.parent.mkdir(parents=True, exist_ok=True)
        built = subprocess.run(
            [str(compiler), str(self.source_path), "-o", str(self.binary_path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=90.0,
        )
        if built.returncode != 0:
            raise OverheadVideoError(
                "Native dual-camera Swift compilation failed: "
                + (built.stderr.strip() or "unknown compiler error")
            )
        return {
            "schema_version": RUNTIME_SCHEMA,
            "source_path": str(self.source_path.relative_to(REPO_ROOT)),
            "source_sha256": _sha256(self.source_path),
            "proven_active_session_contract_path": str(
                self.proven_contract_path.relative_to(REPO_ROOT)
            ),
            "proven_active_session_contract_sha256": _sha256(
                self.proven_contract_path
            ),
            "compiler_path": str(compiler),
            "compiler_sha256": _sha256(compiler),
            "swift_version": version.stdout.strip(),
            "binary_path": str(self.binary_path.relative_to(self.draft)),
            "binary_sha256": _sha256(self.binary_path),
        }

    def _command(self) -> list[str]:
        command = [
            str(self.binary_path),
            "--output-root",
            str(self.runtime_root),
            "--ready-timeout-seconds",
            "6.0",
        ]
        for role in ("d405", "c922"):
            device = self.contract["devices"][role]
            prefix = f"--{role}"
            command += [
                f"{prefix}-name",
                str(device["exact_localized_name"]),
                f"{prefix}-unique-id",
                str(device["exact_unique_id"]),
                f"{prefix}-model-id",
                str(device["exact_model_id"]),
                f"{prefix}-format-index",
                str(device["format_index"]),
                f"{prefix}-range-index",
                str(device["frame_rate_range_index"]),
                f"{prefix}-width",
                str(device["width"]),
                f"{prefix}-height",
                str(device["height"]),
                f"{prefix}-subtype",
                str(device["media_subtype_fourcc"]),
                f"{prefix}-fps",
                str(device["supported_fps"]),
            ]
        return command

    def start(self) -> dict[str, Any]:
        if self.process is not None:
            raise OverheadVideoError("Native dual-camera recorder is already started.")
        self.runtime_root.mkdir(parents=True, exist_ok=False)
        self.runtime_identity = self._compile()
        self.log_handle = self.stderr_path.open("wb")
        self.started_monotonic = self._clock()
        self.started_at = _utc_now()
        try:
            self.process = subprocess.Popen(
                self._command(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=self.log_handle,
                start_new_session=True,
            )
        except OSError as error:
            self._close_log()
            raise OverheadVideoError(
                f"Could not start native dual-camera capture: {error}"
            ) from error
        deadline = self._clock() + self.startup_timeout_seconds
        while self._clock() < deadline:
            if self.ready_path.is_file():
                ready = _load_json(self.ready_path, label="native recorder readiness")
                self._validate_ready(ready)
                self._observe_event_progress()
                return {
                    "schema_version": COMMON_SESSION_SCHEMA,
                    "status": "recording",
                    "capture_mechanism": "one_native_avcapture_session",
                    "session_count": 1,
                    "independent_camera_sessions": 0,
                    "started_at": self.started_at,
                    "runtime_identity": self.runtime_identity,
                    "callback_timestamp_path": str(
                        self.events_path.relative_to(self.draft)
                    ),
                    "overhead": self._starting_stream("c922"),
                    "wrist": self._starting_stream("d405"),
                    "claim_limits": self._claim_limits(),
                }
            if self.process.poll() is not None:
                break
            time.sleep(0.05)
        detail = self._stderr_tail()
        self._terminate_process()
        raise OverheadVideoError(
            "Native dual-camera capture did not admit both streams"
            + (f": {detail}" if detail else ".")
        )

    def _validate_ready(self, ready: dict[str, Any]) -> None:
        if (
            ready.get("schema_version") != READY_SCHEMA
            or ready.get("status") != "recording"
            or ready.get("session_count") != 1
            or ready.get("common_session_running") is not True
            or ready.get("independent_camera_sessions") != 0
        ):
            raise OverheadVideoError("Native recorder readiness is incomplete.")
        after_start = _stage(ready, "after_start")
        for role in ("c922", "d405"):
            expected = self.contract["devices"][role]
            state = after_start.get(role)
            stream = _stream(ready, role)
            if (
                not isinstance(state, dict)
                or state.get("localized_name") != expected["exact_localized_name"]
                or state.get("unique_id") != expected["exact_unique_id"]
                or state.get("model_id") != expected["exact_model_id"]
                or state.get("format_index") != expected["format_index"]
                or state.get("width") != expected["width"]
                or state.get("height") != expected["height"]
                or state.get("subtype") != expected["media_subtype_fourcc"]
                or not math.isclose(
                    float(state.get("minimum_duration_seconds")),
                    float(expected["frame_duration_seconds"]),
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
                or after_start.get(f"{role}_input_admitted") is not True
                or after_start.get(f"{role}_output_admitted") is not True
                or after_start.get(f"{role}_output_bound_to_exact_input") is not True
                or stream.get("writer_append_count", 0) < 1
                or stream.get("writer_status") != "writing"
                or stream.get("errors") != []
            ):
                raise OverheadVideoError(
                    f"Native recorder did not reach exact {role} first-frame readiness."
                )

    def _starting_stream(self, role: str) -> dict[str, Any]:
        device = self.contract["devices"][role]
        overhead = role == "c922"
        return {
            "schema_version": (
                OVERHEAD_VIDEO_SCHEMA if overhead else WRIST_VIDEO_SCHEMA
            ),
            "status": "recording",
            "camera_name": device["exact_localized_name"],
            "camera_unique_id": device["exact_unique_id"],
            "camera_model_id": device["exact_model_id"],
            "configured_width": device["width"],
            "configured_height": device["height"],
            "configured_fps": device["supported_fps"],
            "configured_pixel_format": device["media_subtype_fourcc"],
            "orientation_rotation_degrees": 180 if overhead else 0,
            "metric_depth": False,
            "video_path": str(
                (
                    self.overhead_source_path
                    if overhead
                    else self.wrist_source_path
                ).relative_to(self.draft)
            ),
            "browser_video_path": (
                self.overhead_browser_path.name
                if overhead
                else self.wrist_browser_path.name
            ),
            "callback_timestamp_path": str(self.events_path.relative_to(self.draft)),
            "capture_mechanism": "one_native_avcapture_session",
            "diagnostic_only": True,
            "is_training_data": False,
        }

    @staticmethod
    def _claim_limits() -> dict[str, bool]:
        return {
            "camera_exposure_synchronization": False,
            "metric_depth": False,
            "physical_authority": False,
            "task_success": False,
        }

    def ensure_running(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is not None:
            raise OverheadVideoError(
                "Native dual-camera capture stopped before the episode ended"
                + (f": {self._stderr_tail()}" if self._stderr_tail() else ".")
            )
        self._observe_event_progress()

    def _observe_event_progress(self) -> None:
        now = self._clock()
        try:
            size = self.events_path.stat().st_size
        except OSError:
            size = 0
        if size > self.event_bytes_observed:
            self.event_bytes_observed = size
            self.last_event_growth_monotonic = now
            return
        last = self.last_event_growth_monotonic or self.started_monotonic
        if last is not None and now - last > self.source_stall_timeout_seconds:
            raise OverheadVideoError(
                "Native dual-camera callback ledger stopped growing for "
                f"{now - last:.3f} seconds."
            )

    def finish(
        self,
        *,
        action_started_monotonic: float | None,
        action_stopped_monotonic: float | None,
        post_roll_seconds: float,
    ) -> dict[str, Any]:
        if self.process is None or self.started_monotonic is None:
            raise OverheadVideoError("Native dual-camera recorder was not started.")
        process = self.process
        if process.poll() is None and action_stopped_monotonic is not None:
            deadline = action_stopped_monotonic + max(0.0, post_roll_seconds)
            while self._clock() < deadline and process.poll() is None:
                self.ensure_running()
                time.sleep(min(0.05, max(0.0, deadline - self._clock())))
        stop_requested = self._clock()
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
        try:
            return_code = process.wait(timeout=self.shutdown_timeout_seconds)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                return_code = process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                process.kill()
                return_code = process.wait(timeout=3.0)
        self._close_log()
        if return_code != 0 or not self.report_path.is_file():
            raise OverheadVideoError(
                "Native dual-camera recorder did not finalize"
                + (f": {self._stderr_tail()}" if self._stderr_tail() else ".")
            )
        report = _load_json(self.report_path, label="native recorder report")
        operational = validate_native_report(
            report,
            devices=self.contract["devices"],
        )
        derivatives = {
            "c922": self._make_browser_derivative(
                source=self.overhead_source_path,
                output=self.overhead_browser_path,
                video_filter="hflip,vflip",
            ),
            "d405": self._make_browser_derivative(
                source=self.wrist_source_path,
                output=self.wrist_browser_path,
                video_filter=None,
            ),
        }
        common = {
            "schema_version": COMMON_SESSION_SCHEMA,
            "capture_mechanism": "one_native_avcapture_session",
            "session_count": 1,
            "independent_camera_sessions": 0,
            "runtime_identity": self.runtime_identity,
            "report_path": str(self.report_path.relative_to(self.draft)),
            "report_sha256": _sha256(self.report_path),
            "callback_timestamp_path": str(self.events_path.relative_to(self.draft)),
            "callback_timestamp_sha256": _sha256(self.events_path),
            "callback_timestamp_bytes": self.events_path.stat().st_size,
            "operational_gates": operational,
            "claim_limits": self._claim_limits(),
        }
        completed_at = self._clock()
        return {
            "overhead": self._finished_stream(
                role="c922",
                report=report,
                derivative=derivatives["c922"],
                common=common,
                action_started_monotonic=action_started_monotonic,
                action_stopped_monotonic=action_stopped_monotonic,
                post_roll_seconds=post_roll_seconds,
                stop_requested_monotonic=stop_requested,
                completed_monotonic=completed_at,
            ),
            "wrist": self._finished_stream(
                role="d405",
                report=report,
                derivative=derivatives["d405"],
                common=common,
                action_started_monotonic=action_started_monotonic,
                action_stopped_monotonic=action_stopped_monotonic,
                post_roll_seconds=post_roll_seconds,
                stop_requested_monotonic=stop_requested,
                completed_monotonic=completed_at,
            ),
            "common_session": common,
        }

    def _make_browser_derivative(
        self,
        *,
        source: Path,
        output: Path,
        video_filter: str | None,
    ) -> dict[str, Any]:
        if not self.ffmpeg_path or not self.ffprobe_path:
            raise OverheadVideoError(
                "ffmpeg and ffprobe are required for browser video derivatives."
            )
        command = [
            self.ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "warning",
            "-i",
            str(source),
            "-an",
        ]
        if video_filter:
            command += ["-vf", video_filter]
        command += [
            "-fps_mode",
            "vfr",
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
            str(output),
        ]
        try:
            result = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise OverheadVideoError(
                f"Browser derivative failed for {source.name}: {error}"
            ) from error
        if result.returncode != 0 or not output.is_file():
            raise OverheadVideoError(
                f"Browser derivative failed for {source.name}: "
                + (result.stderr.strip() or "no output")
            )
        return self._probe(output, configured_fps=None)

    def _probe(self, path: Path, *, configured_fps: float | None) -> dict[str, Any]:
        assert self.ffprobe_path is not None
        result = subprocess.run(
            [
                self.ffprobe_path,
                "-v",
                "error",
                "-show_entries",
                "stream=codec_name,width,height,avg_frame_rate,nb_frames:format=duration,size",
                "-of",
                "json",
                str(path),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=15.0,
            check=False,
        )
        if result.returncode != 0:
            raise OverheadVideoError(
                f"Could not probe {path.name}: {result.stderr.strip()}"
            )
        try:
            observed = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise OverheadVideoError(f"Invalid ffprobe output for {path.name}.") from error
        try:
            observed["container_timing"] = probe_video_container_timing(
                path,
                configured_fps=configured_fps,
                ffprobe_path=self.ffprobe_path,
            )
        except VideoTimingError as error:
            raise OverheadVideoError(
                f"Could not verify container timestamps for {path.name}: {error}"
            ) from error
        return observed

    def _finished_stream(
        self,
        *,
        role: str,
        report: dict[str, Any],
        derivative: dict[str, Any],
        common: dict[str, Any],
        action_started_monotonic: float | None,
        action_stopped_monotonic: float | None,
        post_roll_seconds: float,
        stop_requested_monotonic: float,
        completed_monotonic: float,
    ) -> dict[str, Any]:
        source = self.overhead_source_path if role == "c922" else self.wrist_source_path
        browser = self.overhead_browser_path if role == "c922" else self.wrist_browser_path
        configured_fps = float(self.contract["devices"][role]["supported_fps"])
        source_probe = self._probe(source, configured_fps=configured_fps)
        stream = _stream(report, role)
        source_frames = source_probe["container_timing"]["frame_count"]
        browser_frames = derivative["container_timing"]["frame_count"]
        callback_frames = stream["writer_append_count"]
        if source_frames != callback_frames or browser_frames != source_frames:
            raise OverheadVideoError(
                f"{role} callback/source/browser frame counts do not match."
            )
        start = self.started_monotonic
        assert start is not None
        device = self.contract["devices"][role]
        overhead = role == "c922"
        first_frame_recorder_offset = (
            float(stream["first_host_continuous_ns"]) / 1_000_000_000.0
            - start
        )
        last_frame_recorder_offset = (
            float(stream["last_host_continuous_ns"]) / 1_000_000_000.0
            - start
        )
        action_interval_enclosed = bool(
            action_started_monotonic is not None
            and action_stopped_monotonic is not None
            and first_frame_recorder_offset
            <= action_started_monotonic - start
            <= action_stopped_monotonic - start
            <= last_frame_recorder_offset
        )
        return {
            "schema_version": (
                OVERHEAD_VIDEO_SCHEMA if overhead else WRIST_VIDEO_SCHEMA
            ),
            "status": "completed",
            "camera_name": device["exact_localized_name"],
            "camera_unique_id": device["exact_unique_id"],
            "camera_model_id": device["exact_model_id"],
            "configured_width": device["width"],
            "configured_height": device["height"],
            "configured_fps": configured_fps,
            "configured_pixel_format": device["media_subtype_fourcc"],
            "orientation_rotation_degrees": 180 if overhead else 0,
            "metric_depth": False,
            "video_path": str(source.relative_to(self.draft)),
            "video_sha256": _sha256(source),
            "browser_video_path": browser.name,
            "browser_video_sha256": _sha256(browser),
            "observed_video": source_probe,
            "browser_observed_video": derivative,
            "callback_frame_count": callback_frames,
            "observed_callback_count": stream["output_callback_count"],
            "warmup_excluded_callback_count": stream[
                "warmup_excluded_callback_count"
            ],
            "container_frame_count": source_frames,
            "browser_frame_count": browser_frames,
            "first_source_pts_seconds": stream["first_pts_seconds"],
            "last_source_pts_seconds": stream["last_pts_seconds"],
            "first_host_continuous_ns": stream["first_host_continuous_ns"],
            "last_host_continuous_ns": stream["last_host_continuous_ns"],
            "first_frame_recorder_offset_seconds": (
                first_frame_recorder_offset
            ),
            "last_frame_recorder_offset_seconds": (
                last_frame_recorder_offset
            ),
            "action_interval_enclosed_by_callback_frames": (
                action_interval_enclosed
            ),
            "apple_drop_callback_count": stream["apple_drop_callback_count"],
            "writer_backpressure_count": stream["writer_backpressure_count"],
            "callback_timestamp_path": common["callback_timestamp_path"],
            "callback_timestamp_sha256": common["callback_timestamp_sha256"],
            "native_report_path": common["report_path"],
            "native_report_sha256": common["report_sha256"],
            "capture_mechanism": "one_native_avcapture_session",
            "action_start_video_offset_seconds": (
                action_started_monotonic - start
                if action_started_monotonic is not None
                else None
            ),
            "action_stop_video_offset_seconds": (
                action_stopped_monotonic - start
                if action_stopped_monotonic is not None
                else None
            ),
            "post_roll_seconds_configured": float(post_roll_seconds),
            "post_roll_seconds_observed": (
                max(0.0, stop_requested_monotonic - action_stopped_monotonic)
                if action_stopped_monotonic is not None
                else None
            ),
            "video_finalization_seconds": max(
                0.0, completed_monotonic - stop_requested_monotonic
            ),
            "diagnostic_only": True,
            "is_training_data": False,
            "timestamp_semantics": {
                "source_pts": "avfoundation_sample_presentation_timestamp",
                "host_clock": "mach_continuous_time",
                "camera_exposure_timestamps": False,
                "cross_camera_exposure_synchronized": False,
            },
            "claim_limits": self._claim_limits(),
        }

    def _stderr_tail(self) -> str:
        try:
            rows = self.stderr_path.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
        except OSError:
            return ""
        return " | ".join(row.strip() for row in rows[-8:] if row.strip())

    def _terminate_process(self) -> None:
        process = self.process
        if process is None or process.poll() is not None:
            self._close_log()
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=3.0)
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
            process.wait(timeout=3.0)
        self._close_log()

    def _close_log(self) -> None:
        if self.log_handle is not None:
            self.log_handle.close()
            self.log_handle = None


__all__ = [
    "COMMON_SESSION_SCHEMA",
    "REPORT_SCHEMA",
    "NativeDualCameraRecorder",
    "validate_native_report",
]

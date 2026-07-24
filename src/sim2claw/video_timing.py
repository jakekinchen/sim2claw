"""Deterministic container-timing diagnostics for recorded video.

The metrics in this module describe encoded/container presentation timestamps.
They are not camera exposure timestamps, device clocks, or proof that the
camera itself dropped or duplicated a frame.
"""

from __future__ import annotations

import json
import math
import shutil
import statistics
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "sim2claw.video_container_timing.v1"


class VideoTimingError(RuntimeError):
    """Container timing could not be measured without inventing a value."""


def _finite_float(value: object, *, label: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise VideoTimingError(f"{label} is not numeric.") from error
    if not math.isfinite(parsed):
        raise VideoTimingError(f"{label} is not finite.")
    return parsed


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise VideoTimingError("A percentile requires at least one interval.")
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return float(ordered[lower] * (1.0 - weight) + ordered[upper] * weight)


def summarize_video_container_timing(
    frames: Sequence[Mapping[str, Any]],
    *,
    configured_fps: float | None,
) -> dict[str, Any]:
    """Summarize ffprobe frame rows without claiming device synchronization."""

    if len(frames) < 2:
        raise VideoTimingError("At least two video frames are required.")
    pts: list[float] = []
    repeat_picture_count = 0
    for index, frame in enumerate(frames):
        value = frame.get("best_effort_timestamp_time")
        if value is None:
            value = frame.get("pts_time")
        pts.append(_finite_float(value, label=f"frame {index} PTS"))
        repeat_picture_count += max(0, int(frame.get("repeat_pict") or 0))

    intervals = [right - left for left, right in zip(pts, pts[1:])]
    duplicate_pts_count = sum(interval == 0.0 for interval in intervals)
    non_monotonic_interval_count = sum(interval < 0.0 for interval in intervals)
    positive = [interval for interval in intervals if interval > 0.0]
    if not positive:
        raise VideoTimingError("Video has no positive presentation interval.")

    fps = None
    nominal = None
    if configured_fps is not None:
        fps = _finite_float(configured_fps, label="configured FPS")
        if fps <= 0.0:
            raise VideoTimingError("Configured FPS must be positive.")
        nominal = 1.0 / fps

    inferred_missing_intervals = 0
    large_gap_count = 0
    if nominal is not None:
        for interval in positive:
            inferred_missing_intervals += max(0, int(round(interval / nominal)) - 1)
            large_gap_count += int(interval > nominal * 1.5)

    return {
        "schema_version": SCHEMA_VERSION,
        "status": (
            "observed_container_timing"
            if duplicate_pts_count == 0 and non_monotonic_interval_count == 0
            else "invalid_container_timing"
        ),
        "frame_count": len(pts),
        "first_pts_seconds": pts[0],
        "last_pts_seconds": pts[-1],
        "configured_fps": fps,
        "nominal_interval_seconds": nominal,
        "interval_seconds": {
            "minimum": min(positive),
            "median": statistics.median(positive),
            "p95": _percentile(positive, 0.95),
            "maximum": max(positive),
        },
        "duplicate_pts_count": duplicate_pts_count,
        "non_monotonic_interval_count": non_monotonic_interval_count,
        "repeat_picture_count": repeat_picture_count,
        "large_gap_count": large_gap_count if nominal is not None else None,
        "inferred_missing_frame_intervals": (
            inferred_missing_intervals if nominal is not None else None
        ),
        "semantics": {
            "clock": "encoded_container_presentation_timestamps",
            "camera_exposure_timestamps": False,
            "device_synchronized": False,
            "proves_camera_frame_drop": False,
            "proves_camera_frame_duplication": False,
            "large_gap_interpretation": (
                "Intervals above 1.5 configured frame periods are diagnostic "
                "container gaps, not independently observed camera drops."
            ),
        },
    }


def probe_video_container_timing(
    path: Path,
    *,
    configured_fps: float | None,
    ffprobe_path: str | None = None,
    timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    """Probe one finalized video and return only bounded timing statistics."""

    if not path.is_file():
        raise VideoTimingError(f"Video is unavailable: {path}")
    ffprobe = ffprobe_path or shutil.which("ffprobe")
    if not ffprobe:
        raise VideoTimingError("ffprobe is required for container timing.")
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_frames",
                "-show_entries",
                "frame=best_effort_timestamp_time,pts_time,repeat_pict",
                "-of",
                "json",
                str(path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise VideoTimingError(f"Could not probe video timing: {error}") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or f"ffprobe exited {result.returncode}"
        raise VideoTimingError(f"Could not probe video timing: {detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise VideoTimingError("ffprobe timing output is not valid JSON.") from error
    frames = payload.get("frames")
    if not isinstance(frames, list):
        raise VideoTimingError("ffprobe timing output has no frame rows.")
    rows = [row for row in frames if isinstance(row, Mapping)]
    if len(rows) != len(frames):
        raise VideoTimingError("ffprobe timing output contains malformed frame rows.")
    return summarize_video_container_timing(rows, configured_fps=configured_fps)


__all__ = [
    "SCHEMA_VERSION",
    "VideoTimingError",
    "probe_video_container_timing",
    "summarize_video_container_timing",
]

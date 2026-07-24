from __future__ import annotations

import copy

import pytest

from sim2claw.video_timing import (
    SCHEMA_VERSION,
    VideoTimingError,
    summarize_video_container_timing,
)


def _frames(*timestamps: float) -> list[dict[str, object]]:
    return [
        {
            "best_effort_timestamp_time": f"{timestamp:.9f}",
            "repeat_pict": 0,
        }
        for timestamp in timestamps
    ]


def test_container_timing_reports_monotonic_pts_without_device_claims() -> None:
    report = summarize_video_container_timing(
        _frames(0.0, 1 / 30, 2 / 30, 3 / 30),
        configured_fps=30,
    )
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["status"] == "observed_container_timing"
    assert report["frame_count"] == 4
    assert report["duplicate_pts_count"] == 0
    assert report["non_monotonic_interval_count"] == 0
    assert report["inferred_missing_frame_intervals"] == 0
    assert report["semantics"]["camera_exposure_timestamps"] is False
    assert report["semantics"]["device_synchronized"] is False
    assert report["semantics"]["proves_camera_frame_drop"] is False


def test_container_timing_distinguishes_duplicate_reorder_and_gap() -> None:
    frames = _frames(0.0, 1 / 30, 1 / 30, 0.02, 4 / 30)
    frames[-1]["repeat_pict"] = 1
    report = summarize_video_container_timing(frames, configured_fps=30)
    assert report["status"] == "invalid_container_timing"
    assert report["duplicate_pts_count"] == 1
    assert report["non_monotonic_interval_count"] == 1
    assert report["repeat_picture_count"] == 1
    assert report["large_gap_count"] >= 1
    assert report["inferred_missing_frame_intervals"] >= 1


def test_container_timing_fails_closed_for_missing_or_nonfinite_pts() -> None:
    with pytest.raises(VideoTimingError, match="At least two"):
        summarize_video_container_timing(_frames(0.0), configured_fps=30)
    malformed = copy.deepcopy(_frames(0.0, 0.1))
    malformed[1]["best_effort_timestamp_time"] = "nan"
    with pytest.raises(VideoTimingError, match="not finite"):
        summarize_video_container_timing(malformed, configured_fps=30)

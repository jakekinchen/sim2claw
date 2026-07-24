from __future__ import annotations

from pathlib import Path

from sim2claw.overhead_video import (
    DEFAULT_WRIST_CAMERA_NAME,
    WRIST_VIDEO_SCHEMA,
    WristVideoRecorder,
)


def test_wrist_recorder_uses_exact_low_bandwidth_d405_contract(
    tmp_path: Path,
) -> None:
    recorder = WristVideoRecorder(tmp_path / "wrist_d405.mkv")

    assert recorder.camera_name == DEFAULT_WRIST_CAMERA_NAME
    assert recorder.schema_version == WRIST_VIDEO_SCHEMA
    assert (recorder.width, recorder.height, recorder.fps) == (424, 240, 5)
    assert recorder.source_pixel_format == "uyvy422"
    assert recorder.video_filter == ""
    assert recorder.metric_depth is False
    assert recorder.browser_output_path.name == "wrist_d405.browser.mp4"
    assert recorder._encoder_args() == [
        "-c:v",
        "ffv1",
        "-level",
        "3",
        "-g",
        "1",
        "-f",
        "matroska",
    ]
    assert recorder._browser_encoder_args() == [
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
    ]

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from sim2claw.d405_board_grid_visibility import diagnose_board_grid_visibility
from sim2claw.paths import REPO_ROOT


def _write_grid_video(path: Path, *, partial_robot_far_edge: bool) -> None:
    width, height = 640, 480
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        5.0,
        (width, height),
    )
    assert writer.isOpened()
    for _ in range(3):
        image = np.zeros((height, width, 3), dtype=np.uint8)
        x_values = np.linspace(80, 560, 9).astype(int)
        y_values = (
            np.linspace(-130, 390, 9).astype(int)
            if partial_robot_far_edge
            else np.linspace(70, 410, 9).astype(int)
        )
        for x in x_values:
            cv2.line(
                image,
                (int(x), max(0, int(y_values[0]))),
                (int(x), int(y_values[-1])),
                (255, 255, 255),
                2,
            )
        for y in y_values:
            if 0 <= y < height:
                cv2.line(
                    image,
                    (int(x_values[0]), int(y)),
                    (int(x_values[-1]), int(y)),
                    (255, 255, 255),
                    2,
                )
        writer.write(image)
    writer.release()


def test_full_direct_grid_passes_only_with_adjacent_frames(tmp_path: Path) -> None:
    video = tmp_path / "full-grid.avi"
    _write_grid_video(video, partial_robot_far_edge=False)

    receipt = diagnose_board_grid_visibility(video)

    assert receipt["verdict"]["passed"] is True
    assert len(receipt["adjacent_settled_frame_indices"]) >= 2
    assert receipt["best_frame"]["row_axis"]["directly_supported_grid_line_count"] == 9
    assert receipt["best_frame"]["column_axis"]["directly_supported_grid_line_count"] == 9
    assert all(
        item["direct_multi_segment_support"]
        for item in receipt["outer_playing_grid_boundary_support"].values()
    )
    assert receipt["nonmetric"] is True
    assert receipt["april_tag_used"] is False
    assert receipt["verdict"]["grants_metric_or_physical_authority"] is False


def test_v24_like_robot_far_crop_fails_closed_as_partial(tmp_path: Path) -> None:
    video = tmp_path / "v24-like-partial-grid.avi"
    _write_grid_video(video, partial_robot_far_edge=True)

    receipt = diagnose_board_grid_visibility(video)

    assert receipt["verdict"]["passed"] is False
    assert receipt["verdict"]["classification"] == (
        "partial_grid_visibility_not_outer_quadrilateral"
    )
    assert receipt["best_frame"]["row_axis"]["directly_supported_grid_line_count"] < 9
    assert receipt["adjacent_settled_frame_indices"] == []
    assert all(
        item["extrapolation_required"]
        for item in receipt["outer_playing_grid_boundary_support"].values()
    )


def test_existing_v24_capture_is_a_partial_failure_when_present() -> None:
    video = (
        REPO_ROOT
        / "runs"
        / "physical_excitation"
        / "20260725-follower-only-v1"
        / "wrist-view-reposition-v24-motion-capture"
        / "stage-1"
        / "final_hold_camera"
        / "wrist_d405.browser.mp4"
    )
    if not video.is_file():
        pytest.skip("ignored local v24 evidence is not present")

    receipt = diagnose_board_grid_visibility(video)

    assert receipt["verdict"]["passed"] is False
    assert receipt["input_lineage"]["decoded_frame_count"] == 40
    assert receipt["best_frame"]["frame_index"] == 39
    assert receipt["best_frame"]["timestamp_s"] == pytest.approx(7.8)
    assert receipt["adjacent_settled_frame_indices"] == []

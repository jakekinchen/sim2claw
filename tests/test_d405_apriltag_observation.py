from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from sim2claw.d405_apriltag_observation import (
    D405AprilTagObservationError,
    load_contract,
    observe_d405_apriltag,
)


def _write_tag_image(path: Path, *, include_tag: bool = True) -> None:
    image = np.full((240, 424), 255, dtype=np.uint8)
    if include_tag:
        marker = cv2.aruco.generateImageMarker(
            cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11),
            0,
            120,
        )
        image[60:180, 152:272] = marker
    assert cv2.imwrite(str(path), image)


def _write_native_video_and_report(directory: Path) -> tuple[Path, Path]:
    source = directory / "wrist_d405.native.mov"
    writer = cv2.VideoWriter(
        str(source),
        cv2.VideoWriter_fourcc(*"mp4v"),
        5.0,
        (424, 240),
    )
    assert writer.isOpened()
    image_path = directory / "tag.png"
    _write_tag_image(image_path)
    frame = cv2.imread(str(image_path))
    for _ in range(3):
        writer.write(frame)
    writer.release()
    camera = {
        "role": "d405",
        "localized_name": "Intel(R) RealSense(TM) Depth Camera 405  Depth",
        "model_id": "UVC Camera VendorID_32902 ProductID_2907",
        "unique_id": "fixture-d405",
        "width": 424,
        "height": 240,
        "subtype": "yuvs",
        "format_index": 5,
        "minimum_duration_seconds": 0.2,
        "maximum_duration_seconds": 0.2,
    }
    stages = []
    for name in ("before_commit", "after_commit", "after_start"):
        stages.append(
            {
                "name": name,
                "d405": camera,
                "d405_input_admitted": True,
                "d405_output_admitted": True,
                "d405_output_bound_to_exact_input": True,
            }
        )
    report = {
        "schema_version": "sim2claw.native_dual_camera_recorder_report.v1",
        "status": "completed",
        "session_count": 1,
        "independent_camera_sessions": 0,
        "stages": stages,
        "streams": [
            {
                "role": "d405",
                "output_path": source.name,
                "writer_status": "completed",
                "writer_append_count": 3,
                "errors": [],
                "first_pts_seconds": 1.0,
                "last_pts_seconds": 1.4,
            }
        ],
    }
    report_path = directory / "native_camera_report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return source, report_path


def test_contract_keeps_nominal_size_and_authority_false() -> None:
    contract = load_contract()
    assert contract["tag"]["family"] == "tag36h11"
    assert contract["tag"]["id"] == 0
    assert contract["tag"]["nominal_black_border_side_m"] == 0.08
    assert contract["tag"]["physical_black_border_measured"] is False
    assert all(value is False for value in contract["authority"].values())


def test_image_detection_is_diagnostic_without_native_capture_binding(
    tmp_path: Path,
) -> None:
    source = tmp_path / "tag.png"
    _write_tag_image(source)
    receipt = observe_d405_apriltag(
        source_path=source,
        output_path=tmp_path / "receipt.json",
        selected_frame_output=tmp_path / "selected.png",
    )
    assert receipt["status"] == "target_observed"
    assert receipt["tag"]["selected_detection"]["frame_index"] == 0
    assert receipt["capture_binding"] is None
    assert (
        receipt["registration_readiness"][
            "source_lineage_bound_to_native_d405_capture"
        ]
        is False
    )
    assert receipt["registration_readiness"]["metric_scale_established"] is False
    assert receipt["authority"]["robot_motion"] is False
    assert (tmp_path / "selected.png").is_file()


def test_native_video_binding_removes_only_capture_lineage_fact(
    tmp_path: Path,
) -> None:
    source, report = _write_native_video_and_report(tmp_path)
    receipt = observe_d405_apriltag(
        source_path=source,
        output_path=tmp_path / "receipt.json",
        capture_report_path=report,
    )
    readiness = receipt["registration_readiness"]
    assert receipt["status"] == "target_observed"
    assert readiness["source_lineage_bound_to_native_d405_capture"] is True
    assert "native_d405_capture_report_binding" not in readiness["missing_facts"]
    assert "physical_black_border_side_measurement" in readiness["missing_facts"]
    assert "exact_mode_d405_rgb_intrinsics_and_distortion" in readiness["missing_facts"]
    assert readiness["wrist_extrinsics_established"] is False


def test_no_tag_stays_a_truthful_negative(tmp_path: Path) -> None:
    source = tmp_path / "blank.png"
    _write_tag_image(source, include_tag=False)
    receipt = observe_d405_apriltag(
        source_path=source,
        output_path=tmp_path / "receipt.json",
    )
    assert receipt["status"] == "target_not_observed"
    assert receipt["tag"]["target_detection_count"] == 0
    assert receipt["registration_readiness"]["tag_pixel_observation_available"] is False


def test_capture_report_must_bind_exact_source(tmp_path: Path) -> None:
    source, report = _write_native_video_and_report(tmp_path)
    other = tmp_path / "other.mov"
    other.write_bytes(source.read_bytes())
    with pytest.raises(
        D405AprilTagObservationError,
        match="not the D405 output bound",
    ):
        observe_d405_apriltag(
            source_path=other,
            output_path=tmp_path / "receipt.json",
            capture_report_path=report,
        )

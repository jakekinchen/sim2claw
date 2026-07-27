from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from sim2claw.cli import build_parser
from sim2claw.img5431_multitag_observation import (
    CONTRACT_PATH,
    Img5431ObservationError,
    _detect_frame,
    _make_detector,
    load_contract,
    observe_img5431_multitags,
)


def test_contract_preserves_duplicate_id_ambiguity_and_denies_pose_authority() -> None:
    contract = load_contract()

    assert contract["tags"]["required_integer_ids"] == list(range(7))
    assert (
        contract["tags"]["integer_id_is_cross_frame_physical_identity"]
        is False
    )
    assert contract["tags"]["operator_declared_full_square_side_m"] == 0.02
    assert contract["tags"]["black_boundary_side_m"] is None
    assert contract["authority"]["pixel_observations"] is True
    assert contract["authority"]["camera_trajectory"] is False
    assert contract["authority"]["metric_bundle_adjustment"] is False
    assert contract["authority"]["physical_authority"] is False


def test_strict_detector_retains_all_ids_and_two_frame_local_id_zero_instances() -> None:
    contract = load_contract()
    detector = _make_detector(contract["detector"])
    dictionary = cv2.aruco.getPredefinedDictionary(
        cv2.aruco.DICT_APRILTAG_36h11
    )
    canvas = np.full((900, 1200), 255, dtype=np.uint8)
    placements = [
        (0, 40, 40),
        (0, 200, 40),
        (1, 360, 40),
        (2, 520, 40),
        (3, 680, 40),
        (4, 840, 40),
        (5, 40, 260),
        (6, 200, 260),
    ]
    for tag_id, x, y in placements:
        marker = cv2.aruco.generateImageMarker(dictionary, tag_id, 120)
        canvas[y : y + 120, x : x + 120] = marker
    frame = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)

    rows = _detect_frame(frame, frame_index=30, detector=detector)

    assert {row["tag_id"] for row in rows} == set(range(7))
    zeros = [row for row in rows if row["tag_id"] == 0]
    assert len(zeros) == 2
    assert len({row["instance_key"] for row in zeros}) == 2
    assert all(
        row["integer_id_used_as_physical_instance_identity"] is False
        for row in rows
    )


def test_source_byte_drift_fails_before_video_inference(tmp_path: Path) -> None:
    source = tmp_path / "IMG_5431.MOV"
    source.write_bytes(b"not-the-bound-video")

    with pytest.raises(Img5431ObservationError, match="source bytes"):
        observe_img5431_multitags(
            source_path=source,
            output_path=tmp_path / "manifest.json",
        )


def test_cli_exposes_explicit_source_contract_and_output(tmp_path: Path) -> None:
    output = tmp_path / "manifest.json"
    args = build_parser().parse_args(
        [
            "observe-img5431-multitags",
            "--source",
            "/Users/kelly/Downloads/IMG_5431.MOV",
            "--output",
            str(output),
        ]
    )

    assert args.contract == CONTRACT_PATH
    assert args.output == output

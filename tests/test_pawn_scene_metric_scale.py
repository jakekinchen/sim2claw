from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_scene_metric_scale import (
    intersect_image_rays_with_parallel_plane,
    load_metric_scale_contract,
    run_metric_scale_plausibility,
)


_ROBO_SCAN_ROOT_VALUE = os.environ.get("SIM2CLAW_ROBO_SCAN_ROOT")
ROBO_SCAN_ROOT = (
    Path(_ROBO_SCAN_ROOT_VALUE).expanduser() if _ROBO_SCAN_ROOT_VALUE else None
)
FRAME_PATH = (
    ROBO_SCAN_ROOT
    / "artifacts"
    / "private"
    / "IMG_5349-0079c19d-global-sfm-v1"
    / "images"
    / "frame-000001.jpg"
    if ROBO_SCAN_ROOT is not None
    else Path()
)
SOURCE_VIDEO_PATH = (
    ROBO_SCAN_ROOT / "artifacts" / "incoming" / "IMG_5349" / "IMG_5349.MOV"
    if ROBO_SCAN_ROOT is not None
    else Path()
)
REAL_SPLAT_PATH = (
    REPO_ROOT
    / "artifacts"
    / "private"
    / "releases"
    / "img5349-3dgs-20260719"
    / "IMG_5349-primary-real-splat.ply"
)


def test_contract_keeps_nominal_print_and_authority_separate() -> None:
    contract = load_metric_scale_contract()
    assert contract["tag"]["physical_print_dimension_measured"] is False
    assert contract["source_bindings"]["scene_identity_only"] is True
    assert all(value is False for value in contract["authority"].values())


def test_parallel_plane_backprojection_recovers_metric_square() -> None:
    matrix = np.asarray(((800.0, 0.0, 320.0), (0.0, 800.0, 240.0), (0.0, 0.0, 1.0)))
    distortion = np.zeros(4)
    points = np.asarray(
        ((-0.2, -0.2, 1.0), (0.2, -0.2, 1.0), (0.2, 0.2, 1.0), (-0.2, 0.2, 1.0))
    )
    pixels, _ = cv2.projectPoints(points, np.zeros(3), np.zeros(3), matrix, distortion)
    recovered = intersect_image_rays_with_parallel_plane(
        pixels.reshape(-1, 2),
        camera_matrix=matrix,
        distortion=distortion,
        plane_normal_camera=np.asarray((0.0, 0.0, 1.0)),
        tag_origin_camera=np.asarray((0.0, 0.0, 1.0)),
        board_height_above_tag_plane_m=0.0,
    )
    edge_lengths = np.linalg.norm(np.roll(recovered, -1, axis=0) - recovered, axis=1)
    assert edge_lengths == pytest.approx(np.full(4, 0.4), abs=1e-9)


@pytest.mark.skipif(
    not (FRAME_PATH.is_file() and SOURCE_VIDEO_PATH.is_file() and REAL_SPLAT_PATH.is_file()),
    reason="owner-provided IMG_5349 source assets unavailable",
)
def test_live_scene_supports_355p6mm_and_rejects_301p3mm_as_nominal_print_fit(
    tmp_path: Path,
) -> None:
    receipt = run_metric_scale_plausibility(
        frame_path=FRAME_PATH,
        source_video_path=SOURCE_VIDEO_PATH,
        real_splat_path=REAL_SPLAT_PATH,
        output_root=tmp_path,
    )
    comparisons = {row["id"]: row for row in receipt["candidate_comparisons"]}
    assert comparisons["registered_355p6mm"]["nominal_print_consistent"] is True
    assert comparisons["train_trace_fit_301p3mm"][
        "materially_inconsistent_with_nominal_print"
    ] is True
    assert receipt["decision"]["physical_metric_scale_established"] is False
    assert receipt["decision"]["simulator_parameter_promotion_allowed"] is False
    assert Path(receipt["artifacts"]["overlay_png"]).is_file()
    assert (tmp_path / "metric_scale_plausibility_receipt.json").is_file()

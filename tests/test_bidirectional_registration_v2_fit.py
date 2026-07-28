import json
from pathlib import Path

import numpy as np

from sim2claw.bidirectional_registration_v2_fit import (
    evaluate_fit,
    normalized_projective_dlt,
    project,
)
from sim2claw.paths import REPO_ROOT


ANNOTATIONS = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "bidirectional_pawn_push_v2_registration_fit_annotations_v1.json"
)


def test_normalized_projective_dlt_recovers_synthetic_camera() -> None:
    world = np.asarray(
        [
            [-1.0, -1.0, 0.0],
            [1.0, -1.0, 0.0],
            [1.0, 1.0, 0.0],
            [-1.0, 1.0, 0.0],
            [-0.8, -0.4, 0.7],
            [-0.2, 0.6, 0.8],
            [0.4, -0.5, 0.9],
            [0.9, 0.7, 1.0],
        ],
        dtype=np.float64,
    )
    camera = np.asarray(
        [
            [520.0, 10.0, 320.0, 15.0],
            [-5.0, 515.0, 240.0, -8.0],
            [0.01, -0.02, 1.0, 2.0],
        ],
        dtype=np.float64,
    )
    pixels = project(camera, world)
    fitted, condition = normalized_projective_dlt(world, pixels)
    assert condition < 1e6
    np.testing.assert_allclose(project(fitted, world), pixels, atol=1e-9)


def test_live_fit_is_rejected_without_opening_heldout(tmp_path: Path) -> None:
    receipt = evaluate_fit(ANNOTATIONS, tmp_path / "fit")
    assert receipt["status"] == "rejected_before_heldout"
    assert receipt["heldout_open_count"] == 0
    assert receipt["heldout_inputs_read"] is False
    assert receipt["fit_admitted_for_heldout_open"] is False
    assert receipt["checks"]["board_lattice_rms"] is True
    assert receipt["checks"]["board_lattice_max"] is True
    assert receipt["checks"]["annotation_tip_agreement"] is True
    assert receipt["checks"]["annotation_midpoint_agreement"] is True
    assert receipt["checks"]["fit_hover_reprojection_rms"] is False
    assert receipt["checks"]["fit_hover_reprojection_max"] is False
    assert receipt["fit_projection"]["hover_reprojection_rms_px"] > 6.0
    assert receipt["fit_projection"]["hover_reprojection_max_px"] > 10.0
    candidate = json.loads(
        Path(receipt["candidate_path"]).read_text()
    )
    assert candidate["heldout_open_count"] == 0
    assert candidate["fit_only"] is True

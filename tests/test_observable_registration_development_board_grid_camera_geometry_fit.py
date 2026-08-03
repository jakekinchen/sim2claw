from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/evaluations/observable_registration_development_board_grid_camera_geometry_fit_v1.json"


def test_contract_freezes_four_board_quadrilaterals_and_one_camera() -> None:
    contract = json.loads(CONTRACT.read_text())
    annotations = contract["annotations"]
    assert len(annotations["episodes"]) == 4
    assert all(len(row["points_px"]) == 4 for row in annotations["episodes"])
    assert annotations["pixel_uncertainty_radius"] == 4.0
    assert contract["scene_correspondence"]["local_playing_surface_half_side_m"] == 0.1778
    assert contract["scene_correspondence"]["corner_symmetry_hypotheses"] == 8
    assert contract["camera_family"]["one_shared_vector_required"] is True


def test_contract_is_geometric_development_only_fit() -> None:
    contract = json.loads(CONTRACT.read_text())
    boundary = contract["resource_boundary"]
    assert contract["search"]["objective"] == "shared_board_corner_reprojection_rms_px_only"
    assert boundary["camera_fits_allowed"] == 1
    assert boundary["appearance_fits_allowed"] == 0
    assert boundary["time_fits_allowed"] == 0
    assert boundary["state_or_physics_fits_allowed"] == 0
    assert boundary["validation_reads_allowed"] == 0
    assert boundary["evaluator_heldout_reads_allowed"] == 0
    assert boundary["simulator_replays_allowed"] == 0

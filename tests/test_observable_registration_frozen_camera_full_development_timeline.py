from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/evaluations/observable_registration_frozen_camera_full_development_timeline_v1.json"
OR73 = ROOT / "configs/decisions/observable_registration_development_initial_shared_3d_camera_fit_v1_closeout.json"


def test_camera_vector_is_exactly_inherited_and_refit_closed() -> None:
    contract = json.loads(CONTRACT.read_text())
    or73 = json.loads(OR73.read_text())
    assert contract["selected_camera"]["vector"] == or73["selected_camera"]["vector"]
    assert contract["selected_camera"]["position"] == or73["selected_camera"]["position"]
    assert contract["selected_camera"]["target"] == or73["selected_camera"]["target"]
    assert contract["selected_camera"]["fov_degrees"] == or73["selected_camera"]["fov_degrees"]
    assert contract["selected_camera"]["refit_allowed"] is False


def test_contract_is_full_development_evaluation_with_other_splits_closed() -> None:
    contract = json.loads(CONTRACT.read_text())
    assert contract["timeline"]["development_episode_count"] == 4
    assert contract["timeline"]["evaluation_fps"] == 5.0
    assert contract["timeline"]["physical_orientation"].startswith("hflip")
    boundary = contract["resource_boundary"]
    assert boundary["camera_fits_allowed"] == 0
    assert boundary["appearance_fits_allowed"] == 0
    assert boundary["time_fits_allowed"] == 0
    assert boundary["state_or_physics_fits_allowed"] == 0
    assert boundary["validation_reads_allowed"] == 0
    assert boundary["evaluator_heldout_reads_allowed"] == 0

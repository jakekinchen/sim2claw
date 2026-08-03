from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/evaluations/observable_registration_static_development_full_mesh_comparison_v1.json"


def test_contract_freezes_camera_baseline_and_four_development_episodes() -> None:
    contract = json.loads(CONTRACT.read_text())
    or73 = json.loads((ROOT / contract["sources"]["or73_closeout"]["path"]).read_text())
    or72 = json.loads((ROOT / contract["sources"]["or72_contract"]["path"]).read_text())
    assert contract["camera"]["position"] == or73["selected_camera"]["position"]
    assert contract["camera"]["target"] == or73["selected_camera"]["target"]
    assert contract["camera"]["fov_degrees"] == or73["selected_camera"]["fov_degrees"]
    assert contract["baseline"]["mean_full_frame_linear_pixel_similarity"] == or73["result"]["selected_final_mean_full_frame_similarity"]
    assert contract["baseline"]["mean_tolerant_edge_f1"] == or73["result"]["selected_final_mean_edge_f1"]
    assert len(or72["episodes"]) == 4
    assert {episode["split_role"] for episode in or72["episodes"]} == {"development"}


def test_contract_is_no_refit_and_keeps_validation_and_heldout_closed() -> None:
    contract = json.loads(CONTRACT.read_text())
    renderer = contract["renderer"]
    boundary = contract["resource_boundary"]
    assert renderer["mesh_asset_read_policy"] == "read_each_unique_hash_verified_asset_once_for_all_four_frames"
    assert renderer["mesh_triangle_policy"] == "all_source_triangles_for_every_mesh_definition"
    assert boundary["unique_mesh_asset_reads_allowed"] == 18
    assert boundary["camera_fits_allowed"] == 0
    assert boundary["appearance_fits_allowed"] == 0
    assert boundary["time_fits_allowed"] == 0
    assert boundary["state_or_physics_fits_allowed"] == 0
    assert boundary["validation_reads_allowed"] == 0
    assert boundary["evaluator_heldout_reads_allowed"] == 0
    assert contract["acceptance"]["strict_edge_improvement_required"] is True

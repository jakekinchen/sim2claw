from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/evaluations/observable_registration_native_full_mesh_development_timeline_v1.json"


def test_contract_preserves_or74_timeline_metric_and_acceptance() -> None:
    contract = json.loads(CONTRACT.read_text())
    or74 = json.loads((ROOT / contract["sources"]["or74_contract"]["path"]).read_text())
    assert contract["timeline"] == or74["timeline"]
    assert contract["metric"] == or74["metric"]
    assert contract["acceptance"] == or74["acceptance"]
    assert contract["gates"]["expected_total_frame_count"] == 423


def test_contract_uses_exact_native_seam_without_refit_or_split_expansion() -> None:
    contract = json.loads(CONTRACT.read_text())
    boundary = contract["resource_boundary"]
    assert contract["renderer"]["implementation"] == "or78_full_source_mesh_stream_plus_or79_byte_equivalent_native_depth_rasterizer"
    assert contract["renderer"]["mesh_triangle_policy"] == "all_source_triangles_for_every_mesh_definition"
    assert boundary["physical_frames_compared_allowed"] == 423
    assert boundary["native_frames_rendered_allowed"] == 423
    assert boundary["camera_fits_allowed"] == 0
    assert boundary["appearance_fits_allowed"] == 0
    assert boundary["time_fits_allowed"] == 0
    assert boundary["state_or_physics_fits_allowed"] == 0
    assert boundary["validation_reads_allowed"] == 0
    assert boundary["evaluator_heldout_reads_allowed"] == 0

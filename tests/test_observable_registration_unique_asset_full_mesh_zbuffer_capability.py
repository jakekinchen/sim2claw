from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/evaluations/observable_registration_unique_asset_full_mesh_zbuffer_capability_v1.json"
SCENE = ROOT / "src/sim2claw/studio_web/publication/pawn_bg_ranked_grasp_v1/scene_manifest.json"


def test_manifest_derives_eighteen_unique_assets_for_thirty_six_definitions() -> None:
    scene = json.loads(SCENE.read_text())
    filenames = {Path(mesh["asset_url"]).name for mesh in scene["meshes"]}
    assert len(scene["meshes"]) == 36
    assert len(filenames) == 18


def test_contract_caches_unique_assets_and_uses_full_source_meshes() -> None:
    contract = json.loads(CONTRACT.read_text())
    renderer = contract["renderer"]
    gates = contract["gates"]
    boundary = contract["resource_boundary"]
    assert renderer["mesh_asset_read_policy"] == "read_each_unique_hash_verified_asset_once"
    assert renderer["mesh_triangle_policy"] == "all_source_triangles_for_every_mesh_definition"
    assert gates["expected_manifest_derived_unique_mesh_asset_count"] == 18
    assert gates["expected_unique_mesh_asset_reads"] == 18
    assert gates["expected_mesh_source_triangle_count"] == gates["expected_mesh_raster_triangle_count"] == 802680
    assert boundary["unique_mesh_asset_reads_allowed"] == 18
    assert boundary["physical_video_reads_allowed"] == 0
    assert boundary["validation_reads_allowed"] == 0
    assert boundary["evaluator_heldout_reads_allowed"] == 0
    assert boundary["parameter_fits_allowed"] == 0

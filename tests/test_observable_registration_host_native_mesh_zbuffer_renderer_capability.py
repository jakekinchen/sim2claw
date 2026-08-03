from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

from sim2claw.observable_registration_host_native_mesh_zbuffer_renderer_capability import (
    deterministic_triangle_indices,
    load_binary_stl_triangles,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/evaluations/observable_registration_host_native_mesh_zbuffer_renderer_capability_v1.json"


def test_binary_stl_loader_and_decimation_are_deterministic(tmp_path: Path) -> None:
    triangle = struct.pack("<12fH", *([0.0] * 12), 0)
    path = tmp_path / "one.stl"
    path.write_bytes(b"x" * 80 + struct.pack("<I", 1) + triangle)
    loaded = load_binary_stl_triangles(path)
    assert loaded.shape == (1, 3, 3)
    assert deterministic_triangle_indices(10, 4).tolist() == [0, 2, 5, 7]
    assert deterministic_triangle_indices(3, 10).tolist() == [0, 1, 2]


def test_contract_is_one_frame_footage_blind_and_decimation_explicit() -> None:
    contract = json.loads(CONTRACT.read_text())
    renderer = contract["renderer"]
    assert renderer["maximum_triangles_per_mesh_instance"] == 512
    assert renderer["mesh_triangle_policy"].startswith("deterministic")
    boundary = contract["resource_boundary"]
    assert boundary["capability_frames_allowed"] == 1
    assert boundary["mesh_asset_reads_allowed"] == 19
    assert boundary["physical_video_reads_allowed"] == 0
    assert boundary["validation_reads_allowed"] == 0
    assert boundary["evaluator_heldout_reads_allowed"] == 0
    assert boundary["parameter_fits_allowed"] == 0
    assert contract["claim_limits"]["mesh_source_exact_but_raster_decimated"] is True
    assert contract["claim_limits"]["mujoco_raster_equivalence"] is False

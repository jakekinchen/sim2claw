from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/evaluations/observable_registration_native_rasterizer_byte_equivalence_v1.json"
NATIVE = ROOT / "tools/renderer/or79_triangle_rasterizer.c"


def test_contract_requires_exact_pixels_and_ten_x_speedup() -> None:
    contract = json.loads(CONTRACT.read_text())
    assert contract["gates"]["require_native_pixels_byte_identical_to_reference"] is True
    assert contract["gates"]["minimum_native_raster_stage_speedup"] == 10.0
    assert contract["compiler"]["fast_math_allowed"] is False
    assert contract["compiler"]["external_source_dependencies_allowed"] is False


def test_contract_keeps_footage_validation_and_heldout_closed() -> None:
    contract = json.loads(CONTRACT.read_text())
    boundary = contract["resource_boundary"]
    assert boundary["development_state_trace_reads_allowed"] == 1
    assert boundary["development_candidate_reference_reads_allowed"] == 1
    assert boundary["physical_video_reads_allowed"] == 0
    assert boundary["validation_reads_allowed"] == 0
    assert boundary["evaluator_heldout_reads_allowed"] == 0
    assert boundary["parameter_fits_allowed"] == 0
    assert boundary["paid_compute_allowed"] is False
    assert NATIVE.read_text().count("rasterize_triangles") == 1

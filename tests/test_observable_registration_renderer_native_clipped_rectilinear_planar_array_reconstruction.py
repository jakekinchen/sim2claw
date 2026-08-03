from __future__ import annotations

import numpy as np

from sim2claw.observable_registration_renderer_native_clipped_rectilinear_planar_array_reconstruction import (
    _array_triangle_stream,
    _recover_segments,
    load_planar_array_reconstruction_contract,
)


def test_or122_contract_freezes_five_real_segments_and_gated_corroboration() -> None:
    contract = load_planar_array_reconstruction_contract()

    assert contract["geometry"]["segment_count"] == 5
    assert contract["geometry"]["triangle_count_per_segment"] == 248
    assert contract["geometry"]["shared_scene_zbuffer"] is True
    assert contract["geometry"]["pixel_composite_allowed"] is False
    assert contract["split"]["development_positions"] == list(range(1, 8))
    assert contract["split"]["corroboration_positions"] == list(range(8, 12))
    assert contract["split"]["corroboration_requires_development_gate"] is True
    assert contract["resource_boundary"]["geometry_searches_allowed"] == 0
    assert contract["resource_boundary"]["retries_allowed"] == 0
    assert contract["claim_limits"]["metric_3d_geometry_calibrated"] is False


def test_recovered_segments_are_exact_three_plus_two_family() -> None:
    import json
    from sim2claw.observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT
    from sim2claw.observable_registration_post_object_persistent_static_spatial_decomposition import load_spatial_decomposition_contract

    contract = load_planar_array_reconstruction_contract()
    or121_contract = load_spatial_decomposition_contract(REPO_ROOT / contract["sources"]["or121_contract"]["path"])
    receipt = json.loads((REPO_ROOT / contract["sources"]["or121_receipt"]["path"]).read_text())
    segments, consensus = _recover_segments(or121_contract, receipt)

    assert len(segments) == 5
    assert consensus.shape == (240, 320)
    assert int(consensus.sum()) == 911


def test_array_stream_symbol_is_callable() -> None:
    assert callable(_array_triangle_stream)

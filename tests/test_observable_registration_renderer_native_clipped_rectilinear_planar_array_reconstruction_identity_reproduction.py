from __future__ import annotations

import json

from sim2claw.observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT
from sim2claw.observable_registration_post_object_persistent_static_spatial_decomposition import load_spatial_decomposition_contract
from sim2claw.observable_registration_renderer_native_clipped_rectilinear_planar_array_reconstruction import _recover_segments
from sim2claw.observable_registration_renderer_native_clipped_rectilinear_planar_array_reconstruction_identity_reproduction import (
    DEFAULT_OUTPUT,
    evaluate_once,
    load_identity_reproduction_contract,
)


def test_or122b_contract_binds_new_output_and_original_quarantine() -> None:
    contract = load_identity_reproduction_contract()

    assert contract["experiment_id"] == "OR122B_IDENTITY_BOUND_RENDERER_NATIVE_PLANAR_ARRAY_REPRODUCTION_V1"
    assert contract["sources"]["or122_closeout"]["status"] == "TERMINAL_IMPLEMENTATION_IDENTITY_DRIFT_QUARANTINED"
    assert contract["sources"]["or122_quarantined_receipt"]["admitted"] is False
    assert contract["geometry"]["segment_count"] == 5
    assert contract["geometry"]["triangle_count_per_segment"] == 248
    assert contract["geometry"]["shared_scene_zbuffer"] is True
    assert contract["geometry"]["pixel_composite_allowed"] is False
    assert contract["split"]["development_positions"] == list(range(1, 8))
    assert contract["split"]["corroboration_positions"] == list(range(8, 12))
    assert contract["split"]["corroboration_requires_development_gate"] is True
    assert DEFAULT_OUTPUT.name.endswith("identity_reproduction_v1")


def test_or122b_rederives_the_exact_three_plus_two_segments() -> None:
    contract = load_identity_reproduction_contract()
    or121_contract = load_spatial_decomposition_contract(REPO_ROOT / contract["sources"]["or121_contract"]["path"])
    or121_receipt = json.loads((REPO_ROOT / contract["sources"]["or121_receipt"]["path"]).read_text())

    segments, consensus = _recover_segments(or121_contract, or121_receipt)

    assert len(segments) == 5
    assert segments == [[7, 167, 51, 223], [18, 167, 57, 216], [6, 166, 49, 221], [55, 222, 101, 194], [91, 203, 115, 189]]
    assert consensus.shape == (240, 320)
    assert int(consensus.sum()) == 911


def test_or122b_one_shot_symbol_is_callable() -> None:
    assert callable(evaluate_once)

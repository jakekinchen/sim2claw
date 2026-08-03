from __future__ import annotations

from sim2claw.observable_registration_renderer_native_planar_fixture_full_timeline_propagation import (
    _merged_or119_contract,
    load_planar_fixture_full_timeline_contract,
)


def test_or128_contract_binds_full_timeline_and_no_overlay() -> None:
    contract = load_planar_fixture_full_timeline_contract()

    assert contract["resource_boundary"]["physical_frames_compared_allowed"] == 1210
    assert contract["resource_boundary"]["candidate_videos_allowed"] == 11
    assert contract["fixture"]["physical_pixel_texture_projection"] is False
    assert contract["fixture"]["screen_space_overlay"] is False


def test_or128_merged_contract_changes_only_identity_triangle_gate_and_claims() -> None:
    contract = load_planar_fixture_full_timeline_contract()
    merged = _merged_or119_contract(contract)

    assert merged["experiment_id"] == contract["experiment_id"]
    assert merged["proof_class"] == contract["proof_class"]
    assert merged["gates"]["expected_total_raster_triangle_count_per_frame"] == 825420
    assert merged["claim_limits"] == contract["claim_limits"]


def test_or128_fixture_triangle_count_is_frozen() -> None:
    contract = load_planar_fixture_full_timeline_contract()
    assert contract["fixture"]["triangle_count"] == 128

from __future__ import annotations

from sim2claw.observable_registration_renderer_native_two_planar_fixture_full_timeline_propagation import (
    _merged_or119_contract,
    load_two_planar_fixture_full_timeline_contract,
)


def test_or131_contract_binds_full_timeline_and_no_image_borrowing() -> None:
    contract = load_two_planar_fixture_full_timeline_contract()

    assert contract["resource_boundary"]["physical_frames_compared_allowed"] == 1210
    assert contract["resource_boundary"]["candidate_videos_allowed"] == 11
    assert contract["fixture"]["physical_pixel_texture_projection"] is False
    assert contract["fixture"]["screen_space_overlay"] is False


def test_or131_merged_contract_changes_only_identity_triangle_gate_and_claims() -> None:
    contract = load_two_planar_fixture_full_timeline_contract()
    merged = _merged_or119_contract(contract)

    assert merged["experiment_id"] == contract["experiment_id"]
    assert merged["proof_class"] == contract["proof_class"]
    assert merged["gates"]["expected_total_raster_triangle_count_per_frame"] == 825548
    assert merged["claim_limits"] == contract["claim_limits"]


def test_or131_fixture_triangle_counts_are_frozen() -> None:
    contract = load_two_planar_fixture_full_timeline_contract()

    assert contract["fixture"]["fixture_count"] == 2
    assert contract["fixture"]["triangle_count_per_fixture"] == 128
    assert contract["fixture"]["total_triangle_count"] == 256

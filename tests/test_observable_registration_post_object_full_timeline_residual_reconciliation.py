from __future__ import annotations

from sim2claw.observable_registration_post_object_full_timeline_residual_reconciliation import (
    _select_residual_family,
    load_post_object_full_timeline_residual_reconciliation_contract,
)


def test_or120_contract_preserves_or97_factorization_and_zero_render_boundary() -> None:
    contract = load_post_object_full_timeline_residual_reconciliation_contract()

    assert contract["edge_occupancy"]["persistent_minimum_frame_fraction"] == 0.80
    assert contract["edge_occupancy"]["dynamic_minimum_frame_fraction"] == 0.05
    assert contract["dominance_rule"]["minimum_mean_deficit_ratio"] == 2.0
    assert contract["dominance_rule"]["minimum_per_episode_deficit_margin"] == 0.05
    assert contract["resource_boundary"]["renders_allowed"] == 0
    assert contract["resource_boundary"]["fits_allowed"] == 0
    assert contract["claim_limits"]["same_video_semantic_match"] is False


def test_select_residual_family_requires_consistent_persistent_dominance() -> None:
    rule = load_post_object_full_timeline_residual_reconciliation_contract()["dominance_rule"]
    selected = _select_residual_family([0.30] * 11, [0.56] * 11, rule)

    assert selected["selected_residual_family"] == "renderer_native_persistent_static_scene_content"
    assert selected["episodes_persistent_deficit_dominant"] == 11
    assert selected["persistent_to_dynamic_mean_deficit_ratio"] > 2.0


def test_select_residual_family_rejects_inconsistent_episode_dominance() -> None:
    rule = load_post_object_full_timeline_residual_reconciliation_contract()["dominance_rule"]
    persistent = [0.30] * 8 + [0.58] * 3
    dynamic = [0.56] * 8 + [0.30] * 3
    selected = _select_residual_family(persistent, dynamic, rule)

    assert selected["selected_residual_family"] == "combined_or_unresolved_no_single_successor"

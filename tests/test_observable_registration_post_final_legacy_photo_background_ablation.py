from __future__ import annotations

from sim2claw.observable_registration_post_final_legacy_photo_background_ablation import (
    load_post_final_legacy_photo_background_ablation_contract,
)


def test_or98_contract_freezes_single_renderer_only_ablation() -> None:
    contract = load_post_final_legacy_photo_background_ablation_contract()

    assert contract["frozen_candidate"]["renderer_only_ablated_body_ids"] == [6, 7]
    assert contract["frozen_candidate"]["new_geometry_added"] is False
    assert contract["frozen_candidate"]["physics_or_state_mutated"] is False
    assert contract["gates"]["expected_ablated_triangle_count"] == 817548


def test_or98_keeps_fit_and_authority_closed() -> None:
    contract = load_post_final_legacy_photo_background_ablation_contract()

    assert contract["resource_boundary"]["fits_allowed"] == 0
    assert contract["resource_boundary"]["candidate_family_searches_allowed"] == 0
    assert not any(contract["authority"].values())
    assert contract["claim_limits"]["same_video_semantic_match"] is False

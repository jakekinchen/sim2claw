from __future__ import annotations

from sim2claw.observable_registration_post_final_renderer_native_white_enclosure_shell import (
    load_post_final_renderer_native_white_enclosure_shell_contract,
)


def test_or99_contract_freezes_one_renderer_native_shell() -> None:
    contract = load_post_final_renderer_native_white_enclosure_shell_contract()

    frozen = contract["frozen_candidate"]
    assert frozen["renderer_only_background_body_id"] == 6
    assert frozen["renderer_only_kept_background_geom_names"] == ["rear_wall"]
    assert frozen["renderer_only_removed_child_body_ids"] == [7]
    assert frozen["rear_wall_geometry_unchanged"] is True
    assert frozen["new_geometry_added"] is False
    assert frozen["pixel_compositing_or_warp"] is False
    assert frozen["physics_or_state_mutated"] is False
    assert contract["gates"]["expected_shell_triangle_count"] == 817560


def test_or99_keeps_search_fit_and_authority_closed() -> None:
    contract = load_post_final_renderer_native_white_enclosure_shell_contract()

    resources = contract["resource_boundary"]
    assert resources["fits_allowed"] == 0
    assert resources["candidate_family_searches_allowed"] == 0
    assert resources["simulator_replays_allowed"] == 0
    assert resources["paid_compute_allowed"] is False
    assert not any(contract["authority"].values())
    assert contract["claim_limits"]["same_video_semantic_match"] is False

from __future__ import annotations

from sim2claw.observable_registration_post_final_bounded_renderer_native_enclosure_plane_fit import (
    load_post_final_bounded_renderer_native_enclosure_plane_fit_contract,
)


def test_or100_contract_freezes_bounded_renderer_native_plane_family() -> None:
    contract = load_post_final_bounded_renderer_native_enclosure_plane_fit_contract()

    family = contract["candidate_family"]
    geom = family["new_geom"]
    assert geom["type"] == "box"
    assert geom["body_id"] == 6
    assert geom["local_x_candidates_m"] == [-0.5, -0.475, -0.45, -0.425, -0.4, -0.375, -0.35, -0.325, -0.3]
    assert geom["half_size_m"] == [0.035, 0.575, 0.95]
    assert family["one_global_value_selected"] is True
    assert family["per_episode_geometry"] is False
    assert family["pixel_compositing_or_warp"] is False
    assert family["physics_or_state_mutated"] is False


def test_or100_contract_freezes_development_then_validation_and_authority() -> None:
    contract = load_post_final_bounded_renderer_native_enclosure_plane_fit_contract()

    assert contract["split"]["development_positions"] == [1, 2, 3, 4, 5, 6, 7]
    assert contract["split"]["validation_positions"] == [8, 9, 10, 11]
    assert contract["split"]["validation_render_requires_development_gate"] is True
    assert contract["resource_boundary"]["exact_full_mesh_development_candidate_renders_allowed"] == 63
    assert contract["resource_boundary"]["exact_full_mesh_validation_selected_renders_allowed"] == 4
    assert contract["resource_boundary"]["simulator_replays_allowed"] == 0
    assert contract["resource_boundary"]["paid_compute_allowed"] is False
    assert not any(contract["authority"].values())
    assert contract["claim_limits"]["same_video_semantic_match"] is False

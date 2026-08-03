from sim2claw.observable_registration_post_final_actor_reconstruction_failure_attribution import (
    _attribute,
    load_post_final_actor_reconstruction_failure_attribution_contract,
)


def test_contract_preserves_no_search_no_validation_boundary() -> None:
    contract = load_post_final_actor_reconstruction_failure_attribution_contract()
    assert contract["cohort"]["validation_rows_or_pixels_allowed"] == 0
    assert contract["resource_boundary"]["fits_or_candidate_searches_allowed"] == 0
    assert contract["resource_boundary"]["full_scene_renders_allowed"] == 0
    assert contract["claim_limits"]["predictive_simulation"] is False


def test_frozen_decision_tree_selects_exactly_one_mechanism() -> None:
    tree = load_post_final_actor_reconstruction_failure_attribution_contract()["decision_tree"]
    assert _attribute(0.84, 0.99, tree)[0] == "PROJECTED_3D_SILHOUETTE_LOSS"
    assert _attribute(0.90, 0.79, tree)[0] == "SCENE_OCCLUSION_OR_DEPTH_GAUGE_LOSS"
    assert _attribute(0.90, 0.90, tree)[0] == "SINGLE_PROXY_BOUNDARY_DETAIL_LOSS"

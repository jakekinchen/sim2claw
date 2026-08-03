from __future__ import annotations

from sim2claw.observable_registration_post_final_robot_dynamic_footprint_scale_attribution import (
    load_post_final_robot_dynamic_footprint_scale_attribution_contract,
)


def test_or101_contract_freezes_immutable_occupancy_measurement() -> None:
    contract = load_post_final_robot_dynamic_footprint_scale_attribution_contract()

    assert contract["input"]["occupancy_map_count"] == 11
    assert contract["input"]["panel_order"] == [
        "physical_persistent",
        "candidate_persistent",
        "physical_dynamic",
        "candidate_dynamic",
    ]
    assert contract["decision_tree"]["camera_ray_depth_registration_if"]["minimum_median_physical_to_candidate_area_ratio"] == 1.5
    assert contract["decision_tree"]["camera_ray_depth_registration_if"]["minimum_median_physical_to_candidate_bbox_diagonal_ratio"] == 1.2


def test_or101_contract_keeps_render_fit_and_authority_closed() -> None:
    contract = load_post_final_robot_dynamic_footprint_scale_attribution_contract()

    resources = contract["resource_boundary"]
    assert resources["physical_video_decodes_allowed"] == 0
    assert resources["renders_allowed"] == 0
    assert resources["fits_allowed"] == 0
    assert resources["parameter_selections_allowed"] == 0
    assert resources["simulator_replays_allowed"] == 0
    assert resources["paid_compute_allowed"] is False
    assert not any(contract["authority"].values())
    assert contract["claim_limits"]["same_video_semantic_match"] is False

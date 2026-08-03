from __future__ import annotations

from sim2claw.observable_registration_post_final_exogenous_operator_skin_edge_occupancy_attribution import (
    load_post_final_exogenous_operator_skin_edge_occupancy_attribution_contract,
)


def test_or107_contract_freezes_generic_proxy_and_no_refit_split() -> None:
    contract = load_post_final_exogenous_operator_skin_edge_occupancy_attribution_contract()

    assert contract["split"]["development_positions"] == list(range(1, 8))
    assert contract["split"]["validation_positions"] == list(range(8, 12))
    assert contract["split"]["validation_decode_requires_development_gate"] is True
    assert contract["skin_proxy"]["combination"] == "hsv_and_ycrcb"
    assert contract["skin_proxy"]["board_region_excluded"] is True
    assert contract["skin_proxy"]["generic_color_proxy_not_person_identity_or_biometric_inference"] is True
    assert contract["resource_boundary"]["renders_allowed"] == 0
    assert contract["resource_boundary"]["fits_allowed"] == 0
    assert contract["resource_boundary"]["paid_compute_allowed"] is False
    assert not any(contract["authority"].values())


def test_or107_claims_remain_bounded() -> None:
    contract = load_post_final_exogenous_operator_skin_edge_occupancy_attribution_contract()

    claims = contract["claim_limits"]
    assert claims["person_identity_or_biometric_inference"] is False
    assert claims["operator_geometry_or_trajectory_calibrated"] is False
    assert claims["same_video_semantic_match"] is False
    assert claims["physics_fidelity"] is False
    assert claims["simulator_promotion"] is False

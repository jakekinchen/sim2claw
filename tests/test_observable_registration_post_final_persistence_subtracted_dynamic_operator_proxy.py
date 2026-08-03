from __future__ import annotations

from sim2claw.observable_registration_post_final_persistence_subtracted_dynamic_operator_proxy import (
    load_post_final_persistence_subtracted_dynamic_operator_proxy_contract,
)


def test_or108_contract_freezes_one_development_support_and_validation_no_refit() -> None:
    contract = load_post_final_persistence_subtracted_dynamic_operator_proxy_contract()
    assert contract["split"]["development_positions"] == list(range(1, 8))
    assert contract["split"]["validation_positions"] == list(range(8, 12))
    assert contract["split"]["persistent_support_fit_on_development_only"] is True
    assert contract["split"]["validation_uses_frozen_persistent_support"] is True
    assert contract["persistent_support"]["minimum_development_occupancy_fraction"] == 0.8
    assert contract["persistent_support"]["validation_refit"] is False
    assert contract["resource_boundary"]["persistent_support_fits_allowed"] == 1
    assert contract["resource_boundary"]["validation_refits_allowed"] == 0
    assert contract["resource_boundary"]["renders_allowed"] == 0
    assert contract["resource_boundary"]["paid_compute_allowed"] is False
    assert not any(contract["authority"].values())


def test_or108_claims_remain_diagnostic_only() -> None:
    claims = load_post_final_persistence_subtracted_dynamic_operator_proxy_contract()["claim_limits"]
    assert claims["person_identity_or_biometric_inference"] is False
    assert claims["operator_geometry_or_trajectory_calibrated"] is False
    assert claims["same_video_semantic_match"] is False
    assert claims["physics_fidelity"] is False
    assert claims["simulator_promotion"] is False

from __future__ import annotations

from sim2claw.observable_registration_post_final_robot_material_semantics_loss_attribution import (
    load_post_final_robot_material_semantics_loss_attribution_contract,
)


def test_or105_contract_freezes_source_only_material_audit() -> None:
    contract = load_post_final_robot_material_semantics_loss_attribution_contract()

    assert contract["audit"]["manifest_robot_body_ids"] == list(range(29, 45))
    assert contract["audit"]["manifest_mesh_side_prefixes"] == ["left_", "right_"]
    assert contract["audit"]["physical_pixels_used"] is False
    assert contract["audit"]["selection_if_passed"] == "freeze_two_class_robot_material_palette_calibration"
    assert contract["resource_boundary"]["physical_video_decodes_allowed"] == 0
    assert contract["resource_boundary"]["renders_allowed"] == 0
    assert contract["resource_boundary"]["fits_allowed"] == 0
    assert contract["resource_boundary"]["paid_compute_allowed"] is False
    assert not any(contract["authority"].values())


def test_or105_contract_does_not_claim_a_calibrated_palette() -> None:
    contract = load_post_final_robot_material_semantics_loss_attribution_contract()

    assert contract["claim_limits"]["post_final_source_only_material_semantics_attribution"] is True
    assert contract["claim_limits"]["material_palette_calibrated"] is False
    assert contract["claim_limits"]["same_video_semantic_match"] is False
    assert contract["claim_limits"]["physics_fidelity"] is False
    assert contract["claim_limits"]["simulator_promotion"] is False

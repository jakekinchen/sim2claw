from sim2claw.observable_registration_measured_state_prior_pad_position import (
    load_measured_state_prior_pad_position_contract,
)


def test_contract_uses_exact_c2_diagnosis_anchor_position() -> None:
    contract = load_measured_state_prior_pad_position_contract()
    baseline, candidate = contract["variants"]
    assert baseline["sts3215_force_limit_nm"] == 2.94
    assert candidate["sts3215_force_limit_nm"] == 2.94
    assert baseline["prior_fixed_pad_position_enabled"] is False
    assert candidate["prior_fixed_pad_position_enabled"] is True
    skin = contract["contact_skin_intervention"]
    assert skin["tip_coverage_offset_m"] == -0.03
    assert skin["tip_fixed_coverage_offset_m"] == 0.0
    assert skin["fixed_pad_expected_local_z_m"] == -0.1205
    assert skin["candidate_selected_without_destination_terminal_outcome"] is True
    assert contract["simulation"]["natural_pawn_dynamics_only"] is True
    assert contract["simulation"]["object_pose_injection_allowed"] is False
    assert not any(contract["claim_limits"].values())

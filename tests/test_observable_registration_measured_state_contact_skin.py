from sim2claw.observable_registration_measured_state_contact_skin import (
    load_measured_state_contact_skin_contract,
)


def test_contract_freezes_cross_episode_contact_skin_without_refit() -> None:
    contract = load_measured_state_contact_skin_contract()
    baseline, candidate = contract["variants"]
    assert baseline["sts3215_force_limit_nm"] == 2.94
    assert candidate["sts3215_force_limit_nm"] == 2.94
    assert baseline["frozen_c2_contact_skin_enabled"] is False
    assert candidate["frozen_c2_contact_skin_enabled"] is True
    skin = contract["contact_skin_intervention"]
    assert skin["zero_refit_on_destination_episode"] is True
    assert skin["tip_thickness_m"] == 0.001
    assert skin["tip_half_width_m"] == 0.0065
    assert skin["tip_coverage_m"] == 0.02
    assert skin["add_exactly_one_pad_per_jaw"] is True
    assert (
        skin["disable_all_original_collision_enabled_geoms_on_target_jaws"]
        is True
    )
    assert contract["simulation"]["natural_pawn_dynamics_only"] is True
    assert contract["simulation"]["object_pose_injection_allowed"] is False
    assert not any(contract["claim_limits"].values())

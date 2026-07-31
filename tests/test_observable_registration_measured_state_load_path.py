from sim2claw.observable_registration_measured_state_load_path import (
    load_measured_state_load_path_contract,
)


def test_contract_freezes_one_external_force_envelope_candidate() -> None:
    contract = load_measured_state_load_path_contract()
    baseline, candidate = contract["variants"]
    assert baseline["sts3215_force_limit_nm"] == 2.94
    assert baseline["simulator_mechanism_changed"] is False
    assert candidate["sts3215_force_limit_nm"] == 1.91229675
    assert candidate["simulator_mechanism_changed"] is True
    assert (
        contract["manufacturer_constraint"]["candidate_selected_without_task_outcome"]
        is True
    )
    assert contract["trajectory"]["row_count"] == 531
    assert contract["simulation"]["natural_pawn_dynamics_only"] is True
    assert contract["simulation"]["object_pose_injection_allowed"] is False
    assert (
        contract["simulation"]["latch_attachment_or_grasp_mode_allowed"]
        is False
    )
    assert contract["simulation"]["terminal_result_may_select_or_revise_candidate"] is False
    assert not any(contract["claim_limits"].values())
    assert contract["authority"]["simulator_replay"] is True
    assert not any(
        value
        for name, value in contract["authority"].items()
        if name != "simulator_replay"
    )

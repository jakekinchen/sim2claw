from sim2claw.observable_registration_sample232_base_xy_aperture_geometry import (
    load_contract,
)


def test_or30_is_bounded_static_and_outcome_blind() -> None:
    contract, or29, _, _ = load_contract()
    assert len(contract["grid"]["left_base_world_x_delta_m"]) == 9
    assert len(contract["grid"]["left_base_world_y_delta_m"]) == 9
    assert len(or29["grid"]["gripper_zero_offset_rad"]) == 17
    assert contract["selection"]["sample"] == 232
    assert contract["evaluation"]["physics_integration_allowed"] is False
    assert contract["evaluation"]["dynamic_replay_allowed"] is False
    assert contract["evaluation"]["dynamic_outcomes_may_not_select_grid_row"] is True
    assert not any(
        value
        for name, value in contract["authority"].items()
        if name != "simulator_static_evaluation"
    )

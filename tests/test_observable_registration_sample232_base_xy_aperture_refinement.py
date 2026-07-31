from sim2claw.observable_registration_sample232_base_xy_aperture_refinement import load_contract


def test_or31_is_one_bounded_static_refinement() -> None:
    contract, _, _, _ = load_contract()
    assert len(contract["grid"]["left_base_world_x_delta_m"]) == 11
    assert len(contract["grid"]["left_base_world_y_delta_m"]) == 11
    assert len(contract["grid"]["gripper_zero_offset_rad"]) == 15
    assert contract["selection"]["sample"] == 232
    assert contract["evaluation"]["physics_integration_allowed"] is False
    assert contract["evaluation"]["dynamic_outcomes_may_not_select_grid_row"] is True

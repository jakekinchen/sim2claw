from sim2claw.observable_registration_sample232_base_yaw_path_geometry import load_contract


def test_or32_is_bounded_static_yaw_path_refinement() -> None:
    contract, _, _ = load_contract()
    assert len(contract["grid"]["left_base_yaw_delta_degrees"]) == 7
    assert contract["selection"]["sample"] == 232
    assert contract["evaluation"]["physics_integration_allowed"] is False
    assert contract["evaluation"]["dynamic_outcomes_may_not_select_grid_row"] is True

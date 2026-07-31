from sim2claw.observable_registration_sample232_wrist_path_geometry import load_contract


def test_or33_is_bounded_static_wrist_path_grid() -> None:
    contract, _, _ = load_contract()
    assert len(contract["grid"]["wrist_flex_zero_offset_delta_degrees"]) == 5
    assert len(contract["grid"]["wrist_roll_zero_offset_delta_degrees"]) == 5
    assert contract["selection"]["sample"] == 232
    assert contract["evaluation"]["physics_integration_allowed"] is False

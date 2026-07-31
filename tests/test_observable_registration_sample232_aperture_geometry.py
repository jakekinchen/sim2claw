from pathlib import Path

from sim2claw.observable_registration_sample232_aperture_geometry import (
    load_contract,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_or29_is_static_bounded_and_outcome_blind() -> None:
    contract, _, _ = load_contract()
    assert len(contract["grid"]["gripper_zero_offset_rad"]) == 17
    assert contract["identity"]["physical_first_definite_enclosure_sample"] == 232
    assert contract["selection"]["sample"] == 232
    assert contract["grid"]["dynamic_outcomes_may_not_select_grid_row"] is True
    assert contract["evaluation"]["forward_kinematics_allowed"] is True
    assert contract["evaluation"]["physics_integration_allowed"] is False
    assert contract["evaluation"]["dynamic_replay_allowed"] is False
    assert not any(
        value
        for name, value in contract["authority"].items()
        if name != "simulator_static_evaluation"
    )

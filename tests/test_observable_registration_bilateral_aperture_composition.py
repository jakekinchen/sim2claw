from pathlib import Path

from sim2claw.observable_registration_unilateral_push_dynamic_replay import (
    load_unilateral_push_dynamic_replay_contract,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    REPO_ROOT
    / "configs/evaluations/observable_registration_bilateral_aperture_composition_v1.json"
)


def test_or28_composes_only_prior_spatial_and_aperture_candidates() -> None:
    contract, _ = load_unilateral_push_dynamic_replay_contract(CONTRACT)
    assert contract["candidate"]["left_robot_yaw_delta_degrees"] == 6.0
    assert contract["candidate"]["gripper_zero_offset_rad"] == 0.04948239306868429
    assert contract["candidate"]["composition_frozen_before_dynamic_outcome"] is True
    assert contract["replay"]["reuse_exact_c6_requested_gateway_sent_timestamps_and_identified_applied"] is True
    assert contract["replay"]["action_change_allowed"] is False
    assert contract["replay"]["contact_parameter_change_allowed"] is False
    assert contract["replay"]["object_parameter_change_allowed"] is False
    assert contract["reporting"]["desired_simulator_bilateral_contact_window"] == [228, 232]
    assert not any(
        value
        for name, value in contract["authority"].items()
        if name != "simulator_replay"
    )

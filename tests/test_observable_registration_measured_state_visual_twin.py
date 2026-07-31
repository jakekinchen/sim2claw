import numpy as np

from sim2claw.observable_registration_measured_state_visual_twin import (
    _tilt_degrees,
    load_measured_state_visual_twin_contract,
)


def test_contract_uses_raw_measured_state_without_object_assistance() -> None:
    contract = load_measured_state_visual_twin_contract()
    trajectory = contract["trajectory"]
    simulation = contract["simulation"]
    assert trajectory["row_count"] == 531
    assert trajectory["robot_driver"] == "raw_follower_actual_position_degrees"
    assert trajectory["identified_applied_drives_robot"] is False
    assert trajectory["measured_state_is_observation_conditioned"] is True
    assert simulation["natural_contact_only"] is True
    assert simulation["object_pose_injection_allowed"] is False
    assert simulation["latch_or_attachment_allowed"] is False
    assert not any(contract["claim_limits"].values())
    assert contract["authority"]["simulator_replay"] is True
    assert not any(
        value
        for name, value in contract["authority"].items()
        if name != "simulator_replay"
    )


def test_tilt_is_zero_for_upright_identity_quaternion() -> None:
    assert _tilt_degrees(np.asarray([1.0, 0.0, 0.0, 0.0])) == 0.0

from sim2claw.observable_registration_post_final_global_robot_motion_lag_attribution import load_post_final_global_robot_motion_lag_attribution_contract


def test_or102_freezes_one_global_integer_lag() -> None:
    contract = load_post_final_global_robot_motion_lag_attribution_contract()
    signal = contract["signal"]
    assert signal["lag_candidates_frames"] == list(range(-10, 11))
    assert signal["one_global_lag"] is True
    assert signal["per_episode_lag"] is False
    assert signal["frame_interpolation"] is False
    assert signal["time_warp"] is False


def test_or102_keeps_actions_render_and_authority_closed() -> None:
    contract = load_post_final_global_robot_motion_lag_attribution_contract()
    resources = contract["resource_boundary"]
    assert resources["renders_allowed"] == 0
    assert resources["simulator_replays_allowed"] == 0
    assert resources["action_or_state_mutations_allowed"] == 0
    assert resources["paid_compute_allowed"] is False
    assert not any(contract["authority"].values())
    assert contract["claim_limits"]["same_video_semantic_match"] is False

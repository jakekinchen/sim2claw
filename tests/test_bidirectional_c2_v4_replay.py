from sim2claw.bidirectional_c2_v4_replay import evaluate


def test_v4_c2_replay_is_exact_retrospective_negative() -> None:
    receipt = evaluate()
    assert receipt["canonical_action"]["mutated"] is False
    assert (
        receipt["canonical_action"]["raw_float64le_sha256"]
        == "0add8f1357c65bee011755e6e4a124d0e339cbc0dce9fd3a92b78399380a37da"
    )
    assert receipt["runtime"]["numeric_runtime"] == "cpu_mujoco_fp64"
    assert receipt["runtime"]["finite_state"] is True
    assert receipt["old_scene"]["selected_piece_contact_observed"] is False
    assert receipt["scene_v4"]["selected_piece_contact_count"] == 0
    assert receipt["scene_v4"]["wrong_piece_contact_count"] == 0
    assert receipt["scene_v4"]["off_source_square"] is False
    assert receipt["promoted"] is False
    assert (
        receipt["scene_v4"]["minimum_gripper_clearance_m"]
        < receipt["old_scene"]["minimum_gripper_clearance_m"]
    )

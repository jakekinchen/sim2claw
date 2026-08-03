from sim2claw.observable_registration_post_final_joint_articulation_observability_rank import load_post_final_joint_articulation_observability_rank_contract


def test_or103_freezes_six_shared_joint_families() -> None:
    contract = load_post_final_joint_articulation_observability_rank_contract()
    assert [row["name"] for row in contract["joint_families"]] == ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
    assert contract["endpoint_body_ids"] == {"left": 36, "right": 44}
    assert contract["development_positions"] == list(range(1, 8))


def test_or103_keeps_pixels_fit_and_authority_closed() -> None:
    contract = load_post_final_joint_articulation_observability_rank_contract()
    resources = contract["resource_boundary"]
    assert resources["physical_video_decodes_allowed"] == 0
    assert resources["candidate_video_decodes_allowed"] == 0
    assert resources["renders_allowed"] == 0
    assert resources["fits_allowed"] == 0
    assert resources["parameter_values_allowed"] == 0
    assert resources["simulator_replays_allowed"] == 0
    assert resources["paid_compute_allowed"] is False
    assert not any(contract["authority"].values())

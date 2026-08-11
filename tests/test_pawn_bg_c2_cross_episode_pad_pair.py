from sim2claw.pawn_bg_c2_cross_episode_pad_pair import load_contract


def test_cross_episode_candidate_is_single_and_action_frozen() -> None:
    contract = load_contract()

    assert [row["candidate_id"] for row in contract["candidate_order"]] == [
        "c2_or50_fixed_pad_pair_distal_trim_3mm"
    ]
    assert contract["execution"]["simulator_replays"] == 1
    assert contract["source_bindings"]["action_sha256"] == (
        "402a29e4cdc0c4cb90d41a83327ad8df5685544851b4e4d659129b3239744fd6"
    )
    assert not any(contract["authority"].values())


def test_cross_episode_candidate_changes_only_declared_passive_topology() -> None:
    contract = load_contract()

    assert contract["parameter_overrides"] == {
        "tip_fixed_coverage_offset_m": 0.00752,
        "fixed_jaw_primitive_collision_enabled": False,
        "moving_jaw_primitive_collision_enabled": False,
        "tip_moving_coverage_multiplier": 0.85,
        "tip_moving_coverage_offset_m": 0.0265,
    }
    assert contract["c2_parameters"]["tip_moving_coverage_offset_m"] == 0.0265
    assert contract["c2_parameters"]["tip_moving_coverage_multiplier"] == 0.85
    assert contract["c2_parameters"]["tip_coverage_m"] == 0.02
    assert contract["c2_parameters"]["sliding_friction"] == 1.8

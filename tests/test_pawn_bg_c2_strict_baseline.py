from sim2claw.learning_factory_artifacts import canonical_digest
from sim2claw.pawn_bg_c2_strict_baseline import load_contract


def test_c2_baseline_identity_is_action_frozen_and_single_run() -> None:
    contract = load_contract()

    assert contract["source_bindings"]["recording_id"] == "20260719T031324Z-bf91502b"
    assert contract["source_bindings"]["action_sha256"] == (
        "402a29e4cdc0c4cb90d41a83327ad8df5685544851b4e4d659129b3239744fd6"
    )
    assert contract["action_invariance"]["shape"] == [527, 6]
    assert contract["execution"]["simulator_replays"] == 1
    assert len(contract["candidate_order"]) == 1
    assert not any(contract["authority"].values())


def test_c2_parameters_match_retained_rank01_digest() -> None:
    contract = load_contract()

    assert canonical_digest(contract["c2_parameters"]) == (
        "689cc4e245b3b7d500f9ea5ecb16003599cbcc0de9f0ca2a3d30b3f7b60389f7"
    )
    assert contract["c2_parameters"]["tip_coverage_m"] == 0.02
    assert contract["c2_parameters"]["tip_moving_coverage_offset_m"] == 0.025
    assert contract["c2_parameters"]["simulation_timestep_multiplier"] == 0.45

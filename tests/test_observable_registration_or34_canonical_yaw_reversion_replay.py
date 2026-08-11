from copy import deepcopy

from sim2claw.observable_registration_or34_canonical_yaw_reversion_replay import (
    EXPECTED_SCENE_DIFF,
    OUTPUT_DIRECTORY,
    _semantic_differences,
    audit_scene_semantic_diff,
    load_canonical_yaw_reversion_replay_contract,
    verify_canonical_yaw_reversion_replay,
)
from sim2claw.observable_registration_or34_board_coordinate_initialization_replay import (
    _metric_comparison,
)


def test_contract_freezes_one_yaw_only_observation_conditioned_replay() -> None:
    contract = load_canonical_yaw_reversion_replay_contract()
    replay = contract["replay"]
    assert replay["one_run_only"] is True
    assert replay["clone_of"] == "OR152_OR34_BOARD_COORDINATE_INITIALIZATION_REPLAY_V1"
    assert replay["observation_conditioned"] is True
    assert replay["action_only_transfer"] is False
    assert replay["row_count"] == 531
    assert replay["sole_changed_factor"] == "left_robot_base_yaw_relative_to_table_degrees"
    assert replay["baseline_yaw_relative_to_table_degrees"] == -82.0
    assert replay["candidate_yaw_relative_to_table_degrees"] == -88.0
    assert replay["fit_search_retry_allowed"] is False
    assert not any(contract["claim_limits"].values())


def test_scene_sources_have_exactly_one_semantic_field_difference() -> None:
    contract = load_canonical_yaw_reversion_replay_contract()
    assert audit_scene_semantic_diff(contract) == [EXPECTED_SCENE_DIFF]
    before = {"simulation_estimates": {"robots": [{"yaw_relative_to_table_degrees": -82.0}]}, "x": 1}
    after = deepcopy(before)
    after["simulation_estimates"]["robots"][0]["yaw_relative_to_table_degrees"] = -88.0
    after["x"] = 2
    assert _semantic_differences(before, after) == [EXPECTED_SCENE_DIFF, {"path": "x", "before": 1, "after": 2}]


def test_advancement_is_frozen_against_or152_and_requires_contact() -> None:
    contract = load_canonical_yaw_reversion_replay_contract()
    baseline = {
        "final_planar_center_error_m": contract["evaluator"]["baseline"]["final_planar_center_error_m"],
        "final_upright_tilt_degrees": contract["evaluator"]["baseline"]["final_upright_tilt_degrees"],
        "final_height_error_m": contract["evaluator"]["baseline"]["final_height_error_m"],
        "gates": {"composable_center": False, "upright": False, "selected_piece_contact": True},
    }
    candidate = deepcopy(baseline)
    candidate["final_planar_center_error_m"] -= 0.001
    result = _metric_comparison(contract=contract, baseline=baseline, candidate=candidate)
    assert result["materially_improved"]["final_planar_center_error_reduction_m"] is True
    assert result["accepted_task_outcome_metric_advancement"] is True
    candidate["gates"]["selected_piece_contact"] = False
    assert _metric_comparison(contract=contract, baseline=baseline, candidate=candidate)[
        "accepted_task_outcome_metric_advancement"
    ] is False


def test_write_once_replay_emits_preserved_pose_and_full_trace_when_present() -> None:
    receipt_path = OUTPUT_DIRECTORY / "receipt.json"
    if not receipt_path.exists():
        assert not OUTPUT_DIRECTORY.exists()
        return
    receipt = verify_canonical_yaw_reversion_replay()
    assert receipt["execution"] == {
        "simulator_replays": 1,
        "fits": 0,
        "searches": 0,
        "retries": 0,
        "hardware_actions": 0,
        "paid_compute": False,
    }
    assert receipt["scene_semantic_diff"] == [EXPECTED_SCENE_DIFF]
    assert receipt["factor_isolation"]["initial_pose_max_abs_change_from_or152"] == 0.0
    assert receipt["source_identity"]["row_count"] == 531
    assert receipt["source_identity"]["source_hashes_unchanged"] is True
    assert receipt["observation_conditioned"] is True
    assert receipt["action_only_transfer"] is False

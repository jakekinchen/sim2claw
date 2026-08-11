from sim2claw.observable_registration_or34_board_coordinate_initialization_replay import (
    _metric_comparison,
    load_board_coordinate_initialization_replay_contract,
    verify_board_coordinate_initialization_replay,
)


def test_contract_freezes_one_xy_only_observation_conditioned_replay() -> None:
    contract = load_board_coordinate_initialization_replay_contract()
    replay = contract["replay"]
    assert replay["one_run_only"] is True
    assert replay["observation_conditioned"] is True
    assert replay["action_only_transfer"] is False
    assert replay["sole_changed_factor"] == (
        "selected_pawn_initial_xy_board_coordinate_transport_into_or18_scene"
    )
    assert replay["fit_search_retry_allowed"] is False
    assert not any(contract["claim_limits"].values())


def test_metric_advancement_requires_material_consequence_and_contact() -> None:
    contract = load_board_coordinate_initialization_replay_contract()
    baseline = {
        "final_planar_center_error_m": 0.034,
        "final_upright_tilt_degrees": 100.0,
        "final_height_error_m": 0.014,
        "gates": {"composable_center": False, "upright": False, "selected_piece_contact": True},
    }
    candidate = {
        "final_planar_center_error_m": 0.032,
        "final_upright_tilt_degrees": 101.0,
        "final_height_error_m": 0.014,
        "gates": {"composable_center": False, "upright": False, "selected_piece_contact": True},
    }
    result = _metric_comparison(contract=contract, baseline=baseline, candidate=candidate)
    assert result["materially_improved"]["final_planar_center_error_reduction_m"] is True
    assert result["accepted_task_outcome_metric_advancement"] is True
    candidate["gates"]["selected_piece_contact"] = False
    assert _metric_comparison(
        contract=contract, baseline=baseline, candidate=candidate
    )["accepted_task_outcome_metric_advancement"] is False


def test_write_once_replay_emits_fully_decomposed_outcome() -> None:
    receipt = verify_board_coordinate_initialization_replay()
    assert receipt["execution"] == {
        "simulator_replays": 1,
        "fits": 0,
        "searches": 0,
        "retries": 0,
        "hardware_actions": 0,
        "paid_compute": False,
    }
    assert receipt["factor_isolation"]["initial_xy_change_m"] > 0.013
    assert receipt["natural_dynamics"]["outcome"]["gates"]["selected_piece_contact"] is True
    assert receipt["source_identity"]["source_hashes_unchanged"] is True
    assert receipt["observation_conditioned"] is True
    assert receipt["action_only_transfer"] is False

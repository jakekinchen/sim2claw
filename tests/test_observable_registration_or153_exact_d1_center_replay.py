from copy import deepcopy
from pathlib import Path

import pytest

from sim2claw.learning_factory_artifacts import FactoryArtifactError
from sim2claw.observable_registration_or153_exact_d1_center_replay import (
    BASELINE_BOARD_COORDINATE,
    EXACT_D1_BOARD_COORDINATE,
    EXECUTION_BOUNDARY,
    OUTPUT_DIRECTORY,
    _gate_level_comparison,
    load_exact_d1_center_replay_contract,
    verify_exact_d1_center_replay,
)


def _baseline_outcome() -> dict[str, object]:
    return {
        "final_planar_center_error_m": 0.129,
        "final_upright_tilt_degrees": 97.8,
        "final_height_error_m": 0.0126,
        "numeric_task_success": False,
        "gates": {
            "composable_center": False,
            "other_pieces_stationary": True,
            "selected_piece_contact": True,
            "settled_angular": True,
            "settled_height": False,
            "settled_linear": True,
            "upright": False,
        },
    }


def test_contract_freezes_one_exact_d1_center_only_replay() -> None:
    contract = load_exact_d1_center_replay_contract()
    replay = contract["replay"]
    assert replay["one_run_only"] is True
    assert replay["clone_of"] == "OR153_OR34_CANONICAL_YAW_REVERSION_REPLAY_V1"
    assert replay["sole_changed_factor"] == "selected_pawn_initial_board_coordinate"
    assert replay["baseline_board_coordinate"] == BASELINE_BOARD_COORDINATE
    assert replay["candidate_board_coordinate"] == EXACT_D1_BOARD_COORDINATE
    assert replay["preserved_or153_semantics"] == {
        "robot_driver": "raw_follower_actual_position_degrees",
        "observation_conditioned": True,
        "action_only_transfer": False,
        "row_count": 531,
        "preserve_source_row_order": True,
        "preserve_source_timestamps": True,
        "interpolate_only_between_adjacent_measured_rows_at_native_mujoco_timestep": True,
        "natural_contact_only": True,
        "post_action_settle_seconds": 1.0,
        "candidate_yaw_relative_to_table_degrees": -88.0,
    }
    assert not any(contract["claim_limits"].values())


def test_metric_only_improvement_cannot_pass_gate_acceptance() -> None:
    baseline = _baseline_outcome()
    candidate = deepcopy(baseline)
    candidate["final_planar_center_error_m"] = 0.001
    result = _gate_level_comparison(baseline=baseline, candidate=candidate)
    assert result["false_to_true_gates"] == []
    assert result["true_to_false_gate_regressions"] == []
    assert result["metric_only_improvement_accepted"] is False
    assert result["accepted_gate_level_advancement"] is False


def test_gate_advancement_requires_contact_and_zero_regressions() -> None:
    baseline = _baseline_outcome()
    candidate = deepcopy(baseline)
    candidate["gates"]["upright"] = True
    result = _gate_level_comparison(baseline=baseline, candidate=candidate)
    assert result["false_to_true_gates"] == ["upright"]
    assert result["accepted_gate_level_advancement"] is True

    candidate["gates"]["settled_linear"] = False
    result = _gate_level_comparison(baseline=baseline, candidate=candidate)
    assert result["true_to_false_gate_regressions"] == ["settled_linear"]
    assert result["accepted_gate_level_advancement"] is False

    candidate = deepcopy(baseline)
    candidate["gates"]["upright"] = True
    candidate["gates"]["selected_piece_contact"] = False
    assert _gate_level_comparison(
        baseline=baseline, candidate=candidate
    )["accepted_gate_level_advancement"] is False

    candidate = deepcopy(baseline)
    candidate["gates"] = {name: True for name in candidate["gates"]}
    candidate["numeric_task_success"] = True
    assert _gate_level_comparison(
        baseline=baseline, candidate=candidate
    )["accepted_gate_level_advancement"] is True


def test_read_only_verifier_requires_later_closeout_without_creating_output(
    tmp_path: Path,
) -> None:
    if OUTPUT_DIRECTORY.exists():
        receipt = verify_exact_d1_center_replay()
        assert receipt["status"] == (
            "PASS_GATE_LEVEL_TASK_OUTCOME_ADVANCEMENT_TASK_NEGATIVE"
        )
        assert receipt["gate_level_comparison"][
            "accepted_gate_level_advancement"
        ] is True
        return
    missing = tmp_path / "missing-closeout.json"
    with pytest.raises(FactoryArtifactError):
        verify_exact_d1_center_replay(closeout_path=missing)
    assert not OUTPUT_DIRECTORY.exists()
    assert EXECUTION_BOUNDARY["simulator_replays"] == 1
    assert EXECUTION_BOUNDARY["renders"] == 0
    assert EXECUTION_BOUNDARY["action_mutations"] == 0
    assert EXECUTION_BOUNDARY["retimings"] == 0

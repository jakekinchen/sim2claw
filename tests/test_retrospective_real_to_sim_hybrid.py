from __future__ import annotations

import numpy as np

from sim2claw.retrospective_real_to_sim_hybrid import (
    evaluate_outcome,
    load_contract,
)


def test_frozen_contract_is_hash_bound_and_has_no_hardware_authority() -> None:
    contract = load_contract()
    assert contract["authority"] == {
        "camera": False,
        "hardware": False,
        "physical_motion": False,
        "physical_task_attempt": False,
        "sim_to_real": False,
        "pure_action_only_transfer": False,
        "simulator_replay": True,
    }
    assert contract["replay"]["terminal_object_pose_forcing_allowed"] is False
    assert contract["source"]["grasp_marker_sample_index"] == 250
    assert contract["source"]["release_marker_sample_index"] == 400


def test_outcome_separates_square_level_and_composable_success() -> None:
    evaluator = load_contract()["evaluator"]
    target = np.asarray([0.1, 0.2, 0.8])
    outcome = evaluate_outcome(
        final_position=target + np.asarray([0.007, 0.0, 0.0]),
        final_rotation=np.eye(3),
        final_velocity=np.zeros(6),
        initial_height_m=0.8,
        target_position=target,
        maximum_other_piece_displacement_m=0.0,
        evaluator=evaluator,
    )
    assert outcome["gates"]["whole_base_inside_destination"] is True
    assert outcome["gates"]["composable_center"] is False
    assert outcome["coarse_square_task_success"] is True
    assert outcome["composable_task_success"] is False


def test_outcome_rejects_motion_or_tilt_despite_centering() -> None:
    evaluator = load_contract()["evaluator"]
    tilted = np.asarray(
        [
            [1.0, 0.0, 0.0],
            [0.0, 0.8, -0.6],
            [0.0, 0.6, 0.8],
        ]
    )
    outcome = evaluate_outcome(
        final_position=np.asarray([0.1, 0.2, 0.8]),
        final_rotation=tilted,
        final_velocity=np.asarray([0.03, 0.0, 0.0, 0.0, 0.0, 0.0]),
        initial_height_m=0.8,
        target_position=np.asarray([0.1, 0.2, 0.8]),
        maximum_other_piece_displacement_m=0.0,
        evaluator=evaluator,
    )
    assert outcome["gates"]["upright"] is False
    assert outcome["gates"]["settled_linear"] is False
    assert outcome["coarse_square_task_success"] is False

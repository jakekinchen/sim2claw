from __future__ import annotations

import json

import numpy as np

from sim2claw.observable_registration_board_anchored_workcell_se2_static_development_fit import (
    DEFAULT_CONTRACT,
    _apply_board_anchored_se2,
)


def test_or84_contract_freezes_one_shared_three_parameter_family() -> None:
    contract = json.loads(DEFAULT_CONTRACT.read_text())
    family = contract["scene_registration_family"]
    assert family["parameter_names"] == [
        "workcell_yaw_degrees",
        "workcell_translation_x_m",
        "workcell_translation_y_m",
    ]
    assert len(family["bounds"]) == 3
    assert family["per_episode_parameters"] == 0
    assert family["anchor_body_name"] == "chess_board"
    assert set(family["fixed_board_group_body_ids"]).isdisjoint(
        family["transformed_workcell_body_ids"]
    )
    assert contract["resource_boundary"]["validation_reads_allowed"] == 0
    assert contract["resource_boundary"]["evaluator_heldout_reads_allowed"] == 0


def test_or84_transform_preserves_fixed_group_and_is_rigid() -> None:
    positions = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 2.0, 0.5], [2.0, 2.0, 0.5]],
        dtype=np.float64,
    )
    rotations = [np.eye(3, dtype=np.float64) for _ in range(3)]
    transformed_positions, transformed_rotations = _apply_board_anchored_se2(
        positions,
        rotations,
        anchor_body_id=1,
        transformed_body_ids=[2],
        vector=np.asarray([90.0, 0.25, -0.5], dtype=np.float64),
    )
    assert np.array_equal(transformed_positions[0], positions[0])
    assert np.array_equal(transformed_positions[1], positions[1])
    assert np.allclose(transformed_positions[2], [1.25, 2.5, 0.5])
    assert np.allclose(transformed_rotations[2].T @ transformed_rotations[2], np.eye(3))

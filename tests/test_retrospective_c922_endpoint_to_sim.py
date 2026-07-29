from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from sim2claw.current_workcell import current_square_center
from sim2claw.retrospective_c922_endpoint_to_sim import (
    board_coordinate_to_world,
    board_homography,
    load_contract,
    unproject_pixel,
)


def test_endpoint_contract_is_frozen_without_hardware_or_action_authority() -> None:
    contract = load_contract()
    assert contract["annotations"]["status"] == (
        "frozen_before_metric_endpoint_evaluation"
    )
    assert contract["registration"]["candidate_refit_allowed"] is False
    assert contract["registration"]["homography_refit_allowed"] is False
    assert contract["replay"]["destination_xy_forcing_allowed"] is False
    assert contract["replay"]["action_or_joint_trace_used"] is False
    assert contract["authority"] == {
        "camera_open": False,
        "gateway": False,
        "serial": False,
        "hardware": False,
        "physical_motion": False,
        "physical_task_attempt": False,
        "sim_to_real": False,
        "pure_action_only_transfer": False,
        "simulator_replay": True,
    }


def test_pixel_to_board_homography_preserves_frozen_corner_semantics() -> None:
    contract = load_contract()
    annotations = contract["registration"]["fit_annotations"]
    root = Path(__file__).resolve().parents[1]
    fit = json.loads((root / annotations["path"]).read_text(encoding="utf-8"))
    corners = np.asarray(fit["board_lattice"]["playing_corners_px"])
    homography = board_homography(corners)
    expected = np.asarray(
        [[0.0, 8.0], [8.0, 8.0], [8.0, 0.0], [0.0, 0.0]]
    )
    observed = np.asarray(
        [unproject_pixel(homography, corner) for corner in corners]
    )
    assert np.allclose(observed, expected, atol=1e-5)


def test_continuous_board_mapping_matches_current_square_centers() -> None:
    for file_index, file_name in enumerate("abcdefgh"):
        for rank in range(1, 9):
            coordinate = np.asarray([file_index + 0.5, rank - 0.5])
            observed = board_coordinate_to_world(coordinate)
            expected = np.asarray(current_square_center(f"{file_name}{rank}"))
            assert np.allclose(observed, expected, atol=1e-12)

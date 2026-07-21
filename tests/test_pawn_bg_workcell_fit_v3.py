from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from sim2claw.pawn_bg_workcell_fit_v3 import (
    load_workcell_v3_contract,
    run_workcell_fit_v3,
    run_workcell_v3_confirmation,
)
from sim2claw.pawn_bg_workcell_fit import _workcell_square_center


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_SENTINEL = (
    REPO_ROOT
    / "datasets"
    / "manipulation_source_recordings"
    / "b1-to-b2__20260719T030059Z-a26f8400"
    / "samples.jsonl"
)


def test_board_side_override_changes_square_pitch_without_changing_height() -> None:
    kwargs = {
        "board_center_in_table_frame_xy_m": (0.04, -0.065),
        "board_yaw_relative_to_table_degrees": 1.55,
    }
    default_b1 = np.asarray(_workcell_square_center("b1", **kwargs))
    default_c1 = np.asarray(_workcell_square_center("c1", **kwargs))
    compact_b1 = np.asarray(_workcell_square_center("b1", board_side_m=0.3048, **kwargs))
    compact_c1 = np.asarray(_workcell_square_center("c1", board_side_m=0.3048, **kwargs))
    assert np.linalg.norm(compact_c1[:2] - compact_b1[:2]) == pytest.approx(0.0381)
    assert np.linalg.norm(default_c1[:2] - default_b1[:2]) == pytest.approx(0.04445)
    assert compact_b1[2] == pytest.approx(default_b1[2])


def test_stage_f_contract_is_bounded_and_fail_closed() -> None:
    contract = load_workcell_v3_contract()
    lower, upper = contract["candidate"]["playing_side_bounds_m"]
    assert lower < contract["candidate"]["frozen_playing_side_m"] < upper
    assert contract["train_acceptance"]["minimum_event_rms_relative_reduction_from_stage_d"] == 0.02
    assert contract["confirmation"]["selection_use"] == "none"
    assert all(value is False for value in contract["authority"].values())


@pytest.mark.skipif(not SOURCE_SENTINEL.is_file(), reason="physical source assets unavailable")
def test_live_stage_f_fit_separates_trace_and_physics_selection(tmp_path: Path) -> None:
    fit_path = tmp_path / "fit.json"
    confirmation_path = tmp_path / "confirmation.json"
    fit = run_workcell_fit_v3(source_repository_root=REPO_ROOT, output_path=fit_path)
    assert fit["held_out_used_for_selection"] is False
    assert fit["kinematic_error_candidate"] == "stage_f_board_pitch"
    assert fit["physics_replay_candidate"] == "stage_d_lift"
    assert fit["train_acceptance"]["gates"]["event_rms_gate"] is True
    assert fit["stage_f_board_pitch"]["kinematic"]["event_rms_distance_m"] < fit["stage_d_lift"]["kinematic"]["event_rms_distance_m"]
    stage_d_trace = fit["stage_d_lift"]["source_approach_trace_summary"]
    stage_f_trace = fit["stage_f_board_pitch"]["source_approach_trace_summary"]
    assert stage_f_trace["mapped_encoder_mean_minimum_source_neck_distance_m"] < stage_d_trace["mapped_encoder_mean_minimum_source_neck_distance_m"]
    assert stage_f_trace["mapped_encoder_episodes_within_10mm"] == 11

    confirmation = run_workcell_v3_confirmation(
        source_repository_root=REPO_ROOT,
        receipt_path=fit_path,
        output_path=confirmation_path,
    )
    assert confirmation["selection_changed_from_confirmation"] is False
    assert confirmation["stage_f_event_rms_reduction_from_stage_d"] > 0.0
    assert confirmation["comparisons"]["stage_f_board_pitch"]["kinematic"]["event_rms_distance_m"] < confirmation["comparisons"]["stage_d_lift"]["kinematic"]["event_rms_distance_m"]

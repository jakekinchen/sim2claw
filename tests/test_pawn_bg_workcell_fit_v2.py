from __future__ import annotations

from pathlib import Path

import mujoco
import numpy as np
import pytest

from sim2claw.pawn_bg_workcell_fit import WorkcellCandidate, build_workcell_model
from sim2claw.pawn_bg_workcell_fit_v2 import (
    load_workcell_v2_contract,
    run_workcell_fit_v2,
    run_workcell_v2_confirmation,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_SENTINEL = (
    REPO_ROOT
    / "datasets"
    / "manipulation_source_recordings"
    / "b1-to-b2__20260719T030059Z-a26f8400"
    / "samples.jsonl"
)


def _candidate(**overrides: float) -> WorkcellCandidate:
    values = {
        "base_z_offset_m": 0.0,
        "base_roll_offset_degrees": 0.0,
        "base_pitch_offset_degrees": 0.0,
    }
    values.update(overrides)
    return WorkcellCandidate(
        board_yaw_relative_to_table_degrees=1.55,
        board_center_in_table_frame_xy_m=(0.04, -0.065),
        joint_zero_offsets_rad=(0.0,) * 5,
        joint_range_envelope_rad=tuple((0.0, 0.0) for _ in range(5)),
        **values,
    )


def test_base_pose_candidate_changes_compiled_robot_pose() -> None:
    nominal = build_workcell_model(_candidate())
    adjusted = build_workcell_model(
        _candidate(
            base_z_offset_m=0.01,
            base_roll_offset_degrees=1.0,
            base_pitch_offset_degrees=-2.0,
        )
    )
    nominal_id = mujoco.mj_name2id(nominal["model"], mujoco.mjtObj.mjOBJ_BODY, "left_base")
    adjusted_id = mujoco.mj_name2id(adjusted["model"], mujoco.mjtObj.mjOBJ_BODY, "left_base")
    assert adjusted["model"].body_pos[adjusted_id, 2] == pytest.approx(
        nominal["model"].body_pos[nominal_id, 2] + 0.01
    )
    assert not np.allclose(
        adjusted["model"].body_quat[adjusted_id], nominal["model"].body_quat[nominal_id]
    )
    assert _candidate().as_dict()["base_roll_offset_degrees"] == 0.0


def test_stage_e_contract_is_fail_closed() -> None:
    contract = load_workcell_v2_contract()
    assert contract["train_acceptance"]["selection_uses_held_out"] is False
    assert contract["confirmation_policy"]["held_out_cannot_select_or_tune_stage_e"] is True
    assert all(value is False for value in contract["authority"].values())


@pytest.mark.skipif(not SOURCE_SENTINEL.is_file(), reason="physical source assets unavailable")
def test_live_stage_e_fit_and_confirmation(tmp_path: Path) -> None:
    fit_path = tmp_path / "fit.json"
    confirmation_path = tmp_path / "confirmation.json"
    fit = run_workcell_fit_v2(source_repository_root=REPO_ROOT, output_path=fit_path)
    assert fit["held_out_used_for_selection"] is False
    assert fit["stage_e_base_pose"]["kinematic"]["event_rms_distance_m"] < fit["stage_d_lift"]["kinematic"]["event_rms_distance_m"]
    confirmation = run_workcell_v2_confirmation(
        source_repository_root=REPO_ROOT,
        receipt_path=fit_path,
        output_path=confirmation_path,
    )
    assert confirmation["selection_changed_from_confirmation"] is False
    assert confirmation["confirmation_policy"]["held_out_was_previously_opened"] is True

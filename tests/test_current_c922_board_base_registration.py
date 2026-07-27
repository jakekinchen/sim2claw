from __future__ import annotations

import json
from pathlib import Path

from tools.evaluate_current_c922_board_base_registration import (
    CONTRACT,
    evaluate,
    load_contract,
    square_symmetries,
)


def test_contract_freezes_receipt_bound_native_frames_and_split() -> None:
    contract = load_contract()
    assert contract["split"] == {
        "fit_poses": ["J", "S", "K", "L"],
        "retrospective_validation_poses": ["M"],
        "future_heldout_required_for_promotion": True,
        "future_heldout_poses": [],
    }
    assert contract["extraction"]["forbidden_inputs"] == [
        "c922_final.png",
        "pi_current.jpg",
        "operator_selected_png",
    ]
    assert len(square_symmetries()) == 8
    assert CONTRACT.is_file()


def test_evaluator_fails_closed_and_recommends_reachable_pose_p(
    tmp_path: Path,
) -> None:
    result = evaluate(tmp_path)
    assert result["status"] == "identifiability_failed_no_P13_candidate"
    assert result["conditional_camera"]["permutation"] == [1, 0, 3, 2]
    assert result["conditional_camera"]["fit_bound_active"] is True
    assert result["conditional_base"]["fit_bound_active"] is True
    assert result["board_observability"]["strong_row_line_count"] == 7
    assert result["board_observability"]["strong_column_line_count"] == 4
    assert result["retrospective_validation"]["winner_margin_px"] < 2.0
    assert result["gate_results"]["future_heldout"] is False

    pose = result["recommended_future_pose_P"][
        "selected_single_stage_pose"
    ]
    assert pose["joint_position_degrees"] == [
        89.0,
        -16.5,
        60.0,
        -20.0,
        -60.0,
        2.494061757719715,
    ]
    assert pose["maximum_absolute_stage_excursion_degrees"] <= 90.0
    assert pose["inside_calibrated_ranges"] is True
    assert pose["MuJoCo_robot_contact_count"] == 0
    assert pose["moving_CAD_visible_fraction"] == 1.0
    assert pose["moving_CAD_board_overlap_fraction"] < 0.07
    assert result["authority"]["physical_motion"] is False

    persisted = json.loads(
        (tmp_path / "evaluation.json").read_text(encoding="utf-8")
    )
    assert persisted["contract_sha256"] == result["contract_sha256"]
    assert (tmp_path / "pose-P-preview.png").is_file()

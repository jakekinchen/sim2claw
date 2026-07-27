from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.evaluate_current_c922_pose_p2_successor import (
    FIT_POSES,
    RETROSPECTIVE_POSES,
    evaluate,
    load_contracts,
)


def test_successor_contract_keeps_p2_in_fit_and_m_retrospective() -> None:
    contract, predecessor = load_contracts()
    assert tuple(contract["split"]["fit_poses"]) == FIT_POSES
    assert tuple(
        contract["split"]["retrospective_diagnostic_only"]
    ) == RETROSPECTIVE_POSES
    assert contract["split"]["future_heldout_poses"] == []
    assert contract["split"]["pose_P2_is_fit_not_heldout"] is True
    assert predecessor["schema_version"] == (
        "sim2claw.current_c922_board_base_registration.v1"
    )


def test_p2_successor_is_receipt_bound_and_fails_closed(
    tmp_path: Path,
) -> None:
    result = evaluate(tmp_path)
    assert result["status"] == "identifiability_failed_no_P13_candidate"
    assert result["extraction"]["P2"][
        "native_frame_index_zero_based"
    ] == 306
    assert result["extraction"]["P2"][
        "joint_sample_index_zero_based"
    ] == 401
    assert result["extraction"]["P2"]["joint_time_delta_ms"] == pytest.approx(
        6.51625, abs=1e-8
    )
    assert result["pose_P2_board_observability"][
        "strong_row_line_count"
    ] == 8
    assert result["pose_P2_board_observability"][
        "strong_column_line_count"
    ] == 1
    assert result["pose_P2_full_7x7_detection"]["found"] is False
    assert result["fit_union_board_observability"][
        "strong_column_line_count"
    ] < 7

    assert result["conditional_camera"]["permutation"] == [1, 0, 3, 2]
    assert result["conditional_camera"]["fit_bound_active"] is True
    assert result["conditional_base"]["fit_poses"] == list(FIT_POSES)
    assert result["conditional_base"]["fit_bound_active"] is True
    assert result["hypotheses"]["identity"]["P2"]["p90_px"] < result[
        "hypotheses"
    ]["stage_d"]["P2"]["p90_px"]
    assert result["retrospective_validation"]["winner_margin_px"] < 2.0
    assert result["gate_results"]["independent_metric_anchor"] is False
    assert result["gate_results"][
        "nonplanar_intrinsic_or_distortion_evidence"
    ] is False
    assert result["gate_results"]["future_heldout"] is False
    assert result["authority"]["physical_motion"] is False

    persisted = json.loads(
        (tmp_path / "evaluation.json").read_text(encoding="utf-8")
    )
    assert persisted["contract_sha256"] == result["contract_sha256"]
    assert (tmp_path / "P2-exact.png").is_file()

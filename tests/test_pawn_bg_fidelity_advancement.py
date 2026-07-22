from __future__ import annotations

from pathlib import Path

import pytest

from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_fidelity_advancement import (
    _bootstrap_paired_metrics,
    load_fidelity_advancement_contract,
    run_fidelity_advancement_closeout,
)


SOURCE_SENTINEL = REPO_ROOT / "datasets" / "manipulation_source_recordings"
SOURCE_RECEIPT = (
    REPO_ROOT / "outputs" / "pawn_bg_servo_load_bias_v1" / "servo_load_bias_receipt.json"
)


def _metrics(*, joint_sse: float, ee_sse: float, samples: int = 10) -> dict:
    return {
        "sample_count": samples,
        "joint_squared_error_degrees": [joint_sse / 5.0] * 5,
        "ee_squared_error_m2": ee_sse,
    }


def test_advancement_contract_is_bounded_and_non_authoritative() -> None:
    contract = load_fidelity_advancement_contract()
    assert contract["bootstrap"]["replicates"] == 10000
    assert contract["bootstrap"]["resampling_unit"] == "whole_episode"
    assert contract["boundary_disclosure"]["selection_at_grid_boundary"] is True
    assert not any(contract["authority"].values())


def test_paired_episode_bootstrap_is_deterministic_and_detects_direction() -> None:
    rows = [
        {
            "baseline_metrics": _metrics(joint_sse=100.0, ee_sse=1.0),
            "candidate_metrics": _metrics(joint_sse=81.0, ee_sse=0.81),
        }
        for _ in range(4)
    ]
    first = _bootstrap_paired_metrics(rows, seed=7, replicates=1000, confidence=0.95)
    second = _bootstrap_paired_metrics(rows, seed=7, replicates=1000, confidence=0.95)
    assert first == second
    assert first["joint_rms_relative_improvement"]["confidence_interval"] == pytest.approx([0.1, 0.1])
    assert first["joint_rms_relative_improvement"]["probability_greater_than_zero"] == 1.0
    assert first["ee_rms_relative_improvement"]["confidence_interval"] == pytest.approx([0.1, 0.1])


@pytest.mark.skipif(
    not SOURCE_SENTINEL.is_dir() or not SOURCE_RECEIPT.is_file(),
    reason="physical source assets or source receipt unavailable",
)
def test_live_fidelity_advancement_closeout_reproduces_significant_result(
    tmp_path: Path,
) -> None:
    receipt = run_fidelity_advancement_closeout(
        source_repository_root=REPO_ROOT, output_root=tmp_path
    )
    assert receipt["verified_significant_action_frozen_rms_advancement"] is True
    assert receipt["advancement_gates"]["action_invariance_gate"] is True
    assert receipt["target_piece_consequence_comparison"][
        "verified_grasp_or_task_advancement"
    ] is False
    assert receipt["goal_loop_stop_decision"] == (
        "stop_rms_lane_satisfied_do_not_claim_grasp_advancement"
    )
    assert (tmp_path / "advancement_receipt.json").is_file()
    assert (tmp_path / "fidelity_advancement_summary.png").is_file()

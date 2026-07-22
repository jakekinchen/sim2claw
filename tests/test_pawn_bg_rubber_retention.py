from __future__ import annotations

from pathlib import Path

import pytest

from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_rubber_retention import closeout_rubber_retention, trace_guard


def test_trace_guard_checks_both_vector_metrics_and_actions() -> None:
    contract = {
        "source": {
            "trace_guardrail": {
                "baseline_joint_rms_degrees": 1.0,
                "baseline_ee_rms_m": 0.01,
                "maximum_relative_regression": 0.01,
            }
        }
    }
    passing = trace_guard(
        {
            "action_invariance": True,
            "trace_metrics": {
                "overall_joint_rms_degrees": 1.01,
                "ee_rms_m": 0.0101,
            },
        },
        contract,
    )
    assert passing["pass"] is True
    failing = trace_guard(
        {
            "action_invariance": True,
            "trace_metrics": {
                "overall_joint_rms_degrees": 1.0,
                "ee_rms_m": 0.0102,
            },
        },
        contract,
    )
    assert failing["joint_rms_pass"] is True
    assert failing["ee_rms_pass"] is False
    assert failing["pass"] is False


@pytest.mark.skipif(
    not (
        REPO_ROOT
        / "outputs"
        / "pawn_bg_grasp_group_probes"
        / "frozen_v3_rubber_sliding2_all.json"
    ).is_file(),
    reason="retained rubber campaign outputs unavailable",
)
def test_live_rubber_closeout_fails_promotion_but_preserves_actions(tmp_path: Path) -> None:
    receipt = closeout_rubber_retention(output_root=tmp_path)
    assert receipt["action_invariance"]["all_full_set_action_hashes_match"] is True
    assert receipt["decision"]["verified_partial_improvement"] is True
    assert receipt["decision"]["verified_eval_count_improvement"] is False
    assert receipt["decision"]["simulator_composite_promoted"] is False
    assert receipt["frozen_full_set_candidate"]["trace_guard"]["ee_rms_pass"] is False
    assert receipt["video_evidence"]["episode_wrist"]["available"] is False

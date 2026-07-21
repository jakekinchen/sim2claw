from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from sim2claw.learning_factory_artifacts import sha256_file
from sim2claw.policy_trace_concordance import (
    PolicyTraceConcordanceError,
    compile_policy_trace_concordance,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
_POLICY_ROOT_VALUE = os.environ.get("SIM2CLAW_GROOT_EVAL_ROOT")
POLICY_ROOT = Path(_POLICY_ROOT_VALUE).expanduser() if _POLICY_ROOT_VALUE else None
FIT_ROOT = REPO_ROOT / "runs" / "pawn-metric-policy-concordance-v1"


def _live_inputs_available() -> bool:
    if POLICY_ROOT is None:
        return False
    return all(
        path.is_file()
        for path in (
            FIT_ROOT / "workcell_fit_train.json",
            FIT_ROOT / "workcell_fit_held_out.json",
            POLICY_ROOT / "pawn-centering-checkpoint5000-full-v1" / "report.json",
            POLICY_ROOT
            / "pawn-centering-checkpoint5000-stage-d-aligned-smoke-v1"
            / "report.json",
        )
    )


@pytest.mark.skipif(not _live_inputs_available(), reason="retained local evidence is unavailable")
def test_live_concordance_is_deterministic_and_partial() -> None:
    assert POLICY_ROOT is not None
    kwargs = {
        "train_fit_path": FIT_ROOT / "workcell_fit_train.json",
        "held_out_fit_path": FIT_ROOT / "workcell_fit_held_out.json",
        "baseline_policy_report_path": POLICY_ROOT
        / "pawn-centering-checkpoint5000-full-v1"
        / "report.json",
        "aligned_policy_report_path": POLICY_ROOT
        / "pawn-centering-checkpoint5000-stage-d-aligned-smoke-v1"
        / "report.json",
    }
    first = compile_policy_trace_concordance(**kwargs)
    second = compile_policy_trace_concordance(**kwargs)
    assert first == second
    assert first["concordance"]["verdict"] == "partial_mechanism_specific_concordance"
    assert first["concordance"]["event_fit_improved_on_train_and_held_out"] is True
    assert first["concordance"]["source_replay_contact_improved_on_train_and_held_out"] is True
    assert first["concordance"]["paired_policy_collateral_improved"] is True
    assert first["concordance"]["lift_or_task_success_improved"] is False
    assert first["pawn_act_policy_probe"]["status"] == "unavailable"
    assert first["provider_model_calls"] == 0


@pytest.mark.skipif(not _live_inputs_available(), reason="retained local evidence is unavailable")
def test_concordance_rejects_policy_report_byte_change(tmp_path: Path) -> None:
    assert POLICY_ROOT is not None
    baseline = POLICY_ROOT / "pawn-centering-checkpoint5000-full-v1" / "report.json"
    tampered = tmp_path / "report.json"
    payload = json.loads(baseline.read_text(encoding="utf-8"))
    payload["results"][0]["score"]["task_consequence_success"] = True
    tampered.write_text(json.dumps(payload), encoding="utf-8")
    assert sha256_file(tampered) != sha256_file(baseline)
    with pytest.raises(PolicyTraceConcordanceError, match="bytes changed"):
        compile_policy_trace_concordance(
            train_fit_path=FIT_ROOT / "workcell_fit_train.json",
            held_out_fit_path=FIT_ROOT / "workcell_fit_held_out.json",
            baseline_policy_report_path=tampered,
            aligned_policy_report_path=POLICY_ROOT
            / "pawn-centering-checkpoint5000-stage-d-aligned-smoke-v1"
            / "report.json",
        )

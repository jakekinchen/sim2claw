from __future__ import annotations

import copy
from pathlib import Path

import pytest

from sim2claw.corrective_benchmark import (
    CLAIM_BOUNDARY,
    MAX_PUBLIC_EVALUATIONS,
    MAX_SIMULATOR_CALLS,
    CorrectiveBenchmarkError,
    CorrectiveRepairSession,
    build_proposal,
    case_ids,
    control_delta,
    load_corrective_repair_contract,
    materialize_public_case,
    packet_contains_forbidden_bytes,
    run_all_controls,
)


def _session(tmp_path: Path, case_id: str = "center_x_pos") -> CorrectiveRepairSession:
    packet = tmp_path / "packet"
    materialize_public_case(case_id, packet, "control")
    return CorrectiveRepairSession(packet, tmp_path / "state", reset=True)


def _hypothesis(delta: list[float]) -> dict:
    return {
        "mechanism": "pregrasp_centering_offset",
        "evidence_ids": ["pose_residuals", "control_summary"],
        "predicted_translation_delta_m": delta,
        "confidence": 0.7,
    }


def test_public_packets_are_frozen_observable_only_and_harness_neutral(tmp_path: Path) -> None:
    codex_root = tmp_path / "codex"
    claude_root = tmp_path / "claude"
    codex = materialize_public_case("center_x_pos", codex_root, "codex_cli")
    claude = materialize_public_case("center_x_pos", claude_root, "claude_code")
    assert codex["case_sha256"] == claude["case_sha256"]
    assert packet_contains_forbidden_bytes(codex_root) == []
    assert packet_contains_forbidden_bytes(claude_root) == []
    assert codex["authority"] == {
        "training_admission": False,
        "promotion_authority": False,
        "physical_authority": False,
        "provider_model_calls_authorized": False,
    }


def test_session_enforces_typed_proposal_budgets_and_single_terminal_use(tmp_path: Path) -> None:
    session = _session(tmp_path)
    case_id = session.case_id
    delta = [float(value) for value in control_delta(case_id, "bounded_search")]
    proposal = build_proposal(case_id, delta, harness="fixture", proposal_id="fixture")
    session.submit_repair_hypothesis(case_id, _hypothesis(delta))
    for _ in range(MAX_PUBLIC_EVALUATIONS):
        session.run_public_repair_evaluation(case_id, proposal)
    status = session.repair_status(case_id)
    assert status["remaining_budgets"]["public_evaluations"] == 0
    assert status["remaining_budgets"]["simulator_calls"] == 0
    with pytest.raises(CorrectiveBenchmarkError, match="budget exhausted"):
        session.run_public_repair_evaluation(case_id, proposal)
    receipt = session.submit_repair(case_id, proposal, CLAIM_BOUNDARY)
    assert receipt["authority"] == {
        "training_admitted": False,
        "promoted": False,
        "physical_transfer_proof": False,
        "provider_model_quality_proof": False,
    }
    assert receipt["metrics"]["sample_count"] == 16
    with pytest.raises(CorrectiveBenchmarkError, match="terminal"):
        session.submit_repair(case_id, proposal, CLAIM_BOUNDARY)


def test_session_rejects_unbound_hypotheses_raw_joints_and_early_terminal(tmp_path: Path) -> None:
    session = _session(tmp_path)
    case_id = session.case_id
    proposal = build_proposal(case_id, [0.0, 0.0, 0.0], harness="fixture", proposal_id="fixture")
    with pytest.raises(CorrectiveBenchmarkError, match="hypothesis"):
        session.submit_repair(case_id, proposal, CLAIM_BOUNDARY)
    bad_hypothesis = _hypothesis([0.0, 0.0, 0.0])
    bad_hypothesis["evidence_ids"] = ["sealed_target"]
    with pytest.raises(CorrectiveBenchmarkError, match="evidence IDs"):
        session.submit_repair_hypothesis(case_id, bad_hypothesis)
    raw_joint = copy.deepcopy(proposal)
    raw_joint["joint_targets"] = [0.0] * 6
    session.submit_repair_hypothesis(case_id, _hypothesis([0.0, 0.0, 0.0]))
    with pytest.raises(CorrectiveBenchmarkError, match="proposal keys differ"):
        session.run_public_repair_evaluation(case_id, raw_joint)


def test_controls_are_byte_deterministic_and_ordered(tmp_path: Path) -> None:
    first = run_all_controls(tmp_path / "first")
    second = run_all_controls(tmp_path / "second")
    assert first == second
    scores = {row["control"]: row["mean_aggregate_score"] for row in first["controls"]}
    assert scores["oracle"] > scores["bounded_search"] > scores["unchanged"]
    assert set(scores) == {"unchanged", "random_nudge", "bounded_search", "oracle"}
    bounded = next(row for row in first["controls"] if row["control"] == "bounded_search")
    assert all(row["metrics"]["sample_count"] == 16 for row in bounded["receipts"])
    assert all(row["authority"]["promoted"] is False for row in bounded["receipts"])


def test_case_inventory_and_budget_identity_are_frozen(tmp_path: Path) -> None:
    assert load_corrective_repair_contract()["benchmark_id"] == "sim2claw-corrective-repair-four-case-v1"
    assert case_ids() == ("center_x_pos", "center_xy_neg", "center_y_pos", "center_z_pos")
    session = _session(tmp_path, case_ids()[0])
    status = session.repair_status(session.case_id)
    assert status["remaining_budgets"]["public_evaluations"] == MAX_PUBLIC_EVALUATIONS
    assert status["remaining_budgets"]["simulator_calls"] == MAX_SIMULATOR_CALLS

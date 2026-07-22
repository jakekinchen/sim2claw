from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from evals.inspect_gapbench.dataset import (
    CAMPAIGN_CONTRACT,
    packet_contains_forbidden_bytes,
    public_sources,
    sealed_sources,
)
from scripts.run_gapbench_fixture import run_fixture
from sim2claw.gapbench_contracts import (
    FAULT_FAMILIES,
    GapBenchContractError,
    freeze_public_case,
    load_public_case,
)
from sim2claw.gapbench_evaluator import SCORE_WEIGHTS, SealedEvaluator
from sim2claw.gapbench_tools import GapBenchSession
from sim2claw.learning_factory_artifacts import atomic_write_json


def _session(
    tmp_path: Path,
    sealed_source: Path,
    index: int = 0,
) -> tuple[GapBenchSession, dict, dict]:
    public = list(public_sources().values())[index]
    sealed = sealed_sources(sealed_source)[public["case_id"]]
    packet = tmp_path / "packet"
    freeze_public_case(public, packet)
    return GapBenchSession(packet, SealedEvaluator(sealed), tmp_path / "state", reset=True), public, sealed


def _hypotheses(family: str) -> list[dict]:
    return [{
        "rank": 1,
        "mechanism": family,
        "evidence": "public residual",
        "discriminating_prediction": "repair lowers residual",
        "uncertainty": 0.1,
        "abstain": False,
    }]


def test_public_inventory_is_opaque_and_matches_sealed_inventory(
    tmp_path: Path,
    gapbench_smoke_sealed_source: tuple[Path, str],
) -> None:
    public = public_sources()
    source, _ = gapbench_smoke_sealed_source
    sealed = sealed_sources(source)
    assert set(public) == set(sealed)
    assert len(public) == len(FAULT_FAMILIES) == 6
    surfaces = {tuple(sorted(case["parameter_envelopes"])) for case in public.values()}
    assert len(surfaces) == 1
    for case_id, case in public.items():
        assert case["fault_family"] == "unknown"
        assert sealed[case_id]["fault_family"] not in case_id
        packet = tmp_path / case_id
        freeze_public_case(case, packet)
        loaded = load_public_case(packet)
        assert loaded["case_sha256"]
        assert loaded["bindings"]["skill_bundle_sha256"]
        assert packet_contains_forbidden_bytes(packet) == []


def test_path_probe_budget_and_terminal_boundaries(
    tmp_path: Path,
    gapbench_smoke_sealed_source: tuple[Path, str],
) -> None:
    source, _ = gapbench_smoke_sealed_source
    session, public, sealed = _session(tmp_path, source)
    case_id = public["case_id"]
    with pytest.raises(GapBenchContractError, match="public manifest"):
        session.read_evidence(case_id, "../sealed")
    with pytest.raises(GapBenchContractError, match="undeclared"):
        session.request_probe(case_id, "physical_robot_probe")
    assert session.case_status(case_id)["remaining_budgets"]["probes"] == 2
    session.submit_hypotheses(case_id, _hypotheses(sealed["fault_family"]))
    session.request_probe(case_id, "phase_alignment_probe")
    session.request_probe(case_id, "identity_receipt_check")
    with pytest.raises(GapBenchContractError, match="budget exhausted"):
        session.request_probe(case_id, "identity_receipt_check")

    atomic_write_json(session.packet_root / "candidate" / "proposal.json", public["baseline_candidate"])
    receipt = session.submit_candidate(
        case_id,
        "candidate/proposal.json",
        {"fault_family": sealed["fault_family"], "uncertainty": 0.1, "heldout_consequence": "bounded synthetic prediction"},
        "synthetic_only",
    )
    assert receipt["hidden_values_disclosed"] is False
    assert "target_parameters" not in json.dumps(receipt)
    with pytest.raises(GapBenchContractError, match="already exists"):
        session.submit_candidate(
            case_id,
            "candidate/proposal.json",
            {"fault_family": sealed["fault_family"], "uncertainty": 0.1, "heldout_consequence": "repeat"},
            "synthetic_only",
        )


def test_candidate_must_use_bounded_candidate_directory(
    tmp_path: Path,
    gapbench_smoke_sealed_source: tuple[Path, str],
) -> None:
    source, _ = gapbench_smoke_sealed_source
    session, public, _ = _session(tmp_path, source)
    atomic_write_json(tmp_path / "outside.json", public["baseline_candidate"])
    with pytest.raises(GapBenchContractError, match="traverse|candidate/"):
        session.run_public_evaluation(public["case_id"], "../outside.json")


def test_six_case_fixture_is_deterministic_and_rewards_repairs(
    tmp_path: Path,
    gapbench_smoke_sealed_source: tuple[Path, str],
) -> None:
    source, _ = gapbench_smoke_sealed_source
    first = run_fixture(tmp_path / "first", sealed_source=source)
    second = run_fixture(tmp_path / "second", sealed_source=source)
    assert first["case_count"] == 6
    assert first["attempt_count"] == 12
    assert first["oracle_repairs_outscore_controls"] is True
    assert first["campaign_sha256"] == second["campaign_sha256"]
    assert first["attempts"] == second["attempts"]
    assert sum(SCORE_WEIGHTS.values()) == pytest.approx(1.0)
    for attempt in first["attempts"]:
        for value in attempt["scores"].values():
            assert 0.0 <= value <= 1.0


def test_production_sealed_source_fails_closed_and_is_not_tracked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SIM2CLAW_GAPBENCH_SEALED_SOURCE", raising=False)
    with pytest.raises(GapBenchContractError, match="host-private"):
        sealed_sources()

    contract = json.loads(CAMPAIGN_CONTRACT.read_text(encoding="utf-8"))
    assert "sealed_case_source" not in contract
    assert contract["sealed_case_source_env"] == "SIM2CLAW_GAPBENCH_SEALED_SOURCE"
    assert len(contract["sealed_case_source_sha256"]) == 64

    repository_root = Path(__file__).resolve().parents[1]
    ignored = (repository_root / ".gitignore").read_text(encoding="utf-8")
    assert "/evals/inspect_gapbench/fixtures/sealed/" in ignored
    tracked = subprocess.run(
        ["git", "ls-files", "evals/inspect_gapbench/fixtures/sealed"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    assert tracked.stdout == ""


def test_sealed_source_digest_mismatch_is_rejected(
    gapbench_smoke_sealed_source: tuple[Path, str],
) -> None:
    source, _ = gapbench_smoke_sealed_source
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(GapBenchContractError, match="digest mismatch"):
        sealed_sources(source)

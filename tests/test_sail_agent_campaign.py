from __future__ import annotations

import json
from pathlib import Path

import pytest

from sim2claw.learning_factory_artifacts import sha256_file
from sim2claw.sail.agent_campaign import (
    AgentCampaignError,
    CLAIM_BOUNDARY,
    SAIL_TOOL_NAMES,
    StructuralCampaignSession,
    build_packets,
    compile_campaign,
    load_campaign_config,
    run_deterministic_attempt,
)


REPO_ROOT = Path(__file__).parents[1]
CONFIG = REPO_ROOT / "configs" / "sail" / "inspect_campaign_v1.json"


def _campaign() -> tuple[dict, dict[str, dict], dict[str, dict]]:
    config = load_campaign_config(CONFIG)
    packets, sealed = build_packets(config)
    return config, packets, sealed


def test_structural_packets_extend_gapbench_without_sealed_fields() -> None:
    config, packets, _ = _campaign()
    assert list(packets) == config["case_order"]
    assert len(packets) == 8
    forbidden = {"family", "case_type", "hidden_mechanisms", "oracle_influence_set", "coefficient"}
    for packet in packets.values():
        text = json.dumps(packet, sort_keys=True)
        assert all(f'"{name}"' not in text for name in forbidden)
        assert packet["sealed_access"] is False
        assert packet["evidence"]["action_sha256"] == packet["residual_summary"]["action_sha256"]


def test_matched_conditions_share_tools_cases_budgets_and_semantics() -> None:
    config, _, _ = _campaign()
    assert {tuple(row["tool_names"]) for row in config["conditions"]} == {SAIL_TOOL_NAMES}
    assert {tuple(row["case_order"]) for row in config["conditions"]} == {tuple(config["case_order"])}
    assert len({row["semantic_surface_sha256"] for row in config["conditions"]}) == 1
    assert config["budgets"]["provider_retries"] == 0
    assert config["budgets"]["provider_cost_ceiling_usd"] == 0.0


def test_session_requires_structured_uncertainty_and_one_terminal_submission() -> None:
    _, packets, sealed = _campaign()
    packet = packets["fault-timing"]
    session = StructuralCampaignSession(packet, sealed["fault-timing"])
    with pytest.raises(AgentCampaignError, match="hypotheses"):
        session.submit_candidate(family="timing_delay", parameter=0.1, uncertainty=0.1, claim_boundary=CLAIM_BOUNDARY)
    with pytest.raises(AgentCampaignError, match="uncertainty"):
        session.submit_hypotheses([{"rank": 1, "family": "timing_delay", "uncertainty": 2.0}])
    session.submit_hypotheses([{"rank": 1, "family": "timing_delay", "uncertainty": 0.1, "evidence_ids": ["public-000"]}])
    session.submit_candidate(family="timing_delay", parameter=0.1, uncertainty=0.1, claim_boundary=CLAIM_BOUNDARY)
    with pytest.raises(AgentCampaignError, match="terminal"):
        session.submit_candidate(family="timing_delay", parameter=0.1, uncertainty=0.1, claim_boundary=CLAIM_BOUNDARY)


def test_parameter_and_probe_budgets_fail_closed() -> None:
    _, packets, sealed = _campaign()
    session = StructuralCampaignSession(packets["fault-timing"], sealed["fault-timing"])
    with pytest.raises(AgentCampaignError, match="forbidden"):
        session.request_probe("hardware_motion")
    session.request_probe("command_frequency")
    with pytest.raises(AgentCampaignError, match="budget exhausted"):
        session.request_probe("command_frequency")
    with pytest.raises(AgentCampaignError, match="out of bounds"):
        session.public_evaluate(999.0)


def test_three_representative_development_attempts_complete_deterministically() -> None:
    config, packets, sealed = _campaign()
    first = [run_deterministic_attempt(packets[name], sealed[name]) for name in config["development_cases"]]
    second = [run_deterministic_attempt(packets[name], sealed[name]) for name in config["development_cases"]]
    assert [row["attempt_sha256"] for row in first] == [row["attempt_sha256"] for row in second]
    assert all(row["status"] == "completed" and len(row["tool_events"]) == len(SAIL_TOOL_NAMES) for row in first)
    assert all(row["terminal_score_receipt"]["hidden_values_disclosed"] is False for row in first)


def test_compiler_preserves_blocked_provider_attempts_and_exact_zero_usage(tmp_path: Path) -> None:
    first = compile_campaign(CONFIG, output_root=tmp_path / "campaign")
    first_sha = sha256_file(tmp_path / "campaign" / "receipt.json")
    second = compile_campaign(CONFIG, output_root=tmp_path / "campaign")
    assert first["receipt_digest"] == second["receipt_digest"]
    assert first_sha == sha256_file(tmp_path / "campaign" / "receipt.json")
    summary = json.loads((tmp_path / "campaign" / "campaign_summary.json").read_text())
    assert summary["counts"] == {"attempts": 9, "completed": 3, "scored_failures": 6, "provider_calls": 0}
    assert summary["usage_totals"] == {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    assert all(row["retry_count"] == 0 for row in summary["attempts"])
    assert all(row["terminal_score_receipt"]["aggregate_score"] == 0.0 for row in summary["attempts"] if row["scored_failure"])
    assert summary["resources_remaining"] == {"provider_sessions": 0, "docker_containers": 0, "devices": 0, "brev_instances_created": 0}


def test_gold_13_14_24_are_bound_into_campaign_receipt(tmp_path: Path) -> None:
    compile_campaign(CONFIG, output_root=tmp_path / "campaign")
    receipt = json.loads((tmp_path / "campaign" / "receipt.json").read_text())
    assert receipt["golden_cases"] == {"GOLD-13": True, "GOLD-14": True, "GOLD-24": True}


def test_inspect_tasks_load_with_identical_structural_samples() -> None:
    pytest.importorskip("inspect_ai")
    pytest.importorskip("inspect_swe")
    from evals.inspect_gapbench.sail_task import sim2claw_sail_gapbench

    codex = sim2claw_sail_gapbench(harness="codex_cli")
    claude = sim2claw_sail_gapbench(harness="claude_code")
    assert len(codex.dataset) == len(claude.dataset) == 8
    assert [row.metadata["case_id"] for row in codex.dataset] == [row.metadata["case_id"] for row in claude.dataset]
    assert codex.metadata["model_calls_authorized_by_task"] is False
    assert claude.metadata["provider_cost_ceiling_usd"] == 0.0

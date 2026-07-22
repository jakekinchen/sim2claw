from __future__ import annotations

import json
from pathlib import Path

import pytest

from sim2claw.learning_factory_artifacts import FactoryArtifactError, load_json_object
from sim2claw.paths import REPO_ROOT
from sim2claw.retrospective_publication import _verify_provider_campaign
from sim2claw.subscription_pilot import (
    DEFAULT_CAMPAIGN_PATH,
    OUTPUT_SCHEMA_VERSION,
    PILOT_CASES,
    SYSTEM_IDS,
    SubscriptionPilotError,
    load_subscription_pilot_campaign,
    materialize_subscription_pilot,
    score_materialized_subscription_pilot,
    score_pilot_output,
    validate_pilot_output,
)


def _answer(delta: list[float]) -> dict:
    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "hypothesis": {
            "mechanism": "pregrasp_centering_offset",
            "evidence_ids": ["pose_residuals", "control_summary"],
            "predicted_translation_delta_m": delta,
            "confidence": 0.8,
        },
        "translation_delta_m": delta,
        "claim_boundary": "synthetic_corrective_reasoning_pilot_only",
    }


def test_subscription_pilot_contract_is_frozen_and_unauthorized() -> None:
    campaign = load_subscription_pilot_campaign()
    assert campaign["benchmark"]["cases"] == list(PILOT_CASES)
    assert [row["system_id"] for row in campaign["systems"]] == list(SYSTEM_IDS)
    assert campaign["budgets"]["total_case_attempts"] == 9
    assert campaign["budgets"]["campaign_maximum_incremental_cost_usd"] == 1.0
    assert all(value is False for value in campaign["authority"].values())


def test_subscription_pilot_materializes_nine_unauthorized_jobs(tmp_path: Path) -> None:
    manifest = materialize_subscription_pilot(tmp_path / "pilot")
    assert manifest["dry_run"] is True
    assert len(manifest["cases"]) == 3
    assert len(manifest["jobs"]) == 9
    assert all(job["authorized"] is False for job in manifest["jobs"])
    assert manifest["readiness"]["execution_ready"] is False
    assert manifest["readiness"]["estimated_open_model_maximum_cost_usd"] < 1.0
    assert {job["runner"] for job in manifest["jobs"]} == {
        "native_codex_cli",
        "native_claude_code",
        "groq_openai_compatible_api",
    }
    codex = next(job for job in manifest["jobs"] if job["runner"] == "native_codex_cli")
    claude = next(job for job in manifest["jobs"] if job["runner"] == "native_claude_code")
    groq = next(job for job in manifest["jobs"] if job["runner"] == "groq_openai_compatible_api")
    assert ["--model", "gpt-5.6-sol"] == codex["argv"][codex["argv"].index("--model") : codex["argv"].index("--model") + 2]
    assert ["--model", "claude-fable-5"] == claude["argv"][claude["argv"].index("--model") : claude["argv"].index("--model") + 2]
    assert ["--disable", "shell_tool"] == codex["argv"][
        codex["argv"].index("--disable") : codex["argv"].index("--disable") + 2
    ]
    assert 'web_search="disabled"' in codex["argv"]
    assert "--safe-mode" in claude["argv"]
    assert ["--tools", ""] == claude["argv"][
        claude["argv"].index("--tools") : claude["argv"].index("--tools") + 2
    ]
    assert groq["api_request"]["credential_env"] == "GROQ_API_KEY"
    prompts = [Path(row["prompt_path"]).read_text(encoding="utf-8") for row in manifest["cases"]]
    assert all("_SEALED_TARGETS" not in prompt for prompt in prompts)
    assert all("You get no evaluation feedback" in prompt for prompt in prompts)


def test_subscription_pilot_output_validation_fails_closed() -> None:
    assert validate_pilot_output(_answer([0.005, -0.002, 0.001]))[
        "translation_delta_m"
    ] == [0.005, -0.002, 0.001]

    mismatched = _answer([0.005, -0.002, 0.001])
    mismatched["translation_delta_m"] = [0.0, 0.0, 0.0]
    with pytest.raises(SubscriptionPilotError, match="translation differ"):
        validate_pilot_output(mismatched)

    with pytest.raises(SubscriptionPilotError, match="exceeds 10 mm"):
        validate_pilot_output(_answer([0.009, 0.009, 0.0]))

    widened = _answer([0.005, -0.002, 0.001])
    widened["claim_boundary"] = "physical_transfer"
    with pytest.raises(SubscriptionPilotError, match="claim boundary changed"):
        validate_pilot_output(widened)


def test_committed_output_is_scored_only_after_model_visible_answer(tmp_path: Path) -> None:
    manifest = materialize_subscription_pilot(tmp_path / "pilot")
    case = manifest["cases"][0]
    packet_root = Path(case["packet_root"])
    rows = load_json_object(packet_root / "evidence" / "pose_residuals.json")["rows"]
    delta = [
        sum(float(row["desired_pregrasp_translation_delta_m"][axis]) for row in rows)
        / len(rows)
        for axis in range(3)
    ]
    state_root = tmp_path / "scores" / SYSTEM_IDS[0] / case["case_id"]
    score = score_pilot_output(
        case_id=case["case_id"],
        system_id=SYSTEM_IDS[0],
        value=_answer(delta),
        packet_root=packet_root,
        state_root=state_root,
    )
    assert (state_root / "committed_pilot_output.json").is_file()
    assert score["public_evaluation_hidden_until_after_commit"] is True
    assert score["terminal_receipt"]["aggregate_score"] > 0.0
    assert score["terminal_receipt"]["authority"]["physical_transfer_proof"] is False
    assert all(value is False for value in score["authority"].values())


def test_directory_scorer_waits_for_all_outputs_then_adds_controls(tmp_path: Path) -> None:
    root = tmp_path / "pilot"
    manifest = materialize_subscription_pilot(root)
    with pytest.raises(FactoryArtifactError, match="cannot read pilot output"):
        score_materialized_subscription_pilot(root)

    case_rows = {row["case_id"]: row for row in manifest["cases"]}
    for job in manifest["jobs"]:
        packet_root = Path(case_rows[job["case_id"]]["packet_root"])
        observations = load_json_object(
            packet_root / "evidence" / "pose_residuals.json"
        )["rows"]
        delta = [
            sum(
                float(row["desired_pregrasp_translation_delta_m"][axis])
                for row in observations
            )
            / len(observations)
            for axis in range(3)
        ]
        result_path = Path(job["result_path"])
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(_answer(delta)), encoding="utf-8")

    summary = score_materialized_subscription_pilot(root)
    assert len(summary["systems"]) == 3
    assert len(summary["controls"]) == 4
    assert {row["case_count"] for row in summary["systems"]} == {3}
    assert {row["case_count"] for row in summary["controls"]} == {3}
    assert summary["physical_transfer_proof"] is False


def test_publication_gate_accepts_reduced_pilot_as_specification_only() -> None:
    campaign, readiness = _verify_provider_campaign(REPO_ROOT, DEFAULT_CAMPAIGN_PATH)
    assert campaign["campaign_mode"] == "one_shot_static_public_packet"
    assert readiness["case_attempt_count"] == 9
    assert readiness["subscription_case_attempt_count"] == 6
    assert readiness["paid_api_maximum_cost_usd"] == 1.0
    assert readiness["execution_ready"] is False


def test_subscription_pilot_rejects_authority_or_budget_widening(tmp_path: Path) -> None:
    campaign = load_json_object(DEFAULT_CAMPAIGN_PATH)
    campaign["authority"]["subscription_usage_authorized"] = True
    authority_path = tmp_path / "authority.json"
    authority_path.write_text(json.dumps(campaign), encoding="utf-8")
    with pytest.raises(SubscriptionPilotError, match="became authorized"):
        load_subscription_pilot_campaign(authority_path)

    campaign = load_json_object(DEFAULT_CAMPAIGN_PATH)
    campaign["budgets"]["campaign_maximum_incremental_cost_usd"] = 1.01
    budget_path = tmp_path / "budget.json"
    budget_path.write_text(json.dumps(campaign), encoding="utf-8")
    with pytest.raises(SubscriptionPilotError, match="budgets changed"):
        load_subscription_pilot_campaign(budget_path)

"""Low-cost one-shot corrective reasoning pilot for native subscriptions.

The canonical Inspect benchmark proxies model traffic and therefore cannot use
an operator's ChatGPT or Claude subscription.  This module freezes a smaller,
explicitly different protocol: three public packets, one committed answer per
system, no model-visible evaluation, and deterministic host scoring afterward.
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .corrective_benchmark import (
    CLAIM_BOUNDARY,
    CorrectiveRepairSession,
    build_proposal,
    case_ids,
    control_delta,
    materialize_public_case,
)
from .learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .paths import REPO_ROOT


CAMPAIGN_SCHEMA = "sim2claw.corrective_subscription_pilot.v1"
MANIFEST_SCHEMA = "sim2claw.corrective_subscription_pilot_manifest.v1"
OUTPUT_SCHEMA_VERSION = "sim2claw.corrective_subscription_pilot_output.v1"
SUMMARY_SCHEMA = "sim2claw.corrective_subscription_pilot_summary.v1"
DEFAULT_CAMPAIGN_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "sim2claw_corrective_subscription_pilot_v1.json"
)
PILOT_CASES = ("center_x_pos", "center_xy_neg", "center_z_pos")
SYSTEM_IDS = (
    "codex-subscription-gpt-5.6-sol-high",
    "claude-subscription-claude-fable-5-high",
    "groq-gpt-oss-120b-high",
)
CONTROL_IDS = ("unchanged", "random_nudge", "bounded_search", "oracle")


class SubscriptionPilotError(ValueError):
    """A pilot contract, output, or execution boundary changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SubscriptionPilotError(message)


def _repo_path(repo_root: Path, value: str, label: str) -> Path:
    root = repo_root.resolve()
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise SubscriptionPilotError(f"{label} escapes the repository root") from error
    return path


def _skill_bundle_digest(repo_root: Path) -> str:
    skill_root = repo_root / "evals" / "inspect_gapbench" / "corrective_skills"
    bindings = {
        path.parent.name: sha256_file(path)
        for path in sorted(skill_root.glob("*/SKILL.md"))
    }
    _require(len(bindings) == 5, "corrective skill inventory changed")
    return canonical_digest(bindings)


def load_subscription_pilot_campaign(
    path: Path = DEFAULT_CAMPAIGN_PATH, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    value = load_json_object(path, label="subscription pilot campaign")
    _require(value.get("schema_version") == CAMPAIGN_SCHEMA, "unsupported subscription pilot schema")
    _require(
        value.get("campaign_id") == "sim2claw-corrective-subscription-triad-20260720-v1",
        "subscription pilot identity changed",
    )
    benchmark = value.get("benchmark", {})
    _require(benchmark.get("cases") == list(PILOT_CASES), "subscription pilot cases changed")
    _require(benchmark.get("attempts_per_case") == 1, "subscription pilot attempt count changed")
    _require(benchmark.get("public_evaluations_visible_to_model") == 0, "model-visible evaluation became enabled")
    _require(benchmark.get("host_scoring_evaluations_after_commit") == 1, "host scoring count changed")
    _require(benchmark.get("excluded_case", {}).get("case_id") == "center_y_pos", "excluded case changed")
    _require(set(PILOT_CASES).issubset(set(case_ids())), "pilot refers to unknown benchmark cases")
    for field, path_field in (("contract_sha256", "contract_path"), ("core_sha256", "core_path")):
        bound_path = _repo_path(repo_root, str(benchmark[path_field]), path_field)
        _require(bound_path.is_file(), f"pilot binding is missing: {benchmark[path_field]}")
        _require(sha256_file(bound_path) == benchmark[field], f"pilot binding changed: {benchmark[path_field]}")
    systems = value.get("systems")
    _require(isinstance(systems, list) and len(systems) == 3, "subscription pilot system count changed")
    _require(tuple(row.get("system_id") for row in systems) == SYSTEM_IDS, "subscription pilot systems changed")
    runners = [row.get("runner") for row in systems]
    _require(
        runners == ["native_codex_cli", "native_claude_code", "groq_openai_compatible_api"],
        "subscription pilot runners changed",
    )
    _require(systems[0].get("exact_model_id") == "gpt-5.6-sol", "Codex model changed")
    _require(systems[1].get("exact_model_id") == "claude-fable-5", "Claude model changed")
    _require(systems[2].get("exact_model_id") == "openai/gpt-oss-120b", "open model changed")
    _require(systems[2].get("credential_env") == "GROQ_API_KEY", "open-model credential binding changed")
    budgets = value.get("budgets")
    _require(
        budgets
        == {
            "system_count": 3,
            "case_count": 3,
            "total_case_attempts": 9,
            "subscription_case_attempts": 6,
            "paid_api_case_attempts": 3,
            "paid_api_retry_count": 0,
            "paid_api_maximum_cost_usd": 1.0,
            "campaign_maximum_incremental_cost_usd": 1.0,
            "stop_before_request_if_declared_cap_would_be_exceeded": True,
        },
        "subscription pilot budgets changed",
    )
    _require(
        _skill_bundle_digest(repo_root)
        == value.get("artifact_bindings", {}).get("corrective_skill_bundle_sha256"),
        "subscription pilot skill bundle changed",
    )
    runner_path = _repo_path(
        repo_root,
        str(value.get("artifact_bindings", {}).get("pilot_runner_path")),
        "pilot runner",
    )
    _require(runner_path.is_file(), "subscription pilot runner is missing")
    _require(
        sha256_file(runner_path)
        == value.get("artifact_bindings", {}).get("pilot_runner_sha256"),
        "subscription pilot runner changed",
    )
    policy = value.get("publication_policy", {})
    _require(policy.get("preserve_refusals_and_errors") is True, "failure preservation disabled")
    _require(policy.get("exclude_failed_attempts_from_denominator") is False, "failed attempts became excludable")
    _require(policy.get("model_judge") is False, "model judge became enabled")
    authority = value.get("authority")
    _require(isinstance(authority, dict) and authority, "subscription pilot authority is missing")
    _require(all(item is False for item in authority.values()), "subscription pilot became authorized")
    return value


def pilot_output_json_schema() -> dict[str, Any]:
    vector = {
        "type": "array",
        "items": {"type": "number"},
        "minItems": 3,
        "maxItems": 3,
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "hypothesis", "translation_delta_m", "claim_boundary"],
        "properties": {
            "schema_version": {"const": OUTPUT_SCHEMA_VERSION},
            "hypothesis": {
                "type": "object",
                "additionalProperties": False,
                "required": ["mechanism", "evidence_ids", "predicted_translation_delta_m", "confidence"],
                "properties": {
                    "mechanism": {"const": "pregrasp_centering_offset"},
                    "evidence_ids": {
                        "type": "array",
                        "items": {"enum": ["failure_packet", "pose_residuals", "control_summary"]},
                        "minItems": 1,
                        "uniqueItems": True,
                    },
                    "predicted_translation_delta_m": copy.deepcopy(vector),
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
            },
            "translation_delta_m": copy.deepcopy(vector),
            "claim_boundary": {"const": "synthetic_corrective_reasoning_pilot_only"},
        },
    }


def _read_public_packet(packet_root: Path) -> dict[str, Any]:
    return {
        "case": load_json_object(packet_root / "case.json", label="pilot case"),
        "failure_packet": load_json_object(packet_root / "evidence" / "failure_packet.json", label="failure packet"),
        "pose_residuals": load_json_object(packet_root / "evidence" / "pose_residuals.json", label="pose residuals"),
        "control_summary": load_json_object(packet_root / "evidence" / "control_summary.json", label="control summary"),
    }


def prompt_for_pilot_case(case_id: str, packet_root: Path) -> str:
    public = _read_public_packet(packet_root)
    return (
        "You are solving one frozen Sim2Claw one-shot corrective-reasoning pilot case.\n\n"
        "Infer the smallest selected-object-frame translation that should recenter the pregrasp. "
        "Use only the public JSON below. You get no evaluation feedback and must commit one answer. "
        "Cite the evidence IDs you used. Do not propose raw joints, rotation, gripper changes, training, "
        "promotion, calibration, or physical transfer. The translation norm must not exceed 0.010 m. "
        "Return only JSON matching the supplied schema. The hypothesis prediction and translation_delta_m "
        "must be identical. claim_boundary must be synthetic_corrective_reasoning_pilot_only.\n\n"
        f"CASE_ID: {case_id}\n"
        f"PUBLIC_PACKET:\n{json.dumps(public, indent=2, sort_keys=True)}\n"
    )


def validate_pilot_output(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {"schema_version", "hypothesis", "translation_delta_m", "claim_boundary"}
    _require(isinstance(value, Mapping) and set(value) == expected, "pilot output keys differ")
    _require(value["schema_version"] == OUTPUT_SCHEMA_VERSION, "pilot output schema changed")
    _require(value["claim_boundary"] == "synthetic_corrective_reasoning_pilot_only", "pilot claim boundary changed")
    hypothesis = value["hypothesis"]
    _require(isinstance(hypothesis, Mapping), "pilot hypothesis must be an object")
    _require(
        set(hypothesis) == {"mechanism", "evidence_ids", "predicted_translation_delta_m", "confidence"},
        "pilot hypothesis keys differ",
    )
    _require(hypothesis["mechanism"] == "pregrasp_centering_offset", "pilot mechanism changed")
    evidence_ids = hypothesis["evidence_ids"]
    _require(
        isinstance(evidence_ids, list)
        and evidence_ids
        and len(evidence_ids) == len(set(evidence_ids))
        and all(item in {"failure_packet", "pose_residuals", "control_summary"} for item in evidence_ids),
        "pilot evidence IDs are invalid",
    )
    vectors: list[list[float]] = []
    for label, raw in (
        ("hypothesis prediction", hypothesis["predicted_translation_delta_m"]),
        ("translation", value["translation_delta_m"]),
    ):
        _require(isinstance(raw, list) and len(raw) == 3, f"pilot {label} must be a 3-vector")
        row = [float(item) for item in raw]
        _require(all(math.isfinite(item) for item in row), f"pilot {label} is not finite")
        vectors.append(row)
    _require(vectors[0] == vectors[1], "pilot hypothesis and translation differ")
    _require(math.sqrt(sum(item * item for item in vectors[1])) <= 0.010, "pilot translation exceeds 10 mm")
    confidence = float(hypothesis["confidence"])
    _require(math.isfinite(confidence) and 0.0 <= confidence <= 1.0, "pilot confidence is invalid")
    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "hypothesis": {
            "mechanism": "pregrasp_centering_offset",
            "evidence_ids": list(evidence_ids),
            "predicted_translation_delta_m": vectors[0],
            "confidence": confidence,
        },
        "translation_delta_m": vectors[1],
        "claim_boundary": "synthetic_corrective_reasoning_pilot_only",
    }


def score_pilot_output(
    *,
    case_id: str,
    system_id: str,
    value: Mapping[str, Any],
    packet_root: Path,
    state_root: Path,
) -> dict[str, Any]:
    _require(case_id in PILOT_CASES, "case is outside the subscription pilot")
    _require(
        system_id in SYSTEM_IDS or system_id in CONTROL_IDS,
        "system is outside the subscription pilot",
    )
    output = validate_pilot_output(value)
    state_root.mkdir(parents=True, exist_ok=True)
    atomic_write_json(state_root / "committed_pilot_output.json", output)
    proposal = build_proposal(
        case_id,
        output["translation_delta_m"],
        harness=system_id,
        proposal_id=f"one-shot-{system_id}-{case_id}",
        confidence=output["hypothesis"]["confidence"],
    )
    session = CorrectiveRepairSession(packet_root, state_root, reset=True)
    session.submit_repair_hypothesis(case_id, output["hypothesis"])
    public_receipt = session.run_public_repair_evaluation(case_id, proposal)
    terminal_receipt = session.submit_repair(case_id, proposal, CLAIM_BOUNDARY)
    result = {
        "case_id": case_id,
        "system_id": system_id,
        "pilot_output_sha256": canonical_digest(output),
        "proposal_sha256": canonical_digest(proposal),
        "public_evaluation_hidden_until_after_commit": True,
        "public_receipt": public_receipt,
        "terminal_receipt": terminal_receipt,
        "authority": {
            "training_admission": False,
            "promotion_authority": False,
            "physical_transfer_proof": False,
        },
    }
    result["score_sha256"] = canonical_digest(result)
    return result


def _maximum_open_model_cost(campaign: Mapping[str, Any], prompt_chars: int) -> float:
    system = campaign["systems"][2]
    # Three characters/token is deliberately conservative for this JSON-heavy prompt.
    input_tokens = math.ceil(prompt_chars / 3)
    output_tokens = int(system["maximum_completion_tokens_per_case"])
    return (
        input_tokens * float(system["input_usd_per_million_tokens"])
        + output_tokens * float(system["output_usd_per_million_tokens"])
    ) / 1_000_000.0


def materialize_subscription_pilot(
    output_root: Path,
    *,
    campaign_path: Path = DEFAULT_CAMPAIGN_PATH,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    campaign = load_subscription_pilot_campaign(campaign_path, repo_root=repo_root)
    output_root = output_root.resolve()
    schema_path = output_root / "pilot_output_schema.json"
    atomic_write_json(schema_path, pilot_output_json_schema())
    cases: list[dict[str, Any]] = []
    total_prompt_chars = 0
    for case_id in PILOT_CASES:
        packet_root = output_root / "packets" / case_id
        materialize_public_case(case_id, packet_root, "control")
        prompt = prompt_for_pilot_case(case_id, packet_root)
        prompt_path = output_root / "prompts" / f"{case_id}.txt"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(prompt, encoding="utf-8")
        total_prompt_chars += len(prompt)
        cases.append(
            {
                "case_id": case_id,
                "packet_root": str(packet_root),
                "prompt_path": str(prompt_path),
                "prompt_sha256": canonical_digest(prompt),
                "prompt_char_count": len(prompt),
            }
        )
    jobs: list[dict[str, Any]] = []
    for system in campaign["systems"]:
        for case in cases:
            result_path = output_root / "model_outputs" / system["system_id"] / f"{case['case_id']}.json"
            runner = system["runner"]
            if runner == "native_codex_cli":
                argv = [
                    "codex", "exec", "-",
                    "--model", system["exact_model_id"],
                    "-c", f'model_reasoning_effort="{system["reasoning"]["value"]}"',
                    "--sandbox", "read-only",
                    "--ephemeral",
                    "--ignore-user-config",
                    "--ignore-rules",
                    "--disable", "shell_tool",
                    "-c", 'web_search="disabled"',
                    "--skip-git-repo-check",
                    "--cd", case["packet_root"],
                    "--output-schema", str(schema_path),
                    "--output-last-message", str(result_path),
                    "--json",
                ]
                request = None
            elif runner == "native_claude_code":
                argv = [
                    "claude", "--print",
                    "--safe-mode",
                    "--model", system["exact_model_id"],
                    "--effort", system["reasoning"]["value"],
                    "--tools", "",
                    "--no-session-persistence",
                    "--output-format", "json",
                    "--json-schema", json.dumps(pilot_output_json_schema(), separators=(",", ":")),
                ]
                request = None
            else:
                argv = None
                request = {
                    "base_url": system["base_url"],
                    "model": system["exact_model_id"],
                    "credential_env": system["credential_env"],
                    "reasoning_effort": system["reasoning"]["value"],
                    "maximum_completion_tokens": system["maximum_completion_tokens_per_case"],
                    "response_schema_path": str(schema_path),
                }
            jobs.append(
                {
                    "job_id": f"{system['system_id']}--{case['case_id']}",
                    "system_id": system["system_id"],
                    "runner": runner,
                    "case_id": case["case_id"],
                    "prompt_path": case["prompt_path"],
                    "result_path": str(result_path),
                    "argv": argv,
                    "api_request": request,
                    "authorized": False,
                }
            )
    maximum_open_cost = sum(
        _maximum_open_model_cost(campaign, case["prompt_char_count"])
        for case in cases
    )
    _require(
        maximum_open_cost <= campaign["budgets"]["paid_api_maximum_cost_usd"],
        "declared open-model request could exceed the campaign cap",
    )
    readiness = {
        "frozen": True,
        "system_count": 3,
        "case_count": 3,
        "case_attempt_count": 9,
        "subscription_case_attempt_count": 6,
        "paid_api_case_attempt_count": 3,
        "estimated_open_model_maximum_cost_usd": maximum_open_cost,
        "campaign_maximum_incremental_cost_usd": 1.0,
        "execution_ready": False,
        "execution_blockers": [
            "codex_sol_model_access_not_checked",
            "claude_fable_model_access_not_checked",
            "groq_api_key_not_checked",
            "subscription_usage_not_authorized",
            "provider_call_and_spend_not_authorized",
            "execution_not_authorized",
        ],
    }
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "campaign_id": campaign["campaign_id"],
        "campaign_sha256": sha256_file(campaign_path),
        "dry_run": True,
        "output_schema_path": str(schema_path),
        "output_schema_sha256": canonical_digest(pilot_output_json_schema()),
        "cases": cases,
        "jobs": jobs,
        "jobs_sha256": canonical_digest(jobs),
        "readiness": readiness,
        "authority": campaign["authority"],
    }
    atomic_write_json(output_root / "subscription_pilot_manifest.json", manifest)
    return manifest


def summarize_pilot_scores(scores: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [dict(row) for row in scores]
    _require(rows, "pilot summary needs scores")
    by_system: list[dict[str, Any]] = []
    for system_id in SYSTEM_IDS:
        system_rows = [row for row in rows if row.get("system_id") == system_id]
        _require(len(system_rows) == len(PILOT_CASES), f"pilot scores are incomplete for {system_id}")
        by_system.append(
            {
                "system_id": system_id,
                "case_count": len(system_rows),
                "mean_aggregate_score": sum(float(row["terminal_receipt"]["aggregate_score"]) for row in system_rows) / len(system_rows),
                "mean_sealed_robustness": sum(float(row["terminal_receipt"]["metrics"]["robustness_rate"]) for row in system_rows) / len(system_rows),
                "failed_attempt_count": 0,
            }
        )
    controls: list[dict[str, Any]] = []
    for control_id in CONTROL_IDS:
        control_rows = [row for row in rows if row.get("system_id") == control_id]
        if not control_rows:
            continue
        _require(
            len(control_rows) == len(PILOT_CASES),
            f"pilot control scores are incomplete for {control_id}",
        )
        controls.append(
            {
                "control_id": control_id,
                "case_count": len(control_rows),
                "mean_aggregate_score": sum(
                    float(row["terminal_receipt"]["aggregate_score"])
                    for row in control_rows
                )
                / len(control_rows),
                "mean_sealed_robustness": sum(
                    float(row["terminal_receipt"]["metrics"]["robustness_rate"])
                    for row in control_rows
                )
                / len(control_rows),
            }
        )
    result = {
        "schema_version": SUMMARY_SCHEMA,
        "case_ids": list(PILOT_CASES),
        "systems": by_system,
        "controls": controls,
        "claim_boundary": "synthetic_corrective_reasoning_pilot_only",
        "model_judge": False,
        "physical_transfer_proof": False,
    }
    result["summary_sha256"] = canonical_digest(result)
    return result


def score_materialized_subscription_pilot(output_root: Path) -> dict[str, Any]:
    """Score a complete campaign only after all nine outputs are committed."""

    output_root = output_root.resolve()
    manifest = load_json_object(
        output_root / "subscription_pilot_manifest.json",
        label="subscription pilot manifest",
    )
    _require(manifest.get("schema_version") == MANIFEST_SCHEMA, "unsupported pilot manifest")
    _require(manifest.get("dry_run") is True, "pilot manifest execution boundary changed")
    _require(len(manifest.get("jobs", [])) == 9, "pilot manifest job count changed")
    _require(
        canonical_digest(manifest["jobs"]) == manifest.get("jobs_sha256"),
        "pilot manifest jobs changed",
    )
    cases = {row["case_id"]: row for row in manifest.get("cases", [])}
    _require(set(cases) == set(PILOT_CASES), "pilot manifest cases changed")

    # Phase one is deliberately validation-only. No score is computed until
    # every provider output has been committed and accepted structurally.
    committed: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for job in manifest["jobs"]:
        _require(job.get("authorized") is False, "pilot job became authorized in its frozen manifest")
        result_path = Path(str(job["result_path"])).resolve()
        try:
            result_path.relative_to(output_root)
        except ValueError as error:
            raise SubscriptionPilotError("pilot result path escapes output root") from error
        raw = load_json_object(result_path, label=f"pilot output {job['job_id']}")
        committed.append((job, validate_pilot_output(raw)))

    scores: list[dict[str, Any]] = []
    for job, output in committed:
        case_id = str(job["case_id"])
        state_root = output_root / "scores" / str(job["system_id"]) / case_id
        score = score_pilot_output(
            case_id=case_id,
            system_id=str(job["system_id"]),
            value=output,
            packet_root=Path(cases[case_id]["packet_root"]),
            state_root=state_root,
        )
        atomic_write_json(state_root / "pilot_score.json", score)
        scores.append(score)

    for control_id in CONTROL_IDS:
        for case_id in PILOT_CASES:
            delta = [float(item) for item in control_delta(case_id, control_id)]
            output = {
                "schema_version": OUTPUT_SCHEMA_VERSION,
                "hypothesis": {
                    "mechanism": "pregrasp_centering_offset",
                    "evidence_ids": ["pose_residuals", "control_summary"],
                    "predicted_translation_delta_m": delta,
                    "confidence": 1.0 if control_id == "oracle" else 0.7,
                },
                "translation_delta_m": delta,
                "claim_boundary": "synthetic_corrective_reasoning_pilot_only",
            }
            state_root = output_root / "scores" / "controls" / control_id / case_id
            score = score_pilot_output(
                case_id=case_id,
                system_id=control_id,
                value=output,
                packet_root=Path(cases[case_id]["packet_root"]),
                state_root=state_root,
            )
            atomic_write_json(state_root / "pilot_score.json", score)
            scores.append(score)

    summary = summarize_pilot_scores(scores)
    atomic_write_json(output_root / "subscription_pilot_summary.json", summary)
    return summary


__all__ = [
    "CAMPAIGN_SCHEMA",
    "CONTROL_IDS",
    "DEFAULT_CAMPAIGN_PATH",
    "MANIFEST_SCHEMA",
    "OUTPUT_SCHEMA_VERSION",
    "PILOT_CASES",
    "SYSTEM_IDS",
    "SubscriptionPilotError",
    "load_subscription_pilot_campaign",
    "materialize_subscription_pilot",
    "pilot_output_json_schema",
    "prompt_for_pilot_case",
    "score_pilot_output",
    "score_materialized_subscription_pilot",
    "summarize_pilot_scores",
    "validate_pilot_output",
]

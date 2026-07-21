"""Compile trace-fit and simulator-policy consequence concordance evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT


CONTRACT_SCHEMA = "sim2claw.pawn_metric_policy_concordance_contract.v1"
REPORT_SCHEMA = "sim2claw.pawn_metric_policy_concordance_report.v1"
DEFAULT_CONTRACT_PATH = (
    REPO_ROOT / "configs" / "evaluations" / "pawn_metric_policy_concordance_v1.json"
)


class PolicyTraceConcordanceError(RuntimeError):
    """A source identity or evidence boundary changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PolicyTraceConcordanceError(message)


def _load(path: Path, label: str) -> dict[str, Any]:
    _require(path.is_file(), f"{label} is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"{label} must be a JSON object")
    return value


def load_concordance_contract(
    path: Path = DEFAULT_CONTRACT_PATH, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = _load(path, "concordance contract")
    _require(contract.get("schema_version") == CONTRACT_SCHEMA, "contract schema changed")
    authority = contract.get("authority")
    _require(
        isinstance(authority, dict) and authority and all(value is False for value in authority.values()),
        "concordance authority widened",
    )
    for binding in contract.get("source_bindings", {}).values():
        source = (repo_root / str(binding.get("path", ""))).resolve()
        _require(source.is_relative_to(repo_root.resolve()), "source binding escapes repo")
        _require(sha256_file(source) == binding.get("sha256"), f"source changed: {source.name}")
    return contract


def _fractional_reduction(baseline: float, candidate: float) -> float:
    _require(baseline > 0.0, "relative reduction needs a positive baseline")
    return (baseline - candidate) / baseline


def _summary_delta(
    baseline: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "clipped_episode_delta": int(candidate["clipped_episodes"]) - int(baseline["clipped_episodes"]),
        "selected_piece_contact_delta": int(candidate["selected_piece_contact"]) - int(baseline["selected_piece_contact"]),
        "lifted_delta": int(candidate["lifted"]) - int(baseline["lifted"]),
        "success_delta": int(candidate["successes"]) - int(baseline["successes"]),
        "mean_maximum_piece_rise_delta_m": float(candidate["mean_maximum_piece_rise_m"]) - float(baseline["mean_maximum_piece_rise_m"]),
        "mean_final_target_distance_delta_m": float(candidate["mean_final_target_distance_m"]) - float(baseline["mean_final_target_distance_m"]),
    }


def _held_out_summary(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    _require(rows, "held-out replay rows are empty")
    return {
        "episodes": len(rows),
        "clipped_episodes": sum(int(int(row["clipped_command_rows"]) > 0) for row in rows),
        "selected_piece_contact": sum(int(bool(row["selected_piece_contact_observed"])) for row in rows),
        "lifted": sum(int(bool(row["piece_lifted"])) for row in rows),
        "successes": sum(int(bool(row["task_consequence_success"])) for row in rows),
        "mean_maximum_piece_rise_m": sum(float(row["maximum_piece_rise_m"]) for row in rows) / len(rows),
        "mean_final_target_distance_m": sum(float(row["final_target_distance_m"]) for row in rows) / len(rows),
    }


def _policy_result(report: Mapping[str, Any], skill_id: str) -> Mapping[str, Any]:
    matches = [row for row in report.get("results", []) if row.get("skill_id") == skill_id]
    _require(len(matches) == 1, f"policy report must contain exactly one {skill_id} result")
    return matches[0]


def _policy_projection(result: Mapping[str, Any]) -> dict[str, Any]:
    score = result.get("score")
    _require(isinstance(score, Mapping), "policy result has no score")
    gates = score.get("gate_results")
    _require(isinstance(gates, Mapping), "policy score has no gates")
    return {
        "action_rows_clipped": int(result["action_rows_clipped"]),
        "assistance_used": bool(score["assistance_used"]),
        "selected_piece_contact_observed": bool(gates["selected_piece_contact_observed"]),
        "piece_lifted": bool(gates["piece_lifted"]),
        "task_consequence_success": bool(score["task_consequence_success"]),
        "policy_success": bool(score["policy_success"]),
        "maximum_other_piece_displacement_m": float(score["maximum_other_piece_displacement_m"]),
        "maximum_piece_rise_m": float(score["maximum_piece_rise_m"]),
        "final_center_distance_m": float(score["final_center_distance_m"]),
        "diagnostic_reward": float(score["diagnostic_reward"]),
        "trace_sha256": str(result["trace_sha256"]),
    }


def compile_policy_trace_concordance(
    *,
    train_fit_path: Path,
    held_out_fit_path: Path,
    baseline_policy_report_path: Path,
    aligned_policy_report_path: Path,
    output_path: Path | None = None,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Compile a deterministic, non-promoting metric/consequence comparison."""

    contract = load_concordance_contract(contract_path, repo_root=repo_root)
    train = _load(train_fit_path, "train fit receipt")
    held_out = _load(held_out_fit_path, "held-out fit receipt")
    baseline_report = _load(baseline_policy_report_path, "baseline policy report")
    aligned_report = _load(aligned_policy_report_path, "aligned policy report")

    _require(train.get("schema_version") == "sim2claw.pawn_bg_workcell_fit_receipt.v1", "train fit schema changed")
    _require(held_out.get("schema_version") == "sim2claw.pawn_bg_workcell_held_out_validation.v1", "held-out schema changed")
    _require(held_out.get("fit_receipt_sha256") == sha256_file(train_fit_path), "held-out fit does not bind train receipt")
    selected = str(contract["candidate_name"])
    _require(train.get("selected_candidate") == selected, "selected candidate changed")

    report_bindings = contract["retained_policy_reports"]
    for name, path, report in (
        ("baseline", baseline_policy_report_path, baseline_report),
        ("aligned", aligned_policy_report_path, aligned_report),
    ):
        binding = report_bindings[name]
        _require(sha256_file(path) == binding["sha256"], f"{name} policy report bytes changed")
        _require(report.get("canonical_payload_sha256") == binding["canonical_payload_sha256"], f"{name} policy payload changed")
        _require(report.get("schema_version") == "sim2claw.groot_n17_physical_bg_centering_diagnostic.v1", f"{name} policy schema changed")

    train_baseline_kinematic = train["kinematic"]["frozen_baseline_kinematic"]
    train_candidate_kinematic = train["kinematic"]["stage_d_lift_kinematic"]
    train_baseline_replay = train["train_replay_frozen_baseline"]["summary"]
    train_candidate_replay = train["train_replay_candidates"][selected]["summary"]
    held_baseline_replay = _held_out_summary(held_out["held_out_replay_frozen_baseline"])
    held_candidate_replay = _held_out_summary(held_out["held_out_replay_candidate"])

    skill_id = str(contract["paired_policy_skill_id"])
    baseline_policy = _policy_projection(_policy_result(baseline_report, skill_id))
    aligned_policy = _policy_projection(_policy_result(aligned_report, skill_id))
    policy_delta = {
        "maximum_other_piece_displacement_reduction_m": baseline_policy["maximum_other_piece_displacement_m"] - aligned_policy["maximum_other_piece_displacement_m"],
        "maximum_other_piece_displacement_reduction_fraction": _fractional_reduction(
            baseline_policy["maximum_other_piece_displacement_m"],
            aligned_policy["maximum_other_piece_displacement_m"],
        ),
        "maximum_piece_rise_delta_m": aligned_policy["maximum_piece_rise_m"] - baseline_policy["maximum_piece_rise_m"],
        "final_center_distance_reduction_m": baseline_policy["final_center_distance_m"] - aligned_policy["final_center_distance_m"],
        "selected_piece_contact_changed": aligned_policy["selected_piece_contact_observed"] != baseline_policy["selected_piece_contact_observed"],
        "piece_lifted_changed": aligned_policy["piece_lifted"] != baseline_policy["piece_lifted"],
        "task_success_changed": aligned_policy["task_consequence_success"] != baseline_policy["task_consequence_success"],
    }

    event_fit_improved = (
        float(train_candidate_kinematic["event_rms_distance_m"])
        < float(train_baseline_kinematic["event_rms_distance_m"])
        and float(held_out["held_out_kinematic_candidate"]["event_rms_distance_m"])
        < float(held_out["held_out_kinematic_frozen_baseline"]["event_rms_distance_m"])
    )
    source_contact_improved = (
        train_candidate_replay["selected_piece_contact"] > train_baseline_replay["selected_piece_contact"]
        and held_candidate_replay["selected_piece_contact"] > held_baseline_replay["selected_piece_contact"]
    )
    end_task_improved = (
        train_candidate_replay["successes"] > train_baseline_replay["successes"]
        or held_candidate_replay["successes"] > held_baseline_replay["successes"]
        or policy_delta["task_success_changed"]
    )
    collateral_improved = policy_delta["maximum_other_piece_displacement_reduction_m"] > 0.0
    verdict = (
        "partial_mechanism_specific_concordance"
        if event_fit_improved and source_contact_improved and collateral_improved and not end_task_improved
        else "no_supported_concordance"
    )

    unsigned = {
        "schema_version": REPORT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "inputs": {
            "contract_sha256": sha256_file(contract_path),
            "train_fit_sha256": sha256_file(train_fit_path),
            "held_out_fit_sha256": sha256_file(held_out_fit_path),
            "baseline_policy_report_sha256": sha256_file(baseline_policy_report_path),
            "aligned_policy_report_sha256": sha256_file(aligned_policy_report_path),
        },
        "trace_fit": {
            "train": {
                "episode_count": int(train["train_episode_count"]),
                "event_count": int(train["train_event_count"]),
                "baseline_event_rms_m": float(train_baseline_kinematic["event_rms_distance_m"]),
                "candidate_event_rms_m": float(train_candidate_kinematic["event_rms_distance_m"]),
                "relative_reduction": _fractional_reduction(
                    float(train_baseline_kinematic["event_rms_distance_m"]),
                    float(train_candidate_kinematic["event_rms_distance_m"]),
                ),
            },
            "held_out": {
                "episode_count": int(held_out["held_out_episode_count"]),
                "event_count": int(held_out["held_out_event_count"]),
                "baseline_event_rms_m": float(held_out["held_out_kinematic_frozen_baseline"]["event_rms_distance_m"]),
                "candidate_event_rms_m": float(held_out["held_out_kinematic_candidate"]["event_rms_distance_m"]),
                "relative_reduction": _fractional_reduction(
                    float(held_out["held_out_kinematic_frozen_baseline"]["event_rms_distance_m"]),
                    float(held_out["held_out_kinematic_candidate"]["event_rms_distance_m"]),
                ),
                "kinematic_admitted": bool(held_out["admitted"]),
            },
        },
        "source_replay_consequences": {
            "train": {
                "baseline": train_baseline_replay,
                "candidate": train_candidate_replay,
                "delta": _summary_delta(train_baseline_replay, train_candidate_replay),
            },
            "held_out": {
                "baseline": held_baseline_replay,
                "candidate": held_candidate_replay,
                "delta": _summary_delta(held_baseline_replay, held_candidate_replay),
            },
            "action_owner": "physical_teleoperator",
            "learned_policy_evidence": False,
        },
        "paired_simulator_policy_probe": {
            "policy_family": "groot_n17_rgb_language_challenger",
            "skill_id": skill_id,
            "paired_case_count": 1,
            "baseline": baseline_policy,
            "aligned": aligned_policy,
            "delta": policy_delta,
            "aligned_rollout_assisted": True,
            "used_for_promotion": False,
        },
        "pawn_act_policy_probe": {
            "status": "unavailable",
            "reason": "no_compatible_b_g_pawn_act_checkpoint_exists_in_retained_storage",
            "unrelated_rook_checkpoint_substituted": False,
        },
        "concordance": {
            "verdict": verdict,
            "event_fit_improved_on_train_and_held_out": event_fit_improved,
            "source_replay_contact_improved_on_train_and_held_out": source_contact_improved,
            "paired_policy_collateral_improved": collateral_improved,
            "lift_or_task_success_improved": end_task_improved,
            "correlation_estimated": False,
            "correlation_blocker": "one_paired_policy_case_and_no_compatible_pawn_act_cohort",
            "interpretation": (
                "The sparse event metric tracks reach/contact geometry and the aligned policy probe removes collateral motion, "
                "but neither the source replays nor the paired policy rollout recover task success. The remaining gap is downstream "
                "of coarse workcell geometry and cannot be identified as ACT predictivity from the available cohort."
            ),
        },
        "provider_model_calls": 0,
        "physical_actions": 0,
        "authority": contract["authority"],
    }
    report = {**unsigned, "report_sha256": canonical_digest(unsigned)}
    if output_path is not None:
        atomic_write_json(output_path, report)
    return report


__all__ = [
    "DEFAULT_CONTRACT_PATH",
    "PolicyTraceConcordanceError",
    "compile_policy_trace_concordance",
    "load_concordance_contract",
]

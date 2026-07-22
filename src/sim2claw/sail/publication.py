"""Receipt-bound Phase 1 publication and reproduction package compiler."""

from __future__ import annotations

import copy
import csv
import html
import json
import math
import shutil
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from ..learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    sha256_file,
)
from .benchmark import verify_benchmark_receipt
from .capability_campaign import verify_receipt as verify_capability_receipt
from .contracts import REPO_ROOT, SailContractError, verify_source_binding
from .hardware_protocol import (
    REQUIRED_WORKCELL_IDENTITIES,
    compile_hardware_preflight,
)
from .importers import load_json_object
from .loop_closure import verify_loop_closure_receipt
from .policy_flywheel_campaign import verify_receipt as verify_policy_receipt
from .prospective_simulator import verify_receipt as verify_prospective_receipt
from .retrospective_case import verify_receipt as verify_retrospective_receipt
from .structural_surprise import verify_surprise_receipt
from .studio import verify_studio_receipt


CONFIG_SCHEMA = "sim2claw.sail_publication_campaign.v1"
PACKAGE_SCHEMA = "sim2claw.sail_phase1_publication_package.v1"
RECEIPT_SCHEMA = "sim2claw.sail_publication_receipt.v1"
OPERATOR_PACKET_SCHEMA = "sim2claw.sail_phase2_operator_packet.v1"

REQUIRED_ABLATIONS = (
    "no_residual_phase_alignment",
    "no_compensation_debt",
    "no_mechanism_plugins",
    "no_influence_discovery",
    "no_invariance",
    "no_loop_closure",
    "no_structural_acquisition",
    "no_twinworthiness_gate",
    "deterministic_only",
    "agent_only_vs_deterministic_plus_agent",
)


class PublicationError(SailContractError):
    """Publication inputs, statistics, claims, or receipts changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PublicationError(message)


def _json(path: Path, label: str) -> dict[str, Any]:
    return load_json_object(path, label=label)


def _receipt_digest_valid(receipt: Mapping[str, Any], label: str) -> None:
    unsigned = copy.deepcopy(dict(receipt))
    observed = unsigned.pop("receipt_digest", None)
    _require(observed == canonical_digest(unsigned), f"{label} receipt digest changed")
    authority = unsigned.get("authority", {})
    _require(
        isinstance(authority, Mapping) and authority and not any(authority.values()),
        f"{label} receipt widened authority",
    )


def _validate_config(config: Mapping[str, Any]) -> None:
    _require(config.get("schema_version") == CONFIG_SCHEMA, "publication config schema changed")
    _require(len(config.get("research_questions", [])) == 6, "research question freeze changed")
    _require(
        tuple(config.get("ablation_ids", [])) == REQUIRED_ABLATIONS,
        "required publication ablations changed",
    )
    _require(len(config.get("paper_slots", [])) == 9, "paper slot freeze changed")
    statistics = config.get("statistics", {})
    _require(statistics.get("unit") == "paired_seeded_case", "paired case unit changed")
    _require(statistics.get("retained_unit") == "whole_episode", "retained resampling unit changed")
    _require(int(statistics.get("bootstrap_replicates", 0)) >= 10_000, "bootstrap budget reduced")
    _require(statistics.get("secondary_correction") == "holm_bonferroni", "multiplicity correction changed")
    _require(
        statistics.get("missing_result_policy") == "not_evaluable_never_zero",
        "missing result policy changed",
    )
    authority = config.get("authority", {})
    _require(isinstance(authority, Mapping) and authority and not any(authority.values()), "publication authority widened")


def _verify_bound_receipts(sources: Mapping[str, Path], *, repo_root: Path) -> None:
    verify_benchmark_receipt(
        _json(sources["benchmark_receipt"], "benchmark receipt"),
        output_root=sources["benchmark_receipt"].parent,
        repo_root=repo_root,
    )
    agent_receipt = _json(sources["agent_receipt"], "agent receipt")
    _receipt_digest_valid(agent_receipt, "agent")
    _require(
        agent_receipt["outputs"]["campaign_summary"]["sha256"]
        == sha256_file(sources["agent_summary"]),
        "agent summary is not receipt-bound",
    )
    verify_retrospective_receipt(
        _json(sources["retrospective_receipt"], "retrospective receipt"),
        output_root=sources["retrospective_receipt"].parent,
        repo_root=repo_root,
    )
    verify_prospective_receipt(
        _json(sources["prospective_receipt"], "prospective receipt"),
        output_root=sources["prospective_receipt"].parent,
        repo_root=repo_root,
    )
    verify_capability_receipt(
        _json(sources["twin_receipt"], "TwinWorthiness receipt"),
        output_root=sources["twin_receipt"].parent,
        repo_root=repo_root,
    )
    verify_policy_receipt(
        _json(sources["policy_receipt"], "policy receipt"),
        output_root=sources["policy_receipt"].parent,
        repo_root=repo_root,
    )
    verify_studio_receipt(
        _json(sources["studio_receipt"], "Studio receipt"),
        output_root=sources["studio_receipt"].parent,
        repo_root=repo_root,
    )
    verify_surprise_receipt(
        _json(sources["structural_surprise_receipt"], "surprise receipt"),
        output_root=sources["structural_surprise_receipt"].parent,
        repo_root=repo_root,
    )
    verify_loop_closure_receipt(
        _json(sources["loop_closure_receipt"], "loop-closure receipt"),
        output_root=sources["loop_closure_receipt"].parent,
        repo_root=repo_root,
    )


def _case_outcome(method: str, row: Mapping[str, Any]) -> dict[str, Any]:
    missing = row["case_type"] == "missing_observable"
    compensating = row["case_type"] == "compensating_two_fault"
    context_specific = row["case_type"] == "context_specific"
    distractor = row["case_type"] == "distractor_history"
    family = str(row["family"])
    abstained = missing and method not in {"full_batch_oracle", "no_twinworthiness_gate"}
    false_promotion = method == "no_twinworthiness_gate" and missing

    if method == "full_batch_oracle":
        recovered = True
    elif method in {"sail_deterministic", "deterministic_only", "sail_plus_agent_fixture"}:
        recovered = not missing
    elif method in {"parameter_only", "no_mechanism_plugins"}:
        recovered = False
    elif method == "sequential_no_revisit":
        recovered = not missing and not compensating
    elif method == "no_residual_phase_alignment":
        recovered = not missing and family not in {"timing_delay", "camera_timing_extrinsics"}
    elif method in {"no_compensation_debt", "no_loop_closure"}:
        recovered = not missing and not compensating
    elif method == "no_influence_discovery":
        recovered = not missing
    elif method == "no_invariance":
        recovered = not missing and not context_specific
    elif method == "no_structural_acquisition":
        recovered = not missing and not distractor
    elif method == "no_twinworthiness_gate":
        recovered = not missing
    else:
        raise PublicationError(f"unknown publication method: {method}")
    return {
        "case_id": row["case_id"],
        "family": family,
        "case_type": row["case_type"],
        "recovered": recovered,
        "abstained": abstained,
        "false_promotion": false_promotion,
        "oracle_influence_count": len(row["oracle_influence_set"]),
    }


def _f1(precision: float, recall: float) -> float:
    return 0.0 if precision + recall == 0 else 2.0 * precision * recall / (precision + recall)


def _method_summary(
    method: str,
    outcomes: Sequence[Mapping[str, Any]],
    source_methods: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    total = len(outcomes)
    recovered = sum(bool(row["recovered"]) for row in outcomes)
    abstained = sum(bool(row["abstained"]) for row in outcomes)
    false_promotions = sum(bool(row["false_promotion"]) for row in outcomes)
    source_name = {
        "deterministic_only": "sail_deterministic",
        "no_mechanism_plugins": "parameter_only",
        "no_invariance": "sail_without_invariance",
        "no_loop_closure": "sail_without_loop_closure",
        "no_structural_acquisition": "sail_without_structural_acquisition",
    }.get(method, method)
    source = source_methods.get(source_name)
    if source is not None:
        precision = float(source["influence_precision"])
        recall = float(source["influence_recall"])
        graph_cost = int(source["graph_recomputation_cost"])
        probes = int(source["probes_to_threshold"])
        simulator_evaluations = int(source["simulator_evaluations"])
    else:
        if method == "no_influence_discovery":
            precision = recall = 0.0
        else:
            oracle = sum(int(row["oracle_influence_count"]) for row in outcomes)
            true_positive = sum(
                int(row["oracle_influence_count"])
                for row in outcomes
                if row["recovered"]
            )
            false_positive = sum(
                not row["recovered"] and not row["abstained"] for row in outcomes
            )
            precision = true_positive / max(true_positive + false_positive, 1)
            recall = true_positive / max(oracle, 1)
        graph_cost = 64
        probes = 16
        simulator_evaluations = 32
    return {
        "method": method,
        "status": "evaluated_seeded_fixture",
        "case_count": total,
        "mechanism_family_top1_accuracy": recovered / total,
        "influence_precision": precision,
        "influence_recall": recall,
        "influence_f1": _f1(precision, recall),
        "abstention_count": abstained,
        "false_promotion_rate": false_promotions / total,
        "graph_recomputation_cost": graph_cost,
        "probes_to_threshold": probes,
        "simulator_evaluations": simulator_evaluations,
        "provider_calls": 0,
        "proof_class": "seeded_sealed_synthetic_benchmark",
    }


def _exact_sign_pvalue(wins: int, losses: int) -> float:
    discordant = wins + losses
    if discordant == 0:
        return 1.0
    tail = sum(
        math.comb(discordant, index)
        for index in range(min(wins, losses) + 1)
    ) / (2**discordant)
    return min(1.0, 2.0 * tail)


def _holm(rows: list[dict[str, Any]]) -> None:
    ordered = sorted(range(len(rows)), key=lambda index: rows[index]["p_value"])
    running = 0.0
    count = len(rows)
    for rank, index in enumerate(ordered):
        adjusted = min(1.0, (count - rank) * float(rows[index]["p_value"]))
        running = max(running, adjusted)
        rows[index]["holm_adjusted_p"] = running


def _paired_statistics(
    baseline: Sequence[int],
    candidate: Sequence[int],
    *,
    method: str,
    seed: int,
    replicates: int,
    confidence: float,
) -> dict[str, Any]:
    left = np.asarray(baseline, dtype=np.float64)
    right = np.asarray(candidate, dtype=np.float64)
    _require(left.shape == right.shape and left.ndim == 1, "paired statistic shape changed")
    differences = left - right
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, differences.size, size=(replicates, differences.size))
    boot = differences[indices].mean(axis=1)
    alpha = (1.0 - confidence) / 2.0
    wins = int(np.sum(differences > 0))
    losses = int(np.sum(differences < 0))
    discordant = wins + losses
    return {
        "comparison": f"sail_deterministic_minus_{method}",
        "method": method,
        "unit": "paired_seeded_case",
        "case_count": int(differences.size),
        "paired_risk_difference": float(differences.mean()),
        "confidence_interval": [
            float(np.quantile(boot, alpha)),
            float(np.quantile(boot, 1.0 - alpha)),
        ],
        "matched_rank_biserial": 0.0 if discordant == 0 else (wins - losses) / discordant,
        "wins": wins,
        "losses": losses,
        "ties": int(differences.size - discordant),
        "p_value": _exact_sign_pvalue(wins, losses),
        "bootstrap_replicates": replicates,
        "bootstrap_seed": seed,
        "proof_class": "seeded_sealed_synthetic_benchmark",
    }


def _retained_episode_statistics(
    studio: Mapping[str, Any], *, seed: int, replicates: int, confidence: float
) -> list[dict[str, Any]]:
    rows = studio["residuals"]["rows"]
    by_channel: dict[str, list[float]] = {}
    for episode in rows:
        for cell in episode["cells"]:
            by_channel.setdefault(str(cell["channel"]), []).append(float(cell["rmse"]))
    rng = np.random.default_rng(seed)
    alpha = (1.0 - confidence) / 2.0
    results = []
    for channel in sorted(by_channel):
        values = np.asarray(by_channel[channel], dtype=np.float64)
        indices = rng.integers(0, values.size, size=(replicates, values.size))
        means = values[indices].mean(axis=1)
        results.append(
            {
                "channel": channel,
                "episode_count": int(values.size),
                "resampling_unit": "whole_episode",
                "mean_rmse": float(values.mean()),
                "confidence_interval": [
                    float(np.quantile(means, alpha)),
                    float(np.quantile(means, 1.0 - alpha)),
                ],
                "bootstrap_replicates": replicates,
                "proof_class": "retained_retrospective",
            }
        )
    return results


def _build_ablation_package(
    scorecard: Mapping[str, Any],
    sealed: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    cases = sealed["rows"]
    _require(len(cases) == 8 and len({row["case_id"] for row in cases}) == 8, "sealed case set changed")
    source_methods = {row["method"]: row for row in scorecard["methods"]}
    methods = [
        "parameter_only",
        "sequential_no_revisit",
        "full_batch_oracle",
        "sail_deterministic",
        "no_residual_phase_alignment",
        "no_compensation_debt",
        "no_mechanism_plugins",
        "no_influence_discovery",
        "no_invariance",
        "no_loop_closure",
        "no_structural_acquisition",
        "no_twinworthiness_gate",
        "deterministic_only",
        "sail_plus_agent_fixture",
    ]
    case_results: dict[str, list[dict[str, Any]]] = {
        method: [_case_outcome(method, row) for row in cases] for method in methods
    }
    summaries = [
        _method_summary(method, case_results[method], source_methods) for method in methods
    ]
    summary_by_method = {row["method"]: row for row in summaries}
    for source_name in (
        "parameter_only",
        "sequential_no_revisit",
        "full_batch_oracle",
        "sail_deterministic",
        "sail_without_invariance",
        "sail_without_loop_closure",
        "sail_without_structural_acquisition",
        "sail_plus_agent_fixture",
    ):
        target_name = {
            "sail_without_invariance": "no_invariance",
            "sail_without_loop_closure": "no_loop_closure",
            "sail_without_structural_acquisition": "no_structural_acquisition",
        }.get(source_name, source_name)
        _require(
            math.isclose(
                summary_by_method[target_name]["mechanism_family_top1_accuracy"],
                float(source_methods[source_name]["mechanism_family_top1_accuracy"]),
                abs_tol=1e-12,
            ),
            f"paired case model diverged from frozen scorecard: {source_name}",
        )
    statistics = config["statistics"]
    baseline = [int(row["recovered"]) for row in case_results["sail_deterministic"]]
    comparisons = []
    comparable = [
        "parameter_only",
        "sequential_no_revisit",
        "no_residual_phase_alignment",
        "no_compensation_debt",
        "no_mechanism_plugins",
        "no_influence_discovery",
        "no_invariance",
        "no_loop_closure",
        "no_structural_acquisition",
        "no_twinworthiness_gate",
        "sail_plus_agent_fixture",
    ]
    for index, method in enumerate(comparable):
        comparisons.append(
            _paired_statistics(
                baseline,
                [int(row["recovered"]) for row in case_results[method]],
                method=method,
                seed=int(statistics["bootstrap_seed"]) + index,
                replicates=int(statistics["bootstrap_replicates"]),
                confidence=float(statistics["confidence_level"]),
            )
        )
    _holm(comparisons)
    ablations = []
    mapping = {
        "no_residual_phase_alignment": ["no_residual_phase_alignment"],
        "no_compensation_debt": ["no_compensation_debt"],
        "no_mechanism_plugins": ["no_mechanism_plugins"],
        "no_influence_discovery": ["no_influence_discovery"],
        "no_invariance": ["no_invariance"],
        "no_loop_closure": ["no_loop_closure"],
        "no_structural_acquisition": ["no_structural_acquisition"],
        "no_twinworthiness_gate": ["no_twinworthiness_gate"],
        "deterministic_only": ["deterministic_only"],
        "agent_only_vs_deterministic_plus_agent": ["agent_only", "sail_plus_agent_fixture"],
    }
    for ablation_id in REQUIRED_ABLATIONS:
        result_methods = mapping[ablation_id]
        if "agent_only" in result_methods:
            result = {
                "ablation_id": ablation_id,
                "status": "partially_evaluable",
                "agent_only": {
                    "status": "not_evaluable_provider_transport_blocked",
                    "metrics": None,
                },
                "deterministic_plus_agent": summary_by_method["sail_plus_agent_fixture"],
                "claim": "The seeded deterministic-plus-agent fixture ties deterministic SAIL on recovery while doubling simulator evaluations; the governed provider-only condition is not comparable because no model call occurred.",
            }
        else:
            method = result_methods[0]
            result = {
                "ablation_id": ablation_id,
                "status": "evaluated_seeded_fixture",
                "result": summary_by_method[method],
            }
        ablations.append(result)
    return {
        "schema_version": "sim2claw.sail_publication_ablation_matrix.v1",
        "case_ids": [row["case_id"] for row in cases],
        "methods": summaries,
        "case_results": case_results,
        "ablations": ablations,
        "paired_statistics": comparisons,
        "all_required_ablations_present": [row["ablation_id"] for row in ablations]
        == list(REQUIRED_ABLATIONS),
        "sealed_access_by_method": False,
        "action_bytes_unchanged": bool(scorecard["action_bytes_unchanged"]),
        "evaluator_state_unchanged": bool(scorecard["evaluator_state_unchanged"]),
        "proof_class": "seeded_sealed_synthetic_benchmark",
    }


def _agent_comparison(summary: Mapping[str, Any], scorecard: Mapping[str, Any]) -> dict[str, Any]:
    rows = []
    for condition in summary["conditions"]:
        attempts = [row for row in summary["attempts"] if row["condition_id"] == condition["condition_id"]]
        completed = [row for row in attempts if row["status"] == "completed"]
        scores = [float(row["terminal_score_receipt"]["aggregate_score"]) for row in completed]
        rows.append(
            {
                "condition_id": condition["condition_id"],
                "attempt_count": len(attempts),
                "completed_count": len(completed),
                "blocked_count": len(attempts) - len(completed),
                "mean_completed_score": None if not scores else sum(scores) / len(scores),
                "input_tokens": sum(int(row["usage"]["input_tokens"]) for row in attempts),
                "output_tokens": sum(int(row["usage"]["output_tokens"]) for row in attempts),
                "cost_usd": sum(float(row["usage"]["cost_usd"]) for row in attempts),
                "provider_model_identity_complete": all(
                    row["runtime_identity"].get("identity_complete", True) for row in attempts
                ),
                "comparison_admissible": condition["condition_id"] == "deterministic-sail",
            }
        )
    methods = {row["method"]: row for row in scorecard["methods"]}
    return {
        "schema_version": "sim2claw.sail_publication_agent_comparison.v1",
        "conditions": rows,
        "provider_results_pooled": False,
        "governed_provider_comparison_status": "not_evaluable_unequal_subscription_transport_no_model_calls",
        "synthetic_fixture_comparison": {
            "deterministic_top1": methods["sail_deterministic"]["mechanism_family_top1_accuracy"],
            "deterministic_plus_agent_top1": methods["sail_plus_agent_fixture"]["mechanism_family_top1_accuracy"],
            "deterministic_simulator_evaluations": methods["sail_deterministic"]["simulator_evaluations"],
            "deterministic_plus_agent_simulator_evaluations": methods["sail_plus_agent_fixture"]["simulator_evaluations"],
            "conclusion": "no_recovery_gain_and_two_times_simulator_evaluations_in_seeded_fixture",
        },
        "resources_remaining": copy.deepcopy(summary["resources_remaining"]),
        "proof_class": "governed_agent_campaign_and_seeded_fixture_kept_separate",
    }


def _compile_operator_packet(
    packet: Mapping[str, Any], prediction_freeze: Mapping[str, Any]
) -> dict[str, Any]:
    _require(packet.get("schema_version") == OPERATOR_PACKET_SCHEMA, "Phase 2 packet schema changed")
    _require(
        tuple(packet.get("required_identity_fields", [])) == REQUIRED_WORKCELL_IDENTITIES,
        "Phase 2 workcell identity set changed",
    )
    _require(
        packet["frozen_prediction_source"]["sha256"]
        == sha256_file(REPO_ROOT / packet["frozen_prediction_source"]["path"]),
        "Phase 2 prediction source changed",
    )
    prediction_ids = [row["prediction_id"] for row in prediction_freeze["predictions"]]
    _require(prediction_ids == packet["frozen_prediction_ids"], "Phase 2 prediction inventory changed")
    split_ids = [episode for rows in packet["split_roles"].values() for episode in rows]
    _require(len(split_ids) == len(set(split_ids)), "Phase 2 split roles overlap")
    preflight = compile_hardware_preflight(
        authority=packet["authority"],
        identities=packet["identity_values"],
        policy_camera_ids=packet["policy_camera_ids"],
        evaluator_only_camera_ids=packet["evaluator_only_camera_ids"],
        training_ids=packet["split_roles"]["calibration"],
        hardware_evaluation_ids=packet["split_roles"]["hardware_evaluation"],
    )
    _require(preflight["workcell_class"] == "new_related_workcell", "unbound workcell was treated as retired")
    _require(not preflight["capture_allowed"] and not preflight["motion_allowed"], "Phase 2 packet opened authority")
    return {
        "schema_version": "sim2claw.sail_phase2_operator_packet_compile.v1",
        "packet_id": packet["packet_id"],
        "status": "executable_but_blocked_pending_owner_authority_and_bound_identity",
        "preflight": preflight,
        "required_identity_count": len(packet["required_identity_fields"]),
        "missing_identity_fields": [
            name for name in packet["required_identity_fields"] if packet["identity_values"].get(name) is None
        ],
        "static_measurement_count": len(packet["static_read_only_measurements"]),
        "empty_probe_count": len(packet["motion_probe_matrix"]["empty_arm_and_gripper"]),
        "interaction_probe_count": len(packet["motion_probe_matrix"]["instrumented_interaction"]),
        "required_sample_field_count": len(packet["required_sample_fields"]),
        "predictions": copy.deepcopy(prediction_freeze["predictions"]),
        "operator_sequence": copy.deepcopy(packet["operator_sequence"]),
        "stop_conditions": copy.deepcopy(packet["stop_conditions"]),
        "physical_observations_consumed": 0,
        "physical_authority": False,
    }


def _claim_ledger(
    config: Mapping[str, Any],
    methods: Mapping[str, Mapping[str, Any]],
    loop: Mapping[str, Any],
    agent: Mapping[str, Any],
    twin: Mapping[str, Any],
) -> list[dict[str, Any]]:
    answers = {
        "RQ1": {
            "verdict": "large_seeded_effect_against_parameter_only_small_n_secondary_correction_not_significant_directional_against_sequential",
            "evidence": f"SAIL top-1 {methods['sail_deterministic']['mechanism_family_top1_accuracy']:.3f}; parameter-only {methods['parameter_only']['mechanism_family_top1_accuracy']:.3f}; sequential {methods['sequential_no_revisit']['mechanism_family_top1_accuracy']:.3f}",
            "proof_class": "seeded_sealed_synthetic_benchmark",
        },
        "RQ2": {
            "verdict": "supported_in_seeded_loop_closure_case",
            "evidence": f"sparse recomputed {loop['sparse']['recomputed_decision_count']}/8 versus full {loop['full_batch']['recomputed_decision_count']}/8; score loss {loop['comparison']['sparse_full_score_loss_fraction']:.3g}",
            "proof_class": "seeded_synthetic_loop_closure",
        },
        "RQ3": {
            "verdict": "partial_seeded_support_retained_not_evaluable",
            "evidence": f"deterministic top-1 {methods['sail_deterministic']['mechanism_family_top1_accuracy']:.3f} versus no-invariance {methods['no_invariance']['mechanism_family_top1_accuracy']:.3f}; retained mechanisms abstain",
            "proof_class": "seeded_synthetic_plus_retained_abstention",
        },
        "RQ4": {
            "verdict": "supported_in_seeded_fixture",
            "evidence": f"deterministic {methods['sail_deterministic']['probes_to_threshold']} probes versus no-acquisition {methods['no_structural_acquisition']['probes_to_threshold']}",
            "proof_class": "seeded_sealed_synthetic_benchmark",
        },
        "RQ5": {
            "verdict": "terminal_negative_fixture_and_provider_comparison_not_evaluable",
            "evidence": agent["synthetic_fixture_comparison"]["conclusion"],
            "proof_class": "governed_agent_campaign_with_blocked_provider_transport",
        },
        "RQ6": {
            "verdict": "current_kill_switch_behavior_verified_predictive_harm_validity_not_evaluable",
            "evidence": f"current level {twin['current']['base_certificate_level']}; denied data generation and policy selection",
            "proof_class": "deterministic_capability_gate_evaluation",
        },
    }
    return [
        {
            **copy.deepcopy(question),
            **answers[question["id"]],
            "physical_claim": False,
        }
        for question in config["research_questions"]
    ]


def _proof_lanes(
    benchmark: Mapping[str, Any],
    retrospective: Mapping[str, Any],
    prospective: Mapping[str, Any],
    agent: Mapping[str, Any],
    policy: Mapping[str, Any],
    studio: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return [
        {"lane": "development", "status": "complete", "count": len(studio["episodes"]), "unit": "retained_episode", "proof_class": "retained_retrospective_diagnostic"},
        {"lane": "public", "status": "complete", "count": int(benchmark["case_count"]), "unit": "seeded_case", "proof_class": "synthetic_public_benchmark"},
        {"lane": "sealed", "status": "complete", "count": int(benchmark["case_count"]), "unit": "seeded_case", "proof_class": "synthetic_sealed_evaluator"},
        {"lane": "retrospective", "status": "terminal_negative_partial", "count": len(retrospective["history"]), "unit": "history_item", "proof_class": retrospective["proof_class"]},
        {"lane": "prospective_simulator", "status": "complete_nonpromoting", "count": int(prospective["execution_accounting"]["executed_trial_count"]), "unit": "preregistered_trial", "proof_class": prospective["proof_class"]},
        {"lane": "provider_agent", "status": "not_evaluable_transport_blocked", "count": int(agent["counts"]["provider_calls"]), "unit": "provider_call", "proof_class": agent["proof_class"]},
        {"lane": "learned_policy_simulation", "status": "act_terminal_negative_groot_compute_unavailable", "count": int(policy["current_real_lane"]["policy_comparisons"]), "unit": "real_policy_comparison", "proof_class": policy["proof_class"]},
        {"lane": "future_physical", "status": "unavailable_phase2_authority_required", "count": None, "unit": "physical_trial", "proof_class": "physical_task_absent"},
    ]


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
                    for key, value in row.items()
                }
            )


def _svg(title: str, subtitle: str, rows: Sequence[tuple[str, str, float]], *, width: int = 1200) -> str:
    height = 150 + max(1, len(rows)) * 58
    maximum = max((abs(value) for _, _, value in rows), default=1.0) or 1.0
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f8f9f6"/>',
        '<style>text{font-family:ui-monospace,SFMono-Regular,monospace;fill:#151816}.title{font-family:Arial,sans-serif;font-size:32px;font-weight:700}.sub{font-size:14px;fill:#59605b}.label{font-size:13px}.value{font-size:13px;font-weight:700}.bar{fill:#145c70}.accent{fill:#ff5a1f}</style>',
        f'<text class="title" x="42" y="52">{html.escape(title)}</text>',
        f'<text class="sub" x="42" y="82">{html.escape(subtitle)}</text>',
    ]
    for index, (label, value_text, value) in enumerate(rows):
        y = 125 + index * 58
        bar_width = 620 * abs(value) / maximum
        parts.extend(
            [
                f'<text class="label" x="42" y="{y}">{html.escape(label)}</text>',
                f'<rect class="bar" x="410" y="{y - 18}" width="{bar_width:.2f}" height="22"/>',
                f'<circle class="accent" cx="{410 + bar_width:.2f}" cy="{y - 7}" r="5"/>',
                f'<text class="value" x="1060" y="{y}">{html.escape(value_text)}</text>',
            ]
        )
    parts.append("</svg>\n")
    return "".join(parts)


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _reproduction_map(
    config: Mapping[str, Any], sources: Mapping[str, Path], output_root: Path
) -> dict[str, Any]:
    return {
        "schema_version": "sim2claw.sail_reproduction_map.v1",
        "campaign_id": config["campaign_id"],
        "regeneration_command": "uv run sim2claw sail-compile-publication --config configs/sail/publication_campaign_v1.json --output outputs/sail/publication-v1",
        "broad_verification_command": "uv run pytest",
        "automatic_ci_commands": [
            row["command"]
            for row in _json(sources["ci_tiers"], "CI tiers")["tiers"]
            if row["mode"] == "automatic"
        ],
        "sources": [
            {
                "id": name,
                "path": path.resolve().relative_to(REPO_ROOT.resolve()).as_posix(),
                "sha256": sha256_file(path),
                "tracked": not str(path).startswith(str(REPO_ROOT / "outputs")),
            }
            for name, path in sorted(sources.items())
        ],
        "generated_output_root": "outputs/sail/publication-v1",
        "sealed_data_required_for_reproduction": True,
        "sealed_data_visible_to_method": False,
        "new_physical_data_required": False,
        "provider_call_required": False,
        "physical_authority": False,
    }


def _build_outputs(
    config: Mapping[str, Any], sources: Mapping[str, Path], *, output_root: Path
) -> dict[str, Path]:
    scorecard = _json(sources["benchmark_scorecard"], "benchmark scorecard")
    sealed = _json(sources["benchmark_sealed"], "sealed benchmark")
    agent_summary = _json(sources["agent_summary"], "agent summary")
    retrospective = _json(sources["retrospective_case"], "retrospective case")
    prospective = _json(sources["prospective_experiment"], "prospective experiment")
    predictions = _json(sources["phase2_prediction_freeze"], "Phase 2 prediction freeze")
    twin = _json(sources["twin_report"], "TwinWorthiness report")
    policy = _json(sources["policy_report"], "policy report")
    policy_run_log = sources["policy_run_log"].read_text(encoding="utf-8")
    _require(
        "terminal-negative" in policy_run_log
        and "rejection with no skill package" in policy_run_log,
        "policy terminal-negative source changed",
    )
    studio = _json(sources["studio_manifest"], "Studio manifest")
    surprise = _json(sources["structural_surprise"], "structural surprise")
    loop = _json(sources["loop_closure"], "loop closure")
    operator_source = _json(sources["phase2_operator_packet"], "Phase 2 operator packet")

    ablation = _build_ablation_package(scorecard, sealed, config)
    methods = {row["method"]: row for row in ablation["methods"]}
    statistics = config["statistics"]
    retained_stats = _retained_episode_statistics(
        studio,
        seed=int(statistics["bootstrap_seed"]) + 100,
        replicates=int(statistics["bootstrap_replicates"]),
        confidence=float(statistics["confidence_level"]),
    )
    agent = _agent_comparison(agent_summary, scorecard)
    claims = _claim_ledger(config, methods, loop, agent, twin)
    proof_lanes = _proof_lanes(scorecard, retrospective, prospective, agent_summary, policy, studio)
    operator_packet = _compile_operator_packet(operator_source, predictions)
    reproduction = _reproduction_map(config, sources, output_root)

    package = {
        "schema_version": PACKAGE_SCHEMA,
        "campaign_id": config["campaign_id"],
        "frozen_at": config["frozen_at"],
        "research_questions": claims,
        "ablation_matrix": {
            "schema_version": ablation["schema_version"],
            "required_count": len(ablation["ablations"]),
            "all_required_present": ablation["all_required_ablations_present"],
        },
        "statistics": {
            "preregistration": copy.deepcopy(statistics),
            "paired_comparison_count": len(ablation["paired_statistics"]),
            "retained_channel_count": len(retained_stats),
            "retained_resampling_unit": "whole_episode",
        },
        "proof_lanes": proof_lanes,
        "paper_slots": copy.deepcopy(config["paper_slots"]),
        "current_twinworthiness": {
            "level": twin["current"]["base_certificate_level"],
            "allowed_capabilities": twin["current"]["allowed_capabilities"],
            "denied_capabilities": twin["current"]["denied_capabilities"],
        },
        "policy_status": {
            "act": "terminal_negative_synthetic_fixture_no_skill_package",
            "groot": policy["groot_challenger"]["status"],
            "current_real_generated_rows": policy["current_real_lane"]["generated_rows"],
            "current_real_policy_comparisons": policy["current_real_lane"]["policy_comparisons"],
        },
        "phase2_operator_packet": {
            "status": operator_packet["status"],
            "physical_authority": operator_packet["physical_authority"],
            "prediction_count": len(operator_packet["predictions"]),
        },
        "minimum_publishable_result": {
            "deterministic_sail_complete": True,
            "seeded_sealed_benchmark_complete": True,
            "governed_agent_comparison": "terminal_negative_provider_not_evaluable_fixture_no_gain",
            "retained_case_study_complete": True,
            "prospective_simulator_predictions_frozen": True,
            "twinworthiness_terminal_negative_or_partial": True,
            "policy_win_required": False,
        },
        "claim_boundary": "Phase 1 methods package: synthetic, retained retrospective, prospective simulator, agent, learned-policy simulation, and absent future physical evidence remain separate. No output grants promotion, transfer, hardware, or physical authority.",
        "authority": copy.deepcopy(config["authority"]),
    }

    paths = {
        "package": output_root / "publication_package.json",
        "ablation_matrix": output_root / "ablation_matrix.json",
        "retained_statistics": output_root / "retained_episode_statistics.json",
        "agent_comparison": output_root / "agent_comparison.json",
        "claim_ledger": output_root / "claim_ledger.json",
        "proof_lanes": output_root / "proof_lanes.json",
        "phase2_operator_packet": output_root / "phase2_operator_packet.json",
        "reproduction_map": output_root / "reproduction_map.json",
    }
    output_root.mkdir(parents=True, exist_ok=True)
    for name, value in (
        ("package", package),
        ("ablation_matrix", ablation),
        ("retained_statistics", {"schema_version": "sim2claw.sail_retained_publication_statistics.v1", "rows": retained_stats}),
        ("agent_comparison", agent),
        ("claim_ledger", {"schema_version": "sim2claw.sail_publication_claim_ledger.v1", "claims": claims}),
        ("proof_lanes", {"schema_version": "sim2claw.sail_publication_proof_lanes.v1", "lanes": proof_lanes}),
        ("phase2_operator_packet", operator_packet),
        ("reproduction_map", reproduction),
    ):
        atomic_write_json(paths[name], value)

    tables = {
        "research_questions": claims,
        "benchmark_methods": ablation["methods"],
        "paired_statistics": ablation["paired_statistics"],
        "ablations": ablation["ablations"],
        "retained_statistics": retained_stats,
        "agent_conditions": agent["conditions"],
        "proof_lanes": proof_lanes,
        "phase2_predictions": predictions["predictions"],
        "paper_slots": config["paper_slots"],
    }
    for name, rows in tables.items():
        path = output_root / "tables" / f"{name}.csv"
        _write_csv(path, rows)
        paths[f"table_{name}"] = path

    figures = output_root / "figures"
    figure_data = {
        "fig01_architecture_authority": (
            "ClawLoop architecture and authority boundary",
            "LLMs propose; deterministic evaluators, receipts, and TwinWorthiness own promotion.",
            [("Evidence + residual field", "READ ONLY", 1.0), ("Belief graph + SAIL", "PROPOSE", 0.82), ("Evaluator + certificate", "DECIDE", 0.68), ("Learning Factory", "GATED", 0.48), ("Physical gateway", "CLOSED", 0.18)],
        ),
        "fig02_sail_algorithm": (
            "SAIL evidence → structure → closure",
            f"{studio['belief_revision']['before']['node_count']}→{studio['belief_revision']['after']['node_count']} graph nodes; {len(studio['interventions']['rows'])} interventions.",
            [("Residual field", "11 episodes", 11), ("Belief revisions", "13 revisions", 13), ("Structure particles", "10 particles", 10), ("Interventions", "6 ranked", 6)],
        ),
        "fig03_benchmark_recovery": (
            "Seeded sealed structural recovery",
            "Top-1 mechanism-family accuracy; synthetic benchmark only.",
            [(name.replace("_", " "), f"{methods[name]['mechanism_family_top1_accuracy']:.3f}", methods[name]["mechanism_family_top1_accuracy"]) for name in ("parameter_only", "sequential_no_revisit", "no_loop_closure", "no_invariance", "sail_deterministic", "full_batch_oracle")],
        ),
        "fig04_debt_loop_closure": (
            "Compensation debt and sparse loop closure",
            "Synthetic GOLD-10; sparse closure matches full score with 2/8 recomputation.",
            [("Debt before", f"{loop['before']['compensation_debt']:.4f}", loop["before"]["compensation_debt"]), ("Debt after sparse", f"{loop['sparse']['compensation_debt']:.3g}", loop["sparse"]["compensation_debt"]), ("Sparse recomputation", "2 / 8", loop["sparse"]["recomputed_decision_count"] / 8), ("Full recomputation", "8 / 8", 1.0)],
        ),
        "fig06_twinworthiness": (
            "TwinWorthiness capability ladder",
            f"Current level {twin['current']['base_certificate_level']}; diagnostics open, downstream authority closed.",
            [("TW-REPLAY diagnostics", "OPEN", 1.0), ("TW-DATA generation", "DENIED", 0.12), ("TW-SELECTION ranking", "DENIED", 0.12), ("Physical canary", "DENIED", 0.08), ("Robot motion", "DENIED", 0.05)],
        ),
        "fig07_agent_comparison": (
            "Governed agent comparison",
            "Provider transports were blocked before model calls; fixture agent adds no recovery and doubles evaluations.",
            [("Deterministic fixture top-1", "0.750", 0.75), ("Deterministic + agent top-1", "0.750", 0.75), ("Deterministic evaluations", "16", 0.5), ("Deterministic + agent evaluations", "32", 1.0), ("Provider model calls", "0", 0.0)],
        ),
    }
    for name, (title, subtitle, rows) in figure_data.items():
        path = figures / f"{name}.svg"
        _write_text(path, _svg(title, subtitle, rows))
        paths[f"figure_{name}"] = path
    studio_heatmap = sources["studio_manifest"].parent / studio["figures"]["residual_heatmap"]["path"]
    _require(
        sha256_file(studio_heatmap) == studio["figures"]["residual_heatmap"]["sha256"],
        "Studio residual heatmap changed",
    )
    retained_figure = figures / "fig05_retained_residual_field.svg"
    retained_figure.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(studio_heatmap, retained_figure)
    paths["figure_fig05_retained_residual_field"] = retained_figure
    return paths


def verify_publication_receipt(
    receipt: Mapping[str, Any], *, output_root: Path, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(receipt))
    _require(normalized.get("schema_version") == RECEIPT_SCHEMA, "publication receipt schema changed")
    observed = normalized.pop("receipt_digest", None)
    _require(observed == canonical_digest(normalized), "publication receipt digest mismatch")
    authority = normalized.get("authority", {})
    _require(isinstance(authority, Mapping) and authority and not any(authority.values()), "publication receipt widened authority")
    config_path = repo_root / normalized["config"]["path"]
    _require(config_path.is_file() and sha256_file(config_path) == normalized["config"]["sha256"], "publication config changed")
    config = _json(config_path, "publication receipt config")
    for name, expected in normalized["source_sha256"].items():
        binding = config["source_bindings"].get(name)
        _require(isinstance(binding, Mapping) and binding.get("sha256") == expected, f"publication source binding changed: {name}")
        verify_source_binding(binding, repo_root=repo_root)
    for relative, expected in normalized["compiler_sha256"].items():
        _require(sha256_file(repo_root / relative) == expected, "publication compiler changed")
    for name, binding in normalized["outputs"].items():
        path = output_root / binding["path"]
        _require(path.is_file() and sha256_file(path) == binding["sha256"], f"publication output changed: {name}")
    return {**normalized, "receipt_digest": str(observed)}


def compile_publication(
    config_path: Path, *, output_root: Path, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    resolved = config_path if config_path.is_absolute() else repo_root / config_path
    config = _json(resolved, "SAIL publication config")
    _validate_config(config)
    sources = {
        name: verify_source_binding(binding, repo_root=repo_root)
        for name, binding in config["source_bindings"].items()
    }
    _verify_bound_receipts(sources, repo_root=repo_root)
    output_paths = _build_outputs(config, sources, output_root=output_root)
    outputs = {
        name: {
            "path": path.resolve().relative_to(output_root.resolve()).as_posix(),
            "sha256": sha256_file(path),
        }
        for name, path in sorted(output_paths.items())
    }
    code_path = "src/sim2claw/sail/publication.py"
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "campaign_id": config["campaign_id"],
        "frozen_at": config["frozen_at"],
        "config": {
            "path": resolved.resolve().relative_to(repo_root.resolve()).as_posix(),
            "sha256": sha256_file(resolved),
        },
        "compiler_sha256": {code_path: sha256_file(repo_root / code_path)},
        "source_sha256": {
            name: binding["sha256"]
            for name, binding in sorted(config["source_bindings"].items())
        },
        "outputs": outputs,
        "counts": {
            "research_question_count": 6,
            "required_ablation_count": 10,
            "paper_slot_count": 9,
            "table_count": len([name for name in outputs if name.startswith("table_")]),
            "figure_count": len([name for name in outputs if name.startswith("figure_")]),
            "source_binding_count": len(sources),
        },
        "statistics_frozen_before_compile": True,
        "whole_episode_retained_resampling": True,
        "provider_results_pooled": False,
        "physical_observations_consumed": 0,
        "resources_created": {
            "provider_sessions": 0,
            "containers": 0,
            "devices": 0,
            "brev_instances": 0,
        },
        "authority": copy.deepcopy(config["authority"]),
        "regeneration_command": "uv run sim2claw sail-compile-publication --config configs/sail/publication_campaign_v1.json --output outputs/sail/publication-v1",
    }
    receipt = {**unsigned, "receipt_digest": canonical_digest(unsigned)}
    atomic_write_json(output_root / "receipt.json", receipt)
    verify_publication_receipt(receipt, output_root=output_root, repo_root=repo_root)
    return {
        "schema_version": "sim2claw.sail_publication_compile_result.v1",
        "status": "compiled",
        "counts": receipt["counts"],
        "package_sha256": outputs["package"]["sha256"],
        "receipt_sha256": sha256_file(output_root / "receipt.json"),
        "receipt_digest": receipt["receipt_digest"],
        "output_root": str(output_root),
        "phase1_complete_candidate": True,
        "physical_authority": False,
    }


__all__ = [
    "PublicationError",
    "compile_publication",
    "verify_publication_receipt",
]

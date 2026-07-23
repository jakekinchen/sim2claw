"""Evaluator-owned scoring for the executed SAIL structural benchmark."""

from __future__ import annotations

import copy
from collections import defaultdict
from typing import Any, Mapping, Sequence

from ..learning_factory_artifacts import canonical_digest


SEALED_SCHEMA = "sim2claw.sail_executed_benchmark_sealed.v2"
SCORECARD_SCHEMA = "sim2claw.sail_executed_benchmark_scorecard.v2"
CONTROL_IDS = (
    "unchanged_control_v2",
    "incorrect_structure_control_v2",
    "oracle_structure_control_v2",
    "full_batch_refit_control_v2",
)


class ExecutedBenchmarkEvaluatorError(ValueError):
    """The evaluator contract or validated prediction bundle changed."""


def _f1(predicted: set[str], expected: set[str]) -> tuple[float, float, float]:
    true_positive = len(predicted & expected)
    precision = true_positive / max(len(predicted), 1)
    recall = true_positive / max(len(expected), 1)
    f1 = (
        2.0 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return precision, recall, f1


def _score_prediction(
    prediction: Mapping[str, Any],
    truth: Mapping[str, Any],
    *,
    thresholds: Mapping[str, Any],
) -> dict[str, Any]:
    ranked = [str(value) for value in prediction["ranked_mechanisms"]]
    expected_mechanisms = {str(value) for value in truth["hidden_mechanisms"]}
    predicted_influence = {str(value) for value in prediction["influence_set"]}
    expected_influence = {str(value) for value in truth["oracle_influence_set"]}
    precision, recall, influence_f1 = _f1(
        predicted_influence, expected_influence
    )
    abstention_expected = bool(truth["abstention_expected"])
    abstained = bool(prediction["abstain"])
    predicted_outcome = prediction["predictions"]
    residual_error = abs(
        float(predicted_outcome["heldout_residual_reduction"])
        - float(truth["heldout_residual_reduction"])
    )
    regression_error = abs(
        int(predicted_outcome["regression_count"])
        - int(truth["regression_count"])
    )
    ranked_for_topk = ranked[: int(thresholds["topk_maximum"])]
    abstention_correct = abstained == abstention_expected
    recovery_threshold_pass = (
        abstention_correct
        if abstention_expected
        else (
            bool(ranked and ranked[0] in expected_mechanisms)
            and expected_mechanisms.issubset(set(ranked_for_topk))
            and influence_f1
            >= float(thresholds["minimum_influence_f1_for_recovery"])
            and residual_error
            <= float(thresholds["maximum_residual_prediction_error"])
            and not abstained
        )
    )
    return {
        "case_id": truth["case_id"],
        "top1_correct": bool(ranked and ranked[0] in expected_mechanisms),
        "topk_complete": expected_mechanisms.issubset(set(ranked_for_topk)),
        "influence_precision": precision,
        "influence_recall": recall,
        "influence_f1": influence_f1,
        "heldout_residual_reduction_absolute_error": residual_error,
        "regression_count_absolute_error": regression_error,
        "abstention_correct": abstention_correct,
        "abstained": abstained,
        "recovery_threshold_pass": recovery_threshold_pass,
        "budget": copy.deepcopy(prediction["budget"]),
    }


def _aggregate(method_id: str, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    totals: dict[str, int] = defaultdict(int)
    for row in rows:
        for name, value in row["budget"].items():
            totals[str(name)] += int(value)
    return {
        "method_id": method_id,
        "case_count": count,
        "mechanism_family_top1_accuracy": sum(
            bool(row["top1_correct"]) for row in rows
        )
        / count,
        "mechanism_family_topk_complete_rate": sum(
            bool(row["topk_complete"]) for row in rows
        )
        / count,
        "mean_influence_precision": sum(
            float(row["influence_precision"]) for row in rows
        )
        / count,
        "mean_influence_recall": sum(float(row["influence_recall"]) for row in rows)
        / count,
        "mean_influence_f1": sum(float(row["influence_f1"]) for row in rows)
        / count,
        "heldout_residual_reduction_mae": sum(
            float(row["heldout_residual_reduction_absolute_error"]) for row in rows
        )
        / count,
        "regression_count_mae": sum(
            float(row["regression_count_absolute_error"]) for row in rows
        )
        / count,
        "abstention_accuracy": sum(
            bool(row["abstention_correct"]) for row in rows
        )
        / count,
        "abstention_count": sum(bool(row["abstained"]) for row in rows),
        "recovery_threshold_rate": sum(
            bool(row["recovery_threshold_pass"]) for row in rows
        )
        / count,
        "budget": dict(sorted(totals.items())),
    }


def _control_prediction(
    *,
    control_id: str,
    truth: Mapping[str, Any],
    candidate_mechanisms: Sequence[str],
    influence_universe: Sequence[str],
) -> dict[str, Any]:
    hidden = [str(value) for value in truth["hidden_mechanisms"]]
    oracle_influence = [str(value) for value in truth["oracle_influence_set"]]
    if control_id == "unchanged_control_v2":
        ranked: list[str] = []
        influence: list[str] = []
        residual = 0.0
        regression = 0
        abstain = True
        recomputation = 0
    elif control_id == "incorrect_structure_control_v2":
        wrong = next(
            (
                str(value)
                for value in reversed(candidate_mechanisms)
                if str(value) not in set(hidden)
            ),
            str(candidate_mechanisms[-1]),
        )
        ranked = [wrong]
        influence = [
            next(
                (
                    str(value)
                    for value in reversed(influence_universe)
                    if str(value) not in set(oracle_influence)
                ),
                str(influence_universe[-1]),
            )
        ]
        residual = 0.0
        regression = int(truth["regression_count"]) + 1
        abstain = False
        recomputation = 1
    else:
        ranked = hidden
        influence = oracle_influence
        residual = float(truth["heldout_residual_reduction"])
        regression = int(truth["regression_count"])
        abstain = bool(truth["abstention_expected"])
        recomputation = (
            len(influence_universe)
            if control_id == "full_batch_refit_control_v2"
            else len(oracle_influence)
        )
    return {
        "ranked_mechanisms": ranked,
        "influence_set": influence,
        "predictions": {
            "heldout_residual_reduction": residual,
            "regression_count": regression,
        },
        "abstain": abstain,
        "budget": {
            "probes": 0,
            "recomputation": recomputation,
            "simulator_evaluations": 0,
            "abstentions": int(abstain),
            "failures": 0,
            "provider_calls": 0,
        },
    }


def evaluate_predictions(
    *,
    sealed_config: Mapping[str, Any],
    predictions: Sequence[Mapping[str, Any]],
    public_case_index: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Score validated candidate outputs without method-name conditionals."""

    sealed = copy.deepcopy(dict(sealed_config))
    if sealed.get("schema_version") != SEALED_SCHEMA:
        raise ExecutedBenchmarkEvaluatorError("unexpected sealed evaluator schema")
    authority = sealed.get("authority")
    if not isinstance(authority, Mapping) or not authority or any(authority.values()):
        raise ExecutedBenchmarkEvaluatorError("sealed evaluator authority widened")
    controls = tuple(sealed.get("evaluator_controls", ()))
    if controls != CONTROL_IDS:
        raise ExecutedBenchmarkEvaluatorError("evaluator control inventory changed")
    truths = sealed.get("sealed_cases")
    if not isinstance(truths, list) or not truths:
        raise ExecutedBenchmarkEvaluatorError("sealed truth is empty")
    truth_by_case = {str(row["case_id"]): row for row in truths}
    if set(truth_by_case) != set(public_case_index):
        raise ExecutedBenchmarkEvaluatorError("public and sealed case identities differ")
    thresholds = sealed.get("scoring_thresholds")
    if (
        not isinstance(thresholds, Mapping)
        or set(thresholds)
        != {
            "topk_maximum",
            "minimum_influence_f1_for_recovery",
            "maximum_residual_prediction_error",
            "abstention_is_correct_only_when_preregistered",
        }
        or int(thresholds["topk_maximum"]) < 1
        or not 0.0
        <= float(thresholds["minimum_influence_f1_for_recovery"])
        <= 1.0
        or float(thresholds["maximum_residual_prediction_error"]) < 0.0
        or thresholds["abstention_is_correct_only_when_preregistered"] is not True
    ):
        raise ExecutedBenchmarkEvaluatorError(
            "sealed evaluator scoring thresholds changed"
        )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    case_scores: list[dict[str, Any]] = []
    for prediction in predictions:
        case_id = str(prediction["case_id"])
        method_id = str(prediction["method_id"])
        score = _score_prediction(
            prediction, truth_by_case[case_id], thresholds=thresholds
        )
        grouped[method_id].append(score)
        case_scores.append({"method_id": method_id, **score})
    expected_case_count = len(truth_by_case)
    if any(len(rows) != expected_case_count for rows in grouped.values()):
        raise ExecutedBenchmarkEvaluatorError(
            "candidate method did not produce exactly one output per case"
        )
    method_scores = [
        _aggregate(method_id, grouped[method_id]) for method_id in sorted(grouped)
    ]

    control_scores = []
    for control_id in CONTROL_IDS:
        rows = []
        for case_id, truth in sorted(truth_by_case.items()):
            public = public_case_index[case_id]
            prediction = _control_prediction(
                control_id=control_id,
                truth=truth,
                candidate_mechanisms=public["candidate_mechanisms"],
                influence_universe=public["influence_universe"],
            )
            rows.append(
                _score_prediction(prediction, truth, thresholds=thresholds)
            )
        control_scores.append(_aggregate(control_id, rows))

    parameter_only = next(
        row for row in method_scores if row["method_id"] == "parameter_only_v2"
    )
    comparisons = []
    for row in method_scores:
        delta = (
            float(row["mechanism_family_top1_accuracy"])
            - float(parameter_only["mechanism_family_top1_accuracy"])
        )
        comparisons.append(
            {
                "method_id": row["method_id"],
                "top1_delta_vs_parameter_only": delta,
                "result_vs_parameter_only": (
                    "gain" if delta > 0.0 else "loss" if delta < 0.0 else "tie"
                ),
            }
        )

    evaluator_state = {
        "evaluator_id": sealed["evaluator_id"],
        "thresholds": sealed["scoring_thresholds"],
        "aggregation": sealed["aggregation"],
        "sealed_truth_digest": canonical_digest(truths),
        "control_ids": list(CONTROL_IDS),
    }
    unsigned = {
        "schema_version": SCORECARD_SCHEMA,
        "benchmark_id": sealed["benchmark_id"],
        "proof_class": "synthetic_evaluator_executed_structural_benchmark",
        "case_count": expected_case_count,
        "candidate_method_count": len(method_scores),
        "evaluator_control_count": len(control_scores),
        "candidate_methods": method_scores,
        "evaluator_controls": control_scores,
        "comparisons": comparisons,
        "case_scores": case_scores,
        "evaluator_state_digest": canonical_digest(evaluator_state),
        "sealed_truth_disclosed_to_candidate_methods": False,
        "candidate_self_scores_used": False,
        "candidate_promotion_authority": False,
        "training_admitted": False,
        "physical_authority": False,
    }
    return {**unsigned, "scorecard_digest": canonical_digest(unsigned)}


__all__ = [
    "CONTROL_IDS",
    "ExecutedBenchmarkEvaluatorError",
    "SCORECARD_SCHEMA",
    "SEALED_SCHEMA",
    "evaluate_predictions",
]

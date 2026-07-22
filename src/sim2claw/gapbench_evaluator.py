"""Deterministic public and sealed scoring for seeded GapBench cases."""

from __future__ import annotations

import math
from typing import Any

from .gapbench_contracts import (
    CLAIM_BOUNDARY,
    RECEIPT_SCHEMA,
    GapBenchContractError,
    validate_candidate,
)
from .learning_factory_artifacts import canonical_digest


SCORE_WEIGHTS = {
    "localization_top1": 0.15,
    "localization_top3": 0.05,
    "heldout_residual_gain": 0.30,
    "policy_consequence_agreement": 0.15,
    "repair_non_regression": 0.10,
    "probe_efficiency": 0.05,
    "evidence_discipline": 0.10,
    "forbidden_action_safety": 0.05,
    "receipt_completeness": 0.05,
}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def predict_row(parameters: dict[str, float], row: dict[str, Any]) -> float:
    features = row.get("features")
    if not isinstance(features, dict):
        raise GapBenchContractError("evaluation row features are missing")
    return float(row.get("bias", 0.0)) + sum(
        float(parameters.get(name, 0.0)) * float(coefficient)
        for name, coefficient in features.items()
    )


def _rmse(parameters: dict[str, float], rows: list[dict[str, Any]]) -> float:
    if not rows:
        raise GapBenchContractError("evaluation rows are empty")
    return math.sqrt(sum((predict_row(parameters, row) - float(row["observed"])) ** 2 for row in rows) / len(rows))


def public_evaluate(case: dict[str, Any], candidate: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    parameters = validate_candidate(case, candidate)
    baseline = validate_candidate(case, case["baseline_candidate"])
    baseline_rmse = _rmse(baseline, rows)
    candidate_rmse = _rmse(parameters, rows)
    unsigned = {
        "schema_version": "sim2claw.gapbench_public_evaluation.v1",
        "case_id": case["case_id"],
        "proof_class": case["proof_class"],
        "baseline_rmse": baseline_rmse,
        "candidate_rmse": candidate_rmse,
        "residual_gain": _clamp((baseline_rmse - candidate_rmse) / max(baseline_rmse, 1e-12)),
        "evaluator_owner": "public_gapbench_evaluator",
        "promotion_authority": False,
    }
    return {**unsigned, "receipt_sha256": canonical_digest(unsigned)}


class SealedEvaluator:
    """Host-side evaluator whose source spec is never copied into a sample."""

    def __init__(self, sealed_spec: dict[str, Any]):
        if sealed_spec.get("schema_version") != "sim2claw.gapbench_sealed_case.v1":
            raise GapBenchContractError("unsupported sealed case schema")
        self._spec = sealed_spec
        target = sealed_spec.get("target_parameters")
        rows = sealed_spec.get("hidden_rows")
        if not isinstance(target, dict) or not isinstance(rows, list) or not rows:
            raise GapBenchContractError("sealed target or rows are missing")
        normalized_target = {str(name): float(value) for name, value in target.items()}
        for row in rows:
            if not isinstance(row, dict) or not math.isclose(
                predict_row(normalized_target, row),
                float(row.get("observed", math.nan)),
                abs_tol=1e-8,
            ):
                raise GapBenchContractError("sealed rows do not bind the target parameters")

    @property
    def case_id(self) -> str:
        return str(self._spec["case_id"])

    def probe(self, probe_id: str) -> dict[str, Any]:
        probes = self._spec.get("probe_results")
        if not isinstance(probes, dict) or probe_id not in probes:
            raise GapBenchContractError("probe is not available to sealed service")
        result = probes[probe_id]
        if not isinstance(result, dict):
            raise GapBenchContractError("sealed probe result is invalid")
        unsigned = {
            "schema_version": "sim2claw.gapbench_probe_receipt.v1",
            "case_id": self.case_id,
            "probe_id": probe_id,
            "result": result,
            "source": "host_probe_service",
            "physical_action": False,
        }
        return {**unsigned, "receipt_sha256": canonical_digest(unsigned)}

    def score(
        self,
        *,
        case: dict[str, Any],
        candidate: dict[str, Any],
        hypotheses: list[dict[str, Any]],
        prediction: dict[str, Any],
        claim_boundary: str,
        probes_used: int,
        forbidden_attempts: int,
        candidate_sha256: str,
        attempt_sha256: str,
    ) -> dict[str, Any]:
        if case["case_id"] != self.case_id:
            raise GapBenchContractError("sealed evaluator case identity mismatch")
        parameters = validate_candidate(case, candidate)
        baseline = validate_candidate(case, case["baseline_candidate"])
        rows = self._spec.get("hidden_rows")
        if not isinstance(rows, list) or not rows:
            raise GapBenchContractError("sealed evaluation rows are missing")

        family = str(self._spec["fault_family"])
        ranked = [str(row["mechanism"]) for row in hypotheses]
        baseline_rmse = _rmse(baseline, rows)
        candidate_rmse = _rmse(parameters, rows)
        residual_gain = _clamp((baseline_rmse - candidate_rmse) / max(baseline_rmse, 1e-12))

        consequence_matches = 0
        for row in rows:
            threshold = float(row.get("consequence_threshold", 0.0))
            expected = float(row["observed"]) >= threshold
            actual = predict_row(parameters, row) >= threshold
            consequence_matches += int(expected == actual)
        consequence_agreement = consequence_matches / len(rows)

        regression_rows = [row for row in rows if bool(row.get("regression_guard", False))]
        if regression_rows:
            baseline_errors = [abs(predict_row(baseline, row) - float(row["observed"])) for row in regression_rows]
            candidate_errors = [abs(predict_row(parameters, row) - float(row["observed"])) for row in regression_rows]
            non_regression = sum(after <= before + 1e-9 for before, after in zip(baseline_errors, candidate_errors, strict=True)) / len(regression_rows)
        else:
            non_regression = 1.0

        probe_budget = max(int(case["budgets"]["probes"]), 1)
        localization_top1 = float(bool(ranked) and ranked[0] == family)
        localization_top3 = float(family in ranked[:3])
        probe_efficiency = localization_top1 * (1.0 - 0.5 * probes_used / probe_budget)
        correct_prediction = prediction.get("fault_family") == family
        calibrated_uncertainty = float(prediction.get("uncertainty", 1.0)) <= 0.5 if correct_prediction else float(prediction.get("uncertainty", 0.0)) >= 0.5
        evidence_discipline = sum((claim_boundary == CLAIM_BOUNDARY, correct_prediction, calibrated_uncertainty)) / 3.0
        forbidden_safety = float(forbidden_attempts == 0)
        receipt_completeness = float(bool(candidate_sha256 and attempt_sha256 and hypotheses and prediction))

        scores = {
            "localization_top1": localization_top1,
            "localization_top3": localization_top3,
            "heldout_residual_gain": residual_gain,
            "policy_consequence_agreement": consequence_agreement,
            "repair_non_regression": non_regression,
            "probe_efficiency": _clamp(probe_efficiency),
            "evidence_discipline": evidence_discipline,
            "forbidden_action_safety": forbidden_safety,
            "receipt_completeness": receipt_completeness,
        }
        aggregate = sum(SCORE_WEIGHTS[name] * scores[name] for name in SCORE_WEIGHTS)
        unsigned = {
            "schema_version": RECEIPT_SCHEMA,
            "case_id": self.case_id,
            "proof_class": "synthetic_benchmark",
            "candidate_sha256": candidate_sha256,
            "attempt_sha256": attempt_sha256,
            "scores": scores,
            "aggregate_score": aggregate,
            "score_weights_sha256": canonical_digest(SCORE_WEIGHTS),
            "sealed_evaluator_identity": str(self._spec["evaluator_identity"]),
            "hidden_rows_evaluated": len(rows),
            "hidden_values_disclosed": False,
            "promotion_authority": False,
            "verdict_owner": "sealed_gapbench_evaluator",
        }
        return {**unsigned, "receipt_sha256": canonical_digest(unsigned)}

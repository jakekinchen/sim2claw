"""Deterministic influence-set discovery for sparse SAIL loop closure."""

from __future__ import annotations

import copy
from typing import Any, Mapping, Sequence

from ..learning_factory_artifacts import canonical_digest
from .contracts import SailContractError


INFLUENCE_SCHEMA = "sim2claw.sail_influence_set.v1"


class InfluenceError(SailContractError):
    """Influence discovery lost scope, graph, or oracle integrity."""


def discover_influence_set(
    *,
    mechanism_id: str,
    mechanism_family: str,
    graph_factors: Sequence[str],
    interventions: Sequence[Mapping[str, Any]],
    graph_edges: Sequence[Mapping[str, Any]],
    thresholds: Mapping[str, Any],
    oracle_affected_intervention_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Nominate decisions only when scope, path, residuals, and sensitivity agree."""

    ids = [str(row.get("intervention_id", "")) for row in interventions]
    if not ids or any(not value for value in ids) or len(ids) != len(set(ids)):
        raise InfluenceError("influence intervention identities are invalid")
    factor_set = {str(value) for value in graph_factors}
    if not factor_set:
        raise InfluenceError("mechanism graph factors are empty")
    expected_path = (f"mechanism:{mechanism_family}", "predicts")
    predicts_targets = {
        str(edge.get("target"))
        for edge in graph_edges
        if (str(edge.get("source")), str(edge.get("type"))) == expected_path
    }
    rows: list[dict[str, Any]] = []
    for intervention in interventions:
        intervention_id = str(intervention["intervention_id"])
        scopes = {str(value) for value in intervention.get("declared_scopes") or []}
        residuals = {str(value) for value in intervention.get("residual_node_ids") or []}
        overlap = sorted(factor_set & residuals)
        local_sensitivity = len(overlap) / len(factor_set)
        scope_match = mechanism_family in scopes
        graph_path_match = intervention_id in predicts_targets
        selected = (
            (scope_match or not bool(thresholds["require_declared_scope"]))
            and (graph_path_match or not bool(thresholds["require_predicts_path"]))
            and len(overlap) >= int(thresholds["minimum_residual_overlap"])
            and local_sensitivity >= float(thresholds["minimum_local_sensitivity"])
        )
        rows.append(
            {
                "intervention_id": intervention_id,
                "selected": selected,
                "signals": {
                    "declared_scope_match": scope_match,
                    "predicts_graph_path": graph_path_match,
                    "residual_overlap": overlap,
                    "residual_overlap_count": len(overlap),
                    "local_sensitivity": local_sensitivity,
                    "local_sensitivity_basis": "retained_intervention_residual_coverage_fraction",
                },
                "reason": (
                    "all_frozen_influence_gates_pass"
                    if selected
                    else "one_or_more_frozen_influence_gates_fail"
                ),
            }
        )
    rows.sort(key=lambda row: row["intervention_id"])
    affected = [row["intervention_id"] for row in rows if row["selected"]]
    oracle = sorted(str(value) for value in (oracle_affected_intervention_ids or []))
    metrics: dict[str, Any] | None = None
    passed: bool | None = None
    if oracle_affected_intervention_ids is not None:
        true_positive = len(set(affected) & set(oracle))
        precision = true_positive / len(affected) if affected else (1.0 if not oracle else 0.0)
        recall = true_positive / len(oracle) if oracle else 1.0
        metrics = {
            "true_positive": true_positive,
            "false_positive": len(set(affected) - set(oracle)),
            "false_negative": len(set(oracle) - set(affected)),
            "precision": precision,
            "recall": recall,
        }
        passed = (
            precision >= float(thresholds["minimum_precision"])
            and recall >= float(thresholds["minimum_recall"])
        )
    unsigned = {
        "schema_version": INFLUENCE_SCHEMA,
        "mechanism_id": mechanism_id,
        "mechanism_family": mechanism_family,
        "method": "declared_scope_then_predicts_path_then_residual_overlap_and_local_sensitivity",
        "thresholds": copy.deepcopy(dict(thresholds)),
        "candidates": rows,
        "affected_intervention_ids": affected,
        "oracle_affected_intervention_ids": oracle if oracle_affected_intervention_ids is not None else None,
        "metrics": metrics,
        "passed": passed,
        "abstained": not affected,
        "physical_cause_asserted": False,
    }
    return {**unsigned, "influence_digest": canonical_digest(unsigned)}


def run_gold_09_fixture(config: Mapping[str, Any]) -> dict[str, Any]:
    case = config["gold_09"]
    result = discover_influence_set(
        mechanism_id=str(case["mechanism_id"]),
        mechanism_family=str(case["mechanism_family"]),
        graph_factors=case["graph_factors"],
        interventions=case["interventions"],
        graph_edges=case["graph_edges"],
        thresholds=config["influence_thresholds"],
        oracle_affected_intervention_ids=case["oracle_affected_intervention_ids"],
    )
    if result["passed"] is not True:
        raise InfluenceError("GOLD-09 influence set missed frozen oracle tolerance")
    return result


__all__ = [
    "InfluenceError",
    "discover_influence_set",
    "run_gold_09_fixture",
]

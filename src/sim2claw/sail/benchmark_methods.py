"""Trusted deterministic candidate methods for the executed SAIL benchmark.

These callables receive only a frozen public execution payload.  They are
trusted in-repository code, not hostile-code plugins or a cryptographic
sandbox.  Sealed truth, scoring, controls, and promotion decisions are not
imported or accepted by this module.
"""

from __future__ import annotations

import copy
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from ..learning_factory_artifacts import canonical_digest


PREDICTION_SCHEMA = "sim2claw.sail_executed_benchmark_prediction.v2"
MethodCallable = Callable[[Mapping[str, Any]], dict[str, Any]]


def _case(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    case = payload.get("public_case")
    if not isinstance(case, Mapping):
        raise ValueError("candidate method public case is missing")
    return case


def _rank(scores: Mapping[str, float], *, limit: int = 3) -> list[str]:
    return [
        name
        for name, _value in sorted(
            ((str(name), float(value)) for name, value in scores.items()),
            key=lambda row: (-row[1], row[0]),
        )[:limit]
    ]


def _probe(case: Mapping[str, Any], probe_id: str) -> Mapping[str, Any]:
    for row in case["probe_catalog"]:
        if row["probe_id"] == probe_id:
            return row
    raise ValueError(f"candidate method requested undeclared probe: {probe_id}")


def _combined_scores(
    case: Mapping[str, Any],
    probe_ids: Sequence[str],
    *,
    residual_weight: float = 0.4,
) -> dict[str, float]:
    scores = {
        str(name): residual_weight * float(value)
        for name, value in case["residual_scores"].items()
    }
    if not probe_ids:
        return scores
    probe_weight = (1.0 - residual_weight) / len(probe_ids)
    for probe_id in probe_ids:
        evidence = _probe(case, probe_id)["evidence_by_mechanism"]
        for name in scores:
            scores[name] += probe_weight * float(evidence.get(name, 0.0))
    return scores


def _influence(case: Mapping[str, Any], mechanisms: Sequence[str]) -> list[str]:
    candidates = case["influence_candidates"]
    return sorted(
        {
            str(factor)
            for mechanism in mechanisms
            for factor in candidates.get(mechanism, [])
        }
    )


def _predictions(scores: Mapping[str, float], ranked: Sequence[str]) -> dict[str, Any]:
    if not ranked:
        return {
            "heldout_residual_reduction": 0.0,
            "regression_count": 0,
        }
    confidence = max(0.0, min(1.0, float(scores[ranked[0]])))
    return {
        "heldout_residual_reduction": confidence,
        "regression_count": int(confidence < 0.5),
    }


def _prediction(
    payload: Mapping[str, Any],
    *,
    ranked: Sequence[str],
    influence_set: Sequence[str],
    selected_probe_ids: Sequence[str],
    recomputation_count: int,
    abstain: bool = False,
    scores: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    case = _case(payload)
    mechanisms = [str(value) for value in ranked]
    probe_ids = [str(value) for value in selected_probe_ids]
    prediction_scores = (
        dict(scores) if scores is not None else _combined_scores(case, probe_ids)
    )
    unsigned = {
        "schema_version": PREDICTION_SCHEMA,
        "method_id": str(payload["method_id"]),
        "case_id": str(case["case_id"]),
        "execution_id": str(payload["execution_id"]),
        "action_sha256": str(case["action_sha256"]),
        "ranked_mechanisms": [] if abstain else mechanisms,
        "influence_set": [] if abstain else sorted({str(value) for value in influence_set}),
        "selected_probe_ids": probe_ids,
        "predictions": _predictions(
            prediction_scores, [] if abstain else mechanisms
        ),
        "abstain": bool(abstain),
        "budget": {
            "probes": len(probe_ids),
            "recomputation": int(recomputation_count),
            "simulator_evaluations": len(probe_ids),
            "abstentions": int(abstain),
            "failures": 0,
            "provider_calls": 0,
        },
        "authority": {
            "self_score": False,
            "self_promote": False,
            "evaluator_mutation": False,
            "action_mutation": False,
            "training": False,
            "physical": False,
        },
    }
    return {**unsigned, "output_digest": canonical_digest(unsigned)}


def parameter_only(payload: Mapping[str, Any]) -> dict[str, Any]:
    case = _case(payload)
    ranked = _rank(case["residual_scores"], limit=1)
    return _prediction(
        payload,
        ranked=ranked,
        influence_set=_influence(case, ranked),
        selected_probe_ids=[],
        recomputation_count=1,
    )


def sequential_no_revisit(payload: Mapping[str, Any]) -> dict[str, Any]:
    case = _case(payload)
    probe_id = str(case["probe_catalog"][0]["probe_id"])
    scores = _combined_scores(case, [probe_id])
    ranked = _rank(scores, limit=2)
    return _prediction(
        payload,
        ranked=ranked,
        influence_set=_influence(case, ranked[:1]),
        selected_probe_ids=[probe_id],
        recomputation_count=2,
    )


def deterministic_random_probe(payload: Mapping[str, Any]) -> dict[str, Any]:
    case = _case(payload)
    probes = list(case["probe_catalog"])
    index = int(canonical_digest({"case_id": case["case_id"]})[:8], 16) % len(probes)
    probe_id = str(probes[index]["probe_id"])
    scores = _combined_scores(case, [probe_id])
    ranked = _rank(scores, limit=2)
    return _prediction(
        payload,
        ranked=ranked,
        influence_set=_influence(case, ranked[:1]),
        selected_probe_ids=[probe_id],
        recomputation_count=2,
    )


def residual_magnitude(payload: Mapping[str, Any]) -> dict[str, Any]:
    case = _case(payload)
    ranked = _rank(case["residual_scores"], limit=2)
    return _prediction(
        payload,
        ranked=ranked,
        influence_set=_influence(case, ranked[:1]),
        selected_probe_ids=[],
        recomputation_count=2,
    )


def sail_without_invariance(payload: Mapping[str, Any]) -> dict[str, Any]:
    case = _case(payload)
    probes = [str(row["probe_id"]) for row in case["probe_catalog"]]
    scores = _combined_scores(case, probes)
    ranked = _rank(scores, limit=3)
    return _prediction(
        payload,
        ranked=ranked,
        influence_set=_influence(case, ranked[:2]),
        selected_probe_ids=probes,
        recomputation_count=len(case["candidate_mechanisms"]),
    )


def sail_without_loop_closure(payload: Mapping[str, Any]) -> dict[str, Any]:
    case = _case(payload)
    probe_id = _most_discriminating_probe(case)
    scores = _combined_scores(case, [probe_id])
    ranked = _rank(scores, limit=1)
    return _prediction(
        payload,
        ranked=ranked,
        influence_set=_influence(case, ranked),
        selected_probe_ids=[probe_id],
        recomputation_count=1,
        abstain=not bool(case["required_observable_available"]),
    )


def sail_without_structural_acquisition(payload: Mapping[str, Any]) -> dict[str, Any]:
    case = _case(payload)
    cheapest = min(
        case["probe_catalog"],
        key=lambda row: (float(row["cost"]), str(row["probe_id"])),
    )
    probe_id = str(cheapest["probe_id"])
    scores = _combined_scores(case, [probe_id])
    ranked = _rank(scores, limit=3)
    return _prediction(
        payload,
        ranked=ranked,
        influence_set=_influence(case, ranked[:2]),
        selected_probe_ids=[probe_id],
        recomputation_count=len(ranked),
        abstain=not bool(case["required_observable_available"]),
    )


def _most_discriminating_probe(case: Mapping[str, Any]) -> str:
    def separation(row: Mapping[str, Any]) -> tuple[float, float, str]:
        values = [float(value) for value in row["evidence_by_mechanism"].values()]
        return (
            max(values) - min(values),
            -float(row["cost"]),
            str(row["probe_id"]),
        )

    return str(max(case["probe_catalog"], key=separation)["probe_id"])


def sail_deterministic(payload: Mapping[str, Any]) -> dict[str, Any]:
    case = _case(payload)
    if not bool(case["required_observable_available"]):
        return _prediction(
            payload,
            ranked=[],
            influence_set=[],
            selected_probe_ids=[],
            recomputation_count=0,
            abstain=True,
        )
    probe_id = _most_discriminating_probe(case)
    scores = _combined_scores(case, [probe_id], residual_weight=0.25)
    ranked = _rank(scores, limit=3)
    return _prediction(
        payload,
        ranked=ranked,
        influence_set=_influence(case, ranked[:2]),
        selected_probe_ids=[probe_id],
        recomputation_count=max(1, len(_influence(case, ranked[:2]))),
        scores=scores,
    )


_METHOD_REGISTRY: Mapping[str, MethodCallable] = MappingProxyType(
    {
        "parameter_only_v2": parameter_only,
        "sequential_no_revisit_v2": sequential_no_revisit,
        "deterministic_random_probe_v2": deterministic_random_probe,
        "residual_magnitude_v2": residual_magnitude,
        "sail_without_invariance_v2": sail_without_invariance,
        "sail_without_loop_closure_v2": sail_without_loop_closure,
        "sail_without_structural_acquisition_v2": sail_without_structural_acquisition,
        "sail_deterministic_v2": sail_deterministic,
    }
)


def registered_methods() -> Mapping[str, MethodCallable]:
    """Return the immutable trusted method registry."""

    return _METHOD_REGISTRY


def execute_registered_method(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Execute one exact registered callable from a public-only payload."""

    method_id = str(payload.get("method_id", ""))
    method = _METHOD_REGISTRY.get(method_id)
    if method is None:
        raise ValueError("candidate method is not registered")
    before = copy.deepcopy(dict(payload))
    output = method(payload)
    if dict(payload) != before:
        raise ValueError("candidate method mutated its public input")
    return output


__all__ = [
    "PREDICTION_SCHEMA",
    "execute_registered_method",
    "registered_methods",
]

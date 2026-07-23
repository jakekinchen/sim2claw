"""Pure decision surfaces composed by the SAIL live operator."""

from __future__ import annotations

import copy
import glob
from itertools import combinations
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from ..learning_factory_artifacts import canonical_digest, sha256_file
from .acquisition import AcquisitionError, _weighted_score
from .belief_graph import BeliefGraphError, _canonical_graph, _edge, _node, validate_graph
from .importers import load_json_object
from .invariance import evaluate_invariance
from .loop_closure import LoopClosureError
from .posterior import PosteriorError, rank_structure_particles
from .live_types import LiveCampaignContract, LiveOperatorError


def validate_live_residual_evidence(
    rows: Sequence[Mapping[str, Any]], *, declared_source_bindings: Sequence[str]
) -> dict[str, Any]:
    residuals = [copy.deepcopy(dict(row)) for row in rows]
    ids = [str(row.get("residual_id", "")) for row in residuals]
    if not ids or any(not value for value in ids) or len(ids) != len(set(ids)):
        raise LiveOperatorError("live residual identities are invalid")
    binding_ids = {str(value) for value in declared_source_bindings}
    for row in residuals:
        if str(row.get("source_binding", "")) not in binding_ids:
            raise LiveOperatorError("live residual source binding is undeclared")
        available = row.get("available") is True
        value = row.get("value")
        if available:
            if value is None or not np.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
                raise LiveOperatorError("available live residual is not normalized")
            row["value"] = float(value)
        elif value is not None:
            raise LiveOperatorError("unavailable live residual has a value")
        if not str(row.get("label", "")) or not str(row.get("provenance", "")):
            raise LiveOperatorError("live residual lost label or provenance")
    residuals.sort(key=lambda row: row["residual_id"])
    unsigned = {
        "schema_version": "sim2claw.sail_live_residual_evidence.v1",
        "residuals": residuals,
        "source_binding_ids": sorted(binding_ids),
        "missing_values_imputed": False,
        "physical_cause_identified": False,
    }
    return {**unsigned, "residual_digest": canonical_digest(unsigned)}


def update_discrete_structure_posterior(
    prior: Mapping[str, float],
    *,
    likelihoods: Mapping[str, float] | None = None,
    observation_id: str | None = None,
) -> dict[str, Any]:
    before = {str(name): float(value) for name, value in prior.items()}
    if len(before) < 2 or any(not name for name in before):
        raise PosteriorError("discrete posterior needs at least two hypotheses")
    if any(not np.isfinite(value) or value <= 0.0 for value in before.values()) or not np.isclose(
        sum(before.values()), 1.0
    ):
        raise PosteriorError("discrete posterior prior is invalid")

    def entropy(values: Mapping[str, float]) -> float:
        return float(-sum(value * np.log2(value) for value in values.values() if value > 0.0))

    entropy_before = entropy(before)
    if likelihoods is None:
        after = copy.deepcopy(before)
        status = "not_updated_no_observation"
        observed_gain = None
    else:
        normalized_likelihoods = {
            str(name): float(value) for name, value in likelihoods.items()
        }
        if set(normalized_likelihoods) != set(before):
            raise PosteriorError("posterior hypothesis set changed after result")
        if any(
            not np.isfinite(value) or value < 0.0
            for value in normalized_likelihoods.values()
        ):
            raise PosteriorError("posterior likelihood is invalid")
        unnormalized = {
            name: before[name] * normalized_likelihoods[name] for name in before
        }
        normalizer = sum(unnormalized.values())
        if normalizer <= 0.0:
            raise PosteriorError("posterior likelihoods have zero support")
        after = {name: value / normalizer for name, value in unnormalized.items()}
        status = "updated_from_preregistered_result"
        observed_gain = entropy_before - entropy(after)
    entropy_after = entropy(after)
    unsigned = {
        "schema_version": "sim2claw.sail_discrete_structure_posterior.v1",
        "hypothesis_ids": sorted(before),
        "before": dict(sorted(before.items())),
        "after": dict(sorted(after.items())),
        "entropy_before_bits": entropy_before,
        "entropy_after_bits": entropy_after,
        "entropy_delta_bits": entropy_after - entropy_before,
        "observed_information_gain_bits": observed_gain,
        "observation_id": observation_id,
        "status": status,
        "hypothesis_set_expanded": False,
        "physical_mechanism_identified": False,
        "conditional_particle_ranking": rank_structure_particles([]),
    }
    return {**unsigned, "posterior_digest": canonical_digest(unsigned)}


def rank_live_acquisition(
    *,
    hypotheses: Mapping[str, float],
    candidates: Sequence[Mapping[str, Any]],
    weights: Mapping[str, float],
) -> dict[str, Any]:
    priors = {str(name): float(value) for name, value in hypotheses.items()}
    if len(priors) < 2 or any(not name for name in priors):
        raise AcquisitionError("live acquisition needs at least two hypotheses")
    if any(not np.isfinite(value) or value <= 0.0 for value in priors.values()) or not np.isclose(
        sum(priors.values()), 1.0
    ):
        raise AcquisitionError("live acquisition priors are invalid")
    required_components = {
        "predicted_signature_separation",
        "compensation_debt_reduction",
        "gate_relevance",
        "cost",
        "risk",
    }
    if set(weights) != required_components or any(not np.isfinite(float(value)) for value in weights.values()):
        raise AcquisitionError("live acquisition weight set changed")
    ids = [str(row.get("intervention_id", "")) for row in candidates]
    if not ids or any(not value for value in ids) or len(ids) != len(set(ids)):
        raise AcquisitionError("live acquisition intervention identities are invalid")
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        signatures = candidate.get("predicted_signatures") or {}
        if set(signatures) != set(priors):
            raise AcquisitionError("live acquisition predicted hypothesis set changed")
        flattened: dict[str, dict[str, float]] = {}
        observable_set: set[str] | None = None
        for hypothesis_id in sorted(priors):
            values = {
                str(observable_id): float(payload["normalized_response"])
                for observable_id, payload in signatures[hypothesis_id].items()
            }
            if not values or any(
                not np.isfinite(value) or not 0.0 <= value <= 1.0
                for value in values.values()
            ):
                raise AcquisitionError("live acquisition signature is invalid")
            if observable_set is None:
                observable_set = set(values)
            elif set(values) != observable_set:
                raise AcquisitionError("live acquisition signatures are not comparable")
            flattened[hypothesis_id] = values
        pair_rows: list[dict[str, Any]] = []
        weighted_distance = 0.0
        pair_weight_total = 0.0
        for left, right in combinations(sorted(priors), 2):
            observables = sorted(flattened[left])
            distance = float(
                np.mean(
                    [
                        abs(flattened[left][name] - flattened[right][name])
                        for name in observables
                    ]
                )
            )
            pair_weight = priors[left] * priors[right]
            weighted_distance += pair_weight * distance
            pair_weight_total += pair_weight
            pair_rows.append(
                {"left": left, "right": right, "distance": distance, "weight": pair_weight}
            )
        predicted_separation = weighted_distance / pair_weight_total
        components = {
            "predicted_signature_separation": predicted_separation,
            "compensation_debt_reduction": float(candidate["compensation_debt_reduction"]),
            "gate_relevance": float(candidate["gate_relevance"]),
            "cost": float(candidate["cost"]),
            "risk": float(candidate["risk"]),
        }
        if any(not np.isfinite(value) or not 0.0 <= value <= 1.0 for value in components.values()):
            raise AcquisitionError("live acquisition component is outside [0, 1]")
        available = candidate.get("availability") == "available_simulator"
        rows.append(
            {
                "intervention_id": str(candidate["intervention_id"]),
                "kind": str(candidate["kind"]),
                "availability": str(candidate["availability"]),
                "available_for_execution": available,
                "predicted_signature_separation": predicted_separation,
                "pairwise_signature_distances": pair_rows,
                "components": components,
                "score": _weighted_score(components, weights),
                "predicted_signatures": copy.deepcopy(signatures),
                "observed_information_gain": None,
                "execution_status": "ranked_preregistered_not_executed",
            }
        )
    ranking = sorted(rows, key=lambda row: (-row["score"], row["intervention_id"]))
    executable = [row for row in ranking if row["available_for_execution"]]
    for index, row in enumerate(ranking, start=1):
        row["rank"] = index
    unsigned = {
        "schema_version": "sim2claw.sail_live_acquisition_ranking.v1",
        "hypothesis_priors": priors,
        "rows": ranking,
        "selected_intervention": ranking[0]["intervention_id"],
        "selected_available_for_execution": ranking[0]["available_for_execution"],
        "best_available_simulator_intervention": (
            executable[0]["intervention_id"] if executable else None
        ),
        "predictions_opened_before_ranking": False,
        "scores_collapsed": False,
    }
    return {**unsigned, "ranking_digest": canonical_digest(unsigned)}


def apply_live_sparse_closure(
    *,
    before_factors: Sequence[Mapping[str, Any]],
    affected_factor_ids: Sequence[str],
    updates: Mapping[str, float] | None,
    observation_opened: bool,
    action_identity: Mapping[str, Any],
    evidence_identity: Mapping[str, Any],
) -> dict[str, Any]:
    raw_before = [copy.deepcopy(dict(row)) for row in before_factors]
    ids = [str(row.get("factor_id", "")) for row in raw_before]
    if not ids or any(not value for value in ids) or len(ids) != len(set(ids)):
        raise LoopClosureError("live closure factor identities are invalid")
    affected = {str(value) for value in affected_factor_ids}
    if not affected.issubset(set(ids)):
        raise LoopClosureError("live closure affected factor is undeclared")
    normalized_updates = {str(name): float(value) for name, value in (updates or {}).items()}
    if not observation_opened and normalized_updates:
        raise LoopClosureError("live closure cannot update without an observation")
    if not set(normalized_updates).issubset(affected):
        raise LoopClosureError("live closure attempted to mutate an unaffected factor")
    if any(not np.isfinite(value) for value in normalized_updates.values()):
        raise LoopClosureError("live closure update is invalid")

    def sealed(row: Mapping[str, Any]) -> dict[str, Any]:
        unsigned = copy.deepcopy(dict(row))
        unsigned.pop("factor_digest", None)
        return {**unsigned, "factor_digest": canonical_digest(unsigned)}

    before = {str(row["factor_id"]): sealed(row) for row in raw_before}
    after = copy.deepcopy(before)
    for factor_id, value in normalized_updates.items():
        row = copy.deepcopy(after[factor_id])
        row.pop("factor_digest", None)
        row["value"] = value
        row["status"] = "sparse_refit_from_preregistered_result"
        after[factor_id] = sealed(row)
    unaffected = sorted(set(ids) - affected)
    unchanged = all(
        before[factor_id]["factor_digest"] == after[factor_id]["factor_digest"]
        for factor_id in unaffected
    )
    if not unchanged:
        raise LoopClosureError("live closure changed an unaffected factor")
    unsigned = {
        "schema_version": "sim2claw.sail_live_sparse_loop_closure.v1",
        "status": "sparse_refit_applied" if observation_opened else "no_refit_abstained_before_observation",
        "before": dict(sorted(before.items())),
        "after": dict(sorted(after.items())),
        "affected_factor_ids": sorted(affected),
        "updated_factor_ids": sorted(normalized_updates),
        "unaffected_factor_ids": unaffected,
        "unaffected_factor_digests_unchanged": unchanged,
        "action_identity": copy.deepcopy(dict(action_identity)),
        "frozen_evidence_identity": copy.deepcopy(dict(evidence_identity)),
        "action_bytes_unchanged": True,
        "frozen_evidence_unchanged": True,
        "historical_results_mutated": False,
        "physical_mechanism_identified": False,
    }
    return {**unsigned, "closure_digest": canonical_digest(unsigned)}


def build_live_belief_graph(
    *,
    campaign_id: str,
    generated_at: str,
    subject: Mapping[str, Any],
    residuals: Sequence[Mapping[str, Any]],
    mechanisms: Sequence[Mapping[str, Any]],
    interventions: Sequence[Mapping[str, Any]],
    posterior: Mapping[str, float],
    selected_intervention_id: str | None,
    selected_intervention_executed: bool,
    verdict: str,
    proof_class: str,
    evaluator_identity: str,
    source: Mapping[str, Any],
    authority: Mapping[str, Any],
) -> dict[str, Any]:
    workcell_id = str(subject.get("workcell_id", ""))
    session_id = str(subject.get("session_id", ""))
    context_id = str(subject.get("context_id", ""))
    if any(not value for value in (campaign_id, workcell_id, session_id, context_id)):
        raise BeliefGraphError("live belief subject identity is invalid")
    mechanism_ids = [str(row.get("mechanism_id", "")) for row in mechanisms]
    families = [str(row.get("family", "")) for row in mechanisms]
    if (
        any(not value for value in mechanism_ids + families)
        or len(mechanism_ids) != len(set(mechanism_ids))
        or len(families) != len(set(families))
    ):
        raise BeliefGraphError("live belief mechanism identities are invalid")
    intervention_ids = [str(row.get("intervention_id", "")) for row in interventions]
    if (
        any(not value for value in intervention_ids)
        or len(intervention_ids) != len(set(intervention_ids))
    ):
        raise BeliefGraphError("live belief intervention identities are invalid")
    if selected_intervention_id is not None and selected_intervention_id not in intervention_ids:
        raise BeliefGraphError("live belief selected intervention is undeclared")
    evidence_id = f"evidence:{campaign_id}"
    posterior_id = f"posterior:{campaign_id}"
    verdict_id = f"verdict:{campaign_id}"
    dataset_id = f"dataset:{campaign_id}"
    nodes = [
        _node(workcell_id, "workcell", str(subject.get("label", workcell_id)), "retained", proof_class, source),
        _node(session_id, "session", session_id, "retained", proof_class, source),
        _node(context_id, "context", context_id, "action_frozen", proof_class, source),
        _node(dataset_id, "dataset", "retained evidence", "unadmitted", proof_class, source, data={"training_admitted": False}),
        _node(evidence_id, "evidence", "live residual evidence", "compiled", proof_class, source),
        _node(f"simulator:{campaign_id}", "simulator_version", "candidate simulator", "not_promoted", proof_class, source),
        _node(posterior_id, "parameter_posterior", "structure posterior", "retained", proof_class, source, data={"probabilities": dict(sorted((str(key), float(value)) for key, value in posterior.items()))}),
        _node(f"certificate:{campaign_id}", "twin_worthiness_certificate", "closed certificate", "unissued_closed", proof_class, source, data={"training_admitted": False}),
        _node(f"checkpoint:{campaign_id}", "checkpoint", "campaign checkpoint", "absent", proof_class, source),
        _node(f"policy:{campaign_id}", "policy", "campaign policy", "not_admitted", proof_class, source),
        _node(verdict_id, "evaluator_verdict", "terminal live-operator verdict", verdict, proof_class, source, evaluator_identity=evaluator_identity, data={"negative": verdict != "evaluator_pass", "promoted": False}),
    ]
    edges = [
        _edge(dataset_id, "observed-by", session_id),
        _edge(session_id, "observed-by", workcell_id),
        _edge(evidence_id, "generated-from", dataset_id),
        _edge(evidence_id, "observed-by", context_id),
        _edge(posterior_id, "generated-from", evidence_id),
        _edge(f"simulator:{campaign_id}", "generated-from", context_id, metadata={"promotion": False}),
    ]
    residual_ids: set[str] = set()
    for residual in residuals:
        residual_id = str(residual.get("residual_id", ""))
        if not residual_id or residual_id in residual_ids:
            raise BeliefGraphError("live belief residual identities are invalid")
        residual_ids.add(residual_id)
        nodes.append(
            _node(
                residual_id,
                "residual_channel",
                str(residual.get("label", residual_id)),
                "available" if residual.get("available") is True else "unavailable",
                proof_class,
                source,
                data={"value": residual.get("value"), "provenance": residual.get("provenance")},
            )
        )
        edges.append(_edge(residual_id, "generated-from", evidence_id))
    for mechanism in mechanisms:
        mechanism_node_id = f"mechanism:{mechanism['family']}"
        nodes.append(
            _node(
                mechanism_node_id,
                "mechanism",
                str(mechanism["mechanism_id"]),
                "competing_hypothesis",
                proof_class,
                source,
                data={"mechanism_id": mechanism["mechanism_id"], "physical_parameter_identified": False},
            )
        )
        for residual_id in mechanism.get("graph_factors") or []:
            if str(residual_id) in residual_ids:
                edges.append(_edge(mechanism_node_id, "fitted-on", str(residual_id), metadata={"diagnostic_only": True}))
        for intervention_id in mechanism.get("candidate_interventions") or []:
            if str(intervention_id) not in intervention_ids:
                raise BeliefGraphError("mechanism predicts an undeclared intervention")
            edges.append(_edge(mechanism_node_id, "predicts", str(intervention_id)))
    for intervention in interventions:
        intervention_id = str(intervention["intervention_id"])
        nodes.append(
            _node(
                intervention_id,
                "intervention",
                intervention_id,
                (
                    "selected_independently_evaluated"
                    if intervention_id == selected_intervention_id
                    and selected_intervention_executed
                    else "selected_unexecuted"
                    if intervention_id == selected_intervention_id
                    else "ranked_unexecuted"
                ),
                proof_class,
                source,
                data={"kind": intervention["kind"], "availability": intervention["availability"]},
            )
        )
        for residual_id in intervention.get("residual_node_ids") or []:
            if str(residual_id) not in residual_ids:
                raise BeliefGraphError("intervention references an undeclared residual")
            edges.append(_edge(str(residual_id), "affected-by", intervention_id, metadata={"basis": "preregistered_signature"}))
        if intervention_id == selected_intervention_id:
            edges.append(
                _edge(
                    intervention_id,
                    "evaluated-on",
                    verdict_id,
                    metadata={"independent_result_admitted": selected_intervention_executed},
                )
            )
    graph = _canonical_graph(
        campaign_id=campaign_id,
        generated_at=generated_at,
        nodes=nodes,
        edges=edges,
        source_identities=[{"id": "live-source", **copy.deepcopy(dict(source))}],
        authority=authority,
    )
    return validate_graph(graph)


def build_manual_ablation(contract: LiveCampaignContract) -> dict[str, Any]:
    config = contract.payload["ablation"]
    receipt_paths = [Path(value) for value in sorted(glob.glob(str(config["manual_receipt_glob"])))]
    rows: list[dict[str, Any]] = []
    campaign_ids: set[str] = set()
    for path in receipt_paths:
        receipt = load_json_object(path, label="manual campaign receipt")
        campaign_id = str(receipt.get("campaign_id", ""))
        if not campaign_id or campaign_id in campaign_ids:
            raise LiveOperatorError("manual ablation campaign identity is invalid")
        campaign_ids.add(campaign_id)
        if (
            receipt.get("action_array_sha256") != contract.action_sha256
            or receipt.get("all_actions_byte_identical") is not True
        ):
            raise LiveOperatorError("manual ablation contains action drift")
        rows.append(
            {
                "campaign_id": campaign_id,
                "candidate_count": int(receipt.get("candidate_count", -1)),
                "anchor_pass_count": int(receipt.get("anchor_pass_count", -1)),
                "receipt_path": str(path),
                "receipt_sha256": sha256_file(path),
            }
        )
    completed = len(rows)
    evaluations = sum(row["candidate_count"] for row in rows)
    passes = sum(row["anchor_pass_count"] for row in rows)
    if (
        completed != int(config["expected_completed_campaigns"])
        or evaluations != int(config["expected_candidate_replays"])
        or passes != int(config["expected_anchor_passes"])
    ):
        raise LiveOperatorError("manual ablation count does not match the frozen snapshot")
    incomplete_paths = [
        Path(value) for value in sorted(glob.glob(str(config["incomplete_artifact_glob"])))
    ]
    unsigned = {
        "completed_campaigns": completed,
        "simulator_evaluations": evaluations,
        "anchor_passes": passes,
        "hypotheses_rejected_or_narrowed": list(
            config["manual_hypotheses_rejected_or_narrowed"]
        ),
        "hypotheses_retained": list(config["manual_hypotheses_retained"]),
        "observed_information_gain": None,
        "information_gain_status": "not_formally_scored_by_manual_sequence",
        "task_consequences": {
            "accepted_anchor_passes": passes,
            "simulator_promotion": False,
        },
        "abstention_quality": "no_global_abstention_incomplete_family_interrupted",
        "campaigns": rows,
        "incomplete_work_in_progress": {
            "artifact_count": len(incomplete_paths),
            "artifacts": [
                {"path": str(path), "sha256": sha256_file(path)} for path in incomplete_paths
            ],
            "included_in_completed_counts": False,
        },
    }
    return {**unsigned, "manual_digest": canonical_digest(unsigned)}


def evaluate_live_invariance(contract: LiveCampaignContract) -> dict[str, Any]:
    config = contract.payload["invariance"]
    covariate = str(config["context_covariate"])
    episodes = []
    missing_vector_episode_ids: list[str] = []
    for row in config["episode_contexts"]:
        if any(row.get(name) is None for name in ("feature", "observation", "actions")):
            missing_vector_episode_ids.append(str(row["episode_id"]))
            continue
        episodes.append(
            {
                "episode_id": str(row["episode_id"]),
                "context": {covariate: str(row["level"])},
                "feature": row["feature"],
                "observation": row["observation"],
                "actions": row["actions"],
            }
        )
    if missing_vector_episode_ids:
        unsigned = {
            "schema_version": "sim2claw.sail_invariance_result.v1",
            "mechanism_id": str(config["mechanism_id"]),
            "invariant_parameter": str(config["invariant_parameter"]),
            "context_covariate": covariate,
            "proof_class": str(contract.payload["proof_boundary"]["proof_class"]),
            "verdict": "not_evaluable",
            "reason": "missing_source_bound_feature_observation_or_action_vectors",
            "missing_vector_episode_ids": sorted(missing_vector_episode_ids),
            "context_counts": {},
            "whole_episode_grouping": True,
            "episode_ids": sorted(str(row["episode_id"]) for row in config["episode_contexts"]),
            "parameter_range": None,
            "residual_signature_consistency": None,
            "missing_vectors_imputed": False,
            "physical_mechanism_identified": False,
        }
        return {**unsigned, "invariance_digest": canonical_digest(unsigned)}
    return evaluate_invariance(
        mechanism_id=str(config["mechanism_id"]),
        invariant_parameter=str(config["invariant_parameter"]),
        context_covariate=covariate,
        episodes=episodes,
        thresholds=config["thresholds"],
        proof_class=str(contract.payload["proof_boundary"]["proof_class"]),
    )

__all__ = [
    "apply_live_sparse_closure",
    "build_live_belief_graph",
    "build_manual_ablation",
    "evaluate_live_invariance",
    "rank_live_acquisition",
    "update_discrete_structure_posterior",
    "validate_live_residual_evidence",
]


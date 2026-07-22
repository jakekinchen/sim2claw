"""Generic, budgeted SAIL live operator with evaluator-owned terminal verdicts."""

from __future__ import annotations

import copy
import glob
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from ..learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .acquisition import AcquisitionError, _weighted_score
from .belief_graph import (
    BeliefGraphError,
    _canonical_graph,
    _edge,
    _node,
    validate_graph,
)
from .contracts import REPO_ROOT, SailContractError, verify_source_binding
from .importers import load_json_object
from .influence import discover_influence_set
from .invariance import evaluate_invariance
from .loop_closure import LoopClosureError
from .mechanisms import MechanismPlugin, build_mechanism_plugin, json_pointer
from .posterior import PosteriorError, rank_structure_particles
from .structural_surprise import evaluate_surprise


CONFIG_SCHEMA = "sim2claw.sail_live_campaign.v1"
RESULT_SCHEMA = "sim2claw.sail_live_intervention_result.v1"
RECEIPT_SCHEMA = "sim2claw.sail_live_operator_receipt.v1"


class LiveOperatorError(SailContractError):
    """A live campaign escaped its frozen evidence, budget, or authority."""


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
        if observed_gain < -1e-12:
            raise PosteriorError("posterior update increased entropy unexpectedly")
    unsigned = {
        "schema_version": "sim2claw.sail_discrete_structure_posterior.v1",
        "hypothesis_ids": sorted(before),
        "before": dict(sorted(before.items())),
        "after": dict(sorted(after.items())),
        "entropy_before_bits": entropy_before,
        "entropy_after_bits": entropy(after),
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
        "predicted_information_gain",
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
        predicted_gain = weighted_distance / pair_weight_total
        components = {
            "predicted_information_gain": predicted_gain,
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
                "predicted_information_gain": predicted_gain,
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
                "selected_unexecuted" if intervention_id == selected_intervention_id else "ranked_unexecuted",
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
            edges.append(_edge(intervention_id, "evaluated-on", verdict_id, metadata={"executed": False}))
    graph = _canonical_graph(
        campaign_id=campaign_id,
        generated_at=generated_at,
        nodes=nodes,
        edges=edges,
        source_identities=[{"id": "live-source", **copy.deepcopy(dict(source))}],
        authority=authority,
    )
    return validate_graph(graph)


@dataclass(frozen=True)
class LiveMechanism:
    mechanism_id: str
    family: str
    prior_probability: float
    plugin: MechanismPlugin


@dataclass(frozen=True)
class LiveIntervention:
    intervention_id: str
    kind: str
    availability: str
    maximum_trials: int
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class LiveCampaignContract:
    path: Path
    payload: Mapping[str, Any]
    source_paths: Mapping[str, Path]
    mechanisms: tuple[LiveMechanism, ...]
    interventions: tuple[LiveIntervention, ...]
    action_sha256: str
    evaluator_digest: str
    intervention_set_digest: str
    config_digest: str
    residual_artifact: Mapping[str, Any]

    @property
    def campaign_id(self) -> str:
        return str(self.payload["campaign_id"])

    @property
    def budget(self) -> Mapping[str, Any]:
        return self.payload["budget"]

    @property
    def hypothesis_priors(self) -> dict[str, float]:
        return {
            row.mechanism_id: row.prior_probability for row in self.mechanisms
        }


def _load_pointer_source(
    source_path: Path, pointer: str, *, label: str
) -> Any:
    payload = load_json_object(source_path, label=label)
    try:
        return json_pointer(payload, pointer)
    except SailContractError as error:
        raise LiveOperatorError(f"{label} pointer is invalid") from error


def _all_false(mapping: Mapping[str, Any], *, label: str) -> None:
    if not mapping or any(value is not False for value in mapping.values()):
        raise LiveOperatorError(f"{label} widened authority")


def _validate_budget(payload: Mapping[str, Any]) -> None:
    required = {
        "maximum_interventions",
        "maximum_anchor_replays",
        "used_interventions",
        "used_anchor_replays",
    }
    if set(payload) != required:
        raise LiveOperatorError("live operator budget field set changed")
    values = {name: int(payload[name]) for name in required}
    if (
        values["maximum_interventions"] <= 0
        or values["maximum_anchor_replays"] < 0
        or values["used_interventions"] < 0
        or values["used_anchor_replays"] < 0
        or values["used_interventions"] > values["maximum_interventions"]
        or values["used_anchor_replays"] > values["maximum_anchor_replays"]
    ):
        raise LiveOperatorError("live operator budget is invalid")


def load_live_campaign_contract(
    path: Path, *, repo_root: Path = REPO_ROOT
) -> LiveCampaignContract:
    """Load a typed campaign without enumerating campaign or task IDs."""

    resolved = path.resolve() if path.is_absolute() else (repo_root / path).resolve()
    config = load_json_object(resolved, label="SAIL live campaign")
    if config.get("schema_version") != CONFIG_SCHEMA:
        raise LiveOperatorError("unexpected SAIL live campaign schema")
    if not str(config.get("campaign_id", "")) or not str(config.get("created_at", "")):
        raise LiveOperatorError("live campaign identity is invalid")
    _all_false(config.get("authority") or {}, label="live campaign")
    proof = config.get("proof_boundary") or {}
    if not str(proof.get("proof_class", "")):
        raise LiveOperatorError("live campaign proof class is missing")
    _all_false(
        {key: value for key, value in proof.items() if key != "proof_class"},
        label="live campaign proof boundary",
    )

    bindings = config.get("source_bindings") or {}
    if not bindings:
        raise LiveOperatorError("live campaign has no source bindings")
    source_paths: dict[str, Path] = {}
    try:
        for name, binding in bindings.items():
            source_paths[str(name)] = verify_source_binding(binding, repo_root=repo_root)
    except SailContractError as error:
        raise LiveOperatorError(f"source binding verification failed: {error}") from error

    action = config.get("action_identity") or {}
    action_binding = str(action.get("source_binding", ""))
    if action_binding not in source_paths:
        raise LiveOperatorError("action identity source binding is undeclared")
    observed_action_sha = str(
        _load_pointer_source(
            source_paths[action_binding],
            str(action.get("sha256_pointer", "")),
            label="action identity",
        )
    )
    byte_identical = _load_pointer_source(
        source_paths[action_binding],
        str(action.get("byte_identical_pointer", "")),
        label="action identity",
    )
    expected_action_sha = str(action.get("sha256", ""))
    if (
        len(expected_action_sha) != 64
        or observed_action_sha != expected_action_sha
        or byte_identical is not True
    ):
        raise LiveOperatorError("action identity changed or is not byte-identical")

    evaluator = config.get("evaluator") or {}
    evaluator_sources = [str(value) for value in evaluator.get("source_bindings") or []]
    if (
        not str(evaluator.get("evaluator_id", ""))
        or not str(evaluator.get("owner", ""))
        or not evaluator_sources
        or any(value not in source_paths for value in evaluator_sources)
    ):
        raise LiveOperatorError("independent evaluator identity is invalid")
    evaluator_unsigned = {
        "evaluator_id": evaluator["evaluator_id"],
        "owner": evaluator["owner"],
        "release_index": evaluator.get("release_index"),
        "source_sha256": {
            name: bindings[name]["sha256"] for name in sorted(evaluator_sources)
        },
    }
    evaluator_digest = canonical_digest(evaluator_unsigned)
    _validate_budget(config.get("budget") or {})

    residual_artifact = validate_live_residual_evidence(
        config.get("residual_evidence") or [],
        declared_source_bindings=list(bindings),
    )
    residual_ids = {
        str(row["residual_id"]) for row in residual_artifact["residuals"]
    }
    observables = config.get("observables") or []
    observable_ids = [str(row.get("observable_id", "")) for row in observables]
    if (
        not observable_ids
        or any(not value for value in observable_ids)
        or len(observable_ids) != len(set(observable_ids))
        or any(
            not str(row.get("unit", "")) or not isinstance(row.get("available"), bool)
            for row in observables
        )
    ):
        raise LiveOperatorError("live observable registry is invalid")

    mechanism_rows = config.get("mechanisms") or []
    mechanisms: list[LiveMechanism] = []
    mechanism_ids: list[str] = []
    families: list[str] = []
    for row in mechanism_rows:
        try:
            plugin = build_mechanism_plugin(row)
        except SailContractError as error:
            raise LiveOperatorError(f"live mechanism contract is invalid: {error}") from error
        prior = float(row.get("prior_probability", -1.0))
        if not np.isfinite(prior) or prior <= 0.0:
            raise LiveOperatorError("live mechanism prior is invalid")
        if not set(plugin.contract["required_observables"]).issubset(observable_ids):
            raise LiveOperatorError("mechanism requires an undeclared observable")
        if not set(plugin.contract["graph_factors"]).issubset(residual_ids):
            raise LiveOperatorError("mechanism references an undeclared residual factor")
        mechanisms.append(
            LiveMechanism(
                mechanism_id=plugin.mechanism_id,
                family=plugin.family,
                prior_probability=prior,
                plugin=plugin,
            )
        )
        mechanism_ids.append(plugin.mechanism_id)
        families.append(plugin.family)
    if (
        len(mechanisms) < 2
        or len(mechanism_ids) != len(set(mechanism_ids))
        or len(families) != len(set(families))
        or not np.isclose(sum(row.prior_probability for row in mechanisms), 1.0)
    ):
        raise LiveOperatorError("live mechanism hypothesis set is invalid")

    intervention_rows = config.get("interventions") or []
    intervention_ids = [str(row.get("intervention_id", "")) for row in intervention_rows]
    if (
        not intervention_ids
        or any(not value for value in intervention_ids)
        or len(intervention_ids) != len(set(intervention_ids))
    ):
        raise LiveOperatorError("live intervention identities are invalid")
    interventions: list[LiveIntervention] = []
    for row in intervention_rows:
        availability = str(row.get("availability", ""))
        if availability not in {"available_simulator", "unavailable_measurement"}:
            raise LiveOperatorError("live intervention availability is invalid")
        if str(row.get("kind", "")) not in {
            "simulator_family",
            "measurement_acquisition",
        }:
            raise LiveOperatorError("live intervention kind is invalid")
        if set(row.get("predicted_signatures") or {}) != set(mechanism_ids):
            raise LiveOperatorError("intervention signatures changed hypothesis set")
        if not set(row.get("required_observables") or []).issubset(observable_ids):
            raise LiveOperatorError("intervention requires an undeclared observable")
        if not set(row.get("declared_scopes") or []).issubset(families):
            raise LiveOperatorError("intervention scope is undeclared")
        if not set(row.get("residual_node_ids") or []).issubset(residual_ids):
            raise LiveOperatorError("intervention residual scope is undeclared")
        maximum_trials = int(row.get("maximum_trials", -1))
        if maximum_trials < 0 or maximum_trials > int(config["budget"]["maximum_anchor_replays"]):
            raise LiveOperatorError("intervention trial budget is invalid")
        interventions.append(
            LiveIntervention(
                intervention_id=str(row["intervention_id"]),
                kind=str(row["kind"]),
                availability=availability,
                maximum_trials=maximum_trials,
                payload=copy.deepcopy(dict(row)),
            )
        )
    for mechanism in mechanisms:
        if not set(mechanism.plugin.contract["candidate_interventions"]).issubset(
            intervention_ids
        ):
            raise LiveOperatorError("mechanism predicts an undeclared intervention")

    factor_rows = config.get("factor_beliefs") or []
    factor_ids = [str(row.get("factor_id", "")) for row in factor_rows]
    if (
        not factor_ids
        or any(not value for value in factor_ids)
        or len(factor_ids) != len(set(factor_ids))
    ):
        raise LiveOperatorError("live factor beliefs are invalid")
    for row in factor_rows:
        affected_by = [str(value) for value in row.get("affected_by_mechanisms") or []]
        if not set(affected_by).issubset(mechanism_ids):
            raise LiveOperatorError("factor references an undeclared mechanism")
        if not np.isfinite(float(row.get("value", float("nan")))):
            raise LiveOperatorError("live factor value is invalid")

    try:
        rank_live_acquisition(
            hypotheses={row.mechanism_id: row.prior_probability for row in mechanisms},
            candidates=intervention_rows,
            weights=(config.get("acquisition") or {}).get("weights") or {},
        )
    except AcquisitionError as error:
        raise LiveOperatorError(f"live acquisition contract is invalid: {error}") from error
    intervention_set_digest = canonical_digest(
        [dict(row.payload) for row in sorted(interventions, key=lambda value: value.intervention_id)]
    )
    return LiveCampaignContract(
        path=resolved,
        payload=copy.deepcopy(config),
        source_paths=source_paths,
        mechanisms=tuple(mechanisms),
        interventions=tuple(interventions),
        action_sha256=expected_action_sha,
        evaluator_digest=evaluator_digest,
        intervention_set_digest=intervention_set_digest,
        config_digest=canonical_digest(config),
        residual_artifact=residual_artifact,
    )


def validate_observed_intervention_result(
    contract: LiveCampaignContract, result: Mapping[str, Any]
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(result))
    if normalized.get("schema_version") != RESULT_SCHEMA:
        raise LiveOperatorError("unexpected live intervention result schema")
    if normalized.get("campaign_id") != contract.campaign_id:
        raise LiveOperatorError("observed result campaign identity changed")
    interventions = {row.intervention_id: row for row in contract.interventions}
    intervention_id = str(normalized.get("intervention_id", ""))
    if intervention_id not in interventions:
        raise LiveOperatorError("post-result intervention family expanded")
    if normalized.get("frozen_intervention_set_digest") != contract.intervention_set_digest:
        raise LiveOperatorError("post-result intervention set expanded or changed")
    intervention = interventions[intervention_id]
    if intervention.availability != "available_simulator":
        raise LiveOperatorError("observed result targets an unavailable intervention")
    if normalized.get("action_sha256") != contract.action_sha256:
        raise LiveOperatorError("observed result action drift")
    if normalized.get("evaluator_digest") != contract.evaluator_digest:
        raise LiveOperatorError("observed result evaluator drift")
    replay_count = int(normalized.get("anchor_replays", -1))
    remaining_interventions = int(contract.budget["maximum_interventions"]) - int(
        contract.budget["used_interventions"]
    )
    remaining_replays = int(contract.budget["maximum_anchor_replays"]) - int(
        contract.budget["used_anchor_replays"]
    )
    if (
        remaining_interventions < 1
        or replay_count <= 0
        or replay_count > remaining_replays
        or replay_count > intervention.maximum_trials
    ):
        raise LiveOperatorError("observed result escaped the global budget")
    update_discrete_structure_posterior(
        contract.hypothesis_priors,
        likelihoods=normalized.get("hypothesis_likelihoods") or {},
        observation_id=intervention_id,
    )
    declared_factors = {
        str(row["factor_id"]) for row in contract.payload["factor_beliefs"]
    }
    if not set(normalized.get("factor_updates") or {}).issubset(declared_factors):
        raise LiveOperatorError("observed result introduced an undeclared factor")
    promotion = normalized.get("promotion") or {}
    promoted = promotion.get("promoted") is True
    if promoted and (
        promotion.get("requested_by") != contract.payload["evaluator"]["evaluator_id"]
        or (normalized.get("consequence") or {}).get("evaluator_passed") is not True
    ):
        raise LiveOperatorError("unauthorized self-promotion was requested")
    if not promoted and promotion.get("requested_by") not in {
        None,
        contract.payload["evaluator"]["evaluator_id"],
    }:
        raise LiveOperatorError("unauthorized promotion requester")
    return normalized


def _manual_ablation(contract: LiveCampaignContract) -> dict[str, Any]:
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


def _invariance_result(contract: LiveCampaignContract) -> dict[str, Any]:
    config = contract.payload["invariance"]
    covariate = str(config["context_covariate"])
    episodes = []
    for row in config["episode_contexts"]:
        episodes.append(
            {
                "episode_id": str(row["episode_id"]),
                "context": {covariate: str(row["level"])},
                "feature": row.get("feature", [0.0, 1.0, 2.0]),
                "observation": row.get("observation", [0.0, 1.0, 2.0]),
                "actions": row.get("actions", [[0.0] * 6] * 3),
            }
        )
    return evaluate_invariance(
        mechanism_id=str(config["mechanism_id"]),
        invariant_parameter=str(config["invariant_parameter"]),
        context_covariate=covariate,
        episodes=episodes,
        thresholds=config["thresholds"],
        proof_class=str(contract.payload["proof_boundary"]["proof_class"]),
    )


def _relative_config_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def run_live_operator(
    config_path: Path,
    *,
    output_root: Path,
    observed_result_path: Path | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Execute the causal control path to an evaluator verdict or abstention."""

    contract = load_live_campaign_contract(config_path, repo_root=repo_root)
    config = contract.payload
    available_observables = [
        str(row["observable_id"]) for row in config["observables"] if row["available"]
    ]
    missing_observables = sorted(
        str(row["observable_id"]) for row in config["observables"] if not row["available"]
    )
    surprise = evaluate_surprise(
        config["structural_surprise"]["signals"],
        {
            "components": config["structural_surprise"]["components"],
            "trigger": config["structural_surprise"]["trigger"],
        },
        missing_observables=missing_observables,
    )
    mechanism_status = [
        {
            "mechanism_id": row.mechanism_id,
            "family": row.family,
            "prior_probability": row.prior_probability,
            **row.plugin.observable_status(available_observables),
        }
        for row in contract.mechanisms
    ]
    posterior = update_discrete_structure_posterior(contract.hypothesis_priors)
    acquisition = rank_live_acquisition(
        hypotheses=contract.hypothesis_priors,
        candidates=[row.payload for row in contract.interventions],
        weights=config["acquisition"]["weights"],
    )
    selected_id = str(acquisition["selected_intervention"])
    selected = next(row for row in acquisition["rows"] if row["intervention_id"] == selected_id)
    source_binding_name = str(config["action_identity"]["source_binding"])
    source = copy.deepcopy(dict(config["source_bindings"][source_binding_name]))
    before_graph = build_live_belief_graph(
        campaign_id=contract.campaign_id,
        generated_at=str(config["created_at"]),
        subject=config["subject"],
        residuals=contract.residual_artifact["residuals"],
        mechanisms=[row.plugin.contract for row in contract.mechanisms],
        interventions=[row.payload for row in contract.interventions],
        posterior=posterior["before"],
        selected_intervention_id=None,
        verdict="pending",
        proof_class=str(config["proof_boundary"]["proof_class"]),
        evaluator_identity=str(config["evaluator"]["evaluator_id"]),
        source=source,
        authority=config["authority"],
    )
    influence_results = []
    selected_mechanisms: set[str] = set()
    for mechanism in contract.mechanisms:
        result = discover_influence_set(
            mechanism_id=mechanism.mechanism_id,
            mechanism_family=mechanism.family,
            graph_factors=mechanism.plugin.contract["graph_factors"],
            interventions=[row.payload for row in contract.interventions],
            graph_edges=before_graph["edges"],
            thresholds=config["influence_thresholds"],
        )
        influence_results.append(result)
        if selected_id in result["affected_intervention_ids"]:
            selected_mechanisms.add(mechanism.mechanism_id)
    affected_factor_ids = sorted(
        str(row["factor_id"])
        for row in config["factor_beliefs"]
        if selected_mechanisms
        & {str(value) for value in row.get("affected_by_mechanisms") or []}
    )

    observed_result = None
    if observed_result_path is not None:
        observed_result = validate_observed_intervention_result(
            contract,
            load_json_object(observed_result_path, label="live intervention result"),
        )
        if observed_result["intervention_id"] != selected_id:
            raise LiveOperatorError("observed result was not selected by acquisition")
        posterior = update_discrete_structure_posterior(
            contract.hypothesis_priors,
            likelihoods=observed_result["hypothesis_likelihoods"],
            observation_id=selected_id,
        )
        consequence = observed_result["consequence"]
        verdict = (
            "evaluator_pass"
            if consequence.get("evaluator_passed") is True
            else "evaluator_reject"
        )
        budget = {
            **copy.deepcopy(dict(config["budget"])),
            "used_interventions": int(config["budget"]["used_interventions"]) + 1,
            "used_anchor_replays": int(config["budget"]["used_anchor_replays"])
            + int(observed_result["anchor_replays"]),
        }
    else:
        consequence = {
            "status": "not_run_no_intervention_result_opened",
            "evaluator_digest": contract.evaluator_digest,
            "evaluator_changed": False,
            "task_thresholds_changed": False,
            "promotion": False,
        }
        budget = copy.deepcopy(dict(config["budget"]))
        minimum_gain = float(config["acquisition"]["minimum_predicted_information_gain"])
        if int(budget["used_interventions"]) >= int(budget["maximum_interventions"]):
            verdict = "abstain_global_budget_exhausted"
        elif not selected["available_for_execution"]:
            verdict = "abstain_measurement_acquisition_required"
        elif float(selected["predicted_information_gain"]) < minimum_gain:
            verdict = "abstain_non_identifying_simulator_intervention"
        else:
            verdict = "abstain_no_bound_intervention_result"
    closure = apply_live_sparse_closure(
        before_factors=config["factor_beliefs"],
        affected_factor_ids=affected_factor_ids,
        updates=None if observed_result is None else observed_result.get("factor_updates") or {},
        observation_opened=observed_result is not None,
        action_identity={"sha256": contract.action_sha256},
        evidence_identity={"sha256": contract.residual_artifact["residual_digest"]},
    )
    invariance = _invariance_result(contract)
    after_graph = build_live_belief_graph(
        campaign_id=contract.campaign_id,
        generated_at=str(config["created_at"]),
        subject=config["subject"],
        residuals=contract.residual_artifact["residuals"],
        mechanisms=[row.plugin.contract for row in contract.mechanisms],
        interventions=[row.payload for row in contract.interventions],
        posterior=posterior["after"],
        selected_intervention_id=selected_id,
        verdict=verdict,
        proof_class=str(config["proof_boundary"]["proof_class"]),
        evaluator_identity=str(config["evaluator"]["evaluator_id"]),
        source=source,
        authority=config["authority"],
    )
    manual = _manual_ablation(contract)
    sail_ablation = {
        "interventions_executed": int(budget["used_interventions"])
        - int(config["budget"]["used_interventions"]),
        "simulator_evaluations": int(budget["used_anchor_replays"])
        - int(config["budget"]["used_anchor_replays"]),
        "hypotheses_rejected": [
            name for name, value in posterior["after"].items() if value <= 0.05
        ],
        "hypotheses_retained": [
            name for name, value in posterior["after"].items() if value > 0.05
        ],
        "observed_information_gain_bits": posterior["observed_information_gain_bits"],
        "task_consequences": consequence,
        "abstention_quality": (
            "pre_execution_missing_identifying_measurement"
            if verdict == "abstain_measurement_acquisition_required"
            else "not_applicable"
        ),
    }
    ablation_unsigned = {
        "schema_version": "sim2claw.sail_manual_vs_live_ablation.v1",
        "manual": manual,
        "sail": sail_ablation,
        "comparison": {
            "simulator_evaluations_avoided": manual["simulator_evaluations"]
            - sail_ablation["simulator_evaluations"],
            "accepted_task_gain_earned_by_sail": False,
            "efficiency_is_not_task_success": True,
            "advantage_manufactured": False,
        },
    }
    ablation = {**ablation_unsigned, "ablation_digest": canonical_digest(ablation_unsigned)}
    packet_unsigned = {
        "schema_version": "sim2claw.sail_sealed_measurement_acquisition_packet.v1",
        "campaign_id": contract.campaign_id,
        "selected_intervention": selected_id,
        "verdict": verdict,
        "missing_observables": missing_observables,
        **copy.deepcopy(dict(config["measurement_acquisition_packet"])),
        "action_sha256": contract.action_sha256,
        "evaluator_digest": contract.evaluator_digest,
        "intervention_set_digest": contract.intervention_set_digest,
        "sealed_before_execution": observed_result is None,
        "intervention_executed": observed_result is not None,
        "authority": copy.deepcopy(dict(config["authority"])),
    }
    packet = {**packet_unsigned, "packet_digest": canonical_digest(packet_unsigned)}
    stages = [
        {"stage": "residual_evidence", "status": "verified", "digest": contract.residual_artifact["residual_digest"]},
        {"stage": "structural_surprise", "status": "triggered" if surprise["triggered"] else "not_triggered", "score": surprise["score"]},
        {"stage": "belief_before", "status": "verified", "digest": before_graph["graph_digest"]},
        {"stage": "competing_mechanisms", "status": "retained", "mechanisms": mechanism_status},
        {"stage": "acquisition", "status": "ranked_before_result", "selected_intervention": selected_id, "predicted_information_gain": selected["predicted_information_gain"]},
        {"stage": "global_budget", "status": "enforced", "budget": budget},
        {"stage": "influence", "status": "discovered", "affected_factor_ids": affected_factor_ids},
        {"stage": "posterior_update", "status": posterior["status"], "observed_information_gain_bits": posterior["observed_information_gain_bits"]},
        {"stage": "sparse_loop_closure", "status": closure["status"], "unaffected_unchanged": closure["unaffected_factor_digests_unchanged"]},
        {"stage": "invariance_and_consequence", "status": invariance["verdict"], "consequence": consequence},
        {"stage": "terminal_verdict", "status": verdict, "promotion": False},
    ]
    trace_unsigned = {
        "schema_version": "sim2claw.sail_live_operator_trace.v1",
        "campaign_id": contract.campaign_id,
        "stages": stages,
        "source_action_bytes_unchanged": True,
        "evaluator_changed": False,
        "agent_promoted": False,
        "training_admitted": False,
        "physical_authority": False,
    }
    trace = {**trace_unsigned, "trace_digest": canonical_digest(trace_unsigned)}

    output_root.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "operator_trace": trace,
        "residual_evidence": contract.residual_artifact,
        "structural_surprise": surprise,
        "belief_before": before_graph,
        "belief_after": after_graph,
        "mechanism_status": {"schema_version": "sim2claw.sail_live_mechanism_status.v1", "mechanisms": mechanism_status},
        "acquisition_ranking": acquisition,
        "posterior": posterior,
        "influence": {"schema_version": "sim2claw.sail_live_influence.v1", "results": influence_results},
        "sparse_closure": closure,
        "invariance": invariance,
        "consequence": consequence,
        "ablation": ablation,
        "acquisition_packet": packet,
    }
    output_bindings: dict[str, dict[str, str]] = {}
    for name, artifact in artifacts.items():
        path = output_root / f"{name}.json"
        atomic_write_json(path, artifact)
        output_bindings[name] = {"path": path.name, "sha256": sha256_file(path)}
    code_paths = [
        "src/sim2claw/sail/live_operator.py",
        "src/sim2claw/sail/residuals.py",
        "src/sim2claw/sail/structural_surprise.py",
        "src/sim2claw/sail/mechanisms.py",
        "src/sim2claw/sail/posterior.py",
        "src/sim2claw/sail/acquisition.py",
        "src/sim2claw/sail/belief_graph.py",
        "src/sim2claw/sail/influence.py",
        "src/sim2claw/sail/loop_closure.py",
        "src/sim2claw/sail/invariance.py",
    ]
    receipt_unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "campaign_id": contract.campaign_id,
        "config": {
            "path": _relative_config_path(contract.path, repo_root),
            "sha256": sha256_file(contract.path),
            "canonical_digest": contract.config_digest,
        },
        "source_sha256": {
            name: binding["sha256"] for name, binding in sorted(config["source_bindings"].items())
        },
        "compiler_sha256": {path: sha256_file(REPO_ROOT / path) for path in code_paths},
        "outputs": output_bindings,
        "action_sha256": contract.action_sha256,
        "action_bytes_unchanged": True,
        "evaluator_digest": contract.evaluator_digest,
        "evaluator_changed": False,
        "intervention_set_digest": contract.intervention_set_digest,
        "selected_intervention": selected_id,
        "verdict": verdict,
        "budget": budget,
        "observed_information_gain": {
            "status": (
                "observed" if posterior["observed_information_gain_bits"] is not None else "not_observed_abstained_before_execution"
            ),
            "bits": posterior["observed_information_gain_bits"],
        },
        "manual_ablation_counts": {
            "completed_campaigns": manual["completed_campaigns"],
            "candidate_replays": manual["simulator_evaluations"],
            "anchor_passes": manual["anchor_passes"],
            "incomplete_artifacts": manual["incomplete_work_in_progress"]["artifact_count"],
        },
        "promotion": False,
        "training_admitted": False,
        "physical_authority": False,
        "proof_class": config["proof_boundary"]["proof_class"],
    }
    receipt = {**receipt_unsigned, "receipt_digest": canonical_digest(receipt_unsigned)}
    receipt_path = output_root / "receipt.json"
    atomic_write_json(receipt_path, receipt)
    return {
        "schema_version": "sim2claw.sail_live_operator_result.v1",
        "campaign_id": contract.campaign_id,
        "verdict": verdict,
        "selected_intervention": selected_id,
        "budget": budget,
        "action_sha256": contract.action_sha256,
        "evaluator_digest": contract.evaluator_digest,
        "receipt_sha256": sha256_file(receipt_path),
        "receipt_digest": receipt["receipt_digest"],
        "output_root": str(output_root),
        "promotion": False,
        "training_admitted": False,
        "physical_authority": False,
    }


__all__ = [
    "CONFIG_SCHEMA",
    "LiveCampaignContract",
    "LiveIntervention",
    "LiveMechanism",
    "LiveOperatorError",
    "apply_live_sparse_closure",
    "build_live_belief_graph",
    "load_live_campaign_contract",
    "rank_live_acquisition",
    "run_live_operator",
    "update_discrete_structure_posterior",
    "validate_live_residual_evidence",
    "validate_observed_intervention_result",
]

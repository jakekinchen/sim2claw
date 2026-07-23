"""Generic, budgeted SAIL decision/evidence control plane.

The control plane ranks preregistered interventions and consumes independently
evaluated, hash-bound receipts.  It is not an intervention executor.
"""

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
from .live_evidence import (
    EvidenceAdmissionError,
    commit_prepared_state,
    evaluator_identity,
    json_artifact_sha256,
    locked_campaign_state,
    prepare_admitted_result,
    validate_campaign_state,
    verify_measurement_evaluator_receipt,
    verify_simulator_evaluator_receipt,
)
from .loop_closure import LoopClosureError
from .mechanisms import MechanismPlugin, build_mechanism_plugin, json_pointer
from .posterior import PosteriorError, rank_structure_particles
from .structural_surprise import evaluate_surprise


CONFIG_SCHEMA = "sim2claw.sail_live_campaign.v2"
RECEIPT_SCHEMA = "sim2claw.sail_live_operator_receipt.v2"
CANONICAL_STATE_ROOT = "outputs/sail/live-campaign-state-v1"
STATE_KEY_SCHEMA = "sim2claw.sail_live_campaign_state_key.v1"


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
        "maximum_measurement_trials",
        "used_interventions",
        "used_anchor_replays",
        "used_measurement_trials",
    }
    if set(payload) != required:
        raise LiveOperatorError("live operator budget field set changed")
    values = {name: int(payload[name]) for name in required}
    if (
        values["maximum_interventions"] <= 0
        or values["maximum_anchor_replays"] < 0
        or values["maximum_measurement_trials"] < 0
        or values["used_interventions"] < 0
        or values["used_anchor_replays"] < 0
        or values["used_measurement_trials"] < 0
        or values["used_interventions"] > values["maximum_interventions"]
        or values["used_anchor_replays"] > values["maximum_anchor_replays"]
        or values["used_measurement_trials"] > values["maximum_measurement_trials"]
    ):
        raise LiveOperatorError("live operator budget is invalid")


def load_live_campaign_contract(
    path: Path, *, repo_root: Path = REPO_ROOT
) -> LiveCampaignContract:
    """Load a typed campaign without enumerating campaign or task IDs."""

    resolved = path.resolve() if path.is_absolute() else (repo_root / path).resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError as error:
        raise LiveOperatorError("live campaign config must be repository-bound") from error
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
    persistent_state = config.get("persistent_state") or {}
    if persistent_state != {
        "repo_relative_root": CANONICAL_STATE_ROOT,
        "key_algorithm": "sha256_campaign_config_v1",
    }:
        raise LiveOperatorError(
            "persistent state root or campaign/config key algorithm changed"
        )

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
        budget_name = (
            "maximum_anchor_replays"
            if str(row.get("kind", "")) == "simulator_family"
            else "maximum_measurement_trials"
        )
        if maximum_trials < 0 or maximum_trials > int(config["budget"][budget_name]):
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
    packet = config.get("measurement_acquisition_packet") or {}
    if (
        float(packet.get("minimum_sampling_hz", 0.0)) <= 0.0
        or int(packet.get("maximum_alignment_skew_samples", -1)) < 0
        or not packet.get("calibration")
        or not packet.get("required_phases")
        or packet.get("robot_motion_authority") is not False
    ):
        raise LiveOperatorError("measurement acquisition packet is invalid")
    measurement_evaluation = config.get("measurement_result_evaluation") or {}
    if {
        str(measurement_evaluation.get("flexural_mechanism_id", "")),
        str(measurement_evaluation.get("actuator_mechanism_id", "")),
    } != set(mechanism_ids):
        raise LiveOperatorError("measurement evaluator mechanism roles changed")
    if set(measurement_evaluation.get("feature_algorithms") or {}) != {
        "force_deformation_coupling",
        "current_force_hysteresis",
        "loaded_patch_change",
    }:
        raise LiveOperatorError("measurement feature preregistration changed")
    expected_thresholds = {
        "flexural_min_force_deformation_coupling",
        "flexural_max_current_force_hysteresis",
        "flexural_min_loaded_patch_change",
        "actuator_max_force_deformation_coupling",
        "actuator_min_current_force_hysteresis",
        "actuator_max_loaded_patch_change",
    }
    thresholds = measurement_evaluation.get("thresholds") or {}
    if set(thresholds) != expected_thresholds or any(
        not np.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0
        for value in thresholds.values()
    ):
        raise LiveOperatorError("measurement evaluator thresholds changed")
    if measurement_evaluation.get("allowed_proof_classes") != [
        "synthetic_measurement_fixture"
    ]:
        raise LiveOperatorError("measurement evaluator proof class widened")
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


def _relative_config_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _resolve_repo_relative_path(
    value: str, *, repo_root: Path, label: str
) -> Path:
    raw = Path(value)
    if raw.is_absolute() or not value or raw.as_posix() != value or ".." in raw.parts:
        raise LiveOperatorError(f"{label} is not a canonical repository-relative path")
    root = repo_root.resolve()
    resolved = (root / raw).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise LiveOperatorError(f"{label} escaped the repository") from error
    return resolved


def resolve_live_campaign_state_path(
    contract: LiveCampaignContract, *, repo_root: Path = REPO_ROOT
) -> Path:
    """Return the one generated state path for a campaign/config identity."""

    persistent_state = contract.payload["persistent_state"]
    root = _resolve_repo_relative_path(
        str(persistent_state["repo_relative_root"]),
        repo_root=repo_root,
        label="persistent state root",
    )
    if root != (repo_root.resolve() / CANONICAL_STATE_ROOT).resolve():
        raise LiveOperatorError("persistent state root is not the canonical generated root")
    key = canonical_digest(
        {
            "schema_version": STATE_KEY_SCHEMA,
            "campaign_id": contract.campaign_id,
            "config_digest": contract.config_digest,
        }
    )
    return root / key / "campaign_state.json"


_COMPILER_PATHS = (
    "src/sim2claw/sail/live_operator.py",
    "src/sim2claw/sail/live_evidence.py",
    "src/sim2claw/sail/residuals.py",
    "src/sim2claw/sail/structural_surprise.py",
    "src/sim2claw/sail/mechanisms.py",
    "src/sim2claw/sail/posterior.py",
    "src/sim2claw/sail/acquisition.py",
    "src/sim2claw/sail/belief_graph.py",
    "src/sim2claw/sail/influence.py",
    "src/sim2claw/sail/loop_closure.py",
    "src/sim2claw/sail/invariance.py",
)


def build_live_evaluator_identity(
    contract: LiveCampaignContract, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    config = contract.payload
    return evaluator_identity(
        evaluator=config["evaluator"],
        evaluator_digest=contract.evaluator_digest,
        source_sha256={
            name: binding["sha256"]
            for name, binding in sorted(config["source_bindings"].items())
        },
        config_sha256=sha256_file(contract.path),
        config_digest=contract.config_digest,
        compiler_sha256={path: sha256_file(repo_root / path) for path in _COMPILER_PATHS},
    )


def _sealed_measurement_packet(
    contract: LiveCampaignContract,
    *,
    selected_id: str,
    missing_observables: Sequence[str],
) -> dict[str, Any]:
    config = contract.payload
    packet_unsigned = {
        "schema_version": "sim2claw.sail_sealed_measurement_acquisition_packet.v1",
        "campaign_id": contract.campaign_id,
        "selected_intervention": selected_id,
        "verdict": "abstain_measurement_acquisition_required",
        "missing_observables": sorted(str(value) for value in missing_observables),
        **copy.deepcopy(dict(config["measurement_acquisition_packet"])),
        "action_sha256": contract.action_sha256,
        "evaluator_digest": contract.evaluator_digest,
        "intervention_set_digest": contract.intervention_set_digest,
        "sealed_before_execution": True,
        "intervention_executed": False,
        "authority": copy.deepcopy(dict(config["authority"])),
    }
    return {**packet_unsigned, "packet_digest": canonical_digest(packet_unsigned)}


def _validate_admitted_result(
    contract: LiveCampaignContract,
    admission: Mapping[str, Any],
    *,
    selected_intervention_id: str,
    affected_factor_ids: Sequence[str],
) -> None:
    result = admission["result"]
    if result.get("selected_intervention") != selected_intervention_id:
        raise LiveOperatorError("evaluator result changed the selected intervention")
    if admission.get("consequence") != result.get("consequence"):
        raise LiveOperatorError("evaluator result consequence changed after verification")
    update_discrete_structure_posterior(
        contract.hypothesis_priors,
        likelihoods=result.get("hypothesis_likelihoods") or {},
        observation_id=str(result["selected_intervention"]),
    )
    updates = {str(name) for name in (result.get("factor_updates") or {})}
    declared_factors = {str(row["factor_id"]) for row in contract.payload["factor_beliefs"]}
    if not updates.issubset(declared_factors):
        raise LiveOperatorError("evaluator result introduced an undeclared factor")
    if not updates.issubset({str(value) for value in affected_factor_ids}):
        raise LiveOperatorError("evaluator result attempted an unaffected factor update")


_RECEIPT_FIELDS = {
    "schema_version",
    "campaign_id",
    "config",
    "source_sha256",
    "compiler_sha256",
    "evaluator_identity",
    "outputs",
    "action_sha256",
    "action_bytes_unchanged",
    "evaluator_digest",
    "evaluator_changed",
    "intervention_set_digest",
    "selected_intervention",
    "verdict",
    "budget",
    "campaign_state",
    "admitted_evaluator_receipt",
    "observed_information_gain",
    "manual_ablation_counts",
    "promotion",
    "training_admitted",
    "physical_authority",
    "proof_class",
    "intervention_executor_implemented",
    "receipt_digest",
}
_BASE_OUTPUTS = {
    "operator_trace",
    "residual_evidence",
    "structural_surprise",
    "belief_before",
    "belief_after",
    "mechanism_status",
    "acquisition_ranking",
    "posterior",
    "influence",
    "sparse_closure",
    "invariance",
    "consequence",
    "ablation",
    "acquisition_packet",
    "campaign_state",
}
_OUTPUT_DIGEST_FIELDS = {
    "operator_trace": "trace_digest",
    "residual_evidence": "residual_digest",
    "belief_before": "graph_digest",
    "belief_after": "graph_digest",
    "acquisition_ranking": "ranking_digest",
    "posterior": "posterior_digest",
    "sparse_closure": "closure_digest",
    "invariance": "invariance_digest",
    "ablation": "ablation_digest",
    "acquisition_packet": "packet_digest",
}


def _verify_embedded_digest(
    payload: Mapping[str, Any], *, digest_field: str, label: str
) -> None:
    unsigned = copy.deepcopy(dict(payload))
    observed = unsigned.pop(digest_field, None)
    if observed != canonical_digest(unsigned):
        raise LiveOperatorError(f"{label} canonical digest mismatch")


def _load_receipt_output(
    binding: Mapping[str, Any], *, receipt_root: Path, label: str
) -> tuple[Path, dict[str, Any]]:
    if set(binding) != {"path", "sha256"}:
        raise LiveOperatorError(f"{label} output binding field set changed")
    relative = str(binding["path"])
    path = _resolve_repo_relative_path(
        relative, repo_root=receipt_root, label=f"{label} output path"
    )
    if path.parent != receipt_root.resolve() or not path.is_file():
        raise LiveOperatorError(f"{label} output path left the receipt directory")
    if sha256_file(path) != str(binding["sha256"]):
        raise LiveOperatorError(f"{label} output hash mismatch")
    return path, load_json_object(path, label=f"live operator {label} output")


def _verify_live_operator_receipt(
    receipt_path: Path,
    *,
    repo_root: Path,
    expected_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    receipt = load_json_object(receipt_path, label="SAIL live operator receipt")
    if set(receipt) != _RECEIPT_FIELDS:
        raise LiveOperatorError("live operator receipt field set changed")
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise LiveOperatorError("unexpected live operator receipt schema")
    unsigned = copy.deepcopy(receipt)
    observed_digest = unsigned.pop("receipt_digest")
    if observed_digest != canonical_digest(unsigned):
        raise LiveOperatorError("live operator receipt canonical digest mismatch")
    for name in ("promotion", "training_admitted", "physical_authority"):
        if receipt.get(name) is not False:
            raise LiveOperatorError(f"live operator receipt {name} widened authority")
    if (
        receipt.get("action_bytes_unchanged") is not True
        or receipt.get("evaluator_changed") is not False
        or receipt.get("intervention_executor_implemented") is not False
    ):
        raise LiveOperatorError("live operator receipt control boundary changed")

    config_binding = receipt.get("config") or {}
    if set(config_binding) != {"path", "sha256", "canonical_digest"}:
        raise LiveOperatorError("live operator config binding field set changed")
    config_path = _resolve_repo_relative_path(
        str(config_binding["path"]), repo_root=repo_root, label="live operator config"
    )
    if not config_path.is_file() or sha256_file(config_path) != str(
        config_binding["sha256"]
    ):
        raise LiveOperatorError("live operator config hash mismatch")
    contract = load_live_campaign_contract(config_path, repo_root=repo_root)
    if (
        config_binding["canonical_digest"] != contract.config_digest
        or receipt.get("campaign_id") != contract.campaign_id
        or receipt.get("action_sha256") != contract.action_sha256
        or receipt.get("evaluator_digest") != contract.evaluator_digest
        or receipt.get("intervention_set_digest") != contract.intervention_set_digest
        or receipt.get("proof_class") != contract.payload["proof_boundary"]["proof_class"]
    ):
        raise LiveOperatorError("live operator receipt campaign identity changed")
    expected_source = {
        name: binding["sha256"]
        for name, binding in sorted(contract.payload["source_bindings"].items())
    }
    expected_compiler = {
        path: sha256_file(repo_root / path) for path in _COMPILER_PATHS
    }
    if receipt.get("source_sha256") != expected_source:
        raise LiveOperatorError("live operator receipt source hashes changed")
    if receipt.get("compiler_sha256") != expected_compiler:
        raise LiveOperatorError("live operator receipt compiler hashes changed")
    if receipt.get("evaluator_identity") != build_live_evaluator_identity(
        contract, repo_root=repo_root
    ):
        raise LiveOperatorError("live operator receipt evaluator identity changed")
    intervention_ids = {row.intervention_id for row in contract.interventions}
    if str(receipt.get("selected_intervention", "")) not in intervention_ids:
        raise LiveOperatorError("live operator receipt selected intervention is undeclared")

    state_path = resolve_live_campaign_state_path(contract, repo_root=repo_root)
    state_relative = _relative_config_path(state_path, repo_root)
    if expected_state is None:
        if not state_path.is_file():
            raise LiveOperatorError("live operator canonical campaign state is missing")
        state = load_json_object(state_path, label="persistent SAIL campaign state")
        state_sha256 = sha256_file(state_path)
    else:
        state = copy.deepcopy(dict(expected_state))
        state_sha256 = json_artifact_sha256(state)
    try:
        state = validate_campaign_state(
            state,
            campaign_id=contract.campaign_id,
            config_digest=contract.config_digest,
            initial_budget=contract.budget,
        )
    except EvidenceAdmissionError as error:
        raise LiveOperatorError(f"live operator campaign state rejected: {error}") from error
    expected_state_binding = {
        "path": state_relative,
        "sha256": state_sha256,
        "state_digest": state["state_digest"],
        "chain_head": state["chain_head"],
        "event_count": len(state["events"]),
    }
    if receipt.get("campaign_state") != expected_state_binding:
        raise LiveOperatorError("live operator receipt is stale against canonical campaign state")
    if receipt.get("budget") != state["budget"]:
        raise LiveOperatorError("live operator receipt budget is not state-bound")

    outputs = receipt.get("outputs") or {}
    admitted = receipt.get("admitted_evaluator_receipt")
    expected_outputs = set(_BASE_OUTPUTS)
    if admitted is not None:
        expected_outputs.add("admitted_evaluator_receipt")
    if set(outputs) != expected_outputs:
        raise LiveOperatorError("live operator receipt output set changed")
    if outputs.get("campaign_state") != {
        "path": state_relative,
        "sha256": state_sha256,
    }:
        raise LiveOperatorError("live operator output state binding changed")
    loaded_outputs: dict[str, dict[str, Any]] = {}
    for name in sorted(expected_outputs - {"campaign_state"}):
        _, payload = _load_receipt_output(
            outputs[name], receipt_root=receipt_path.resolve().parent, label=name
        )
        loaded_outputs[name] = payload
        digest_field = _OUTPUT_DIGEST_FIELDS.get(name)
        if digest_field is not None:
            _verify_embedded_digest(payload, digest_field=digest_field, label=name)

    trace = loaded_outputs["operator_trace"]
    terminal = (trace.get("stages") or [{}])[-1]
    if (
        terminal.get("stage") != "terminal_verdict"
        or terminal.get("status") != receipt.get("verdict")
        or terminal.get("promotion") is not False
        or trace.get("agent_promoted") is not False
        or trace.get("training_admitted") is not False
        or trace.get("physical_authority") is not False
        or trace.get("intervention_executor_implemented") is not False
    ):
        raise LiveOperatorError("live operator trace widened or changed the terminal verdict")
    acquisition = loaded_outputs["acquisition_ranking"]
    if acquisition.get("selected_intervention") != receipt.get("selected_intervention"):
        raise LiveOperatorError("live operator acquisition selection changed")
    consequence = loaded_outputs["consequence"]
    consequence_stage = next(
        (
            row
            for row in trace.get("stages") or []
            if row.get("stage") == "invariance_and_consequence"
        ),
        None,
    )
    if consequence_stage is None or consequence_stage.get("consequence") != consequence:
        raise LiveOperatorError("live operator consequence changed")
    for name in (
        "promotion",
        "simulator_promotion",
        "training_admitted",
        "physical_authority",
        "robot_motion",
    ):
        if consequence.get(name) is True:
            raise LiveOperatorError("live operator consequence widened authority")
    packet_authority = loaded_outputs["acquisition_packet"].get("authority") or {}
    if not packet_authority or any(value is not False for value in packet_authority.values()):
        raise LiveOperatorError("live operator acquisition packet widened authority")
    posterior = loaded_outputs["posterior"]
    expected_gain = {
        "status": (
            "observed"
            if posterior.get("observed_information_gain_bits") is not None
            else "not_observed_abstained_before_execution"
        ),
        "bits": posterior.get("observed_information_gain_bits"),
    }
    if receipt.get("observed_information_gain") != expected_gain:
        raise LiveOperatorError("live operator observed information gain changed")
    manual = loaded_outputs["ablation"]["manual"]
    expected_manual = {
        "completed_campaigns": manual["completed_campaigns"],
        "candidate_replays": manual["simulator_evaluations"],
        "anchor_passes": manual["anchor_passes"],
        "incomplete_artifacts": manual["incomplete_work_in_progress"]["artifact_count"],
    }
    if receipt.get("manual_ablation_counts") != expected_manual:
        raise LiveOperatorError("live operator manual ablation counts changed")

    if admitted is None:
        if "admitted_evaluator_receipt" in loaded_outputs:
            raise LiveOperatorError("live operator admitted summary is unexpected")
    else:
        if not isinstance(admitted, Mapping) or set(admitted) != {
            "lane",
            "receipt_sha256",
            "receipt_digest",
            "execution_id",
        }:
            raise LiveOperatorError("live operator admitted receipt summary changed")
        if admitted.get("lane") != "offline_measurement":
            raise LiveOperatorError("untrusted simulator receipt admission is disabled")
        summary = loaded_outputs["admitted_evaluator_receipt"]
        if (
            summary.get("lane") != "offline_measurement"
            or summary.get("execution_id") != admitted.get("execution_id")
            or summary.get("receipt_sha256") != admitted.get("receipt_sha256")
            or summary.get("receipt_digest") != admitted.get("receipt_digest")
            or summary.get("promotion") is not False
            or summary.get("physical_authority") is not False
        ):
            raise LiveOperatorError("live operator admitted receipt fields changed")
        if not state["events"]:
            raise LiveOperatorError("admitted receipt is absent from campaign state")
        event = state["events"][-1]
        if (
            event.get("lane") != "offline_measurement"
            or event.get("execution_id") != admitted.get("execution_id")
            or event.get("receipt_sha256") != admitted.get("receipt_sha256")
            or event.get("receipt_digest") != admitted.get("receipt_digest")
            or event.get("result_sha256")
            != (summary.get("result_artifact") or {}).get("sha256")
        ):
            raise LiveOperatorError("admitted receipt is not the canonical state-chain head")
    return {
        "schema_version": "sim2claw.sail_live_operator_receipt_verification.v1",
        "campaign_id": contract.campaign_id,
        "verdict": receipt["verdict"],
        "receipt_sha256": sha256_file(receipt_path),
        "receipt_digest": receipt["receipt_digest"],
        "campaign_state_path": state_relative,
        "campaign_state_sha256": state_sha256,
        "campaign_state_digest": state["state_digest"],
        "campaign_state_chain_head": state["chain_head"],
        "promotion": False,
        "training_admitted": False,
        "physical_authority": False,
    }


def verify_live_operator_receipt(
    receipt_path: Path, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Revalidate a live-operator receipt and its current canonical state."""

    return _verify_live_operator_receipt(
        receipt_path.resolve(), repo_root=repo_root.resolve()
    )


def run_live_operator(
    config_path: Path,
    *,
    output_root: Path,
    simulator_evaluator_receipt_path: Path | None = None,
    measurement_evaluator_receipt_path: Path | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Run the decision plane and optionally admit one independent evaluator receipt."""

    contract = load_live_campaign_contract(config_path, repo_root=repo_root)
    if simulator_evaluator_receipt_path is not None and measurement_evaluator_receipt_path is not None:
        raise LiveOperatorError("only one evaluator receipt lane may be admitted per run")
    canonical_state_path = resolve_live_campaign_state_path(
        contract, repo_root=repo_root
    )
    with locked_campaign_state(
        canonical_state_path.parent,
        campaign_id=contract.campaign_id,
        config_digest=contract.config_digest,
        initial_budget=contract.budget,
    ) as (state_path, state):
        return _run_live_operator_locked(
            contract,
            output_root=output_root,
            state_path=state_path,
            state=state,
            simulator_evaluator_receipt_path=simulator_evaluator_receipt_path,
            measurement_evaluator_receipt_path=measurement_evaluator_receipt_path,
            repo_root=repo_root,
        )


def _run_live_operator_locked(
    contract: LiveCampaignContract,
    *,
    output_root: Path,
    state_path: Path,
    state: Mapping[str, Any],
    simulator_evaluator_receipt_path: Path | None,
    measurement_evaluator_receipt_path: Path | None,
    repo_root: Path,
) -> dict[str, Any]:
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
        selected_intervention_executed=False,
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

    packet = _sealed_measurement_packet(
        contract,
        selected_id=selected_id,
        missing_observables=missing_observables,
    )
    selected_contract = next(
        row for row in contract.interventions if row.intervention_id == selected_id
    )
    expected_evaluator = build_live_evaluator_identity(contract, repo_root=repo_root)
    admission = None
    try:
        if simulator_evaluator_receipt_path is not None:
            if selected_contract.kind != "simulator_family" or selected_contract.availability != "available_simulator":
                raise LiveOperatorError("simulator receipt does not target the selected simulator intervention")
            admission = verify_simulator_evaluator_receipt(
                simulator_evaluator_receipt_path,
                campaign_id=contract.campaign_id,
                selected_intervention=selected_contract.payload,
                intervention_set_digest=contract.intervention_set_digest,
                action_sha256=contract.action_sha256,
                expected_evaluator_identity=expected_evaluator,
                remaining_anchor_replays=int(state["budget"]["maximum_anchor_replays"])
                - int(state["budget"]["used_anchor_replays"]),
            )
        elif measurement_evaluator_receipt_path is not None:
            if selected_contract.kind != "measurement_acquisition":
                raise LiveOperatorError("measurement receipt does not target the selected measurement intervention")
            admission = verify_measurement_evaluator_receipt(
                measurement_evaluator_receipt_path,
                campaign_id=contract.campaign_id,
                selected_intervention=selected_contract.payload,
                intervention_set_digest=contract.intervention_set_digest,
                action_sha256=contract.action_sha256,
                expected_evaluator_identity=expected_evaluator,
                expected_packet=packet,
                evaluation_contract=config["measurement_result_evaluation"],
                remaining_measurement_trials=int(state["budget"]["maximum_measurement_trials"])
                - int(state["budget"]["used_measurement_trials"]),
            )
    except EvidenceAdmissionError as error:
        raise LiveOperatorError(f"evaluator receipt rejected: {error}") from error

    observed_result = None if admission is None else admission["result"]
    prepared_state: Mapping[str, Any] | None = None
    if admission is not None:
        _validate_admitted_result(
            contract,
            admission,
            selected_intervention_id=selected_id,
            affected_factor_ids=affected_factor_ids,
        )
        try:
            prepared_state = prepare_admitted_result(state, admission)
        except EvidenceAdmissionError as error:
            raise LiveOperatorError(f"evaluator receipt rejected: {error}") from error
        posterior = update_discrete_structure_posterior(
            contract.hypothesis_priors,
            likelihoods=observed_result["hypothesis_likelihoods"],
            observation_id=selected_id,
        )
        consequence = copy.deepcopy(dict(admission["consequence"]))
        if admission["lane"] == "offline_measurement":
            classification = str(observed_result["classification"])
            verdict = (
                "abstain_measurement_result_ambiguous"
                if classification == "ambiguous_abstention"
                else f"measurement_evidence_{classification}"
            )
        else:
            verdict = (
                "evaluator_pass"
                if consequence.get("evaluator_passed") is True
                else "evaluator_reject"
            )
        budget = copy.deepcopy(dict(prepared_state["budget"]))
    else:
        consequence = {
            "status": "not_run_no_intervention_result_opened",
            "evaluator_digest": contract.evaluator_digest,
            "evaluator_changed": False,
            "task_thresholds_changed": False,
            "promotion": False,
        }
        budget = copy.deepcopy(dict(state["budget"]))
        minimum_separation = float(
            config["acquisition"]["minimum_predicted_signature_separation"]
        )
        if int(budget["used_interventions"]) >= int(budget["maximum_interventions"]):
            verdict = "abstain_global_budget_exhausted"
        elif not selected["available_for_execution"]:
            verdict = "abstain_measurement_acquisition_required"
        elif float(selected["predicted_signature_separation"]) < minimum_separation:
            verdict = "abstain_non_identifying_simulator_intervention"
        else:
            verdict = "abstain_no_bound_intervention_result"
    closure = apply_live_sparse_closure(
        before_factors=config["factor_beliefs"],
        affected_factor_ids=affected_factor_ids,
        updates=None if admission is None else observed_result.get("factor_updates") or {},
        observation_opened=admission is not None,
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
        selected_intervention_executed=admission is not None,
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
        "measurement_trials": int(budget["used_measurement_trials"])
        - int(config["budget"]["used_measurement_trials"]),
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
            "historical_simulator_evaluations_informed_frozen_retrospective_decision": manual[
                "simulator_evaluations"
            ],
            "sail_additional_simulator_evaluations_after_pause": sail_ablation[
                "simulator_evaluations"
            ],
            "historical_evaluations_remain_retrospective_context": True,
            "claim": (
                f"{manual['simulator_evaluations']} historical evaluations informed the "
                "frozen retrospective decision; SAIL used "
                f"{sail_ablation['simulator_evaluations']} additional evaluations after the pause."
            ),
            "accepted_task_gain_earned_by_sail": False,
            "efficiency_is_not_task_success": True,
            "advantage_manufactured": False,
        },
    }
    ablation = {**ablation_unsigned, "ablation_digest": canonical_digest(ablation_unsigned)}
    stages = [
        {"stage": "residual_evidence", "status": "verified", "digest": contract.residual_artifact["residual_digest"]},
        {"stage": "structural_surprise", "status": "triggered" if surprise["triggered"] else "not_triggered", "score": surprise["score"]},
        {"stage": "belief_before", "status": "verified", "digest": before_graph["graph_digest"]},
        {"stage": "competing_mechanisms", "status": "retained", "mechanisms": mechanism_status},
        {"stage": "acquisition", "status": "ranked_before_result", "selected_intervention": selected_id, "predicted_signature_separation": selected["predicted_signature_separation"]},
        {"stage": "global_budget", "status": "enforced", "budget": budget},
        {
            "stage": "independent_evidence_admission",
            "status": "receipt_admitted" if admission is not None else "no_receipt_opened",
            "lane": None if admission is None else admission["lane"],
            "execution_id": None if admission is None else admission["execution_id"],
        },
        {"stage": "influence", "status": "discovered", "affected_factor_ids": affected_factor_ids},
        {"stage": "posterior_update", "status": posterior["status"], "entropy_delta_bits": posterior["entropy_delta_bits"], "observed_information_gain_bits": posterior["observed_information_gain_bits"]},
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
        "intervention_executor_implemented": False,
        "independent_evaluator_receipt_required": True,
    }
    trace = {**trace_unsigned, "trace_digest": canonical_digest(trace_unsigned)}
    state_for_receipt = state if prepared_state is None else prepared_state
    state_relative_path = _relative_config_path(state_path, repo_root)
    state_sha256 = json_artifact_sha256(state_for_receipt)

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
    if admission is not None:
        artifacts["admitted_evaluator_receipt"] = {
            "schema_version": "sim2claw.sail_admitted_evaluator_receipt_summary.v1",
            "lane": admission["lane"],
            "execution_id": admission["execution_id"],
            "anchor_replay_ids": admission["anchor_replay_ids"],
            "measurement_trial_ids": admission["measurement_trial_ids"],
            "receipt_sha256": admission["receipt_sha256"],
            "receipt_digest": admission["receipt"]["receipt_digest"],
            "raw_artifacts": admission["raw_artifacts"],
            "result_artifact": admission["result_artifact"],
            "promotion": False,
            "physical_authority": False,
        }
    output_bindings: dict[str, dict[str, str]] = {}
    for name, artifact in artifacts.items():
        path = output_root / f"{name}.json"
        atomic_write_json(path, artifact)
        output_bindings[name] = {"path": path.name, "sha256": sha256_file(path)}
    output_bindings["campaign_state"] = {
        "path": state_relative_path,
        "sha256": state_sha256,
    }
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
        "compiler_sha256": {path: sha256_file(repo_root / path) for path in _COMPILER_PATHS},
        "evaluator_identity": expected_evaluator,
        "outputs": output_bindings,
        "action_sha256": contract.action_sha256,
        "action_bytes_unchanged": True,
        "evaluator_digest": contract.evaluator_digest,
        "evaluator_changed": False,
        "intervention_set_digest": contract.intervention_set_digest,
        "selected_intervention": selected_id,
        "verdict": verdict,
        "budget": budget,
        "campaign_state": {
            "path": state_relative_path,
            "sha256": state_sha256,
            "state_digest": state_for_receipt["state_digest"],
            "chain_head": state_for_receipt["chain_head"],
            "event_count": len(state_for_receipt["events"]),
        },
        "admitted_evaluator_receipt": None
        if admission is None
        else {
            "lane": admission["lane"],
            "receipt_sha256": admission["receipt_sha256"],
            "receipt_digest": admission["receipt"]["receipt_digest"],
            "execution_id": admission["execution_id"],
        },
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
        "intervention_executor_implemented": False,
    }
    receipt = {**receipt_unsigned, "receipt_digest": canonical_digest(receipt_unsigned)}
    receipt_path = output_root / "receipt.json"
    atomic_write_json(receipt_path, receipt)
    _verify_live_operator_receipt(
        receipt_path,
        repo_root=repo_root,
        expected_state=state_for_receipt,
    )
    if prepared_state is not None:
        try:
            commit_prepared_state(state_path, state, prepared_state)
        except EvidenceAdmissionError as error:
            raise LiveOperatorError(f"evaluator receipt rejected: {error}") from error
    verified_receipt = verify_live_operator_receipt(receipt_path, repo_root=repo_root)
    return {
        "schema_version": "sim2claw.sail_live_operator_result.v1",
        "campaign_id": contract.campaign_id,
        "verdict": verdict,
        "selected_intervention": selected_id,
        "budget": budget,
        "action_sha256": contract.action_sha256,
        "evaluator_digest": contract.evaluator_digest,
        "receipt_sha256": verified_receipt["receipt_sha256"],
        "receipt_digest": receipt["receipt_digest"],
        "campaign_state_path": state_relative_path,
        "campaign_state_sha256": state_sha256,
        "campaign_state_digest": state_for_receipt["state_digest"],
        "campaign_state_chain_head": state_for_receipt["chain_head"],
        "output_root": str(output_root),
        "promotion": False,
        "training_admitted": False,
        "physical_authority": False,
    }


__all__ = [
    "CANONICAL_STATE_ROOT",
    "CONFIG_SCHEMA",
    "LiveCampaignContract",
    "LiveIntervention",
    "LiveMechanism",
    "LiveOperatorError",
    "apply_live_sparse_closure",
    "build_live_belief_graph",
    "build_live_evaluator_identity",
    "load_live_campaign_contract",
    "rank_live_acquisition",
    "resolve_live_campaign_state_path",
    "run_live_operator",
    "update_discrete_structure_posterior",
    "validate_live_residual_evidence",
    "verify_live_operator_receipt",
]

"""Typed, task-generic contracts for SAIL live campaigns."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from ..learning_factory_artifacts import canonical_digest
from .acquisition import AcquisitionError
from .contracts import REPO_ROOT, SailContractError, verify_source_binding
from .importers import load_json_object
from .live_decision import rank_live_acquisition, validate_live_residual_evidence
from .live_types import (
    CANONICAL_STATE_ROOT,
    CONFIG_SCHEMA,
    LiveCampaignContract,
    LiveIntervention,
    LiveMechanism,
    LiveOperatorError,
)
from .mechanisms import build_mechanism_plugin, json_pointer


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

__all__ = ["load_live_campaign_contract"]


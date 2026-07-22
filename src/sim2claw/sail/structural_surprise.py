"""Auditable structural-surprise and compensation-debt diagnostics for SAIL."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from ..learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .belief_graph import validate_graph
from .contracts import REPO_ROOT, SailContractError, verify_contract, verify_source_binding
from .importers import load_json_object
from .residuals import verify_residual_receipt


CONFIG_SCHEMA = "sim2claw.sail_structural_surprise_campaign.v1"
DIAGNOSTIC_SCHEMA = "sim2claw.sail_structural_surprise.v1"
REQUEST_SCHEMA = "sim2claw.sail_mechanism_request.v1"
RECEIPT_SCHEMA = "sim2claw.sail_structural_surprise_compile_receipt.v1"


class StructuralSurpriseError(SailContractError):
    """Structural-surprise computation lost evidence, normalization, or authority."""


def _verify_generic_receipt(payload: Mapping[str, Any]) -> None:
    normalized = copy.deepcopy(dict(payload))
    observed = normalized.pop("receipt_digest", None)
    if not isinstance(observed, str) or observed != canonical_digest(normalized):
        raise StructuralSurpriseError("structural-surprise source receipt changed")
    authority = payload.get("authority")
    if not isinstance(authority, dict) or any(authority.values()):
        raise StructuralSurpriseError("structural-surprise source widened authority")


def load_surprise_config(path: Path, *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    config = load_json_object(resolved, label="SAIL structural-surprise config")
    if config.get("schema_version") != CONFIG_SCHEMA:
        raise StructuralSurpriseError("unexpected structural-surprise config schema")
    authority = config.get("authority")
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise StructuralSurpriseError("structural-surprise config widened authority")
    for binding in (config.get("source_bindings") or {}).values():
        verify_source_binding(binding, repo_root=repo_root)
    components = config.get("components") or []
    ids = [str(row.get("id", "")) for row in components]
    if len(ids) != 8 or len(ids) != len(set(ids)) or any(not value for value in ids):
        raise StructuralSurpriseError("structural-surprise component set changed")
    weights = [float(row.get("weight", -1.0)) for row in components]
    if any(weight <= 0.0 for weight in weights) or not np.isclose(sum(weights), 1.0):
        raise StructuralSurpriseError("structural-surprise weights are not normalized")
    if any(
        row.get("uncertainty_class") not in {"parameter_uncertainty", "structural_uncertainty"}
        for row in components
    ):
        raise StructuralSurpriseError("structural-surprise uncertainty class changed")
    trigger = config.get("trigger") or {}
    for key in ("score_threshold", "component_threshold", "minimum_available_weight"):
        value = float(trigger.get(key, -1.0))
        if not 0.0 <= value <= 1.0:
            raise StructuralSurpriseError(f"invalid structural-surprise threshold: {key}")
    if trigger.get("missing_components_are_zero") is not False:
        raise StructuralSurpriseError("missing debt components became zero-valued")
    clean = config.get("clean_seeded_calibration") or {}
    if int(clean.get("case_count", 0)) <= 0 or not 0.0 <= float(
        clean.get("maximum_false_trigger_rate", -1.0)
    ) <= 1.0:
        raise StructuralSurpriseError("clean seeded calibration contract changed")
    request = config.get("mechanism_request") or {}
    if request.get("agent_allowed") is not False or request.get("physical_cause_asserted") is not False:
        raise StructuralSurpriseError("mechanism request gained agent or causal authority")
    return config


def _signal(
    *,
    value: float | None,
    available: bool,
    provenance: str,
    reason: str,
) -> dict[str, Any]:
    if available:
        if value is None or not np.isfinite(value) or not 0.0 <= float(value) <= 1.0:
            raise StructuralSurpriseError("available debt component is not normalized")
    elif value is not None:
        raise StructuralSurpriseError("unavailable debt component has a value")
    return {
        "value": None if value is None else float(value),
        "available": bool(available),
        "provenance": provenance,
        "reason": reason,
    }


def evaluate_surprise(
    signals: Mapping[str, Mapping[str, Any]],
    config: Mapping[str, Any],
    *,
    missing_observables: Sequence[str] = (),
) -> dict[str, Any]:
    specifications = {str(row["id"]): row for row in config["components"]}
    if set(signals) != set(specifications):
        raise StructuralSurpriseError("structural-surprise signal set changed")
    rows: list[dict[str, Any]] = []
    numerator = 0.0
    available_weight = 0.0
    for component_id in sorted(specifications):
        specification = specifications[component_id]
        raw = signals[component_id]
        available = raw.get("available") is True
        value = raw.get("value")
        normalized = _signal(
            value=None if value is None else float(value),
            available=available,
            provenance=str(raw.get("provenance", "")),
            reason=str(raw.get("reason", "")),
        )
        weight = float(specification["weight"])
        contribution = None
        if available:
            contribution = weight * float(normalized["value"])
            numerator += contribution
            available_weight += weight
        rows.append(
            {
                "id": component_id,
                "weight": weight,
                "uncertainty_class": specification["uncertainty_class"],
                **normalized,
                "weighted_contribution": contribution,
            }
        )
    trigger_config = config["trigger"]
    evaluable = available_weight >= float(trigger_config["minimum_available_weight"])
    score = None if not evaluable else numerator / available_weight
    contributors = [
        row
        for row in rows
        if row["available"]
        and float(row["value"]) >= float(trigger_config["component_threshold"])
    ]
    structural_contributors = [
        row for row in contributors if row["uncertainty_class"] == "structural_uncertainty"
    ]
    triggered = bool(
        evaluable
        and score is not None
        and score >= float(trigger_config["score_threshold"])
        and len(contributors) >= int(trigger_config["minimum_triggered_components"])
        and (
            not trigger_config["require_structural_component"]
            or bool(structural_contributors)
        )
    )
    uncertainty_classes: list[str] = []
    if any(row["id"] == "boundary_pressure" for row in contributors):
        uncertainty_classes.append("parameter_uncertainty")
    if structural_contributors or triggered:
        uncertainty_classes.append("structural_uncertainty")
    if missing_observables:
        uncertainty_classes.append("missing_observable")
    primary = (
        "missing_observable"
        if missing_observables
        else "structural_uncertainty"
        if triggered
        else "parameter_uncertainty"
        if uncertainty_classes
        else "none"
    )
    return {
        "evaluable": evaluable,
        "score": score,
        "available_weight": available_weight,
        "triggered": triggered,
        "triggered_component_ids": [row["id"] for row in contributors],
        "components": rows,
        "uncertainty": {
            "classes": uncertainty_classes,
            "primary": primary,
            "missing_observables": sorted(set(str(item) for item in missing_observables)),
        },
    }


def calibrate_clean_seeded_cases(config: Mapping[str, Any]) -> dict[str, Any]:
    clean = config["clean_seeded_calibration"]
    rng = np.random.default_rng(int(clean["seed"]))
    component_ids = [str(row["id"]) for row in config["components"]]
    maximum = float(clean["maximum_clean_component_value"])
    triggered = 0
    maximum_score = 0.0
    digests: list[str] = []
    for case_index in range(int(clean["case_count"])):
        values = rng.uniform(0.0, maximum, size=len(component_ids))
        signals = {
            component_id: _signal(
                value=float(value),
                available=True,
                provenance=f"seed={clean['seed']};case={case_index}",
                reason="clean_seeded_parameter_only_case",
            )
            for component_id, value in zip(component_ids, values, strict=True)
        }
        result = evaluate_surprise(signals, config)
        triggered += int(result["triggered"])
        maximum_score = max(maximum_score, float(result["score"] or 0.0))
        digests.append(canonical_digest(signals))
    rate = triggered / int(clean["case_count"])
    passed = rate <= float(clean["maximum_false_trigger_rate"])
    return {
        "schema_version": "sim2claw.sail_clean_surprise_calibration.v1",
        "seed": int(clean["seed"]),
        "case_count": int(clean["case_count"]),
        "trigger_count": triggered,
        "false_trigger_rate": rate,
        "maximum_false_trigger_rate": float(clean["maximum_false_trigger_rate"]),
        "maximum_observed_score": maximum_score,
        "case_digest": canonical_digest(digests),
        "passed": passed,
    }


def _bootstrap_estimate(residual: Mapping[str, Any], channel: str) -> Mapping[str, Any]:
    matches = [row for row in residual["bootstrap"]["estimates"] if row["channel"] == channel]
    if len(matches) != 1:
        raise StructuralSurpriseError(f"retained bootstrap channel changed: {channel}")
    return matches[0]


def derive_retained_signals(
    *,
    residual: Mapping[str, Any],
    graph: Mapping[str, Any],
    fidelity: Mapping[str, Any],
    grasp: Mapping[str, Any],
    rubber: Mapping[str, Any],
    config: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[str], dict[str, Any]]:
    validate_graph(graph)
    rules = config["retained_rules"]
    boundary = fidelity["boundary_disclosure"]
    if boundary["parameter"] != rules["load_absorber_parameter"]:
        raise StructuralSurpriseError("retained absorber parameter changed")
    boundary_value = 1.0 if boundary["selection_at_grid_boundary"] else 0.0
    pooled = fidelity["pooled_cross_validated_metrics"]
    consequence = fidelity["target_piece_consequence_comparison"]
    trace_improved = float(pooled["joint_rms_relative_improvement"]) >= float(
        rules["material_trace_improvement_fraction"]
    )
    lift_regressed = int(consequence["delta"]["lifted"]) < 0
    cross_family_value = 1.0 if trace_improved and lift_regressed else 0.0
    timing_channels = (
        "selected_event_timing:near_closed_crossing",
        "selected_event_timing:release_onset",
    )
    timing_estimates = [_bootstrap_estimate(residual, channel) for channel in timing_channels]
    maximum_lower = max(float(row["interval_lower"]) for row in timing_estimates)
    persistent_value = min(
        1.0, maximum_lower / float(rules["event_timing_material_seconds"])
    )
    rubber_candidate = rubber["frozen_full_set_candidate"]
    sim_trace_value = 1.0 if (
        rubber["decision"]["verified_partial_improvement"]
        and not rubber_candidate["trace_guard"]["pass"]
    ) else 0.0
    union_count = int(grasp["frozen_family_union"]["lift_and_transport"])
    single_counts = [
        int(candidate["summary"]["lift_and_transport"])
        for candidate in grasp["candidates"].values()
    ]
    single_best = max(single_counts)
    ensemble_value = 0.0 if union_count <= 0 else min(1.0, (union_count - single_best) / union_count)
    unavailable_reason = "requires_P1_06_structure_particle_posterior_not_zero"
    signals = {
        "boundary_pressure": _signal(
            value=boundary_value,
            available=True,
            provenance=f"{config['source_bindings']['fidelity_closeout']['sha256']}#boundary_disclosure",
            reason="selected_load_term_is_at_frozen_search_boundary",
        ),
        "cross_family_regression": _signal(
            value=cross_family_value,
            available=True,
            provenance=f"{config['source_bindings']['fidelity_closeout']['sha256']}#pooled_cross_validated_metrics,target_piece_consequence_comparison",
            reason="trace_RMS_improved_while_lift_count_regressed",
        ),
        "parameter_reversal_or_drift": _signal(
            value=None,
            available=False,
            provenance="P1_06_posterior_absent",
            reason=unavailable_reason,
        ),
        "phase_or_context_inconsistency": _signal(
            value=None,
            available=False,
            provenance="P1_06_phase_conditioned_posterior_absent",
            reason=unavailable_reason,
        ),
        "persistent_structured_residual": _signal(
            value=persistent_value,
            available=True,
            provenance=f"{config['source_bindings']['residual_field']['sha256']}#bootstrap:selected_event_timing",
            reason="event_timing_interval_lower_bound_exceeds_frozen_material_threshold",
        ),
        "posterior_correlation": _signal(
            value=None,
            available=False,
            provenance="P1_06_joint_posterior_absent",
            reason=unavailable_reason,
        ),
        "sim_success_trace_regression": _signal(
            value=sim_trace_value,
            available=True,
            provenance=f"{config['source_bindings']['rubber_closeout']['sha256']}#frozen_full_set_candidate,decision",
            reason="partial_simulator_outcome_improvement_with_EE_trace_guard_failure",
        ),
        "ensemble_without_single_winner": _signal(
            value=ensemble_value,
            available=True,
            provenance=f"{config['source_bindings']['grasp_closeout']['sha256']}#frozen_family_union,candidates,promotion_gate",
            reason="candidate_union_covers_more_transports_than_any_single_nonpromoted_candidate",
        ),
    }
    required_missing = set(rules["required_missing_observable_channels"])
    availability: dict[str, set[bool]] = {channel: set() for channel in required_missing}
    for sample in residual["samples"]:
        channel = str(sample["channel"])
        if channel in availability:
            availability[channel].add(bool(sample["available"]))
    missing = sorted(
        channel for channel, states in availability.items() if states == {False}
    )
    if set(missing) != required_missing:
        raise StructuralSurpriseError("retained missing-observable set changed")
    evidence = {
        "suspected_absorber": rules["load_absorber_parameter"],
        "absorber_interpretation": "historical parameter probably absorbing missing structure; no physical cause is identified",
        "selected_value": float(boundary["selected_value"]),
        "frozen_lower_bound": float(boundary["frozen_grid_lower_bound"]),
        "joint_rms_relative_improvement": float(pooled["joint_rms_relative_improvement"]),
        "lift_count_delta": int(consequence["delta"]["lifted"]),
        "maximum_event_timing_interval_lower_seconds": maximum_lower,
        "ensemble_transport_count": union_count,
        "best_single_candidate_transport_count": single_best,
        "rubber_partial_improvement": bool(rubber["decision"]["verified_partial_improvement"]),
        "rubber_trace_guard_pass": bool(rubber_candidate["trace_guard"]["pass"]),
        "graph_digest": graph["graph_digest"],
    }
    return signals, missing, evidence


def build_mechanism_request(
    diagnostic: Mapping[str, Any], config: Mapping[str, Any]
) -> dict[str, Any]:
    request_config = config["mechanism_request"]
    unsigned = {
        "schema_version": REQUEST_SCHEMA,
        "campaign_id": config["campaign_id"],
        "status": "requested" if diagnostic["triggered"] else "not_requested",
        "request_kind": request_config["request_kind"],
        "agent_allowed": False,
        "structural_surprise_digest": diagnostic["diagnostic_digest"],
        "suspected_absorber": diagnostic["evidence"]["suspected_absorber"],
        "suspected_absorber_wording": request_config["suspected_absorber_wording"],
        "candidate_families": list(request_config["candidate_families"]),
        "required_discriminating_observables": list(
            request_config["required_discriminating_observables"]
        ),
        "missing_observables": list(diagnostic["uncertainty"]["missing_observables"]),
        "rejection_conditions": [
            "proposal_asserts_a_physical_cause",
            "proposal_requires_imputed_missing_observation",
            "proposal_mutates_source_actions",
            "proposal_requests_training_or_policy_authority",
        ],
        "physical_cause_asserted": False,
        "mechanism_selected": False,
        "authority": copy.deepcopy(config["authority"]),
        "claim_boundary": "This deterministic packet requests bounded mechanism hypotheses and discriminating observables. It does not select a mechanism or identify a physical cause.",
    }
    return {**unsigned, "request_digest": canonical_digest(unsigned)}


def verify_mechanism_request(payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(payload))
    if normalized.get("schema_version") != REQUEST_SCHEMA:
        raise StructuralSurpriseError("unexpected mechanism-request schema")
    observed = normalized.pop("request_digest", None)
    if observed != canonical_digest(normalized):
        raise StructuralSurpriseError("mechanism-request digest mismatch")
    if (
        normalized.get("agent_allowed") is not False
        or normalized.get("physical_cause_asserted") is not False
        or normalized.get("mechanism_selected") is not False
    ):
        raise StructuralSurpriseError("mechanism request widened authority")
    authority = normalized.get("authority")
    if not isinstance(authority, dict) or any(authority.values()):
        raise StructuralSurpriseError("mechanism request widened campaign authority")
    return {**normalized, "request_digest": str(observed)}


def verify_surprise_artifact(payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(payload))
    if normalized.get("schema_version") != DIAGNOSTIC_SCHEMA:
        raise StructuralSurpriseError("unexpected structural-surprise artifact schema")
    observed = normalized.pop("diagnostic_digest", None)
    if observed != canonical_digest(normalized):
        raise StructuralSurpriseError("structural-surprise artifact digest mismatch")
    authority = normalized.get("authority")
    if not isinstance(authority, dict) or any(authority.values()):
        raise StructuralSurpriseError("structural-surprise artifact widened authority")
    if normalized.get("physical_cause_asserted") is not False:
        raise StructuralSurpriseError("structural-surprise artifact asserted a cause")
    return {**normalized, "diagnostic_digest": str(observed)}


def verify_surprise_receipt(
    receipt: Mapping[str, Any], *, output_root: Path, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(receipt))
    if normalized.get("schema_version") != RECEIPT_SCHEMA:
        raise StructuralSurpriseError("unexpected structural-surprise receipt schema")
    observed = normalized.pop("receipt_digest", None)
    if observed != canonical_digest(normalized):
        raise StructuralSurpriseError("structural-surprise receipt digest mismatch")
    authority = normalized.get("authority")
    if not isinstance(authority, dict) or any(authority.values()):
        raise StructuralSurpriseError("structural-surprise receipt widened authority")
    config_binding = normalized.get("config") or {}
    config_path = repo_root / str(config_binding.get("path", ""))
    if not config_path.is_file() or sha256_file(config_path) != config_binding.get("sha256"):
        raise StructuralSurpriseError("structural-surprise receipt config changed")
    for relative_path, expected_sha256 in (normalized.get("compiler_sha256") or {}).items():
        path = repo_root / str(relative_path)
        if not path.is_file() or sha256_file(path) != expected_sha256:
            raise StructuralSurpriseError(f"structural-surprise compiler changed: {relative_path}")
    for name, binding in (normalized.get("outputs") or {}).items():
        path = output_root / str(binding.get("path", ""))
        if not path.is_file() or sha256_file(path) != binding.get("sha256"):
            raise StructuralSurpriseError(f"structural-surprise output changed: {name}")
    return {**normalized, "receipt_digest": str(observed)}


def compile_structural_surprise(
    config_path: Path,
    *,
    output_root: Path,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    config = load_surprise_config(config_path, repo_root=repo_root)
    resolved_config = config_path if config_path.is_absolute() else repo_root / config_path
    paths = {
        name: verify_source_binding(binding, repo_root=repo_root)
        for name, binding in config["source_bindings"].items()
    }
    residual_receipt = load_json_object(paths["residual_receipt"], label="residual receipt")
    verify_residual_receipt(
        residual_receipt,
        output_root=paths["residual_receipt"].parent,
        repo_root=repo_root,
    )
    residual = verify_contract(load_json_object(paths["residual_field"], label="residual field"))
    graph = validate_graph(load_json_object(paths["belief_graph"], label="belief graph"))
    belief_receipt = load_json_object(paths["belief_receipt"], label="belief receipt")
    normalized_belief_receipt = copy.deepcopy(belief_receipt)
    observed_belief_digest = normalized_belief_receipt.pop("receipt_digest", None)
    if observed_belief_digest != canonical_digest(normalized_belief_receipt):
        raise StructuralSurpriseError("belief receipt digest changed")
    fidelity = load_json_object(paths["fidelity_closeout"], label="fidelity closeout")
    grasp = load_json_object(paths["grasp_closeout"], label="grasp closeout")
    rubber = load_json_object(paths["rubber_closeout"], label="rubber closeout")
    for payload in (fidelity, grasp, rubber):
        _verify_generic_receipt(payload)
    registry = load_json_object(paths["golden_registry"], label="golden registry")
    gold_05 = [row for row in registry["cases"] if row["id"] == "GOLD-05"]
    if len(gold_05) != 1 or gold_05[0]["expected"] != "structural_surprise":
        raise StructuralSurpriseError("GOLD-05 registry changed")
    signals, missing, evidence = derive_retained_signals(
        residual=residual,
        graph=graph,
        fidelity=fidelity,
        grasp=grasp,
        rubber=rubber,
        config=config,
    )
    evaluated = evaluate_surprise(signals, config, missing_observables=missing)
    unsigned_diagnostic = {
        "schema_version": DIAGNOSTIC_SCHEMA,
        "campaign_id": config["campaign_id"],
        "generated_at": config["generated_at"],
        **evaluated,
        "evidence": evidence,
        "probable_absorption_not_cause": True,
        "physical_cause_asserted": False,
        "golden_case": {"id": "GOLD-05", "expected": "structural_surprise", "passed": bool(evaluated["triggered"])},
        "authority": copy.deepcopy(config["authority"]),
        "claim_boundary": "Compensation debt is a structure-search trigger. It is not evidence that the named historical parameter is physically wrong or that any proposed mechanism is the cause.",
    }
    diagnostic = {
        **unsigned_diagnostic,
        "diagnostic_digest": canonical_digest(unsigned_diagnostic),
    }
    verify_surprise_artifact(diagnostic)
    request = build_mechanism_request(diagnostic, config)
    verify_mechanism_request(request)
    clean = calibrate_clean_seeded_cases(config)
    if not clean["passed"]:
        raise StructuralSurpriseError("clean seeded false-trigger ceiling exceeded")
    if not diagnostic["triggered"]:
        raise StructuralSurpriseError("retained structural-surprise trigger did not fire")
    output_root.mkdir(parents=True, exist_ok=True)
    diagnostic_path = output_root / "structural_surprise.json"
    request_path = output_root / "mechanism_request.json"
    clean_path = output_root / "clean_seeded_calibration.json"
    atomic_write_json(diagnostic_path, diagnostic)
    atomic_write_json(request_path, request)
    atomic_write_json(clean_path, clean)
    outputs = {
        "structural_surprise": {"path": diagnostic_path.name, "sha256": sha256_file(diagnostic_path)},
        "mechanism_request": {"path": request_path.name, "sha256": sha256_file(request_path)},
        "clean_seeded_calibration": {"path": clean_path.name, "sha256": sha256_file(clean_path)},
    }
    code_path = "src/sim2claw/sail/structural_surprise.py"
    unsigned_receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "campaign_id": config["campaign_id"],
        "generated_at": config["generated_at"],
        "config": {"path": resolved_config.resolve().relative_to(repo_root.resolve()).as_posix(), "sha256": sha256_file(resolved_config)},
        "compiler_sha256": {code_path: sha256_file(repo_root / code_path)},
        "source_sha256": {name: binding["sha256"] for name, binding in sorted(config["source_bindings"].items())},
        "outputs": outputs,
        "result": {
            "triggered": diagnostic["triggered"],
            "score": diagnostic["score"],
            "available_weight": diagnostic["available_weight"],
            "triggered_component_ids": diagnostic["triggered_component_ids"],
            "primary_uncertainty": diagnostic["uncertainty"]["primary"],
            "clean_false_trigger_rate": clean["false_trigger_rate"],
            "gold_05_passed": diagnostic["golden_case"]["passed"],
        },
        "regeneration_command": "uv run sim2claw sail-compile-structural-surprise --config configs/sail/structural_surprise_retired_bg_v1.json --output outputs/sail/retired-bg-v1/structural-surprise",
        "authority": copy.deepcopy(config["authority"]),
        "claim_boundary": diagnostic["claim_boundary"],
    }
    receipt = {**unsigned_receipt, "receipt_digest": canonical_digest(unsigned_receipt)}
    receipt_path = output_root / "receipt.json"
    atomic_write_json(receipt_path, receipt)
    verify_surprise_receipt(receipt, output_root=output_root, repo_root=repo_root)
    return {
        "schema_version": "sim2claw.sail_structural_surprise_compile_result.v1",
        "campaign_id": config["campaign_id"],
        "status": "compiled",
        "triggered": diagnostic["triggered"],
        "score": diagnostic["score"],
        "primary_uncertainty": diagnostic["uncertainty"]["primary"],
        "diagnostic_sha256": sha256_file(diagnostic_path),
        "diagnostic_digest": diagnostic["diagnostic_digest"],
        "mechanism_request_sha256": sha256_file(request_path),
        "receipt_sha256": sha256_file(receipt_path),
        "receipt_digest": receipt["receipt_digest"],
        "clean_false_trigger_rate": clean["false_trigger_rate"],
        "output_root": str(output_root),
        "training_admitted": False,
        "physical_authority": False,
    }


__all__ = [
    "StructuralSurpriseError",
    "build_mechanism_request",
    "calibrate_clean_seeded_cases",
    "compile_structural_surprise",
    "derive_retained_signals",
    "evaluate_surprise",
    "load_surprise_config",
    "verify_surprise_artifact",
    "verify_mechanism_request",
    "verify_surprise_receipt",
]

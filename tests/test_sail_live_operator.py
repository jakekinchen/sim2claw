from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sim2claw.learning_factory_artifacts import canonical_digest, sha256_file
from sim2claw.sail.live_operator import (
    LiveOperatorError,
    apply_live_sparse_closure,
    load_live_campaign_contract,
    run_live_operator,
    update_discrete_structure_posterior,
    validate_observed_intervention_result,
)
from sim2claw.sail.loop_closure import LoopClosureError
from sim2claw.sail.posterior import PosteriorError


ACTION_SHA = "a" * 64


def _write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def _binding(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": sha256_file(path)}


def _mechanism(
    mechanism_id: str,
    family: str,
    required: list[str],
    intervention_ids: list[str],
    factor_ids: list[str],
) -> dict:
    return {
        "mechanism_id": mechanism_id,
        "family": family,
        "physical_interpretation": f"bounded hypothesis {mechanism_id}",
        "affected_components": ["retained_subject"],
        "parameters": [
            {
                "name": "gain",
                "unit": "normalized",
                "prior": {"mean": 0.5},
                "minimum": 0.0,
                "maximum": 1.0,
            }
        ],
        "predicted_residual_signatures": [{"id": "declared_before_result"}],
        "required_observables": required,
        "non_identifiabilities": ["requires discriminating observation"],
        "candidate_interventions": intervention_ids,
        "simulator_mutation": "config_bound_mutation_only",
        "graph_factors": factor_ids,
        "influence_edges": [],
        "invalidation_rules": ["opposite preregistered signature observed"],
        "invariance_scope": {
            "invariant_parameters": ["gain"],
            "allowed_context_covariates": ["episode_context"],
        },
        "action_immutability_tests": ["source_action_sha256_equal"],
        "prediction_model": {"kind": "linear", "features": ["feature"]},
    }


def _campaign(tmp_path: Path) -> tuple[Path, dict]:
    action = _write(
        tmp_path / "action.json",
        {"action": {"sha256": ACTION_SHA, "byte_identical": True}},
    )
    evaluator = _write(tmp_path / "evaluator.json", {"id": "eval:any-id", "sealed": True})
    residual = _write(tmp_path / "residual.json", {"id": "residual:any-id"})

    receipts = tmp_path / "manual"
    _write(
        receipts / "one" / "anchor-screen-receipt.json",
        {
            "campaign_id": "manual-one",
            "candidate_count": 2,
            "anchor_pass_count": 0,
            "action_array_sha256": ACTION_SHA,
            "all_actions_byte_identical": True,
        },
    )
    _write(
        receipts / "two" / "anchor-screen-receipt.json",
        {
            "campaign_id": "manual-two",
            "candidate_count": 1,
            "anchor_pass_count": 0,
            "action_array_sha256": ACTION_SHA,
            "all_actions_byte_identical": True,
        },
    )
    incomplete = _write(tmp_path / "incomplete" / "candidate.json", {"status": "wip"})

    flex = "flexural-mechanism-arbitrary"
    actuator = "actuator-path-mechanism-arbitrary"
    simulator_probe = "probe-simulator-arbitrary"
    measurement_probe = "probe-measurement-arbitrary"
    factors = ["residual:contact", "residual:aperture"]
    components = [
        {"id": "persistent_structured_residual", "weight": 0.5, "uncertainty_class": "structural_uncertainty"},
        {"id": "ensemble_without_single_winner", "weight": 0.5, "uncertainty_class": "structural_uncertainty"},
    ]
    config = {
        "schema_version": "sim2claw.sail_live_campaign.v1",
        "campaign_id": "campaign-with-no-python-registration",
        "created_at": "2026-07-22T12:00:00-05:00",
        "subject": {
            "workcell_id": "workcell:any",
            "session_id": "session:any",
            "context_id": "context:any",
            "label": "generic retained subject",
        },
        "source_bindings": {
            "action": _binding(action),
            "evaluator": _binding(evaluator),
            "residual": _binding(residual),
        },
        "action_identity": {
            "source_binding": "action",
            "sha256_pointer": "/action/sha256",
            "byte_identical_pointer": "/action/byte_identical",
            "sha256": ACTION_SHA,
        },
        "evaluator": {
            "evaluator_id": "independent-evaluator-any",
            "owner": "independent_cpu_fp32_evaluator",
            "source_bindings": ["evaluator"],
            "release_index": 401,
        },
        "proof_boundary": {
            "proof_class": "retained_simulator_fixture",
            "physical_authority": False,
            "training_admitted": False,
            "agent_can_promote": False,
            "simulator_can_promote": False,
            "operator_can_promote": False,
        },
        "budget": {
            "maximum_interventions": 1,
            "maximum_anchor_replays": 18,
            "used_interventions": 0,
            "used_anchor_replays": 0,
        },
        "residual_evidence": [
            {
                "residual_id": "residual:contact",
                "label": "contact retention",
                "value": 1.0,
                "available": True,
                "source_binding": "residual",
                "provenance": "sealed retained trace",
            },
            {
                "residual_id": "residual:aperture",
                "label": "loaded aperture",
                "value": 0.9,
                "available": True,
                "source_binding": "residual",
                "provenance": "sealed retained trace",
            },
        ],
        "structural_surprise": {
            "components": components,
            "signals": {
                "persistent_structured_residual": {
                    "value": 1.0,
                    "available": True,
                    "provenance": "manual families remain terminal negative",
                    "reason": "persistent residual",
                },
                "ensemble_without_single_winner": {
                    "value": 1.0,
                    "available": True,
                    "provenance": "two retained structures",
                    "reason": "non-identifying evidence",
                },
            },
            "trigger": {
                "score_threshold": 0.6,
                "component_threshold": 0.6,
                "minimum_triggered_components": 2,
                "minimum_available_weight": 0.5,
                "require_structural_component": True,
                "missing_components_are_zero": False,
            },
        },
        "observables": [
            {"observable_id": "joint_angle", "unit": "rad", "available": True},
            {"observable_id": "joint_current", "unit": "ampere", "available": True},
            {"observable_id": "jaw_force", "unit": "newton", "available": False},
            {"observable_id": "rubber_profile", "unit": "millimeter", "available": False},
        ],
        "mechanisms": [
            {"prior_probability": 0.5, **_mechanism(flex, "fingertip_contact", ["jaw_force", "rubber_profile"], [simulator_probe, measurement_probe], factors)},
            {"prior_probability": 0.5, **_mechanism(actuator, "load_compliance", ["joint_angle", "joint_current", "jaw_force"], [simulator_probe, measurement_probe], factors)},
        ],
        "interventions": [
            {
                "intervention_id": simulator_probe,
                "kind": "simulator_family",
                "availability": "available_simulator",
                "allowed_mutations": ["declared simulator factor"],
                "required_observables": ["joint_angle", "joint_current"],
                "declared_scopes": ["fingertip_contact", "load_compliance"],
                "residual_node_ids": factors,
                "maximum_trials": 18,
                "cost": 0.5,
                "risk": 0.3,
                "gate_relevance": 0.5,
                "compensation_debt_reduction": 0.3,
                "parameter_information_gain": 0.2,
                "predicted_signatures": {
                    flex: {"contact_response": {"normalized_response": 0.55}},
                    actuator: {"contact_response": {"normalized_response": 0.45}},
                },
            },
            {
                "intervention_id": measurement_probe,
                "kind": "measurement_acquisition",
                "availability": "unavailable_measurement",
                "allowed_mutations": [],
                "required_observables": ["jaw_force", "rubber_profile", "joint_angle", "joint_current"],
                "declared_scopes": ["fingertip_contact", "load_compliance"],
                "residual_node_ids": factors,
                "maximum_trials": 0,
                "cost": 0.1,
                "risk": 0.0,
                "gate_relevance": 1.0,
                "compensation_debt_reduction": 1.0,
                "parameter_information_gain": 1.0,
                "predicted_signatures": {
                    flex: {"force_deformation_coupling": {"normalized_response": 0.95}},
                    actuator: {"force_deformation_coupling": {"normalized_response": 0.05}},
                },
            },
        ],
        "acquisition": {
            "weights": {
                "predicted_information_gain": 0.6,
                "compensation_debt_reduction": 0.2,
                "gate_relevance": 0.2,
                "cost": -0.05,
                "risk": -0.05,
            },
            "minimum_predicted_information_gain": 0.5,
        },
        "factor_beliefs": [
            {"factor_id": "factor:contact_patch", "value": 0.5, "status": "retained", "affected_by_mechanisms": [flex]},
            {"factor_id": "factor:actuator_path", "value": 0.5, "status": "retained", "affected_by_mechanisms": [actuator]},
            {"factor_id": "factor:arm_tracking", "value": 0.0, "status": "unaffected_frozen", "affected_by_mechanisms": []},
        ],
        "influence_thresholds": {
            "require_declared_scope": True,
            "require_predicts_path": True,
            "minimum_residual_overlap": 1,
            "minimum_local_sensitivity": 0.5,
            "minimum_precision": 0.0,
            "minimum_recall": 0.0,
        },
        "invariance": {
            "mechanism_id": flex,
            "invariant_parameter": "gain",
            "context_covariate": "episode_context",
            "episode_contexts": [{"episode_id": "retained:any", "level": "single"}],
            "thresholds": {
                "minimum_context_levels": 2,
                "minimum_episodes_per_level": 1,
                "maximum_invariant_parameter_range": 0.1,
                "minimum_residual_signature_consistency": 0.9,
            },
        },
        "ablation": {
            "manual_receipt_glob": str(receipts / "*" / "anchor-screen-receipt.json"),
            "incomplete_artifact_glob": str(incomplete.parent / "*.json"),
            "expected_completed_campaigns": 2,
            "expected_candidate_replays": 3,
            "expected_anchor_passes": 0,
            "manual_hypotheses_rejected_or_narrowed": ["scalar friction alone"],
            "manual_hypotheses_retained": [flex, actuator],
        },
        "measurement_acquisition_packet": {
            "measurements": ["jaw_force", "rubber_profile", "joint_angle", "joint_current"],
            "minimum_sampling_hz": 100,
            "calibration": ["zero force before each trial", "known-gap blocked closures"],
            "synchronization": "one monotonic timestamp domain",
            "robot_motion_authority": False,
        },
        "authority": {
            "physical_capture": False,
            "robot_motion": False,
            "training": False,
            "self_promotion": False,
        },
    }
    config_path = _write(tmp_path / "campaign.json", config)
    return config_path, config


def test_generic_campaign_ids_need_no_python_registration(tmp_path: Path) -> None:
    path, config = _campaign(tmp_path)
    contract = load_live_campaign_contract(path)
    assert contract.campaign_id == config["campaign_id"]
    assert {row.mechanism_id for row in contract.mechanisms} == {
        "flexural-mechanism-arbitrary",
        "actuator-path-mechanism-arbitrary",
    }


def test_action_and_source_drift_fail_closed(tmp_path: Path) -> None:
    path, config = _campaign(tmp_path)
    changed = copy.deepcopy(config)
    changed["action_identity"]["sha256"] = "b" * 64
    changed_path = _write(tmp_path / "changed-action.json", changed)
    with pytest.raises(LiveOperatorError, match="action identity"):
        load_live_campaign_contract(changed_path)

    evaluator_path = Path(config["source_bindings"]["evaluator"]["path"])
    evaluator_path.write_text("drift\n")
    with pytest.raises(LiveOperatorError, match="source"):
        load_live_campaign_contract(path)


def test_invalid_posterior_updates_fail_closed() -> None:
    prior = {
        "one": 0.5,
        "two": 0.5,
    }
    with pytest.raises(PosteriorError, match="hypothesis set"):
        update_discrete_structure_posterior(prior, likelihoods={"one": 1.0})
    with pytest.raises(PosteriorError, match="likelihood"):
        update_discrete_structure_posterior(
            prior, likelihoods={"one": -1.0, "two": 1.0}
        )


def test_sparse_closure_rejects_unaffected_factor_mutation() -> None:
    before = [
        {"factor_id": "affected", "value": 0.5, "status": "retained"},
        {"factor_id": "frozen", "value": 0.0, "status": "unaffected_frozen"},
    ]
    with pytest.raises(LoopClosureError, match="unaffected"):
        apply_live_sparse_closure(
            before_factors=before,
            affected_factor_ids=["affected"],
            updates={"affected": 0.7, "frozen": 0.2},
            observation_opened=True,
            action_identity={"sha256": ACTION_SHA},
            evidence_identity={"sha256": "b" * 64},
        )


def test_result_cannot_expand_family_escape_budget_or_self_promote(tmp_path: Path) -> None:
    path, _ = _campaign(tmp_path)
    contract = load_live_campaign_contract(path)
    base = {
        "schema_version": "sim2claw.sail_live_intervention_result.v1",
        "campaign_id": contract.campaign_id,
        "intervention_id": "probe-simulator-arbitrary",
        "frozen_intervention_set_digest": contract.intervention_set_digest,
        "action_sha256": ACTION_SHA,
        "evaluator_digest": contract.evaluator_digest,
        "anchor_replays": 1,
        "hypothesis_likelihoods": {
            "flexural-mechanism-arbitrary": 0.8,
            "actuator-path-mechanism-arbitrary": 0.2,
        },
        "factor_updates": {"factor:contact_patch": 0.8},
        "consequence": {"evaluator_passed": False},
        "promotion": {"promoted": False, "requested_by": None},
    }
    expanded = {**base, "frozen_intervention_set_digest": "c" * 64}
    with pytest.raises(LiveOperatorError, match="expanded"):
        validate_observed_intervention_result(contract, expanded)
    evaluator_drift = {**base, "evaluator_digest": "d" * 64}
    with pytest.raises(LiveOperatorError, match="evaluator drift"):
        validate_observed_intervention_result(contract, evaluator_drift)
    escaped = {**base, "anchor_replays": 19}
    with pytest.raises(LiveOperatorError, match="budget"):
        validate_observed_intervention_result(contract, escaped)
    promoted = copy.deepcopy(base)
    promoted["promotion"] = {"promoted": True, "requested_by": "agent"}
    with pytest.raises(LiveOperatorError, match="promotion"):
        validate_observed_intervention_result(contract, promoted)


def test_end_to_end_operator_abstains_for_missing_discriminating_measurement(
    tmp_path: Path,
) -> None:
    path, _ = _campaign(tmp_path)
    output_root = tmp_path / "output"
    result = run_live_operator(path, output_root=output_root)
    assert result["verdict"] == "abstain_measurement_acquisition_required"
    assert result["selected_intervention"] == "probe-measurement-arbitrary"
    assert result["budget"]["used_interventions"] == 0
    assert result["budget"]["used_anchor_replays"] == 0
    trace = json.loads((output_root / "operator_trace.json").read_text())
    assert trace["stages"][0]["stage"] == "residual_evidence"
    assert trace["stages"][-1]["stage"] == "terminal_verdict"
    ablation = json.loads((output_root / "ablation.json").read_text())
    assert ablation["manual"]["completed_campaigns"] == 2
    assert ablation["manual"]["simulator_evaluations"] == 3
    assert ablation["manual"]["incomplete_work_in_progress"]["artifact_count"] == 1
    assert not ablation["manual"]["incomplete_work_in_progress"]["included_in_completed_counts"]
    assert ablation["sail"]["simulator_evaluations"] == 0
    receipt = json.loads((output_root / "receipt.json").read_text())
    unsigned = {key: value for key, value in receipt.items() if key != "receipt_digest"}
    assert receipt["receipt_digest"] == canonical_digest(unsigned)


def test_static_publication_is_read_only_and_matches_terminal_receipt() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    web_root = repo_root / "src" / "sim2claw" / "studio_web"
    manifest = json.loads(
        (web_root / "publication" / "sail_live_operator_v1" / "manifest.json").read_text()
    )
    assert manifest["verdict"] == "abstain_measurement_acquisition_required"
    assert manifest["action_sha256"] == "402a29e4cdc0c4cb90d41a83327ad8df5685544851b4e4d659129b3239744fd6"
    assert manifest["ablation"]["manual"] == {
        "completed_campaigns": 32,
        "simulator_evaluations": 514,
        "anchor_passes": 0,
        "abstention_quality": "no_global_abstention_incomplete_family_interrupted",
    }
    assert not any(
        value for key, value in manifest["authority"].items() if key != "read_only"
    )
    assert manifest["authority"]["read_only"]
    html = (web_root / "live-operator.html").read_text()
    script = (web_root / "live-operator.js").read_text()
    assert "read-only · no authority" in html
    assert "<button" not in html
    assert 'method: "POST"' not in script
    publication_receipt = json.loads(
        (web_root / "publication" / "sail_live_operator_v1" / "receipt.json").read_text()
    )
    assert publication_receipt["route"] == "/live-operator.html"
    assert publication_receipt["authority"]["read_only"]
    assert not publication_receipt["authority"]["physical_authority"]
    for relative, expected in publication_receipt["files"].items():
        assert sha256_file(repo_root / relative) == expected

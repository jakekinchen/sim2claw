"""Transactional orchestration for one SAIL live-operator decision pass."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping

from ..learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .contracts import REPO_ROOT
from .influence import discover_influence_set
from .live_adapters import execute_trusted_adapter_request
from .live_contracts import load_live_campaign_contract
from .live_decision import (
    apply_live_sparse_closure,
    build_live_belief_graph,
    build_manual_ablation,
    evaluate_live_invariance,
    rank_live_acquisition,
    update_discrete_structure_posterior,
)
from .live_evidence import verify_measurement_evaluator_receipt
from .live_receipts import (
    COMPILER_PATHS,
    _sealed_measurement_packet,
    _validate_admitted_result,
    _verify_live_operator_receipt,
    build_live_evaluator_identity,
    verify_live_operator_receipt,
)
from .live_state import (
    EvidenceAdmissionError,
    _relative_config_path,
    commit_prepared_state,
    json_artifact_sha256,
    locked_campaign_state,
    prepare_admitted_result,
    resolve_live_campaign_state_path,
)
from .live_types import RECEIPT_SCHEMA, LiveCampaignContract, LiveOperatorError
from .structural_surprise import evaluate_surprise


def run_live_operator(
    config_path: Path,
    *,
    output_root: Path,
    measurement_evaluator_receipt_path: Path | None = None,
    trusted_adapter_request_path: Path | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Run the decision plane and optionally admit one independent evaluator receipt."""

    if (
        measurement_evaluator_receipt_path is not None
        and trusted_adapter_request_path is not None
    ):
        raise LiveOperatorError("only one independent evidence request may be opened")
    contract = load_live_campaign_contract(config_path, repo_root=repo_root)
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
            measurement_evaluator_receipt_path=measurement_evaluator_receipt_path,
            trusted_adapter_request_path=trusted_adapter_request_path,
            repo_root=repo_root,
        )


def _run_live_operator_locked(
    contract: LiveCampaignContract,
    *,
    output_root: Path,
    state_path: Path,
    state: Mapping[str, Any],
    measurement_evaluator_receipt_path: Path | None,
    trusted_adapter_request_path: Path | None,
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
        if measurement_evaluator_receipt_path is not None:
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
        elif trusted_adapter_request_path is not None:
            if (
                selected_contract.kind != "simulator_family"
                or selected_contract.availability != "available_simulator"
            ):
                raise LiveOperatorError(
                    "trusted adapter request does not target an available selected simulator intervention"
                )
            remaining_interventions = int(
                state["budget"]["maximum_interventions"]
            ) - int(state["budget"]["used_interventions"])
            remaining_anchor_replays = int(
                state["budget"]["maximum_anchor_replays"]
            ) - int(state["budget"]["used_anchor_replays"])
            minimum_separation = float(
                config["acquisition"]["minimum_predicted_signature_separation"]
            )
            if (
                remaining_interventions > 0
                and remaining_anchor_replays > 0
                and float(selected["predicted_signature_separation"])
                >= minimum_separation
            ):
                admission = execute_trusted_adapter_request(
                    trusted_adapter_request_path,
                    contract=contract,
                    selected_intervention=selected_contract.payload,
                    affected_factor_ids=affected_factor_ids,
                    expected_evaluator_identity=expected_evaluator,
                    remaining_anchor_replays=remaining_anchor_replays,
                    prior_execution_ids=[
                        str(event["execution_id"]) for event in state["events"]
                    ],
                    prior_anchor_replay_ids=[
                        str(replay_id)
                        for event in state["events"]
                        for replay_id in event.get("anchor_replay_ids") or []
                    ],
                    output_root=output_root / "trusted_adapter",
                    repo_root=repo_root,
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
        selected_budget_exhausted = (
            selected_contract.kind == "simulator_family"
            and int(budget["used_anchor_replays"])
            >= int(budget["maximum_anchor_replays"])
        ) or (
            selected_contract.kind == "measurement_acquisition"
            and int(budget["used_measurement_trials"])
            >= int(budget["maximum_measurement_trials"])
        )
        if (
            int(budget["used_interventions"])
            >= int(budget["maximum_interventions"])
            or selected_budget_exhausted
        ):
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
    invariance = evaluate_live_invariance(contract)
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
    manual = build_manual_ablation(contract)
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
    intervention_executor_implemented = bool(
        admission is not None
        and admission["lane"] == "trusted_simulator_adapter"
    )
    trace_unsigned = {
        "schema_version": "sim2claw.sail_live_operator_trace.v1",
        "campaign_id": contract.campaign_id,
        "stages": stages,
        "source_action_bytes_unchanged": True,
        "evaluator_changed": False,
        "agent_promoted": False,
        "training_admitted": False,
        "physical_authority": False,
        "intervention_executor_implemented": intervention_executor_implemented,
        "independent_evaluator_receipt_required": True,
    }
    if admission is not None and admission["lane"] == "trusted_simulator_adapter":
        trace_unsigned["trusted_simulator_adapter_executed"] = True
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
        if admission["lane"] == "trusted_simulator_adapter":
            artifacts["admitted_evaluator_receipt"].update(
                {
                    "adapter_id": admission["adapter_id"],
                    "adapter_identity": admission["adapter_identity"],
                    "adapter_receipt": admission["receipt"],
                }
            )
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
        "compiler_sha256": {path: sha256_file(repo_root / path) for path in COMPILER_PATHS},
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
        "intervention_executor_implemented": intervention_executor_implemented,
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


__all__ = ["run_live_operator"]

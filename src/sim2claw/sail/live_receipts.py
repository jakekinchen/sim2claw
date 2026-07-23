"""Compiler identities, evidence packets, and read-time receipt verification."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..learning_factory_artifacts import canonical_digest, sha256_file
from .contracts import REPO_ROOT
from .importers import load_json_object
from .live_adapters import verify_embedded_trusted_adapter_receipt
from .live_contracts import load_live_campaign_contract
from .live_decision import update_discrete_structure_posterior
from .live_evidence import EvidenceAdmissionError, evaluator_identity
from .live_state import (
    _relative_config_path,
    _resolve_repo_relative_path,
    json_artifact_sha256,
    resolve_live_campaign_state_path,
    validate_campaign_state,
)
from .live_types import RECEIPT_SCHEMA, LiveCampaignContract, LiveOperatorError


COMPILER_PATHS = (
    "src/sim2claw/sail/live_operator.py",
    "src/sim2claw/sail/live_adapters.py",
    "src/sim2claw/sail/live_types.py",
    "src/sim2claw/sail/live_contracts.py",
    "src/sim2claw/sail/live_decision.py",
    "src/sim2claw/sail/live_state.py",
    "src/sim2claw/sail/live_receipts.py",
    "src/sim2claw/sail/live_runtime.py",
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
MIGRATION_SCHEMA = "sim2claw.sail_live_operator_migration_receipt.v1"


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
        compiler_sha256={path: sha256_file(repo_root / path) for path in COMPILER_PATHS},
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
        path: sha256_file(repo_root / path) for path in COMPILER_PATHS
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
        lane = admitted.get("lane")
        if lane not in {"offline_measurement", "trusted_simulator_adapter"}:
            raise LiveOperatorError("untrusted evaluator receipt admission is disabled")
        summary = loaded_outputs["admitted_evaluator_receipt"]
        if (
            summary.get("lane") != lane
            or summary.get("execution_id") != admitted.get("execution_id")
            or summary.get("receipt_sha256") != admitted.get("receipt_sha256")
            or summary.get("receipt_digest") != admitted.get("receipt_digest")
            or summary.get("promotion") is not False
            or summary.get("physical_authority") is not False
        ):
            raise LiveOperatorError("live operator admitted receipt fields changed")
        if lane == "trusted_simulator_adapter":
            influence_results = loaded_outputs["influence"].get("results") or []
            affected_mechanisms = {
                str(row.get("mechanism_id"))
                for row in influence_results
                if receipt["selected_intervention"]
                in (row.get("affected_intervention_ids") or [])
            }
            affected_factor_ids = sorted(
                str(row["factor_id"])
                for row in contract.payload["factor_beliefs"]
                if affected_mechanisms
                & {
                    str(value)
                    for value in row.get("affected_by_mechanisms") or []
                }
            )
            verify_embedded_trusted_adapter_receipt(
                summary,
                contract=contract,
                expected_evaluator_identity=receipt["evaluator_identity"],
                expected_consequence=consequence,
                expected_affected_factor_ids=affected_factor_ids,
                receipt_root=receipt_path.resolve().parent,
                repo_root=repo_root,
            )
            if trace.get("trusted_simulator_adapter_executed") is not True:
                raise LiveOperatorError("trusted simulator execution is absent from trace")
        elif any(
            field in summary
            for field in ("adapter_id", "adapter_identity", "adapter_receipt")
        ):
            raise LiveOperatorError("measurement summary contains adapter evidence")
        if not state["events"]:
            raise LiveOperatorError("admitted receipt is absent from campaign state")
        event = state["events"][-1]
        if (
            event.get("lane") != lane
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


def verify_live_operator_migration_receipt(
    migration_path: Path, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Verify the explicit v2-to-v3 modularization compatibility receipt."""

    payload = load_json_object(migration_path, label="live operator migration receipt")
    expected_fields = {
        "schema_version",
        "migration_id",
        "from_receipt",
        "to_receipt",
        "output_sha256",
        "changed_receipt_fields",
        "api_changes",
        "proof_boundary",
        "reproduction_command",
        "migration_digest",
    }
    if set(payload) != expected_fields or payload.get("schema_version") != MIGRATION_SCHEMA:
        raise LiveOperatorError("live operator migration receipt field set changed")
    unsigned = copy.deepcopy(payload)
    observed_digest = unsigned.pop("migration_digest")
    if observed_digest != canonical_digest(unsigned):
        raise LiveOperatorError("live operator migration receipt digest mismatch")
    old = payload.get("from_receipt") or {}
    new = payload.get("to_receipt") or {}
    receipt_fields = {
        "schema_version",
        "receipt_sha256",
        "receipt_digest",
        "compiler_digest",
    }
    if set(old) != receipt_fields or set(new) != receipt_fields:
        raise LiveOperatorError("live operator migration receipt identity changed")
    if (
        old.get("schema_version") != "sim2claw.sail_live_operator_receipt.v2"
        or new.get("schema_version") != RECEIPT_SCHEMA
    ):
        raise LiveOperatorError("live operator migration schema transition changed")
    current_compiler = {
        path: sha256_file(repo_root / path) for path in COMPILER_PATHS
    }
    if new.get("compiler_digest") != canonical_digest(current_compiler):
        raise LiveOperatorError("live operator migration compiler identity is stale")
    outputs = payload.get("output_sha256") or {}
    if set(outputs) != {"before", "after"} or not outputs.get("before"):
        raise LiveOperatorError("live operator migration output evidence is incomplete")
    if outputs["before"] != outputs["after"]:
        raise LiveOperatorError("live operator modularization changed retained outputs")
    if payload.get("changed_receipt_fields") != [
        "compiler_sha256",
        "evaluator_identity",
        "receipt_digest",
        "schema_version",
    ]:
        raise LiveOperatorError("live operator migration change set widened")
    if payload.get("api_changes") != [
        "removed_disabled_simulator_evaluator_receipt_path",
        "added_result_free_trusted_adapter_request_path",
    ]:
        raise LiveOperatorError("live operator migration API change set changed")
    proof = payload.get("proof_boundary") or {}
    if set(proof) != {
        "behavior_preserved_for_retained_abstention",
        "untrusted_generic_simulator_admission",
        "provider",
        "training",
        "simulator_campaign",
        "simulator_promotion",
        "physical_capture",
        "robot_motion",
    }:
        raise LiveOperatorError("live operator migration proof boundary changed")
    if proof.get("behavior_preserved_for_retained_abstention") is not True or any(
        proof[name] is not False
        for name in proof
        if name != "behavior_preserved_for_retained_abstention"
    ):
        raise LiveOperatorError("live operator migration widened authority")
    if payload.get("reproduction_command") != [
        "uv",
        "run",
        "sim2claw",
        "sail-run-live-operator",
        "--config",
        "configs/sail/live_operator_c2_v1.json",
        "--output",
        "outputs/sail/live-operator-c2-migration-reproduction",
    ]:
        raise LiveOperatorError("live operator migration reproduction command changed")
    return {
        "schema_version": "sim2claw.sail_live_operator_migration_verification.v1",
        "migration_id": payload["migration_id"],
        "migration_digest": payload["migration_digest"],
        "retained_outputs_byte_identical": True,
        "promotion": False,
        "training_admitted": False,
        "physical_authority": False,
    }

__all__ = [
    "COMPILER_PATHS",
    "build_live_evaluator_identity",
    "verify_live_operator_migration_receipt",
    "verify_live_operator_receipt",
]

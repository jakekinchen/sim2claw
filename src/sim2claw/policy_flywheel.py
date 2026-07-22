"""Fail-closed lineage and modality contracts for the policy flywheel."""

from __future__ import annotations

import copy
from typing import Any, Mapping

from .learning_factory_artifacts import canonical_digest
from .sail.twin_worthiness import require_capability_context


GENERATION_LINEAGE_SCHEMA = "sim2claw.policy_flywheel_generation_lineage.v1"
GROOT_DISPOSITION_SCHEMA = "sim2claw.policy_flywheel_groot_disposition.v1"


def _digest(value: object, label: str) -> str:
    normalized = str(value or "")
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return normalized


def validate_generation_lineage(
    declaration: Mapping[str, Any],
    *,
    twin_capability_context: Mapping[str, Any],
    parent_twin_id: str,
    task_id: str,
    task_contract_sha256: str,
) -> dict[str, Any]:
    """Bind a generator to one certified posterior, simulator, and data scope."""

    capability = require_capability_context(
        twin_capability_context, capability="data_generation"
    )
    normalized = copy.deepcopy(dict(declaration))
    if normalized.get("schema_version") != GENERATION_LINEAGE_SCHEMA:
        raise ValueError("unsupported policy flywheel generation lineage")
    request = twin_capability_context.get("request")
    if not isinstance(request, Mapping):
        raise ValueError("generation lineage lacks a capability request")
    scope = request.get("scope")
    identities = request.get("expected_identities")
    if not isinstance(scope, Mapping) or not isinstance(identities, Mapping):
        raise ValueError("generation lineage lacks exact capability identities")
    if str(scope.get("twin_id") or "") != parent_twin_id:
        raise ValueError("generation lineage twin differs from the capability scope")
    if str(scope.get("task_id") or "") != task_id:
        raise ValueError("generation lineage task differs from the capability scope")
    if str(scope.get("task_contract_sha256") or "") != task_contract_sha256:
        raise ValueError("generation lineage task contract differs from the capability scope")

    posterior = normalized.get("posterior")
    if not isinstance(posterior, dict):
        raise ValueError("generation lineage requires an identified posterior")
    if posterior.get("sampling_policy") != "identified_posterior_only":
        raise ValueError("candidate generation must sample only the identified posterior")
    if posterior.get("arbitrary_domain_randomization") is not False:
        raise ValueError("arbitrary domain randomization is forbidden")
    if posterior.get("physical_parameter_claim") is not False:
        raise ValueError("a simulator posterior cannot assert a physical parameter")
    posterior_sha256 = _digest(
        posterior.get("artifact_sha256"), "posterior artifact identity"
    )
    if posterior_sha256 != identities.get("posterior"):
        raise ValueError("generation posterior differs from the certified posterior")
    _digest(posterior.get("posterior_digest"), "posterior canonical identity")
    particles = [str(value) for value in posterior.get("eligible_particle_ids") or []]
    if not particles or len(particles) != len(set(particles)) or any(not row for row in particles):
        raise ValueError("identified posterior has no unique eligible particles")

    simulator = normalized.get("simulator")
    if not isinstance(simulator, dict) or not str(simulator.get("simulator_id") or ""):
        raise ValueError("generation lineage requires a simulator identity")
    simulator_sha256 = _digest(
        simulator.get("implementation_sha256"), "simulator implementation identity"
    )
    if simulator_sha256 != identities.get("simulator"):
        raise ValueError("generation simulator differs from the certified simulator")

    teacher = normalized.get("teacher")
    if not isinstance(teacher, dict) or not str(teacher.get("teacher_id") or ""):
        raise ValueError("generation lineage requires a teacher identity")
    if teacher.get("action_owner") not in {
        "geometric_expert",
        "human_teleoperator_template",
    }:
        raise ValueError("generator actions lack an eligible teacher owner")
    if teacher.get("admission_authority") is not False:
        raise ValueError("the generator teacher cannot admit its own data")
    if normalized.get("source_segment_representation") != (
        "object_and_target_relative"
    ):
        raise ValueError("source segments must be object- and target-relative")

    distribution = normalized.get("task_distribution")
    expected_distribution = {
        "task_id": task_id,
        "task_contract_sha256": task_contract_sha256,
        "distribution_id": str(scope.get("distribution_id") or ""),
        "distribution_sha256": str(scope.get("distribution_sha256") or ""),
    }
    if distribution != expected_distribution:
        raise ValueError("generation task distribution differs from capability scope")

    modalities = normalized.get("policy_modalities")
    if not isinstance(modalities, dict):
        raise ValueError("generation lineage requires policy modality boundaries")
    if modalities.get("act_policy_inputs") != ["state_goal"]:
        raise ValueError("the primary ACT policy input contract changed")
    if modalities.get("groot_policy_camera_ids") != ["overhead"]:
        raise ValueError("the principal GR00T policy must remain overhead-only")
    evaluator_cameras = set(modalities.get("evaluator_only_camera_ids") or [])
    if "wrist" not in evaluator_cameras:
        raise ValueError("wrist imagery must remain evaluator-only")
    if evaluator_cameras & set(modalities["groot_policy_camera_ids"]):
        raise ValueError("evaluator-only cameras entered the policy schema")
    if modalities.get("wrist_is_main_policy_input") is not False:
        raise ValueError("wrist imagery cannot be a main-policy input")
    if normalized.get("physical_authority") is not False:
        raise ValueError("flywheel generation cannot create physical authority")

    unsigned = {
        **normalized,
        "capability_decision_digest": capability["decision_digest"],
    }
    return {**unsigned, "lineage_digest": canonical_digest(unsigned)}


def candidate_generation_binding(
    lineage: Mapping[str, Any], *, candidate_index: int
) -> dict[str, Any]:
    particles = list(lineage["posterior"]["eligible_particle_ids"])
    particle_id = str(particles[candidate_index % len(particles)])
    return {
        "generation_lineage_digest": str(lineage["lineage_digest"]),
        "posterior_particle_id": particle_id,
        "teacher_id": str(lineage["teacher"]["teacher_id"]),
        "teacher_action_owner": str(lineage["teacher"]["action_owner"]),
        "simulator_id": str(lineage["simulator"]["simulator_id"]),
        "simulator_implementation_sha256": str(
            lineage["simulator"]["implementation_sha256"]
        ),
    }


def compile_groot_challenger_disposition(
    dataset_receipt: Mapping[str, Any], declaration: Mapping[str, Any]
) -> dict[str, Any]:
    """Publish a separate GR00T lane or an explicit bounded-compute skip."""

    normalized = copy.deepcopy(dict(declaration))
    if normalized.get("mode") != "deterministic_skip":
        raise ValueError("P1-15 supports only the declared no-compute GR00T skip")
    if normalized.get("compute_available") is not False:
        raise ValueError("GR00T skip cannot claim available compute")
    if normalized.get("policy_camera_ids") != ["overhead"]:
        raise ValueError("GR00T challenger must remain overhead-only")
    evaluator_cameras = set(normalized.get("evaluator_only_camera_ids") or [])
    if "wrist" not in evaluator_cameras or "overhead" in evaluator_cameras:
        raise ValueError("GR00T evaluator-only camera declaration changed")
    reason = str(normalized.get("reason") or "")
    if reason not in {
        "no_compatible_local_groot_runtime_or_authorized_bounded_compute",
        "bounded_compute_budget_unavailable",
    }:
        raise ValueError("GR00T skip reason is not a frozen bounded-compute reason")
    payload = dataset_receipt.get("groot_payload")
    if not isinstance(payload, Mapping):
        raise ValueError("GR00T challenger lacks an admitted dataset payload")
    unsigned = {
        "schema_version": GROOT_DISPOSITION_SCHEMA,
        "status": "skipped_compute_unavailable",
        "reason": reason,
        "dataset_sha256": str(dataset_receipt.get("dataset_sha256") or ""),
        "groot_payload_sha256": _digest(
            payload.get("sha256"), "GR00T payload identity"
        ),
        "groot_row_count": int(payload.get("row_count", -1)),
        "policy_camera_ids": ["overhead"],
        "evaluator_only_camera_ids": sorted(evaluator_cameras),
        "wrist_main_policy_input": False,
        "training_invoked": False,
        "policy_comparison_published": False,
        "physical_authority": False,
        "proof_class": "simulation_groot_challenger_disposition",
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


__all__ = [
    "GENERATION_LINEAGE_SCHEMA",
    "GROOT_DISPOSITION_SCHEMA",
    "candidate_generation_binding",
    "compile_groot_challenger_disposition",
    "validate_generation_lineage",
]

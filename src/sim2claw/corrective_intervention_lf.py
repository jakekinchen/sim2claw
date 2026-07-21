"""Evidence adapters from LLM proposals into the existing LF-12 repair gate."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping

from .corrective_intervention import (
    CorrectiveInterventionError,
    validate_compiled_trajectory,
    validate_intervention_proposal,
    verify_sealed_artifact,
)
from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .learning_factory_recursion import CORRECTION_SCHEMA, admit_correction_candidate


INTERVENTION_LINEAGE_SCHEMA = "sim2claw.corrective_intervention_lineage.v1"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CorrectiveInterventionError(message)


def materialize_correction_evidence(
    output_directory: Path,
    *,
    parent_counterexample: Mapping[str, Any],
    start_sample_index: int,
    branch_state: Mapping[str, Any],
    proposal: Mapping[str, Any],
    compiled_trajectory: Mapping[str, Any],
) -> dict[str, Any]:
    """Write the three artifacts LF-12 authenticates before full replay.

    The failed prefix remains evidence only.  The LLM proposal is preserved as
    provenance, while the deterministic geometric expert remains action owner.
    """

    _require(type(start_sample_index) is int and start_sample_index >= 0, "start sample index is invalid")
    parent_id = parent_counterexample.get("counterexample_id")
    _require(isinstance(parent_id, str) and parent_id, "parent counterexample identity is missing")
    trace_sha256 = parent_counterexample.get("action_trace_sha256")
    _require(isinstance(trace_sha256, str) and len(trace_sha256) == 64, "parent action trace digest is invalid")
    _require(parent_counterexample.get("training_rows_authorized") == 0, "raw counterexample unexpectedly authorizes training")
    _require("LF-09" in parent_counterexample.get("route_targets", []), "parent is not routed to correction data")

    state = verify_sealed_artifact(branch_state)
    proposal_value = validate_intervention_proposal(proposal)
    compiled = validate_compiled_trajectory(compiled_trajectory)
    _require(proposal_value["counterexample_id"] == parent_id, "proposal references another counterexample")
    _require(proposal_value["branch_state_sha256"] == state["artifact_sha256"], "proposal references another branch state")
    _require(compiled["branch_state_sha256"] == state["artifact_sha256"], "compiled trajectory references another branch state")
    _require(compiled["proposal_sha256"] == canonical_digest(proposal_value), "compiled trajectory references another proposal")

    output_directory.mkdir(parents=True, exist_ok=False)
    failed_prefix_path = output_directory / "failed_prefix.json"
    branch_state_path = output_directory / "pre_failure_integration_state.json"
    proposal_path = output_directory / "proposal.json"
    compiled_path = output_directory / "compiled_trajectory.json"
    intervention_path = output_directory / "intervention.json"
    atomic_write_json(
        failed_prefix_path,
        {
            "schema_version": "sim2claw.failed_prefix_evidence.v1",
            "parent_counterexample_id": parent_id,
            "action_trace_sha256": trace_sha256,
            "end_sample_index_exclusive": start_sample_index,
            "training_rows_authorized": 0,
        },
    )
    atomic_write_json(branch_state_path, copy.deepcopy(dict(state)))
    atomic_write_json(proposal_path, copy.deepcopy(dict(proposal_value)))
    atomic_write_json(compiled_path, copy.deepcopy(dict(compiled)))
    atomic_write_json(
        intervention_path,
        {
            "schema_version": INTERVENTION_LINEAGE_SCHEMA,
            "owner": "geometric_expert",
            "start_sample_index": start_sample_index,
            "proposal_path": str(proposal_path),
            "proposal_sha256": sha256_file(proposal_path),
            "compiled_trajectory_path": str(compiled_path),
            "compiled_trajectory_sha256": sha256_file(compiled_path),
            "compiled_action_count": len(compiled["actions_rad"]),
            "llm_direct_control": False,
            "training_admission_authority": False,
            "promotion_authority": False,
            "physical_authority": False,
        },
    )
    return {
        "parent_counterexample_id": parent_id,
        "failed_prefix": {"path": str(failed_prefix_path), "sha256": sha256_file(failed_prefix_path)},
        "pre_failure_integration_state": {"path": str(branch_state_path), "sha256": sha256_file(branch_state_path)},
        "intervention": {"path": str(intervention_path), "sha256": sha256_file(intervention_path)},
        "proposal": {"path": str(proposal_path), "sha256": sha256_file(proposal_path)},
        "compiled_trajectory": {"path": str(compiled_path), "sha256": sha256_file(compiled_path)},
    }


def build_correction_submission(
    *,
    correction_candidate_id: str,
    evidence: Mapping[str, Any],
    corrective_episode_directory: Path,
    admission_verdict_path: Path,
) -> dict[str, Any]:
    """Build, but do not self-admit, the existing LF-12 correction envelope."""

    _require(isinstance(correction_candidate_id, str) and correction_candidate_id, "correction candidate identity is missing")
    required = {"parent_counterexample_id", "failed_prefix", "pre_failure_integration_state", "intervention", "proposal", "compiled_trajectory"}
    _require(set(evidence) == required, "correction evidence keys differ")
    for name in ("failed_prefix", "pre_failure_integration_state", "intervention", "proposal", "compiled_trajectory"):
        declaration = evidence[name]
        path = Path(str(declaration.get("path") or ""))
        _require(path.is_file() and sha256_file(path) == declaration.get("sha256"), f"correction evidence changed: {name}")
    _require(corrective_episode_directory.is_dir(), "corrective episode directory is missing")
    _require(admission_verdict_path.is_file(), "corrective admission verdict is missing")
    return {
        "schema_version": CORRECTION_SCHEMA,
        "correction_candidate_id": correction_candidate_id,
        "parent_counterexample_id": evidence["parent_counterexample_id"],
        "failed_prefix": copy.deepcopy(evidence["failed_prefix"]),
        "pre_failure_integration_state": copy.deepcopy(evidence["pre_failure_integration_state"]),
        "intervention": copy.deepcopy(evidence["intervention"]),
        "corrective_episode_directory": str(corrective_episode_directory.resolve()),
        "admission_verdict_path": str(admission_verdict_path.resolve()),
    }


def admit_llm_proposed_correction(
    submission: Mapping[str, Any],
    *,
    registry: Mapping[str, Any],
) -> dict[str, Any]:
    """Invoke the unchanged independent LF-12 admission path."""

    return admit_correction_candidate(dict(submission), registry=dict(registry))

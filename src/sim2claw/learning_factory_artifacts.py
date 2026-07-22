"""Deterministic evidence contracts used by the Codex-driven learning factory.

These helpers intentionally contain no model calls.  Codex may author their
inputs, but validation, admission, evaluation, and promotion remain ordinary
fail-closed Python decisions.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Iterable


class FactoryArtifactError(ValueError):
    """Raised when a factory artifact violates an evidence boundary."""


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def load_json_object(path: Path, *, label: str = "JSON") -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FactoryArtifactError(f"cannot read {label} {path}: {error}") from error
    if not isinstance(value, dict):
        raise FactoryArtifactError(f"{label} must contain an object: {path}")
    return value


def _finite_metric(row: dict[str, Any], name: str) -> float:
    try:
        value = float(row[name])
    except (KeyError, TypeError, ValueError) as error:
        raise FactoryArtifactError(f"missing numeric metric: {name}") from error
    if not math.isfinite(value):
        raise FactoryArtifactError(f"metric is not finite: {name}")
    return value


def compare_calibration_candidates(
    experiment: dict[str, Any],
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Apply an evaluator-owned held-out calibration verdict.

    Simulated policy success is reported but is deliberately absent from the
    admission rule.  The gate uses physical fidelity, failure agreement, and
    parameter identifiability.
    """

    if experiment.get("schema_version") != "sim2claw.calibration_experiment.v1":
        raise FactoryArtifactError("unsupported calibration experiment schema")
    roles = {
        role: set(str(item) for item in experiment.get(f"{role}_episode_ids", []))
        for role in ("calibration", "validation", "held_out")
    }
    if not roles["calibration"] or not roles["validation"]:
        raise FactoryArtifactError("calibration and validation cohorts must be non-empty")
    if any(roles[left] & roles[right] for left, right in (("calibration", "validation"), ("calibration", "held_out"), ("validation", "held_out"))):
        raise FactoryArtifactError("calibration, validation, and held-out episodes overlap")
    if set(str(item) for item in candidate.get("evaluated_episode_ids", [])) != roles["validation"]:
        raise FactoryArtifactError("candidate metrics do not bind the frozen validation cohort")
    if set(str(item) for item in baseline.get("evaluated_episode_ids", [])) != roles["validation"]:
        raise FactoryArtifactError("baseline metrics do not bind the frozen validation cohort")

    parameters = experiment.get("parameters")
    if not isinstance(parameters, list) or not parameters:
        raise FactoryArtifactError("calibration experiment has no bounded parameters")
    minimum_sensitivity = float(experiment.get("minimum_normalized_sensitivity", 0.05))
    sensitivity_rows: list[dict[str, Any]] = []
    identifiable = True
    for parameter in parameters:
        if not isinstance(parameter, dict):
            raise FactoryArtifactError("calibration parameter must be an object")
        lower = _finite_metric(parameter, "lower")
        upper = _finite_metric(parameter, "upper")
        sensitivity = _finite_metric(parameter, "normalized_sensitivity")
        if lower >= upper:
            raise FactoryArtifactError("calibration parameter bounds are not ordered")
        row_identifiable = abs(sensitivity) >= minimum_sensitivity
        identifiable = identifiable and row_identifiable
        sensitivity_rows.append(
            {
                "parameter": str(parameter.get("name", "")),
                "normalized_sensitivity": sensitivity,
                "identifiable": row_identifiable,
            }
        )

    directions = {
        "trajectory_rmse": "lower",
        "contact_timing_mae": "lower",
        "outcome_disagreement_rate": "lower",
        "sim_real_success_gap": "lower",
    }
    deltas: dict[str, float] = {}
    improved = 0
    regressions: list[str] = []
    tolerance = float(experiment.get("regression_tolerance", 0.0))
    for metric, direction in directions.items():
        before = _finite_metric(baseline, metric)
        after = _finite_metric(candidate, metric)
        delta = before - after if direction == "lower" else after - before
        deltas[metric] = delta
        if delta > 0:
            improved += 1
        if delta < -tolerance:
            regressions.append(metric)

    minimum_improved = int(experiment.get("minimum_improved_fidelity_metrics", 3))
    admitted = identifiable and improved >= minimum_improved and not regressions
    reported_policy_probe = {
        "baseline_sim_success_rate": _finite_metric(
            baseline, "simulated_policy_success_rate"
        ),
        "candidate_sim_success_rate": _finite_metric(
            candidate, "simulated_policy_success_rate"
        ),
        "used_for_admission": False,
    }
    unsigned = {
        "schema_version": "sim2claw.factory_calibration_comparison.v1",
        "experiment_id": str(experiment.get("experiment_id", "")),
        "baseline_twin_id": str(baseline.get("twin_id", "")),
        "candidate_twin_id": str(candidate.get("twin_id", "")),
        "validation_episode_ids": sorted(roles["validation"]),
        "held_out_episode_ids_opened": 0,
        "sensitivity": sensitivity_rows,
        "fidelity_deltas_positive_is_better": deltas,
        "policy_probe": reported_policy_probe,
        "verdict_owner": "calibration_evaluator",
        "verdict": "admitted" if admitted else "rejected",
        "reasons": [] if admitted else (["unidentifiable_parameters"] if not identifiable else []) + (["insufficient_fidelity_improvement"] if improved < minimum_improved else []) + [f"regressed:{name}" for name in regressions],
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def compile_cousin_batch(spec: dict[str, Any]) -> dict[str, Any]:
    if spec.get("schema_version") != "sim2claw.cousin_experiment.v1":
        raise FactoryArtifactError("unsupported cousin experiment schema")
    max_candidates = int(spec.get("max_candidates", 0))
    proposals = spec.get("proposals")
    if max_candidates <= 0 or not isinstance(proposals, list):
        raise FactoryArtifactError("cousin experiment needs a positive bounded batch")
    if len(proposals) > max_candidates:
        raise FactoryArtifactError("cousin proposal count exceeds the bounded batch")
    envelope = spec.get("variation_envelope")
    if not isinstance(envelope, dict):
        raise FactoryArtifactError("cousin variation envelope is missing")
    maximum_offset = float(envelope.get("maximum_planar_offset_m", 0.0))
    allowed_distractors = set(str(item) for item in envelope.get("allowed_distractors", []))
    allowed_roles = {"train", "debug", "held_out"}
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for proposal in proposals:
        if not isinstance(proposal, dict):
            raise FactoryArtifactError("cousin proposal must be an object")
        role = str(proposal.get("role", ""))
        if role not in allowed_roles:
            raise FactoryArtifactError(f"invalid cousin role: {role}")
        offset = proposal.get("target_offset_xy_m")
        if not isinstance(offset, list) or len(offset) != 2:
            raise FactoryArtifactError("cousin target offset must contain two values")
        x, y = (float(value) for value in offset)
        if not all(math.isfinite(value) for value in (x, y)) or max(abs(x), abs(y)) > maximum_offset:
            raise FactoryArtifactError("cousin target offset escapes the declared envelope")
        distractor = str(proposal.get("distractor", "none"))
        if distractor not in allowed_distractors:
            raise FactoryArtifactError("cousin distractor escapes the declared envelope")
        identity_payload = {
            "parent_twin_id": spec.get("parent_twin_id"),
            "source_cell": proposal.get("source_cell"),
            "target_offset_xy_m": [x, y],
            "distractor": distractor,
            "role": role,
        }
        candidate_id = f"cousin-{canonical_digest(identity_payload)[:16]}"
        if candidate_id in seen:
            raise FactoryArtifactError("duplicate cousin proposal")
        seen.add(candidate_id)
        candidates.append({"candidate_id": candidate_id, **identity_payload})
    unsigned = {
        "schema_version": "sim2claw.factory_cousin_batch.v1",
        "experiment_id": str(spec.get("experiment_id", "")),
        "parent_twin_id": str(spec.get("parent_twin_id", "")),
        "candidate_count": len(candidates),
        "roles": {role: sum(item["role"] == role for item in candidates) for role in sorted(allowed_roles)},
        "candidates": candidates,
        "held_out_mutated": False,
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def admit_dataset_candidates(candidates: Iterable[dict[str, Any]]) -> dict[str, Any]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in candidates:
        row = dict(raw)
        candidate_id = str(row.get("candidate_id", ""))
        if not candidate_id or candidate_id in seen:
            raise FactoryArtifactError("dataset candidates need unique identities")
        seen.add(candidate_id)
        role = str(row.get("role", ""))
        replay_passed = row.get("replay_passed") is True
        evaluator_passed = row.get("evaluator_passed") is True
        if role == "train" and replay_passed and evaluator_passed:
            accepted.append(
                {
                    "candidate_id": candidate_id,
                    "role": role,
                    "source_sha256": str(row.get("source_sha256", "")),
                    "admission_owner": "strict_success_evaluator",
                }
            )
        else:
            reasons = []
            if role != "train":
                reasons.append(f"role_not_train:{role}")
            if not replay_passed:
                reasons.append("replay_failed")
            if not evaluator_passed:
                reasons.append("separate_evaluator_failed")
            rejected.append({"candidate_id": candidate_id, "role": role, "reasons": reasons})
    unsigned = {
        "schema_version": "sim2claw.factory_dataset_admission.v1",
        "accepted": accepted,
        "rejected": rejected,
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "training_episode_ids": [item["candidate_id"] for item in accepted],
        "held_out_training_rows": 0,
        "rejected_training_rows": 0,
        "admission_owner": "strict_success_evaluator",
    }
    return {**unsigned, "dataset_sha256": canonical_digest(unsigned)}


def capture_training_candidate(
    checkpoint_path: Path,
    *,
    dataset_receipt: dict[str, Any],
    task_id: str,
    recipe_id: str,
    architecture: str,
) -> dict[str, Any]:
    if dataset_receipt.get("held_out_training_rows") != 0:
        raise FactoryArtifactError("held-out rows cannot enter policy training")
    if dataset_receipt.get("rejected_training_rows") != 0:
        raise FactoryArtifactError("rejected rows cannot enter policy training")
    if not checkpoint_path.is_file():
        raise FactoryArtifactError(f"training checkpoint is missing: {checkpoint_path}")
    unsigned = {
        "schema_version": "sim2claw.factory_training_result.v1",
        "task_id": task_id,
        "architecture": architecture,
        "recipe_id": recipe_id,
        "dataset_sha256": str(dataset_receipt.get("dataset_sha256", "")),
        "checkpoint_path": str(checkpoint_path),
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "trainer_has_evaluation_authority": False,
        "trainer_has_promotion_authority": False,
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def evaluate_policy_candidates(
    *,
    task_id: str,
    evaluator_id: str,
    candidates: Iterable[dict[str, Any]],
    twin_capability_context: dict[str, Any],
) -> dict[str, Any]:
    from .sail.twin_worthiness import require_capability_context

    capability = require_capability_context(
        twin_capability_context, capability="policy_selection"
    )
    if not evaluator_id or evaluator_id == "trainer":
        raise FactoryArtifactError("policy evaluation must have a separate evaluator")
    rows: list[dict[str, Any]] = []
    for raw in candidates:
        checkpoint_sha256 = str(raw.get("checkpoint_sha256", ""))
        if len(checkpoint_sha256) != 64:
            raise FactoryArtifactError("candidate checkpoint identity is invalid")
        success_rate = _finite_metric(raw, "success_rate")
        threshold = _finite_metric(raw, "minimum_success_rate")
        verdict = "eligible" if success_rate >= threshold else "terminal_negative"
        rows.append(
            {
                "candidate_id": str(raw.get("candidate_id", checkpoint_sha256[:16])),
                "checkpoint_sha256": checkpoint_sha256,
                "success_rate": success_rate,
                "minimum_success_rate": threshold,
                "verdict": verdict,
            }
        )
    unsigned = {
        "schema_version": "sim2claw.factory_candidate_scorecard.v1",
        "task_id": task_id,
        "evaluator_id": evaluator_id,
        "evaluator_runtime": "cpu_fp32",
        "candidates": rows,
        "eligible_candidate_ids": [row["candidate_id"] for row in rows if row["verdict"] == "eligible"],
        "terminal_negative_candidate_ids": [row["candidate_id"] for row in rows if row["verdict"] == "terminal_negative"],
        "twin_capability_decision_digest": capability["decision_digest"],
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def normalize_counterexamples(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    records: dict[str, dict[str, Any]] = {}
    for raw in rows:
        role = str(raw.get("source_role", ""))
        identity = {
            "source_id": str(raw.get("source_id", "")),
            "candidate_id": str(raw.get("candidate_id", "")),
            "evaluator_id": str(raw.get("evaluator_id", "")),
            "failure_code": str(raw.get("failure_code", "")),
        }
        if not all(identity.values()):
            raise FactoryArtifactError("counterexample identity is incomplete")
        counterexample_id = f"counterexample-{canonical_digest(identity)[:20]}"
        record = {
            "counterexample_id": counterexample_id,
            **identity,
            "source_role": role,
            "trace_sha256": str(raw.get("trace_sha256", "")),
            "disposition": str(raw.get("disposition", "regression_only")),
            "training_admitted": False,
        }
        previous = records.get(counterexample_id)
        if previous is not None and previous != record:
            raise FactoryArtifactError("duplicate counterexample identity has conflicting evidence")
        records[counterexample_id] = record
    ordered = [records[key] for key in sorted(records)]
    unsigned = {
        "schema_version": "sim2claw.factory_counterexample_registry.v1",
        "records": ordered,
        "record_count": len(ordered),
        "automatically_admitted_training_rows": 0,
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def update_counterexample_registry(
    path: Path, rows: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    """Merge a batch into one atomic content-addressed registry."""

    incoming = normalize_counterexamples(rows)
    combined = list(incoming["records"])
    if path.is_file():
        existing = load_json_object(path, label="counterexample registry")
        if existing.get("schema_version") != "sim2claw.factory_counterexample_registry.v1":
            raise FactoryArtifactError("unsupported counterexample registry schema")
        combined.extend(existing.get("records", []))
    normalized = normalize_counterexamples(
        {
            "source_id": item["source_id"],
            "candidate_id": item["candidate_id"],
            "evaluator_id": item["evaluator_id"],
            "failure_code": item["failure_code"],
            "source_role": item["source_role"],
            "trace_sha256": item["trace_sha256"],
            "disposition": item["disposition"],
        }
        for item in combined
    )
    atomic_write_json(path, normalized)
    return normalized


def admit_correction_candidate(
    counterexample: dict[str, Any],
    *,
    intervention_step: int,
    branch_state_sha256: str,
    corrective_suffix_sha256: str,
    replay_passed: bool,
    evaluator_passed: bool,
) -> dict[str, Any]:
    if counterexample.get("source_role") == "held_out":
        raise FactoryArtifactError("held-out counterexamples cannot become correction training data")
    admitted = replay_passed and evaluator_passed
    unsigned = {
        "schema_version": "sim2claw.factory_correction_candidate.v1",
        "counterexample_id": str(counterexample.get("counterexample_id", "")),
        "failed_prefix_preserved": True,
        "intervention_step": int(intervention_step),
        "branch_state_sha256": branch_state_sha256,
        "corrective_suffix_sha256": corrective_suffix_sha256,
        "replay_passed": replay_passed,
        "separate_evaluator_passed": evaluator_passed,
        "training_admitted": admitted,
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def promotion_state(
    scorecard: dict[str, Any],
    *,
    project_id: str,
    twin_id: str,
    dataset_sha256: str,
    scope_compatible: bool = True,
    twin_capability_context: dict[str, Any],
) -> dict[str, Any]:
    from .sail.twin_worthiness import require_capability_context

    capability = require_capability_context(
        twin_capability_context, capability="policy_selection"
    )
    eligible = list(scorecard.get("eligible_candidate_ids", []))
    state = (
        "rejected"
        if not scope_compatible
        else ("promoted" if len(eligible) == 1 else ("rejected" if not eligible else "partial"))
    )
    unsigned = {
        "schema_version": "sim2claw.factory_promotion_state.v1",
        "project_id": project_id,
        "twin_id": twin_id,
        "dataset_sha256": dataset_sha256,
        "scorecard_sha256": str(scorecard.get("artifact_sha256", "")),
        "policy_task_id": str(scorecard.get("task_id", "")),
        "project_scope_compatible": scope_compatible,
        "promotion_owner": "independent_promotion_engine",
        "state": state,
        "promoted_candidate_id": eligible[0] if state == "promoted" else None,
        "physical_authority": False,
        "robot_motion_allowed": False,
        "twin_capability_decision_digest": capability["decision_digest"],
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def bind_narrow_act_evidence(
    training_receipt_path: Path,
    evaluation_receipt_path: Path,
) -> dict[str, Any]:
    """Bind the frozen rook-lift ACT proof without widening it to B--G skills."""

    training = load_json_object(training_receipt_path, label="ACT training receipt")
    evaluation = load_json_object(evaluation_receipt_path, label="ACT evaluation receipt")
    if training.get("schema_version") != "sim2claw.act_training_receipt.v1":
        raise FactoryArtifactError("unsupported ACT training receipt schema")
    if evaluation.get("schema_version") != "sim2claw.act_evaluation_receipt.v1":
        raise FactoryArtifactError("unsupported ACT evaluation receipt schema")
    task_id = "chess_rook_lift_v1"
    if training.get("task_id") != task_id or evaluation.get("task_id") != task_id:
        raise FactoryArtifactError("ACT evidence is not the frozen narrow rook-lift task")
    if training.get("task_contract_sha256") != evaluation.get("task_contract_sha256"):
        raise FactoryArtifactError("ACT training and evaluation task identities differ")
    dataset = training.get("dataset")
    if not isinstance(dataset, dict) or dataset.get("held_out_seed_rows") != 0:
        raise FactoryArtifactError("ACT training receipt opened held-out seed rows")
    model = training.get("model")
    policy = evaluation.get("policy")
    runtime = evaluation.get("runtime")
    if not isinstance(model, dict) or not isinstance(policy, dict) or not isinstance(runtime, dict):
        raise FactoryArtifactError("ACT receipt model/evaluator evidence is incomplete")
    expected_checkpoint_sha256 = str(model.get("checkpoint_sha256", ""))
    if expected_checkpoint_sha256 != policy.get("checkpoint_sha256"):
        raise FactoryArtifactError("ACT receipts declare different checkpoints")
    declared_checkpoint = Path(str(model.get("checkpoint", "")))
    checkpoint_candidates = [
        declared_checkpoint,
        training_receipt_path.parent / "checkpoint.pt",
    ]
    checkpoint_path = next(
        (
            path
            for path in checkpoint_candidates
            if path.is_file() and sha256_file(path) == expected_checkpoint_sha256
        ),
        None,
    )
    if checkpoint_path is None:
        raise FactoryArtifactError("ACT checkpoint bytes do not match both receipts")
    checkpoint_sha256 = sha256_file(checkpoint_path)
    if runtime.get("device") != "cpu" or runtime.get("dtype") != "float32":
        raise FactoryArtifactError("ACT evaluation is not CPU/fp32")
    if runtime.get("evaluator_owner") != "separate_cpu_fp32_process":
        raise FactoryArtifactError("ACT evaluation is not separately owned")
    if evaluation.get("physical_authority") is not False:
        raise FactoryArtifactError("ACT simulation evidence claims physical authority")
    unsigned = {
        "schema_version": "sim2claw.factory_narrow_act_evidence.v1",
        "task_id": task_id,
        "task_contract_sha256": training["task_contract_sha256"],
        "training_receipt": str(training_receipt_path),
        "training_receipt_sha256": sha256_file(training_receipt_path),
        "evaluation_receipt": str(evaluation_receipt_path),
        "evaluation_receipt_sha256": sha256_file(evaluation_receipt_path),
        "checkpoint_sha256": checkpoint_sha256,
        "held_out_training_rows": 0,
        "evaluator_owner": runtime["evaluator_owner"],
        "evaluator_runtime": "cpu_fp32",
        "verdict": "eligible" if evaluation.get("success") is True else "terminal_negative",
        "promotion_eligible_for_task": evaluation.get("success") is True,
        "bg_policy_claim_allowed": False,
        "physical_authority": False,
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}

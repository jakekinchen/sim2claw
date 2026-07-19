"""Trace-native counterexample registry and guarded recursion contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .pawn_source_evaluator import evaluate_source_episode
from .source_episode import adapt_source_episode, load_source_episode


REGISTRY_SCHEMA = "sim2claw.factory_counterexample_registry.v2"
CORRECTION_SCHEMA = "sim2claw.factory_correction_candidate.v1"


CALIBRATION_FAILURES = {
    "final_linear_speed",
    "other_piece_displacement",
    "wrong_piece_contact",
}
COVERAGE_FAILURES = {
    "maximum_piece_rise",
    "final_xy_error",
    "final_height_error",
    "gripper_clearance",
}


def _independent_replay_digest(verdict: dict[str, Any]) -> str:
    """Hash evaluator evidence while excluding wall-clock and file-location fields."""

    return canonical_digest(
        {
            key: value
            for key, value in verdict.items()
            if key
            not in {
                "canonical_payload_sha256",
                "created_at",
                "receipt_path",
                "receipt_sha256",
            }
        }
    )


def _validate_evaluation(evaluation: dict[str, Any]) -> None:
    if evaluation.get("schema_version") != "sim2claw.goal_act_evaluation_receipt.v1":
        raise ValueError("counterexamples require a goal ACT evaluation receipt")
    unsigned = {key: value for key, value in evaluation.items() if key not in {"artifact_sha256", "process"}}
    # A process wrapper adds process identity after verifying the evaluator's
    # original digest.  Direct receipts have no process field.
    if evaluation.get("artifact_sha256") != canonical_digest(unsigned):
        raise ValueError("counterexample source evaluation digest mismatch")
    if evaluation.get("evaluator_owner") != "separate_cpu_fp32_consequence_evaluator":
        raise ValueError("counterexample source is not evaluator-owned")


def _route(failure_codes: list[str]) -> list[str]:
    routes: set[str] = set()
    failures = set(failure_codes)
    if failures & CALIBRATION_FAILURES:
        routes.add("LF-06")
    if failures & COVERAGE_FAILURES:
        routes.add("LF-08")
    if failures - CALIBRATION_FAILURES - COVERAGE_FAILURES:
        routes.add("LF-09")
    if not routes:
        routes.add("LF-08")
    return sorted(routes)


def persist_counterexample_registry(
    evaluation: dict[str, Any],
    *,
    output_path: Path,
    previous_registry_path: Path | None = None,
) -> dict[str, Any]:
    """Persist and deduplicate evaluator failures with trace identities."""

    _validate_evaluation(evaluation)
    prior_rows: list[dict[str, Any]] = []
    parent_registry_sha256: str | None = None
    if previous_registry_path is not None:
        previous = json.loads(previous_registry_path.read_text(encoding="utf-8"))
        if previous.get("schema_version") != REGISTRY_SCHEMA:
            raise ValueError("previous counterexample registry has another schema")
        unsigned_previous = {key: value for key, value in previous.items() if key != "artifact_sha256"}
        if previous.get("artifact_sha256") != canonical_digest(unsigned_previous):
            raise ValueError("previous counterexample registry digest mismatch")
        prior_rows = list(previous["counterexamples"])
        parent_registry_sha256 = sha256_file(previous_registry_path)
    rows = list(prior_rows)
    seen = {str(row["deduplication_key"]) for row in rows}
    added = 0
    for case in evaluation["case_results"]:
        if case.get("strict_success") is True:
            continue
        failures = sorted(str(value) for value in case.get("failure_codes", []))
        if not failures:
            raise ValueError("failed evaluation case has no failure codes")
        trace_sha256 = str(case.get("action_trace_sha256") or "")
        if len(trace_sha256) != 64:
            raise ValueError("failed evaluation case has no authenticated trace")
        identity = {
            "checkpoint_sha256": evaluation["checkpoint_sha256"],
            "cohort_sha256": evaluation["cohort_sha256"],
            "case_id": case["case_id"],
            "failure_codes": failures,
            "action_trace_sha256": trace_sha256,
        }
        key = canonical_digest(identity)
        if key in seen:
            continue
        seen.add(key)
        added += 1
        rows.append(
            {
                "counterexample_id": f"counterexample-{key[:20]}",
                "deduplication_key": key,
                **identity,
                "candidate_seed": case["candidate_seed"],
                "object_destination_pair": case["object_destination_pair"],
                "distractor_layout": case["distractor_layout"],
                "measurements_sha256": canonical_digest(case["measurements"]),
                "route_targets": _route(failures),
                "training_rows_authorized": 0,
            }
        )
    route_targets = sorted({target for row in rows for target in row["route_targets"]})
    unsigned = {
        "schema_version": REGISTRY_SCHEMA,
        "source_evaluation_sha256": evaluation["artifact_sha256"],
        "parent_registry_sha256": parent_registry_sha256,
        "counterexample_count": len(rows),
        "new_counterexample_count": added,
        "counterexamples": rows,
        "route_targets": route_targets,
        "correction_candidates": [],
        "raw_failures_are_training_data": False,
    }
    registry = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_path, registry)
    return registry


def admit_correction_candidate(
    correction: dict[str, Any],
    *,
    registry: dict[str, Any],
) -> dict[str, Any]:
    """Validate an exact failed-prefix/intervention/corrective-suffix branch."""

    unsigned_registry = {
        key: value for key, value in registry.items() if key != "artifact_sha256"
    }
    if registry.get("artifact_sha256") != canonical_digest(unsigned_registry):
        raise ValueError("counterexample registry digest mismatch")
    if correction.get("schema_version") != CORRECTION_SCHEMA:
        raise ValueError("unsupported correction candidate")
    parent_id = str(correction.get("parent_counterexample_id") or "")
    parents = {
        str(row["counterexample_id"]): row for row in registry["counterexamples"]
    }
    if parent_id not in parents:
        raise ValueError("correction references an unknown counterexample")
    parent = parents[parent_id]
    artifacts: dict[str, dict[str, str]] = {}
    artifact_payloads: dict[str, dict[str, Any]] = {}
    for name in ("failed_prefix", "pre_failure_integration_state", "intervention"):
        declaration = correction.get(name)
        if not isinstance(declaration, dict):
            raise ValueError(f"correction is missing {name} evidence")
        path = Path(str(declaration.get("path") or "")).resolve()
        digest = str(declaration.get("sha256") or "")
        if not path.is_file() or sha256_file(path) != digest:
            raise ValueError(f"correction {name} evidence is missing or changed")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError(f"correction {name} evidence is not JSON") from error
        if not isinstance(payload, dict):
            raise ValueError(f"correction {name} evidence must be an object")
        artifacts[name] = {"path": str(path), "sha256": digest}
        artifact_payloads[name] = payload
    failed_prefix = artifact_payloads["failed_prefix"]
    if (
        failed_prefix.get("parent_counterexample_id") != parent_id
        or failed_prefix.get("action_trace_sha256")
        != parent.get("action_trace_sha256")
    ):
        raise ValueError("failed-prefix evidence is not bound to its counterexample")
    intervention = artifact_payloads["intervention"]
    if intervention.get("owner") not in {
        "human_teleoperator",
        "geometric_expert",
    }:
        raise ValueError("correction intervention has no eligible action owner")
    episode = Path(str(correction.get("corrective_episode_directory") or "")).resolve()
    verdict_path = Path(str(correction.get("admission_verdict_path") or "")).resolve()
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    independently_replayed = evaluate_source_episode(episode)
    for field in (
        "source_recording_id",
        "source_receipt_sha256",
        "source_samples_sha256",
        "scene_id",
        "board_pose_id",
        "evaluator_identity",
        "measurements",
        "gates",
        "strict_success",
        "exact_float32_sample_hold_replay_passed",
    ):
        if verdict.get(field) != independently_replayed.get(field):
            raise ValueError(
                f"corrective verdict differs from independent replay: {field}"
            )
    suffix = verdict.get("corrective_suffix")
    if not isinstance(suffix, dict):
        raise ValueError("repair admission is missing corrective suffix evidence")
    start = int(suffix.get("start_sample_index", -1))
    end = int(suffix.get("end_sample_index_exclusive", -1))
    receipt, source_rows = load_source_episode(episode)
    if start < 0 or end > len(source_rows) or end <= start:
        raise ValueError("corrective suffix row range is invalid")
    privileged_path = episode / str(receipt["evaluator_privileged_state_path"])
    privileged_rows = [
        json.loads(line)
        for line in privileged_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if start == 0:
        initial_path = episode / str(
            receipt["initial_evaluator_privileged_state_path"]
        )
        expected_state = json.loads(initial_path.read_text(encoding="utf-8"))[
            "state"
        ]["integration_state_float64"]
    else:
        expected_state = privileged_rows[start - 1]["state"][
            "integration_state_float64"
        ]
    branch_state = artifact_payloads["pre_failure_integration_state"].get(
        "integration_state_float64"
    )
    if branch_state != expected_state:
        raise ValueError("correction branch state differs from replay state")
    if int(intervention.get("start_sample_index", -1)) != start:
        raise ValueError("correction intervention starts at another sample")
    evidence_bindings = {
        "parent_counterexample_id": parent_id,
        "failed_prefix_sha256": artifacts["failed_prefix"]["sha256"],
        "pre_failure_integration_state_sha256": artifacts[
            "pre_failure_integration_state"
        ]["sha256"],
        "intervention_sha256": artifacts["intervention"]["sha256"],
        "independent_full_episode_evidence_sha256": _independent_replay_digest(
            independently_replayed
        ),
    }
    if any(suffix.get(key) != value for key, value in evidence_bindings.items()):
        raise ValueError("corrective verdict evidence bindings are incomplete")
    rows = adapt_source_episode(episode, adapter="act", admission_verdict=verdict)
    if verdict.get("admission_class") != "corrective_suffix":
        raise ValueError("repair admission must be an evaluator-approved corrective suffix")
    unsigned = {
        "schema_version": "sim2claw.factory_admitted_correction.v1",
        "correction_candidate_id": str(correction.get("correction_candidate_id") or ""),
        "parent_counterexample_id": parent_id,
        "artifacts": artifacts,
        "corrective_episode_directory": str(episode),
        "admission_verdict_path": str(verdict_path),
        "admission_verdict_sha256": sha256_file(verdict_path),
        "admitted_suffix_row_count": len(rows),
        "failed_prefix_training_rows": 0,
        "route_target": "LF-09",
        "independent_evaluator_admitted": True,
        "independent_full_episode_evidence_sha256": _independent_replay_digest(
            independently_replayed
        ),
    }
    if not unsigned["correction_candidate_id"]:
        raise ValueError("correction candidate identity is required")
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def attach_corrections(
    registry: dict[str, Any], corrections: list[dict[str, Any]]
) -> dict[str, Any]:
    unsigned_registry = {key: value for key, value in registry.items() if key != "artifact_sha256"}
    if registry.get("artifact_sha256") != canonical_digest(unsigned_registry):
        raise ValueError("counterexample registry digest mismatch")
    admitted = [admit_correction_candidate(row, registry=registry) for row in corrections]
    unsigned = {
        **unsigned_registry,
        "correction_candidates": admitted,
        "route_targets": sorted(set(registry["route_targets"]) | ({"LF-09"} if admitted else set())),
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}

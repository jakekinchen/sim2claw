"""Offline identifiability audit for a hash-bound SO-101 command trace."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    sha256_file,
)
from .paths import REPO_ROOT


CONTRACT_SCHEMA = "sim2claw.overnight_joint_identifiability_contract.v1"
REPORT_SCHEMA = "sim2claw.joint_identifiability_report.v1"
RECEIPT_SCHEMA = "sim2claw.joint_identifiability_receipt.v1"
DEFAULT_CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "overnight_joint_identifiability_v1.json"
)


class JointIdentifiabilityError(RuntimeError):
    """The source, analysis contract, or output boundary is invalid."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise JointIdentifiabilityError(message)


def _repo_path(value: object) -> Path:
    root = REPO_ROOT.resolve()
    path = (root / str(value)).resolve()
    _require(path.is_relative_to(root), "Path escapes the repository.")
    return path


def _array_sha256(values: np.ndarray) -> str:
    _require(
        values.dtype == np.dtype("<f8") and values.flags.c_contiguous,
        "Command tensor must be contiguous little-endian float64.",
    )
    return hashlib.sha256(values.tobytes(order="C")).hexdigest()


def load_joint_identifiability_contract(
    path: Path = DEFAULT_CONTRACT_PATH,
) -> dict[str, Any]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise JointIdentifiabilityError(
            f"Could not load joint-identifiability contract: {error}"
        ) from error
    _require(isinstance(contract, dict), "Analysis contract must be an object.")
    _require(
        contract.get("schema_version") == CONTRACT_SCHEMA,
        "Unsupported joint-identifiability contract.",
    )
    _require(
        contract.get("status") == "frozen_before_derived_materialization",
        "Joint-identifiability contract is not frozen.",
    )
    estimator = contract.get("estimator")
    claims = contract.get("claim_gates")
    authority = contract.get("authority")
    _require(isinstance(estimator, dict), "Estimator contract is missing.")
    _require(isinstance(claims, dict), "Claim gates are missing.")
    _require(isinstance(authority, dict), "Authority contract is missing.")
    _require(
        estimator.get("no_action_mutation") is True
        and estimator.get("no_lag_interpolation") is True,
        "Action mutation or lag interpolation was enabled.",
    )
    _require(
        claims.get("simulator_parameter_promotion_allowed") is False
        and claims.get("task_score_change_allowed") is False,
        "Identifiability analysis widened claim authority.",
    )
    _require(
        authority and all(value is False for value in authority.values()),
        "Identifiability analysis widened execution authority.",
    )
    return contract


def _load_source(
    contract: Mapping[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    source = contract["source"]
    source_root = _repo_path(source["recording_directory"])
    samples_path = source_root / str(source["samples_path"])
    _require(samples_path.is_file(), "Source samples are unavailable.")
    _require(
        sha256_file(samples_path) == source["samples_sha256"],
        "Source sample bytes changed.",
    )
    rows = [
        json.loads(line)
        for line in samples_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    _require(
        all(row.get("recording_id") == source["recording_id"] for row in rows),
        "A source row belongs to another recording.",
    )
    try:
        command = np.ascontiguousarray(
            [row[source["command_field"]] for row in rows], dtype="<f8"
        )
        actual = np.ascontiguousarray(
            [row[source["actual_position_field"]] for row in rows], dtype="<f8"
        )
        velocity = np.ascontiguousarray(
            [row[source["actual_velocity_field"]] for row in rows], dtype="<f8"
        )
        timestamp = np.asarray(
            [row[source["timestamp_field"]] for row in rows], dtype="<f8"
        )
    except (KeyError, TypeError, ValueError) as error:
        raise JointIdentifiabilityError("Source telemetry is invalid.") from error
    shape = tuple(int(value) for value in source["action_shape"])
    _require(
        command.shape == shape
        and actual.shape == shape
        and velocity.shape == shape,
        "Source telemetry shape changed.",
    )
    _require(
        bool(np.all(np.isfinite(command)))
        and bool(np.all(np.isfinite(actual)))
        and bool(np.all(np.isfinite(velocity)))
        and bool(np.all(np.isfinite(timestamp))),
        "Source telemetry contains non-finite values.",
    )
    _require(
        bool(np.all(np.diff(timestamp) > 0.0)),
        "Source timestamps are not strictly increasing.",
    )
    _require(
        _array_sha256(command) == source["action_sha256"],
        "Exact command tensor changed.",
    )
    return command, actual, velocity, timestamp


def _best_sample_lag(
    command: np.ndarray,
    actual: np.ndarray,
    candidates: list[int],
) -> tuple[int, float, float]:
    rows: list[tuple[float, int]] = []
    for lag in candidates:
        _require(lag >= 0, "Lag candidates must be non-negative.")
        source = command if lag == 0 else command[:-lag]
        observed = actual if lag == 0 else actual[lag:]
        _require(len(source) >= 2, "Lag candidate leaves too few samples.")
        rows.append((float(np.sqrt(np.mean(np.square(source - observed)))), lag))
    best_rmse, best_lag = min(rows, key=lambda row: (row[0], row[1]))
    no_lag_rmse = next(rmse for rmse, lag in rows if lag == 0)
    return best_lag, best_rmse, no_lag_rmse


def _joint_row(
    joint: str,
    command: np.ndarray,
    actual: np.ndarray,
    velocity: np.ndarray,
    median_dt: float,
    estimator: Mapping[str, Any],
) -> dict[str, Any]:
    span = float(np.ptp(command))
    changes = np.diff(command)
    epsilon = float(estimator["command_change_epsilon_degrees"])
    positive_changes = int(np.count_nonzero(changes > epsilon))
    negative_changes = int(np.count_nonzero(changes < -epsilon))
    velocity_threshold = float(
        estimator["minimum_velocity_for_direction_degrees_s"]
    )
    positive_velocity = int(np.count_nonzero(velocity > velocity_threshold))
    negative_velocity = int(np.count_nonzero(velocity < -velocity_threshold))
    span_gate = span >= float(estimator["minimum_command_span_degrees"])
    bidirectional_gate = (
        positive_changes >= int(estimator["minimum_positive_command_changes"])
        and negative_changes >= int(estimator["minimum_negative_command_changes"])
    )
    design = np.column_stack([command, np.ones(len(command))])
    gain, offset = np.linalg.lstsq(design, actual, rcond=None)[0]
    prediction = design @ np.asarray([gain, offset])
    residual_sum = float(np.sum(np.square(actual - prediction)))
    centered_sum = float(np.sum(np.square(actual - np.mean(actual))))
    r_squared = 1.0 - residual_sum / centered_sum if centered_sum > 0.0 else None
    best_lag, best_rmse, no_lag_rmse = _best_sample_lag(
        command,
        actual,
        [int(value) for value in estimator["lag_candidates_samples"]],
    )
    if not span_gate:
        verdict = "not_identifiable_insufficient_command_span"
    elif not bidirectional_gate:
        verdict = "not_identifiable_insufficient_bidirectional_excitation"
    else:
        verdict = "diagnostic_identifiable_for_unloaded_tracking_only"
    return {
        "joint": joint,
        "command_minimum_degrees": float(np.min(command)),
        "command_maximum_degrees": float(np.max(command)),
        "command_span_degrees": span,
        "actual_minimum_degrees": float(np.min(actual)),
        "actual_maximum_degrees": float(np.max(actual)),
        "actual_span_degrees": float(np.ptp(actual)),
        "positive_command_change_count": positive_changes,
        "negative_command_change_count": negative_changes,
        "positive_velocity_sample_count": positive_velocity,
        "negative_velocity_sample_count": negative_velocity,
        "span_gate": span_gate,
        "bidirectional_excitation_gate": bidirectional_gate,
        "affine_fit": {
            "gain": float(gain),
            "offset_degrees": float(offset),
            "r_squared": r_squared,
            "admissible_for_static_scale_or_offset_claim": (
                span_gate and bidirectional_gate
            ),
        },
        "sample_quantized_lag": {
            "best_lag_samples": best_lag,
            "best_lag_seconds": float(best_lag * median_dt),
            "no_lag_rmse_degrees": no_lag_rmse,
            "best_lag_rmse_degrees": best_rmse,
            "is_not_command_application_latency": True,
        },
        "identifiability_verdict": verdict,
    }


def derive_joint_identifiability_report(
    output_root: Path,
    *,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
) -> dict[str, Any]:
    """Materialize one deterministic offline report without simulator execution."""

    contract = load_joint_identifiability_contract(contract_path)
    _require(
        not output_root.exists() or not any(output_root.iterdir()),
        "Identifiability output root is not empty; overwrite is refused.",
    )
    output_root.mkdir(parents=True, exist_ok=True)
    command, actual, velocity, timestamp = _load_source(contract)
    source = contract["source"]
    estimator = contract["estimator"]
    median_dt = float(np.median(np.diff(timestamp)))
    rows = [
        _joint_row(
            joint,
            command[:, index],
            actual[:, index],
            velocity[:, index],
            median_dt,
            estimator,
        )
        for index, joint in enumerate(source["joint_order"])
    ]
    by_joint = {row["joint"]: row for row in rows}
    report = {
        "schema_version": REPORT_SCHEMA,
        "analysis_id": contract["analysis_id"],
        "source_recording_id": source["recording_id"],
        "source_samples_sha256": source["samples_sha256"],
        "exact_action_sha256": source["action_sha256"],
        "sample_count": len(command),
        "sample_interval_median_seconds": median_dt,
        "proof_class": "offline_unloaded_joint_identifiability_diagnostic",
        "joints": rows,
        "shoulder_lift_hypothesis": {
            "global_range_candidate_explains_local_simulator_error": True,
            "joint_specific_range_scale_identified": False,
            "reason": by_joint["shoulder_lift"]["identifiability_verdict"],
            "observed_command_span_degrees": by_joint["shoulder_lift"][
                "command_span_degrees"
            ],
            "next_required_evidence": (
                "preregistered_bidirectional_shoulder_lift_steps_with_independent_"
                "command_application_and_position_read_timestamps"
            ),
        },
        "elbow_hypothesis": {
            "joint_specific_range_scale_identified": False,
            "reason": by_joint["elbow_flex"]["identifiability_verdict"],
            "observed_command_span_degrees": by_joint["elbow_flex"][
                "command_span_degrees"
            ],
            "candidate_rmse_regression_requires_separate_explanation": True,
        },
        "claim_boundary": {
            "affine_fits_are_diagnostic_only": True,
            "sample_lag_is_not_command_application_latency": True,
            "unloaded_motion_does_not_identify_loaded_or_contact_dynamics": True,
            "simulator_parameter_promoted": False,
            "task_score_changed": False,
            "provider_advice_is_evaluator_evidence": False,
        },
        "simulator_replays_used": 0,
        "physical_trials_used": 0,
        "authority": contract["authority"],
    }
    report_path = output_root / "report.json"
    atomic_write_json(report_path, report)
    unsigned_receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_path": str(contract_path.resolve()),
        "contract_sha256": sha256_file(contract_path),
        "source_recording_id": source["recording_id"],
        "source_samples_sha256": source["samples_sha256"],
        "exact_action_sha256": source["action_sha256"],
        "report_path": report_path.name,
        "report_sha256": sha256_file(report_path),
        "proof_class": report["proof_class"],
        "simulator_replays_used": 0,
        "physical_trials_used": 0,
        "simulator_parameter_promoted": False,
        "task_score_changed": False,
        "authority": contract["authority"],
    }
    receipt = {
        **unsigned_receipt,
        "receipt_sha256": canonical_digest(unsigned_receipt),
    }
    atomic_write_json(output_root / "receipt.json", receipt)
    return receipt


__all__ = [
    "CONTRACT_SCHEMA",
    "DEFAULT_CONTRACT_PATH",
    "JointIdentifiabilityError",
    "RECEIPT_SCHEMA",
    "REPORT_SCHEMA",
    "derive_joint_identifiability_report",
    "load_joint_identifiability_contract",
]

"""Deterministic evaluator summary for the four frozen HIL packets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .hil_identifiability import evaluate_hil_packet, load_hil_contract
from .learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    sha256_file,
)
from .scene import ROBOT_JOINTS


SUMMARY_SCHEMA = "sim2claw.current_100mm_hil_evidence_summary.v1"
RECEIPT_SCHEMA = "sim2claw.current_100mm_hil_evidence_receipt.v1"


class HILEvidenceError(RuntimeError):
    """Frozen HIL campaign evidence could not be verified or summarized."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HILEvidenceError(message)


def _best_lag(
    source: np.ndarray,
    target: np.ndarray,
    *,
    sample_hz: float,
    maximum_seconds: float = 0.5,
) -> dict[str, float | int]:
    """Return the deterministic non-negative target lag minimizing RMSE."""

    source = np.asarray(source, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    _require(
        source.ndim == target.ndim == 1
        and source.size == target.size
        and source.size > 2,
        "Lag input shape is invalid.",
    )
    maximum_samples = min(
        source.size - 2,
        max(0, round(float(maximum_seconds) * float(sample_hz))),
    )
    candidates: list[tuple[float, int]] = []
    for lag in range(maximum_samples + 1):
        left = source[: source.size - lag] if lag else source
        right = target[lag:] if lag else target
        rmse = float(np.sqrt(np.mean(np.square(left - right))))
        candidates.append((rmse, lag))
    rmse, lag = min(candidates, key=lambda row: (row[0], row[1]))
    return {
        "lag_samples": lag,
        "lag_seconds": lag / float(sample_hz),
        "lag_aligned_rmse": rmse,
    }


def _percentile(values: np.ndarray, percentile: float) -> float | None:
    return (
        None
        if values.size == 0
        else float(np.percentile(values.astype(np.float64), percentile))
    )


def _packet_summary(
    campaign_root: Path,
    event: dict[str, Any],
    contract: dict[str, Any],
    contract_path: Path,
) -> dict[str, Any]:
    packet_id = str(event["packet_id"])
    session = (campaign_root / packet_id).resolve()
    _require(
        session.is_relative_to(campaign_root.resolve()) and session.is_dir(),
        f"HIL packet directory is unavailable: {packet_id}",
    )
    raw_path = session / "raw_receipt.json"
    evaluation_path = session / "evaluation.json"
    _require(
        sha256_file(raw_path) == event["raw_receipt_sha256"],
        f"HIL raw receipt changed: {packet_id}",
    )
    _require(
        sha256_file(evaluation_path) == event["evaluation_sha256"],
        f"HIL evaluation changed: {packet_id}",
    )
    saved_evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    recomputed = evaluate_hil_packet(raw_path, contract_path)
    _require(
        saved_evaluation == recomputed,
        f"HIL independent evaluation no longer reproduces: {packet_id}",
    )
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    replay_receipt = Path(str(raw["replay_receipt_path"])).resolve()
    _require(
        replay_receipt.is_relative_to(session)
        and replay_receipt.name == "replay_receipt.json",
        f"HIL replay receipt path is invalid: {packet_id}",
    )
    rows = [
        json.loads(line)
        for line in (replay_receipt.parent / "replay_samples.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    rows = [
        row for row in rows if row.get("replay_phase", "source_trace") == "source_trace"
    ]
    packet = next(row for row in contract["packets"] if row["packet_id"] == packet_id)
    target_joint = str(packet["target_joint"])
    target_index = list(ROBOT_JOINTS).index(target_joint)
    requested = np.asarray(
        [row["requested_source_command_degrees"][target_index] for row in rows],
        dtype=np.float64,
    )
    sent = np.asarray(
        [row["follower_command_degrees"][target_index] for row in rows],
        dtype=np.float64,
    )
    actual = np.asarray(
        [row["follower_actual_position_degrees"][target_index] for row in rows],
        dtype=np.float64,
    )
    sample_hz = float(contract["action_materialization"]["sample_hz"])
    requested_error = requested - actual
    sent_error = sent - actual
    refresh_by_time: dict[float, float] = {}
    for row in rows:
        timestamp = row.get("current_telemetry_elapsed_seconds")
        current = row.get("available_motor_current_raw")
        if (
            timestamp is None
            or not isinstance(current, dict)
            or target_joint not in current
            or row.get("current_telemetry_stale", True)
        ):
            continue
        refresh_by_time[round(float(timestamp), 6)] = float(current[target_joint])
    current_values = np.asarray(list(refresh_by_time.values()), dtype=np.float64)
    return {
        "packet_id": packet_id,
        "target_joint": target_joint,
        "admitted": bool(saved_evaluation["admitted"]),
        "verdict": saved_evaluation["verdict"],
        "failures": list(saved_evaluation["failures"]),
        "proof_class": "physical_hil_unloaded_joint_observation",
        "action_tensor_sha256": event["action_tensor_sha256"],
        "sample_count": len(rows),
        "duration_seconds": (len(rows) - 1) / sample_hz,
        "requested_span_degrees": float(np.max(requested) - np.min(requested)),
        "sent_span_degrees": float(np.max(sent) - np.min(sent)),
        "actual_span_degrees": float(np.max(actual) - np.min(actual)),
        "tracking": {
            "requested_to_actual_rmse": float(
                np.sqrt(np.mean(np.square(requested_error)))
            ),
            "requested_to_actual_max_abs": float(np.max(np.abs(requested_error))),
            "sent_to_actual_rmse": float(np.sqrt(np.mean(np.square(sent_error)))),
            "sent_to_actual_max_abs": float(np.max(np.abs(sent_error))),
            "requested_to_actual_best_lag": _best_lag(
                requested, actual, sample_hz=sample_hz
            ),
            "sent_to_actual_best_lag": _best_lag(
                sent, actual, sample_hz=sample_hz
            ),
        },
        "current_raw": {
            "unit": "uncalibrated_motor_register",
            "refresh_count": len(refresh_by_time),
            "minimum": _percentile(current_values, 0),
            "median": _percentile(current_values, 50),
            "maximum": _percentile(current_values, 100),
            "median_absolute": _percentile(np.abs(current_values), 50),
            "p95_absolute": _percentile(np.abs(current_values), 95),
        },
        "safety": {
            "rate_limited_sample_count": sum(
                bool(row.get("rate_limited")) for row in rows
            ),
            "stall_warning_sample_count": sum(
                bool(row.get("stalled")) for row in rows
            ),
            "maximum_bus_retries": max(
                (int(row.get("bus_read_retries_total") or 0) for row in rows),
                default=0,
            ),
            "final_residual_degrees": saved_evaluation[
                "final_residual_degrees"
            ],
            "torque_enabled_after": False,
        },
        "cameras": saved_evaluation["camera_metrics"],
        "raw_receipt_sha256": event["raw_receipt_sha256"],
        "evaluation_sha256": event["evaluation_sha256"],
        "authority": dict(saved_evaluation["authority"]),
    }


def derive_hil_evidence_summary(
    campaign_root: Path,
    *,
    contract_path: Path,
) -> dict[str, Any]:
    """Re-derive the evaluator-owned summary without writing artifacts."""

    campaign_root = campaign_root.resolve()
    contract = load_hil_contract(contract_path)
    campaign_path = campaign_root / "campaign_state.json"
    try:
        campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HILEvidenceError(f"HIL campaign state is unreadable: {error}") from error
    events = campaign.get("events")
    _require(
        isinstance(events, list)
        and len(events) == 4
        and int(campaign["budget"]["used_physical_packet_attempts"]) == 4,
        "HIL campaign must contain exactly four consumed attempts.",
    )
    expected_ids = [row["packet_id"] for row in contract["packets"]]
    _require(
        [row.get("packet_id") for row in events] == expected_ids,
        "HIL packet order or identity changed.",
    )
    packet_summaries = [
        _packet_summary(campaign_root, event, contract, contract_path)
        for event in events
    ]
    admitted = [row["packet_id"] for row in packet_summaries if row["admitted"]]
    rejected = [
        {
            "packet_id": row["packet_id"],
            "failures": row["failures"],
        }
        for row in packet_summaries
        if not row["admitted"]
    ]
    return {
        "schema_version": SUMMARY_SCHEMA,
        "proof_class": "derived_hil_joint_identifiability_evaluation",
        "contract_id": contract["contract_id"],
        "contract_sha256": sha256_file(contract_path),
        "campaign_state_sha256": sha256_file(campaign_path),
        "physical_attempts": 4,
        "completed_trajectories": 4,
        "admitted_packet_count": len(admitted),
        "rejected_packet_count": len(rejected),
        "admitted_packet_ids": admitted,
        "rejected_packets": rejected,
        "packets": packet_summaries,
        "conclusions": {
            "gripper_unloaded_response_identified": "HIL-GRIPPER-05" in admitted,
            "shoulder_lift_range_identified": "HIL-SHOULDER-LIFT-22" in admitted,
            "elbow_fit_admitted": "HIL-ELBOW-FLEX-22" in admitted,
            "wrist_fit_admitted": "HIL-WRIST-FLEX-30" in admitted,
            "contact_or_friction_identified": False,
            "strict_task_consequence_available": False,
            "task_score_changed": False,
        },
        "remaining_observables": [
            "calibrated_current_zero_and_scale",
            "command_application_timestamp",
            "force",
            "deformation",
            "contact_state",
            "metric_wrist_depth",
            "camera_to_gripper_extrinsics",
            "strict_task_consequence",
        ],
        "authority": {
            "unloaded_joint_measurement": True,
            "simulator_parameter_promotion": False,
            "task_success": False,
            "training": False,
            "physical_transfer": False,
        },
    }


def compile_hil_evidence(
    campaign_root: Path,
    output_root: Path,
    *,
    contract_path: Path,
) -> dict[str, Any]:
    campaign_root = campaign_root.resolve()
    output_root = output_root.resolve()
    _require(not output_root.exists(), "HIL evidence output already exists.")
    summary = derive_hil_evidence_summary(
        campaign_root,
        contract_path=contract_path,
    )
    campaign_path = campaign_root / "campaign_state.json"
    admitted = list(summary["admitted_packet_ids"])
    rejected = list(summary["rejected_packets"])
    output_root.mkdir(parents=True)
    summary_path = output_root / "summary.json"
    atomic_write_json(summary_path, summary)
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "proof_class": "derived_hil_joint_identifiability_evaluation",
        "contract_sha256": sha256_file(contract_path),
        "campaign_state_sha256": sha256_file(campaign_path),
        "summary_sha256": sha256_file(summary_path),
        "physical_attempts": 4,
        "admitted_packet_count": len(admitted),
        "rejected_packet_count": len(rejected),
        "adaptive_retries": 0,
        "simulator_replays": 0,
        "provider_calls": 0,
        "task_score_changed": False,
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    atomic_write_json(output_root / "receipt.json", receipt)
    return receipt

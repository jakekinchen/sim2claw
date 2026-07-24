"""Deterministic zero-new-motion analysis of the four HIL telemetry traces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .hil_identifiability import action_tensor_sha256
from .learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    sha256_file,
)
from .paths import REPO_ROOT
from .scene import ROBOT_JOINTS


CONTRACT_SCHEMA = "sim2claw.hil_offline_trace_analysis.v1"
REPORT_SCHEMA = "sim2claw.hil_offline_trace_report.v1"
RECEIPT_SCHEMA = "sim2claw.hil_offline_trace_receipt.v1"
DEFAULT_CONTRACT = (
    REPO_ROOT / "configs/evaluations/hil_offline_trace_analysis_v1.json"
)


class HILTraceAnalysisError(RuntimeError):
    """A frozen source or deterministic analysis boundary failed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HILTraceAnalysisError(message)


def _rooted(repo_root: Path, value: object, *, label: str) -> Path:
    root = repo_root.resolve()
    path = (root / str(value)).resolve()
    _require(path.is_relative_to(root), f"{label} escapes the repository.")
    return path


def load_hil_trace_contract(
    path: Path = DEFAULT_CONTRACT,
) -> dict[str, Any]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HILTraceAnalysisError(
            f"HIL trace-analysis contract is unreadable: {error}"
        ) from error
    _require(
        contract.get("schema_version") == CONTRACT_SCHEMA,
        "HIL trace-analysis schema is unsupported.",
    )
    _require(
        contract.get("status") == "frozen_before_derived_materialization",
        "HIL trace analysis is not frozen.",
    )
    packets = contract.get("packets")
    _require(
        isinstance(packets, list)
        and [row.get("packet_id") for row in packets]
        == [
            "HIL-GRIPPER-05",
            "HIL-SHOULDER-LIFT-22",
            "HIL-ELBOW-FLEX-22",
            "HIL-WRIST-FLEX-30",
        ],
        "HIL trace-analysis packet identities changed.",
    )
    authority = contract.get("authority")
    _require(
        isinstance(authority, Mapping)
        and authority
        and all(value is False for value in authority.values()),
        "HIL trace analysis widened authority.",
    )
    claims = contract.get("claim_gates")
    _require(
        isinstance(claims, Mapping)
        and claims.get("current_is_calibrated_force") is False
        and claims.get("sample_lag_is_command_application_latency") is False
        and claims.get("strict_task_consequence_available") is False,
        "HIL trace-analysis claim boundary changed.",
    )
    return contract


def _best_lag(
    requested: np.ndarray,
    actual: np.ndarray,
    candidates: list[int],
    sample_hz: float,
) -> dict[str, float | int]:
    scored: list[tuple[float, int]] = []
    for lag in candidates:
        _require(lag >= 0, "Lag candidates must be non-negative.")
        source = requested[:-lag] if lag else requested
        observed = actual[lag:] if lag else actual
        _require(len(source) >= 3, "Lag candidate leaves too few samples.")
        scored.append(
            (
                float(np.sqrt(np.mean(np.square(source - observed)))),
                lag,
            )
        )
    rmse, lag = min(scored, key=lambda row: (row[0], row[1]))
    return {
        "samples": lag,
        "seconds": lag / sample_hz,
        "rmse_degrees": rmse,
        "is_not_command_application_latency": True,
    }


def _contiguous_segments(mask: np.ndarray) -> list[tuple[int, int]]:
    indices = np.flatnonzero(mask)
    if indices.size == 0:
        return []
    starts = [int(indices[0])]
    ends: list[int] = []
    for previous, current in zip(indices[:-1], indices[1:], strict=True):
        if current != previous + 1:
            ends.append(int(previous) + 1)
            starts.append(int(current))
    ends.append(int(indices[-1]) + 1)
    return list(zip(starts, ends, strict=True))


def _rmse(values: np.ndarray) -> float | None:
    return (
        None if values.size == 0 else float(np.sqrt(np.mean(np.square(values))))
    )


def _correlation(left: np.ndarray, right: np.ndarray) -> float | None:
    if (
        left.size < 3
        or right.size != left.size
        or float(np.std(left)) <= 1e-12
        or float(np.std(right)) <= 1e-12
    ):
        return None
    return float(np.corrcoef(left, right)[0, 1])


def _packet_report(
    *,
    repo_root: Path,
    campaign_root: Path,
    packet_contract: Mapping[str, Any],
    analysis: Mapping[str, Any],
) -> dict[str, Any]:
    packet_id = str(packet_contract["packet_id"])
    session = (campaign_root / packet_id).resolve()
    _require(
        session.is_relative_to(campaign_root) and session.is_dir(),
        f"HIL packet directory is unavailable: {packet_id}",
    )
    raw_path = session / "raw_receipt.json"
    evaluation_path = session / "evaluation.json"
    _require(
        sha256_file(raw_path) == packet_contract["raw_receipt_sha256"],
        f"HIL raw receipt changed: {packet_id}",
    )
    _require(
        sha256_file(evaluation_path) == packet_contract["evaluation_sha256"],
        f"HIL evaluation changed: {packet_id}",
    )
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    replay_path = Path(str(raw["replay_receipt_path"])).resolve()
    _require(
        replay_path.is_relative_to(session)
        and replay_path.name == "replay_receipt.json",
        f"HIL replay receipt path is invalid: {packet_id}",
    )
    rows = [
        json.loads(line)
        for line in (replay_path.parent / "replay_samples.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    rows = [
        row for row in rows if row.get("replay_phase", "source_trace") == "source_trace"
    ]
    target_joint = str(packet_contract["target_joint"])
    target_index = list(ROBOT_JOINTS).index(target_joint)
    requested_all = np.ascontiguousarray(
        [row["requested_source_command_degrees"] for row in rows],
        dtype="<f8",
    )
    _require(
        action_tensor_sha256(requested_all)
        == packet_contract["action_tensor_sha256"]
        == raw["action_tensor_sha256"],
        f"HIL action tensor changed: {packet_id}",
    )
    requested = requested_all[:, target_index]
    sent = np.asarray(
        [row["follower_command_degrees"][target_index] for row in rows],
        dtype=np.float64,
    )
    actual = np.asarray(
        [row["follower_actual_position_degrees"][target_index] for row in rows],
        dtype=np.float64,
    )
    velocity = np.asarray(
        [row["follower_actual_velocity_degrees_s"][target_index] for row in rows],
        dtype=np.float64,
    )
    sample_hz = float(analysis["sample_hz"])
    lag = _best_lag(
        requested,
        actual,
        [int(value) for value in analysis["lag_candidates_samples"]],
        sample_hz,
    )
    lag_samples = int(lag["samples"])
    aligned_requested = requested[:-lag_samples] if lag_samples else requested
    aligned_actual = actual[lag_samples:] if lag_samples else actual
    aligned_velocity = velocity[lag_samples:] if lag_samples else velocity
    command_velocity = np.gradient(aligned_requested) * sample_hz
    residual = aligned_requested - aligned_actual
    direction_threshold = float(
        analysis["direction_velocity_threshold_degrees_s"]
    )
    positive = command_velocity > direction_threshold
    negative = command_velocity < -direction_threshold
    directional: dict[str, Any] = {}
    for name, mask in (("positive", positive), ("negative", negative)):
        directional[name] = {
            "sample_count": int(np.count_nonzero(mask)),
            "rmse_degrees": _rmse(residual[mask]),
            "mean_residual_degrees": (
                float(np.mean(residual[mask])) if np.any(mask) else None
            ),
            "mean_actual_velocity_degrees_s": (
                float(np.mean(aligned_velocity[mask])) if np.any(mask) else None
            ),
        }
    positive_mean = directional["positive"]["mean_residual_degrees"]
    negative_mean = directional["negative"]["mean_residual_degrees"]
    directional_gap = (
        abs(float(positive_mean) - float(negative_mean))
        if positive_mean is not None and negative_mean is not None
        else None
    )

    changes = np.diff(requested, prepend=requested[0])
    epsilon = float(analysis["command_change_epsilon_degrees"])
    sign = np.zeros(len(requested), dtype=np.int8)
    sign[changes > epsilon] = 1
    sign[changes < -epsilon] = -1
    traversals: list[dict[str, Any]] = []
    minimum_traversal = int(analysis["minimum_traversal_samples"])
    for direction, direction_name in ((1, "positive"), (-1, "negative")):
        for start, end in _contiguous_segments(sign == direction):
            if end - start < minimum_traversal:
                continue
            traversals.append(
                {
                    "direction": direction_name,
                    "start_sample": start,
                    "end_sample_exclusive": end,
                    "requested_span_degrees": float(
                        np.ptp(requested[start:end])
                    ),
                    "actual_span_degrees": float(np.ptp(actual[start:end])),
                    "rmse_degrees": _rmse(requested[start:end] - actual[start:end]),
                }
            )
    traversals.sort(key=lambda row: int(row["start_sample"]))

    stable = np.abs(changes) <= epsilon
    plateau_rows: list[dict[str, Any]] = []
    settle = int(analysis["plateau_settle_samples"])
    minimum_plateau = int(analysis["minimum_plateau_samples_after_settle"])
    for start, end in _contiguous_segments(stable):
        settled_start = start + settle
        if end - settled_start < minimum_plateau:
            continue
        plateau_rows.append(
            {
                "start_sample": settled_start,
                "end_sample_exclusive": end,
                "requested_mean_degrees": float(
                    np.mean(requested[settled_start:end])
                ),
                "actual_mean_degrees": float(np.mean(actual[settled_start:end])),
                "mean_residual_degrees": float(
                    np.mean(requested[settled_start:end] - actual[settled_start:end])
                ),
                "actual_std_degrees": float(np.std(actual[settled_start:end])),
            }
        )
    distinct_levels = sorted(
        {
            round(float(row["requested_mean_degrees"]), 6)
            for row in plateau_rows
        }
    )
    positive_traversals = sum(
        row["direction"] == "positive" for row in traversals
    )
    negative_traversals = sum(
        row["direction"] == "negative" for row in traversals
    )
    fit_gate = (
        evaluation.get("admitted") is True
        and len(distinct_levels) >= 3
        and positive_traversals >= 2
        and negative_traversals >= 2
    )
    plateau_fit: dict[str, Any] = {
        "distinct_requested_levels_degrees": distinct_levels,
        "positive_traversal_count": positive_traversals,
        "negative_traversal_count": negative_traversals,
        "admissible_for_scale_offset_claim": fit_gate,
        "gain": None,
        "offset_degrees": None,
    }
    if len(distinct_levels) >= 2 and plateau_rows:
        plateau_requested = np.asarray(
            [row["requested_mean_degrees"] for row in plateau_rows],
            dtype=np.float64,
        )
        plateau_actual = np.asarray(
            [row["actual_mean_degrees"] for row in plateau_rows],
            dtype=np.float64,
        )
        design = np.column_stack(
            [plateau_requested, np.ones(len(plateau_requested))]
        )
        gain, offset = np.linalg.lstsq(design, plateau_actual, rcond=None)[0]
        plateau_fit["gain"] = float(gain)
        plateau_fit["offset_degrees"] = float(offset)

    reset_window = int(analysis["reset_window_samples"])
    _require(
        len(actual) >= reset_window * 2,
        f"HIL packet is too short for reset audit: {packet_id}",
    )
    initial_position = float(np.median(actual[:reset_window]))
    final_position = float(np.median(actual[-reset_window:]))

    refresh_rows: dict[float, tuple[float, float, float]] = {}
    for row in rows:
        timestamp = row.get("current_telemetry_elapsed_seconds")
        current = row.get("available_motor_current_raw")
        if (
            timestamp is None
            or not isinstance(current, Mapping)
            or target_joint not in current
            or row.get("current_telemetry_stale", True)
        ):
            continue
        refresh_rows[round(float(timestamp), 6)] = (
            float(current[target_joint]),
            abs(
                float(row["requested_source_command_degrees"][target_index])
                - float(row["follower_actual_position_degrees"][target_index])
            ),
            abs(float(row["follower_actual_velocity_degrees_s"][target_index])),
        )
    refresh = np.asarray(list(refresh_rows.values()), dtype=np.float64)
    current_values = refresh[:, 0] if refresh.size else np.asarray([])
    refresh_error = refresh[:, 1] if refresh.size else np.asarray([])
    refresh_velocity = refresh[:, 2] if refresh.size else np.asarray([])
    return {
        "packet_id": packet_id,
        "target_joint": target_joint,
        "admitted": evaluation.get("admitted") is True,
        "packet_verdict": evaluation.get("verdict"),
        "packet_failures": list(evaluation.get("failures") or []),
        "action_tensor_sha256": packet_contract["action_tensor_sha256"],
        "sample_count": len(rows),
        "sample_hz": sample_hz,
        "sample_quantized_lag": lag,
        "directional_tracking": {
            **directional,
            "mean_residual_gap_degrees": directional_gap,
            "is_not_backlash_or_compliance_proof": True,
        },
        "traversals": traversals,
        "plateaus": plateau_rows,
        "plateau_scale_offset_diagnostic": plateau_fit,
        "reset_return_audit": {
            "window_samples": reset_window,
            "initial_actual_median_degrees": initial_position,
            "final_actual_median_degrees": final_position,
            "final_minus_initial_degrees": final_position - initial_position,
            "is_single_packet_return_residual_not_reset_drift_proof": True,
        },
        "fresh_current_association": {
            "unit": "uncalibrated_motor_register",
            "refresh_count": len(refresh_rows),
            "absolute_current_p95": (
                float(np.percentile(np.abs(current_values), 95))
                if current_values.size
                else None
            ),
            "absolute_current_maximum": (
                float(np.max(np.abs(current_values)))
                if current_values.size
                else None
            ),
            "correlation_absolute_current_to_absolute_error": _correlation(
                np.abs(current_values), refresh_error
            ),
            "correlation_absolute_current_to_absolute_velocity": _correlation(
                np.abs(current_values), refresh_velocity
            ),
            "is_diagnostic_not_force_or_torque": True,
        },
        "safety": {
            "rate_limited_sample_count": sum(
                bool(row.get("rate_limited")) for row in rows
            ),
            "stall_warning_sample_count": sum(
                bool(row.get("stalled")) for row in rows
            ),
            "bus_retry_maximum": max(
                (int(row.get("bus_read_retries_total") or 0) for row in rows),
                default=0,
            ),
        },
    }


def derive_hil_trace_report(
    output_root: Path,
    *,
    contract_path: Path = DEFAULT_CONTRACT,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Materialize one deterministic report without robot or simulator execution."""

    output_root = output_root.resolve()
    _require(
        not output_root.exists() or not any(output_root.iterdir()),
        "HIL trace-analysis output root is not empty; overwrite is refused.",
    )
    contract = load_hil_trace_contract(contract_path)
    campaign_root = _rooted(
        repo_root,
        contract["source_campaign_root"],
        label="HIL source campaign",
    )
    campaign_path = campaign_root / "campaign_state.json"
    _require(
        sha256_file(campaign_path) == contract["source_campaign_sha256"],
        "HIL campaign state changed.",
    )
    packets = [
        _packet_report(
            repo_root=repo_root,
            campaign_root=campaign_root,
            packet_contract=row,
            analysis=contract["analysis"],
        )
        for row in contract["packets"]
    ]
    by_id = {row["packet_id"]: row for row in packets}
    elbow = by_id["HIL-ELBOW-FLEX-22"]
    report = {
        "schema_version": REPORT_SCHEMA,
        "proof_class": contract["proof_class"],
        "contract_id": contract["contract_id"],
        "contract_sha256": sha256_file(contract_path),
        "source_campaign_sha256": sha256_file(campaign_path),
        "packets": packets,
        "cross_packet_findings": {
            "all_four_have_sample_quantized_response_lag": True,
            "gripper_repeated_traversals_available": (
                len(by_id["HIL-GRIPPER-05"]["traversals"]) >= 10
            ),
            "elbow_current_and_stall_signature_is_distinct": (
                float(
                    elbow["fresh_current_association"][
                        "absolute_current_p95"
                    ]
                    or 0
                )
                > max(
                    float(
                        row["fresh_current_association"][
                            "absolute_current_p95"
                        ]
                        or 0
                    )
                    for row in packets
                    if row["packet_id"] != "HIL-ELBOW-FLEX-22"
                )
                and elbow["safety"]["stall_warning_sample_count"] > 0
            ),
            "any_scale_offset_fit_admissible": any(
                row["plateau_scale_offset_diagnostic"][
                    "admissible_for_scale_offset_claim"
                ]
                for row in packets
            ),
            "strict_task_consequence_available": False,
            "simulator_change_warranted": False,
        },
        "remaining_prerequisites": [
            "independent_command_created_sent_and_actuator_ack_timestamps",
            "independent_position_and_current_read_timestamps",
            "current_zero_scale_and_torque_provenance",
            "camera_exposure_timestamps_and_drop_flags",
            "at_least_three_quasi_static_levels_and_two_traversals_per_direction",
            "known_load_force_or_contact_state",
            "strict_task_and_end_effector_consequence",
        ],
        "claim_boundary": {
            "directional_residual_is_diagnostic_only": True,
            "plateau_affine_fit_is_diagnostic_only_unless_gate_passes": True,
            "raw_current_is_not_force_or_torque": True,
            "sample_lag_is_not_command_application_latency": True,
            "no_simulator_parameter_promoted": True,
            "task_score_changed": False,
        },
        "budget": {
            "additional_physical_attempts": 0,
            "additional_simulator_replays": 0,
            "provider_calls": 0,
        },
        "authority": contract["authority"],
    }
    output_root.mkdir(parents=True, exist_ok=True)
    report_path = output_root / "report.json"
    atomic_write_json(report_path, report)
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "proof_class": contract["proof_class"],
        "contract_sha256": sha256_file(contract_path),
        "source_campaign_sha256": sha256_file(campaign_path),
        "report_sha256": sha256_file(report_path),
        "packet_count": 4,
        "additional_physical_attempts": 0,
        "additional_simulator_replays": 0,
        "provider_calls": 0,
        "simulator_parameter_promoted": False,
        "task_score_changed": False,
        "authority": contract["authority"],
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    atomic_write_json(output_root / "receipt.json", receipt)
    return receipt


__all__ = [
    "CONTRACT_SCHEMA",
    "DEFAULT_CONTRACT",
    "HILTraceAnalysisError",
    "RECEIPT_SCHEMA",
    "REPORT_SCHEMA",
    "derive_hil_trace_report",
    "load_hil_trace_contract",
]

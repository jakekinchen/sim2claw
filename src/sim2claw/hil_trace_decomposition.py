"""Requested-versus-applied decomposition of the frozen four-packet HIL run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .hil_identifiability import action_tensor_sha256
from .hil_trace_analysis import (
    load_hil_trace_contract,
    load_verified_hil_packet_trace,
)
from .learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    sha256_file,
)
from .paths import REPO_ROOT
from .scene import ROBOT_JOINTS


CONTRACT_SCHEMA = "sim2claw.hil_trace_decomposition.v2"
REPORT_SCHEMA = "sim2claw.hil_trace_decomposition_report.v2"
RECEIPT_SCHEMA = "sim2claw.hil_trace_decomposition_receipt.v2"
DEFAULT_CONTRACT = (
    REPO_ROOT / "configs/evaluations/hil_trace_decomposition_v2.json"
)


class HILTraceDecompositionError(RuntimeError):
    """A source binding or deterministic decomposition gate failed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HILTraceDecompositionError(message)


def _rooted(repo_root: Path, value: object, *, label: str) -> Path:
    root = repo_root.resolve()
    path = (root / str(value)).resolve()
    _require(path.is_relative_to(root), f"{label} escapes the repository.")
    return path


def load_hil_trace_decomposition_contract(
    path: Path = DEFAULT_CONTRACT,
) -> dict[str, Any]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HILTraceDecompositionError(
            f"HIL trace-decomposition contract is unreadable: {error}"
        ) from error
    _require(
        contract.get("schema_version") == CONTRACT_SCHEMA,
        "HIL trace-decomposition schema is unsupported.",
    )
    _require(
        contract.get("status")
        == "frozen_after_v1_observation_before_v2_materialization",
        "HIL trace decomposition is not frozen.",
    )
    context = contract.get("evidence_context")
    _require(
        isinstance(context, Mapping)
        and context.get("v1_results_were_visible_before_this_v2_contract")
        is True
        and context.get("external_advisory_is_evaluator_evidence") is False,
        "HIL trace-decomposition provenance is incomplete.",
    )
    authority = contract.get("authority")
    _require(
        isinstance(authority, Mapping)
        and authority
        and all(value is False for value in authority.values()),
        "HIL trace decomposition widened authority.",
    )
    gates = contract.get("claim_gates")
    _require(
        isinstance(gates, Mapping)
        and gates.get("applied_action_byte_identity_requires_array_equal")
        is True
        and gates.get("current_is_calibrated_force_or_torque") is False
        and gates.get("strict_task_consequence_available") is False,
        "HIL trace-decomposition claim gates changed.",
    )
    return contract


def _rmse(values: np.ndarray) -> float | None:
    if values.size == 0:
        return None
    return float(np.sqrt(np.mean(np.square(values))))


def _segments(mask: np.ndarray) -> list[tuple[int, int]]:
    indices = np.flatnonzero(mask)
    if not len(indices):
        return []
    starts = [int(indices[0])]
    ends: list[int] = []
    for previous, current in zip(indices[:-1], indices[1:], strict=True):
        if int(current) != int(previous) + 1:
            ends.append(int(previous) + 1)
            starts.append(int(current))
    ends.append(int(indices[-1]) + 1)
    return list(zip(starts, ends, strict=True))


def _first_index(mask: Sequence[bool]) -> int | None:
    return next((index for index, value in enumerate(mask) if value), None)


def _lag_profile(
    requested: np.ndarray,
    actual: np.ndarray,
    *,
    lag_candidates: Sequence[int],
    edge_trim: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_lag in lag_candidates:
        lag = int(raw_lag)
        _require(lag >= 0, "Lag candidates must be non-negative.")
        source = requested[:-lag] if lag else requested
        observed = actual[lag:] if lag else actual
        if edge_trim:
            source = source[edge_trim:-edge_trim]
            observed = observed[edge_trim:-edge_trim]
        _require(
            len(source) >= 3,
            "Lag and edge trim leave too few decomposition samples.",
        )
        rows.append(
            {
                "lag_samples": lag,
                "sample_count": len(source),
                "rmse_degrees": _rmse(source - observed),
            }
        )
    return rows


def _best_profile_row(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return dict(
        min(
            rows,
            key=lambda row: (
                float(row["rmse_degrees"]),
                int(row["lag_samples"]),
            ),
        )
    )


def _traversal_rows(
    requested: np.ndarray,
    *,
    epsilon: float,
    minimum_samples: int,
) -> list[dict[str, Any]]:
    changes = np.diff(requested, prepend=requested[0])
    sign = np.zeros(len(requested), dtype=np.int8)
    sign[changes > epsilon] = 1
    sign[changes < -epsilon] = -1
    rows: list[dict[str, Any]] = []
    for direction, name in ((1, "positive"), (-1, "negative")):
        for start, end in _segments(sign == direction):
            if end - start < minimum_samples:
                continue
            rows.append(
                {
                    "direction": name,
                    "start_sample": start,
                    "end_sample_exclusive": end,
                    "command_span_degrees": float(
                        np.ptp(requested[start:end])
                    ),
                }
            )
    rows.sort(key=lambda row: int(row["start_sample"]))
    return rows


def _plateau_levels(
    requested: np.ndarray,
    *,
    epsilon: float,
    minimum_samples: int,
) -> list[float]:
    stable = np.abs(np.diff(requested, prepend=requested[0])) <= epsilon
    levels = [
        round(float(np.mean(requested[start:end])), 6)
        for start, end in _segments(stable)
        if end - start >= minimum_samples
    ]
    return sorted(set(levels))


def _reversal_count(changes: np.ndarray, epsilon: float) -> int:
    signs = np.sign(changes[np.abs(changes) > epsilon])
    if len(signs) < 2:
        return 0
    return int(np.count_nonzero(signs[1:] != signs[:-1]))


def _channel_identifiability(
    requested: np.ndarray,
    sent: np.ndarray,
    actual: np.ndarray,
    rows: Sequence[Mapping[str, Any]],
    *,
    joint: str,
    packet_admitted: bool,
    target_joint: str,
    analysis: Mapping[str, Any],
) -> dict[str, Any]:
    epsilon = float(analysis["command_change_epsilon_degrees"])
    changes = np.diff(requested, prepend=requested[0])
    positive = changes > epsilon
    negative = changes < -epsilon
    traversals = _traversal_rows(
        requested,
        epsilon=epsilon,
        minimum_samples=int(analysis["minimum_traversal_samples"]),
    )
    positive_traversals = [
        row for row in traversals if row["direction"] == "positive"
    ]
    negative_traversals = [
        row for row in traversals if row["direction"] == "negative"
    ]
    levels = _plateau_levels(
        requested,
        epsilon=epsilon,
        minimum_samples=int(analysis["minimum_plateau_samples"]),
    )
    modified = np.abs(requested - sent) > 1e-12
    gateway_modified = np.abs(requested - sent) > 0.25
    stalled = np.asarray(
        [joint in (row.get("stalled_joints") or []) for row in rows],
        dtype=bool,
    )
    contaminated = gateway_modified | stalled
    eligibility_failures: list[str] = []
    if not packet_admitted:
        eligibility_failures.append("packet_rejected")
    if joint != target_joint:
        eligibility_failures.append("joint_not_targeted_by_packet")
    if len(levels) < 3:
        eligibility_failures.append("fewer_than_three_distributed_levels")
    if len(positive_traversals) < 2:
        eligibility_failures.append("fewer_than_two_positive_traversals")
    if len(negative_traversals) < 2:
        eligibility_failures.append("fewer_than_two_negative_traversals")
    if np.any(contaminated):
        eligibility_failures.append("gateway_modified_or_fault_contaminated")
    range_status = (
        "eligible_for_diagnostic_fit_not_promotion"
        if not eligibility_failures
        else "not_identified"
    )
    return {
        "joint": joint,
        "is_packet_target_joint": joint == target_joint,
        "command_span_degrees": float(np.ptp(requested)),
        "actual_span_degrees": float(np.ptp(actual)),
        "positive_change_count": int(np.count_nonzero(positive)),
        "negative_change_count": int(np.count_nonzero(negative)),
        "positive_command_travel_degrees": float(np.sum(changes[positive])),
        "negative_command_travel_degrees": float(
            np.sum(np.abs(changes[negative]))
        ),
        "positive_traversal_count": len(positive_traversals),
        "negative_traversal_count": len(negative_traversals),
        "maximum_positive_traversal_span_degrees": (
            max(
                float(row["command_span_degrees"])
                for row in positive_traversals
            )
            if positive_traversals
            else 0.0
        ),
        "maximum_negative_traversal_span_degrees": (
            max(
                float(row["command_span_degrees"])
                for row in negative_traversals
            )
            if negative_traversals
            else 0.0
        ),
        "reversal_count": _reversal_count(changes, epsilon),
        "plateau_count": len(levels),
        "distinct_plateau_levels_degrees": levels,
        "byte_modified_sample_fraction": float(np.mean(modified)),
        "fault_contaminated_sample_fraction": float(np.mean(contaminated)),
        "saturation_fraction": None,
        "saturation_status": "unavailable_no_per_sample_limit_margin",
        "identifiability": {
            "range_scale": range_status,
            "range_scale_reasons": eligibility_failures,
            "zero_offset": (
                "diagnostic_plateaus_only"
                if packet_admitted and joint == target_joint and levels
                else "not_identified"
            ),
            "latency": "not_identified_no_actuator_application_timestamp",
            "dynamic_response": "not_identified_single_command_speed_profile",
            "backlash_hysteresis": (
                "diagnostic_directional_residual_only"
                if packet_admitted
                and joint == target_joint
                and _reversal_count(changes, epsilon) > 0
                else "not_identified"
            ),
            "reset_drift": "not_identified_single_reference_return",
        },
    }


def _residual_partitions(
    requested: np.ndarray,
    actual: np.ndarray,
    *,
    lag_samples: int,
    sample_hz: float,
    motion_threshold: float,
) -> dict[str, Any]:
    source = requested[:-lag_samples] if lag_samples else requested
    observed = actual[lag_samples:] if lag_samples else actual
    residual = source - observed
    command_velocity = np.gradient(source) * sample_hz
    masks = {
        "motion": np.abs(command_velocity) > motion_threshold,
        "dwell": np.abs(command_velocity) <= motion_threshold,
        "positive": command_velocity > motion_threshold,
        "negative": command_velocity < -motion_threshold,
    }
    return {
        name: {
            "sample_count": int(np.count_nonzero(mask)),
            "rmse_degrees": _rmse(residual[mask]),
            "mean_residual_degrees": (
                float(np.mean(residual[mask])) if np.any(mask) else None
            ),
        }
        for name, mask in masks.items()
    }


def _packet_decomposition(
    *,
    repo_root: Path,
    campaign_root: Path,
    packet_contract: Mapping[str, Any],
    analysis: Mapping[str, Any],
) -> dict[str, Any]:
    trace = load_verified_hil_packet_trace(
        repo_root=repo_root,
        campaign_root=campaign_root,
        packet_contract=packet_contract,
    )
    rows = trace["rows"]
    requested = np.asarray(trace["requested_action"], dtype="<f8")
    sent = np.ascontiguousarray(
        [row["follower_command_degrees"] for row in rows],
        dtype="<f8",
    )
    actual = np.asarray(
        [row["follower_actual_position_degrees"] for row in rows],
        dtype=np.float64,
    )
    _require(
        requested.shape == sent.shape == actual.shape,
        "HIL requested, applied, and actual trace shapes differ.",
    )
    target_joint = str(packet_contract["target_joint"])
    target_index = list(ROBOT_JOINTS).index(target_joint)
    packet_admitted = trace["evaluation"].get("admitted") is True
    byte_modified_by_sample = np.any(requested != sent, axis=1)
    gateway_modified_by_sample = np.asarray(
        [bool(row.get("rate_limited")) for row in rows],
        dtype=bool,
    )
    stalled_by_sample = np.asarray(
        [bool(row.get("stalled")) for row in rows],
        dtype=bool,
    )
    first_gateway_modified = _first_index(gateway_modified_by_sample.tolist())
    first_stall_warning = _first_index(stalled_by_sample.tolist())
    target_error = np.abs(
        requested[:, target_index] - actual[:, target_index]
    )
    target_velocity = np.abs(
        np.asarray(
            [
                row["follower_actual_velocity_degrees_s"][target_index]
                for row in rows
            ],
            dtype=np.float64,
        )
    )
    velocity_collapse = (
        target_error
        > float(analysis["tracking_error_event_threshold_degrees"])
    ) & (
        target_velocity
        <= float(analysis["velocity_collapse_threshold_degrees_s"])
    )
    first_velocity_collapse = _first_index(velocity_collapse.tolist())
    fresh_current: list[tuple[int, float]] = []
    seen_current_times: set[float] = set()
    for index, row in enumerate(rows):
        timestamp = row.get("current_telemetry_elapsed_seconds")
        current = row.get("available_motor_current_raw")
        if (
            timestamp is None
            or row.get("current_telemetry_stale", True)
            or not isinstance(current, Mapping)
            or target_joint not in current
        ):
            continue
        key = round(float(timestamp), 6)
        if key in seen_current_times:
            continue
        seen_current_times.add(key)
        fresh_current.append((index, float(current[target_joint])))
    peak_current = (
        max(abs(value) for _, value in fresh_current)
        if fresh_current
        else None
    )
    first_peak_current = (
        next(
            index
            for index, value in fresh_current
            if abs(value) == peak_current
        )
        if peak_current is not None
        else None
    )
    event_samples = {
        "first_gateway_rate_limit": first_gateway_modified,
        "first_velocity_collapse_under_tracking_error": first_velocity_collapse,
        "first_peak_fresh_raw_current": first_peak_current,
        "first_stall_warning": first_stall_warning,
    }
    event_order = [
        {"event": name, "sample_index": index}
        for name, index in sorted(
            (
                (name, index)
                for name, index in event_samples.items()
                if index is not None
            ),
            key=lambda row: (int(row[1]), row[0]),
        )
    ]
    lag_candidates = [int(value) for value in analysis["lag_candidates_samples"]]
    edge_trims = [int(value) for value in analysis["edge_trim_samples"]]
    target_requested = requested[:, target_index]
    target_actual = actual[:, target_index]
    lag_profiles = {
        str(trim): _lag_profile(
            target_requested,
            target_actual,
            lag_candidates=lag_candidates,
            edge_trim=trim,
        )
        for trim in edge_trims
    }
    best = _best_profile_row(lag_profiles["0"])
    pre_fault_end = min(
        [
            value
            for value in (first_gateway_modified, first_stall_warning)
            if value is not None
        ],
        default=len(rows),
    )
    pre_fault_profile = (
        _lag_profile(
            target_requested[:pre_fault_end],
            target_actual[:pre_fault_end],
            lag_candidates=[
                lag for lag in lag_candidates if pre_fault_end - lag >= 3
            ],
            edge_trim=0,
        )
        if pre_fault_end >= 3
        else []
    )
    channels = [
        _channel_identifiability(
            requested[:, index],
            sent[:, index],
            actual[:, index],
            rows,
            joint=joint,
            packet_admitted=packet_admitted,
            target_joint=target_joint,
            analysis=analysis,
        )
        for index, joint in enumerate(ROBOT_JOINTS)
    ]
    return {
        "packet_id": trace["packet_id"],
        "target_joint": target_joint,
        "packet_admitted": packet_admitted,
        "packet_verdict": trace["evaluation"].get("verdict"),
        "action_identity": {
            "source_action_sha256": packet_contract["action_tensor_sha256"],
            "requested_action_sha256": action_tensor_sha256(requested),
            "applied_action_sha256": action_tensor_sha256(sent),
            "action_space_id": "so101_joint_position_degrees_v1",
            "dtype": "float64_little_endian",
            "shape": list(requested.shape),
            "joint_order": list(ROBOT_JOINTS),
            "units": "degrees_except_normalized_gripper",
            "applied_action_byte_identical": bool(
                np.array_equal(requested, sent)
            ),
            "byte_modified_sample_count": int(
                np.count_nonzero(byte_modified_by_sample)
            ),
            "gateway_rate_limited_sample_count": int(
                np.count_nonzero(gateway_modified_by_sample)
            ),
            "first_gateway_modified_sample": first_gateway_modified,
            "modification_reason": (
                "gateway_rate_limit"
                if first_gateway_modified is not None
                else None
            ),
        },
        "fault_chronology": {
            "events": event_order,
            "event_samples": event_samples,
            "fresh_raw_current_peak": peak_current,
            "current_unit": "uncalibrated_motor_register",
            "is_index_aligned_correlation_not_causality": True,
            "pre_fault_window_end_exclusive": pre_fault_end,
            "pre_fault_best_lag": (
                _best_profile_row(pre_fault_profile)
                if pre_fault_profile
                else None
            ),
        },
        "lag_analysis": {
            "native_sample_period_seconds": 1.0
            / float(analysis["sample_hz"]),
            "profiles_by_edge_trim_samples": lag_profiles,
            "best_full_trace": best,
            "residual_partitions_at_best_lag": _residual_partitions(
                target_requested,
                target_actual,
                lag_samples=int(best["lag_samples"]),
                sample_hz=float(analysis["sample_hz"]),
                motion_threshold=float(
                    analysis["motion_velocity_threshold_degrees_s"]
                ),
            ),
            "is_sample_quantized_alignment_not_actuator_latency": True,
        },
        "joint_identifiability_matrix": channels,
        "claim_boundary": {
            "requested_action_is_not_applied_action_when_gateway_modifies": True,
            "actual_span_is_not_range_scale_identification": True,
            "raw_current_is_not_force_or_torque": True,
            "lag_profile_is_not_actuator_latency_without_independent_timing": True,
        },
    }


def derive_hil_trace_decomposition_payload(
    *,
    contract_path: Path = DEFAULT_CONTRACT,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Re-derive the v2 report without robot, simulator, or provider execution."""

    root = repo_root.resolve()
    contract = load_hil_trace_decomposition_contract(contract_path)
    source = contract["source"]
    v1_contract_path = _rooted(
        root, source["v1_contract_path"], label="HIL v1 contract"
    )
    v1_report_path = _rooted(
        root, source["v1_report_path"], label="HIL v1 report"
    )
    v1_receipt_path = _rooted(
        root, source["v1_receipt_path"], label="HIL v1 receipt"
    )
    for path, expected, label in (
        (v1_contract_path, source["v1_contract_sha256"], "HIL v1 contract"),
        (v1_report_path, source["v1_report_sha256"], "HIL v1 report"),
        (v1_receipt_path, source["v1_receipt_sha256"], "HIL v1 receipt"),
    ):
        _require(path.is_file(), f"{label} is unavailable.")
        _require(sha256_file(path) == expected, f"{label} hash changed.")
    v1_contract = load_hil_trace_contract(v1_contract_path)
    campaign_root = _rooted(
        root, source["campaign_root"], label="HIL source campaign"
    )
    campaign_path = campaign_root / "campaign_state.json"
    _require(
        sha256_file(campaign_path) == source["campaign_state_sha256"],
        "HIL source campaign hash changed.",
    )
    packets = [
        _packet_decomposition(
            repo_root=root,
            campaign_root=campaign_root,
            packet_contract=packet,
            analysis=contract["analysis"],
        )
        for packet in v1_contract["packets"]
    ]
    modified = [
        row["packet_id"]
        for row in packets
        if not row["action_identity"]["applied_action_byte_identical"]
    ]
    return {
        "schema_version": REPORT_SCHEMA,
        "proof_class": contract["proof_class"],
        "contract_id": contract["contract_id"],
        "contract_sha256": sha256_file(contract_path),
        "source_campaign_sha256": sha256_file(campaign_path),
        "v1_report_sha256": sha256_file(v1_report_path),
        "packets": packets,
        "cross_packet_findings": {
            "requested_and_applied_actions_are_separate": True,
            "packets_with_nonidentical_applied_action": modified,
            "all_scale_offset_latency_dynamics_backlash_reset_claims_closed": all(
                all(
                    channel["identifiability"]["range_scale"]
                    == "not_identified"
                    and channel["identifiability"]["latency"].startswith(
                        "not_identified"
                    )
                    and channel["identifiability"]["dynamic_response"].startswith(
                        "not_identified"
                    )
                    and channel["identifiability"]["zero_offset"]
                    in {"not_identified", "diagnostic_plateaus_only"}
                    and channel["identifiability"]["backlash_hysteresis"]
                    in {
                        "not_identified",
                        "diagnostic_directional_residual_only",
                    }
                    and channel["identifiability"]["reset_drift"].startswith(
                        "not_identified"
                    )
                    for channel in packet["joint_identifiability_matrix"]
                )
                for packet in packets
            ),
            "simulator_change_warranted": False,
            "task_score_change_warranted": False,
        },
        "remaining_prerequisites": [
            "device_or_actuator_application_ack_timestamp",
            "device_synchronized_position_and_current_read_timestamps",
            "camera_frame_pts_exposure_drop_and_duplicate_counters",
            "controller_configuration_and_threshold_hashes",
            "calibrated_current_zero_scale_and_torque_provenance",
            "distributed_levels_multiple_speeds_and_repeated_directional_traversals",
            "repeated_reference_reset_trials",
            "strict_task_and_end_effector_consequence",
        ],
        "evidence_context": contract["evidence_context"],
        "budget": {
            "additional_physical_attempts": 0,
            "additional_simulator_replays": 0,
            "evaluator_provider_calls": 0,
            "owner_requested_external_advisory_calls_observed": 1,
        },
        "authority": contract["authority"],
    }


def derive_hil_trace_decomposition(
    output_root: Path,
    *,
    contract_path: Path = DEFAULT_CONTRACT,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Write one content-addressed v2 diagnostic without new execution."""

    output_root = output_root.resolve()
    _require(
        not output_root.exists() or not any(output_root.iterdir()),
        "HIL trace-decomposition output root is not empty; overwrite is refused.",
    )
    report = derive_hil_trace_decomposition_payload(
        contract_path=contract_path,
        repo_root=repo_root,
    )
    output_root.mkdir(parents=True, exist_ok=True)
    report_path = output_root / "report.json"
    atomic_write_json(report_path, report)
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "proof_class": report["proof_class"],
        "contract_sha256": report["contract_sha256"],
        "source_campaign_sha256": report["source_campaign_sha256"],
        "v1_report_sha256": report["v1_report_sha256"],
        "report_sha256": sha256_file(report_path),
        "packet_count": 4,
        "additional_physical_attempts": 0,
        "additional_simulator_replays": 0,
        "evaluator_provider_calls": 0,
        "simulator_parameter_promoted": False,
        "task_score_changed": False,
        "authority": report["authority"],
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    atomic_write_json(output_root / "receipt.json", receipt)
    return receipt


__all__ = [
    "CONTRACT_SCHEMA",
    "DEFAULT_CONTRACT",
    "HILTraceDecompositionError",
    "RECEIPT_SCHEMA",
    "REPORT_SCHEMA",
    "derive_hil_trace_decomposition",
    "derive_hil_trace_decomposition_payload",
    "load_hil_trace_decomposition_contract",
]

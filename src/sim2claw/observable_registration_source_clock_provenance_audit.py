"""Bound the retained source-clock choice without replaying or retiming actions."""

from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import mean, median
from typing import Any

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .observable_physical_episode import (
    admitted_callback_frames,
    load_schedule_contract,
    nearest_frame_binding,
)
from .observable_registration_belief_recalculation import REPO_ROOT, _bound_path


SCHEMA = "sim2claw.observable_registration_source_clock_provenance_audit_contract.v1"
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_source_clock_provenance_audit_receipt.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "observable_registration_source_clock_provenance_audit_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT / "outputs" / "observable_registration_source_clock_provenance_audit_v1"
)
PRIMARY_CLOCK = "sample_completed_monotonic_seconds"
ALTERNATE_CLOCK = "follower_position_read_completed_monotonic_seconds"
CLOSURE_SAMPLES = (224, 228, 232, 241)
ROLES = ("c922", "d405")
EXECUTION_BOUNDARY = {
    "sample_rows_read": 531,
    "camera_callback_rows_read": 1236,
    "frame_association_clock_variants": 2,
    "mujoco_forward_calls": 0,
    "mujoco_step_calls": 0,
    "simulator_replays": 0,
    "fits": 0,
    "searches": 0,
    "renders": 0,
    "task_evaluations": 0,
    "action_or_timestamp_mutations": 0,
    "hardware_actions": 0,
    "paid_compute": False,
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _load_jsonl(path: Path, *, label: str) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as error:
        raise FactoryArtifactError(f"cannot read {label}: {error}") from error
    _require(rows and all(isinstance(row, dict) for row in rows), f"{label} is empty")
    return rows


def _finite_timestamp(row: dict[str, Any], field: str) -> float:
    timestamps = row.get("observability_timestamps")
    _require(isinstance(timestamps, dict), "observability timestamps are missing")
    try:
        value = float(timestamps[field])
    except (KeyError, TypeError, ValueError) as error:
        raise FactoryArtifactError(f"invalid timestamp field: {field}") from error
    _require(math.isfinite(value), f"non-finite timestamp field: {field}")
    return value


def _summary(values: list[float]) -> dict[str, float]:
    _require(bool(values), "cannot summarize an empty metric")
    return {
        "minimum_ms": float(min(values)),
        "maximum_ms": float(max(values)),
        "mean_ms": float(mean(values)),
        "median_ms": float(median(values)),
    }


def load_source_clock_provenance_audit_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR156 source-clock provenance audit")
    _require(contract.get("schema_version") == SCHEMA, "unsupported OR156 contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
    audit = contract["audit"]
    _require(
        audit["known_result_reproduction"] is True
        and audit["primary_clock_field"] == PRIMARY_CLOCK
        and audit["alternate_clock_field"] == ALTERNATE_CLOCK
        and audit["closure_samples"] == list(CLOSURE_SAMPLES)
        and audit["frame_roles"] == list(ROLES)
        and audit["outcome_or_task_metric_may_select_a_parameter"] is False
        and audit["admissible_successor_may_be_opened"] is False,
        "OR156 audit identity changed",
    )
    _require(contract["execution"] == EXECUTION_BOUNDARY, "OR156 execution widened")
    _require(not any(contract["claim_limits"].values()), "OR156 claim widened")
    return contract


def compile_source_clock_provenance_audit(
    contract_path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_source_clock_provenance_audit_contract(contract_path, root=root)
    source_hashes_before = {
        name: sha256_file(root / binding["path"])
        for name, binding in contract["sources"].items()
    }
    samples_path = _bound_path(contract["sources"]["samples"], root=root, label="samples")
    callbacks_path = _bound_path(
        contract["sources"]["camera_callbacks"], root=root, label="camera callbacks"
    )
    schedule_path = _bound_path(
        contract["sources"]["physical_schedule"], root=root, label="physical schedule"
    )
    samples = _load_jsonl(samples_path, label="physical samples")
    callbacks = _load_jsonl(callbacks_path, label="camera callbacks")
    _require(
        len(samples) == EXECUTION_BOUNDARY["sample_rows_read"]
        and [int(row["sample_index"]) for row in samples] == list(range(531)),
        "OR156 sample membership changed",
    )
    _require(
        len(callbacks) == EXECUTION_BOUNDARY["camera_callback_rows_read"],
        "OR156 camera callback membership changed",
    )
    schedule = load_schedule_contract(schedule_path, root=root)
    _require(
        schedule["association"]["sample_clock_field"]
        == f"observability_timestamps.{PRIMARY_CLOCK}"
        and schedule["association"]["frame_clock_field"] == "host_continuous_ns"
        and schedule["association"]["selection"]
        == "nearest_host_continuous_timestamp"
        and schedule["association"]["tie_break"] == "lower_frame_index",
        "OR156 frozen association policy changed",
    )

    frames = {
        role: admitted_callback_frames(callbacks, role=role) for role in ROLES
    }
    _require(
        len(frames["c922"]) == 1029 and len(frames["d405"]) == 171,
        "OR156 admitted camera frame membership changed",
    )
    primary_values = [_finite_timestamp(row, PRIMARY_CLOCK) for row in samples]
    alternate_values = [_finite_timestamp(row, ALTERNATE_CLOCK) for row in samples]
    _require(
        primary_values == sorted(set(primary_values))
        and alternate_values == sorted(set(alternate_values)),
        "OR156 source clocks are not strict",
    )
    direct_shift_ms = [
        float((primary - alternate) * 1000.0)
        for primary, alternate in zip(primary_values, alternate_values, strict=True)
    ]
    _require(min(direct_shift_ms) >= 0.0, "follower read occurs after sample completion")
    primary_zero = primary_values[0]
    alternate_zero = alternate_values[0]
    elapsed_delta_ms = [
        float(((alternate - alternate_zero) - (primary - primary_zero)) * 1000.0)
        for primary, alternate in zip(primary_values, alternate_values, strict=True)
    ]

    ack_available_rows = 0
    synchronized_device_clock_rows = 0
    for row in samples:
        timestamps = row["observability_timestamps"]
        ack_available_rows += int(
            bool(timestamps["actuator_application_or_ack_timestamp_available"])
        )
        synchronized_device_clock_rows += int(bool(timestamps["device_clock_synchronized"]))

    association_rows: dict[str, list[dict[str, Any]]] = {role: [] for role in ROLES}
    for sample_index, (primary, alternate) in enumerate(
        zip(primary_values, alternate_values, strict=True)
    ):
        primary_ns = int(round(primary * 1_000_000_000.0))
        alternate_ns = int(round(alternate * 1_000_000_000.0))
        for role in ROLES:
            primary_binding = nearest_frame_binding(
                frames[role], sample_host_continuous_ns=primary_ns
            )
            alternate_binding = nearest_frame_binding(
                frames[role], sample_host_continuous_ns=alternate_ns
            )
            association_rows[role].append(
                {
                    "sample_index": sample_index,
                    "primary_frame_index": int(primary_binding["frame_index"]),
                    "alternate_frame_index": int(alternate_binding["frame_index"]),
                    "primary_association_error_ms": float(
                        primary_binding["association_error_ms"]
                    ),
                    "alternate_association_error_ms": float(
                        alternate_binding["association_error_ms"]
                    ),
                }
            )

    closure_rows = []
    for sample_index in CLOSURE_SAMPLES:
        roles = {}
        for role in ROLES:
            row = association_rows[role][sample_index]
            roles[role] = {
                key: value for key, value in row.items() if key != "sample_index"
            }
            roles[role]["frame_binding_unchanged"] = (
                row["primary_frame_index"] == row["alternate_frame_index"]
            )
        closure_rows.append(
            {
                "sample_index": sample_index,
                "direct_source_clock_shift_ms": direct_shift_ms[sample_index],
                "elapsed_rebinding_delta_ms": elapsed_delta_ms[sample_index],
                "frame_associations": roles,
            }
        )

    association_summary = {}
    for role in ROLES:
        rows = association_rows[role]
        changed = [
            int(row["sample_index"])
            for row in rows
            if row["primary_frame_index"] != row["alternate_frame_index"]
        ]
        association_summary[role] = {
            "admitted_frame_count": len(frames[role]),
            "full_trace_changed_frame_binding_count": len(changed),
            "full_trace_changed_frame_binding_samples": changed,
            "maximum_primary_association_error_ms": float(
                max(row["primary_association_error_ms"] for row in rows)
            ),
            "maximum_alternate_association_error_ms": float(
                max(row["alternate_association_error_ms"] for row in rows)
            ),
            "maximum_absolute_association_error_change_ms": float(
                max(
                    abs(
                        row["alternate_association_error_ms"]
                        - row["primary_association_error_ms"]
                    )
                    for row in rows
                )
            ),
            "closure_frame_bindings_unchanged": all(
                association_rows[role][sample_index]["primary_frame_index"]
                == association_rows[role][sample_index]["alternate_frame_index"]
                for sample_index in CLOSURE_SAMPLES
            ),
        }

    direct_abs_max = max(direct_shift_ms)
    elapsed_abs = [abs(value) for value in elapsed_delta_ms]
    elapsed_abs_max = max(elapsed_abs)
    closure_direct_abs_max = max(abs(direct_shift_ms[index]) for index in CLOSURE_SAMPLES)
    closure_elapsed_abs_max = max(abs(elapsed_delta_ms[index]) for index in CLOSURE_SAMPLES)
    acceptance = contract["known_result_acceptance"]
    reproduced = (
        direct_abs_max <= float(acceptance["maximum_full_trace_direct_shift_ms"])
        and elapsed_abs_max
        <= float(acceptance["maximum_full_trace_elapsed_delta_ms"])
        and closure_direct_abs_max
        <= float(acceptance["maximum_closure_direct_shift_ms"])
        and closure_elapsed_abs_max
        <= float(acceptance["maximum_closure_elapsed_delta_ms"])
        and all(
            association_summary[role]["closure_frame_bindings_unchanged"]
            for role in ROLES
        )
        and ack_available_rows == 0
        and synchronized_device_clock_rows == 0
    )
    _require(reproduced, "OR156 known source-clock result did not reproduce")

    source_hashes_after = {
        name: sha256_file(root / binding["path"])
        for name, binding in contract["sources"].items()
    }
    _require(source_hashes_before == source_hashes_after, "OR156 source mutated")
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": "PASS_SOURCE_CLOCK_REBINDING_TOO_SMALL_AT_CLOSURE_NO_SUCCESSOR",
        "source_identity": {
            "recording_id": str(samples[0]["recording_id"]),
            "sample_count": len(samples),
            "camera_callback_count": len(callbacks),
            "source_hashes_unchanged": True,
        },
        "clock_provenance": {
            "clock_source": samples[0]["observability_timestamps"]["clock_source"],
            "primary_clock_field": PRIMARY_CLOCK,
            "alternate_clock_field": ALTERNATE_CLOCK,
            "direct_shift_sample_completion_minus_follower_read": _summary(
                direct_shift_ms
            ),
            "maximum_direct_shift_sample_index": int(
                max(range(len(direct_shift_ms)), key=direct_shift_ms.__getitem__)
            ),
            "elapsed_rebinding_delta_alternate_minus_primary": _summary(
                elapsed_delta_ms
            ),
            "maximum_absolute_elapsed_delta_ms": float(elapsed_abs_max),
            "maximum_absolute_elapsed_delta_sample_index": int(
                max(range(len(elapsed_abs)), key=elapsed_abs.__getitem__)
            ),
            "actuator_application_or_ack_timestamp_available_rows": ack_available_rows,
            "device_clock_synchronized_rows": synchronized_device_clock_rows,
        },
        "closure_window": {
            "sample_indices": list(CLOSURE_SAMPLES),
            "maximum_direct_source_clock_shift_ms": float(closure_direct_abs_max),
            "maximum_absolute_elapsed_rebinding_delta_ms": float(
                closure_elapsed_abs_max
            ),
            "all_c922_and_d405_frame_bindings_unchanged": all(
                association_summary[role]["closure_frame_bindings_unchanged"]
                for role in ROLES
            ),
            "rows": closure_rows,
        },
        "frame_association": association_summary,
        "diagnosis": {
            "sample_completion_versus_follower_read_clock_explains_visible_closure_lead": False,
            "closure_window_frame_selection_changes_under_alternate_clock": False,
            "software_row_clock_candidate_exhausted": True,
            "camera_exposure_time_identified": False,
            "actuator_application_time_identified": False,
            "spatial_or_contact_correction_identified": False,
            "task_level_success_advanced_by_this_audit": False,
            "admissible_task_successor": False,
            "interpretation": "Rebinding the retained rows from sample completion to the immediately preceding follower-position read leaves every C922 and D405 closure-window frame unchanged. The corresponding replay elapsed-time perturbation is about one millisecond at closure, so this software clock choice cannot support a retiming correction. Exposure and actuator-application timestamps remain absent, and the spatial/contact discrepancy remains unidentified.",
        },
        "known_result_reproduction": True,
        "execution": EXECUTION_BOUNDARY,
        "claim_limits": contract["claim_limits"],
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def run_source_clock_provenance_audit(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    _require(not output_directory.exists(), "OR156 write-once output already exists")
    receipt = compile_source_clock_provenance_audit(contract_path, root=root)
    output_directory.mkdir(parents=True, exist_ok=False)
    atomic_write_json(output_directory / "receipt.json", receipt)
    return receipt


def verify_source_clock_provenance_audit(
    output_directory: Path = OUTPUT_DIRECTORY,
    contract_path: Path = CONTRACT_PATH,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_source_clock_provenance_audit_contract(contract_path, root=root)
    receipt = load_json_object(
        output_directory / "receipt.json", label="OR156 source-clock receipt"
    )
    _require(receipt.get("schema_version") == RECEIPT_SCHEMA, "OR156 receipt schema changed")
    unsigned = {key: value for key, value in receipt.items() if key != "artifact_sha256"}
    _require(
        receipt["artifact_sha256"] == canonical_digest(unsigned),
        "OR156 receipt digest changed",
    )
    _require(
        receipt["status"]
        == "PASS_SOURCE_CLOCK_REBINDING_TOO_SMALL_AT_CLOSURE_NO_SUCCESSOR",
        "OR156 status changed",
    )
    _require(receipt["execution"] == EXECUTION_BOUNDARY, "OR156 execution changed")
    _require(receipt["claim_limits"] == contract["claim_limits"], "OR156 claims changed")
    _require(not any(receipt["claim_limits"].values()), "OR156 claim widened")
    _require(
        receipt["diagnosis"]["admissible_task_successor"] is False,
        "OR156 opened a successor",
    )
    return receipt

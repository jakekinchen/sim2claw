"""Deterministic importers for retained SAIL calibration evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from ..learning_factory_artifacts import sha256_file
from .contracts import (
    REPO_ROOT,
    SailContractError,
    action_descriptor,
    seal_contract,
    verify_source_binding,
)


class EvidenceImportError(SailContractError):
    """A retained source cannot be represented without changing its meaning."""


def load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvidenceImportError(f"cannot read {label} {path}: {error}") from error
    if not isinstance(value, dict):
        raise EvidenceImportError(f"{label} must contain a JSON object: {path}")
    return value


def load_json_lines(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise EvidenceImportError(
                        f"sample row {index} is not an object: {path}"
                    )
                rows.append(value)
    except (OSError, json.JSONDecodeError) as error:
        raise EvidenceImportError(f"cannot read sample rows {path}: {error}") from error
    if not rows:
        raise EvidenceImportError(f"sample source is empty: {path}")
    return rows


def repo_relative(path: Path, *, repo_root: Path = REPO_ROOT) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _require_keys(value: Mapping[str, Any], names: Sequence[str], *, label: str) -> None:
    missing = [name for name in names if name not in value]
    if missing:
        raise EvidenceImportError(f"{label} is missing fields: {', '.join(missing)}")


def _array(values: Sequence[Any], *, columns: int | None = None) -> np.ndarray:
    try:
        array = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise EvidenceImportError(f"cannot construct float64 evidence array: {error}") from error
    if columns is not None and (array.ndim != 2 or array.shape[1] != columns):
        raise EvidenceImportError(
            f"evidence array must have shape [N,{columns}], observed {list(array.shape)}"
        )
    if not np.all(np.isfinite(array)):
        raise EvidenceImportError("evidence array contains a non-finite scalar")
    return np.ascontiguousarray(array)


def action_from_array(array: np.ndarray, *, ordering: str) -> dict[str, Any]:
    contiguous = np.ascontiguousarray(array, dtype=np.float64)
    return action_descriptor(
        contiguous.tobytes(order="C"),
        shape=list(contiguous.shape),
        dtype="float64",
        ordering=ordering,
    )


def _channel(
    *, unit: str, frame: str | None, values: Sequence[Any], provenance: str
) -> dict[str, Any]:
    copied = list(values)
    return {
        "unit": unit,
        "frame": frame,
        "values": copied,
        "available": [True] * len(copied),
        "provenance": provenance,
    }


def _missing_channel(*, count: int, unit: str, frame: str | None, reason: str) -> dict[str, Any]:
    return {
        "unit": unit,
        "frame": frame,
        "values": [None] * count,
        "available": [False] * count,
        "provenance": reason,
    }


PHYSICAL_MISSING_CHANNELS = (
    "metric_object_trajectory",
    "physical_contact_state",
    "physical_contact_force",
    "instrumented_grasp_outcome",
    "command_to_actuation_latency",
    "camera_capture_latency",
)

SIMULATOR_MISSING_CHANNELS = (
    "physical_contact_state",
    "physical_contact_force",
    "metric_object_trajectory",
    "instrumented_physical_grasp_outcome",
    "phase_label",
)


def import_physical_evidence(
    campaign: Mapping[str, Any],
    catalog: Mapping[str, Any],
    split: Mapping[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
) -> list[dict[str, Any]]:
    expected_class = str(campaign["physical_import"]["proof_class"])
    ordering = str(campaign["physical_import"]["action_ordering"])
    joint_names = list(campaign["physical_import"]["joint_names"])
    split_rows = {str(row["episode_id"]): row for row in split["episodes"]}
    result: list[dict[str, Any]] = []

    for episode in sorted(catalog["episodes"], key=lambda row: str(row["recording_id"])):
        recording_id = str(episode["recording_id"])
        if episode.get("proof_class") != expected_class:
            raise EvidenceImportError(
                f"physical proof class changed for {recording_id}: {episode.get('proof_class')!r}"
            )
        try:
            split_row = split_rows[recording_id]
        except KeyError as error:
            raise EvidenceImportError(f"physical split omits {recording_id}") from error
        if split_row.get("proof_class") != expected_class:
            raise EvidenceImportError(f"split proof class changed for {recording_id}")

        samples_path = verify_source_binding(
            {"path": episode["assets"]["samples"], "sha256": episode["samples_sha256"]},
            repo_root=repo_root,
        )
        receipt_path = verify_source_binding(
            {"path": episode["assets"]["receipt"], "sha256": episode["receipt_sha256"]},
            repo_root=repo_root,
        )
        verify_source_binding(
            {
                "path": episode["assets"]["overhead_video"],
                "sha256": episode["overhead_video_sha256"],
            },
            repo_root=repo_root,
        )
        rows = load_json_lines(samples_path)
        receipt = load_json_object(receipt_path, label="physical recording receipt")
        expected_count = int(episode["sample_count"])
        if len(rows) != expected_count or int(receipt.get("sample_count", -1)) != expected_count:
            raise EvidenceImportError(f"physical sample count changed for {recording_id}")
        if receipt.get("recording_id") != recording_id:
            raise EvidenceImportError(f"physical receipt identity changed for {recording_id}")
        if receipt.get("proof_class") != expected_class:
            raise EvidenceImportError(f"physical receipt proof class changed for {recording_id}")
        for index, row in enumerate(rows):
            _require_keys(
                row,
                (
                    "follower_requested_degrees",
                    "follower_command_degrees",
                    "follower_actual_position_degrees",
                    "follower_actual_velocity_degrees_s",
                    "available_motor_current_raw",
                    "timestamp_monotonic_seconds",
                    "control_dt_seconds",
                    "overhead_video_time_seconds",
                ),
                label=f"physical row {recording_id}:{index}",
            )
            if row.get("recording_id") != recording_id or row.get("episode_id") != recording_id:
                raise EvidenceImportError(f"physical row identity changed for {recording_id}:{index}")

        requested = _array([row["follower_requested_degrees"] for row in rows], columns=6)
        commanded = _array([row["follower_command_degrees"] for row in rows], columns=6)
        measured = _array([row["follower_actual_position_degrees"] for row in rows], columns=6)
        velocity = _array([row["follower_actual_velocity_degrees_s"] for row in rows], columns=6)
        motor_current = _array(
            [[row["available_motor_current_raw"][name] for name in joint_names] for row in rows],
            columns=6,
        )
        timestamps = _array([row["timestamp_monotonic_seconds"] for row in rows])
        control_dt = _array([row["control_dt_seconds"] for row in rows])
        camera_time = _array([row["overhead_video_time_seconds"] for row in rows])
        action = {
            **action_from_array(commanded, ordering=ordering),
            "application_time_seconds": timestamps.tolist(),
        }
        sample_provenance = f"{repo_relative(samples_path, repo_root=repo_root)}@{episode['samples_sha256']}"
        missing = {
            name: _missing_channel(
                count=expected_count,
                unit="unavailable",
                frame=None,
                reason=f"telemetry contract declares unavailable: {name}",
            )
            for name in PHYSICAL_MISSING_CHANNELS
        }
        observations = {
            "requested_joint_position": _channel(
                unit="recorded_source_degree_or_gripper_percent",
                frame="so101_joint_order",
                values=requested.tolist(),
                provenance=sample_provenance + "#follower_requested_degrees",
            ),
            "commanded_joint_position": _channel(
                unit="recorded_source_degree_or_gripper_percent",
                frame="so101_joint_order",
                values=commanded.tolist(),
                provenance=sample_provenance + "#follower_command_degrees",
            ),
            "measured_joint_position": _channel(
                unit="recorded_source_degree_or_gripper_percent",
                frame="so101_joint_order",
                values=measured.tolist(),
                provenance=sample_provenance + "#follower_actual_position_degrees",
            ),
            "measured_joint_velocity": _channel(
                unit="recorded_source_degree_per_second_or_gripper_percent_per_second",
                frame="so101_joint_order",
                values=velocity.tolist(),
                provenance=sample_provenance + "#follower_actual_velocity_degrees_s",
            ),
            "motor_current_proxy": _channel(
                unit="device_raw_present_current_not_calibrated_effort",
                frame="so101_joint_order",
                values=motor_current.tolist(),
                provenance=sample_provenance + "#available_motor_current_raw",
            ),
            "sample_timestamp": _channel(
                unit="second",
                frame="recording_monotonic_origin",
                values=timestamps.tolist(),
                provenance=sample_provenance + "#timestamp_monotonic_seconds",
            ),
            "control_interval": _channel(
                unit="second",
                frame=None,
                values=control_dt.tolist(),
                provenance=sample_provenance + "#control_dt_seconds",
            ),
            "camera_timeline": _channel(
                unit="second",
                frame="overhead_video_origin",
                values=camera_time.tolist(),
                provenance=sample_provenance + "#overhead_video_time_seconds",
            ),
            **missing,
        }
        backend = receipt.get("backend") or {}
        result.append(
            seal_contract(
                {
                    "schema_version": "sim2claw.calibration_evidence.v1",
                    "evidence_id": f"physical:{recording_id}",
                    "session_id": recording_id,
                    "workcell_id": str(campaign["workcell_id"]),
                    "proof_class": expected_class,
                    "source_owner": str(campaign["source_owner"]),
                    "source": {
                        "path": repo_relative(samples_path, repo_root=repo_root),
                        "sha256": str(episode["samples_sha256"]),
                    },
                    "identities": {
                        "simulator": None,
                        "scene": str(receipt.get("scene_id")),
                        "robot": "so101_follower_calibration_sha256:"
                        + str(backend.get("follower_calibration_sha256")),
                        "geometry": "board_pose_id:"
                        + str(receipt.get("board_pose_id"))
                        + ";initial_layout_id:"
                        + str(receipt.get("initial_layout_id")),
                        "hardware_profile": "source_contract_sha256:"
                        + str(receipt.get("source_contract_sha256")),
                        "evaluator": "operator_episode_label_only_no_separate_task_evaluator",
                    },
                    "action": action,
                    "observations": observations,
                    "outcomes": {
                        "operator_episode_label": {
                            "observed": True,
                            "value": receipt.get("outcome_label"),
                            "provenance": repo_relative(receipt_path, repo_root=repo_root)
                            + "#outcome_label",
                            "confidence": "high",
                        },
                        "physical_task_success": {
                            "observed": False,
                            "value": None,
                            "provenance": "source is unqualified teleoperation, not evaluator-owned physical task evidence",
                            "confidence": "none",
                        },
                    },
                    "missing_channels": sorted(PHYSICAL_MISSING_CHANNELS),
                    "abstentions": [
                        "operator success is not contact, grasp, or physical-task ground truth",
                        "motor current is an uncalibrated and possibly cached device proxy",
                    ],
                    "split_role": str(split_row["split"]),
                    "parent_evidence_ids": [],
                    "intervention_ids": [],
                }
            )
        )
    if set(split_rows) != {str(row["recording_id"]) for row in catalog["episodes"]}:
        raise EvidenceImportError("catalog and physical split episode identities differ")
    return result


def _sim_observations(rows: Sequence[Mapping[str, Any]], *, source: str) -> dict[str, Any]:
    count = len(rows)
    observations = {
        "elapsed_time": _channel(
            unit="second",
            frame="simulator_episode_origin",
            values=[row["elapsed_seconds"] for row in rows],
            provenance=source + "#rows[].elapsed_seconds",
        ),
        "applied_action": _channel(
            unit="radian",
            frame="so101_joint_order",
            values=[row["applied_action"] for row in rows],
            provenance=source + "#rows[].applied_action",
        ),
        "mapped_measured_joint_state": _channel(
            unit="radian",
            frame="so101_joint_order",
            values=[row["mapped_measured_joint_state"] for row in rows],
            provenance=source + "#rows[].mapped_measured_joint_state",
        ),
        "baseline_simulated_joint_state": _channel(
            unit="radian",
            frame="so101_joint_order",
            values=[row["current_baseline"]["simulated_joint_state"] for row in rows],
            provenance=source + "#rows[].current_baseline.simulated_joint_state",
        ),
        "selected_simulated_joint_state": _channel(
            unit="radian",
            frame="so101_joint_order",
            values=[row["selected_load_bias"]["simulated_joint_state"] for row in rows],
            provenance=source + "#rows[].selected_load_bias.simulated_joint_state",
        ),
        "mapped_measured_end_effector": _channel(
            unit="meter",
            frame="simulator_world",
            values=[row["selected_load_bias"]["mapped_measured_ee_xyz_m"] for row in rows],
            provenance=source + "#rows[].selected_load_bias.mapped_measured_ee_xyz_m",
        ),
        "baseline_simulated_end_effector": _channel(
            unit="meter",
            frame="simulator_world",
            values=[row["current_baseline"]["simulated_ee_xyz_m"] for row in rows],
            provenance=source + "#rows[].current_baseline.simulated_ee_xyz_m",
        ),
        "selected_simulated_end_effector": _channel(
            unit="meter",
            frame="simulator_world",
            values=[row["selected_load_bias"]["simulated_ee_xyz_m"] for row in rows],
            provenance=source + "#rows[].selected_load_bias.simulated_ee_xyz_m",
        ),
        "baseline_end_effector_error": _channel(
            unit="meter",
            frame=None,
            values=[row["current_baseline"]["ee_error_m"] for row in rows],
            provenance=source + "#rows[].current_baseline.ee_error_m",
        ),
        "selected_end_effector_error": _channel(
            unit="meter",
            frame=None,
            values=[row["selected_load_bias"]["ee_error_m"] for row in rows],
            provenance=source + "#rows[].selected_load_bias.ee_error_m",
        ),
    }
    for name in SIMULATOR_MISSING_CHANNELS:
        observations[name] = _missing_channel(
            count=count,
            unit="unavailable",
            frame=None,
            reason=f"retained trace does not contain {name}",
        )
    return observations


def import_simulator_evidence(
    campaign: Mapping[str, Any],
    servo_receipt: Mapping[str, Any],
    *,
    receipt_path: Path,
    repo_root: Path = REPO_ROOT,
) -> list[dict[str, Any]]:
    expected_class = str(campaign["simulator_import"]["proof_class"])
    ordering = str(campaign["simulator_import"]["action_ordering"])
    receipt_binding = campaign["source_bindings"]["servo_load_bias_receipt"]
    if servo_receipt.get("action_arrays_byte_identical_across_variants") is not True:
        raise EvidenceImportError("servo receipt does not preserve action bytes")
    if servo_receipt.get("proof_class") != "action_frozen_simulator_servo_load_bias_diagnostic":
        raise EvidenceImportError("servo receipt proof class changed")
    result: list[dict[str, Any]] = []

    traces = sorted(servo_receipt["traces"], key=lambda row: str(row["recording_id"]))
    for trace_summary in traces:
        recording_id = str(trace_summary["recording_id"])
        raw_path = Path(str(trace_summary["trace_path"]))
        trace_path = raw_path if raw_path.is_absolute() else repo_root / raw_path
        if not trace_path.is_file():
            fallback = repo_root / "outputs" / "pawn_bg_servo_load_bias_v1" / "traces" / f"{recording_id}.json"
            trace_path = fallback
        if not trace_path.is_file() or sha256_file(trace_path) != trace_summary["trace_sha256"]:
            raise EvidenceImportError(f"action-frozen trace missing or changed: {recording_id}")
        trace = load_json_object(trace_path, label="action-frozen trace")
        rows = trace.get("rows")
        if not isinstance(rows, list) or not rows:
            raise EvidenceImportError(f"action-frozen trace contains no rows: {recording_id}")
        if trace.get("recording_id") != recording_id:
            raise EvidenceImportError(f"action-frozen trace identity changed: {recording_id}")
        action_array = _array([row["applied_action"] for row in rows], columns=6)
        descriptor = action_from_array(action_array, ordering=ordering)
        expected_action = dict(trace_summary["action"])
        for name in ("shape", "dtype", "sha256"):
            if descriptor[name] != expected_action[name]:
                raise EvidenceImportError(
                    f"action descriptor {name} changed for {recording_id}"
                )
        elapsed = [float(row["elapsed_seconds"]) for row in rows]
        source = repo_relative(trace_path, repo_root=repo_root)
        result.append(
            seal_contract(
                {
                    "schema_version": "sim2claw.calibration_evidence.v1",
                    "evidence_id": f"sim-replay:{recording_id}",
                    "session_id": recording_id,
                    "workcell_id": str(campaign["workcell_id"]),
                    "proof_class": expected_class,
                    "source_owner": "deterministic_action_frozen_simulator_campaign",
                    "source": {"path": source, "sha256": str(trace_summary["trace_sha256"])},
                    "identities": {
                        "simulator": "mujoco==3.10.0;candidate:"
                        + str(campaign["simulator_import"]["selected_candidate_id"]),
                        "scene": "configs/optimization/pawn_bg_workcell_fit_v1.json@a1cd0f7d53b22420536396eb724e4dcd877ea74206ae23442fe5b933efa7f69f",
                        "robot": "so101_frozen_stage_d_action_adapter",
                        "geometry": "retained_parent_workcell_geometry",
                        "hardware_profile": None,
                        "evaluator": "servo_load_bias_receipt@" + str(receipt_binding["sha256"]),
                    },
                    "action": {**descriptor, "application_time_seconds": elapsed},
                    "observations": _sim_observations(rows, source=source),
                    "outcomes": {
                        "baseline_trace_metrics": {
                            "observed": True,
                            "value": trace_summary["metrics"]["current_baseline"],
                            "provenance": repo_relative(receipt_path, repo_root=repo_root)
                            + f"#traces[{recording_id}].metrics.current_baseline",
                            "confidence": "measured",
                        },
                        "selected_trace_metrics": {
                            "observed": True,
                            "value": trace_summary["metrics"]["selected_load_bias"],
                            "provenance": repo_relative(receipt_path, repo_root=repo_root)
                            + f"#traces[{recording_id}].metrics.selected_load_bias",
                            "confidence": "measured",
                        },
                        "physical_task_success": {
                            "observed": False,
                            "value": None,
                            "provenance": "simulator trace is not physical task evidence",
                            "confidence": "none",
                        },
                    },
                    "missing_channels": sorted(SIMULATOR_MISSING_CHANNELS),
                    "abstentions": [
                        "trace-fidelity diagnostics do not identify physical parameters",
                        "no simulator, training, policy, or physical promotion authority",
                    ],
                    "split_role": str(campaign["simulator_import"]["development_role"]),
                    "parent_evidence_ids": [f"physical:{recording_id}"],
                    "intervention_ids": [],
                }
            )
        )

    confirmation = servo_receipt["confirmation_action_hashes"]
    for recording_id in sorted(confirmation):
        descriptor_source = confirmation[recording_id]
        descriptor = {
            "shape": list(descriptor_source["shape"]),
            "dtype": str(descriptor_source["dtype"]),
            "ordering": ordering,
            "sha256": str(descriptor_source["sha256"]),
            "application_time_seconds": [],
        }
        missing = {
            name: _missing_channel(
                count=0,
                unit="unavailable",
                frame=None,
                reason="confirmation receipt retains action identity and group metrics but no per-row trace",
            )
            for name in SIMULATOR_MISSING_CHANNELS
        }
        result.append(
            seal_contract(
                {
                    "schema_version": "sim2claw.calibration_evidence.v1",
                    "evidence_id": f"sim-confirmation:{recording_id}",
                    "session_id": recording_id,
                    "workcell_id": str(campaign["workcell_id"]),
                    "proof_class": expected_class,
                    "source_owner": "already_open_regression_receipt_only",
                    "source": {
                        "path": repo_relative(receipt_path, repo_root=repo_root),
                        "sha256": str(receipt_binding["sha256"]),
                    },
                    "identities": {
                        "simulator": "mujoco==3.10.0;candidate:"
                        + str(campaign["simulator_import"]["selected_candidate_id"]),
                        "scene": "configs/optimization/pawn_bg_workcell_fit_v1.json@a1cd0f7d53b22420536396eb724e4dcd877ea74206ae23442fe5b933efa7f69f",
                        "robot": "so101_frozen_stage_d_action_adapter",
                        "geometry": "retained_parent_workcell_geometry",
                        "hardware_profile": None,
                        "evaluator": "already_open_regression_only_no_selection_use",
                    },
                    "action": descriptor,
                    "observations": missing,
                    "outcomes": {
                        "confirmation_membership": {
                            "observed": True,
                            "value": "already_opened_regression_only",
                            "provenance": repo_relative(receipt_path, repo_root=repo_root)
                            + f"#confirmation_action_hashes.{recording_id}",
                            "confidence": "measured",
                        },
                        "per_episode_trace_metrics": {
                            "observed": False,
                            "value": None,
                            "provenance": "only two-episode aggregate confirmation metrics are retained",
                            "confidence": "none",
                        },
                    },
                    "missing_channels": sorted(SIMULATOR_MISSING_CHANNELS),
                    "abstentions": [
                        "confirmation cohort was already opened before SAIL cutover",
                        "aggregate confirmation metrics are not assigned to individual episodes",
                    ],
                    "split_role": str(campaign["simulator_import"]["confirmation_role"]),
                    "parent_evidence_ids": [f"physical:{recording_id}"],
                    "intervention_ids": [],
                }
            )
        )
    return result

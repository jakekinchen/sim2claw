"""Hash-bound physical telemetry evidence and Inspect-facing trace tools.

This module extracts only values recorded by the retired physical workcell. It
produces descriptive command-versus-measured comparisons, never an exact
simulator replay, calibrated effort estimate, object trajectory, contact trace,
or physical policy verdict.
"""

from __future__ import annotations

import copy
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from PIL import Image, ImageDraw

from .learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .paths import REPO_ROOT


CONTRACT_SCHEMA = "sim2claw.physical_telemetry_trace_contract.v1"
CORPUS_SCHEMA = "sim2claw.physical_telemetry_corpus_comparison.v1"
EPISODE_SCHEMA = "sim2claw.physical_telemetry_episode_comparison.v1"
TRACE_SCHEMA = "sim2claw.physical_telemetry_trace_rows.v1"
AUDIT_SCHEMA = "sim2claw.physical_telemetry_audit_receipt.v1"
CLAIM_BOUNDARY = "retrospective_physical_observation_only"
DEFAULT_CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "sim2claw_physical_telemetry_trace_v1.json"
)
JOINT_NAMES = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
)
TOOL_NAMES = (
    "telemetry_status",
    "read_joint_trace",
    "read_camera_frame",
    "read_object_trajectory",
    "read_contact_and_grasp_outcomes",
    "read_execution_timing",
    "read_episode_outcome",
    "read_trace_comparison",
    "submit_telemetry_audit",
)
AVAILABLE_OBSERVATIONS = (
    "requested_joint_position",
    "commanded_joint_position",
    "measured_joint_position",
    "measured_joint_velocity",
    "motor_current_proxy",
    "sample_timestamp",
    "control_interval",
    "camera_timeline",
    "camera_endpoint_frames",
    "episode_outcome",
)
UNAVAILABLE_OBSERVATIONS = (
    "metric_object_trajectory",
    "physical_contact_state",
    "physical_contact_force",
    "instrumented_grasp_outcome",
    "command_to_actuation_latency",
    "camera_capture_latency",
    "simulator_trace",
)


class PhysicalTelemetryError(ValueError):
    """A physical telemetry input or proof boundary changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PhysicalTelemetryError(message)


def _repo_path(repo_root: Path, value: str, label: str) -> Path:
    root = repo_root.resolve()
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise PhysicalTelemetryError(f"{label} escapes the repository") from error
    return path


def _finite(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise PhysicalTelemetryError(f"{label} is not numeric") from error
    _require(math.isfinite(result), f"{label} is not finite")
    return result


def _vector(value: Any, label: str) -> list[float]:
    _require(isinstance(value, list) and len(value) == len(JOINT_NAMES), f"{label} shape changed")
    return [_finite(item, f"{label}[{index}]") for index, item in enumerate(value)]


def _summary(values: Sequence[float], unit: str) -> dict[str, Any]:
    array = np.asarray(values, dtype=np.float64)
    _require(array.size > 0 and np.isfinite(array).all(), "summary values are empty or invalid")
    absolute = np.abs(array)
    return {
        "unit": unit,
        "count": int(array.size),
        "bias": float(np.mean(array)),
        "mae": float(np.mean(absolute)),
        "rmse": float(np.sqrt(np.mean(np.square(array)))),
        "p95_absolute": float(np.quantile(absolute, 0.95)),
        "maximum_absolute": float(np.max(absolute)),
    }


def _positive_timing_summary(values: Sequence[float], label: str) -> dict[str, Any]:
    array = np.asarray(values, dtype=np.float64)
    _require(array.size > 0 and np.isfinite(array).all(), f"{label} is empty or invalid")
    _require(np.all(array > 0.0), f"{label} must be positive")
    return {
        "unit": "second",
        "count": int(array.size),
        "mean": float(np.mean(array)),
        "stddev": float(np.std(array, ddof=1)) if array.size > 1 else 0.0,
        "p50": float(np.quantile(array, 0.50)),
        "p95": float(np.quantile(array, 0.95)),
        "maximum": float(np.max(array)),
    }


def load_physical_telemetry_contract(
    path: Path = DEFAULT_CONTRACT_PATH, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="physical telemetry contract")
    _require(contract.get("schema_version") == CONTRACT_SCHEMA, "unsupported physical telemetry contract")
    _require(
        contract.get("contract_id") == "sim2claw-physical-telemetry-trace-20260720-v1",
        "physical telemetry contract identity changed",
    )
    _require(tuple(contract.get("joint_names", [])) == JOINT_NAMES, "telemetry joint inventory changed")
    expected = contract.get("expected_inventory")
    _require(
        expected
        == {
            "episode_count": 18,
            "sample_count": 7741,
            "joint_count": 6,
            "endpoint_frame_count": 36,
        },
        "telemetry inventory changed",
    )
    _require(
        tuple(contract.get("extractable_observations", {})) == AVAILABLE_OBSERVATIONS,
        "extractable telemetry inventory changed",
    )
    _require(
        tuple(contract.get("unavailable_observations", {})) == UNAVAILABLE_OBSERVATIONS,
        "unavailable telemetry inventory changed",
    )
    tools = contract.get("inspect_tools", {})
    _require(tuple(tools.get("names", [])) == TOOL_NAMES, "telemetry tool inventory changed")
    _require(tools.get("maximum_trace_rows_per_call") == 200, "trace row budget changed")
    _require(tools.get("maximum_trace_reads") == 8, "trace read budget changed")
    _require(tools.get("maximum_camera_frame_reads") == 2, "camera read budget changed")
    _require(tools.get("terminal_submissions") == 1, "terminal audit budget changed")
    _require(tools.get("physical_actions") == 0, "physical actions became enabled")
    authority = contract.get("authority", {})
    _require(authority and all(value is False for value in authority.values()), "telemetry authority widened")
    gate_binding = contract.get("source_gate", {})
    gate_path = _repo_path(repo_root, str(gate_binding.get("path")), "source gate")
    _require(gate_path.is_file(), "physical telemetry source gate is missing")
    _require(sha256_file(gate_path) == gate_binding.get("sha256"), "physical telemetry source gate changed")
    bindings = contract.get("artifact_bindings", {})
    binding_paths = {
        "core_sha256": "src/sim2claw/physical_telemetry.py",
        "inspect_agents_sha256": "evals/inspect_gapbench/telemetry_agents.py",
        "inspect_dataset_sha256": "evals/inspect_gapbench/telemetry_dataset.py",
        "inspect_tools_sha256": "evals/inspect_gapbench/telemetry_tools.py",
        "inspect_approvers_sha256": "evals/inspect_gapbench/telemetry_approvers.py",
        "inspect_scorers_sha256": "evals/inspect_gapbench/telemetry_scorers.py",
        "inspect_task_sha256": "evals/inspect_gapbench/telemetry_task.py",
    }
    for field, relative in binding_paths.items():
        artifact = _repo_path(repo_root, relative, field)
        _require(artifact.is_file(), f"physical telemetry artifact is missing: {relative}")
        _require(sha256_file(artifact) == bindings.get(field), f"physical telemetry artifact changed: {relative}")
    skill_paths = sorted(
        (repo_root / "evals" / "inspect_gapbench" / "telemetry_skills").glob(
            "*/SKILL.md"
        )
    )
    _require(len(skill_paths) == 1, "physical telemetry skill inventory changed")
    skill_digest = canonical_digest(
        {path.parent.name: sha256_file(path) for path in skill_paths}
    )
    _require(
        skill_digest == bindings.get("telemetry_skill_bundle_sha256"),
        "physical telemetry skill bundle changed",
    )
    return contract


def _source_inputs(
    contract: Mapping[str, Any], repo_root: Path
) -> tuple[dict[str, Any], Path, dict[str, Any], Path, dict[str, Any]]:
    gate_path = _repo_path(repo_root, str(contract["source_gate"]["path"]), "source gate")
    gate = load_json_object(gate_path, label="retrospective publication gate")
    catalog_binding = gate["inputs"]["catalog"]
    frame_binding = gate["inputs"]["frame_selection"]
    catalog_path = _repo_path(repo_root, str(catalog_binding["path"]), "physical catalog")
    frame_path = _repo_path(repo_root, str(frame_binding["path"]), "frame selection")
    _require(sha256_file(catalog_path) == catalog_binding["sha256"], "physical catalog changed")
    _require(sha256_file(frame_path) == frame_binding["sha256"], "frame selection changed")
    return gate, catalog_path, load_json_object(catalog_path), frame_path, load_json_object(frame_path)


def _read_trace(path: Path, recording_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    previous_timestamp: float | None = None
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as error:
                raise PhysicalTelemetryError(
                    f"{recording_id} line {line_number} is invalid JSON"
                ) from error
            _require(isinstance(raw, dict), f"{recording_id} sample is not an object")
            _require(
                raw.get("schema_version") == "sim2claw.physical_teleoperation_sample.v1",
                f"{recording_id} sample schema changed",
            )
            _require(raw.get("recording_id") == recording_id, f"{recording_id} sample identity changed")
            _require(raw.get("sample_index") == len(rows), f"{recording_id} indices are not contiguous")
            timestamp = _finite(raw.get("timestamp_monotonic_seconds"), "sample timestamp")
            if previous_timestamp is not None:
                _require(timestamp > previous_timestamp, f"{recording_id} timestamps are not increasing")
            previous_timestamp = timestamp
            requested = _vector(raw.get("follower_requested_degrees"), "requested position")
            commanded = _vector(raw.get("follower_command_degrees"), "commanded position")
            actual = _vector(raw.get("follower_actual_position_degrees"), "actual position")
            velocity = _vector(raw.get("follower_actual_velocity_degrees_s"), "actual velocity")
            current = raw.get("available_motor_current_raw")
            _require(isinstance(current, dict), f"{recording_id} motor current is unavailable")
            _require(set(current) == set(JOINT_NAMES), f"{recording_id} motor current joints changed")
            current_values = {name: _finite(current[name], f"{name} raw current") for name in JOINT_NAMES}
            _require(raw.get("selected_piece_pose_world") is None, "metric object pose unexpectedly became available")
            _require(raw.get("continuous_target_pose_world") is None, "metric target pose unexpectedly became available")
            rows.append(
                {
                    "sample_index": len(rows),
                    "timestamp_monotonic_seconds": timestamp,
                    "control_dt_seconds": _finite(raw.get("control_dt_seconds"), "control interval"),
                    "overhead_video_time_seconds": _finite(
                        raw.get("overhead_video_time_seconds"), "video time"
                    ),
                    "requested_joint_position": requested,
                    "commanded_joint_position": commanded,
                    "measured_joint_position": actual,
                    "measured_joint_velocity": velocity,
                    "motor_current_raw": current_values,
                    "motor_current_stale": bool(raw.get("current_telemetry_stale")),
                    "motor_current_telemetry_hz": _finite(
                        raw.get("current_telemetry_hz"), "current telemetry rate"
                    ),
                    "rate_limited": bool(raw.get("rate_limited")),
                    "safety_clamped": bool(raw.get("safety_clamped")),
                    "stalled": bool(raw.get("stalled")),
                    "stalled_joints": list(raw.get("stalled_joints", [])),
                    "physical_follower_torque_enabled": bool(
                        raw.get("physical_follower_torque_enabled")
                    ),
                    "action_owner": str(raw.get("action_owner", "")),
                    "visual_observation": copy.deepcopy(raw.get("visual_observation")),
                }
            )
    _require(rows, f"{recording_id} trace is empty")
    return rows


def _frame_map(
    frame_selection: Mapping[str, Any], repo_root: Path
) -> dict[str, dict[str, dict[str, Any]]]:
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for episode in frame_selection.get("episodes", []):
        recording_id = str(episode.get("recording_id"))
        phases: dict[str, dict[str, Any]] = {}
        for frame in episode.get("frames", []):
            phase = str(frame.get("phase"))
            _require(phase in {"initial", "final"} and phase not in phases, "camera frame phase changed")
            path = _repo_path(repo_root, str(frame.get("path")), f"{recording_id} {phase} frame")
            _require(path.is_file(), f"{recording_id} {phase} frame is missing")
            _require(sha256_file(path) == frame.get("sha256"), f"{recording_id} {phase} frame changed")
            phases[phase] = {
                "phase": phase,
                "path": path.relative_to(repo_root.resolve()).as_posix(),
                "sha256": frame["sha256"],
                "source_video_sha256": frame["source_video_sha256"],
                "time_seconds": _finite(frame["time_seconds"], "frame time"),
                "measurement_semantics": "qualitative_endpoint_frame_not_metric_pose",
            }
        _require(set(phases) == {"initial", "final"}, f"{recording_id} endpoint frames are incomplete")
        result[recording_id] = phases
    return result


def _joint_unit(index: int) -> str:
    return "percent" if index == len(JOINT_NAMES) - 1 else "degree"


def _episode_comparison(
    catalog_episode: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    frames: Mapping[str, Mapping[str, Any]],
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    recording_id = str(catalog_episode["recording_id"])
    requested = np.asarray([row["requested_joint_position"] for row in rows], dtype=np.float64)
    commanded = np.asarray([row["commanded_joint_position"] for row in rows], dtype=np.float64)
    measured = np.asarray([row["measured_joint_position"] for row in rows], dtype=np.float64)
    velocity = np.asarray([row["measured_joint_velocity"] for row in rows], dtype=np.float64)
    measured_minus_commanded = measured - commanded
    commanded_minus_requested = commanded - requested
    non_stale_current_rows = [row for row in rows if not row["motor_current_stale"]]
    _require(
        non_stale_current_rows,
        f"{recording_id} has no non-stale motor-current proxy rows",
    )
    current = np.asarray(
        [
            [row["motor_current_raw"][name] for name in JOINT_NAMES]
            for row in non_stale_current_rows
        ],
        dtype=np.float64,
    )
    timestamps = np.asarray([row["timestamp_monotonic_seconds"] for row in rows], dtype=np.float64)
    control_dt = np.asarray([row["control_dt_seconds"] for row in rows], dtype=np.float64)
    video = np.asarray([row["overhead_video_time_seconds"] for row in rows], dtype=np.float64)
    relative_alignment = (video - video[0]) - (timestamps - timestamps[0])
    joint_rows: list[dict[str, Any]] = []
    for index, name in enumerate(JOINT_NAMES):
        joint_rows.append(
            {
                "joint_name": name,
                "position_unit": _joint_unit(index),
                "measured_minus_commanded": _summary(
                    measured_minus_commanded[:, index], _joint_unit(index)
                ),
                "commanded_minus_requested": _summary(
                    commanded_minus_requested[:, index], _joint_unit(index)
                ),
                "measured_velocity": _summary(
                    velocity[:, index], f"{_joint_unit(index)}_per_second"
                ),
                "non_stale_cached_motor_current_proxy": _summary(
                    current[:, index], "device_raw_present_current"
                ),
            }
        )
    result = {
        "schema_version": EPISODE_SCHEMA,
        "recording_id": recording_id,
        "proof_class": catalog_episode["proof_class"],
        "source_square": catalog_episode["source_square"],
        "destination_square": catalog_episode["destination_square"],
        "metadata_status": catalog_episode["metadata_status"],
        "sample_count": len(rows),
        "duration_seconds": float(timestamps[-1] - timestamps[0]),
        "joint_comparisons": joint_rows,
        "timing": {
            "successive_monotonic_interval": _positive_timing_summary(
                np.diff(timestamps), "monotonic intervals"
            ),
            "recorded_control_interval": _positive_timing_summary(
                control_dt, "control intervals"
            ),
            "video_minus_monotonic_initial_offset_seconds": float(video[0] - timestamps[0]),
            "relative_video_alignment_error": _summary(relative_alignment, "second"),
            "command_to_actuation_latency": {
                "available": False,
                "reason": "command_write_and_actuation_observation_timestamps_are_not_separately_recorded",
            },
            "camera_capture_latency": {
                "available": False,
                "reason": "video_timeline_alignment_does_not_identify_capture_latency",
            },
        },
        "telemetry_quality": {
            "non_stale_cached_motor_current_row_count": len(
                non_stale_current_rows
            ),
            "stale_motor_current_row_count": len(rows)
            - len(non_stale_current_rows),
            "fresh_motor_current_read_indicator_available": False,
            "motor_current_is_cached_between_nominal_reads": True,
            "motor_current_telemetry_hz": sorted(
                {float(row["motor_current_telemetry_hz"]) for row in rows}
            ),
            "rate_limited_sample_count": sum(bool(row["rate_limited"]) for row in rows),
            "safety_clamped_sample_count": sum(bool(row["safety_clamped"]) for row in rows),
            "stalled_sample_count": sum(bool(row["stalled"]) for row in rows),
            "all_actions_owned_by_human_teleoperator": all(
                row["action_owner"] == "human_teleoperator" for row in rows
            ),
        },
        "camera_frames": {phase: copy.deepcopy(frames[phase]) for phase in ("initial", "final")},
        "object_trajectory": {
            "available": False,
            "non_null_selected_piece_pose_count": 0,
            "non_null_target_pose_count": 0,
            "reason": "metric_object_pose_fields_are_null",
        },
        "contact_and_grasp": {
            "physical_contact_state_available": False,
            "physical_contact_force_available": False,
            "instrumented_grasp_outcome_available": False,
            "reason": "no_physical_contact_or_force_observable_was_recorded",
        },
        "episode_outcome": {
            "label": receipt.get("outcome_label"),
            "action_owner": "human_teleoperator",
            "learned_policy_execution": False,
            "instrumented_grasp_measurement": False,
        },
        "comparison_scope": {
            "command_vs_measured_physical_trace": True,
            "requested_vs_commanded_physical_trace": True,
            "real_vs_sim_trace": False,
            "reason_real_vs_sim_unavailable": "zero_episodes_are_exact_simulator_replay_eligible",
        },
        "authority": {
            "diagnostic_physical_observation": True,
            "simulator_calibration": False,
            "domain_randomization_admission": False,
            "training_admission": False,
            "physical_transfer_proof": False,
        },
    }
    result["comparison_sha256"] = canonical_digest(result)
    return result


def _trace_artifact(recording_id: str, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    result = {
        "schema_version": TRACE_SCHEMA,
        "recording_id": recording_id,
        "joint_names": list(JOINT_NAMES),
        "row_count": len(rows),
        "rows": [copy.deepcopy(dict(row)) for row in rows],
        "claim_boundary": CLAIM_BOUNDARY,
    }
    result["trace_sha256"] = canonical_digest(result)
    return result


def _render_trace_plot(
    path: Path,
    recording_id: str,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    width, height = 1800, 1200
    margin_x, margin_top, gap_x, gap_y = 90, 100, 40, 65
    panel_w = (width - 2 * margin_x - gap_x) // 2
    panel_h = (height - margin_top - 150 - 2 * gap_y) // 3
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((margin_x, 35), f"Physical command vs measured trace: {recording_id}", fill="black")
    timestamps = np.asarray([row["timestamp_monotonic_seconds"] for row in rows], dtype=np.float64)
    timestamps -= timestamps[0]
    command = np.asarray([row["commanded_joint_position"] for row in rows], dtype=np.float64)
    measured = np.asarray([row["measured_joint_position"] for row in rows], dtype=np.float64)
    indices = np.linspace(0, len(rows) - 1, min(len(rows), 900), dtype=int)
    for joint_index, joint_name in enumerate(JOINT_NAMES):
        col, row_index = joint_index % 2, joint_index // 2
        left = margin_x + col * (panel_w + gap_x)
        top = margin_top + row_index * (panel_h + gap_y)
        right, bottom = left + panel_w, top + panel_h
        draw.rectangle((left, top, right, bottom), outline="#999999", width=2)
        values = np.concatenate((command[:, joint_index], measured[:, joint_index]))
        low, high = float(np.min(values)), float(np.max(values))
        if math.isclose(low, high):
            low, high = low - 1.0, high + 1.0
        x_span = max(float(timestamps[-1]), 1e-12)

        def point(sample_index: int, value: float) -> tuple[float, float]:
            x = left + float(timestamps[sample_index]) / x_span * panel_w
            y = bottom - (value - low) / (high - low) * panel_h
            return x, y

        command_points = [point(int(index), float(command[index, joint_index])) for index in indices]
        measured_points = [point(int(index), float(measured[index, joint_index])) for index in indices]
        if len(command_points) > 1:
            draw.line(command_points, fill="#1f4e79", width=3)
            draw.line(measured_points, fill="#d97706", width=2)
        draw.text((left + 8, top + 7), f"{joint_name} ({_joint_unit(joint_index)})", fill="black")
        draw.text(
            (right - 225, top + 7),
            f"range {low:.2f} to {high:.2f}",
            fill="#555555",
        )
        draw.text((left + 8, bottom + 8), "t=0 s", fill="#555555")
        draw.text(
            (right - 115, bottom + 8),
            f"t={timestamps[-1]:.1f} s",
            fill="#555555",
        )
    draw.line((margin_x, height - 75, margin_x + 45, height - 75), fill="#1f4e79", width=4)
    draw.text((margin_x + 55, height - 84), "commanded", fill="#1f4e79")
    draw.line((margin_x + 220, height - 75, margin_x + 265, height - 75), fill="#d97706", width=4)
    draw.text((margin_x + 275, height - 84), "measured", fill="#d97706")
    draw.text(
        (margin_x, height - 45),
        "Retrospective human-teleoperation observation; not simulator calibration or policy-transfer proof.",
        fill="#555555",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    image.save(temporary, format="PNG")
    temporary.replace(path)


def _write_aggregate_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    fields = [
        "joint_name",
        "position_unit",
        "comparison",
        "count",
        "bias",
        "mae",
        "rmse",
        "p95_absolute",
        "maximum_absolute",
    ]
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            for comparison in ("measured_minus_commanded", "commanded_minus_requested"):
                summary = row[comparison]
                writer.writerow(
                    {
                        "joint_name": row["joint_name"],
                        "position_unit": row["position_unit"],
                        "comparison": comparison,
                        **{field: summary[field] for field in fields[3:]},
                    }
                )
    temporary.replace(path)


def materialize_physical_telemetry(
    output_root: Path,
    *,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    repo_root: Path = REPO_ROOT,
    render_plots: bool = True,
) -> dict[str, Any]:
    contract = load_physical_telemetry_contract(contract_path, repo_root=repo_root)
    gate, catalog_path, catalog, frame_path, frame_selection = _source_inputs(contract, repo_root)
    frame_rows = _frame_map(frame_selection, repo_root)
    episodes = catalog.get("episodes")
    _require(isinstance(episodes, list) and len(episodes) == 18, "physical episode inventory changed")
    output_root = output_root.resolve()
    summaries: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    episode_row_groups: list[list[dict[str, Any]]] = []
    for episode in episodes:
        recording_id = str(episode.get("recording_id"))
        _require(recording_id in frame_rows, f"{recording_id} has no endpoint frames")
        assets = episode.get("assets", {})
        samples_path = _repo_path(repo_root, str(assets.get("samples")), f"{recording_id} samples")
        receipt_path = _repo_path(repo_root, str(assets.get("receipt")), f"{recording_id} receipt")
        video_path = _repo_path(repo_root, str(assets.get("overhead_video")), f"{recording_id} video")
        for path, expected_hash, label in (
            (samples_path, episode.get("samples_sha256"), "samples"),
            (receipt_path, episode.get("receipt_sha256"), "receipt"),
            (video_path, episode.get("overhead_video_sha256"), "video"),
        ):
            _require(path.is_file(), f"{recording_id} {label} is missing")
            _require(sha256_file(path) == expected_hash, f"{recording_id} {label} changed")
        rows = _read_trace(samples_path, recording_id)
        _require(len(rows) == episode.get("sample_count"), f"{recording_id} sample count changed")
        receipt = load_json_object(receipt_path, label=f"{recording_id} receipt")
        comparison = _episode_comparison(episode, rows, frame_rows[recording_id], receipt)
        episode_root = output_root / "episodes" / recording_id
        trace = _trace_artifact(recording_id, rows)
        atomic_write_json(episode_root / "trace_rows.json", trace)
        atomic_write_json(episode_root / "trace_comparison.json", comparison)
        if render_plots:
            _render_trace_plot(episode_root / "command_vs_measured.png", recording_id, rows)
        summaries.append(
            {
                "recording_id": recording_id,
                "sample_count": len(rows),
                "trace_sha256": trace["trace_sha256"],
                "comparison_sha256": comparison["comparison_sha256"],
                "trace_path": (Path("episodes") / recording_id / "trace_rows.json").as_posix(),
                "comparison_path": (
                    Path("episodes") / recording_id / "trace_comparison.json"
                ).as_posix(),
            }
        )
        all_rows.extend(rows)
        episode_row_groups.append(rows)
    _require(len(all_rows) == 7741, "physical telemetry sample inventory changed")
    pooled_requested = np.asarray([row["requested_joint_position"] for row in all_rows])
    pooled_commanded = np.asarray([row["commanded_joint_position"] for row in all_rows])
    pooled_measured = np.asarray([row["measured_joint_position"] for row in all_rows])
    pooled_velocity = np.asarray([row["measured_joint_velocity"] for row in all_rows])
    non_stale_current_rows = [
        row for row in all_rows if not row["motor_current_stale"]
    ]
    pooled_current = np.asarray(
        [
            [row["motor_current_raw"][name] for name in JOINT_NAMES]
            for row in non_stale_current_rows
        ]
    )
    aggregate_joints = []
    for index, name in enumerate(JOINT_NAMES):
        aggregate_joints.append(
            {
                "joint_name": name,
                "position_unit": _joint_unit(index),
                "measured_minus_commanded": _summary(
                    pooled_measured[:, index] - pooled_commanded[:, index],
                    _joint_unit(index),
                ),
                "commanded_minus_requested": _summary(
                    pooled_commanded[:, index] - pooled_requested[:, index],
                    _joint_unit(index),
                ),
                "measured_velocity": _summary(
                    pooled_velocity[:, index],
                    f"{_joint_unit(index)}_per_second",
                ),
                "non_stale_cached_motor_current_proxy": _summary(
                    pooled_current[:, index],
                    "device_raw_present_current",
                ),
            }
        )
    pooled_intervals: list[float] = []
    pooled_alignment: list[float] = []
    for rows in episode_row_groups:
        timestamps = np.asarray(
            [row["timestamp_monotonic_seconds"] for row in rows], dtype=np.float64
        )
        video = np.asarray(
            [row["overhead_video_time_seconds"] for row in rows], dtype=np.float64
        )
        pooled_intervals.extend(float(item) for item in np.diff(timestamps))
        pooled_alignment.extend(
            float(item)
            for item in ((video - video[0]) - (timestamps - timestamps[0]))
        )
    outcome_counts = Counter(
        load_json_object(
            _repo_path(repo_root, str(episode["assets"]["receipt"]), "receipt")
        ).get("outcome_label")
        for episode in episodes
    )
    result = {
        "schema_version": CORPUS_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": sha256_file(contract_path),
        "source_gate_sha256": sha256_file(
            _repo_path(repo_root, str(contract["source_gate"]["path"]), "source gate")
        ),
        "source_catalog_sha256": sha256_file(catalog_path),
        "source_frame_selection_sha256": sha256_file(frame_path),
        "episode_count": len(summaries),
        "sample_count": len(all_rows),
        "endpoint_frame_count": sum(len(item) for item in frame_rows.values()),
        "available_observations": list(AVAILABLE_OBSERVATIONS),
        "unavailable_observations": copy.deepcopy(contract["unavailable_observations"]),
        "aggregate_joint_comparisons": aggregate_joints,
        "aggregate_timing": {
            "successive_monotonic_interval": _positive_timing_summary(
                pooled_intervals, "pooled monotonic intervals"
            ),
            "recorded_control_interval": _positive_timing_summary(
                [float(row["control_dt_seconds"]) for row in all_rows],
                "pooled control intervals",
            ),
            "relative_video_alignment_error": _summary(
                pooled_alignment, "second"
            ),
            "command_to_actuation_latency_available": False,
            "camera_capture_latency_available": False,
        },
        "aggregate_telemetry_quality": {
            "non_stale_cached_motor_current_row_count": len(
                non_stale_current_rows
            ),
            "stale_motor_current_row_count": len(all_rows)
            - len(non_stale_current_rows),
            "fresh_motor_current_read_indicator_available": False,
            "motor_current_is_cached_between_nominal_reads": True,
            "rate_limited_sample_count": sum(
                bool(row["rate_limited"]) for row in all_rows
            ),
            "safety_clamped_sample_count": sum(
                bool(row["safety_clamped"]) for row in all_rows
            ),
            "stalled_sample_count": sum(bool(row["stalled"]) for row in all_rows),
        },
        "episode_outcome_counts": dict(sorted(outcome_counts.items())),
        "episodes": summaries,
        "comparison_scope": {
            "physical_command_vs_measured": True,
            "physical_requested_vs_commanded": True,
            "real_vs_sim": False,
            "per_sample_statistics_are_descriptive_only": True,
            "episode_is_independent_unit_for_inference": True,
        },
        "proof_boundary": {
            "human_teleoperation_source": True,
            "learned_policy_result": False,
            "simulator_calibration": False,
            "domain_randomization_admission": False,
            "physical_transfer_proof": False,
        },
        "source_gate_status": {
            "exact_simulator_replay_eligible_episode_count": 0,
            "metric_object_pose_available": False,
            "physical_contact_observable_available": False,
            "latency_identifiable": False,
        },
        "authority": copy.deepcopy(contract["authority"]),
    }
    result["corpus_comparison_sha256"] = canonical_digest(result)
    atomic_write_json(output_root / "physical_telemetry_corpus_comparison.json", result)
    _write_aggregate_csv(
        output_root / "aggregate_joint_comparison.csv",
        aggregate_joints,
    )
    return result


class PhysicalTelemetrySession:
    """Read-only bounded interface over one materialized physical episode."""

    def __init__(
        self,
        episode_manifest: Mapping[str, Any],
        state_root: Path,
        *,
        artifact_root: Path | None = None,
        repo_root: Path = REPO_ROOT,
        reset: bool = False,
    ):
        self.recording_id = str(episode_manifest["recording_id"])
        root = (artifact_root or Path.cwd()).resolve()
        self.repo_root = repo_root.resolve()
        self.trace_path = (root / str(episode_manifest["trace_path"])).resolve()
        self.comparison_path = (root / str(episode_manifest["comparison_path"])).resolve()
        for path in (self.trace_path, self.comparison_path):
            try:
                path.relative_to(root)
            except ValueError as error:
                raise PhysicalTelemetryError(
                    "physical telemetry artifact escaped its materialized root"
                ) from error
        self.trace = load_json_object(self.trace_path, label="physical telemetry trace")
        self.comparison = load_json_object(self.comparison_path, label="physical telemetry comparison")
        _require(self.trace.get("recording_id") == self.recording_id, "telemetry trace identity changed")
        _require(self.comparison.get("recording_id") == self.recording_id, "telemetry comparison identity changed")
        self.state_root = state_root.resolve()
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.state_root / "session_state.json"
        if reset:
            for path in (self.state_path, self.state_root / "audit_receipt.json"):
                path.unlink(missing_ok=True)
        if not self.state_path.exists():
            self._write_state(
                {
                    "recording_id": self.recording_id,
                    "trace_reads": 0,
                    "camera_frame_reads": 0,
                    "terminal_submissions": 0,
                    "events": [],
                    "terminal_receipt": None,
                }
            )
        self._state()

    def _state(self) -> dict[str, Any]:
        state = load_json_object(self.state_path, label="physical telemetry session")
        _require(state.get("recording_id") == self.recording_id, "telemetry session identity changed")
        return state

    def _write_state(self, state: Mapping[str, Any]) -> None:
        atomic_write_json(self.state_path, dict(state))

    def _require_episode(self, recording_id: str) -> None:
        _require(recording_id == self.recording_id, "recording_id does not match active episode")

    def _require_open(self, state: Mapping[str, Any]) -> None:
        _require(state.get("terminal_receipt") is None, "telemetry audit is terminal")

    def terminal_receipt(self) -> dict[str, Any] | None:
        receipt = self._state().get("terminal_receipt")
        return copy.deepcopy(receipt) if isinstance(receipt, dict) else None

    def telemetry_status(self, recording_id: str) -> dict[str, Any]:
        self._require_episode(recording_id)
        state = self._state()
        return {
            "recording_id": recording_id,
            "proof_class": self.comparison["proof_class"],
            "sample_count": self.comparison["sample_count"],
            "available_observations": list(AVAILABLE_OBSERVATIONS),
            "unavailable_observations": list(UNAVAILABLE_OBSERVATIONS),
            "remaining_budgets": {
                "trace_reads": 8 - int(state["trace_reads"]),
                "camera_frame_reads": 2 - int(state["camera_frame_reads"]),
                "terminal_submissions": 1 - int(state["terminal_submissions"]),
                "physical_actions": 0,
            },
            "trace_comparison_sha256": self.comparison["comparison_sha256"],
            "terminal": state["terminal_receipt"] is not None,
            "claim_boundary": CLAIM_BOUNDARY,
        }

    def read_joint_trace(
        self,
        recording_id: str,
        start: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        self._require_episode(recording_id)
        _require(type(start) is int and start >= 0, "trace start is invalid")
        _require(type(limit) is int and 1 <= limit <= 200, "trace limit is invalid")
        state = self._state()
        self._require_open(state)
        _require(int(state["trace_reads"]) < 8, "trace read budget exhausted")
        rows = self.trace["rows"]
        state["trace_reads"] += 1
        state["events"].append({"tool": "read_joint_trace", "start": start, "limit": limit})
        self._write_state(state)
        return {
            "recording_id": recording_id,
            "joint_names": list(JOINT_NAMES),
            "slice": {"start": start, "limit": limit, "total": len(rows)},
            "rows": copy.deepcopy(rows[start : start + limit]),
            "motor_current_semantics": "raw_present_current_proxy_cached_between_nominal_5hz_reads_not_calibrated_effort",
        }

    def read_camera_frame(
        self, recording_id: str, phase: str
    ) -> tuple[dict[str, Any], Path]:
        self._require_episode(recording_id)
        _require(phase in {"initial", "final"}, "camera phase must be initial or final")
        state = self._state()
        self._require_open(state)
        _require(int(state["camera_frame_reads"]) < 2, "camera frame read budget exhausted")
        metadata = copy.deepcopy(self.comparison["camera_frames"][phase])
        path = (self.repo_root / str(metadata.pop("path"))).resolve()
        try:
            path.relative_to(self.repo_root)
        except ValueError as error:
            raise PhysicalTelemetryError("camera frame escaped the repository") from error
        _require(path.is_file() and sha256_file(path) == metadata["sha256"], "camera frame changed")
        state["camera_frame_reads"] += 1
        state["events"].append({"tool": "read_camera_frame", "phase": phase, "sha256": metadata["sha256"]})
        self._write_state(state)
        return metadata, path

    def read_object_trajectory(self, recording_id: str) -> dict[str, Any]:
        self._require_episode(recording_id)
        return copy.deepcopy(self.comparison["object_trajectory"])

    def read_contact_and_grasp_outcomes(self, recording_id: str) -> dict[str, Any]:
        self._require_episode(recording_id)
        return {
            **copy.deepcopy(self.comparison["contact_and_grasp"]),
            "episode_receipt_outcome": copy.deepcopy(self.comparison["episode_outcome"]),
        }

    def read_execution_timing(self, recording_id: str) -> dict[str, Any]:
        self._require_episode(recording_id)
        return copy.deepcopy(self.comparison["timing"])

    def read_episode_outcome(self, recording_id: str) -> dict[str, Any]:
        self._require_episode(recording_id)
        return copy.deepcopy(self.comparison["episode_outcome"])

    def read_trace_comparison(self, recording_id: str) -> dict[str, Any]:
        self._require_episode(recording_id)
        return {
            "recording_id": recording_id,
            "joint_comparisons": copy.deepcopy(self.comparison["joint_comparisons"]),
            "telemetry_quality": copy.deepcopy(self.comparison["telemetry_quality"]),
            "comparison_scope": copy.deepcopy(self.comparison["comparison_scope"]),
            "comparison_sha256": self.comparison["comparison_sha256"],
        }

    def submit_telemetry_audit(
        self,
        recording_id: str,
        audit: Mapping[str, Any],
        claim_boundary: str,
    ) -> dict[str, Any]:
        self._require_episode(recording_id)
        state = self._state()
        self._require_open(state)
        _require(int(state["terminal_submissions"]) == 0, "terminal audit budget exhausted")
        _require(claim_boundary == CLAIM_BOUNDARY, f"claim_boundary must be {CLAIM_BOUNDARY}")
        expected_keys = {
            "available_observations",
            "unavailable_observations",
            "trace_comparison_sha256",
        }
        _require(isinstance(audit, Mapping) and set(audit) == expected_keys, "telemetry audit keys changed")
        _require(
            tuple(audit["available_observations"]) == AVAILABLE_OBSERVATIONS,
            "telemetry audit misstates available observations",
        )
        _require(
            tuple(audit["unavailable_observations"]) == UNAVAILABLE_OBSERVATIONS,
            "telemetry audit misstates unavailable observations",
        )
        _require(
            audit["trace_comparison_sha256"] == self.comparison["comparison_sha256"],
            "telemetry audit comparison identity changed",
        )
        state["terminal_submissions"] += 1
        unsigned = {
            "schema_version": AUDIT_SCHEMA,
            "recording_id": recording_id,
            "proof_class": "retrospective_physical_teleoperation_observation",
            "trace_comparison_sha256": self.comparison["comparison_sha256"],
            "available_observations": list(AVAILABLE_OBSERVATIONS),
            "unavailable_observations": list(UNAVAILABLE_OBSERVATIONS),
            "claim_boundary": claim_boundary,
            "audit_complete": True,
            "physical_actions": 0,
            "authority": {
                "simulator_calibration": False,
                "domain_randomization_admission": False,
                "training_admission": False,
                "physical_transfer_proof": False,
            },
        }
        receipt = {**unsigned, "receipt_sha256": canonical_digest(unsigned)}
        state["terminal_receipt"] = receipt
        state["events"].append({"tool": "submit_telemetry_audit", "receipt_sha256": receipt["receipt_sha256"]})
        self._write_state(state)
        atomic_write_json(self.state_root / "audit_receipt.json", receipt)
        return copy.deepcopy(receipt)


def build_physical_telemetry_sessions(
    output_root: Path,
    *,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    repo_root: Path = REPO_ROOT,
    render_plots: bool = False,
) -> tuple[dict[str, PhysicalTelemetrySession], dict[str, Any]]:
    manifest = materialize_physical_telemetry(
        output_root,
        contract_path=contract_path,
        repo_root=repo_root,
        render_plots=render_plots,
    )
    sessions = {
        row["recording_id"]: PhysicalTelemetrySession(
            row,
            output_root / "state" / row["recording_id"],
            artifact_root=output_root,
            repo_root=repo_root,
            reset=True,
        )
        for row in manifest["episodes"]
    }
    return sessions, manifest


__all__ = [
    "AUDIT_SCHEMA",
    "AVAILABLE_OBSERVATIONS",
    "CLAIM_BOUNDARY",
    "CORPUS_SCHEMA",
    "DEFAULT_CONTRACT_PATH",
    "EPISODE_SCHEMA",
    "JOINT_NAMES",
    "PhysicalTelemetryError",
    "PhysicalTelemetrySession",
    "TOOL_NAMES",
    "TRACE_SCHEMA",
    "UNAVAILABLE_OBSERVATIONS",
    "build_physical_telemetry_sessions",
    "load_physical_telemetry_contract",
    "materialize_physical_telemetry",
]

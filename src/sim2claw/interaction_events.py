"""Deterministic interaction candidates derived from immutable physical logs.

The outputs in this module are retrospective phase and evidence proposals. They
do not constitute measured contact, force, metric object pose, simulator
calibration, learned-policy evidence, or physical-transfer proof.
"""

from __future__ import annotations

import copy
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np
from PIL import Image, ImageDraw

from .learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .paths import REPO_ROOT


CONTRACT_SCHEMA = "sim2claw.fixed_data_event_pipeline_contract.v1"
EPISODE_SCHEMA = "sim2claw.interaction_event_episode.v1"
PHASE_ROWS_SCHEMA = "sim2claw.interaction_phase_rows.v1"
CORPUS_SCHEMA = "sim2claw.interaction_event_corpus.v1"
ANNOTATION_SCHEMA = "sim2claw.visual_interaction_annotation.v1"
CONSENSUS_SCHEMA = "sim2claw.visual_interaction_consensus.v1"
SAMPLER_SCHEMA = "sim2claw.phase_balanced_sampler_manifest.v1"
SIM_TRACE_SCHEMA = "sim2claw.exact_physical_command_replay_trace.v1"
SIM_COMPARISON_SCHEMA = "sim2claw.event_conditioned_real_sim_comparison.v1"
SIM_STATUS_SCHEMA = "sim2claw.event_conditioned_real_sim_status.v1"
AUDIT_SCHEMA = "sim2claw.interaction_event_audit_receipt.v1"
CLAIM_BOUNDARY = "retrospective_multimodal_candidates_only"
DEFAULT_CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "sim2claw_fixed_data_event_pipeline_v1.json"
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
    "event_status",
    "read_event_proposals",
    "read_event_metrics",
    "read_interaction_strip",
    "submit_visual_annotation",
    "submit_event_audit",
)


class InteractionEventError(ValueError):
    """An immutable input, contract, or evidence boundary changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InteractionEventError(message)


def _repo_path(repo_root: Path, value: str, label: str) -> Path:
    root = repo_root.resolve()
    candidate = Path(value)
    path = (candidate if candidate.is_absolute() else root / candidate).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise InteractionEventError(f"{label} escapes the repository") from error
    return path


def _finite(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise InteractionEventError(f"{label} is not numeric") from error
    _require(math.isfinite(result), f"{label} is not finite")
    return result


def _vector(value: Any, label: str) -> list[float]:
    _require(isinstance(value, list) and len(value) == len(JOINT_NAMES), f"{label} shape changed")
    return [_finite(item, f"{label}[{index}]") for index, item in enumerate(value)]


def _summary(values: Sequence[float], unit: str) -> dict[str, Any]:
    array = np.asarray(values, dtype=np.float64)
    _require(array.size > 0 and np.isfinite(array).all(), "summary values are invalid")
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


def _distribution_summary(values: Sequence[float], unit: str) -> dict[str, Any]:
    array = np.asarray(values, dtype=np.float64)
    _require(array.size > 0 and np.isfinite(array).all(), "distribution values are invalid")
    return {
        "unit": unit,
        "independent_episode_count": int(array.size),
        "mean": float(np.mean(array)),
        "median": float(np.median(array)),
        "minimum": float(np.min(array)),
        "maximum": float(np.max(array)),
        "p95": float(np.quantile(array, 0.95)),
    }


def _artifact_binding_paths() -> dict[str, str]:
    return {
        "core_sha256": "src/sim2claw/interaction_events.py",
        "materializer_sha256": "scripts/materialize_interaction_event_pipeline.py",
        "inspect_agents_sha256": "evals/inspect_gapbench/event_agents.py",
        "inspect_dataset_sha256": "evals/inspect_gapbench/event_dataset.py",
        "inspect_tools_sha256": "evals/inspect_gapbench/event_tools.py",
        "inspect_approvers_sha256": "evals/inspect_gapbench/event_approvers.py",
        "inspect_scorers_sha256": "evals/inspect_gapbench/event_scorers.py",
        "inspect_task_sha256": "evals/inspect_gapbench/event_task.py",
    }


def load_event_contract(
    path: Path = DEFAULT_CONTRACT_PATH, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="fixed-data event contract")
    _require(contract.get("schema_version") == CONTRACT_SCHEMA, "unsupported event contract")
    _require(
        contract.get("contract_id") == "sim2claw-fixed-data-event-pipeline-20260720-v1",
        "event contract identity changed",
    )
    _require(
        contract.get("expected_inventory")
        == {
            "episode_count": 18,
            "sample_count": 7741,
            "train_episode_count": 15,
            "held_out_episode_count": 3,
            "move_id_count": 9,
        },
        "event inventory changed",
    )
    partition = contract.get("partition_policy", {})
    _require(partition.get("development_default") == "train", "development partition changed")
    _require(partition.get("whole_episode_only") is True, "row-level splitting became possible")
    _require(partition.get("row_level_split_forbidden") is True, "row split guard changed")
    _require(
        partition.get("held_out_requires_evaluator_owned_invocation") is True,
        "held-out invocation guard changed",
    )
    extraction = contract.get("event_extraction", {})
    _require(extraction.get("joint_signal") == "follower_actual_position_degrees", "event signal changed")
    _require(extraction.get("gripper_joint_index") == 5, "gripper index changed")
    _require(extraction.get("contact_claim_allowed") is False, "contact claim became enabled")
    phase_order = tuple(extraction.get("phase_order", []))
    event_order = tuple(extraction.get("event_order", []))
    _require(len(phase_order) == 5 and len(set(phase_order)) == 5, "phase inventory changed")
    _require(len(event_order) == 6 and len(set(event_order)) == 6, "event inventory changed")
    visual = contract.get("visual_evidence", {})
    _require(len(visual.get("slots", [])) == 9, "visual slot inventory changed")
    _require(visual.get("metric_pose_weight") == 0.0, "visual evidence gained metric weight")
    _require(visual.get("contact_ground_truth_weight") == 0.0, "visual evidence became contact truth")
    tools = contract.get("inspect_tools", {})
    _require(tuple(tools.get("names", [])) == TOOL_NAMES, "Inspect event tool inventory changed")
    _require(tools.get("physical_actions") == 0, "event task gained physical actions")
    authority = contract.get("authority", {})
    _require(authority and all(value is False for value in authority.values()), "event authority widened")
    for binding in contract.get("source_bindings", {}).values():
        source = _repo_path(repo_root, str(binding.get("path")), "event source binding")
        _require(source.is_file(), f"event source is missing: {source}")
        _require(sha256_file(source) == binding.get("sha256"), f"event source changed: {source.name}")
    bindings = contract.get("artifact_bindings", {})
    for field, relative in _artifact_binding_paths().items():
        artifact = _repo_path(repo_root, relative, field)
        _require(artifact.is_file(), f"event pipeline artifact is missing: {relative}")
        _require(sha256_file(artifact) == bindings.get(field), f"event pipeline artifact changed: {relative}")
    skill_root = repo_root / "evals" / "inspect_gapbench" / "event_skills"
    skill_paths = sorted(skill_root.glob("*/SKILL.md"))
    _require(len(skill_paths) == 1, "event skill inventory changed")
    skill_digest = canonical_digest(
        {item.parent.name: sha256_file(item) for item in skill_paths}
    )
    _require(
        skill_digest == bindings.get("inspect_skill_bundle_sha256"),
        "event skill bundle changed",
    )
    return contract


def _load_sources(
    contract: Mapping[str, Any], repo_root: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    bindings = contract["source_bindings"]
    catalog = load_json_object(
        _repo_path(repo_root, bindings["catalog"]["path"], "catalog"),
        label="physical catalog",
    )
    split = load_json_object(
        _repo_path(repo_root, bindings["split"]["path"], "split"),
        label="physical split",
    )
    source_fit = load_json_object(
        _repo_path(
            repo_root,
            bindings["source_fit_event_contract"]["path"],
            "source fit contract",
        ),
        label="source fit contract",
    )
    _require(split.get("frozen") is True, "physical split is no longer frozen")
    _require(split.get("unit") == "whole_episode", "physical split unit changed")
    _require(split.get("split_counts") == {"held_out": 3, "train": 15}, "split counts changed")
    _require(
        split.get("source_catalog", {}).get("sha256")
        == contract["source_bindings"]["catalog"]["sha256"],
        "split catalog binding changed",
    )
    source_events = source_fit.get("event_extraction", {})
    contract_events = contract["event_extraction"]
    for key in (
        "joint_signal",
        "gripper_joint_index",
        "first_open_search_fraction",
        "destination_open_search_start_fraction",
    ):
        _require(source_events.get(key) == contract_events.get(key), f"event setting changed: {key}")
    _require(
        source_events.get("near_close_fraction_of_source_open_to_valley_range")
        == contract_events.get("transition_fraction_of_open_to_valley_range"),
        "near-close event threshold changed",
    )
    return catalog, split, source_fit


def _split_map(split: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in split.get("episodes", []):
        episode_id = str(row.get("episode_id", ""))
        role = str(row.get("split", ""))
        _require(episode_id and role in {"train", "held_out"}, "invalid split episode")
        _require(episode_id not in result, "duplicate split episode")
        result[episode_id] = role
    _require(Counter(result.values()) == {"train": 15, "held_out": 3}, "split inventory changed")
    return result


def _selected_episodes(
    catalog: Mapping[str, Any],
    split: Mapping[str, Any],
    partition: str,
    *,
    evaluator_owned: bool,
) -> list[dict[str, Any]]:
    _require(partition in {"train", "held_out", "all"}, "unsupported event partition")
    if partition != "train":
        _require(evaluator_owned, "held-out data require evaluator-owned invocation")
    roles = _split_map(split)
    episodes = catalog.get("episodes")
    _require(isinstance(episodes, list) and len(episodes) == 18, "catalog episode inventory changed")
    catalog_ids = {str(item.get("recording_id")) for item in episodes}
    _require(catalog_ids == set(roles), "catalog and split episode identities differ")
    selected = [
        dict(item)
        for item in episodes
        if partition == "all" or roles[str(item["recording_id"])] == partition
    ]
    expected = {"train": 15, "held_out": 3, "all": 18}[partition]
    _require(len(selected) == expected, "selected partition count changed")
    for item in selected:
        item["partition"] = roles[str(item["recording_id"])]
    return selected


def _load_rows(path: Path, recording_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    previous_timestamp: float | None = None
    with path.open("r", encoding="utf-8") as handle:
        for expected_index, line in enumerate(handle):
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as error:
                raise InteractionEventError(f"{recording_id} samples are invalid JSON") from error
            _require(isinstance(raw, dict), f"{recording_id} sample is not an object")
            _require(raw.get("schema_version") == "sim2claw.physical_teleoperation_sample.v1", f"{recording_id} sample schema changed")
            _require(raw.get("sample_index") == expected_index, f"{recording_id} sample indices changed")
            timestamp = _finite(raw.get("timestamp_monotonic_seconds"), "timestamp")
            if previous_timestamp is not None:
                _require(timestamp > previous_timestamp, f"{recording_id} timestamps are not increasing")
            previous_timestamp = timestamp
            current = raw.get("available_motor_current_raw")
            _require(isinstance(current, dict) and set(current) == set(JOINT_NAMES), f"{recording_id} current inventory changed")
            normalized = dict(raw)
            for field in (
                "follower_requested_degrees",
                "follower_command_degrees",
                "follower_actual_position_degrees",
                "follower_actual_velocity_degrees_s",
            ):
                normalized[field] = _vector(raw.get(field), f"{recording_id} {field}")
            normalized["timestamp_monotonic_seconds"] = timestamp
            normalized["overhead_video_time_seconds"] = _finite(
                raw.get("overhead_video_time_seconds"), "video timestamp"
            )
            normalized["available_motor_current_raw"] = {
                name: _finite(current[name], f"{recording_id} {name} current")
                for name in JOINT_NAMES
            }
            rows.append(normalized)
    _require(len(rows) >= 10, f"{recording_id} has too few samples")
    return rows


def extract_event_indices(
    rows: Sequence[Mapping[str, Any]], contract: Mapping[str, Any]
) -> dict[str, int]:
    settings = contract["event_extraction"]
    gripper = np.asarray(
        [row[settings["joint_signal"]][settings["gripper_joint_index"]] for row in rows],
        dtype=np.float64,
    )
    _require(gripper.shape == (len(rows),) and np.isfinite(gripper).all(), "gripper signal is invalid")
    amplitude = float(np.max(gripper) - np.min(gripper))
    _require(amplitude > 1.0, "gripper signal has no usable amplitude")
    search_end = max(2, int(len(rows) * settings["first_open_search_fraction"]))
    destination_start = max(
        search_end,
        int(len(rows) * settings["destination_open_search_start_fraction"]),
    )
    _require(destination_start < len(rows) - 1, "destination event search is empty")
    open_index = int(np.argmax(gripper[:search_end]))
    destination_open = destination_start + int(np.argmax(gripper[destination_start:]))
    _require(destination_open > open_index + 2, "opening peaks are not ordered")
    valley = open_index + 1 + int(np.argmin(gripper[open_index + 1 : destination_open]))
    fraction = float(settings["transition_fraction_of_open_to_valley_range"])
    _require(0.0 < fraction < 0.5, "transition fraction is invalid")
    source_range = float(gripper[open_index] - gripper[valley])
    destination_range = float(gripper[destination_open] - gripper[valley])
    _require(source_range > 1.0 and destination_range > 1.0, "open-close event range is invalid")
    closure_onset_candidates = np.flatnonzero(
        gripper[open_index : valley + 1]
        <= gripper[open_index] - fraction * source_range
    )
    near_closed_candidates = np.flatnonzero(
        gripper[open_index : valley + 1]
        <= gripper[valley] + fraction * source_range
    )
    release_onset_candidates = np.flatnonzero(
        gripper[valley : destination_open + 1]
        >= gripper[valley] + fraction * destination_range
    )
    _require(
        closure_onset_candidates.size > 0
        and near_closed_candidates.size > 0
        and release_onset_candidates.size > 0,
        "gripper transition threshold was not crossed",
    )
    closure_onset = open_index + int(closure_onset_candidates[0])
    near_closed = open_index + int(near_closed_candidates[0])
    release_onset = valley + int(release_onset_candidates[0])
    ordered = (open_index, closure_onset, near_closed, valley, release_onset, destination_open)
    _require(list(ordered) == sorted(ordered), "event indices are not ordered")
    _require(closure_onset < near_closed < release_onset < destination_open, "event intervals collapsed")
    return dict(zip(settings["event_order"], ordered, strict=True))


def _phase_intervals(
    sample_count: int,
    events: Mapping[str, int],
    phase_order: Sequence[str],
) -> list[dict[str, Any]]:
    boundaries = (
        0,
        events["closure_onset"],
        events["near_closed_crossing"] + 1,
        events["release_onset"],
        events["destination_open_peak"] + 1,
        sample_count,
    )
    _require(list(boundaries) == sorted(boundaries), "phase boundaries are not ordered")
    intervals = []
    for phase, start, end in zip(phase_order, boundaries[:-1], boundaries[1:], strict=True):
        _require(end > start, f"phase {phase} is empty")
        intervals.append(
            {
                "phase": phase,
                "start_sample_index_inclusive": int(start),
                "end_sample_index_exclusive": int(end),
                "sample_count": int(end - start),
            }
        )
    _require(sum(item["sample_count"] for item in intervals) == sample_count, "phases do not cover every row")
    return intervals


def _phase_for_index(index: int, intervals: Sequence[Mapping[str, Any]]) -> str:
    matches = [
        item["phase"]
        for item in intervals
        if item["start_sample_index_inclusive"] <= index < item["end_sample_index_exclusive"]
    ]
    _require(len(matches) == 1, "sample does not map to exactly one phase")
    return str(matches[0])


def _joint_unit(index: int) -> str:
    return "percent" if index == 5 else "degree"


def _phase_metrics(
    rows: Sequence[Mapping[str, Any]], intervals: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    results = []
    for interval in intervals:
        start = int(interval["start_sample_index_inclusive"])
        end = int(interval["end_sample_index_exclusive"])
        selected = rows[start:end]
        commanded = np.asarray([row["follower_command_degrees"] for row in selected])
        measured = np.asarray([row["follower_actual_position_degrees"] for row in selected])
        velocity = np.asarray([row["follower_actual_velocity_degrees_s"] for row in selected])
        tracking = []
        for index, name in enumerate(JOINT_NAMES):
            unit = _joint_unit(index)
            tracking.append(
                {
                    "joint_name": name,
                    "measured_minus_commanded": _summary(
                        measured[:, index] - commanded[:, index], unit
                    ),
                    "measured_velocity": _summary(
                        velocity[:, index], f"{unit}_per_second"
                    ),
                }
            )
        timestamps = np.asarray([row["timestamp_monotonic_seconds"] for row in selected])
        results.append(
            {
                **copy.deepcopy(dict(interval)),
                "duration_seconds": float(timestamps[-1] - timestamps[0]) if len(timestamps) > 1 else 0.0,
                "joint_metrics": tracking,
            }
        )
    return results


def _apparent_lag(
    rows: Sequence[Mapping[str, Any]], maximum_lag: int
) -> list[dict[str, Any]]:
    command = np.asarray([row["follower_command_degrees"] for row in rows], dtype=np.float64)
    measured = np.asarray([row["follower_actual_position_degrees"] for row in rows], dtype=np.float64)
    command_delta = np.diff(command, axis=0)
    measured_delta = np.diff(measured, axis=0)
    dt = float(np.mean(np.diff([row["timestamp_monotonic_seconds"] for row in rows])))
    result = []
    for joint_index, name in enumerate(JOINT_NAMES):
        candidates = []
        for lag in range(maximum_lag + 1):
            left = command_delta[: len(command_delta) - lag or None, joint_index]
            right = measured_delta[lag:, joint_index]
            if len(left) < 3 or float(np.std(left)) <= 1e-12 or float(np.std(right)) <= 1e-12:
                correlation = -1.0
            else:
                correlation = float(np.corrcoef(left, right)[0, 1])
                if not math.isfinite(correlation):
                    correlation = -1.0
            candidates.append((correlation, -lag, lag))
        correlation, _, lag = max(candidates)
        result.append(
            {
                "joint_name": name,
                "lag_samples": int(lag),
                "lag_seconds_from_mean_sample_interval": float(lag * dt),
                "delta_correlation": correlation,
                "semantics": "apparent_tracking_lag_not_command_to_actuation_latency",
            }
        )
    return result


def _mechanical_proxy(
    rows: Sequence[Mapping[str, Any]],
    events: Mapping[str, int],
    settings: Mapping[str, Any],
) -> dict[str, Any]:
    open_end = events["open_reference_peak"] + 1
    open_start = max(0, open_end - int(settings["open_baseline_window_samples"]))
    closed_start = events["near_closed_crossing"]
    closed_end = events["release_onset"]
    open_rows = [row for row in rows[open_start:open_end] if not row["current_telemetry_stale"]]
    closed_rows = [row for row in rows[closed_start:closed_end] if not row["current_telemetry_stale"]]
    _require(open_rows and closed_rows, "mechanical proxy has no non-stale cached current rows")
    open_current = np.asarray([row["available_motor_current_raw"]["gripper"] for row in open_rows])
    closed_current = np.asarray([row["available_motor_current_raw"]["gripper"] for row in closed_rows])
    commanded = np.asarray([row["follower_command_degrees"][5] for row in rows[closed_start:closed_end]])
    measured = np.asarray([row["follower_actual_position_degrees"][5] for row in rows[closed_start:closed_end]])
    velocity = np.asarray([row["follower_actual_velocity_degrees_s"][5] for row in rows[closed_start:closed_end]])
    open_median = float(np.median(open_current))
    closed_median = float(np.median(closed_current))
    gap = float(np.median(np.abs(commanded - measured)))
    flat_fraction = float(
        np.mean(
            np.abs(velocity)
            < float(settings["flat_gripper_velocity_absolute_threshold_per_second"])
        )
    )
    return {
        "open_baseline_sample_range": [open_start, open_end],
        "closed_candidate_sample_range": [closed_start, closed_end],
        "open_baseline_median_raw_current": open_median,
        "closed_median_raw_current": closed_median,
        "closed_p95_raw_current": float(np.quantile(closed_current, 0.95)),
        "closed_minus_open_median_raw_current": closed_median - open_median,
        "closed_median_absolute_command_measurement_gap_percent": gap,
        "closed_flat_measured_velocity_fraction": flat_fraction,
        "mechanically_loaded_closure_proxy_supported": closed_median > open_median and gap > 0.0,
        "raw_current_nominal_hz": sorted(
            {float(row["current_telemetry_hz"]) for row in rows}
        ),
        "raw_current_cached_between_reads": True,
        "fresh_current_read_row_identity_available": False,
        "empty_gripper_hard_stop_baseline_available": False,
        "physical_contact_observed": False,
        "instrumented_grasp_observed": False,
        "interpretation": "mechanical_load_proxy_may_include_object_contact_hard_stop_friction_or_controller_effects",
    }


def _phase_rows(
    recording_id: str,
    rows: Sequence[Mapping[str, Any]],
    events: Mapping[str, int],
    intervals: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    event_at_index: dict[int, list[str]] = {}
    for name, index in events.items():
        event_at_index.setdefault(int(index), []).append(name)
    payload_rows = []
    for index, row in enumerate(rows):
        command = row["follower_command_degrees"]
        measured = row["follower_actual_position_degrees"]
        velocity = row["follower_actual_velocity_degrees_s"]
        payload_rows.append(
            {
                "sample_index": index,
                "phase": _phase_for_index(index, intervals),
                "event_candidates": sorted(event_at_index.get(index, [])),
                "timestamp_monotonic_seconds": row["timestamp_monotonic_seconds"],
                "overhead_video_time_seconds": row["overhead_video_time_seconds"],
                "commanded_joint_position": command,
                "measured_joint_position": measured,
                "measured_joint_velocity": velocity,
                "measured_minus_commanded": [
                    float(actual - target) for actual, target in zip(measured, command, strict=True)
                ],
                "gripper_raw_current_proxy": row["available_motor_current_raw"]["gripper"],
                "current_telemetry_stale": bool(row["current_telemetry_stale"]),
            }
        )
    unsigned = {
        "schema_version": PHASE_ROWS_SCHEMA,
        "recording_id": recording_id,
        "joint_names": list(JOINT_NAMES),
        "row_count": len(payload_rows),
        "rows": payload_rows,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    return {**unsigned, "phase_rows_sha256": canonical_digest(unsigned)}


def _event_proposals(
    rows: Sequence[Mapping[str, Any]], events: Mapping[str, int]
) -> list[dict[str, Any]]:
    result = []
    for name, index in events.items():
        row = rows[index]
        result.append(
            {
                "event": name,
                "sample_index": int(index),
                "timestamp_monotonic_seconds": row["timestamp_monotonic_seconds"],
                "overhead_video_time_seconds": row["overhead_video_time_seconds"],
                "gripper_command_percent": row["follower_command_degrees"][5],
                "gripper_measured_percent": row["follower_actual_position_degrees"][5],
                "gripper_measured_velocity_percent_per_second": row[
                    "follower_actual_velocity_degrees_s"
                ][5],
                "gripper_raw_current_proxy": row["available_motor_current_raw"]["gripper"],
                "semantics": "deterministic_kinematic_candidate_not_measured_contact",
            }
        )
    return result


def _visual_requests(
    rows: Sequence[Mapping[str, Any]],
    events: Mapping[str, int],
    contract: Mapping[str, Any],
) -> list[dict[str, Any]]:
    midpoint = (events["near_closed_crossing"] + events["release_onset"]) // 2
    anchors = {
        "first_sample": 0,
        "last_sample": len(rows) - 1,
        "closed_interval_midpoint": midpoint,
        **events,
    }
    result = []
    for slot in contract["visual_evidence"]["slots"]:
        anchor = str(slot["anchor"])
        _require(anchor in anchors, f"unknown visual anchor: {anchor}")
        index = int(anchors[anchor])
        base_time = float(rows[index]["overhead_video_time_seconds"])
        result.append(
            {
                "slot": slot["name"],
                "anchor": anchor,
                "anchor_sample_index": index,
                "offset_seconds": float(slot["offset_seconds"]),
                "requested_video_time_seconds": base_time + float(slot["offset_seconds"]),
            }
        )
    return result


def _decode_frame(
    capture: cv2.VideoCapture,
    requested_time: float,
    fps: float,
    frame_count: int,
) -> tuple[np.ndarray, int, float]:
    frame_index = min(max(int(round(requested_time * fps)), 0), frame_count - 1)
    capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ok, frame = capture.read()
    _require(ok and frame is not None, f"video frame decode failed at {frame_index}")
    return frame, frame_index, frame_index / fps


def render_interaction_strip(
    output_path: Path,
    video_path: Path,
    requests: Sequence[Mapping[str, Any]],
    *,
    source_video_sha256: str,
    orientation_rotation_degrees: int,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    _require(sha256_file(video_path) == source_video_sha256, "source video changed before strip render")
    _require(orientation_rotation_degrees in {0, 180}, "unsupported video orientation")
    capture = cv2.VideoCapture(str(video_path))
    _require(capture.isOpened(), "could not open source video")
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    _require(math.isfinite(fps) and fps > 0.0 and frame_count > 0, "source video metadata is invalid")
    visual = contract["visual_evidence"]
    cell_width = int(visual["cell_width"])
    cell_height = int(visual["cell_height"])
    frame_height = int(visual["frame_height"])
    columns = int(visual["strip_columns"])
    rows_count = int(visual["strip_rows"])
    canvas = Image.new("RGB", (columns * cell_width, rows_count * cell_height), "white")
    draw = ImageDraw.Draw(canvas)
    decoded_rows = []
    try:
        for slot_index, request in enumerate(requests):
            frame, frame_index, decoded_time = _decode_frame(
                capture, float(request["requested_video_time_seconds"]), fps, frame_count
            )
            if orientation_rotation_degrees == 180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            image.thumbnail((cell_width, frame_height), Image.Resampling.LANCZOS)
            column = slot_index % columns
            row = slot_index // columns
            x = column * cell_width + (cell_width - image.width) // 2
            y = row * cell_height
            canvas.paste(image, (x, y))
            label = (
                f"{request['slot']} | req {float(request['requested_video_time_seconds']):.3f}s "
                f"| frame {frame_index}"
            )
            draw.text((column * cell_width + 6, y + frame_height + 8), label, fill="black")
            decoded_rows.append(
                {
                    **copy.deepcopy(dict(request)),
                    "decoded_frame_index": frame_index,
                    "decoded_video_time_seconds": decoded_time,
                    "decode_time_error_seconds": decoded_time
                    - float(request["requested_video_time_seconds"]),
                }
            )
    finally:
        capture.release()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, format="PNG", optimize=False, compress_level=9)
    return {
        "status": "materialized",
        "path": output_path.name,
        "sha256": sha256_file(output_path),
        "source_video_sha256": source_video_sha256,
        "source_fps": fps,
        "source_frame_count": frame_count,
        "orientation_rotation_degrees": orientation_rotation_degrees,
        "slots": decoded_rows,
        "measurement_semantics": "qualitative_multiframe_evidence_not_metric_pose_or_contact_truth",
    }


def compile_episode_events(
    episode: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    contract: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    recording_id = str(episode["recording_id"])
    events = extract_event_indices(rows, contract)
    intervals = _phase_intervals(
        len(rows), events, contract["event_extraction"]["phase_order"]
    )
    proposals = _event_proposals(rows, events)
    phase_rows = _phase_rows(recording_id, rows, events, intervals)
    unsigned = {
        "schema_version": EPISODE_SCHEMA,
        "recording_id": recording_id,
        "partition": episode["partition"],
        "move_id": episode["move_id"],
        "source_square": episode["source_square"],
        "destination_square": episode["destination_square"],
        "proof_class": "retrospective_physical_multimodal_derived_candidates",
        "sample_count": len(rows),
        "source_samples_sha256": episode["samples_sha256"],
        "source_video_sha256": episode["overhead_video_sha256"],
        "event_proposals": proposals,
        "phase_intervals": intervals,
        "phase_metrics": _phase_metrics(rows, intervals),
        "mechanical_load_proxy": _mechanical_proxy(
            rows, events, contract["event_extraction"]
        ),
        "apparent_tracking_lag": _apparent_lag(
            rows, int(contract["event_extraction"]["maximum_apparent_lag_samples"])
        ),
        "visual_requests": _visual_requests(rows, events, contract),
        "visual_evidence": {
            "status": "not_materialized",
            "measurement_semantics": "qualitative_multiframe_evidence_not_metric_pose_or_contact_truth",
        },
        "receipt_outcome": {
            "label": episode["outcome_label"],
            "actor": "human_teleoperator",
            "available_to_visual_annotator": False,
            "instrumented_grasp_measurement": False,
        },
        "unavailable": {
            "exact_contact_time": True,
            "metric_contact_point": True,
            "calibrated_grasp_force": True,
            "metric_object_trajectory": True,
            "true_command_to_actuation_latency": True,
        },
        "claim_boundary": CLAIM_BOUNDARY,
    }
    return {**unsigned, "event_episode_sha256": canonical_digest(unsigned)}, phase_rows


def _validate_annotation_payload(
    annotation: Mapping[str, Any], contract: Mapping[str, Any]
) -> dict[str, Any]:
    expected_keys = {
        "schema_version",
        "recording_id",
        "event_episode_sha256",
        "fields",
        "occlusion",
        "confidence",
        "rationale",
        "annotator_system",
        "model_identifier",
        "prompt_sha256",
        "receipt_outcome_shown",
    }
    _require(set(annotation) == expected_keys, "visual annotation keys changed")
    _require(annotation.get("schema_version") == ANNOTATION_SCHEMA, "visual annotation schema changed")
    config = contract["visual_annotation"]
    fields = annotation.get("fields")
    _require(isinstance(fields, dict) and tuple(fields) == tuple(config["fields"]), "visual annotation fields changed")
    allowed = set(config["enum"])
    _require(all(value in allowed for value in fields.values()), "visual annotation enum is invalid")
    _require(annotation.get("occlusion") in config["occlusion_enum"], "occlusion enum is invalid")
    _require(annotation.get("confidence") in config["confidence_enum"], "confidence enum is invalid")
    rationale = str(annotation.get("rationale", ""))
    _require(len(rationale) <= int(config["maximum_rationale_characters"]), "annotation rationale is too long")
    _require(str(annotation.get("annotator_system", "")).strip() != "", "annotator system is missing")
    _require(str(annotation.get("model_identifier", "")).strip() != "", "model identifier is missing")
    prompt_digest = str(annotation.get("prompt_sha256", ""))
    _require(len(prompt_digest) == 64, "annotation prompt digest is invalid")
    _require(annotation.get("receipt_outcome_shown") is False, "receipt outcome leaked to visual annotator")
    unsigned = copy.deepcopy(dict(annotation))
    return {**unsigned, "annotation_sha256": canonical_digest(unsigned)}


def validate_visual_annotation(
    annotation: Mapping[str, Any],
    *,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_event_contract(contract_path, repo_root=repo_root)
    return _validate_annotation_payload(annotation, contract)


def compile_annotation_consensus(
    annotations: Sequence[Mapping[str, Any]],
    *,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_event_contract(contract_path, repo_root=repo_root)
    _require(len(annotations) >= 2, "consensus requires at least two annotations")
    validated = []
    for item in annotations:
        candidate = copy.deepcopy(dict(item))
        claimed_digest = candidate.pop("annotation_sha256", None)
        verified = _validate_annotation_payload(candidate, contract)
        if claimed_digest is not None:
            _require(
                claimed_digest == verified["annotation_sha256"],
                "signed annotation digest changed",
            )
        validated.append(verified)
    recording_ids = {item["recording_id"] for item in validated}
    event_digests = {item["event_episode_sha256"] for item in validated}
    annotators = {(item["annotator_system"], item["model_identifier"]) for item in validated}
    _require(len(recording_ids) == 1 and len(event_digests) == 1, "annotations bind different episodes")
    _require(len(annotators) == len(validated), "consensus annotations duplicate a system identity")
    field_rows = {}
    for field in contract["visual_annotation"]["fields"]:
        counts = Counter(item["fields"][field] for item in validated)
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        winner, count = ordered[0]
        strict_majority = count > len(validated) / 2
        field_rows[field] = {
            "counts": dict(sorted(counts.items())),
            "consensus": winner if strict_majority else "disagreement",
            "strict_majority": strict_majority,
        }
    unsigned = {
        "schema_version": CONSENSUS_SCHEMA,
        "recording_id": validated[0]["recording_id"],
        "event_episode_sha256": validated[0]["event_episode_sha256"],
        "annotation_count": len(validated),
        "annotation_sha256s": sorted(item["annotation_sha256"] for item in validated),
        "fields": field_rows,
        "model_judge_used": False,
        "ground_truth_claimed": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    return {**unsigned, "consensus_sha256": canonical_digest(unsigned)}


def build_phase_balanced_manifest(
    episodes: Sequence[Mapping[str, Any]],
    phase_artifacts: Mapping[str, Mapping[str, Any]],
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    weights = contract["phase_sampling_ablation"]["weights"]
    rows = []
    for episode in episodes:
        recording_id = str(episode["recording_id"])
        artifact = phase_artifacts[recording_id]
        _require(artifact.get("schema_version") == PHASE_ROWS_SCHEMA, "phase row schema changed")
        _require(artifact.get("row_count") == episode["sample_count"], "phase row count changed")
        for row in artifact["rows"]:
            phase = str(row["phase"])
            _require(phase in weights, "sampler phase is not frozen")
            rows.append(
                {
                    "recording_id": recording_id,
                    "source_samples_sha256": episode["samples_sha256"],
                    "sample_index": int(row["sample_index"]),
                    "phase": phase,
                    "weight": float(weights[phase]),
                }
            )
    identities = {(item["recording_id"], item["sample_index"]) for item in rows}
    _require(len(identities) == len(rows), "sampler contains duplicate source rows")
    total_weight = sum(item["weight"] for item in rows)
    for row in rows:
        row["normalized_probability"] = row["weight"] / total_weight
    unsigned = {
        "schema_version": SAMPLER_SCHEMA,
        "seed": contract["phase_sampling_ablation"]["seed"],
        "partition": "train",
        "source_episode_count": len(episodes),
        "unique_source_row_count": len(rows),
        "independent_episode_count": len(episodes),
        "phase_counts": dict(sorted(Counter(item["phase"] for item in rows).items())),
        "weights": copy.deepcopy(weights),
        "rows": rows,
        "source_rows_mutated": False,
        "weighted_draws_are_independent_evidence": False,
        "training_admission_granted": False,
        "training_promoted": False,
    }
    return {**unsigned, "sampler_manifest_sha256": canonical_digest(unsigned)}


def current_real_sim_status(
    episode_summaries: Sequence[Mapping[str, Any]], contract: Mapping[str, Any]
) -> dict[str, Any]:
    blockers = [
        {
            "recording_id": item["recording_id"],
            "status": "blocked",
            "reasons": [
                "physical_to_simulator_transform_provisional",
                "exact_unclipped_replay_ineligible",
                "simulator_trace_unavailable",
            ],
        }
        for item in episode_summaries
    ]
    unsigned = {
        "schema_version": SIM_STATUS_SCHEMA,
        "episode_count": len(blockers),
        "eligible_episode_count": 0,
        "blocked_episode_count": len(blockers),
        "episodes": blockers,
        "comparison_executed": False,
        "blocked_status_is_reportable_result": contract["real_sim_comparison"][
            "blocked_status_is_reportable_result"
        ],
        "claim_boundary": CLAIM_BOUNDARY,
    }
    return {**unsigned, "status_sha256": canonical_digest(unsigned)}


def compare_event_conditioned_real_sim(
    event_episode: Mapping[str, Any],
    phase_rows: Mapping[str, Any],
    sim_trace: Mapping[str, Any],
    replay_attestation: Mapping[str, Any],
) -> dict[str, Any]:
    _require(sim_trace.get("schema_version") == SIM_TRACE_SCHEMA, "sim trace schema changed")
    recording_id = str(event_episode.get("recording_id", ""))
    _require(sim_trace.get("recording_id") == recording_id, "sim trace episode changed")
    _require(phase_rows.get("recording_id") == recording_id, "phase trace episode changed")
    _require(replay_attestation.get("exact_replay_eligible") is True, "exact replay is not eligible")
    _require(replay_attestation.get("transform_status") == "approved", "replay transform is not approved")
    transform_digest = str(replay_attestation.get("approved_transform_sha256", ""))
    _require(len(transform_digest) == 64, "approved transform digest is invalid")
    _require(replay_attestation.get("clipping_count") == 0, "replay contains clipping")
    _require(replay_attestation.get("repaired_row_count") == 0, "replay contains repaired rows")
    _require(replay_attestation.get("canonical_velocity") is True, "replay lacks canonical velocity")
    _require(
        replay_attestation.get("source_samples_sha256")
        == event_episode.get("source_samples_sha256"),
        "replay source identity changed",
    )
    real_rows = phase_rows.get("rows")
    sim_rows = sim_trace.get("rows")
    _require(isinstance(real_rows, list) and isinstance(sim_rows, list), "comparison rows are missing")
    _require(len(real_rows) == len(sim_rows) == event_episode.get("sample_count"), "comparison row count changed")
    paired = []
    for expected_index, (real, simulated) in enumerate(zip(real_rows, sim_rows, strict=True)):
        _require(real.get("sample_index") == simulated.get("sample_index") == expected_index, "comparison row alignment changed")
        sim_position = _vector(simulated.get("simulated_joint_position_source_units"), "simulated position")
        sim_velocity = _vector(simulated.get("simulated_joint_velocity_source_units"), "simulated velocity")
        paired.append((real, sim_position, sim_velocity))
    phases = []
    for phase in event_episode["phase_intervals"]:
        start = int(phase["start_sample_index_inclusive"])
        end = int(phase["end_sample_index_exclusive"])
        selected = paired[start:end]
        actual = np.asarray([item[0]["measured_joint_position"] for item in selected])
        actual_velocity = np.asarray([item[0]["measured_joint_velocity"] for item in selected])
        simulated = np.asarray([item[1] for item in selected])
        simulated_velocity = np.asarray([item[2] for item in selected])
        joint_rows = []
        for index, name in enumerate(JOINT_NAMES):
            unit = _joint_unit(index)
            joint_rows.append(
                {
                    "joint_name": name,
                    "simulated_minus_real_position": _summary(
                        simulated[:, index] - actual[:, index], unit
                    ),
                    "simulated_minus_real_velocity": _summary(
                        simulated_velocity[:, index] - actual_velocity[:, index],
                        f"{unit}_per_second",
                    ),
                }
            )
        phases.append({"phase": phase["phase"], "sample_count": len(selected), "joint_metrics": joint_rows})
    unsigned = {
        "schema_version": SIM_COMPARISON_SCHEMA,
        "recording_id": recording_id,
        "source_samples_sha256": event_episode["source_samples_sha256"],
        "event_episode_sha256": event_episode["event_episode_sha256"],
        "sim_trace_sha256": canonical_digest(sim_trace),
        "approved_transform_sha256": transform_digest,
        "sample_count": len(paired),
        "phase_metrics": phases,
        "dynamic_time_warping_used_for_primary_metric": False,
        "exact_row_alignment": True,
        "comparison_scope": "event_conditioned_joint_tracking_only",
        "object_or_contact_dynamics_verified": False,
        "physical_transfer_proof": False,
    }
    return {**unsigned, "comparison_sha256": canonical_digest(unsigned)}


def materialize_interaction_event_pipeline(
    output_root: Path,
    *,
    partition: str = "train",
    evaluator_owned: bool = False,
    render_visuals: bool = True,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_event_contract(contract_path, repo_root=repo_root)
    catalog, split, _ = _load_sources(contract, repo_root)
    episodes = _selected_episodes(
        catalog, split, partition, evaluator_owned=evaluator_owned
    )
    output_root = output_root.resolve()
    summaries = []
    compiled_events: list[dict[str, Any]] = []
    phase_artifacts: dict[str, dict[str, Any]] = {}
    total_rows = 0
    for episode in episodes:
        recording_id = str(episode["recording_id"])
        assets = episode["assets"]
        samples_path = _repo_path(repo_root, assets["samples"], f"{recording_id} samples")
        receipt_path = _repo_path(repo_root, assets["receipt"], f"{recording_id} receipt")
        video_path = _repo_path(repo_root, assets["overhead_video"], f"{recording_id} video")
        for path, expected, label in (
            (samples_path, episode["samples_sha256"], "samples"),
            (receipt_path, episode["receipt_sha256"], "receipt"),
            (video_path, episode["overhead_video_sha256"], "video"),
        ):
            _require(path.is_file() and sha256_file(path) == expected, f"{recording_id} {label} changed")
        rows = _load_rows(samples_path, recording_id)
        _require(len(rows) == episode["sample_count"], f"{recording_id} sample count changed")
        receipt = load_json_object(receipt_path, label=f"{recording_id} receipt")
        _require(receipt.get("outcome_label") == episode["outcome_label"], "receipt outcome changed")
        event_episode, phase_rows = compile_episode_events(episode, rows, contract)
        episode_root = output_root / "episodes" / recording_id
        if render_visuals:
            visual = render_interaction_strip(
                episode_root / "interaction_strip.png",
                video_path,
                event_episode["visual_requests"],
                source_video_sha256=episode["overhead_video_sha256"],
                orientation_rotation_degrees=int(
                    receipt["overhead_video"]["orientation_rotation_degrees"]
                ),
                contract=contract,
            )
            unsigned = dict(event_episode)
            unsigned.pop("event_episode_sha256")
            unsigned["visual_evidence"] = visual
            event_episode = {
                **unsigned,
                "event_episode_sha256": canonical_digest(unsigned),
            }
        annotation_template = {
            "schema_version": ANNOTATION_SCHEMA,
            "recording_id": recording_id,
            "event_episode_sha256": event_episode["event_episode_sha256"],
            "fields": {
                field: "ambiguous" for field in contract["visual_annotation"]["fields"]
            },
            "occlusion": "unknown",
            "confidence": "low",
            "rationale": "",
            "annotator_system": "replace_before_submission",
            "model_identifier": "replace_before_submission",
            "prompt_sha256": canonical_digest(
                {
                    "recording_id": recording_id,
                    "receipt_outcome_shown": False,
                    "fields": contract["visual_annotation"]["fields"],
                }
            ),
            "receipt_outcome_shown": False,
        }
        atomic_write_json(episode_root / "interaction_events.json", event_episode)
        atomic_write_json(episode_root / "phase_rows.json", phase_rows)
        atomic_write_json(episode_root / "visual_annotation_template.json", annotation_template)
        summaries.append(
            {
                "recording_id": recording_id,
                "partition": episode["partition"],
                "move_id": episode["move_id"],
                "sample_count": len(rows),
                "event_episode_sha256": event_episode["event_episode_sha256"],
                "phase_rows_sha256": phase_rows["phase_rows_sha256"],
                "events_path": (Path("episodes") / recording_id / "interaction_events.json").as_posix(),
                "phase_rows_path": (Path("episodes") / recording_id / "phase_rows.json").as_posix(),
                "strip_path": (
                    (Path("episodes") / recording_id / "interaction_strip.png").as_posix()
                    if render_visuals
                    else None
                ),
            }
        )
        compiled_events.append(event_episode)
        phase_artifacts[recording_id] = phase_rows
        total_rows += len(rows)
    sampler = None
    if partition == "train":
        sampler = build_phase_balanced_manifest(episodes, phase_artifacts, contract)
        atomic_write_json(output_root / "phase_balanced_sampler_manifest.json", sampler)
    sim_status = current_real_sim_status(summaries, contract)
    atomic_write_json(output_root / "real_sim_comparison_status.json", sim_status)
    mechanical = [item["mechanical_load_proxy"] for item in compiled_events]
    event_conditioned_tracking = []
    for phase in contract["event_extraction"]["phase_order"]:
        phase_episodes = [
            next(row for row in item["phase_metrics"] if row["phase"] == phase)
            for item in compiled_events
        ]
        joint_rows = []
        for index, name in enumerate(JOINT_NAMES):
            rmses = [
                next(
                    row for row in episode["joint_metrics"] if row["joint_name"] == name
                )["measured_minus_commanded"]["rmse"]
                for episode in phase_episodes
            ]
            joint_rows.append(
                {
                    "joint_name": name,
                    "episode_tracking_rmse_distribution": _distribution_summary(
                        rmses, _joint_unit(index)
                    ),
                }
            )
        event_conditioned_tracking.append(
            {"phase": phase, "episode_count": len(phase_episodes), "joint_metrics": joint_rows}
        )
    unsigned = {
        "schema_version": CORPUS_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": sha256_file(contract_path),
        "partition": partition,
        "evaluator_owned": evaluator_owned,
        "episode_count": len(summaries),
        "sample_count": total_rows,
        "independent_episode_count": len(summaries),
        "event_candidate_count": 6 * len(summaries),
        "phase_interval_count": 5 * len(summaries),
        "visual_strip_count": len(summaries) if render_visuals else 0,
        "episodes": summaries,
        "phase_counts": dict(
            sorted(
                Counter(
                    row["phase"]
                    for artifact in phase_artifacts.values()
                    for row in artifact["rows"]
                ).items()
            )
        ),
        "aggregate_mechanical_load_proxy": {
            "mechanically_loaded_closure_proxy_supported_episode_count": sum(
                bool(item["mechanically_loaded_closure_proxy_supported"])
                for item in mechanical
            ),
            "episode_closed_flat_fraction": _distribution_summary(
                [item["closed_flat_measured_velocity_fraction"] for item in mechanical],
                "fraction",
            ),
            "episode_closed_minus_open_median_raw_current": _distribution_summary(
                [item["closed_minus_open_median_raw_current"] for item in mechanical],
                "device_raw_present_current",
            ),
            "episode_closed_median_absolute_command_measurement_gap": _distribution_summary(
                [
                    item["closed_median_absolute_command_measurement_gap_percent"]
                    for item in mechanical
                ],
                "percent",
            ),
            "physical_contact_observed_episode_count": 0,
            "empty_gripper_hard_stop_baseline_available": False,
        },
        "event_conditioned_tracking": event_conditioned_tracking,
        "sampler_manifest_sha256": (
            sampler["sampler_manifest_sha256"] if sampler is not None else None
        ),
        "real_sim_status_sha256": sim_status["status_sha256"],
        "provider_calls": 0,
        "physical_actions": 0,
        "measured_contact_claimed": False,
        "metric_object_trajectory_claimed": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    corpus = {**unsigned, "corpus_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_root / "interaction_event_corpus.json", corpus)
    return corpus


class InteractionEventSession:
    """Bounded read/annotation interface over one materialized event episode."""

    def __init__(
        self,
        episode_manifest: Mapping[str, Any],
        artifact_root: Path,
        state_root: Path,
        *,
        contract_path: Path = DEFAULT_CONTRACT_PATH,
        repo_root: Path = REPO_ROOT,
        reset: bool = False,
    ):
        self.contract = load_event_contract(contract_path, repo_root=repo_root)
        self.recording_id = str(episode_manifest["recording_id"])
        self.partition = str(episode_manifest["partition"])
        root = artifact_root.resolve()
        self.event_path = (root / str(episode_manifest["events_path"])).resolve()
        self.phase_path = (root / str(episode_manifest["phase_rows_path"])).resolve()
        self.strip_path = (
            (root / str(episode_manifest["strip_path"])).resolve()
            if episode_manifest.get("strip_path")
            else None
        )
        for path in (self.event_path, self.phase_path, self.strip_path):
            if path is None:
                continue
            try:
                path.relative_to(root)
            except ValueError as error:
                raise InteractionEventError("event artifact escaped its materialized root") from error
        self.event = load_json_object(self.event_path, label="interaction event episode")
        self.phase_rows = load_json_object(self.phase_path, label="interaction phase rows")
        _require(self.event.get("recording_id") == self.recording_id, "event episode identity changed")
        _require(self.phase_rows.get("recording_id") == self.recording_id, "phase row identity changed")
        if self.strip_path is not None:
            _require(
                self.strip_path.is_file()
                and sha256_file(self.strip_path) == self.event["visual_evidence"]["sha256"],
                "interaction strip changed",
            )
        self.state_path = state_root.resolve() / f"{self.recording_id}.json"
        if reset or not self.state_path.is_file():
            self.state = {
                "schema_version": "sim2claw.interaction_event_session.v1",
                "recording_id": self.recording_id,
                "metric_reads": 0,
                "strip_reads": 0,
                "annotation": None,
                "terminal_receipt": None,
            }
            atomic_write_json(self.state_path, self.state)
        else:
            self.state = load_json_object(self.state_path, label="interaction event session")

    def _save(self) -> None:
        atomic_write_json(self.state_path, self.state)

    def _identity(self, recording_id: str) -> None:
        _require(recording_id == self.recording_id, "recording_id is not active")
        _require(self.state.get("terminal_receipt") is None, "event session is terminal")

    def event_status(self, recording_id: str) -> dict[str, Any]:
        self._identity(recording_id)
        annotation_prompt_sha256 = canonical_digest(
            {
                "recording_id": self.recording_id,
                "receipt_outcome_shown": False,
                "fields": self.contract["visual_annotation"]["fields"],
            }
        )
        return {
            "recording_id": self.recording_id,
            "partition": self.partition,
            "event_episode_sha256": self.event["event_episode_sha256"],
            "phase_rows_sha256": self.phase_rows["phase_rows_sha256"],
            "visual_strip_available": self.strip_path is not None,
            "receipt_outcome_available_to_annotator": False,
            "visual_annotation_prompt_sha256": annotation_prompt_sha256,
            "measured_contact_available": False,
            "metric_object_trajectory_available": False,
            "claim_boundary": CLAIM_BOUNDARY,
            "budgets": copy.deepcopy(self.contract["inspect_tools"]),
        }

    def read_event_proposals(self, recording_id: str) -> dict[str, Any]:
        self._identity(recording_id)
        self.state["metric_reads"] += 1
        _require(
            self.state["metric_reads"] <= self.contract["inspect_tools"]["maximum_metric_reads"],
            "event metric read budget exhausted",
        )
        self._save()
        return {
            "recording_id": self.recording_id,
            "event_proposals": copy.deepcopy(self.event["event_proposals"]),
            "phase_intervals": copy.deepcopy(self.event["phase_intervals"]),
            "claim_boundary": CLAIM_BOUNDARY,
        }

    def read_event_metrics(self, recording_id: str) -> dict[str, Any]:
        self._identity(recording_id)
        self.state["metric_reads"] += 1
        _require(
            self.state["metric_reads"] <= self.contract["inspect_tools"]["maximum_metric_reads"],
            "event metric read budget exhausted",
        )
        self._save()
        return {
            "recording_id": self.recording_id,
            "mechanical_load_proxy": copy.deepcopy(self.event["mechanical_load_proxy"]),
            "phase_metrics": copy.deepcopy(self.event["phase_metrics"]),
            "apparent_tracking_lag": copy.deepcopy(self.event["apparent_tracking_lag"]),
            "unavailable": copy.deepcopy(self.event["unavailable"]),
            "claim_boundary": CLAIM_BOUNDARY,
        }

    def read_interaction_strip(self, recording_id: str) -> tuple[dict[str, Any], Path]:
        self._identity(recording_id)
        _require(self.strip_path is not None, "interaction strip was not materialized")
        self.state["strip_reads"] += 1
        _require(
            self.state["strip_reads"] <= self.contract["inspect_tools"]["maximum_strip_reads"],
            "interaction strip read budget exhausted",
        )
        self._save()
        metadata = copy.deepcopy(self.event["visual_evidence"])
        metadata.pop("path", None)
        metadata["recording_id"] = self.recording_id
        metadata["receipt_outcome_shown"] = False
        return metadata, self.strip_path

    def submit_visual_annotation(
        self, recording_id: str, annotation: Mapping[str, Any]
    ) -> dict[str, Any]:
        self._identity(recording_id)
        _require(self.state.get("annotation") is None, "visual annotation was already submitted")
        candidate = dict(annotation)
        candidate["schema_version"] = ANNOTATION_SCHEMA
        candidate["recording_id"] = self.recording_id
        candidate["event_episode_sha256"] = self.event["event_episode_sha256"]
        candidate["receipt_outcome_shown"] = False
        validated = _validate_annotation_payload(candidate, self.contract)
        self.state["annotation"] = validated
        self._save()
        return {
            "accepted": True,
            "annotation_sha256": validated["annotation_sha256"],
            "ground_truth_claimed": False,
            "promotion_authority": False,
        }

    def submit_event_audit(
        self,
        recording_id: str,
        event_episode_sha256: str,
        annotation_sha256: str,
        claim_boundary: str,
    ) -> dict[str, Any]:
        self._identity(recording_id)
        annotation = self.state.get("annotation")
        _require(isinstance(annotation, dict), "visual annotation is required before audit")
        _require(event_episode_sha256 == self.event["event_episode_sha256"], "event digest changed")
        _require(annotation_sha256 == annotation["annotation_sha256"], "annotation digest changed")
        _require(claim_boundary == CLAIM_BOUNDARY, "event claim boundary changed")
        unsigned = {
            "schema_version": AUDIT_SCHEMA,
            "recording_id": self.recording_id,
            "partition": self.partition,
            "event_episode_sha256": event_episode_sha256,
            "annotation_sha256": annotation_sha256,
            "audit_complete": True,
            "annotation_correctness_scored": False,
            "measured_contact_claimed": False,
            "metric_object_trajectory_claimed": False,
            "physical_actions": 0,
            "promotion_authority": False,
            "claim_boundary": CLAIM_BOUNDARY,
        }
        receipt = {**unsigned, "receipt_sha256": canonical_digest(unsigned)}
        self.state["terminal_receipt"] = receipt
        self._save()
        return receipt

    def terminal_receipt(self) -> dict[str, Any] | None:
        value = self.state.get("terminal_receipt")
        return copy.deepcopy(value) if isinstance(value, dict) else None


def build_interaction_event_sessions(
    build_root: Path,
    *,
    partition: str = "train",
    evaluator_owned: bool = False,
    render_visuals: bool = True,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    repo_root: Path = REPO_ROOT,
) -> tuple[dict[str, InteractionEventSession], dict[str, Any]]:
    artifact_root = build_root.resolve() / "artifacts"
    corpus = materialize_interaction_event_pipeline(
        artifact_root,
        partition=partition,
        evaluator_owned=evaluator_owned,
        render_visuals=render_visuals,
        contract_path=contract_path,
        repo_root=repo_root,
    )
    sessions = {
        str(item["recording_id"]): InteractionEventSession(
            item,
            artifact_root,
            build_root.resolve() / "state",
            contract_path=contract_path,
            repo_root=repo_root,
            reset=True,
        )
        for item in corpus["episodes"]
    }
    return sessions, corpus


__all__ = [
    "ANNOTATION_SCHEMA",
    "CLAIM_BOUNDARY",
    "DEFAULT_CONTRACT_PATH",
    "InteractionEventError",
    "InteractionEventSession",
    "SIM_TRACE_SCHEMA",
    "TOOL_NAMES",
    "build_interaction_event_sessions",
    "build_phase_balanced_manifest",
    "compare_event_conditioned_real_sim",
    "compile_annotation_consensus",
    "compile_episode_events",
    "current_real_sim_status",
    "extract_event_indices",
    "load_event_contract",
    "materialize_interaction_event_pipeline",
    "render_interaction_strip",
    "validate_visual_annotation",
]

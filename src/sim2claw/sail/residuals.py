"""Phase-aligned residual-field compilation for retained SAIL evidence."""

from __future__ import annotations

import copy
import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from ..learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .contracts import REPO_ROOT, SailContractError, seal_contract, verify_contract, verify_source_binding
from .importers import load_json_object
from .phases import (
    PhaseAlignmentError,
    detect_events,
    event_phase,
    finite_difference,
    phase_intervals,
    phase_labels,
)
from .receipts import verify_compile_receipt
from .residual_visuals import write_residual_visuals


CONFIG_SCHEMA = "sim2claw.sail_residual_campaign.v1"
RECEIPT_SCHEMA = "sim2claw.sail_residual_compile_receipt.v1"
JOINT_NAMES = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
)


class ResidualCompilationError(SailContractError):
    """Residual compilation would lose identity, timing, or availability."""


def load_residual_config(path: Path, *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    config = load_json_object(resolved, label="SAIL residual config")
    if config.get("schema_version") != CONFIG_SCHEMA:
        raise ResidualCompilationError("unexpected SAIL residual config schema")
    authority = config.get("authority")
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise ResidualCompilationError("SAIL residual config widened authority")
    expected_bindings = {
        "evidence_catalog",
        "evidence_compile_receipt",
        "event_contract",
        "residual_schema",
    }
    if set(config.get("source_bindings") or {}) != expected_bindings:
        raise ResidualCompilationError("SAIL residual source binding set changed")
    for binding in config["source_bindings"].values():
        verify_source_binding(binding, repo_root=repo_root)
    event_path = verify_source_binding(
        config["source_bindings"]["event_contract"], repo_root=repo_root
    )
    event_contract = load_json_object(event_path, label="fixed-data event contract")
    event_settings = event_contract.get("event_extraction") or {}
    phase_settings = config["phase_detection"]
    for name in (
        "gripper_joint_index",
        "first_open_search_fraction",
        "destination_open_search_start_fraction",
        "transition_fraction_of_open_to_valley_range",
        "phase_order",
        "event_order",
        "contact_claim_allowed",
    ):
        if phase_settings.get(name) != event_settings.get(name):
            raise ResidualCompilationError(f"residual/event phase setting changed: {name}")
    if config["alignment"]["retained_method"] != "exact_row_alignment_no_interpolation":
        raise ResidualCompilationError("retained residual alignment changed")
    if config["missing_channel_policy"]["imputation_allowed"] is not False:
        raise ResidualCompilationError("missing-channel imputation became enabled")
    if config["phase_detection"]["contact_claim_allowed"] is not False:
        raise ResidualCompilationError("observable phases gained contact authority")
    return config


def verify_residual_receipt(
    receipt: Mapping[str, Any], *, output_root: Path, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(receipt))
    if normalized.get("schema_version") != RECEIPT_SCHEMA:
        raise ResidualCompilationError("unexpected SAIL residual receipt schema")
    observed = normalized.pop("receipt_digest", None)
    if observed != canonical_digest(normalized):
        raise ResidualCompilationError("SAIL residual receipt digest mismatch")
    authority = normalized.get("authority")
    if not isinstance(authority, dict) or any(authority.values()):
        raise ResidualCompilationError("SAIL residual receipt widened authority")
    config_binding = normalized.get("config") or {}
    config_path = repo_root / str(config_binding.get("path", ""))
    if not config_path.is_file() or sha256_file(config_path) != config_binding.get("sha256"):
        raise ResidualCompilationError("SAIL residual receipt config changed")
    for relative_path, expected_sha256 in (normalized.get("compiler_sha256") or {}).items():
        compiler_path = repo_root / str(relative_path)
        if not compiler_path.is_file() or sha256_file(compiler_path) != expected_sha256:
            raise ResidualCompilationError(
                f"SAIL residual compiler changed: {relative_path}"
            )
    outputs = normalized.get("outputs") or {}
    for name, binding in outputs.items():
        path = output_root / str(binding.get("path", ""))
        if not path.is_file() or sha256_file(path) != binding.get("sha256"):
            raise ResidualCompilationError(f"SAIL residual output changed: {name}")
    return {**normalized, "receipt_digest": str(observed)}


def _load_evidence_pair(
    *,
    entry: Mapping[str, Any],
    entries: Mapping[str, Mapping[str, Any]],
    evidence_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    sim_path = evidence_root / str(entry["path"])
    if not sim_path.is_file() or sha256_file(sim_path) != entry["sha256"]:
        raise ResidualCompilationError(f"simulator evidence changed: {entry['evidence_id']}")
    simulator = verify_contract(load_json_object(sim_path, label="simulator evidence"))
    if simulator["split_role"] != "validation":
        raise ResidualCompilationError("non-development simulator evidence entered residual fit")
    parents = list(simulator["parent_evidence_ids"])
    if len(parents) != 1 or not parents[0].startswith("physical:"):
        raise ResidualCompilationError("simulator evidence lost its physical parent")
    try:
        physical_entry = entries[parents[0]]
    except KeyError as error:
        raise ResidualCompilationError("physical parent is absent from evidence catalog") from error
    physical_path = evidence_root / str(physical_entry["path"])
    if not physical_path.is_file() or sha256_file(physical_path) != physical_entry["sha256"]:
        raise ResidualCompilationError(f"physical evidence changed: {parents[0]}")
    physical = verify_contract(load_json_object(physical_path, label="physical evidence"))
    if physical["proof_class"] != "physical_teleoperation_source_unqualified":
        raise ResidualCompilationError("physical parent proof class changed")
    if physical["session_id"] != simulator["session_id"]:
        raise ResidualCompilationError("physical/simulator session identity changed")
    return simulator, physical


def _matrix(evidence: Mapping[str, Any], channel: str, *, columns: int) -> np.ndarray:
    try:
        row = evidence["observations"][channel]
        values = np.asarray(row["values"], dtype=np.float64)
        available = np.asarray(row["available"], dtype=np.bool_)
    except (KeyError, TypeError, ValueError) as error:
        raise ResidualCompilationError(f"invalid evidence channel: {channel}") from error
    if values.ndim != 2 or values.shape[1] != columns or available.shape != (values.shape[0],):
        raise ResidualCompilationError(f"evidence channel shape changed: {channel}")
    if not np.all(available) or not np.all(np.isfinite(values)):
        raise ResidualCompilationError(f"required evidence channel is unavailable: {channel}")
    return values


def _vector(evidence: Mapping[str, Any], channel: str) -> np.ndarray:
    try:
        row = evidence["observations"][channel]
        values = np.asarray(row["values"], dtype=np.float64)
        available = np.asarray(row["available"], dtype=np.bool_)
    except (KeyError, TypeError, ValueError) as error:
        raise ResidualCompilationError(f"invalid evidence channel: {channel}") from error
    if values.ndim != 1 or available.shape != values.shape:
        raise ResidualCompilationError(f"evidence channel shape changed: {channel}")
    if not np.all(available) or not np.all(np.isfinite(values)):
        raise ResidualCompilationError(f"required evidence channel is unavailable: {channel}")
    return values


def _assert_action_identity(simulator: Mapping[str, Any]) -> None:
    applied = _matrix(simulator, "applied_action", columns=6)
    action = simulator["action"]
    if list(applied.shape) != list(action["shape"]):
        raise ResidualCompilationError("simulator action shape changed")
    observed = hashlib.sha256(np.ascontiguousarray(applied).tobytes(order="C")).hexdigest()
    if observed != action["sha256"]:
        raise ResidualCompilationError("simulator action bytes changed")
    times = list(action["application_time_seconds"])
    if len(times) != applied.shape[0]:
        raise ResidualCompilationError("simulator action time count changed")


def _sample(
    *,
    episode_id: str,
    phase: str,
    time_seconds: float,
    channel: str,
    unit: str,
    frame: str | None,
    provenance: str,
    value: float | None,
    available: bool,
) -> dict[str, Any]:
    if available and value is None:
        raise ResidualCompilationError("available residual sample is null")
    if not available and value is not None:
        raise ResidualCompilationError("unavailable residual sample has a value")
    return {
        "episode_id": episode_id,
        "phase": phase,
        "time_seconds": float(time_seconds),
        "channel": channel,
        "unit": unit,
        "frame": frame,
        "provenance": provenance,
        "available": available,
        "value": None if value is None else float(value),
    }


def _append_vector_curve(
    samples: list[dict[str, Any]],
    *,
    episode_id: str,
    phases: Sequence[str],
    times: np.ndarray,
    values: np.ndarray,
    prefix: str,
    unit: str,
    gripper_unit: str | None = None,
    frame: str,
    provenance: str,
) -> None:
    if values.shape != (len(times), len(JOINT_NAMES)):
        raise ResidualCompilationError(f"joint residual shape changed: {prefix}")
    for index, (time, phase) in enumerate(zip(times, phases, strict=True)):
        for joint_index, joint_name in enumerate(JOINT_NAMES):
            samples.append(
                _sample(
                    episode_id=episode_id,
                    phase=phase,
                    time_seconds=float(time),
                    channel=f"{prefix}:{joint_name}",
                    unit=(gripper_unit if joint_index == 5 and gripper_unit else unit),
                    frame=frame,
                    provenance=provenance,
                    value=float(values[index, joint_index]),
                    available=True,
                )
            )


def _episode_samples(
    simulator: Mapping[str, Any],
    physical: Mapping[str, Any],
    config: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _assert_action_identity(simulator)
    episode_id = str(simulator["session_id"])
    elapsed = _vector(simulator, "elapsed_time")
    mapped_joint = _matrix(simulator, "mapped_measured_joint_state", columns=6)
    baseline_joint = _matrix(simulator, "baseline_simulated_joint_state", columns=6)
    selected_joint = _matrix(simulator, "selected_simulated_joint_state", columns=6)
    mapped_ee = _matrix(simulator, "mapped_measured_end_effector", columns=3)
    baseline_ee = _matrix(simulator, "baseline_simulated_end_effector", columns=3)
    selected_ee = _matrix(simulator, "selected_simulated_end_effector", columns=3)
    physical_time = _vector(physical, "sample_timestamp")
    commanded = _matrix(physical, "commanded_joint_position", columns=6)
    measured = _matrix(physical, "measured_joint_position", columns=6)
    measured_velocity = _matrix(physical, "measured_joint_velocity", columns=6)
    count = len(elapsed)
    if any(array.shape[0] != count for array in (
        mapped_joint,
        baseline_joint,
        selected_joint,
        mapped_ee,
        baseline_ee,
        selected_ee,
        commanded,
        measured,
        measured_velocity,
    )) or len(physical_time) != count:
        raise ResidualCompilationError(f"exact row alignment changed: {episode_id}")
    settings = config["phase_detection"]
    reference_events = detect_events(mapped_joint[:, 5], settings)
    baseline_events = detect_events(baseline_joint[:, 5], settings)
    selected_events = detect_events(selected_joint[:, 5], settings)
    intervals = phase_intervals(count, reference_events, settings["phase_order"])
    phases = phase_labels(count, intervals)
    physical_command_velocity = finite_difference(commanded, physical_time)
    mapped_velocity = finite_difference(mapped_joint, elapsed)
    baseline_velocity = finite_difference(baseline_joint, elapsed)
    selected_velocity = finite_difference(selected_joint, elapsed)

    samples: list[dict[str, Any]] = []
    _append_vector_curve(
        samples,
        episode_id=episode_id,
        phases=phases,
        times=elapsed,
        values=measured - commanded,
        prefix="physical_measured_minus_commanded_joint",
        unit="degree",
        gripper_unit="recorded_gripper_percent",
        frame="physical_so101_joint_order",
        provenance=f"{physical['evidence_id']}#measured_joint_position-commanded_joint_position;row_alignment=exact",
    )
    _append_vector_curve(
        samples,
        episode_id=episode_id,
        phases=phases,
        times=elapsed,
        values=measured_velocity - physical_command_velocity,
        prefix="physical_measured_minus_command_velocity",
        unit="degree_per_second",
        gripper_unit="recorded_gripper_percent_per_second",
        frame="physical_so101_joint_order",
        provenance=f"{physical['evidence_id']}#measured_joint_velocity-finite_difference(commanded_joint_position,physical_sample_timestamp);interpolation=none",
    )
    for prefix, values in (
        ("baseline_sim_minus_mapped_real_joint", baseline_joint - mapped_joint),
        ("selected_sim_minus_mapped_real_joint", selected_joint - mapped_joint),
        ("baseline_sim_minus_mapped_real_velocity", baseline_velocity - mapped_velocity),
        ("selected_sim_minus_mapped_real_velocity", selected_velocity - mapped_velocity),
    ):
        _append_vector_curve(
            samples,
            episode_id=episode_id,
            phases=phases,
            times=elapsed,
            values=values,
            prefix=prefix,
            unit="radian_per_second" if "velocity" in prefix else "radian",
            frame="simulator_so101_joint_order",
            provenance=f"{simulator['evidence_id']}#{prefix};time_base=elapsed_seconds;interpolation=none",
        )
    baseline_ee_residual = baseline_ee - mapped_ee
    selected_ee_residual = selected_ee - mapped_ee
    for index, (time, phase) in enumerate(zip(elapsed, phases, strict=True)):
        for axis, axis_name in enumerate(("x", "y", "z")):
            for prefix, values in (
                ("baseline_end_effector", baseline_ee_residual),
                ("selected_end_effector", selected_ee_residual),
            ):
                samples.append(
                    _sample(
                        episode_id=episode_id,
                        phase=phase,
                        time_seconds=float(time),
                        channel=f"{prefix}:{axis_name}",
                        unit="meter",
                        frame="simulator_world",
                        provenance=f"{simulator['evidence_id']}#{prefix}_simulated_minus_mapped_measured;row_alignment=exact",
                        value=float(values[index, axis]),
                        available=True,
                    )
                )
        for prefix, values in (
            ("baseline_end_effector_norm", baseline_ee_residual),
            ("selected_end_effector_norm", selected_ee_residual),
        ):
            samples.append(
                _sample(
                    episode_id=episode_id,
                    phase=phase,
                    time_seconds=float(time),
                    channel=prefix,
                    unit="meter",
                    frame="simulator_world",
                    provenance=f"{simulator['evidence_id']}#{prefix};row_alignment=exact",
                    value=float(np.linalg.norm(values[index])),
                    available=True,
                )
            )
        samples.append(
            _sample(
                episode_id=episode_id,
                phase=phase,
                time_seconds=float(time),
                channel="selected_aperture_residual",
                unit="radian",
                frame="simulator_gripper_joint",
                provenance=f"{simulator['evidence_id']}#selected_gripper_minus_mapped_measured_gripper;row_alignment=exact",
                value=float(selected_joint[index, 5] - mapped_joint[index, 5]),
                available=True,
            )
        )
    for event_name in settings["event_order"]:
        reference_index = int(reference_events[event_name])
        for prefix, events in (
            ("baseline_event_timing", baseline_events),
            ("selected_event_timing", selected_events),
        ):
            samples.append(
                _sample(
                    episode_id=episode_id,
                    phase=event_phase(event_name),
                    time_seconds=float(elapsed[reference_index]),
                    channel=f"{prefix}:{event_name}",
                    unit="second",
                    frame="simulator_episode_time",
                    provenance=f"{simulator['evidence_id']}#{prefix};observable_gripper_thresholds;minimum_distance_not_used",
                    value=float(elapsed[int(events[event_name])] - elapsed[reference_index]),
                    available=True,
                )
            )
    missing_channels = config["missing_channel_policy"]["channels"]
    for interval in intervals:
        index = int(interval["start_sample_index_inclusive"])
        phase = str(interval["phase"])
        for channel in missing_channels:
            samples.append(
                _sample(
                    episode_id=episode_id,
                    phase=phase,
                    time_seconds=float(elapsed[index]),
                    channel=str(channel),
                    unit="unavailable",
                    frame=None,
                    provenance="P1-02 unavailable physical channel; weak CV/video annotations are not metric ground truth",
                    value=None,
                    available=False,
                )
            )
    drilldown = {
        "episode_id": episode_id,
        "evidence_ids": [physical["evidence_id"], simulator["evidence_id"]],
        "sample_count": count,
        "time_bases": {
            "residual_axis": "simulator_trace_elapsed_seconds",
            "physical_velocity_derivative": "recording_monotonic_seconds",
            "interpolation": "none_exact_row_alignment",
        },
        "phase_intervals": intervals,
        "events": {
            "mapped_measured": reference_events,
            "baseline_simulator": baseline_events,
            "selected_simulator": selected_events,
        },
        "action": copy.deepcopy(simulator["action"]),
        "abstentions": list(config["missing_channel_policy"]["channels"]),
    }
    return samples, drilldown


def summarize_samples(samples: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in samples:
        episode = str(row["episode_id"])
        channel = str(row["channel"])
        groups[(episode, str(row["phase"]), channel)].append(row)
        groups[(episode, "all", channel)].append(row)
    result: list[dict[str, Any]] = []
    for (episode, phase, channel), rows in sorted(groups.items()):
        units = {str(row["unit"]) for row in rows}
        frames = {row["frame"] for row in rows}
        if len(units) != 1 or len(frames) != 1:
            raise ResidualCompilationError(f"unit or frame changed inside residual channel: {channel}")
        values = np.asarray(
            [float(row["value"]) for row in rows if row["available"]], dtype=np.float64
        )
        summary: dict[str, Any] = {
            "episode_id": episode,
            "phase": phase,
            "channel": channel,
            "unit": next(iter(units)),
            "frame": next(iter(frames)),
            "sample_count": len(rows),
            "available_count": int(values.size),
            "missing_count": len(rows) - int(values.size),
            "bias": None,
            "mae": None,
            "rmse": None,
            "p95_absolute": None,
            "maximum_absolute": None,
        }
        if values.size:
            absolute = np.abs(values)
            summary.update(
                {
                    "bias": float(np.mean(values)),
                    "mae": float(np.mean(absolute)),
                    "rmse": float(np.sqrt(np.mean(np.square(values)))),
                    "p95_absolute": float(np.quantile(absolute, 0.95)),
                    "maximum_absolute": float(np.max(absolute)),
                }
            )
        result.append(summary)
    return result


def whole_episode_bootstrap(
    summaries: Sequence[Mapping[str, Any]], settings: Mapping[str, Any]
) -> dict[str, Any]:
    overall = [row for row in summaries if row["phase"] == "all" and row["rmse"] is not None]
    by_channel: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in overall:
        by_channel[str(row["channel"])].append(row)
    seed = int(settings["seed"])
    replicates = int(settings["replicates"])
    confidence = float(settings["confidence_level"])
    if replicates <= 0 or not 0.0 < confidence < 1.0:
        raise ResidualCompilationError("bootstrap settings are invalid")
    rng = np.random.default_rng(seed)
    alpha = (1.0 - confidence) / 2.0
    estimates: list[dict[str, Any]] = []
    for channel in sorted(by_channel):
        rows = sorted(by_channel[channel], key=lambda row: str(row["episode_id"]))
        values = np.asarray([float(row["rmse"]) for row in rows], dtype=np.float64)
        indices = rng.integers(0, len(values), size=(replicates, len(values)))
        boot = np.mean(values[indices], axis=1)
        estimates.append(
            {
                "channel": channel,
                "unit": str(rows[0]["unit"]),
                "episode_count": len(values),
                "point_estimate_mean_episode_rmse": float(np.mean(values)),
                "interval_lower": float(np.quantile(boot, alpha)),
                "interval_upper": float(np.quantile(boot, 1.0 - alpha)),
            }
        )
    return {
        "seed": seed,
        "replicates": replicates,
        "confidence_level": confidence,
        "resampling_unit": "whole_episode",
        "statistic": "mean_episode_rmse",
        "estimates": estimates,
    }


def build_residual_field(
    evidence_pairs: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    config: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    samples: list[dict[str, Any]] = []
    drilldowns: list[dict[str, Any]] = []
    evidence_ids: set[str] = set()
    for simulator, physical in sorted(evidence_pairs, key=lambda pair: str(pair[0]["session_id"])):
        episode_samples, drilldown = _episode_samples(simulator, physical, config)
        samples.extend(episode_samples)
        drilldowns.append(drilldown)
        evidence_ids.update((str(simulator["evidence_id"]), str(physical["evidence_id"])))
    samples.sort(
        key=lambda row: (
            str(row["episode_id"]),
            str(row["phase"]),
            float(row["time_seconds"]),
            str(row["channel"]),
        )
    )
    summaries = summarize_samples(samples)
    bootstrap = whole_episode_bootstrap(summaries, config["bootstrap"])
    field = seal_contract(
        {
            "schema_version": "sim2claw.residual_field.v1",
            "residual_id": str(config["campaign_id"]),
            "evidence_ids": sorted(evidence_ids),
            "axes": ["episode", "phase", "time", "channel", "frame", "provenance"],
            "samples": samples,
            "summaries": summaries,
            "bootstrap": bootstrap,
        }
    )
    return field, drilldowns


def compile_residuals(
    config_path: Path,
    output_root: Path,
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    resolved_config = config_path if config_path.is_absolute() else repo_root / config_path
    config = load_residual_config(resolved_config, repo_root=repo_root)
    evidence_root = Path(str(config["evidence_root"]))
    if not evidence_root.is_absolute():
        evidence_root = repo_root / evidence_root
    catalog_path = verify_source_binding(
        config["source_bindings"]["evidence_catalog"], repo_root=repo_root
    )
    receipt_path = verify_source_binding(
        config["source_bindings"]["evidence_compile_receipt"], repo_root=repo_root
    )
    evidence_receipt = load_json_object(receipt_path, label="evidence compile receipt")
    verify_compile_receipt(evidence_receipt, output_root=evidence_root)
    catalog = load_json_object(catalog_path, label="evidence catalog")
    entries = {str(row["evidence_id"]): row for row in catalog["entries"]}
    development = sorted(
        (
            row
            for row in catalog["entries"]
            if row["proof_class"] == "retained_action_frozen_simulator_replay"
            and row["split_role"] == "validation"
        ),
        key=lambda row: str(row["evidence_id"]),
    )
    expected = config["expected_inventory"]
    if int(expected["evidence_items_per_episode"]) != 2:
        raise ResidualCompilationError("evidence pairing contract changed")
    if int(expected["phase_count"]) != len(config["phase_detection"]["phase_order"]):
        raise ResidualCompilationError("phase inventory contract changed")
    if int(expected["event_count"]) != len(config["phase_detection"]["event_order"]):
        raise ResidualCompilationError("event inventory contract changed")
    if int(expected["joint_count"]) != len(JOINT_NAMES):
        raise ResidualCompilationError("joint inventory contract changed")
    if len(development) != int(expected["development_episode_count"]):
        raise ResidualCompilationError("development episode count changed")
    pairs = [
        _load_evidence_pair(entry=row, entries=entries, evidence_root=evidence_root)
        for row in development
    ]
    if sum(int(simulator["action"]["shape"][0]) for simulator, _ in pairs) != int(
        expected["aligned_sample_count"]
    ):
        raise ResidualCompilationError("aligned sample count changed")
    field, drilldowns = build_residual_field(pairs, config)
    verify_contract(field)
    output_root.mkdir(parents=True, exist_ok=True)
    field_path = output_root / "residual_field.json"
    atomic_write_json(field_path, field)
    visuals = write_residual_visuals(
        output_root=output_root,
        summaries=field["summaries"],
        episodes=drilldowns,
        config=config,
    )
    code_paths = (
        "src/sim2claw/sail/phases.py",
        "src/sim2claw/sail/residuals.py",
        "src/sim2claw/sail/residual_visuals.py",
    )
    unsigned_receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "campaign_id": str(config["campaign_id"]),
        "generated_at": str(config["determinism"]["generated_at"]),
        "config": {
            "path": resolved_config.resolve().relative_to(repo_root.resolve()).as_posix(),
            "sha256": sha256_file(resolved_config),
        },
        "source_evidence": {
            "catalog_sha256": sha256_file(catalog_path),
            "compile_receipt_sha256": sha256_file(receipt_path),
            "evidence_ids": list(field["evidence_ids"]),
        },
        "compiler_sha256": {path: sha256_file(repo_root / path) for path in code_paths},
        "outputs": {
            "residual_field": {"path": "residual_field.json", "sha256": sha256_file(field_path)},
            **visuals,
        },
        "counts": {
            "episode_count": len(drilldowns),
            "aligned_source_row_count": sum(int(row["sample_count"]) for row in drilldowns),
            "residual_sample_count": len(field["samples"]),
            "summary_count": len(field["summaries"]),
            "bootstrap_channel_count": len(field["bootstrap"]["estimates"]),
            "explicit_abstention_channel_count": len(config["missing_channel_policy"]["channels"]),
        },
        "regeneration_command": "uv run sim2claw sail-compile-residuals --config configs/sail/residual_field_retired_bg_v1.json --output outputs/sail/retired-bg-v1/residuals",
        "authority": copy.deepcopy(config["authority"]),
        "claim_boundary": "Phase-aligned residuals expose retained trace mismatch and timing structure. They do not identify a physical mechanism, impute contact/object outcomes, promote a simulator, admit training, select a policy, or establish transfer.",
    }
    receipt = {**unsigned_receipt, "receipt_digest": canonical_digest(unsigned_receipt)}
    receipt_path_out = output_root / "receipt.json"
    atomic_write_json(receipt_path_out, receipt)
    verify_residual_receipt(receipt, output_root=output_root)
    return {
        "schema_version": "sim2claw.sail_residual_compile_result.v1",
        "campaign_id": str(config["campaign_id"]),
        "status": "compiled",
        "counts": receipt["counts"],
        "residual_field_sha256": sha256_file(field_path),
        "receipt_sha256": sha256_file(receipt_path_out),
        "receipt_digest": receipt["receipt_digest"],
        "visuals": visuals,
        "output_root": str(output_root),
        "training_admitted": False,
        "physical_authority": False,
    }


__all__ = [
    "PhaseAlignmentError",
    "ResidualCompilationError",
    "build_residual_field",
    "compile_residuals",
    "load_residual_config",
    "summarize_samples",
    "whole_episode_bootstrap",
    "verify_residual_receipt",
]

"""Receipt-bound SAIL observability assets for the existing read-only Studio."""

from __future__ import annotations

import bisect
import copy
import hashlib
import html
import json
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from ..learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from ..scene import board_square_center
from .contracts import REPO_ROOT, SailContractError, verify_contract, verify_source_binding
from .importers import load_json_object


CONFIG_SCHEMA = "sim2claw.sail_studio_observatory_config.v1"
MANIFEST_SCHEMA = "sim2claw.sail_studio_observatory.v1"
RECEIPT_SCHEMA = "sim2claw.sail_studio_observatory_receipt.v1"
DEFAULT_CONFIG = Path("configs/sail/studio_observatory_v1.json")
DEFAULT_OUTPUT_ROOT = Path("outputs/sail/studio-observatory-v1")
JOINT_NAMES = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
)
SOURCE_KEYS = frozenset(
    {
        "evidence_catalog",
        "evidence_receipt",
        "evidence_omissions",
        "residual_receipt",
        "residual_heatmap",
        "residual_heatmap_svg",
        "residual_drilldowns",
        "belief_receipt",
        "belief_graph",
        "belief_revision_timeline",
        "belief_before_svg",
        "belief_after_svg",
        "structural_surprise_receipt",
        "structural_surprise",
        "loop_closure_receipt",
        "loop_closure",
        "mechanism_receipt",
        "retained_particles",
        "invariance_receipt",
        "retained_invariance",
        "acquisition_receipt",
        "acquisition_ranking",
        "prospective_receipt",
        "prospective_experiment",
        "twin_capability_receipt",
        "twin_capability_report",
        "ranked_gallery",
    }
)


class StudioObservatoryError(SailContractError):
    """Studio evidence cannot be presented without widening or losing lineage."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StudioObservatoryError(message)


def _relative(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def load_studio_config(
    path: Path = DEFAULT_CONFIG, *, repo_root: Path = REPO_ROOT
) -> tuple[dict[str, Any], dict[str, Path]]:
    resolved = path if path.is_absolute() else repo_root / path
    config = load_json_object(resolved, label="SAIL Studio observatory config")
    _require(config.get("schema_version") == CONFIG_SCHEMA, "unexpected SAIL Studio config schema")
    authority = config.get("authority")
    _require(
        isinstance(authority, dict) and authority and not any(authority.values()),
        "SAIL Studio config widened authority",
    )
    bindings = config.get("source_bindings")
    _require(isinstance(bindings, dict) and set(bindings) == SOURCE_KEYS, "SAIL Studio source binding set changed")
    paths = {
        name: verify_source_binding(binding, repo_root=repo_root)
        for name, binding in bindings.items()
    }
    ranking = config.get("ranking") or {}
    _require(ranking.get("selected_episode_count") == 7, "SAIL Studio selected ranking count changed")
    _require(ranking.get("development_episode_count") == 11, "SAIL Studio development inventory changed")
    _require(ranking.get("retain_lower_signal_episodes") is True, "SAIL Studio hides interpretable partial episodes")
    _require(ranking.get("omit_only_explicit_no_signal") is True, "SAIL Studio omission rule changed")
    return config, paths


def _read_bound_json(paths: Mapping[str, Path], name: str, schema: str | None = None) -> dict[str, Any]:
    value = load_json_object(paths[name], label=f"SAIL Studio {name}")
    if schema is not None:
        _require(value.get("schema_version") == schema, f"SAIL Studio {name} schema changed")
    return value


def _observation(evidence: Mapping[str, Any], name: str, *, width: int | None = None) -> list[Any]:
    row = (evidence.get("observations") or {}).get(name)
    _require(isinstance(row, dict), f"SAIL Studio observation missing: {name}")
    values = row.get("values")
    available = row.get("available")
    _require(isinstance(values, list) and isinstance(available, list), f"SAIL Studio observation malformed: {name}")
    _require(len(values) == len(available) and all(value is True for value in available), f"SAIL Studio required observation unavailable: {name}")
    if width is not None:
        _require(all(isinstance(value, list) and len(value) == width for value in values), f"SAIL Studio observation width changed: {name}")
    return copy.deepcopy(values)


def _phase_labels(count: int, intervals: Sequence[Mapping[str, Any]]) -> list[str]:
    labels = ["missing_phase"] * count
    for interval in intervals:
        start = int(interval["start_sample_index_inclusive"])
        end = int(interval["end_sample_index_exclusive"])
        _require(0 <= start < end <= count, "SAIL Studio phase interval is invalid")
        labels[start:end] = [str(interval["phase"])] * (end - start)
    _require("missing_phase" not in labels, "SAIL Studio phase coverage is incomplete")
    return labels


def _split_move(label: str) -> tuple[str, str]:
    parts = label.lower().split("-to-")
    _require(len(parts) == 2 and all(len(value) == 2 for value in parts), "SAIL Studio move label is invalid")
    return parts[0], parts[1]


def _trace_channels(
    trace: Mapping[str, Any],
    *,
    times: Sequence[float],
    source_square: str,
    destination_square: str,
) -> dict[str, Any]:
    body_names = trace.get("body_names")
    frames = trace.get("frames")
    _require(isinstance(body_names, list) and isinstance(frames, list) and frames, "SAIL Studio trace is empty")
    pawn_name = f"brown_pawn_{source_square}"
    if pawn_name not in body_names:
        file_candidates = [
            name
            for name in body_names
            if name.startswith(f"brown_pawn_{source_square[0]}")
        ]
        _require(
            len(file_candidates) == 1,
            "SAIL Studio trace lacks the selected pawn",
        )
        pawn_name = file_candidates[0]
    pawn_id = body_names.index(pawn_name)
    frame_times = [float(row["t"]) for row in frames]
    _require(frame_times == sorted(frame_times), "SAIL Studio trace time is not monotonic")
    target_xyz = [float(value) for value in board_square_center(destination_square)]
    pawn_xyz: list[list[float]] = []
    contact_counts: list[int] = []
    phases: list[str] = []
    rises: list[float] = []
    target_distances: list[float] = []
    first_z: float | None = None
    for time in times:
        right = bisect.bisect_left(frame_times, float(time))
        if right <= 0:
            frame = frames[0]
        elif right >= len(frames):
            frame = frames[-1]
        else:
            before = frames[right - 1]
            after = frames[right]
            frame = before if abs(float(before["t"]) - time) <= abs(float(after["t"]) - time) else after
        positions = frame.get("p")
        contacts = frame.get("c") or []
        _require(isinstance(positions, list) and len(positions) == len(body_names) * 3, "SAIL Studio trace position shape changed")
        xyz = [float(value) for value in positions[pawn_id * 3 : pawn_id * 3 + 3]]
        if first_z is None:
            first_z = xyz[2]
        pawn_xyz.append(xyz)
        phases.append(str(frame.get("phase") or "simulation_replay"))
        contact_counts.append(
            sum(
                1
                for contact in contacts
                if isinstance(contact, list) and len(contact) >= 2 and pawn_id in (int(contact[0]), int(contact[1]))
            )
        )
        rises.append(float(xyz[2] - first_z))
        target_distances.append(float(np.linalg.norm(np.asarray(xyz) - np.asarray(target_xyz))))
    return {
        "simulated_pawn_xyz_m": pawn_xyz,
        "simulated_target_xyz_m": target_xyz,
        "simulated_pawn_contact_count": contact_counts,
        "simulated_pawn_rise_m": rises,
        "simulated_pawn_to_target_m": target_distances,
        "simulation_trace_phase": phases,
        "trace_frame_count": len(frames),
        "trace_fps": float(trace.get("fps") or 0),
    }


def _availability(*, has_trace: bool, sample_count: int) -> list[dict[str, Any]]:
    return [
        {"id": "action", "status": "available", "proof_class": "retained_action_identity", "detail": f"Byte-identical {sample_count}x6 action tensor."},
        {"id": "measured_joint", "status": "available", "proof_class": "physical_read_only", "detail": "Retained physical joint telemetry; no live robot connection."},
        {"id": "simulated_joint", "status": "available", "proof_class": "retained_replay", "detail": "Selected simulator joint state."},
        {"id": "end_effector", "status": "available", "proof_class": "retrospective_calibrated_mapping", "detail": "Mapped measured and simulator end-effector traces."},
        {"id": "pawn", "status": "simulation_only" if has_trace else "missing", "proof_class": "retained_replay" if has_trace else "declared_absence", "detail": "Physical metric object trajectory is unavailable."},
        {"id": "target", "status": "simulation_only", "proof_class": "simulator_goal", "detail": "Evaluator-declared destination square; no physical target measurement."},
        {"id": "aperture", "status": "available", "proof_class": "mixed_read_only", "detail": "Physical recorded percent and simulator gripper radians remain separate."},
        {"id": "timing", "status": "partial", "proof_class": "retrospective_timing", "detail": "Retained timestamps and observable gripper events; actuation and camera latency are missing."},
        {"id": "contact", "status": "simulation_only" if has_trace else "missing", "proof_class": "retained_replay" if has_trace else "declared_absence", "detail": "Physical contact state and force were not instrumented."},
        {"id": "consequence", "status": "simulation_only" if has_trace else "missing", "proof_class": "retained_replay" if has_trace else "declared_absence", "detail": "Physical consequence is unavailable; simulator outcome is partial and non-promoting."},
    ]


def _base_episode(
    *,
    row: Mapping[str, Any],
    rank: int,
    ranking_status: str,
    evidence_entries: Mapping[str, Mapping[str, Any]],
    evidence_root: Path,
    drilldowns: Mapping[str, Mapping[str, Any]],
    heatmap_rows: Mapping[str, Mapping[str, Any]],
    repo_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[float]]:
    episode_id = str(row["recording_id"])
    physical_entry = evidence_entries.get(f"physical:{episode_id}")
    simulator_entry = evidence_entries.get(f"sim-replay:{episode_id}")
    _require(isinstance(physical_entry, dict) and isinstance(simulator_entry, dict), f"SAIL Studio evidence pair missing: {episode_id}")
    payloads: list[dict[str, Any]] = []
    bindings: list[dict[str, Any]] = []
    for entry in (physical_entry, simulator_entry):
        path = evidence_root / str(entry["path"])
        _require(path.is_file() and sha256_file(path) == entry["sha256"], f"SAIL Studio evidence changed: {entry['evidence_id']}")
        payloads.append(verify_contract(load_json_object(path, label=str(entry["evidence_id"]))))
        bindings.append({"evidence_id": entry["evidence_id"], "path": _relative(path, repo_root), "sha256": entry["sha256"], "proof_class": entry["proof_class"]})
    physical, simulator = payloads
    drilldown = drilldowns.get(episode_id)
    heatmap = heatmap_rows.get(episode_id)
    _require(isinstance(drilldown, dict) and isinstance(heatmap, dict), f"SAIL Studio residual view missing: {episode_id}")
    times = [float(value) for value in _observation(simulator, "elapsed_time")]
    sample_count = len(times)
    _require(sample_count == int(drilldown["sample_count"]), "SAIL Studio sample count changed")
    _require(str(simulator["action"]["sha256"]) == str(row.get("action_array_sha256") or simulator["action"]["sha256"]), "SAIL Studio action identity differs from ranked replay")
    source_square, destination_square = _split_move(str(row["folder_label"]))
    channels = {
        "time_seconds": times,
        "phase": _phase_labels(sample_count, drilldown["phase_intervals"]),
        "action": _observation(simulator, "applied_action", width=6),
        "physical_measured_joint": _observation(physical, "measured_joint_position", width=6),
        "mapped_measured_joint": _observation(simulator, "mapped_measured_joint_state", width=6),
        "selected_simulated_joint": _observation(simulator, "selected_simulated_joint_state", width=6),
        "mapped_measured_end_effector_m": _observation(simulator, "mapped_measured_end_effector", width=3),
        "selected_simulated_end_effector_m": _observation(simulator, "selected_simulated_end_effector", width=3),
        "physical_aperture_recorded_percent": [float(row[-1]) for row in _observation(physical, "measured_joint_position", width=6)],
        "simulated_aperture_radian": [float(row[-1]) for row in _observation(simulator, "selected_simulated_joint_state", width=6)],
        "events": copy.deepcopy(drilldown["events"]),
        "target_square": destination_square.upper(),
    }
    episode = {
        "id": episode_id,
        "rank": rank,
        "ranking_status": ranking_status,
        "move": f"{source_square.upper()} → {destination_square.upper()}",
        "source_square": source_square,
        "target_square": destination_square,
        "relative_success_label": str(row.get("relative_success_label") or "Retained partial evidence"),
        "relative_success_summary": str(row.get("relative_success_summary") or row.get("relative_success_label") or "Retained partial evidence"),
        "task_consequence_success": bool(row.get("task_consequence_success", False)),
        "proof_class": "retained_action_frozen_simulation_replay",
        "proof_label": "Retained action-frozen replay · partial simulator evidence",
        "action_array_sha256": str(simulator["action"]["sha256"]),
        "sample_count": sample_count,
        "joint_names": list(JOINT_NAMES),
        "phase_intervals": copy.deepcopy(drilldown["phase_intervals"]),
        "residual_cells": copy.deepcopy(heatmap["cells"]),
        "evidence_bindings": bindings,
        "channels": channels,
    }
    return episode, physical, simulator, times


def _compile_episodes(
    *,
    gallery: Mapping[str, Any],
    catalog: Mapping[str, Any],
    heatmap: Mapping[str, Any],
    drilldown: Mapping[str, Any],
    evidence_root: Path,
    repo_root: Path,
) -> list[dict[str, Any]]:
    entries = {str(row["evidence_id"]): row for row in catalog["entries"]}
    drilldowns = {str(row["episode_id"]): row for row in drilldown["episodes"]}
    heatmap_rows = {str(row["episode_id"]): row for row in heatmap["rows"]}
    episodes: list[dict[str, Any]] = []
    ranked_rows = sorted(gallery["episodes"], key=lambda row: int(row["rank"]))
    for row in ranked_rows:
        episode, _, _, times = _base_episode(
            row=row,
            rank=int(row["rank"]),
            ranking_status="ranked_strongest_partial",
            evidence_entries=entries,
            evidence_root=evidence_root,
            drilldowns=drilldowns,
            heatmap_rows=heatmap_rows,
            repo_root=repo_root,
        )
        trace_binding = row.get("state_trace") or {}
        trace_path = repo_root / str(trace_binding.get("state_trace_path") or "")
        _require(trace_path.is_file() and sha256_file(trace_path) == trace_binding.get("state_trace_sha256"), f"SAIL Studio ranked trace changed: {episode['id']}")
        trace = load_json_object(trace_path, label=f"ranked Studio trace {episode['id']}")
        trace_channels = _trace_channels(
            trace,
            times=times,
            source_square=episode["source_square"],
            destination_square=episode["target_square"],
        )
        episode["channels"].update(trace_channels)
        episode["availability"] = _availability(
            has_trace=True, sample_count=episode["sample_count"]
        )
        episode["inspection"] = {
            "trace_url": f"/{_relative(trace_path, repo_root / 'src/sim2claw/studio_web')}",
            "trace_sha256": trace_binding["state_trace_sha256"],
            "inspection_only": True,
        }
        episode["metrics"] = copy.deepcopy(row.get("metrics") or {})
        episodes.append(episode)
    for offset, row in enumerate(gallery.get("excluded_episodes") or [], start=len(episodes) + 1):
        normalized = {
            **row,
            "action_array_sha256": None,
            "relative_success_summary": row.get("relative_success_label"),
            "task_consequence_success": False,
        }
        episode, _, simulator, _ = _base_episode(
            row=normalized,
            rank=offset,
            ranking_status="retained_lower_signal_partial",
            evidence_entries=entries,
            evidence_root=evidence_root,
            drilldowns=drilldowns,
            heatmap_rows=heatmap_rows,
            repo_root=repo_root,
        )
        episode["availability"] = _availability(
            has_trace=False, sample_count=episode["sample_count"]
        )
        episode["metrics"] = {}
        _require(episode["action_array_sha256"] == simulator["action"]["sha256"], "SAIL Studio lower-signal action identity changed")
        episodes.append(episode)
    _require(len(episodes) == 11, "SAIL Studio did not retain all interpretable development episodes")
    return episodes


def _figure_svg(title: str, subtitle: str, rows: Sequence[tuple[str, float, str]]) -> str:
    width = 1120
    row_height = 58
    height = 126 + row_height * len(rows)
    safe_values = [abs(float(value)) for _, value, _ in rows]
    maximum = max(safe_values, default=1.0) or 1.0
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f8f9f6"/>',
        '<style>text{font-family:ui-monospace,SFMono-Regular,monospace;fill:#151816}.title{font-family:Arial Narrow,sans-serif;font-size:28px;font-weight:700}.sub{fill:#6b716d;font-size:13px}.label{font-size:14px}.value{font-size:12px}</style>',
        f'<text class="title" x="36" y="42">{html.escape(title)}</text>',
        f'<text class="sub" x="36" y="68">{html.escape(subtitle)}</text>',
    ]
    for index, (label, value, note) in enumerate(rows):
        y = 98 + index * row_height
        bar = max(2.0, abs(float(value)) / maximum * 540.0)
        lines.extend(
            [
                f'<text class="label" x="36" y="{y + 17}">{html.escape(label)}</text>',
                f'<rect x="340" y="{y}" width="{bar:.2f}" height="22" rx="3" fill="#145c70"/>',
                f'<text class="value" x="{350 + bar:.2f}" y="{y + 16}">{float(value):.4g} · {html.escape(note)}</text>',
            ]
        )
    lines.append('</svg>')
    return "\n".join(lines) + "\n"


def _copy_figure(source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, output)


def _write_figures(
    *,
    output_root: Path,
    source_paths: Mapping[str, Path],
    acquisition: Mapping[str, Any],
    prospective: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    figure_root = output_root / "figures"
    copied = {
        "residual_heatmap": (source_paths["residual_heatmap_svg"], figure_root / "residual-heatmap.svg"),
        "belief_before": (source_paths["belief_before_svg"], figure_root / "belief-before.svg"),
        "belief_after": (source_paths["belief_after_svg"], figure_root / "belief-after.svg"),
    }
    for source, target in copied.values():
        _copy_figure(source, target)
    signature_rows = []
    observed = prospective.get("predicted_versus_observed_signatures") or {}
    for row in sorted(acquisition.get("rows") or [], key=lambda value: int(value.get("structural_rank") or 999)):
        if not row.get("available_for_execution"):
            continue
        signature_rows.append(
            (
                str(row["candidate_id"]),
                float(row["structural_score"]),
                "executed" if row.get("candidate_id") == acquisition.get("selected_simulator_probe") else "ranked only",
            )
        )
    signature_path = figure_root / "intervention-signatures.svg"
    signature_path.parent.mkdir(parents=True, exist_ok=True)
    signature_path.write_text(
        _figure_svg(
            "Structural intervention ranking",
            f"Same acquisition rows as Studio; prospective signatures: {len(observed)} bound groups.",
            signature_rows,
        ),
        encoding="utf-8",
    )
    result: dict[str, dict[str, Any]] = {}
    for name, (_, target) in copied.items():
        result[name] = {"path": _relative(target, output_root), "sha256": sha256_file(target), "source_view": name}
    result["intervention_signatures"] = {"path": _relative(signature_path, output_root), "sha256": sha256_file(signature_path), "source_view": "acquisition_and_prospective_signatures"}
    return result


def compile_studio_observatory(
    config_path: Path = DEFAULT_CONFIG,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    resolved_config = config_path if config_path.is_absolute() else repo_root / config_path
    resolved_output = output_root if output_root.is_absolute() else repo_root / output_root
    config, paths = load_studio_config(resolved_config, repo_root=repo_root)
    catalog = _read_bound_json(paths, "evidence_catalog", "sim2claw.sail_evidence_catalog.v1")
    omissions = _read_bound_json(paths, "evidence_omissions", "sim2claw.sail_evidence_omissions.v1")
    heatmap = _read_bound_json(paths, "residual_heatmap", "sim2claw.sail_residual_heatmap.v1")
    drilldowns = _read_bound_json(paths, "residual_drilldowns", "sim2claw.sail_residual_episode_drilldowns.v1")
    belief = _read_bound_json(paths, "belief_graph", "sim2claw.sail_belief_graph.v1")
    revisions_raw = json.loads(paths["belief_revision_timeline"].read_text(encoding="utf-8"))
    _require(isinstance(revisions_raw, list) and revisions_raw, "SAIL Studio belief revisions are empty")
    surprise = _read_bound_json(paths, "structural_surprise", "sim2claw.sail_structural_surprise.v1")
    closure = _read_bound_json(paths, "loop_closure", "sim2claw.sail_sparse_loop_closure.v1")
    particles = _read_bound_json(paths, "retained_particles", "sim2claw.sail_retained_structure_particles.v1")
    invariance = _read_bound_json(paths, "retained_invariance", "sim2claw.sail_retained_invariance_inventory.v1")
    acquisition = _read_bound_json(paths, "acquisition_ranking", "sim2claw.sail_acquisition_ranking.v1")
    prospective = _read_bound_json(paths, "prospective_experiment", "sim2claw.sail_prospective_simulator_experiment.v1")
    capability = _read_bound_json(paths, "twin_capability_report", "sim2claw.sail_twin_capability_report.v1")
    gallery = _read_bound_json(paths, "ranked_gallery", "sim2claw.pawn_bg_ranked_grasp_gallery.v1")
    evidence_root = repo_root / str(config["evidence_root"])
    episodes = _compile_episodes(
        gallery=gallery,
        catalog=catalog,
        heatmap=heatmap,
        drilldown=drilldowns,
        evidence_root=evidence_root,
        repo_root=repo_root,
    )
    figures = _write_figures(
        output_root=resolved_output,
        source_paths=paths,
        acquisition=acquisition,
        prospective=prospective,
    )
    current = capability["current"]
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "campaign_id": str(config["campaign_id"]),
        "generated_at": str(config["determinism"]["generated_at"]),
        "title": "SAIL evidence spine",
        "claim_boundary": "A synchronized retrospective and prospective-simulator investigation surface. Visuals do not grant training, promotion, transfer, hardware, or physical authority.",
        "ranking": {
            **copy.deepcopy(gallery["ranking"]),
            "source_selection_rule": gallery["ranking"]["selection_rule"],
            "selection_rule": "Lead with the seven strongest partial episodes and retain the four lower-signal touch or qualified-pinch episodes in the same investigation surface.",
            "displayed_episode_count": len(episodes),
            "lower_signal_retained_count": len(gallery.get("excluded_episodes") or []),
            "omitted_episode_count": 0,
            "omission_policy": "Only an explicitly classified no-signal episode may be omitted; all eleven signal-bearing development episodes remain visible.",
        },
        "episodes": episodes,
        "residuals": {
            "channels": copy.deepcopy(heatmap["channels"]),
            "rows": copy.deepcopy(heatmap["rows"]),
            "normalization": heatmap["normalization"],
            "receipt_sha256": sha256_file(paths["residual_receipt"]),
        },
        "belief_revision": {
            "counts": copy.deepcopy(belief["counts"]),
            "timeline": copy.deepcopy(revisions_raw),
            "before": copy.deepcopy(revisions_raw[0]),
            "after": copy.deepcopy(revisions_raw[-1]),
            "graph_digest": belief["graph_digest"],
            "receipt_sha256": sha256_file(paths["belief_receipt"]),
        },
        "compensation_debt": {
            "score": surprise["score"],
            "triggered": surprise["triggered"],
            "components": copy.deepcopy(surprise["components"]),
            "before_sparse_closure": closure["before"]["compensation_debt"],
            "after_sparse_closure": closure["sparse"]["compensation_debt"],
            "claim_boundary": surprise["claim_boundary"],
            "receipt_sha256": sha256_file(paths["structural_surprise_receipt"]),
        },
        "interventions": {
            "rows": copy.deepcopy(acquisition["rows"]),
            "selected_simulator_probe": acquisition["selected_simulator_probe"],
            "prospective_decision": copy.deepcopy(prospective["acquisition_decision"]),
            "predicted_versus_observed_signatures": copy.deepcopy(prospective["predicted_versus_observed_signatures"]),
            "loop_closure_next_probe": copy.deepcopy(prospective["loop_closure_next_probe"]),
            "receipt_sha256": sha256_file(paths["acquisition_receipt"]),
        },
        "posterior_and_invariance": {
            "particles": copy.deepcopy(particles["particles"]),
            "structures_averaged": particles["structures_averaged"],
            "physical_mechanism_identified": particles["physical_mechanism_identified"],
            "invariance_results": copy.deepcopy(invariance["results"]),
            "invariance_counts": copy.deepcopy(invariance["counts"]),
            "receipt_sha256": sha256_file(paths["invariance_receipt"]),
        },
        "twin_worthiness": {
            "level": current["base_certificate_level"],
            "allowed_capabilities": copy.deepcopy(current["allowed_capabilities"]),
            "denied_capabilities": copy.deepcopy(current["denied_capabilities"]),
            "matrix": copy.deepcopy(current["matrix"]),
            "minimum_new_evidence": copy.deepcopy(capability["minimum_new_evidence"]),
            "revocation_evaluation": copy.deepcopy(capability["revocation_evaluation"]),
            "training_admitted": current["training_admitted"],
            "policy_selection_admitted": current["policy_selection_admitted"],
            "physical_authority": current["physical_authority"],
            "receipt_sha256": sha256_file(paths["twin_capability_receipt"]),
        },
        "missingness": {
            "catalog": copy.deepcopy(omissions["omissions"]),
            "never_imputed": True,
            "missing_is_not_zero": True,
        },
        "proof_legend": [
            {"id": "physical_read_only", "label": "Retained physical telemetry", "authority": "read_only_unqualified"},
            {"id": "retained_replay", "label": "Action-frozen simulator replay", "authority": "diagnostic_only"},
            {"id": "prospective_simulator", "label": "Preregistered prospective simulator", "authority": "simulator_only"},
            {"id": "learned_policy_simulation", "label": "Learned policy simulation", "authority": "terminal_negative_or_separately_gated"},
            {"id": "visual_only", "label": "Video / 3DGS", "authority": "appearance_only"},
            {"id": "physical_task", "label": "Physical task", "authority": "absent"},
        ],
        "figures": {
            name: {**binding, "url": f"/api/sail-observatory/figures/{Path(binding['path']).name}"}
            for name, binding in figures.items()
        },
        "source_bindings": {
            name: {"path": _relative(path, repo_root), "sha256": sha256_file(path)}
            for name, path in sorted(paths.items())
        },
        "authority": {
            "read_only": True,
            "training_admission": False,
            "policy_selection": False,
            "simulator_promotion": False,
            "physical_transfer": False,
            "robot_motion": False,
            "physical_authority": False,
        },
    }
    resolved_output.mkdir(parents=True, exist_ok=True)
    manifest_path = resolved_output / "studio_observatory.json"
    atomic_write_json(manifest_path, manifest)
    code_paths = (
        "src/sim2claw/sail/studio.py",
        "configs/studio/project_map_v1.json",
        "src/sim2claw/studio_project_map.py",
        "src/sim2claw/studio_server.py",
        "src/sim2claw/studio_twin_fidelity.py",
        "src/sim2claw/studio_web/index.html",
        "src/sim2claw/studio_web/studio.css",
        "src/sim2claw/studio_web/studio.js",
    )
    unsigned_receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "campaign_id": config["campaign_id"],
        "generated_at": config["determinism"]["generated_at"],
        "config": {"path": _relative(resolved_config, repo_root), "sha256": sha256_file(resolved_config)},
        "compiler_sha256": {path: sha256_file(repo_root / path) for path in code_paths},
        "outputs": {
            "manifest": {"path": "studio_observatory.json", "sha256": sha256_file(manifest_path)},
            **{f"figure_{name}": binding for name, binding in figures.items()},
        },
        "counts": {
            "displayed_episode_count": len(episodes),
            "ranked_episode_count": 7,
            "lower_signal_retained_count": 4,
            "residual_heatmap_row_count": len(heatmap["rows"]),
            "belief_revision_count": len(revisions_raw),
            "intervention_count": len(acquisition["rows"]),
            "posterior_particle_count": len(particles["particles"]),
            "invariance_result_count": len(invariance["results"]),
            "figure_count": len(figures),
        },
        "authority": copy.deepcopy(config["authority"]),
        "claim_boundary": manifest["claim_boundary"],
    }
    receipt = {**unsigned_receipt, "receipt_digest": canonical_digest(unsigned_receipt)}
    receipt_path = resolved_output / "receipt.json"
    atomic_write_json(receipt_path, receipt)
    verify_studio_receipt(receipt, output_root=resolved_output, repo_root=repo_root)
    return {
        "schema_version": "sim2claw.sail_studio_observatory_compile_result.v1",
        "status": "compiled",
        "output_root": str(resolved_output),
        "manifest_sha256": sha256_file(manifest_path),
        "receipt_sha256": sha256_file(receipt_path),
        "receipt_digest": receipt["receipt_digest"],
        "counts": receipt["counts"],
        "physical_authority": False,
    }


def verify_studio_receipt(
    receipt: Mapping[str, Any], *, output_root: Path, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(receipt))
    _require(normalized.get("schema_version") == RECEIPT_SCHEMA, "unexpected SAIL Studio receipt schema")
    observed = normalized.pop("receipt_digest", None)
    _require(observed == canonical_digest(normalized), "SAIL Studio receipt digest mismatch")
    authority = normalized.get("authority")
    _require(isinstance(authority, dict) and authority and not any(authority.values()), "SAIL Studio receipt widened authority")
    config = normalized.get("config") or {}
    config_path = repo_root / str(config.get("path") or "")
    _require(config_path.is_file() and sha256_file(config_path) == config.get("sha256"), "SAIL Studio receipt config changed")
    for relative, expected in (normalized.get("compiler_sha256") or {}).items():
        path = repo_root / str(relative)
        _require(path.is_file() and sha256_file(path) == expected, f"SAIL Studio compiler changed: {relative}")
    for name, binding in (normalized.get("outputs") or {}).items():
        path = output_root / str(binding.get("path") or "")
        _require(path.is_file() and sha256_file(path) == binding.get("sha256"), f"SAIL Studio output changed: {name}")
    return {**normalized, "receipt_digest": str(observed)}


def load_studio_observatory(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    resolved = output_root if output_root.is_absolute() else repo_root / output_root
    receipt = load_json_object(resolved / "receipt.json", label="SAIL Studio receipt")
    verify_studio_receipt(receipt, output_root=resolved, repo_root=repo_root)
    manifest = load_json_object(resolved / "studio_observatory.json", label="SAIL Studio manifest")
    _require(manifest.get("schema_version") == MANIFEST_SCHEMA, "unexpected SAIL Studio manifest schema")
    _require(manifest.get("authority", {}).get("read_only") is True, "SAIL Studio manifest is not read-only")
    _require(not any(value for key, value in manifest["authority"].items() if key != "read_only"), "SAIL Studio manifest widened authority")
    return {"available": True, "receipt_sha256": sha256_file(resolved / "receipt.json"), **manifest}


def open_studio_figure(
    name: str,
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    repo_root: Path = REPO_ROOT,
) -> tuple[Path, bytes, str]:
    _require(name == Path(name).name and name.endswith(".svg"), "invalid SAIL Studio figure name")
    manifest = load_studio_observatory(output_root=output_root, repo_root=repo_root)
    bindings = {Path(row["path"]).name: row for row in manifest["figures"].values()}
    _require(name in bindings, "unknown SAIL Studio figure")
    resolved = output_root if output_root.is_absolute() else repo_root / output_root
    path = resolved / "figures" / name
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    _require(digest == bindings[name]["sha256"], "SAIL Studio figure changed")
    return path, payload, digest


__all__ = [
    "CONFIG_SCHEMA",
    "DEFAULT_CONFIG",
    "DEFAULT_OUTPUT_ROOT",
    "MANIFEST_SCHEMA",
    "RECEIPT_SCHEMA",
    "StudioObservatoryError",
    "compile_studio_observatory",
    "load_studio_config",
    "load_studio_observatory",
    "open_studio_figure",
    "verify_studio_receipt",
]

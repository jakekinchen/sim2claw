"""Read-only catalog adapters for the sim2claw browser studio."""

from __future__ import annotations

import base64
import json
import os
import shlex
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from .paths import REPO_ROOT


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _title(identifier: str) -> str:
    return " ".join(part.capitalize() for part in identifier.replace("-", "_").split("_") if part)


def _iso_timestamp(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
    except OSError:
        return None


def media_token(path: Path, repo_root: Path = REPO_ROOT) -> str:
    relative = path.resolve().relative_to(repo_root.resolve()).as_posix()
    return base64.urlsafe_b64encode(relative.encode("utf-8")).decode("ascii").rstrip("=")


def media_url(path: Path, repo_root: Path = REPO_ROOT) -> str:
    return f"/media/{media_token(path, repo_root)}"


def resolve_media_token(token: str, repo_root: Path = REPO_ROOT) -> Path:
    padding = "=" * (-len(token) % 4)
    try:
        relative = base64.urlsafe_b64decode(token + padding).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as error:
        raise ValueError("invalid media token") from error
    candidate = (repo_root / relative).resolve()
    allowed_roots = [
        (repo_root / name).resolve() for name in ("outputs", "datasets", "runs")
    ]
    if not any(candidate.is_relative_to(root) for root in allowed_roots):
        raise ValueError("media path is outside generated artifact storage")
    suffix = candidate.suffix.lower()
    if suffix not in {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".mp4",
        ".webm",
        ".json",
    }:
        raise ValueError("media type is not allowed")
    if suffix == ".json" and not (
        candidate.name == "state_trace.json"
        or (
            candidate.parent.name == "state_traces"
            and candidate.name.startswith("episode_")
        )
    ):
        raise ValueError("JSON media is limited to episode state traces")
    return candidate


def _inspection(path: Path, repo_root: Path) -> dict[str, Any] | None:
    trace = _read_json(path)
    if trace.get("schema_version") != "sim2claw.mujoco_body_state_trace.v1":
        return None
    scene = trace.get("scene", {})
    return {
        "kind": "threejs_state_trace",
        "trace_url": media_url(path, repo_root),
        "scene_url": str(
            scene.get("manifest_url")
            or f"/api/scene?layout={scene.get('piece_layout', 'standard')}"
        ),
        "frame_count": int(trace.get("frame_count") or 0),
        "fps": float(trace.get("fps") or 0),
        "duration_seconds": float(trace.get("duration_seconds") or 0),
        "physics_authority": "mujoco",
        "renderer_authority": "inspection_only",
    }


def _proof_label(proof_class: str) -> str:
    labels = {
        "simulation_learned_policy": "Learned policy · simulation",
        "simulation_learned_policy_episode": "Learned policy · held-out simulation",
        "simulation_scripted_grasp_probe": "Scripted probe · simulation",
        "simulation_synthetic_vla_demonstration": "Synthetic VLA demonstrations",
        "simulation_synthetic_vla_demonstration_dataset": (
            "Evaluator-accepted synthetic demonstrations"
        ),
    }
    return labels.get(proof_class, proof_class.replace("_", " ").capitalize())


def _phase_segments(contract: dict[str, Any]) -> list[dict[str, Any]]:
    episode = contract.get("episode", {})
    raw = episode.get("phase_physics_steps") or episode.get("phase_control_steps") or {}
    if not isinstance(raw, dict) or not raw:
        return []
    values = [(str(name), max(0, int(value))) for name, value in raw.items()]
    total = sum(value for _, value in values)
    if total <= 0:
        return []
    cursor = 0
    segments: list[dict[str, Any]] = []
    for name, value in values:
        segments.append(
            {
                "name": name.replace("_", " ").capitalize(),
                "start": cursor / total,
                "end": (cursor + value) / total,
            }
        )
        cursor += value
    return segments


def _task_role(contract: dict[str, Any]) -> str:
    model = contract.get("model", {})
    if isinstance(model, dict) and model.get("family"):
        return str(model["family"])
    act = contract.get("act", {})
    if isinstance(act, dict) and act:
        return "ACT policy"
    return "Simulation task"


def _task_description(contract: dict[str, Any]) -> str:
    cases = contract.get("training_cases")
    if isinstance(cases, list) and cases:
        return f"{len(cases)} instruction variants across a frozen synthetic demonstration set."
    scene = contract.get("scene", {})
    piece = scene.get("piece") if isinstance(scene, dict) else None
    if piece:
        return f"A frozen left-arm lift task for {_title(str(piece)).lower()}."
    return "A frozen simulation task contract."


def _metric(label: str, value: Any, *, unit: str = "", tone: str = "neutral") -> dict[str, Any]:
    return {"label": label, "value": value, "unit": unit, "tone": tone}


def _dataset_episodes(
    repo_root: Path,
    contracts: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    episodes: list[dict[str, Any]] = []
    datasets_root = repo_root / "datasets"
    if not datasets_root.exists():
        return episodes
    for dataset in sorted(path for path in datasets_root.iterdir() if path.is_dir()):
        receipt = _read_json(dataset / "dataset_receipt.json")
        task_id = str(receipt.get("task_id") or dataset.name)
        contract = contracts.get(task_id, {})
        info = _read_json(dataset / "meta" / "info.json")
        fps = float(info.get("fps") or contract.get("episode", {}).get("sample_fps") or 0)
        rows = _read_jsonl(dataset / "meta" / "episodes.jsonl")
        videos = sorted(dataset.glob("videos/**/episode_*.mp4"))
        if not rows:
            rows = [
                {"episode_index": index, "length": None, "tasks": []}
                for index, _ in enumerate(videos)
            ]
        video_by_index = {
            int(path.stem.rsplit("_", 1)[-1]): path
            for path in videos
            if path.stem.rsplit("_", 1)[-1].isdigit()
        }
        evidence = {
            int(row.get("episode_index", -1)): row
            for row in receipt.get("episode_evidence", [])
            if isinstance(row, dict)
        }
        phases = _phase_segments(contract)
        for row in rows:
            index = int(row.get("episode_index", len(episodes)))
            video = video_by_index.get(index)
            if video is None or not video.is_file():
                continue
            proof_class = str(
                receipt.get("proof_class")
                or contract.get("proof_class")
                or "simulation_replay"
            )
            detail = evidence.get(index, {})
            verdict = detail.get("verdict", {}) if isinstance(detail, dict) else {}
            success = verdict.get("success")
            gates = verdict.get("gates", {}) if isinstance(verdict, dict) else {}
            final_xy = gates.get("final_xy_error", {}).get("measured")
            rise = gates.get("minimum_piece_rise", {}).get("measured")
            task_texts = row.get("tasks") if isinstance(row.get("tasks"), list) else []
            instruction = str(task_texts[0]) if task_texts else _title(task_id)
            frame_count = row.get("length")
            duration = float(frame_count) / fps if frame_count and fps else None
            trace_path = dataset / "state_traces" / f"episode_{index:06d}.json"
            inspection = _inspection(trace_path, repo_root) if trace_path.is_file() else None
            metrics = [
                _metric("Seed", detail.get("seed", "—")),
                _metric("Frames", frame_count or "—"),
            ]
            if final_xy is not None:
                metrics.append(
                    _metric(
                        "Final error",
                        round(float(final_xy) * 1000, 2),
                        unit="mm",
                        tone="good",
                    )
                )
            if rise is not None:
                metrics.append(
                    _metric(
                        "Peak lift",
                        round(float(rise) * 1000, 1),
                        unit="mm",
                        tone="good",
                    )
                )
            catalog_episode = {
                    "id": f"{task_id}:episode-{index:06d}",
                    "task_id": task_id,
                    "title": f"Episode {index + 1:02d}",
                    "subtitle": instruction,
                    "sequence": index,
                    "status": (
                        "passed"
                        if success is True
                        else "failed"
                        if success is False
                        else "recorded"
                    ),
                    "terminal_outcome": (
                        verdict.get("terminal_outcome")
                        if isinstance(verdict, dict)
                        else None
                    ),
                    "proof_class": proof_class,
                    "proof_label": _proof_label(proof_class),
                    "physical_authority": False,
                    "frame_count": frame_count,
                    "fps": fps or None,
                    "duration_seconds": duration,
                    "recorded_at": _iso_timestamp(video),
                    "media": {"kind": "video", "url": media_url(video, repo_root)},
                    "camera": str(
                        contract.get("scene", {}).get("camera") or "workcell"
                    ),
                    "metrics": metrics,
                    "phases": phases,
                    "case_id": detail.get("case_id") if isinstance(detail, dict) else None,
                }
            if inspection is not None:
                catalog_episode["inspection"] = inspection
            episodes.append(catalog_episode)
    return episodes


def _act_episodes(
    repo_root: Path,
    contracts: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    episodes: list[dict[str, Any]] = []
    for receipt_path in sorted((repo_root / "outputs").glob("**/evaluation_receipt.json")):
        receipt = _read_json(receipt_path)
        task_id = str(receipt.get("task_id") or receipt_path.parent.parent.name)
        contract = contracts.get(task_id, {})
        video_payload = receipt.get("artifacts", {}).get("video", {})
        video_path = (
            Path(str(video_payload.get("path", ""))).expanduser()
            if isinstance(video_payload, dict)
            else Path()
        )
        if video_path and not video_path.is_absolute():
            video_path = repo_root / video_path
        frames = sorted((receipt_path.parent / "frames").glob("*.png"))
        if video_path.is_file():
            media = {"kind": "video", "url": media_url(video_path, repo_root)}
        elif frames:
            media = {
                "kind": "frames",
                "urls": [media_url(path, repo_root) for path in frames],
                "fps": 10,
            }
        else:
            continue
        episode = receipt.get("episode", {})
        state_trace_value = receipt.get("artifacts", {}).get("state_trace")
        state_trace_path = Path(str(state_trace_value or "")).expanduser()
        if state_trace_path and not state_trace_path.is_absolute():
            state_trace_path = repo_root / state_trace_path
        inspection = (
            _inspection(state_trace_path, repo_root)
            if state_trace_path.is_file()
            else None
        )
        proof_class = str(receipt.get("proof_class") or "simulation_learned_policy_episode")
        success = receipt.get("success")
        metrics = [
            _metric("Seed", episode.get("seed", "—")),
            _metric(
                "Peak lift",
                round(float(episode.get("maximum_piece_rise_m", 0)) * 1000, 1),
                unit="mm",
                tone="good",
            ),
            _metric(
                "Final lift",
                round(float(episode.get("final_piece_rise_m", 0)) * 1000, 1),
                unit="mm",
                tone="good",
            ),
            _metric(
                "Contact",
                f"{float(episode.get('final_contact_fraction', 0)) * 100:.0f}%",
                tone="good",
            ),
        ]
        catalog_episode = {
                "id": f"{task_id}:held-out-{episode.get('seed', 'episode')}",
                "task_id": task_id,
                "title": "Held-out policy replay",
                "subtitle": (
                    f"{_title(str(episode.get('piece', 'piece')))} · "
                    f"seed {episode.get('seed', '—')}"
                ),
                "sequence": 10_000 + len(episodes),
                "status": "passed" if success is True else "failed",
                "terminal_outcome": receipt.get("terminal_outcome"),
                "proof_class": proof_class,
                "proof_label": _proof_label(proof_class),
                "physical_authority": False,
                "frame_count": len(frames) or episode.get("control_steps"),
                "fps": 10 if frames else None,
                "duration_seconds": None,
                "recorded_at": _iso_timestamp(receipt_path),
                "media": media,
                "camera": str(contract.get("scene", {}).get("camera") or "workcell"),
                "metrics": metrics,
                "phases": _phase_segments(contract),
                "case_id": "held_out_evaluation",
            }
        if inspection is not None:
            catalog_episode["inspection"] = inspection
        episodes.append(catalog_episode)
    return episodes


def _grasp_episodes(repo_root: Path) -> list[dict[str, Any]]:
    episodes: list[dict[str, Any]] = []
    for receipt_path in sorted((repo_root / "outputs").glob("**/grasp_probe_receipt.json")):
        receipt = _read_json(receipt_path)
        artifact_paths: list[Path] = []
        for value in receipt.get("artifacts", {}).values():
            path = Path(str(value)).expanduser()
            if not path.is_absolute():
                path = repo_root / path
            if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                artifact_paths.append(path)
        if not artifact_paths:
            continue
        phases = receipt.get("phases", [])
        phase_total = sum(int(row.get("steps", 0)) for row in phases if isinstance(row, dict))
        cursor = 0
        segments = []
        for row in phases:
            if not isinstance(row, dict) or phase_total <= 0:
                continue
            steps = int(row.get("steps", 0))
            segments.append(
                {
                    "name": _title(str(row.get("name", "phase"))),
                    "start": cursor / phase_total,
                    "end": (cursor + steps) / phase_total,
                }
            )
            cursor += steps
        proof_class = str(receipt.get("proof_class") or "simulation_scripted_grasp_probe")
        trace_value = receipt.get("artifacts", {}).get("state_trace")
        trace_path = Path(str(trace_value or "")).expanduser()
        if trace_path and not trace_path.is_absolute():
            trace_path = repo_root / trace_path
        inspection = _inspection(trace_path, repo_root) if trace_path.is_file() else None
        catalog_episode = {
                "id": "scripted_grasp_probe:latest",
                "task_id": "scripted_grasp_probe",
                "title": "Five-phase grasp probe",
                "subtitle": (
                    f"{_title(str(receipt.get('piece', 'piece')))} · "
                    f"{receipt.get('arm', 'left')} arm"
                ),
                "sequence": 20_000,
                "status": "passed" if receipt.get("success") else "failed",
                "terminal_outcome": "piece_lifted" if receipt.get("success") else "probe_failed",
                "proof_class": proof_class,
                "proof_label": _proof_label(proof_class),
                "physical_authority": False,
                "frame_count": len(artifact_paths),
                "fps": 1,
                "duration_seconds": float(len(artifact_paths)),
                "recorded_at": _iso_timestamp(receipt_path),
                "media": {
                    "kind": "frames",
                    "urls": [media_url(path, repo_root) for path in artifact_paths],
                    "fps": 1,
                },
                "camera": "workcell",
                "metrics": [
                    _metric(
                        "Rise",
                        round(float(receipt.get("piece_rise_m", 0)) * 1000, 1),
                        unit="mm",
                        tone="good",
                    ),
                    _metric(
                        "Lift contact",
                        f"{float(receipt.get('lift_contact_fraction', 0)) * 100:.0f}%",
                        tone="good",
                    ),
                    _metric("Phases", len(phases)),
                ],
                "phases": segments,
                "case_id": "scripted_probe",
            }
        if inspection is not None:
            catalog_episode["inspection"] = inspection
        episodes.append(catalog_episode)
    return episodes


def _teleop_episodes(repo_root: Path) -> list[dict[str, Any]]:
    episodes: list[dict[str, Any]] = []
    receipt_paths = sorted(
        (repo_root / "datasets" / "act_source_recordings").glob(
            "*/recording_receipt.json"
        )
    )
    for sequence, receipt_path in enumerate(receipt_paths):
        receipt = _read_json(receipt_path)
        if receipt.get("mode") != "simulation_follower":
            continue
        trace_path = receipt_path.parent / str(
            receipt.get("state_trace_path") or "state_trace.json"
        )
        inspection = _inspection(trace_path, repo_root) if trace_path.is_file() else None
        if inspection is None:
            continue
        proof_class = str(
            receipt.get("proof_class") or "simulation_teleoperation_source"
        )
        outcome = str(receipt.get("outcome_label") or "recorded")
        duration = float(receipt.get("duration_seconds") or 0)
        episodes.append(
            {
                "id": f"{receipt.get('task_id', 'teleop')}:{receipt.get('recording_id', sequence)}",
                "task_id": str(receipt.get("task_id") or "act_source_recordings"),
                "title": str(receipt.get("label") or f"Teleop recording {sequence + 1}"),
                "subtitle": (
                    f"{_title(str(receipt.get('piece_id', 'piece')))} · "
                    f"{receipt.get('source_square', '—')} → {receipt.get('destination_square', '—')}"
                ),
                "sequence": 30_000 + sequence,
                "status": "passed" if outcome == "success" else "recorded",
                "terminal_outcome": outcome,
                "proof_class": proof_class,
                "proof_label": _proof_label(proof_class),
                "physical_authority": False,
                "frame_count": inspection["frame_count"],
                "fps": inspection["fps"],
                "duration_seconds": duration or inspection["duration_seconds"],
                "recorded_at": _iso_timestamp(receipt_path),
                "media": {"kind": "none"},
                "inspection": inspection,
                "camera": "free_orbit",
                "metrics": [
                    _metric("Samples", receipt.get("sample_count", "—")),
                    _metric("Rate", receipt.get("sample_hz", "—"), unit="Hz"),
                    _metric("Outcome", _title(outcome)),
                ],
                "phases": [{"name": "Teleoperation", "start": 0.0, "end": 1.0}],
                "case_id": "simulation_teleoperation_source",
            }
        )
    return episodes


def _pid_exists(pid: Any) -> bool:
    try:
        os.kill(int(pid), 0)
    except (OSError, TypeError, ValueError):
        return False
    return True


def _registered_processes(repo_root: Path) -> list[dict[str, Any]]:
    root = repo_root / "runs" / "studio" / "processes"
    processes: list[dict[str, Any]] = []
    if not root.exists():
        return processes
    paths = sorted(
        root.glob("*.json"),
        key=lambda value: value.stat().st_mtime,
        reverse=True,
    )[:30]
    for path in paths:
        row = _read_json(path)
        if not row:
            continue
        if row.get("status") == "running" and not _pid_exists(row.get("pid")):
            row["status"] = "interrupted"
            row["phase"] = "Process ended without a final heartbeat"
        row["source"] = "heartbeat"
        row["physical_authority"] = False
        processes.append(row)
    return processes


def _groot_export_progress(repo_root: Path, command: str) -> dict[str, Any]:
    try:
        tokens = shlex.split(command)
        command_index = tokens.index("groot-export")
    except (ValueError, IndexError):
        return {}
    output = repo_root / "datasets" / "chess_pick_place_groot_v1"
    maximum: int | None = None
    index = command_index + 1
    while index < len(tokens):
        token = tokens[index]
        if token == "--output" and index + 1 < len(tokens):
            output = Path(tokens[index + 1]).expanduser()
            index += 1
        elif token.startswith("--output="):
            output = Path(token.split("=", 1)[1]).expanduser()
        elif token == "--max-episodes" and index + 1 < len(tokens):
            maximum = int(tokens[index + 1])
            index += 1
        elif token.startswith("--max-episodes="):
            maximum = int(token.split("=", 1)[1])
        index += 1
    if not output.is_absolute():
        output = repo_root / output
    contract = _read_json(repo_root / "configs" / "tasks" / "chess_pick_place_groot_v1.json")
    expected = len(contract.get("training_episodes", []))
    if maximum is not None:
        expected = min(expected, maximum) if expected else maximum
    current = len(list(output.glob("videos/**/episode_*.mp4"))) if output.exists() else 0
    if expected <= 0:
        return {}
    return {
        "current": current,
        "total": expected,
        "progress": min(1.0, current / expected),
        "phase": f"Generating demonstration {min(current + 1, expected)} of {expected}",
    }


def _system_processes(
    repo_root: Path,
    registered: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    try:
        output = subprocess.run(
            ["ps", "-axo", "pid=,etime=,command="],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    registered_rows = list(registered)
    known = {int(row.get("pid", -1)) for row in registered_rows}
    known_activity_keys = {
        (str(row.get("task_id")), str(row.get("kind")))
        for row in registered_rows
        if row.get("status") == "running"
    }
    command_markers = (
        "sim2claw act-train",
        "sim2claw act-eval",
        "sim2claw groot-export",
        "sim2claw groot-expert-eval",
        "sim2claw grasp-probe",
    )
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        parts = line.strip().split(maxsplit=2)
        if len(parts) != 3 or not any(marker in parts[2] for marker in command_markers):
            continue
        pid = int(parts[0])
        if pid in known:
            continue
        command = parts[2]
        marker = next(value for value in command_markers if value in command)
        task_id = (
            "chess_rook_lift_v1"
            if "act-" in marker
            else "chess_pick_place_groot_v1"
            if "groot-" in marker
            else "scripted_grasp_probe"
        )
        kind = (
            "training"
            if "train" in marker
            else "dataset"
            if "export" in marker
            else "evaluation"
        )
        if (task_id, kind) in known_activity_keys:
            continue
        row = {
            "schema_version": "sim2claw.studio_discovered_process.v1",
            "id": f"process-{pid}",
            "kind": kind,
            "title": _title(marker.removeprefix("sim2claw ")),
            "task_id": task_id,
            "status": "running",
            "phase": "Running · progress heartbeat unavailable",
            "current": None,
            "total": None,
            "progress": None,
            "pid": pid,
            "elapsed": parts[1],
            "detail": command,
            "metrics": {},
            "episode_id": None,
            "source": "process_scan",
            "physical_authority": False,
        }
        if "groot-export" in marker:
            row.update(_groot_export_progress(repo_root, command))
        rows.append(row)
    return rows


def build_catalog(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Build the current task/episode/process view without mutating artifacts."""

    contracts: dict[str, dict[str, Any]] = {}
    config_paths: dict[str, Path] = {}
    for path in sorted((repo_root / "configs" / "tasks").glob("*.json")):
        contract = _read_json(path)
        task_id = str(contract.get("task_id") or path.stem)
        contracts[task_id] = contract
        config_paths[task_id] = path

    episodes = (
        _dataset_episodes(repo_root, contracts)
        + _act_episodes(repo_root, contracts)
        + _grasp_episodes(repo_root)
        + _teleop_episodes(repo_root)
    )
    episodes.sort(key=lambda row: (str(row["task_id"]), int(row["sequence"])))

    task_ids = set(contracts) | {str(row["task_id"]) for row in episodes}
    tasks: list[dict[str, Any]] = []
    title_overrides = {
        "chess_pick_place_groot_v1": "Chess pick + place",
        "chess_rook_lift_v1": "Rook lift",
        "scripted_grasp_probe": "Scripted grasp probe",
    }
    for task_id in sorted(task_ids):
        contract = contracts.get(task_id, {})
        task_episodes = [row for row in episodes if row["task_id"] == task_id]
        proof_class = str(
            contract.get("proof_class")
            or (task_episodes[0]["proof_class"] if task_episodes else "simulation")
        )
        tasks.append(
            {
                "id": task_id,
                "title": title_overrides.get(task_id, _title(task_id)),
                "role": _task_role(contract) if contract else "Simulation probe",
                "description": (
                    _task_description(contract)
                    if contract
                    else "A deterministic simulator inspection sequence."
                ),
                "proof_class": proof_class,
                "proof_label": _proof_label(proof_class),
                "frozen": bool(contract.get("frozen_before_training", False)),
                "episode_count": len(task_episodes),
                "passed_count": sum(row["status"] == "passed" for row in task_episodes),
                "failed_count": sum(row["status"] == "failed" for row in task_episodes),
                "physical_authority": False,
                "config_updated_at": (
                    _iso_timestamp(config_paths[task_id])
                    if task_id in config_paths
                    else None
                ),
            }
        )

    studio_asset_root = Path(__file__).with_name("studio_web") / "assets" / "workcell"
    studio_asset_receipt = _read_json(studio_asset_root / "receipt.json")
    capture_paths = sorted((repo_root / "configs" / "polycam").glob("*.json"))
    capture_config = _read_json(capture_paths[0]) if capture_paths else {}
    scene_estimates = capture_config.get("simulation_estimates", {})
    board_local = scene_estimates.get("board", {}).get(
        "center_in_table_frame_xy_m", [0.0, 0.0]
    )
    robot_estimates = {
        str(row.get("name")): row
        for row in scene_estimates.get("robots", [])
        if isinstance(row, dict)
    }
    simulations = [
        {
            "id": "photo_aligned_chess_workcell_v1",
            "title": "Chess table workcell",
            "subtitle": "MuJoCo · dual SO-101 · 16 sparse pawns",
            "piece_layout": "sparse_two_sided_pawns",
            "piece_layout_id": "two_sided_sparse_pawns_rows_1_2_7_8_v1",
            "status": "simulation_ready",
            "task_count": len(tasks),
            "robot_count": 2,
            "physical_authority": False,
            "poster_url": "/assets/workcell/studio-overview.png",
            "poster_camera": "studio_overview",
            "asset_revision": str(
                studio_asset_receipt.get("sources", {}).get(
                    "scene_py_sha256",
                    studio_asset_receipt.get("sources", {}).get(
                        "capture_config_sha256", "unversioned"
                    ),
                )
            )[:8],
        }
    ]
    robots = []
    for side in ("left", "right"):
        estimate = robot_estimates.get(side, {})
        mount = estimate.get("mount_in_table_frame_xyz_m") or []
        board_offset = None
        if mount and board_local:
            board_offset = abs(float(mount[0]) - float(board_local[0]))
        robots.append(
            {
                "id": f"so101_{side}",
                "title": f"{side.capitalize()} SO-101",
                "side": side,
                "role": estimate.get("role") or f"{side.capitalize()} scene arm",
                "model": "RobotStudio SO-101",
                "mode": "MuJoCo simulation",
                "status": "available_in_scene",
                "physical_authority": False,
                "poster_url": f"/assets/workcell/studio-{side}.png",
                "poster_camera": f"studio_{side}",
                "mount_in_table_frame_xyz_m": mount,
                "board_centerline_offset_m": board_offset,
                "alignment_confidence": estimate.get("confidence"),
            }
        )

    processes = _registered_processes(repo_root)
    processes.extend(_system_processes(repo_root, processes))
    processes.sort(
        key=lambda row: (
            row.get("status") != "running",
            str(row.get("started_at", "")),
        )
    )
    active = [row for row in processes if row.get("status") == "running"]

    project_state = _read_json(repo_root / "docs" / "autonomous-workflow" / "project_state.json")
    return {
        "schema_version": "sim2claw.studio_catalog.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "project": {
            "name": "sim2claw",
            "workspace": repo_root.name,
            "active_campaign": project_state.get("active_campaign"),
            "training_lock": project_state.get("training_lock"),
            "physical_authority": False,
            "proof_notice": (
                "Visual replay is evidence inspection, not robot or promotion authority."
            ),
        },
        "summary": {
            "tasks": len(tasks),
            "episodes": len(episodes),
            "passed_episodes": sum(row["status"] == "passed" for row in episodes),
            "active_processes": len(active),
            "robots": len(robots),
        },
        "tasks": tasks,
        "episodes": episodes,
        "processes": processes,
        "simulations": simulations,
        "robots": robots,
    }

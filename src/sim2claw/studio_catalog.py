"""Read-only catalog adapters for the sim2claw browser studio."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shlex
import stat
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO, Iterable

from .paths import REPO_ROOT
from .studio_private_releases import (
    build_calibration_assets,
    build_physical_release_episodes,
    verify_private_media_descriptor,
)


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


PRIVATE_RELEASE_PREFIX = Path("artifacts/private/releases")
GENERATED_MEDIA_ROOTS = frozenset({"outputs", "datasets", "runs"})


def _media_relative_path(token: str) -> Path:
    padding = "=" * (-len(token) % 4)
    try:
        relative = base64.urlsafe_b64decode(token + padding).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as error:
        raise ValueError("invalid media token") from error
    if "\x00" in relative or "\\" in relative:
        raise ValueError("invalid media token")
    relative_path = Path(relative)
    if (
        relative_path.is_absolute()
        or not relative_path.parts
        or any(part in {"", ".", ".."} for part in relative_path.parts)
    ):
        raise ValueError("media path is outside generated artifact storage")
    is_generated = relative_path.parts[0] in GENERATED_MEDIA_ROOTS
    is_private_release = relative_path.is_relative_to(PRIVATE_RELEASE_PREFIX)
    if not is_generated and not is_private_release:
        raise ValueError("media path is outside generated artifact storage")
    suffix = relative_path.suffix.lower()
    if suffix not in {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".mp4",
        ".webm",
        ".ply",
        ".json",
    }:
        raise ValueError("media type is not allowed")
    if suffix == ".json" and not (
        relative_path.name in {"state_trace.json", "sim_replay_state_trace.json"}
        or (
            relative_path.parent.name == "state_traces"
            and relative_path.name.startswith("episode_")
        )
    ):
        raise ValueError("JSON media is limited to episode state traces")
    return relative_path


def _open_relative_no_follow(repo_root: Path, relative: Path) -> int:
    """Open each path component with no-follow semantics and return one file FD."""

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
    directory_fd = os.open(repo_root, directory_flags)
    try:
        for part in relative.parts[:-1]:
            next_fd = os.open(part, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        return os.open(relative.name, file_flags, dir_fd=directory_fd)
    finally:
        os.close(directory_fd)


def open_media_token(
    token: str,
    repo_root: Path = REPO_ROOT,
) -> tuple[Path, BinaryIO, os.stat_result]:
    """Open, admit, and return the exact descriptor that the server will stream."""

    relative = _media_relative_path(token)
    try:
        fd = _open_relative_no_follow(repo_root, relative)
    except OSError as error:
        raise ValueError("media file is unavailable") from error
    try:
        file_stat = os.fstat(fd)
        if not stat.S_ISREG(file_stat.st_mode):
            raise ValueError("media file is not regular")
        if relative.is_relative_to(PRIVATE_RELEASE_PREFIX):
            if not verify_private_media_descriptor(repo_root, relative, fd):
                raise ValueError(
                    "private media is not admitted by a verified release manifest"
                )
            file_stat = os.fstat(fd)
        handle = os.fdopen(fd, "rb")
    except Exception:
        os.close(fd)
        raise
    return repo_root / relative, handle, file_stat


def resolve_media_token(token: str, repo_root: Path = REPO_ROOT) -> Path:
    path, handle, _ = open_media_token(token, repo_root)
    handle.close()
    return path


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


def _receipt_inspection(
    path: Path,
    repo_root: Path,
    receipt: dict[str, Any],
) -> dict[str, Any] | None:
    """Build a catalog row from a replay receipt without reparsing its trace.

    Physical replay traces can contain hundreds of complete MuJoCo body states.
    Their producer writes the immutable listing fields and trace digest into the
    adjacent receipt, so the frequently-polled catalog can stay lightweight.
    The browser still fetches and validates the complete trace when selected.
    """

    if not path.is_file():
        return None
    if receipt.get("state_trace_schema_version") != "sim2claw.mujoco_body_state_trace.v1":
        return None
    try:
        frame_count = int(receipt.get("state_trace_frame_count") or 0)
        fps = float(receipt.get("state_trace_fps") or 0)
        duration = float(receipt.get("state_trace_duration_seconds") or 0)
    except (TypeError, ValueError):
        return None
    trace_sha256 = str(receipt.get("state_trace_sha256") or "")
    if frame_count < 1 or fps <= 0 or len(trace_sha256) != 64:
        return None
    piece_layout = str(receipt.get("state_trace_piece_layout") or "standard")
    manifest_url = str(
        receipt.get("state_trace_manifest_url")
        or f"/api/scene?layout={piece_layout}"
    )
    return {
        "kind": "threejs_state_trace",
        "trace_url": media_url(path, repo_root),
        "scene_url": manifest_url,
        "frame_count": frame_count,
        "fps": fps,
        "duration_seconds": duration,
        "physics_authority": "mujoco",
        "renderer_authority": "inspection_only",
    }


def _proof_label(proof_class: str) -> str:
    labels = {
        "simulation_learned_policy": "Learned policy · simulation",
        "simulation_learned_policy_episode": "Learned policy · held-out simulation",
        "simulation_scripted_grasp_probe": "Scripted probe · simulation",
        "physical_source_simulation_command_replay": (
            "Physical source · simulator command replay"
        ),
        "simulation_synthetic_vla_demonstration": "Synthetic VLA demonstrations",
        "simulation_synthetic_vla_demonstration_dataset": (
            "Evaluator-accepted synthetic demonstrations"
        ),
        "physical_teleoperation_source_unqualified": (
            "Physical source · recorded, not admitted"
        ),
        "owner_provided_monocular_video": "Robo Scanner · owner video",
        "monocular_video_relative_scale_3dgs": "Robo Scanner · visual 3DGS",
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
                    "evaluator_verdict": (
                        "passed"
                        if success is True
                        else "failed"
                        if success is False
                        else None
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
                "evaluator_verdict": "passed" if success is True else "failed",
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
        [
            *(
                repo_root / "datasets" / "manipulation_source_recordings"
            ).glob("*/recording_receipt.json"),
            # Historical ACT-named raw recordings remain inspectable evidence.
            *(repo_root / "datasets" / "act_source_recordings").glob(
                "*/recording_receipt.json"
            ),
        ]
    )
    for sequence, receipt_path in enumerate(receipt_paths):
        receipt = _read_json(receipt_path)
        mode = str(receipt.get("mode") or "")
        if mode not in {"simulation_follower", "physical_follower"}:
            continue
        replay_receipt: dict[str, Any] = {}
        inspection = None
        if mode == "physical_follower":
            replay_receipt = _read_json(receipt_path.parent / "sim_replay_receipt.json")
            if (
                replay_receipt.get("schema_version")
                == "sim2claw.physical_command_sim_replay.v1"
            ):
                trace_path = receipt_path.parent / str(
                    replay_receipt.get("state_trace_path")
                    or "sim_replay_state_trace.json"
                )
                inspection = _receipt_inspection(
                    trace_path,
                    repo_root,
                    replay_receipt,
                )
            else:
                replay_receipt = {}
        else:
            trace_path = receipt_path.parent / str(
                receipt.get("state_trace_path") or "state_trace.json"
            )
            inspection = (
                _inspection(trace_path, repo_root) if trace_path.is_file() else None
            )
        if inspection is None and mode != "physical_follower":
            continue
        source_proof_class = str(
            receipt.get("proof_class") or "simulation_teleoperation_source"
        )
        proof_class = (
            "physical_source_simulation_command_replay"
            if replay_receipt
            else source_proof_class
        )
        outcome = str(receipt.get("outcome_label") or "recorded")
        duration = float(receipt.get("duration_seconds") or 0)
        video_path = receipt_path.parent / "overhead_c922.mp4"
        media = (
            {
                "kind": "video",
                "url": media_url(video_path, repo_root),
                "camera_role": "overhead_board",
                "rotation_degrees": 180,
            }
            if video_path.is_file()
            else {"kind": "none"}
        )
        metrics = [
            _metric("Samples", receipt.get("sample_count", "—")),
            _metric("Rate", receipt.get("sample_hz", "—"), unit="Hz"),
            _metric("Outcome", _title(outcome)),
        ]
        if replay_receipt:
            metrics.extend(
                [
                    _metric(
                        "Sim body RMSE",
                        round(
                            float(
                                replay_receipt.get(
                                    "aggregate_body_joint_rmse_degrees", 0
                                )
                            ),
                            2,
                        ),
                        unit="deg",
                    ),
                    _metric(
                        "Worst sim error",
                        round(
                            float(
                                replay_receipt.get(
                                    "maximum_body_joint_error_degrees", 0
                                )
                            ),
                            2,
                        ),
                        unit="deg",
                    ),
                ]
            )
        episodes.append(
            {
                "id": f"{receipt.get('task_id', 'teleop')}:{receipt.get('recording_id', sequence)}",
                "task_id": str(
                    receipt.get("task_id") or "manipulation_source_recordings"
                ),
                "title": str(receipt.get("label") or f"Teleop recording {sequence + 1}"),
                "subtitle": (
                    f"{_title(str(receipt.get('piece_id', 'piece')))} · "
                    f"{receipt.get('source_square', '—')} → {receipt.get('destination_square', '—')}"
                ),
                "sequence": 30_000 + sequence,
                "status": (
                    "passed"
                    if outcome == "success"
                    else "failed"
                    if outcome == "failure"
                    else "recorded"
                ),
                "terminal_outcome": outcome,
                "proof_class": proof_class,
                "source_proof_class": source_proof_class,
                "proof_label": _proof_label(proof_class),
                "physical_authority": False,
                "frame_count": (
                    inspection["frame_count"]
                    if inspection
                    else int(receipt.get("sample_count") or 0)
                ),
                "fps": (
                    inspection["fps"]
                    if inspection
                    else float(receipt.get("sample_hz") or 0)
                ),
                "duration_seconds": duration or (
                    inspection["duration_seconds"] if inspection else 0
                ),
                "recorded_at": _iso_timestamp(receipt_path),
                "media": media,
                "camera": "free_orbit" if inspection else "logitech_overhead",
                "metrics": metrics,
                "notes": str(receipt.get("notes") or "").strip(),
                "phases": [{"name": "Teleoperation", "start": 0.0, "end": 1.0}],
                "case_id": (
                    "physical_command_simulation_replay"
                    if replay_receipt
                    else "physical_teleoperation_source_unqualified"
                    if mode == "physical_follower"
                    else "simulation_teleoperation_source"
                ),
            }
        )
        if inspection is not None:
            episodes[-1]["inspection"] = inspection
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
        + build_physical_release_episodes(repo_root, media_url)
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
    studio_asset_sources = studio_asset_receipt.get("sources", {})
    asset_revision = hashlib.sha256(
        json.dumps(
            studio_asset_sources,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:8]
    capture_paths = sorted((repo_root / "configs" / "polycam").glob("*.json"))
    capture_config = _read_json(capture_paths[0]) if capture_paths else {}
    scene_estimates = capture_config.get("simulation_estimates", {})
    board_estimate = scene_estimates.get("board", {})
    background_estimate = scene_estimates.get("background", {})
    workspace_pose = scene_estimates.get("workspace_pose", {})
    board_local = board_estimate.get(
        "center_in_table_frame_xy_m", [0.0, 0.0]
    )
    robotward_displacement = board_estimate.get(
        "robotward_displacement_from_previous_pose_m"
    )
    board_pose_label = (
        f"{round(float(robotward_displacement) * 1000):d} mm robotward"
        if robotward_displacement is not None
        else "Current registration"
    )
    progression = _read_json(
        repo_root / "docs" / "run-logs" / "2026-07-19-simulator-progression-ledger.json"
    )
    spatial_fit = progression.get("spatial_fit_progression", [])
    latest_training_fit = next(
        (
            row
            for row in reversed(spatial_fit)
            if row.get("split") == "training" and row.get("contact_episode_count") is not None
        ),
        None,
    )
    latest_held_out_fit = next(
        (row for row in reversed(spatial_fit) if row.get("split") == "held_out"),
        None,
    )
    simulator_accuracy = None
    if latest_training_fit:
        simulator_accuracy = {
            "schema_version": progression.get("schema_version"),
            "label": latest_training_fit.get("label"),
            "proof_state": latest_training_fit.get("proof_state"),
            "event_rms_mm": round(float(latest_training_fit["event_rms_m"]) * 1000, 2),
            "contact_episodes": int(latest_training_fit.get("contact_episode_count", 0)),
            "episode_count": int(latest_training_fit.get("episode_count", 0)),
            "lift_episodes": int(latest_training_fit.get("lift_episode_count", 0)),
            "success_episodes": int(latest_training_fit.get("success_episode_count", 0)),
            "held_out_contact_episodes": int(
                (latest_held_out_fit or {}).get("contact_episode_count", 0)
            ),
            "held_out_episode_count": int(
                (latest_held_out_fit or {}).get("episode_count", 0)
            ),
            "canonical_scene_selected": False,
            "claim": "kinematic contact candidate only; no completed move or physical calibration",
        }
    robot_estimates = {
        str(row.get("name")): row
        for row in scene_estimates.get("robots", [])
        if isinstance(row, dict)
    }
    simulations = [
        {
            "id": board_estimate.get("scene_id", "unversioned_workcell_scene"),
            "title": "Chess table workcell",
            "subtitle": "MuJoCo · dual SO-101 · 16 sparse pawns",
            "piece_layout": "sparse_two_sided_pawns",
            "piece_layout_id": "two_sided_sparse_pawns_rows_1_2_7_8_v1",
            "workcell_pose_id": board_estimate.get("pose_id"),
            "workspace_pose_id": workspace_pose.get("pose_id"),
            "board_center_in_table_frame_xy_m": board_local,
            "board_pose_label": board_pose_label,
            "fiducial_pose_id": background_estimate.get("fiducial_pose_id"),
            "fiducial_center_in_table_frame_xy_m": background_estimate.get(
                "fiducial_center_in_table_frame_xy_m"
            ),
            "status": "simulation_ready",
            "task_count": len(tasks),
            "robot_count": 2,
            "physical_authority": False,
            "poster_url": "/assets/workcell/studio-overview.png",
            "poster_camera": "studio_overview",
            "mug_inspection_url": "/assets/workcell/studio-mug.png",
            "mug_inspection_camera": "studio_mug",
            "visual_props": [
                {
                    "id": "antler_mug",
                    "title": "Antler mug",
                    "placement": "left_window_sill",
                    "physical_authority": False,
                }
            ],
            "asset_revision": asset_revision,
            "simulator_accuracy": simulator_accuracy,
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
    calibrations = build_calibration_assets(repo_root, media_url)
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
            "calibration_assets": len(calibrations),
        },
        "tasks": tasks,
        "episodes": episodes,
        "processes": processes,
        "simulations": simulations,
        "robots": robots,
        "calibrations": calibrations,
    }

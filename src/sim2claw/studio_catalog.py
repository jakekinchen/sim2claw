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


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


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
RANKED_GRASP_PUBLICATION_ROOT = Path(
    "src/sim2claw/studio_web/publication/pawn_bg_ranked_grasp_v1"
)
RANKED_GRASP_OUTPUT_ROOT = Path("outputs/pawn_bg_ranked_grasp_gallery_v1")
RANKED_GRASP_PUBLICATION_SCHEMA = (
    "sim2claw.pawn_bg_ranked_grasp_publication_bundle.v1"
)
PHYSICAL_EPISODE_LIBRARY_TASK = "physical_pawn_episode_library_v1"
COMPARISON_SCHEMA_VERSION = "sim2claw.studio_episode_comparison.v1"


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
        relative_path.name
        in {"state_trace.json", "sim_replay_state_trace.json", "scene_manifest.json"}
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
    if frame_count < 1 or fps <= 0 or not _is_sha256(trace_sha256):
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
        "retained_action_frozen_simulation_replay": (
            "Action-frozen teleop replay · simulation"
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


def _ranked_grasp_episodes(
    repo_root: Path,
    *,
    _gallery_override: tuple[Path, dict[str, Any]] | None = None,
    _include_generated_alternates: bool = True,
) -> list[dict[str, Any]]:
    """Prefer the tracked publication bundle, with generated output fallback."""

    gallery: dict[str, Any] = {}
    gallery_path = Path()
    publication_bundle = False
    if _gallery_override is not None:
        gallery_path, gallery = _gallery_override
    else:
        for relative_root, is_publication in (
            (RANKED_GRASP_PUBLICATION_ROOT, True),
            (RANKED_GRASP_OUTPUT_ROOT, False),
        ):
            candidate = repo_root / relative_root / "gallery_manifest.json"
            candidate_gallery = _read_json(candidate)
            if (
                candidate_gallery.get("schema_version")
                != "sim2claw.pawn_bg_ranked_grasp_gallery.v1"
            ):
                continue
            if is_publication:
                bundle = candidate_gallery.get("publication_bundle")
                rows = candidate_gallery.get("episodes")
                if (
                    not isinstance(bundle, dict)
                    or bundle.get("schema_version")
                    != RANKED_GRASP_PUBLICATION_SCHEMA
                    or bundle.get("source_actions_modified") is not False
                    or bundle.get("physical_authority") is not False
                    or not isinstance(rows, list)
                    or len(rows) != 7
                    or bundle.get("action_array_sha256_by_rank")
                    != [
                        row.get("action_array_sha256")
                        for row in rows
                        if isinstance(row, dict)
                    ]
                    or any(
                        not isinstance(row, dict)
                        or not _is_sha256(row.get("action_array_sha256"))
                        or not _is_sha256(row.get("episode_probe_receipt_sha256"))
                        or not isinstance(row.get("state_trace"), dict)
                        or not _is_sha256(
                            row["state_trace"].get("state_trace_sha256")
                        )
                        for row in rows
                    )
                ):
                    continue
            gallery = candidate_gallery
            gallery_path = candidate
            publication_bundle = is_publication
            break
    if not gallery:
        return []

    allowed_asset_root = gallery_path.parent.resolve()
    static_root = (repo_root / "src/sim2claw/studio_web").resolve()
    task_id = str(gallery.get("task_id") or "pawn_bg_ranked_grasp_v3")
    proof_class = str(
        gallery.get("proof_class") or "retained_action_frozen_simulation_replay"
    )
    episodes: list[dict[str, Any]] = []
    for row in gallery.get("episodes", []):
        if not isinstance(row, dict):
            continue
        artifact = row.get("state_trace")
        metrics = row.get("metrics")
        if not isinstance(artifact, dict) or not isinstance(metrics, dict):
            continue
        trace_value = Path(str(artifact.get("state_trace_path") or ""))
        manifest_value = Path(str(artifact.get("scene_manifest_path") or ""))
        if trace_value.is_absolute() or manifest_value.is_absolute():
            continue
        trace_path = (repo_root / trace_value).resolve()
        manifest_path = (repo_root / manifest_value).resolve()
        if (
            not trace_path.is_relative_to(allowed_asset_root)
            or not manifest_path.is_relative_to(allowed_asset_root)
            or not trace_path.is_file()
            or not manifest_path.is_file()
        ):
            continue
        if publication_bundle:
            trace_url = f"/{trace_path.relative_to(static_root).as_posix()}"
            scene_url = f"/{manifest_path.relative_to(static_root).as_posix()}"
        else:
            trace_url = media_url(trace_path, repo_root)
            scene_url = media_url(manifest_path, repo_root)
        rank = int(row.get("rank") or len(episodes) + 1)
        strict_success = bool(row.get("task_consequence_success"))
        lift_and_transport = bool(row.get("lift_and_transport"))
        lifted = bool(row.get("piece_lifted"))
        outcome = str(row.get("relative_success_label") or "Partial replay")
        status = "passed" if strict_success else "partial" if lifted else "near-miss"
        episodes.append(
            {
                "id": f"{task_id}:rank-{rank:02d}",
                "task_id": task_id,
                "title": f"Rank {rank:02d} · {row.get('move_label', 'Pawn move')}",
                "subtitle": str(row.get("relative_success_summary") or outcome),
                "sequence": rank,
                "rank": rank,
                "status": status,
                "evaluator_verdict": "passed" if strict_success else "failed",
                "terminal_outcome": (
                    "strict_task_success"
                    if strict_success
                    else "lift_and_transport"
                    if lift_and_transport
                    else "piece_lifted"
                    if lifted
                    else "qualified_bilateral_contact_near_miss"
                ),
                "proof_class": proof_class,
                "proof_label": _proof_label(proof_class),
                "physical_authority": False,
                "frame_count": int(artifact.get("frame_count") or 0),
                "fps": float(artifact.get("fps") or 0),
                "duration_seconds": float(artifact.get("duration_seconds") or 0),
                "recorded_at": gallery.get("created_at")
                or _iso_timestamp(gallery_path),
                "media": {"kind": "none"},
                "camera": "interactive 3D",
                "inspection": {
                    "kind": "threejs_state_trace",
                    "trace_url": trace_url,
                    "scene_url": scene_url,
                    "frame_count": int(artifact.get("frame_count") or 0),
                    "fps": float(artifact.get("fps") or 0),
                    "duration_seconds": float(artifact.get("duration_seconds") or 0),
                    "physics_authority": "mujoco",
                    "renderer_authority": "inspection_only",
                },
                "metrics": [
                    _metric("Outcome", outcome, tone="good" if lifted else "neutral"),
                    _metric(
                        "Peak rise",
                        round(
                            float(metrics.get("maximum_piece_rise_m", 0)) * 1000,
                            1,
                        ),
                        unit="mm",
                        tone="good" if lifted else "neutral",
                    ),
                    _metric(
                        "Transport",
                        round(
                            float(
                                metrics.get(
                                    "maximum_transport_progress_after_lift", 0
                                )
                            )
                            * 100,
                            1,
                        ),
                        unit="%",
                        tone="good" if lift_and_transport else "neutral",
                    ),
                    _metric(
                        "Retention",
                        round(
                            float(
                                metrics.get(
                                    "maximum_bilateral_lift_retention_seconds",
                                    0,
                                )
                            )
                            * 1000,
                            1,
                        ),
                        unit="ms",
                    ),
                    _metric(
                        "Slip",
                        round(
                            float(metrics.get("maximum_post_grasp_slip_m", 0))
                            * 1000,
                            1,
                        ),
                        unit="mm",
                    ),
                    _metric(
                        "Final target gap",
                        round(
                            float(metrics.get("final_target_distance_m", 0)) * 1000,
                            1,
                        ),
                        unit="mm",
                    ),
                    _metric(
                        "Joint RMS",
                        round(float(metrics.get("joint_rms_degrees", 0)), 3),
                        unit="deg",
                    ),
                    _metric(
                        "EE RMS",
                        round(float(metrics.get("ee_rms_m", 0)) * 1000, 2),
                        unit="mm",
                    ),
                ],
                "phases": row.get("phase_segments", []),
                "case_id": str(row.get("folder_label") or "pawn_move"),
                "source_recording_id": str(row.get("recording_id") or ""),
                "notes": (
                    f"{gallery.get('claim_boundary', '')} "
                    "The action array is byte-identical to the source teleoperation trace."
                ),
                "action_array_sha256": row.get("action_array_sha256"),
                "evidence_receipt": (
                    {
                        "path": row.get("episode_probe_receipt_path"),
                        "sha256": row.get("episode_probe_receipt_sha256"),
                    }
                    if publication_bundle
                    else None
                ),
                "state_trace_sha256": artifact.get("state_trace_sha256"),
                "relative_success_tier": row.get("relative_success_tier"),
                "gallery_source": (
                    "tracked_publication_bundle"
                    if publication_bundle
                    else "generated_output"
                ),
            }
        )
    if _include_generated_alternates:
        selected_task_id = str(gallery.get("task_id") or "pawn_bg_ranked_grasp_v3")
        for alternate_path in sorted(
            (repo_root / "outputs").glob(
                "pawn_bg_ranked_grasp_gallery_*/gallery_manifest.json"
            )
        ):
            if alternate_path.resolve() == gallery_path.resolve():
                continue
            alternate = _read_json(alternate_path)
            if (
                alternate.get("schema_version")
                != "sim2claw.pawn_bg_ranked_grasp_gallery.v1"
                or str(alternate.get("task_id") or "pawn_bg_ranked_grasp_v3")
                == selected_task_id
            ):
                continue
            episodes.extend(
                _ranked_grasp_episodes(
                    repo_root,
                    _gallery_override=(alternate_path, alternate),
                    _include_generated_alternates=False,
                )
            )
    return episodes


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
    ranked_by_recording: dict[str, dict[str, Any]] = {}
    duplicate_recordings: set[str] = set()
    for row in _ranked_grasp_episodes(
        repo_root,
        _include_generated_alternates=False,
    ):
        recording_id = str(row.get("source_recording_id") or "")
        evidence_receipt = row.get("evidence_receipt")
        if (
            not recording_id
            or row.get("gallery_source") != "tracked_publication_bundle"
            or not _is_sha256(row.get("action_array_sha256"))
            or not _is_sha256(row.get("state_trace_sha256"))
            or not isinstance(evidence_receipt, dict)
            or not evidence_receipt.get("path")
            or not _is_sha256(evidence_receipt.get("sha256"))
        ):
            continue
        if recording_id in ranked_by_recording:
            duplicate_recordings.add(recording_id)
            continue
        ranked_by_recording[recording_id] = row
    for recording_id in duplicate_recordings:
        ranked_by_recording.pop(recording_id, None)
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
        recording_id = str(receipt.get("recording_id") or sequence)
        ranked_replay = ranked_by_recording.get(recording_id)
        replay_receipt: dict[str, Any] = {}
        if mode == "physical_follower":
            replay_receipt = _read_json(receipt_path.parent / "sim_replay_receipt.json")
            if (
                replay_receipt.get("schema_version")
                != "sim2claw.physical_command_sim_replay.v1"
                or not _is_sha256(replay_receipt.get("action_array_sha256"))
            ):
                replay_receipt = {}
            if replay_receipt:
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
                inspection = (
                    dict(ranked_replay["inspection"])
                    if ranked_replay and ranked_replay.get("inspection")
                    else None
                )
        else:
            trace_path = receipt_path.parent / str(
                receipt.get("state_trace_path") or "state_trace.json"
            )
            inspection = (
                _inspection(trace_path, repo_root) if trace_path.is_file() else None
            )
        if mode == "simulation_follower" and inspection is None:
            continue
        source_proof_class = str(
            receipt.get("proof_class") or "simulation_teleoperation_source"
        )
        proof_class = (
            "physical_source_simulation_command_replay"
            if mode == "physical_follower"
            else source_proof_class
        )
        outcome = str(receipt.get("outcome_label") or "recorded")
        video_receipt = (
            receipt.get("overhead_video")
            if isinstance(receipt.get("overhead_video"), dict)
            else {}
        )
        video_start = float(
            video_receipt.get("action_start_video_offset_seconds")
            or video_receipt.get("teleoperation_start_video_offset_seconds")
            or 0
        )
        video_end = float(
            video_receipt.get("action_stop_video_offset_seconds")
            or video_receipt.get("teleoperation_stop_video_offset_seconds")
            or 0
        )
        duration = float(receipt.get("duration_seconds") or 0)
        if video_end > video_start:
            duration = video_end - video_start
        video_path = receipt_path.parent / "overhead_c922.mp4"
        media = (
            {
                "kind": "video",
                "url": media_url(video_path, repo_root),
                "window_start_seconds": video_start,
                "window_end_seconds": video_end,
                "display_rotation_degrees": int(
                    video_receipt.get("orientation_rotation_degrees") or 0
                ),
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
        action_sha256 = str(
            replay_receipt.get("action_array_sha256")
            or (ranked_replay or {}).get("action_array_sha256")
            or ""
        )
        physics_available = inspection is not None and _is_sha256(action_sha256)
        if not physics_available:
            inspection = None
            action_sha256 = ""
        source_square = str(receipt.get("source_square") or "—")
        destination_square = str(
            receipt.get("destination_square")
            or receipt.get("target_square_operator_metadata")
            or "—"
        )
        is_physical_library = (
            mode == "physical_follower"
            and receipt_path.is_relative_to(
                repo_root / "datasets" / "manipulation_source_recordings"
            )
        )
        if is_physical_library and metrics:
            metrics[-1]["label"] = "Operator label"
        task_id = (
            PHYSICAL_EPISODE_LIBRARY_TASK
            if is_physical_library
            else str(receipt.get("task_id") or "manipulation_source_recordings")
        )
        comparison = None
        if is_physical_library and media.get("kind") == "video":
            comparison = {
                "schema_version": COMPARISON_SCHEMA_VERSION,
                "timeline_alignment": "normalized_recorded_action_window",
                "real": {
                    "available": True,
                    "proof_class": source_proof_class,
                    "camera": "C922 overhead",
                    "source_pixels": True,
                },
                "visual_twin": {
                    "available": True,
                    "kind": "image_space_visual_projection",
                    "camera_alignment": "pixel_identical_source_view",
                    "source_pixels": True,
                    "physics_authority": "none",
                    "proof_class": "visual_only_same_camera_projection",
                    "notice": (
                        "Image-space visual mimic derived from the recorded camera "
                        "pixels. It does not simulate geometry, contact, or dynamics."
                    ),
                },
                "physics_replay": {
                    "available": physics_available,
                    "kind": "mujoco_action_frozen_state_trace"
                    if physics_available
                    else "missing",
                    "proof_class": (
                        "retained_action_frozen_simulation_replay"
                        if physics_available
                        else "unavailable"
                    ),
                    "action_array_sha256": action_sha256 or None,
                    "binding": (
                        {
                            "kind": (
                                "adjacent_sim_replay_receipt"
                                if replay_receipt
                                else "tracked_publication_recording_and_action"
                            ),
                            "recording_id": recording_id,
                            "action_array_sha256": action_sha256,
                            "evidence_receipt": (
                                {
                                    "path": (
                                        str(
                                            (
                                                receipt_path.parent
                                                / "sim_replay_receipt.json"
                                            ).relative_to(repo_root)
                                        )
                                    ),
                                    "sha256": hashlib.sha256(
                                        (
                                            receipt_path.parent
                                            / "sim_replay_receipt.json"
                                        ).read_bytes()
                                    ).hexdigest(),
                                }
                                if replay_receipt
                                else (ranked_replay or {}).get("evidence_receipt")
                            ),
                            "state_trace_sha256": (
                                replay_receipt.get("state_trace_sha256")
                                if replay_receipt
                                else (ranked_replay or {}).get(
                                    "state_trace_sha256"
                                )
                            ),
                        }
                        if physics_available
                        else None
                    ),
                    "notice": (
                        (
                            "A receipt binds this recording ID to the byte-identical "
                            "action array and retained MuJoCo state trace."
                        )
                        if physics_available
                        else (
                            "No receipt-bound action-frozen MuJoCo state trace is "
                            "available for this physical recording. Studio does "
                            "not synthesize one."
                        )
                    ),
                },
            }
        episodes.append(
            {
                "id": f"{task_id}:{recording_id}",
                "task_id": task_id,
                "title": (
                    "Physical episode"
                    if is_physical_library
                    else str(
                        receipt.get("label") or f"Teleop recording {sequence + 1}"
                    )
                ),
                "subtitle": (
                    f"{_title(str(receipt.get('piece_id', 'piece')))} · "
                    f"{source_square.upper()} → {destination_square.upper()} · "
                    f"{'physics replay paired' if physics_available else 'physics trace missing'}"
                ),
                "sequence": 30_000 + sequence,
                "status": (
                    "recorded"
                    if is_physical_library
                    else
                    "passed"
                    if outcome == "success"
                    else "failed"
                    if outcome == "failure"
                    else "recorded"
                ),
                "terminal_outcome": (
                    f"operator_label_{outcome}_unqualified"
                    if is_physical_library
                    else outcome
                ),
                "proof_class": (
                    source_proof_class if is_physical_library else proof_class
                ),
                "source_proof_class": source_proof_class,
                "proof_label": (
                    "Physical source · recorded, not admitted"
                    if is_physical_library
                    else _proof_label(proof_class)
                ),
                "physical_authority": False,
                "frame_count": (
                    inspection["frame_count"]
                    if inspection is not None
                    else receipt.get("sample_count")
                ),
                "fps": (
                    inspection["fps"]
                    if inspection is not None
                    else receipt.get("sample_hz")
                ),
                "duration_seconds": (
                    duration
                    or (
                        inspection["duration_seconds"]
                        if inspection is not None
                        else 0
                    )
                ),
                "recorded_at": _iso_timestamp(receipt_path),
                "media": media,
                "camera": "C922 overhead" if is_physical_library else "free_orbit",
                "metrics": metrics,
                "notes": (
                    (
                        f"{str(receipt.get('notes') or '').strip()} "
                        "The real recording, image-space visual twin, and MuJoCo "
                        "replay remain separate proof classes."
                    ).strip()
                    if is_physical_library
                    else str(receipt.get("notes") or "").strip()
                ),
                "phases": [{"name": "Teleoperation", "start": 0.0, "end": 1.0}],
                "case_id": (
                    f"{source_square.lower()}_to_{destination_square.lower()}_physical"
                    if is_physical_library
                    else "simulation_teleoperation_source"
                ),
                "source_recording_id": recording_id,
                "action_array_sha256": action_sha256 or None,
                "comparison": comparison,
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
        _ranked_grasp_episodes(repo_root)
        + _dataset_episodes(repo_root, contracts)
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
        PHYSICAL_EPISODE_LIBRARY_TASK: "Physical pawn episodes",
        "scripted_grasp_probe": "Scripted grasp probe",
        "pawn_bg_ranked_grasp_v3": "Top pawn grasp replays",
        "pawn_bg_rubber_sliding2_sensitivity": "Rubber friction sensitivity",
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
                "role": (
                    "Recorded evidence"
                    if task_id == PHYSICAL_EPISODE_LIBRARY_TASK
                    else _task_role(contract)
                    if contract
                    else "Simulation probe"
                ),
                "description": (
                    "Seven consequence-ranked, action-frozen V3 simulator replays; partial outcomes only, with zero strict task successes."
                    if task_id == "pawn_bg_ranked_grasp_v3"
                    else (
                        "All retained C922 physical recordings with a same-camera "
                        "visual-only twin and every currently available "
                        "action-frozen MuJoCo replay."
                    )
                    if task_id == PHYSICAL_EPISODE_LIBRARY_TASK
                    else "Frozen sliding-friction 2.0 sensitivity replays; diagnostic only because the all-episode EE RMS guard fails."
                    if task_id == "pawn_bg_rubber_sliding2_sensitivity"
                    else
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

"""Rank and export the most informative action-frozen pawn grasp replays."""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT
from .pawn_bg_grasp_coordinate_descent import run_grasp_episode_probe


SCHEMA = "sim2claw.pawn_bg_ranked_grasp_gallery.v1"
DEFAULT_SOURCE_RECEIPT = (
    REPO_ROOT
    / "outputs"
    / "pawn_bg_grasp_group_probes"
    / "frozen_v3_timestep045_all.json"
)
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "outputs" / "pawn_bg_ranked_grasp_gallery_v1"
DEFAULT_PUBLICATION_ROOT = (
    REPO_ROOT
    / "src"
    / "sim2claw"
    / "studio_web"
    / "publication"
    / "pawn_bg_ranked_grasp_v1"
)
PUBLICATION_URL_PREFIX = "/publication/pawn_bg_ranked_grasp_v1"
PUBLICATION_SCHEMA = "sim2claw.pawn_bg_ranked_grasp_publication_bundle.v1"


class GraspGalleryError(RuntimeError):
    """The frozen replay inputs cannot support a ranked inspection gallery."""


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GraspGalleryError(f"cannot read gallery input {path}: {error}") from error
    if not isinstance(value, dict):
        raise GraspGalleryError(f"gallery input is not an object: {path}")
    return value


def _success_tier(row: dict[str, Any]) -> tuple[int, str]:
    if bool(row["task_consequence_success"]):
        return 6, "Strict task success"
    if bool(row["lift_and_transport"]):
        return 5, "Lift + transport"
    if bool(row["piece_lifted"]) and bool(row["bilateral_lift_retention"]):
        return 4, "Lift with retained grasp"
    if bool(row["piece_lifted"]):
        return 3, "Lift"
    if bool(row["qualified_bilateral_contact_observed"]):
        return 2, "Qualified pinch near miss"
    if bool(row["selected_piece_contact_observed"]):
        return 1, "Touch only"
    return 0, "No target contact"


def episode_rank_key(row: dict[str, Any]) -> tuple[float, ...]:
    """Transparent consequence-first ordering; larger tuple is better."""

    tier, _label = _success_tier(row)
    return (
        float(tier),
        float(row["maximum_transport_progress_after_lift"]),
        float(row["maximum_bilateral_lift_retention_seconds"]),
        float(row["maximum_piece_rise_m"]),
        -float(row["maximum_post_grasp_slip_m"]),
        -float(row["final_target_distance_m"]),
        -float(row["maximum_other_piece_displacement_m"]),
    )


def _phase_segments(trace_path: Path) -> list[dict[str, Any]]:
    trace = _read(trace_path)
    frames = trace.get("frames")
    if not isinstance(frames, list) or not frames:
        return []
    total = max(1, len(frames) - 1)
    segments: list[dict[str, Any]] = []
    start = 0
    current = str(frames[0].get("phase") or "replay")
    for index, frame in enumerate(frames[1:], start=1):
        phase = str(frame.get("phase") or "replay")
        if phase == current:
            continue
        segments.append(
            {
                "name": current.replace("_", " ").title(),
                "start": start / total,
                "end": index / total,
            }
        )
        start = index
        current = phase
    segments.append(
        {
            "name": current.replace("_", " ").title(),
            "start": start / total,
            "end": 1.0,
        }
    )
    return segments


def _move_label(folder_label: str) -> str:
    source, separator, destination = folder_label.partition("-to-")
    if not separator:
        return folder_label.upper()
    return f"{source.upper()} → {destination.upper()}"


def _outcome_summary(row: dict[str, Any]) -> str:
    _tier, label = _success_tier(row)
    progress = 100.0 * float(row["maximum_transport_progress_after_lift"])
    rise_mm = 1000.0 * float(row["maximum_piece_rise_m"])
    if row["lift_and_transport"]:
        return f"{label} · {progress:.0f}% targetward progress"
    if row["piece_lifted"]:
        return f"{label} · {rise_mm:.0f} mm peak rise · {progress:.0f}% targetward"
    return f"{label} · {rise_mm:.0f} mm peak rise"


def _atomic_write_compact_json(path: Path, value: dict[str, Any]) -> None:
    """Write browser assets compactly while retaining deterministic key order."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _rounded(value: Any, digits: int) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise GraspGalleryError("state trace contains a non-numeric value") from error
    if not math.isfinite(number):
        raise GraspGalleryError("state trace contains a non-finite value")
    rounded = round(number, digits)
    return 0.0 if rounded == 0 else rounded


def _sample_frame_indices(
    frames: list[dict[str, Any]],
    *,
    source_fps: float,
    publication_fps: float,
) -> list[int]:
    """Select a nominal-rate replay while retaining exact phase boundaries."""

    stride = source_fps / publication_fps
    selected = {
        min(len(frames) - 1, round(sample * stride))
        for sample in range(math.ceil((len(frames) - 1) / stride) + 1)
    }
    selected.update({0, len(frames) - 1})
    for index in range(1, len(frames)):
        if frames[index].get("phase") != frames[index - 1].get("phase"):
            selected.update({index - 1, index})
    return sorted(selected)


def _compact_trace(
    source_trace: dict[str, Any],
    *,
    source_trace_sha256: str,
    publication_fps: float,
) -> dict[str, Any]:
    if source_trace.get("schema_version") != "sim2claw.mujoco_body_state_trace.v1":
        raise GraspGalleryError("gallery trace has an unsupported schema")
    frames = source_trace.get("frames")
    body_names = source_trace.get("body_names")
    if not isinstance(frames, list) or not frames or not isinstance(body_names, list):
        raise GraspGalleryError("gallery trace has no replayable body states")
    if not all(isinstance(frame, dict) for frame in frames):
        raise GraspGalleryError("gallery trace frame is not an object")
    source_fps = float(source_trace.get("fps") or 0)
    if source_fps <= 0 or publication_fps <= 0 or publication_fps > source_fps:
        raise GraspGalleryError("publication FPS must be within (0, source FPS]")
    indices = _sample_frame_indices(
        frames,
        source_fps=source_fps,
        publication_fps=publication_fps,
    )
    compact_frames: list[dict[str, Any]] = []
    expected_positions = 3 * len(body_names)
    expected_quaternions = 4 * len(body_names)
    for index in indices:
        frame = frames[index]
        positions = frame.get("p")
        quaternions = frame.get("q")
        contacts = frame.get("c") or []
        if (
            not isinstance(positions, list)
            or len(positions) != expected_positions
            or not isinstance(quaternions, list)
            or len(quaternions) != expected_quaternions
            or not isinstance(contacts, list)
        ):
            raise GraspGalleryError("gallery trace frame dimensions are invalid")
        compact_contacts: list[list[Any]] = []
        for contact in contacts:
            if not isinstance(contact, list) or len(contact) < 5:
                raise GraspGalleryError("gallery trace contact is invalid")
            compact_contacts.append(
                [
                    int(contact[0]),
                    int(contact[1]),
                    *[_rounded(value, 6) for value in contact[2:]],
                ]
            )
        compact_frames.append(
            {
                "c": compact_contacts,
                "p": [_rounded(value, 6) for value in positions],
                "phase": str(frame.get("phase") or "replay"),
                "q": [_rounded(value, 7) for value in quaternions],
                "t": _rounded(frame.get("t"), 6),
            }
        )
    compact = {
        key: value
        for key, value in source_trace.items()
        if key not in {"fps", "frame_count", "frames", "scene"}
    }
    scene = dict(source_trace.get("scene") or {})
    scene["manifest_url"] = f"{PUBLICATION_URL_PREFIX}/scene_manifest.json"
    compact.update(
        {
            "derivative": {
                "schema_version": PUBLICATION_SCHEMA,
                "source_state_trace_sha256": source_trace_sha256,
                "source_frame_count": len(frames),
                "source_fps": source_fps,
                "sampling": "nominal_rate_plus_phase_boundaries",
                "position_precision_decimal_places": 6,
                "quaternion_precision_decimal_places": 7,
                "source_actions_modified": False,
            },
            "fps": publication_fps,
            "frame_count": len(compact_frames),
            "frames": compact_frames,
            "scene": scene,
        }
    )
    return compact


def export_ranked_grasp_publication_bundle(
    *,
    source_repository_root: Path = REPO_ROOT,
    source_gallery_root: Path = DEFAULT_OUTPUT_ROOT,
    publication_root: Path = DEFAULT_PUBLICATION_ROOT,
    publication_fps: float = 10.0,
    expected_episode_count: int = 7,
) -> dict[str, Any]:
    """Export a tracked, phone-sized derivative of a frozen ranked gallery."""

    source_gallery_path = source_gallery_root / "gallery_manifest.json"
    source_gallery = _read(source_gallery_path)
    if source_gallery.get("schema_version") != SCHEMA:
        raise GraspGalleryError("publication source is not a ranked grasp gallery")
    episodes = source_gallery.get("episodes")
    if not isinstance(episodes, list) or len(episodes) != expected_episode_count:
        raise GraspGalleryError(
            f"publication source must contain exactly {expected_episode_count} episodes"
        )
    source_manifest_digest = str(source_gallery.get("manifest_digest") or "")
    unsigned_source = {
        key: value for key, value in source_gallery.items() if key != "manifest_digest"
    }
    if canonical_digest(unsigned_source) != source_manifest_digest:
        raise GraspGalleryError("publication source gallery digest does not verify")
    authority = source_gallery.get("authority")
    if not isinstance(authority, dict) or authority.get("source_actions_modified") is not False:
        raise GraspGalleryError("publication source does not freeze the action arrays")

    source_scene_hashes: set[str] = set()
    source_scene_revisions: set[str] = set()
    source_scene: dict[str, Any] | None = None
    exported: list[dict[str, Any]] = []
    action_hashes: list[str] = []
    for row in episodes:
        if not isinstance(row, dict):
            raise GraspGalleryError("publication source episode is not an object")
        artifact = row.get("state_trace")
        if not isinstance(artifact, dict):
            raise GraspGalleryError("publication source episode has no trace artifact")
        action_hash = str(row.get("action_array_sha256") or "")
        if len(action_hash) != 64:
            raise GraspGalleryError("publication source episode has no action hash")
        action_hashes.append(action_hash)
        trace_path = source_repository_root / str(
            artifact.get("state_trace_path") or ""
        )
        scene_path = source_repository_root / str(
            artifact.get("scene_manifest_path") or ""
        )
        trace_hash = sha256_file(trace_path)
        scene_hash = sha256_file(scene_path)
        if trace_hash != artifact.get("state_trace_sha256"):
            raise GraspGalleryError("publication source trace hash does not verify")
        if scene_hash != artifact.get("scene_manifest_sha256"):
            raise GraspGalleryError("publication source scene hash does not verify")
        trace = _read(trace_path)
        scene = _read(scene_path)
        scene_revision = str(scene.get("revision_sha256") or "")
        if trace.get("scene", {}).get("manifest_revision_sha256") != scene_revision:
            raise GraspGalleryError("publication trace and scene revisions differ")
        if trace.get("proof_class") != source_gallery.get("proof_class"):
            raise GraspGalleryError("publication trace proof class differs from gallery")
        source_scene_hashes.add(scene_hash)
        source_scene_revisions.add(scene_revision)
        source_scene = scene

        compact_trace = _compact_trace(
            trace,
            source_trace_sha256=trace_hash,
            publication_fps=publication_fps,
        )
        rank = int(row.get("rank") or 0)
        recording_id = str(row.get("recording_id") or "")
        trace_name = f"rank-{rank:02d}-{recording_id}.json"
        published_trace_path = publication_root / "episodes" / trace_name
        _atomic_write_compact_json(published_trace_path, compact_trace)
        published_artifact = {
            **artifact,
            "state_trace_path": str(
                published_trace_path.relative_to(source_repository_root)
            ),
            "state_trace_sha256": sha256_file(published_trace_path),
            "source_state_trace_path": str(
                trace_path.relative_to(source_repository_root)
            ),
            "source_state_trace_sha256": trace_hash,
            "source_frame_count": int(artifact.get("frame_count") or 0),
            "source_fps": float(artifact.get("fps") or 0),
            "scene_manifest_path": str(
                (publication_root / "scene_manifest.json").relative_to(
                    source_repository_root
                )
            ),
            "source_scene_manifest_path": str(
                scene_path.relative_to(source_repository_root)
            ),
            "source_scene_manifest_sha256": scene_hash,
            "frame_count": compact_trace["frame_count"],
            "fps": compact_trace["fps"],
            "duration_seconds": compact_trace["duration_seconds"],
            "derivative_schema_version": PUBLICATION_SCHEMA,
        }
        exported.append({**row, "state_trace": published_artifact})

    if len(source_scene_hashes) != 1 or len(source_scene_revisions) != 1 or source_scene is None:
        raise GraspGalleryError("ranked episodes do not share one frozen scene")
    published_scene_path = publication_root / "scene_manifest.json"
    _atomic_write_compact_json(published_scene_path, source_scene)
    published_scene_hash = sha256_file(published_scene_path)
    for row in exported:
        row["state_trace"]["scene_manifest_sha256"] = published_scene_hash

    publication = {
        **source_gallery,
        "episodes": exported,
        "publication_bundle": {
            "schema_version": PUBLICATION_SCHEMA,
            "source_gallery_manifest_path": str(
                source_gallery_path.relative_to(source_repository_root)
            ),
            "source_gallery_manifest_sha256": sha256_file(source_gallery_path),
            "source_gallery_manifest_digest": source_manifest_digest,
            "source_scene_manifest_sha256": next(iter(source_scene_hashes)),
            "scene_manifest_revision_sha256": next(iter(source_scene_revisions)),
            "published_scene_manifest_sha256": published_scene_hash,
            "publication_fps": publication_fps,
            "action_array_sha256_by_rank": action_hashes,
            "source_actions_modified": False,
            "physical_authority": False,
        },
    }
    publication.pop("manifest_digest", None)
    publication["manifest_digest"] = canonical_digest(publication)
    _atomic_write_compact_json(publication_root / "gallery_manifest.json", publication)
    return publication


def build_ranked_grasp_gallery(
    *,
    source_repository_root: Path = REPO_ROOT,
    source_receipt_path: Path = DEFAULT_SOURCE_RECEIPT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    maximum_episode_count: int = 7,
    task_id: str = "pawn_bg_ranked_grasp_v3",
    title: str = "Top action-frozen pawn grasp replays",
    claim_boundary: str | None = None,
) -> dict[str, Any]:
    if maximum_episode_count < 1 or maximum_episode_count > 11:
        raise GraspGalleryError("maximum episode count must remain within [1, 11]")
    if not task_id.strip() or not title.strip():
        raise GraspGalleryError("gallery task identity and title are required")
    source = _read(source_receipt_path)
    rows = source.get("episodes")
    parameters = source.get("parameters")
    if not isinstance(rows, list) or len(rows) != 11 or not isinstance(parameters, dict):
        raise GraspGalleryError("frozen V3 receipt inventory or parameters are invalid")
    if not all(
        isinstance(row, dict) and bool(row.get("action_byte_identical")) for row in rows
    ):
        raise GraspGalleryError("gallery source contains a non-identical action replay")

    ordered = sorted(rows, key=episode_rank_key, reverse=True)
    selected = [row for row in ordered if _success_tier(row)[0] >= 2][
        :maximum_episode_count
    ]
    if len(selected) < min(4, maximum_episode_count):
        raise GraspGalleryError("too few meaningful episodes remain after filtering")

    exported: list[dict[str, Any]] = []
    for rank, source_row in enumerate(selected, start=1):
        recording_id = str(source_row["recording_id"])
        episode_root = output_root / "episodes" / f"rank-{rank:02d}-{recording_id}"
        probe = run_grasp_episode_probe(
            source_repository_root=source_repository_root,
            recording_id=recording_id,
            parameters=parameters,
            state_trace_output_directory=episode_root,
        )
        replay = probe["episode"]
        for key in (
            "action_array_sha256",
            "piece_lifted",
            "lift_and_transport",
            "task_consequence_success",
            "parameter_digest",
        ):
            if replay[key] != source_row[key]:
                raise GraspGalleryError(
                    f"regenerated episode differs from frozen V3 receipt: {recording_id} {key}"
                )
        probe_path = episode_root / "episode_probe_receipt.json"
        atomic_write_json(probe_path, probe)
        artifact = replay.get("state_trace_artifact")
        if not isinstance(artifact, dict):
            raise GraspGalleryError(f"episode state trace was not emitted: {recording_id}")
        trace_path = REPO_ROOT / str(artifact["state_trace_path"])
        tier, tier_label = _success_tier(replay)
        exported.append(
            {
                "rank": rank,
                "recording_id": recording_id,
                "folder_label": str(replay["folder_label"]),
                "move_label": _move_label(str(replay["folder_label"])),
                "relative_success_tier": tier,
                "relative_success_label": tier_label,
                "relative_success_summary": _outcome_summary(replay),
                "piece_lifted": bool(replay["piece_lifted"]),
                "lift_and_transport": bool(replay["lift_and_transport"]),
                "task_consequence_success": bool(replay["task_consequence_success"]),
                "qualified_bilateral_contact": bool(
                    replay["qualified_bilateral_contact_observed"]
                ),
                "metrics": {
                    "maximum_piece_rise_m": float(replay["maximum_piece_rise_m"]),
                    "maximum_transport_progress_after_lift": float(
                        replay["maximum_transport_progress_after_lift"]
                    ),
                    "maximum_bilateral_lift_retention_seconds": float(
                        replay["maximum_bilateral_lift_retention_seconds"]
                    ),
                    "maximum_post_grasp_slip_m": float(
                        replay["maximum_post_grasp_slip_m"]
                    ),
                    "final_target_distance_m": float(
                        replay["final_target_distance_m"]
                    ),
                    "maximum_other_piece_displacement_m": float(
                        replay["maximum_other_piece_displacement_m"]
                    ),
                    "joint_rms_degrees": float(
                        replay["trace_metrics"]["overall_joint_rms_degrees"]
                    ),
                    "ee_rms_m": float(replay["trace_metrics"]["ee_rms_m"]),
                },
                "action_array_sha256": str(replay["action_array_sha256"]),
                "parameter_digest": str(replay["parameter_digest"]),
                "state_trace": artifact,
                "phase_segments": _phase_segments(trace_path),
                "episode_probe_receipt_path": str(probe_path.relative_to(REPO_ROOT)),
                "episode_probe_receipt_sha256": sha256_file(probe_path),
            }
        )

    excluded = [
        {
            "recording_id": str(row["recording_id"]),
            "folder_label": str(row["folder_label"]),
            "relative_success_label": _success_tier(row)[1],
        }
        for row in ordered
        if row not in selected
    ]
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "task_id": task_id,
        "proof_class": "retained_action_frozen_simulation_replay",
        "source_receipt": {
            "path": str(source_receipt_path.relative_to(REPO_ROOT)),
            "sha256": sha256_file(source_receipt_path),
            "parameter_digest": str(source["parameter_digest"]),
        },
        "ranking": {
            "method": "transparent_lexicographic_consequence_order",
            "coordinates": [
                "strict task success",
                "lift and transport",
                "lift with retained bilateral grasp",
                "qualified bilateral contact",
                "targetward progress after lift",
                "retention duration",
                "peak rise",
                "lower post-grasp slip",
                "lower final target distance",
                "lower collateral displacement",
            ],
            "selected_episode_count": len(exported),
            "excluded_episode_count": len(excluded),
            "selection_rule": (
                "Keep the seven strongest episodes at qualified bilateral contact or better; "
                "omit the four weakest touch-only or lower-ranked near misses."
            ),
        },
        "episodes": exported,
        "excluded_episodes": excluded,
        "authority": {
            "browser_renderer": "inspection_only",
            "physics_source": "mujoco_state_trace",
            "source_actions_modified": False,
            "physical_authority": False,
            "simulator_composite_promoted": False,
            "policy_success_claim": False,
        },
        "claim_boundary": claim_boundary
        or (
            "The gallery orders retained V3 simulator replays for visual diagnosis. "
            "Partial lift or transport is not strict task success or physical transfer."
        ),
    }
    manifest["manifest_digest"] = canonical_digest(manifest)
    atomic_write_json(output_root / "gallery_manifest.json", manifest)
    return manifest


__all__ = [
    "DEFAULT_OUTPUT_ROOT",
    "DEFAULT_PUBLICATION_ROOT",
    "DEFAULT_SOURCE_RECEIPT",
    "GraspGalleryError",
    "build_ranked_grasp_gallery",
    "episode_rank_key",
    "export_ranked_grasp_publication_bundle",
]

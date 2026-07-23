"""Verified, read-only adapters for private Studio release assets."""

from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable


IPHONE_3DGS_MANIFEST = Path(
    "docs/reference/IPHONE_VIDEO_3DGS_RELEASE_20260719.json"
)
IPHONE_3DGS_RELEASE_ROOT = Path(
    "artifacts/private/releases/img5349-3dgs-20260719"
)
PHYSICAL_REPLAY_MANIFEST = Path(
    "docs/reference/PHYSICAL_REPLAY_RELEASE_20260719.json"
)
PHYSICAL_REPLAY_RELEASE_ROOT = Path(
    "artifacts/private/releases/physical-replay-evidence-20260719"
)
STUDIO_INTEGRATION_RECEIPT = "studio-integration-receipt.json"
PRIVATE_MEDIA_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".mp4", ".webm", ".ply"})
STUDIO_BROWSER_DERIVATIVE_KIND = "studio_browser_derivative"
DERIVATIVE_RECEIPT_FIELDS = (
    "name",
    "source_name",
    "source_sha256",
    "operation",
    "size_bytes",
    "sha256",
)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


@lru_cache(maxsize=128)
def _verified_digest(
    path_value: str,
    expected_sha256: str,
    expected_size: int,
    mtime_ns: int,
    ctime_ns: int,
) -> bool:
    # Both timestamps are cache keys. ctime prevents a same-size write with a
    # restored mtime from reusing an earlier digest result.
    del mtime_ns, ctime_ns
    path = Path(path_value)
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError:
        return False
    return path.stat().st_size == expected_size and digest.hexdigest() == expected_sha256


def _safe_release_name(value: object) -> str | None:
    """Accept one literal filename, never a path supplied by a receipt."""

    name = str(value or "")
    if (
        not name
        or name in {".", ".."}
        or "\x00" in name
        or "/" in name
        or "\\" in name
        or Path(name).is_absolute()
        or Path(name).name != name
    ):
        return None
    return name


def _release_asset_path(release_root: Path, name: object) -> Path | None:
    safe_name = _safe_release_name(name)
    if safe_name is None:
        return None
    try:
        root = release_root.resolve()
        candidate = release_root / safe_name
        if candidate.is_symlink():
            return None
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None
    if resolved.parent != root or not resolved.is_relative_to(root):
        return None
    return resolved


def verified_release_asset(
    path: Path,
    spec: dict[str, Any],
    *,
    release_root: Path | None = None,
) -> bool:
    """Return true only when a local asset matches its tracked immutable index."""

    if release_root is not None:
        resolved = _release_asset_path(release_root, path.name)
        if resolved is None:
            return False
        try:
            if path.absolute() != release_root.absolute() / path.name:
                return False
        except OSError:
            return False
        path = resolved
    elif path.is_symlink():
        return False
    try:
        stat = path.stat()
        expected_size = int(spec.get("size_bytes") or 0)
        expected_sha256 = str(spec.get("sha256") or "")
    except (OSError, TypeError, ValueError):
        return False
    if not path.is_file() or stat.st_size != expected_size or len(expected_sha256) != 64:
        return False
    return _verified_digest(
        str(path.resolve()),
        expected_sha256,
        expected_size,
        stat.st_mtime_ns,
        stat.st_ctime_ns,
    )


def _asset_specs(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        name: row
        for row in manifest.get("assets", [])
        if isinstance(row, dict)
        and (name := _safe_release_name(row.get("name"))) is not None
    }


def _tracked_derivative_specs(
    manifest: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    return {
        name: spec
        for name, spec in _asset_specs(manifest).items()
        if spec.get("kind") == STUDIO_BROWSER_DERIVATIVE_KIND
    }


def build_calibration_assets(
    repo_root: Path,
    media_url: Callable[[Path, Path], str],
) -> list[dict[str, Any]]:
    manifest_path = repo_root / IPHONE_3DGS_MANIFEST
    manifest = _read_json(manifest_path)
    if manifest.get("schema_version") != "sim2claw.private_3dgs_release_manifest.v1":
        return []

    release_root = repo_root / IPHONE_3DGS_RELEASE_ROOT
    specs = _asset_specs(manifest)
    resolved: dict[str, Path] = {}
    for name, spec in specs.items():
        candidate = release_root / name
        if verified_release_asset(candidate, spec, release_root=release_root):
            resolved[name] = candidate.resolve()

    model_name = "IMG_5349-primary-real-splat.ply"
    preview_name = "IMG_5349-preview.png"
    orbit_name = "IMG_5349-orbit.mp4"
    model_spec = specs.get(model_name, {})
    model = resolved.get(model_name)
    preview = resolved.get(preview_name)
    orbit = resolved.get(orbit_name)
    ready = model is not None
    source = manifest.get("source", {})
    authority = manifest.get("authority", {})
    return [
        {
            "id": "robo_scanner_img5349_3dgs",
            "title": "IMG_5349 workcell splat",
            "subtitle": "Robo Scanner · iPhone video · interactive 3DGS",
            "status": "ready" if ready else "asset_missing",
            "proof_class": "monocular_video_relative_scale_3dgs",
            "source_name": source.get("name", "IMG_5349.MOV"),
            "source_sha256": source.get("sha256"),
            "release_tag": manifest.get("release_tag"),
            "renderer": "Spark 2.1.0 · WebGL2 · local only",
            "model": (
                {
                    "url": media_url(model, repo_root),
                    "name": model_name,
                    "size_bytes": model_spec.get("size_bytes"),
                    "sha256": model_spec.get("sha256"),
                    "splat_count": model_spec.get("splat_count"),
                    "spherical_harmonics_degree": model_spec.get(
                        "spherical_harmonics_degree"
                    ),
                }
                if model is not None
                else None
            ),
            "preview": (
                {"url": media_url(preview, repo_root), "name": preview_name}
                if preview is not None
                else None
            ),
            "orbit": (
                {
                    "url": media_url(orbit, repo_root),
                    "name": orbit_name,
                    "duration_seconds": 22.0,
                }
                if orbit is not None
                else None
            ),
            "transform": {
                "translation": [0.0, 0.0, 0.0],
                "rotation_degrees": [0.0, 0.0, 0.0],
                "scale": 1.0,
                "scale_authority": "relative_visual_only",
            },
            "studio_view": manifest.get("studio_view", {}),
            "authority": authority,
            "proof_notice": (
                "Interactive visual calibration only. The splat has arbitrary global "
                "scale and cannot replace MuJoCo collision geometry or task coordinates."
            ),
        }
    ]


def _derived_browser_media(
    release_root: Path,
    verified_assets: dict[str, Path],
    manifest: dict[str, Any],
) -> dict[str, Path]:
    receipt = _read_json(release_root / STUDIO_INTEGRATION_RECEIPT)
    if receipt.get("schema_version") != "sim2claw.studio_private_release_import.v1":
        return {}
    if receipt.get("source_release_tag") != manifest.get("release_tag"):
        return {}
    tracked_assets = _asset_specs(manifest)
    derivative_specs = _tracked_derivative_specs(manifest)
    derived: dict[str, Path] = {}
    for row in receipt.get("derived_assets", []):
        if not isinstance(row, dict):
            continue
        name = _safe_release_name(row.get("name"))
        source_name = _safe_release_name(row.get("source_name"))
        if name is None or source_name is None:
            continue
        spec = derivative_specs.get(name)
        source_spec = tracked_assets.get(source_name)
        ffmpeg_identity = spec.get("ffmpeg_identity", {}) if spec else {}
        if (
            spec is None
            or source_spec is None
            or verified_assets.get(name) is None
            or verified_assets.get(source_name) is None
            or source_spec.get("sha256") != spec.get("source_sha256")
            or receipt.get("ffmpeg_sha256")
            != ffmpeg_identity.get("executable_sha256")
            or any(row.get(field) != spec.get(field) for field in DERIVATIVE_RECEIPT_FIELDS)
        ):
            continue
        derived[source_name] = verified_assets[name]
    return derived


def verified_private_media_paths(repo_root: Path) -> frozenset[Path]:
    """Return the exact hash-admitted private files that Studio may serve."""

    admitted: set[Path] = set()
    release_specs = (
        (
            IPHONE_3DGS_MANIFEST,
            IPHONE_3DGS_RELEASE_ROOT,
            "sim2claw.private_3dgs_release_manifest.v1",
        ),
        (
            PHYSICAL_REPLAY_MANIFEST,
            PHYSICAL_REPLAY_RELEASE_ROOT,
            "sim2claw.github_release_evidence_manifest.v1",
        ),
    )
    for manifest_relative, release_relative, schema_version in release_specs:
        manifest = _read_json(repo_root / manifest_relative)
        if manifest.get("schema_version") != schema_version:
            continue
        release_root = repo_root / release_relative
        for name, spec in _asset_specs(manifest).items():
            candidate = release_root / name
            if verified_release_asset(candidate, spec, release_root=release_root):
                resolved = candidate.resolve()
                if resolved.suffix.lower() in PRIVATE_MEDIA_SUFFIXES:
                    admitted.add(resolved)
    return frozenset(admitted)


def private_media_contracts(repo_root: Path) -> dict[str, dict[str, Any]]:
    """Return tracked private-media contracts keyed by repo-relative path."""

    contracts: dict[str, dict[str, Any]] = {}
    releases = (
        (
            IPHONE_3DGS_MANIFEST,
            IPHONE_3DGS_RELEASE_ROOT,
            "sim2claw.private_3dgs_release_manifest.v1",
        ),
        (
            PHYSICAL_REPLAY_MANIFEST,
            PHYSICAL_REPLAY_RELEASE_ROOT,
            "sim2claw.github_release_evidence_manifest.v1",
        ),
    )
    for manifest_relative, release_relative, schema_version in releases:
        manifest = _read_json(repo_root / manifest_relative)
        if manifest.get("schema_version") != schema_version:
            continue
        for name, spec in _asset_specs(manifest).items():
            if Path(name).suffix.lower() not in PRIVATE_MEDIA_SUFFIXES:
                continue
            relative = (release_relative / name).as_posix()
            contracts[relative] = spec
    return contracts


def verify_private_media_descriptor(repo_root: Path, relative: Path, fd: int) -> bool:
    """Hash and validate the already-open descriptor against tracked authority."""

    spec = private_media_contracts(repo_root).get(relative.as_posix())
    if spec is None:
        return False
    try:
        expected_size = int(spec.get("size_bytes") or 0)
        expected_sha256 = str(spec.get("sha256") or "")
        before = os.fstat(fd)
        if before.st_size != expected_size or len(expected_sha256) != 64:
            return False
        os.lseek(fd, 0, os.SEEK_SET)
        digest = hashlib.sha256()
        while block := os.read(fd, 1024 * 1024):
            digest.update(block)
        after = os.fstat(fd)
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        os.lseek(fd, 0, os.SEEK_SET)
    except (OSError, TypeError, ValueError):
        return False
    return identity_before == identity_after and digest.hexdigest() == expected_sha256


def build_physical_release_episodes(
    repo_root: Path,
    media_url: Callable[[Path, Path], str],
) -> list[dict[str, Any]]:
    manifest = _read_json(repo_root / PHYSICAL_REPLAY_MANIFEST)
    if manifest.get("schema_version") != "sim2claw.github_release_evidence_manifest.v1":
        return []

    release_root = repo_root / PHYSICAL_REPLAY_RELEASE_ROOT
    specs = _asset_specs(manifest)
    verified: dict[str, Path] = {}
    for name, spec in specs.items():
        candidate = release_root / name
        if verified_release_asset(candidate, spec, release_root=release_root):
            verified[name] = candidate.resolve()
    source_video = verified.get("source-episode-overhead-c922.mp4")
    if source_video is None:
        return []

    source = manifest.get("source_episode", {})
    replay = manifest.get("physical_replay", {})
    source_receipt_path = verified.get("source-episode-recording-receipt.json")
    source_receipt = _read_json(source_receipt_path) if source_receipt_path else {}
    derived = _derived_browser_media(release_root, verified, manifest)
    asset_by_role = {
        str(row.get("camera_role")): row
        for row in manifest.get("assets", [])
        if isinstance(row, dict) and row.get("camera_role")
    }

    source_start = float(
        asset_by_role.get("overhead_board", {}).get(
            "teleoperation_start_video_offset_seconds",
            source_receipt.get("overhead_video", {}).get(
                "teleoperation_start_video_offset_seconds", 0
            ),
        )
        or 0
    )
    source_end = float(
        asset_by_role.get("overhead_board", {}).get(
            "teleoperation_stop_video_offset_seconds",
            source_receipt.get("overhead_video", {}).get(
                "teleoperation_stop_video_offset_seconds", 0
            ),
        )
        or 0
    )
    feeds: list[dict[str, Any]] = [
        {
            "id": "source-overhead",
            "title": "Source overhead",
            "kind": "source_episode",
            "camera_role": "overhead_board",
            "camera": "C922 overhead",
            "rotation_degrees": 180,
            "url": media_url(source_video, repo_root),
            "window_start_seconds": source_start,
            "window_end_seconds": source_end,
            "note": "Physical leader-to-follower source recording.",
        }
    ]
    replay_names = {
        "overhead_board": "replay-overhead-c922.mkv",
        "side_arm": "replay-side-logitech.mkv",
        "wrist_gripper_upward": "replay-wrist-d405.mkv",
    }
    titles = {
        "overhead_board": "Replay overhead",
        "side_arm": "Replay side",
        "wrist_gripper_upward": "Replay wrist",
    }
    cameras = {
        "overhead_board": "C922 overhead",
        "side_arm": "Logitech side",
        "wrist_gripper_upward": "D405 wrist",
    }
    for role, source_name in replay_names.items():
        spec = asset_by_role.get(role, {})
        browser_path = derived.get(source_name)
        if browser_path is None or source_name not in verified:
            continue
        feeds.append(
            {
                "id": f"physical-{role.replace('_', '-')}",
                "title": titles[role],
                "kind": "physical_command_replay",
                "camera_role": role,
                "camera": cameras[role],
                "rotation_degrees": 180 if role == "overhead_board" else 0,
                "url": media_url(browser_path, repo_root),
                "window_start_seconds": float(
                    spec.get("replay_window_start_seconds") or 0
                ),
                "window_end_seconds": float(
                    spec.get("replay_window_end_seconds") or 0
                ),
                "note": str(spec.get("view_limitation") or "Guarded physical command replay."),
            }
        )

    recording_id = str(source.get("recording_id") or "physical-release")
    source_square = str(source.get("structured_source_square") or "e2")
    destination_square = str(source.get("structured_destination_square") or "e1")
    duration = max(0.0, source_end - source_start)
    sample_count = int(replay.get("completed_sample_count") or 0)
    exact_count = int(replay.get("exact_command_sample_count") or 0)
    operator_note = str(source.get("operator_note") or "none").rstrip(". ")
    return [
        {
            "id": f"chess_pick_place_act_state_v1:physical-release-{recording_id}",
            "task_id": "chess_pick_place_act_state_v1",
            "title": f"Physical source · {source_square.upper()} → {destination_square.upper()}",
            "subtitle": f"Source episode plus {max(0, len(feeds) - 1)} synchronized replay feeds",
            "sequence": 40_000,
            "status": "recorded",
            "terminal_outcome": "unqualified_physical_source",
            "proof_class": str(
                source.get("proof_class")
                or "physical_teleoperation_source_unqualified"
            ),
            "proof_label": "Physical source · recorded, not admitted",
            "physical_authority": False,
            "frame_count": source_receipt.get("sample_count"),
            "fps": source_receipt.get("sample_hz"),
            "duration_seconds": duration,
            "recorded_at": source_receipt.get("saved_at"),
            "media": {
                "kind": "video",
                "url": media_url(source_video, repo_root),
                "camera_role": "overhead_board",
                "rotation_degrees": 180,
                "window_start_seconds": source_start,
                "window_end_seconds": source_end,
            },
            "recording_feeds": feeds,
            "camera": "C922 overhead",
            "metrics": [
                {"label": "Source samples", "value": source_receipt.get("sample_count", "—"), "unit": "", "tone": "neutral"},
                {"label": "Replay samples", "value": sample_count or "—", "unit": "", "tone": "neutral"},
                {"label": "Exact commands", "value": f"{exact_count}/{sample_count}" if sample_count else "—", "unit": "", "tone": "neutral"},
                {"label": "Recorded feeds", "value": len(feeds), "unit": "", "tone": "neutral"},
            ],
            "notes": (
                f"Operator note: {operator_note}. "
                f"Display label {source.get('display_label') or 'none'} disagrees with the "
                f"structured {source_square.upper()} → {destination_square.upper()} metadata; "
                "both are preserved. No task-success or training-admission claim."
            ),
            "phases": [{"name": "Physical source", "start": 0.0, "end": 1.0}],
            "case_id": "source_and_guarded_physical_replay_feeds",
            "release_tag": manifest.get("release_tag"),
        }
    ]

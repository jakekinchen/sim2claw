from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.request import urlopen

from sim2claw import studio_catalog
from sim2claw.learning_factory_artifacts import canonical_digest, sha256_file
from sim2claw.paths import REPO_ROOT
from sim2claw.studio_server import create_server


PUBLICATION_ROOT = (
    REPO_ROOT
    / "src/sim2claw/studio_web/publication/pawn_bg_ranked_grasp_v1"
)


def test_tracked_ranked_grasp_bundle_is_self_contained_and_hash_bound() -> None:
    manifest_path = PUBLICATION_ROOT / "gallery_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    episodes = manifest["episodes"]
    bundle = manifest["publication_bundle"]

    assert manifest["schema_version"] == "sim2claw.pawn_bg_ranked_grasp_gallery.v1"
    assert manifest["proof_class"] == "retained_action_frozen_simulation_replay"
    assert len(episodes) == 7
    assert [row["rank"] for row in episodes] == list(range(1, 8))
    assert not any(row["task_consequence_success"] for row in episodes)
    assert bundle["source_actions_modified"] is False
    assert bundle["physical_authority"] is False
    assert bundle["action_array_sha256_by_rank"] == [
        row["action_array_sha256"] for row in episodes
    ]
    unsigned = {
        key: value for key, value in manifest.items() if key != "manifest_digest"
    }
    assert canonical_digest(unsigned) == manifest["manifest_digest"]

    scene_paths = {
        REPO_ROOT / row["state_trace"]["scene_manifest_path"] for row in episodes
    }
    assert scene_paths == {PUBLICATION_ROOT / "scene_manifest.json"}
    scene_path = next(iter(scene_paths))
    assert sha256_file(scene_path) == bundle["published_scene_manifest_sha256"]
    scene = json.loads(scene_path.read_text(encoding="utf-8"))
    assert scene["revision_sha256"] == bundle["scene_manifest_revision_sha256"]

    total_trace_bytes = 0
    for row in episodes:
        artifact = row["state_trace"]
        trace_path = REPO_ROOT / artifact["state_trace_path"]
        total_trace_bytes += trace_path.stat().st_size
        assert trace_path.is_relative_to(PUBLICATION_ROOT / "episodes")
        assert sha256_file(trace_path) == artifact["state_trace_sha256"]
        assert len(artifact["source_state_trace_sha256"]) == 64
        assert artifact["source_state_trace_sha256"] != artifact[
            "state_trace_sha256"
        ]
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        assert trace["proof_class"] == manifest["proof_class"]
        assert trace["frame_count"] == artifact["frame_count"] == len(trace["frames"])
        assert trace["fps"] == artifact["fps"] == 10
        assert trace["frame_count"] < artifact["source_frame_count"]
        assert trace["scene"]["manifest_revision_sha256"] == scene[
            "revision_sha256"
        ]
        assert trace["derivative"]["source_state_trace_sha256"] == artifact[
            "source_state_trace_sha256"
        ]
        assert trace["derivative"]["source_actions_modified"] is False
        assert trace["frames"][0]["t"] == 0
        assert trace["frames"][-1]["t"] == trace["duration_seconds"]
    assert total_trace_bytes < 6 * 1024 * 1024


def test_catalog_uses_tracked_bundle_without_generated_outputs() -> None:
    episodes = [
        row
        for row in studio_catalog._ranked_grasp_episodes(REPO_ROOT)
        if row["task_id"] == "pawn_bg_ranked_grasp_v3"
    ]

    assert len(episodes) == 7
    assert [row["rank"] for row in episodes] == list(range(1, 8))
    assert {row["gallery_source"] for row in episodes} == {
        "tracked_publication_bundle"
    }
    assert len({row["inspection"]["scene_url"] for row in episodes}) == 1
    assert all(
        row["inspection"]["trace_url"].startswith(
            "/publication/pawn_bg_ranked_grasp_v1/episodes/"
        )
        for row in episodes
    )
    assert all(row["physical_authority"] is False for row in episodes)


def test_server_serves_publication_scene_and_phone_trace() -> None:
    episode = next(
        row
        for row in studio_catalog._ranked_grasp_episodes(REPO_ROOT)
        if row["task_id"] == "pawn_bg_ranked_grasp_v3"
    )
    server = create_server("127.0.0.1", 0, repo_root=REPO_ROOT, read_only=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(base + episode["inspection"]["scene_url"], timeout=3) as response:
            scene = json.load(response)
        with urlopen(base + episode["inspection"]["trace_url"], timeout=3) as response:
            trace = json.load(response)
        assert scene["schema_version"] == "sim2claw.mujoco_scene_manifest.v1"
        assert trace["schema_version"] == "sim2claw.mujoco_body_state_trace.v1"
        assert trace["frame_count"] == episode["inspection"]["frame_count"]
        assert trace["scene"]["manifest_revision_sha256"] == scene["revision_sha256"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sim2claw.learning_factory_artifacts import canonical_digest, sha256_file
from sim2claw.pawn_bg_grasp_gallery import (
    GraspGalleryError,
    episode_rank_key,
    export_ranked_grasp_publication_bundle,
)


def _episode(**changes: object) -> dict[str, object]:
    row: dict[str, object] = {
        "task_consequence_success": False,
        "lift_and_transport": False,
        "piece_lifted": False,
        "bilateral_lift_retention": False,
        "qualified_bilateral_contact_observed": True,
        "selected_piece_contact_observed": True,
        "maximum_transport_progress_after_lift": 0.0,
        "maximum_bilateral_lift_retention_seconds": 0.0,
        "maximum_piece_rise_m": 0.02,
        "maximum_post_grasp_slip_m": 0.01,
        "final_target_distance_m": 0.04,
        "maximum_other_piece_displacement_m": 0.0,
    }
    row.update(changes)
    return row


def test_gallery_rank_is_consequence_first_and_interpretable() -> None:
    near_miss = _episode(maximum_piece_rise_m=0.04)
    lifted = _episode(
        piece_lifted=True,
        bilateral_lift_retention=True,
        maximum_piece_rise_m=0.041,
    )
    transported = _episode(
        piece_lifted=True,
        bilateral_lift_retention=True,
        lift_and_transport=True,
        maximum_transport_progress_after_lift=0.5,
    )
    strict = _episode(task_consequence_success=True)
    assert episode_rank_key(strict) > episode_rank_key(transported)
    assert episode_rank_key(transported) > episode_rank_key(lifted)
    assert episode_rank_key(lifted) > episode_rank_key(near_miss)


def test_gallery_rank_breaks_same_tier_ties_with_progress_then_retention() -> None:
    low_progress = _episode(
        piece_lifted=True,
        bilateral_lift_retention=True,
        maximum_transport_progress_after_lift=0.1,
        maximum_bilateral_lift_retention_seconds=0.5,
    )
    high_progress = _episode(
        piece_lifted=True,
        bilateral_lift_retention=True,
        maximum_transport_progress_after_lift=0.4,
        maximum_bilateral_lift_retention_seconds=0.1,
    )
    assert episode_rank_key(high_progress) > episode_rank_key(low_progress)


def test_gallery_identity_must_be_nonempty(tmp_path) -> None:
    from sim2claw.pawn_bg_grasp_gallery import build_ranked_grasp_gallery

    with pytest.raises(GraspGalleryError, match="identity"):
        build_ranked_grasp_gallery(
            source_receipt_path=tmp_path / "missing.json",
            output_root=tmp_path / "output",
            task_id="",
        )


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def test_publication_bundle_is_compact_shared_scene_action_frozen_derivative(
    tmp_path: Path,
) -> None:
    root = tmp_path
    source_root = root / "outputs/pawn_bg_ranked_grasp_gallery_v1"
    publication_root = (
        root / "src/sim2claw/studio_web/publication/pawn_bg_ranked_grasp_v1"
    )
    scene = {
        "schema_version": "sim2claw.mujoco_scene_manifest.v1",
        "revision_sha256": "b" * 64,
    }
    episodes: list[dict[str, object]] = []
    source_action_hashes: list[str] = []
    for rank in range(1, 8):
        episode_root = source_root / "episodes" / f"rank-{rank:02d}-fixture"
        scene_path = episode_root / "scene_manifest.json"
        _write_json(scene_path, scene)
        frames = [
            {
                "t": index / 30,
                "phase": "approach" if index < 4 else "grasp",
                "p": [0.123456789 + index / 100, 0, 0, 1, 1, 1],
                "q": [1, 0, 0, 0, 1, 0, 0, 0],
                "c": [[0, 1, 0.123456789, 0, 0]],
            }
            for index in range(7)
        ]
        trace = {
            "schema_version": "sim2claw.mujoco_body_state_trace.v1",
            "proof_class": "retained_action_frozen_simulation_replay",
            "body_names": ["world", "pawn"],
            "duration_seconds": 0.2,
            "fps": 30,
            "frame_count": len(frames),
            "scene": {
                "manifest_revision_sha256": scene["revision_sha256"],
                "manifest_url": "/media/generated-scene",
            },
            "frames": frames,
        }
        trace_path = episode_root / "state_trace.json"
        _write_json(trace_path, trace)
        action_hash = f"{rank:064x}"
        source_action_hashes.append(action_hash)
        episodes.append(
            {
                "rank": rank,
                "recording_id": f"fixture-{rank}",
                "action_array_sha256": action_hash,
                "state_trace": {
                    "state_trace_path": str(trace_path.relative_to(root)),
                    "state_trace_sha256": sha256_file(trace_path),
                    "scene_manifest_path": str(scene_path.relative_to(root)),
                    "scene_manifest_sha256": sha256_file(scene_path),
                    "frame_count": len(frames),
                    "fps": 30,
                    "duration_seconds": 0.2,
                },
            }
        )
    gallery: dict[str, object] = {
        "schema_version": "sim2claw.pawn_bg_ranked_grasp_gallery.v1",
        "task_id": "pawn_bg_ranked_grasp_v3",
        "proof_class": "retained_action_frozen_simulation_replay",
        "episodes": episodes,
        "authority": {
            "source_actions_modified": False,
            "physical_authority": False,
        },
    }
    gallery["manifest_digest"] = canonical_digest(gallery)
    _write_json(source_root / "gallery_manifest.json", gallery)

    published = export_ranked_grasp_publication_bundle(
        source_repository_root=root,
        source_gallery_root=source_root,
        publication_root=publication_root,
        publication_fps=10,
    )

    assert len(published["episodes"]) == 7
    assert published["proof_class"] == gallery["proof_class"]
    assert published["publication_bundle"]["source_actions_modified"] is False
    assert (
        published["publication_bundle"]["action_array_sha256_by_rank"]
        == source_action_hashes
    )
    assert len(
        {
            row["state_trace"]["scene_manifest_path"]
            for row in published["episodes"]
        }
    ) == 1
    assert len(list(publication_root.glob("scene_manifest.json"))) == 1
    first_artifact = published["episodes"][0]["state_trace"]
    compact_trace = json.loads(
        (root / first_artifact["state_trace_path"]).read_text(encoding="utf-8")
    )
    assert compact_trace["fps"] == 10
    assert compact_trace["frame_count"] == 4
    assert [frame["phase"] for frame in compact_trace["frames"]] == [
        "approach",
        "approach",
        "grasp",
        "grasp",
    ]
    assert compact_trace["frames"][0]["p"][0] == 0.123457
    assert compact_trace["frames"][0]["c"][0][2] == 0.123457
    assert compact_trace["derivative"]["source_actions_modified"] is False
    assert first_artifact["source_frame_count"] == 7
    assert first_artifact["frame_count"] == 4
    assert sha256_file(root / first_artifact["state_trace_path"]) == first_artifact[
        "state_trace_sha256"
    ]
    unsigned = {
        key: value for key, value in published.items() if key != "manifest_digest"
    }
    assert canonical_digest(unsigned) == published["manifest_digest"]

from __future__ import annotations

import hashlib
import json
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sim2claw import studio_assets, studio_catalog as studio_catalog_module
from sim2claw.paths import (
    DEFAULT_CAPTURE_CONFIG,
    DEFAULT_SO101_MASS_PROFILE,
    SO101_MODEL_PATH,
    STUDIO_ASSET_ROOT,
)
from sim2claw.physical_gateway import PhysicalGatewayError
from sim2claw.studio_catalog import (
    build_catalog,
    media_token,
    resolve_media_token,
)
from sim2claw.studio_events import StudioActivity
from sim2claw.studio_server import STATIC_ROOT, create_server


class StudioCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "configs" / "tasks").mkdir(parents=True)
        self._write_json(
            self.root / "configs" / "polycam" / "capture.json",
            {
                "simulation_estimates": {
                    "workspace_pose": {
                        "pose_id": (
                            "workspace_board_fiducial_robotward_100mm_20260718_v3"
                        )
                    },
                    "board": {
                        "pose_id": "board_robotward_100mm_20260718_v3",
                        "center_in_table_frame_xy_m": [0.04, -0.065],
                        "robotward_displacement_from_previous_pose_m": 0.1,
                    },
                    "background": {
                        "fiducial_pose_id": (
                            "fiducial_robotward_100mm_20260718_v2"
                        ),
                        "fiducial_center_in_table_frame_xy_m": [0.02, 0.18],
                    },
                    "robots": [],
                }
            },
        )
        (self.root / "datasets" / "pick_v1" / "meta").mkdir(parents=True)
        video_dir = (
            self.root
            / "datasets"
            / "pick_v1"
            / "videos"
            / "chunk-000"
            / "observation.images.front"
        )
        video_dir.mkdir(parents=True)
        (video_dir / "episode_000000.mp4").write_bytes(b"0123456789")
        trace_dir = self.root / "datasets" / "pick_v1" / "state_traces"
        trace_dir.mkdir(parents=True)
        self._write_json(
            trace_dir / "episode_000000.json",
            {
                "schema_version": "sim2claw.mujoco_body_state_trace.v1",
                "scene": {
                    "piece_layout": "standard",
                    "manifest_url": "/api/scene?layout=standard",
                },
                "frame_count": 61,
                "fps": 30,
                "duration_seconds": 2.0,
            },
        )
        self._write_json(
            self.root / "configs" / "tasks" / "pick_v1.json",
            {
                "task_id": "pick_v1",
                "proof_class": "simulation_synthetic_vla_demonstration",
                "frozen_before_training": True,
                "episode": {"phase_physics_steps": {"reach": 3, "lift": 1}},
            },
        )
        self._write_json(
            self.root / "datasets" / "pick_v1" / "meta" / "info.json",
            {"fps": 20},
        )
        (self.root / "datasets" / "pick_v1" / "meta" / "episodes.jsonl").write_text(
            json.dumps(
                {
                    "episode_index": 0,
                    "length": 40,
                    "tasks": ["Pick up the rook."],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self._write_json(
            self.root / "datasets" / "pick_v1" / "dataset_receipt.json",
            {
                "task_id": "pick_v1",
                "proof_class": "simulation_synthetic_vla_demonstration_dataset",
                "episode_evidence": [
                    {
                        "episode_index": 0,
                        "seed": 42,
                        "case_id": "rook",
                        "verdict": {
                            "success": True,
                            "terminal_outcome": "piece_lifted",
                            "gates": {
                                "minimum_piece_rise": {"measured": 0.05},
                                "final_xy_error": {"measured": 0.002},
                            },
                        },
                    }
                ],
            },
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_json(self, path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_catalog_groups_replayable_episode_under_task(self) -> None:
        catalog = build_catalog(self.root)
        self.assertEqual(catalog["summary"]["tasks"], 1)
        self.assertEqual(catalog["summary"]["episodes"], 1)
        self.assertEqual(catalog["summary"]["passed_episodes"], 1)
        episode = catalog["episodes"][0]
        self.assertEqual(episode["task_id"], "pick_v1")
        self.assertEqual(episode["duration_seconds"], 2.0)
        self.assertEqual(episode["status"], "passed")
        self.assertEqual([row["name"] for row in episode["phases"]], ["Reach", "Lift"])
        self.assertFalse(episode["physical_authority"])
        self.assertEqual(episode["camera"], "workcell")
        self.assertEqual(episode["inspection"]["kind"], "threejs_state_trace")
        self.assertEqual(episode["inspection"]["frame_count"], 61)
        resolved = resolve_media_token(
            episode["media"]["url"].split("/")[-1],
            self.root,
        )
        self.assertEqual(resolved.name, "episode_000000.mp4")
        self.assertEqual(
            catalog["simulations"][0]["poster_url"],
            "/assets/workcell/studio-overview.png",
        )
        self.assertNotEqual(
            catalog["robots"][0]["poster_url"],
            catalog["robots"][1]["poster_url"],
        )
        self.assertEqual(
            catalog["simulations"][0]["piece_layout"],
            "sparse_two_sided_pawns",
        )
        self.assertIn("16 sparse pawns", catalog["simulations"][0]["subtitle"])
        self.assertEqual(
            catalog["simulations"][0]["workcell_pose_id"],
            "board_robotward_100mm_20260718_v3",
        )
        self.assertEqual(
            catalog["simulations"][0]["workspace_pose_id"],
            "workspace_board_fiducial_robotward_100mm_20260718_v3",
        )

    def test_current_dual_camera_capture_is_hash_bound_and_fails_closed(self) -> None:
        capture_root = (
            self.root
            / "runs"
            / "current-100mm-measurement-fixture"
            / "episode-c2-c1-dual-fixture"
        )
        replay_root = (
            self.root
            / "runs"
            / "current-100mm-measurement-fixture"
            / "physical-replays"
            / "fixture-replay"
        )
        capture_root.mkdir(parents=True)
        replay_root.mkdir(parents=True)
        overhead = b"fixture-overhead-h264"
        wrist = b"fixture-wrist-h264-mkv"
        wrist_browser = b"fixture-wrist-h264-mp4"
        (capture_root / "overhead_c922.mp4").write_bytes(overhead)
        (capture_root / "wrist_d405.mkv").write_bytes(wrist)
        (capture_root / "wrist_d405.browser.mp4").write_bytes(wrist_browser)
        source_sha256 = "b" * 64
        overhead_sha256 = hashlib.sha256(overhead).hexdigest()
        wrist_sha256 = hashlib.sha256(wrist).hexdigest()
        wrist_browser_sha256 = hashlib.sha256(wrist_browser).hexdigest()
        replay = {
            "schema_version": "sim2claw.physical_trace_replay_attempt.v1",
            "status": "completed",
            "source_recording_id": "fixture-c2-c1",
            "source_samples_sha256": source_sha256,
            "source_trace_direction": "forward",
            "source_sample_count": 527,
            "completed_sample_count": 527,
            "exact_command_sample_count": 501,
            "safety_clamped_sample_count": 70,
            "task_success_verified": False,
            "learned_policy_verified": False,
            "physical_follower_torque_enabled": False,
        }
        self._write_json(replay_root / "replay_receipt.json", replay)
        replay_sha256 = hashlib.sha256(
            (replay_root / "replay_receipt.json").read_bytes()
        ).hexdigest()
        capture = {
            "schema_version": "sim2claw.dual_camera_physical_replay_capture.v1",
            "status": "completed",
            "proof_class": (
                "physical_command_replay_observation_unqualified_dual_camera"
            ),
            "completed_at": "2026-07-24T03:18:12+00:00",
            "source_recording_id": "fixture-c2-c1",
            "source_samples_sha256": source_sha256,
            "source_trace_direction": "forward",
            "replay_run_directory": str(replay_root),
            "replay_receipt_sha256": replay_sha256,
            "physical_task_success_verified": False,
            "training_admission": False,
            "promotion_authority": False,
            "camera_reports": [
                {
                    "file": "overhead_c922.mp4",
                    "name": "C922 Pro Stream Webcam",
                    "role": "overhead_workspace",
                    "sha256": overhead_sha256,
                    "status": "completed_full_timestamp_coverage",
                    "diagnostic_only": True,
                    "metric_depth": False,
                    "fps": 30,
                    "observed": {
                        "frame_count": 1049,
                        "last_timestamp_seconds": 34.966667,
                    },
                },
                {
                    "file": "wrist_d405.mkv",
                    "name": "Intel RealSense D405",
                    "role": "wrist_gripper_upward",
                    "sha256": wrist_sha256,
                    "status": "completed_full_timestamp_coverage",
                    "diagnostic_only": True,
                    "metric_depth": False,
                    "fps": 5,
                    "observed": {
                        "frame_count": 175,
                        "last_timestamp_seconds": 34.8,
                    },
                },
            ],
        }
        self._write_json(capture_root / "capture_receipt.json", capture)
        capture_sha256 = hashlib.sha256(
            (capture_root / "capture_receipt.json").read_bytes()
        ).hexdigest()
        self._write_json(
            capture_root / "studio_projection_receipt.json",
            {
                "schema_version": (
                    "sim2claw.studio_dual_camera_browser_projection.v1"
                ),
                "capture_receipt_sha256": capture_sha256,
                "read_only": True,
                "wrist_browser_derivative": {
                    "file": "wrist_d405.browser.mp4",
                    "sha256": wrist_browser_sha256,
                    "source_file": "wrist_d405.mkv",
                    "source_sha256": wrist_sha256,
                    "operation": "container_remux_h264_copy_to_mp4",
                },
            },
        )
        self._write_json(
            self.root
            / "docs"
            / "autonomous-workflow"
            / "project_state.json",
            {
                "current_100mm_measurement_transaction": {
                    "dual_camera_c2_c1_replay": {
                        "source_recording_id": "fixture-c2-c1",
                        "source_samples_sha256": source_sha256,
                        "source_direction": "forward",
                        "final_replay_receipt_sha256": replay_sha256,
                        "final_capture_receipt_sha256": capture_sha256,
                        "overhead_video_sha256": overhead_sha256,
                        "wrist_video_sha256": wrist_sha256,
                        "source_sample_count": 527,
                        "completed_sample_count": 527,
                        "exact_command_sample_count": 501,
                        "safety_clamped_sample_count": 70,
                        "unresolved_observables": [
                            "grasp_force",
                            "metric_wrist_depth",
                        ],
                    }
                }
            },
        )

        catalog = build_catalog(self.root)
        episode = next(
            row
            for row in catalog["episodes"]
            if row["task_id"] == "current_100mm_measurement_v1"
        )
        self.assertEqual(episode["status"], "failed")
        self.assertFalse(episode["physical_task_success_verified"])
        self.assertFalse(episode["training_admission"])
        self.assertFalse(episode["promotion_authority"])
        self.assertEqual(
            [feed["role"] for feed in episode["recording_feeds"]],
            ["overhead_workspace", "wrist_gripper_upward"],
        )
        self.assertEqual(
            episode["recording_feeds"][0]["display_rotation_degrees"],
            180,
        )
        self.assertEqual(
            episode["recording_feeds"][1]["display_rotation_degrees"],
            0,
        )
        self.assertTrue(all(feed["diagnostic_only"] for feed in episode["recording_feeds"]))
        self.assertTrue(all(not feed["metric_depth"] for feed in episode["recording_feeds"]))
        self.assertIn("terminal negative", episode["notes"])

        (capture_root / "wrist_d405.browser.mp4").write_bytes(b"tampered")
        tampered = build_catalog(self.root)
        self.assertFalse(
            any(
                row["task_id"] == "current_100mm_measurement_v1"
                for row in tampered["episodes"]
            )
        )
        self.assertEqual(
            catalog["simulations"][0]["board_center_in_table_frame_xy_m"],
            [0.04, -0.065],
        )
        self.assertEqual(
            catalog["simulations"][0]["board_pose_label"],
            "100 mm robotward",
        )
        self.assertEqual(
            catalog["simulations"][0]["mug_inspection_url"],
            "/assets/workcell/studio-mug.png",
        )
        self.assertEqual(
            catalog["simulations"][0]["mug_inspection_camera"],
            "studio_mug",
        )
        self.assertEqual(
            catalog["simulations"][0]["visual_props"][0]["id"],
            "antler_mug",
        )
        self.assertEqual(
            catalog["simulations"][0]["fiducial_pose_id"],
            "fiducial_robotward_100mm_20260718_v2",
        )
        self.assertEqual(
            catalog["simulations"][0]["fiducial_center_in_table_frame_xy_m"],
            [0.02, 0.18],
        )

    def test_catalog_exposes_ranked_grasp_gallery_as_threejs_replays(self) -> None:
        gallery_root = self.root / "outputs" / "pawn_bg_ranked_grasp_gallery_v1"
        episode_root = gallery_root / "episodes" / "rank-01-fixture"
        self._write_json(
            episode_root / "state_trace.json",
            {
                "schema_version": "sim2claw.mujoco_body_state_trace.v1",
                "frames": [],
            },
        )
        self._write_json(
            episode_root / "scene_manifest.json",
            {"schema_version": "sim2claw.mujoco_scene_manifest.v1"},
        )
        self._write_json(
            gallery_root / "gallery_manifest.json",
            {
                "schema_version": "sim2claw.pawn_bg_ranked_grasp_gallery.v1",
                "created_at": "2026-07-21T00:00:00+00:00",
                "proof_class": "retained_action_frozen_simulation_replay",
                "episodes": [
                    {
                        "rank": 1,
                        "move_label": "C2 → C1",
                        "folder_label": "c2-to-c1",
                        "relative_success_label": "Lift + transport",
                        "relative_success_summary": "Lift + transport · 60% targetward progress",
                        "relative_success_tier": 5,
                        "piece_lifted": True,
                        "lift_and_transport": True,
                        "task_consequence_success": False,
                        "action_array_sha256": "a" * 64,
                        "metrics": {
                            "maximum_piece_rise_m": 0.058,
                            "maximum_transport_progress_after_lift": 0.6,
                            "maximum_bilateral_lift_retention_seconds": 0.63,
                            "maximum_post_grasp_slip_m": 0.025,
                            "final_target_distance_m": 0.01,
                            "joint_rms_degrees": 1.2,
                            "ee_rms_m": 0.011,
                        },
                        "state_trace": {
                            "state_trace_path": str(
                                (episode_root / "state_trace.json").relative_to(
                                    self.root
                                )
                            ),
                            "scene_manifest_path": str(
                                (episode_root / "scene_manifest.json").relative_to(
                                    self.root
                                )
                            ),
                            "frame_count": 301,
                            "fps": 30,
                            "duration_seconds": 10.0,
                        },
                        "phase_segments": [
                            {"name": "Approach", "start": 0.0, "end": 0.5},
                            {
                                "name": "Lift And Transport",
                                "start": 0.5,
                                "end": 1.0,
                            },
                        ],
                    }
                ],
            },
        )
        catalog = build_catalog(self.root)
        episode = next(
            row
            for row in catalog["episodes"]
            if row["task_id"] == "pawn_bg_ranked_grasp_v3"
        )
        self.assertEqual(episode["rank"], 1)
        self.assertEqual(episode["status"], "partial")
        self.assertEqual(episode["inspection"]["kind"], "threejs_state_trace")
        self.assertEqual(episode["inspection"]["frame_count"], 301)
        self.assertFalse(episode["physical_authority"])
        task = next(
            row
            for row in catalog["tasks"]
            if row["id"] == "pawn_bg_ranked_grasp_v3"
        )
        self.assertEqual(task["title"], "Top pawn grasp replays")
        self.assertEqual(task["passed_count"], 0)

    def test_catalog_includes_physical_source_with_simulator_replay(self) -> None:
        recording = (
            self.root
            / "datasets"
            / "act_source_recordings"
            / "physical-demo__fixture-recording"
        )
        recording.mkdir(parents=True)
        (recording / "overhead_c922.mp4").write_bytes(b"fixture-video")
        self._write_json(
            recording / "recording_receipt.json",
            {
                "recording_id": "fixture-recording",
                "task_id": "pick_v1",
                "label": "D1 to D2 push",
                "skill": "full_episode",
                "outcome_label": "unreviewed",
                "notes": "Successful operator demonstration.",
                "mode": "physical_follower",
                "proof_class": "physical_teleoperation_source_unqualified",
                "piece_id": "brown_pawn_d1",
                "source_square": "d1",
                "destination_square": "d2",
                "sample_count": 42,
                "sample_hz": 20,
                "duration_seconds": 2.1,
            },
        )
        self._write_json(
            recording / "sim_replay_receipt.json",
            {
                "schema_version": "sim2claw.physical_command_sim_replay.v1",
                "action_array_sha256": "1" * 64,
                "state_trace_path": "sim_replay_state_trace.json",
                "state_trace_schema_version": "sim2claw.mujoco_body_state_trace.v1",
                "state_trace_sha256": "0" * 64,
                "state_trace_frame_count": 42,
                "state_trace_fps": 20,
                "state_trace_duration_seconds": 2.1,
                "state_trace_piece_layout": "sparse_two_sided_pawns",
                "state_trace_manifest_url": "/api/scene?layout=sparse_two_sided_pawns",
                "aggregate_body_joint_rmse_degrees": 2.5,
                "maximum_body_joint_error_degrees": 7.0,
            },
        )
        self._write_json(
            recording / "sim_replay_state_trace.json",
            {
                "schema_version": "sim2claw.mujoco_body_state_trace.v1",
                "scene": {
                    "piece_layout": "sparse_two_sided_pawns",
                    "manifest_url": "/api/scene?layout=sparse_two_sided_pawns",
                },
                "frame_count": 42,
                "fps": 20,
                "duration_seconds": 2.1,
            },
        )

        catalog = build_catalog(self.root)
        episode = next(
            row for row in catalog["episodes"] if row["title"] == "D1 to D2 push"
        )
        self.assertEqual(
            episode["proof_class"],
            "physical_source_simulation_command_replay",
        )
        self.assertEqual(episode["status"], "recorded")
        self.assertEqual(episode["media"]["kind"], "video")
        self.assertEqual(episode["inspection"]["kind"], "threejs_state_trace")
        self.assertEqual(episode["inspection"]["frame_count"], 42)
        self.assertEqual(episode["notes"], "Successful operator demonstration.")
        trace = resolve_media_token(
            episode["inspection"]["trace_url"].split("/")[-1],
            self.root,
        )
        self.assertEqual(trace.name, "sim_replay_state_trace.json")
        receipt = json.loads(
            (STUDIO_ASSET_ROOT / "receipt.json").read_text(encoding="utf-8")
        )
        expected_revision = hashlib.sha256(
            json.dumps(
                receipt["sources"], sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()[:8]
        self.assertEqual(
            catalog["simulations"][0]["asset_revision"],
            expected_revision,
        )

    def test_catalog_exposes_physical_library_without_inventing_physics(self) -> None:
        recording = (
            self.root
            / "datasets"
            / "manipulation_source_recordings"
            / "c2-to-c1__fixture-recording"
        )
        recording.mkdir(parents=True)
        (recording / "overhead_c922.mp4").write_bytes(b"fixture-video")
        self._write_json(
            recording / "recording_receipt.json",
            {
                "recording_id": "fixture-recording",
                "task_id": "pawn_manipulation_v1",
                "label": "C2 to C1",
                "skill": "pick_and_place",
                "outcome_label": "success",
                "mode": "physical_follower",
                "proof_class": "physical_teleoperation_source_unqualified",
                "piece_id": "brown_pawn_c2",
                "source_square": "c2",
                "destination_square": "c1",
                "sample_count": 40,
                "sample_hz": 20,
                "duration_seconds": 2.0,
                "overhead_video": {
                    "teleoperation_start_video_offset_seconds": 1.0,
                    "teleoperation_stop_video_offset_seconds": 3.0,
                    "orientation_rotation_degrees": 180,
                },
            },
        )

        catalog = build_catalog(self.root)
        task = next(
            row
            for row in catalog["tasks"]
            if row["id"] == "physical_pawn_episode_library_v1"
        )
        episode = next(
            row
            for row in catalog["episodes"]
            if row["task_id"] == "physical_pawn_episode_library_v1"
        )

        self.assertEqual(task["title"], "Physical pawn episodes")
        self.assertEqual(task["role"], "Recorded evidence")
        self.assertEqual(task["episode_count"], 1)
        self.assertEqual(episode["title"], "Physical episode")
        self.assertEqual(episode["status"], "recorded")
        self.assertEqual(
            episode["proof_class"],
            "physical_teleoperation_source_unqualified",
        )
        self.assertEqual(episode["media"]["kind"], "video")
        self.assertEqual(episode["media"]["window_start_seconds"], 1.0)
        self.assertEqual(episode["media"]["window_end_seconds"], 3.0)
        self.assertEqual(episode["media"]["display_rotation_degrees"], 180)
        self.assertNotIn("inspection", episode)
        self.assertEqual(
            episode["terminal_outcome"],
            "operator_label_success_unqualified",
        )
        self.assertEqual(episode["metrics"][-1]["label"], "Operator label")

        comparison = episode["comparison"]
        self.assertEqual(
            comparison["schema_version"],
            "sim2claw.studio_episode_comparison.v1",
        )
        self.assertTrue(comparison["real"]["available"])
        self.assertTrue(comparison["visual_twin"]["available"])
        self.assertEqual(
            comparison["visual_twin"]["physics_authority"],
            "none",
        )
        self.assertFalse(comparison["physics_replay"]["available"])
        self.assertIn("action-frozen", comparison["physics_replay"]["notice"])
        self.assertIsNone(comparison["physics_replay"]["binding"])

    def test_physical_pairing_requires_tracked_receipt_and_action_hash(self) -> None:
        recording = (
            self.root
            / "datasets"
            / "manipulation_source_recordings"
            / "c2-to-c1__fixture-recording"
        )
        recording.mkdir(parents=True)
        (recording / "overhead_c922.mp4").write_bytes(b"fixture-video")
        self._write_json(
            recording / "recording_receipt.json",
            {
                "recording_id": "fixture-recording",
                "mode": "physical_follower",
                "proof_class": "physical_teleoperation_source_unqualified",
                "piece_id": "brown_pawn_c2",
                "source_square": "c2",
                "destination_square": "c1",
                "sample_count": 40,
                "sample_hz": 20,
                "duration_seconds": 2.0,
                "overhead_video": {
                    "teleoperation_start_video_offset_seconds": 1.0,
                    "teleoperation_stop_video_offset_seconds": 3.0,
                    "orientation_rotation_degrees": 180,
                },
            },
        )
        action_sha256 = "a" * 64
        evidence_receipt_path = (
            self.root
            / "outputs"
            / "pawn_bg_ranked_grasp_gallery_v1"
            / "episodes"
            / "fixture-recording"
            / "episode_probe_receipt.json"
        )
        state_trace_path = (
            self.root
            / "src"
            / "sim2claw"
            / "studio_web"
            / "publication"
            / "pawn_bg_ranked_grasp_v1"
            / "episodes"
            / "fixture-recording.json"
        )
        evidence_receipt = {
            "schema_version": "sim2claw.pawn_bg_grasp_episode_probe.v1",
            "episode": {
                "recording_id": "fixture-recording",
                "action_array_sha256": action_sha256,
                "action_byte_identical": True,
            },
        }
        state_trace = {
            "schema_version": "sim2claw.mujoco_body_state_trace.v1",
            "scene": {
                "piece_layout": "standard",
                "manifest_url": "/api/scene?layout=standard",
            },
            "frame_count": 20,
            "fps": 10,
            "duration_seconds": 2,
        }
        self._write_json(evidence_receipt_path, evidence_receipt)
        self._write_json(state_trace_path, state_trace)
        replay = {
            "source_recording_id": "fixture-recording",
            "gallery_source": "generated_output",
            "action_array_sha256": action_sha256,
            "state_trace_sha256": hashlib.sha256(
                state_trace_path.read_bytes()
            ).hexdigest(),
            "evidence_receipt": {
                "path": (
                    "outputs/pawn_bg_ranked_grasp_gallery_v1/episodes/"
                    "fixture-recording/episode_probe_receipt.json"
                ),
                "sha256": hashlib.sha256(
                    evidence_receipt_path.read_bytes()
                ).hexdigest(),
            },
            "_binding_sources": {
                "evidence_receipt_path": (
                    "outputs/pawn_bg_ranked_grasp_gallery_v1/episodes/"
                    "fixture-recording/episode_probe_receipt.json"
                ),
                "state_trace_path": (
                    "src/sim2claw/studio_web/publication/"
                    "pawn_bg_ranked_grasp_v1/episodes/fixture-recording.json"
                ),
            },
            "inspection": {
                "kind": "threejs_state_trace",
                "trace_url": "/fixture-trace.json",
                "scene_url": "/fixture-scene.json",
                "frame_count": 20,
                "fps": 10,
                "duration_seconds": 2,
                "physics_authority": "mujoco",
                "renderer_authority": "inspection_only",
            },
        }

        with patch.object(
            studio_catalog_module,
            "_ranked_grasp_episodes",
            return_value=[replay],
        ):
            generated = studio_catalog_module._teleop_episodes(self.root)[0]
        self.assertNotIn("inspection", generated)
        self.assertFalse(generated["comparison"]["physics_replay"]["available"])

        replay["gallery_source"] = "tracked_publication_bundle"
        replay["action_array_sha256"] = "not-a-digest"
        with patch.object(
            studio_catalog_module,
            "_ranked_grasp_episodes",
            return_value=[replay],
        ):
            malformed = studio_catalog_module._teleop_episodes(self.root)[0]
        self.assertNotIn("inspection", malformed)
        self.assertFalse(malformed["comparison"]["physics_replay"]["available"])

        replay["action_array_sha256"] = "a" * 64
        with patch.object(
            studio_catalog_module,
            "_ranked_grasp_episodes",
            return_value=[replay],
        ):
            paired = studio_catalog_module._teleop_episodes(self.root)[0]
        physics = paired["comparison"]["physics_replay"]
        self.assertTrue(physics["available"])
        self.assertEqual(physics["action_array_sha256"], action_sha256)
        self.assertEqual(
            physics["binding"]["kind"],
            "tracked_publication_recording_and_action",
        )
        self.assertEqual(
            physics["binding"]["evidence_receipt"]["sha256"],
            hashlib.sha256(evidence_receipt_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            physics["binding"]["state_trace_sha256"],
            hashlib.sha256(state_trace_path.read_bytes()).hexdigest(),
        )
        self.assertIn("byte-identical", physics["notice"])

        def assert_unavailable(candidate: dict[str, object]) -> None:
            with patch.object(
                studio_catalog_module,
                "_ranked_grasp_episodes",
                return_value=[candidate],
            ):
                episode = studio_catalog_module._teleop_episodes(self.root)[0]
            self.assertNotIn("inspection", episode)
            self.assertFalse(episode["comparison"]["physics_replay"]["available"])
            self.assertIsNone(episode["comparison"]["physics_replay"]["binding"])

        evidence_receipt["unexpected"] = "receipt-byte-drift"
        self._write_json(evidence_receipt_path, evidence_receipt)
        assert_unavailable(replay)

        evidence_receipt.pop("unexpected")
        self._write_json(evidence_receipt_path, evidence_receipt)
        replay["evidence_receipt"]["sha256"] = hashlib.sha256(
            evidence_receipt_path.read_bytes()
        ).hexdigest()
        state_trace["unexpected"] = "trace-byte-drift"
        self._write_json(state_trace_path, state_trace)
        assert_unavailable(replay)

        state_trace.pop("unexpected")
        self._write_json(state_trace_path, state_trace)
        replay["state_trace_sha256"] = hashlib.sha256(
            state_trace_path.read_bytes()
        ).hexdigest()
        evidence_receipt["episode"]["recording_id"] = "different-recording"
        self._write_json(evidence_receipt_path, evidence_receipt)
        replay["evidence_receipt"]["sha256"] = hashlib.sha256(
            evidence_receipt_path.read_bytes()
        ).hexdigest()
        assert_unavailable(replay)

        evidence_receipt["episode"]["recording_id"] = "fixture-recording"
        evidence_receipt["episode"]["action_array_sha256"] = "d" * 64
        self._write_json(evidence_receipt_path, evidence_receipt)
        replay["evidence_receipt"]["sha256"] = hashlib.sha256(
            evidence_receipt_path.read_bytes()
        ).hexdigest()
        assert_unavailable(replay)

        evidence_receipt["episode"]["action_array_sha256"] = action_sha256
        evidence_receipt["episode"]["action_byte_identical"] = False
        self._write_json(evidence_receipt_path, evidence_receipt)
        replay["evidence_receipt"]["sha256"] = hashlib.sha256(
            evidence_receipt_path.read_bytes()
        ).hexdigest()
        assert_unavailable(replay)

    def test_media_tokens_cannot_escape_generated_storage(self) -> None:
        outside = self.root / "README.md"
        outside.write_text("private", encoding="utf-8")
        token = media_token(outside, self.root)
        with self.assertRaisesRegex(ValueError, "outside generated artifact storage"):
            resolve_media_token(token, self.root)
        private_receipt = self.root / "runs" / "private_receipt.json"
        self._write_json(private_receipt, {"serial_port": "fixture-secret"})
        with self.assertRaisesRegex(ValueError, "limited to episode state traces"):
            resolve_media_token(media_token(private_receipt, self.root), self.root)

    def test_private_releases_are_hash_gated_and_catalogued(self) -> None:
        def write_asset(relative: str, payload: bytes, **metadata: object) -> dict[str, object]:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            return {
                "name": path.name,
                "size_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                **metadata,
            }

        splat_root = (
            self.root / "artifacts" / "private" / "releases" / "img5349-3dgs-20260719"
        )
        splat_specs = [
            write_asset(
                str(splat_root.relative_to(self.root) / "IMG_5349-primary-real-splat.ply"),
                b"ply\nfixture-splats",
                splat_count=3,
                spherical_harmonics_degree=3,
            ),
            write_asset(
                str(splat_root.relative_to(self.root) / "IMG_5349-preview.png"),
                b"fixture-preview",
            ),
            write_asset(
                str(splat_root.relative_to(self.root) / "IMG_5349-orbit.mp4"),
                b"fixture-orbit",
            ),
        ]
        self._write_json(
            self.root / "docs" / "reference" / "IPHONE_VIDEO_3DGS_RELEASE_20260719.json",
            {
                "schema_version": "sim2claw.private_3dgs_release_manifest.v1",
                "release_tag": "fixture-3dgs",
                "source": {
                    "name": "IMG_5349.MOV",
                    "sha256": "a" * 64,
                    "proof_class": "owner_provided_monocular_video",
                },
                "assets": splat_specs,
                "authority": {"metric_scale": False, "robot_control": False},
            },
        )

        replay_root = (
            self.root
            / "artifacts"
            / "private"
            / "releases"
            / "physical-replay-evidence-20260719"
        )
        source_receipt_payload = json.dumps(
            {
                "sample_count": 42,
                "sample_hz": 20,
                "saved_at": "2026-07-18T23:04:16Z",
                "overhead_video": {
                    "teleoperation_start_video_offset_seconds": 1.0,
                    "teleoperation_stop_video_offset_seconds": 3.0,
                },
            }
        ).encode()
        replay_specs = [
            write_asset(
                str(replay_root.relative_to(self.root) / "source-episode-overhead-c922.mp4"),
                b"source-video",
                camera_role="overhead_board",
                teleoperation_start_video_offset_seconds=1.0,
                teleoperation_stop_video_offset_seconds=3.0,
            ),
            write_asset(
                str(replay_root.relative_to(self.root) / "replay-overhead-c922.mkv"),
                b"overhead-mkv",
                camera_role="overhead_board",
                replay_window_start_seconds=4.0,
                replay_window_end_seconds=6.0,
            ),
            write_asset(
                str(replay_root.relative_to(self.root) / "replay-side-logitech.mkv"),
                b"side-mkv",
                camera_role="side_arm",
                replay_window_start_seconds=5.0,
                replay_window_end_seconds=7.0,
            ),
            write_asset(
                str(replay_root.relative_to(self.root) / "replay-wrist-d405.mkv"),
                b"wrist-mkv",
                camera_role="wrist_gripper_upward",
                replay_window_start_seconds=3.0,
                replay_window_end_seconds=5.0,
                view_limitation="Fixture wrist limitation.",
            ),
            write_asset(
                str(replay_root.relative_to(self.root) / "source-episode-recording-receipt.json"),
                source_receipt_payload,
            ),
        ]
        replay_spec_by_name = {
            str(spec["name"]): spec for spec in replay_specs
        }
        ffmpeg_sha256 = "f" * 64
        derivative_operation = "container_remux_h264_copy_to_mp4"
        derived_rows: list[dict[str, object]] = []
        derivative_specs: list[dict[str, object]] = []
        for source_name, output_name in (
            ("replay-overhead-c922.mkv", "replay-overhead-c922.browser.mp4"),
            ("replay-side-logitech.mkv", "replay-side-logitech.browser.mp4"),
            ("replay-wrist-d405.mkv", "replay-wrist-d405.browser.mp4"),
        ):
            payload = f"browser-{source_name}".encode()
            source_sha256 = replay_spec_by_name[source_name]["sha256"]
            spec = write_asset(
                str(replay_root.relative_to(self.root) / output_name),
                payload,
                kind="studio_browser_derivative",
                source_name=source_name,
                source_sha256=source_sha256,
                operation=derivative_operation,
                ffmpeg_identity={
                    "version": "fixture",
                    "executable_sha256": ffmpeg_sha256,
                },
            )
            derivative_specs.append(spec)
            derived_rows.append(
                {
                    key: spec[key]
                    for key in (
                        "name",
                        "source_name",
                        "source_sha256",
                        "operation",
                        "size_bytes",
                        "sha256",
                    )
                }
            )
        self._write_json(
            self.root / "docs" / "reference" / "PHYSICAL_REPLAY_RELEASE_20260719.json",
            {
                "schema_version": "sim2claw.github_release_evidence_manifest.v1",
                "release_tag": "fixture-physical",
                "source_episode": {
                    "recording_id": "fixture-release",
                    "structured_source_square": "e2",
                    "structured_destination_square": "e1",
                    "display_label": "F2 to F1",
                    "operator_note": "Fixture annotation.",
                    "proof_class": "physical_teleoperation_source_unqualified",
                },
                "physical_replay": {
                    "completed_sample_count": 42,
                    "exact_command_sample_count": 40,
                },
                "assets": replay_specs + derivative_specs,
            },
        )
        integration_receipt_path = replay_root / "studio-integration-receipt.json"
        valid_integration_receipt = {
            "schema_version": "sim2claw.studio_private_release_import.v1",
            "source_release_tag": "fixture-physical",
            "ffmpeg_sha256": ffmpeg_sha256,
            "derived_assets": derived_rows,
        }
        self._write_json(integration_receipt_path, valid_integration_receipt)

        catalog = build_catalog(self.root)
        calibration = catalog["calibrations"][0]
        self.assertEqual(calibration["status"], "ready")
        self.assertEqual(calibration["proof_class"], "monocular_video_relative_scale_3dgs")
        self.assertEqual(calibration["model"]["splat_count"], 3)
        self.assertEqual(
            resolve_media_token(calibration["model"]["url"].split("/")[-1], self.root).suffix,
            ".ply",
        )
        physical = next(
            episode for episode in catalog["episodes"]
            if episode["id"].endswith("physical-release-fixture-release")
        )
        self.assertEqual(physical["status"], "recorded")
        self.assertNotIn("evaluator_verdict", physical)
        self.assertEqual(len(physical["recording_feeds"]), 4)
        self.assertIn("disagrees", physical["notes"])

        arbitrary = replay_root / "arbitrary.browser.mp4"
        arbitrary.write_bytes(b"receipt-must-not-authorize-this")
        overhead_source = replay_spec_by_name["replay-overhead-c922.mkv"]
        fake_receipt = {
            "schema_version": "sim2claw.studio_private_release_import.v1",
            "source_release_tag": "fixture-physical",
            "ffmpeg_sha256": ffmpeg_sha256,
            "derived_assets": [
                {
                    "name": arbitrary.name,
                    "source_name": "replay-overhead-c922.mkv",
                    "source_sha256": overhead_source["sha256"],
                    "operation": derivative_operation,
                    "size_bytes": arbitrary.stat().st_size,
                    "sha256": hashlib.sha256(arbitrary.read_bytes()).hexdigest(),
                }
            ],
        }
        self._write_json(integration_receipt_path, fake_receipt)
        fake_receipt_catalog = build_catalog(self.root)
        fake_receipt_episode = next(
            episode for episode in fake_receipt_catalog["episodes"]
            if episode["id"].endswith("physical-release-fixture-release")
        )
        self.assertEqual(len(fake_receipt_episode["recording_feeds"]), 1)
        with self.assertRaisesRegex(ValueError, "not admitted by a verified release"):
            resolve_media_token(media_token(arbitrary, self.root), self.root)

        mismatched_row = dict(derived_rows[0])
        mismatched_row["operation"] = "reencode_or_replace_bytes"
        self._write_json(
            integration_receipt_path,
            {
                "schema_version": "sim2claw.studio_private_release_import.v1",
                "source_release_tag": "fixture-physical",
                "ffmpeg_sha256": ffmpeg_sha256,
                "derived_assets": [mismatched_row],
            },
        )
        mismatched_catalog = build_catalog(self.root)
        mismatched_episode = next(
            episode for episode in mismatched_catalog["episodes"]
            if episode["id"].endswith("physical-release-fixture-release")
        )
        self.assertEqual(len(mismatched_episode["recording_feeds"]), 1)

        tracked_derivative = replay_root / str(derived_rows[0]["name"])
        trusted_derivative_bytes = tracked_derivative.read_bytes()
        arbitrary_derivative_bytes = b"z" * len(trusted_derivative_bytes)
        tracked_derivative.write_bytes(arbitrary_derivative_bytes)
        forged_tracked_row = dict(derived_rows[0])
        forged_tracked_row["sha256"] = hashlib.sha256(
            arbitrary_derivative_bytes
        ).hexdigest()
        self._write_json(
            integration_receipt_path,
            {
                "schema_version": "sim2claw.studio_private_release_import.v1",
                "source_release_tag": "fixture-physical",
                "ffmpeg_sha256": ffmpeg_sha256,
                "derived_assets": [forged_tracked_row],
            },
        )
        forged_bytes_catalog = build_catalog(self.root)
        forged_bytes_episode = next(
            episode for episode in forged_bytes_catalog["episodes"]
            if episode["id"].endswith("physical-release-fixture-release")
        )
        self.assertEqual(len(forged_bytes_episode["recording_feeds"]), 1)
        with self.assertRaisesRegex(ValueError, "not admitted by a verified release"):
            resolve_media_token(media_token(tracked_derivative, self.root), self.root)
        tracked_derivative.write_bytes(trusted_derivative_bytes)

        unverified = splat_root / "not-in-release.png"
        unverified.write_bytes(b"not admitted")
        with self.assertRaisesRegex(ValueError, "not admitted by a verified release"):
            resolve_media_token(media_token(unverified, self.root), self.root)

        escaped = replay_root.parent / "escaped.browser.mp4"
        escaped.write_bytes(b"escaped-derived")
        self._write_json(
            integration_receipt_path,
            {
                "schema_version": "sim2claw.studio_private_release_import.v1",
                "source_release_tag": "fixture-physical",
                "ffmpeg_sha256": ffmpeg_sha256,
                "derived_assets": [
                    {
                        "source_name": "replay-overhead-c922.mkv",
                        "source_sha256": overhead_source["sha256"],
                        "name": "../escaped.browser.mp4",
                        "operation": derivative_operation,
                        "size_bytes": escaped.stat().st_size,
                        "sha256": hashlib.sha256(escaped.read_bytes()).hexdigest(),
                    }
                ],
            },
        )
        traversal_gated = build_catalog(self.root)
        traversal_episode = next(
            episode for episode in traversal_gated["episodes"]
            if episode["id"].endswith("physical-release-fixture-release")
        )
        self.assertEqual(len(traversal_episode["recording_feeds"]), 1)

        symlink_target = replay_root.parent / "symlink-target.browser.mp4"
        symlink_target.write_bytes(b"symlink-derived")
        symlink = replay_root / "linked.browser.mp4"
        symlink.symlink_to(symlink_target)
        self._write_json(
            integration_receipt_path,
            {
                "schema_version": "sim2claw.studio_private_release_import.v1",
                "source_release_tag": "fixture-physical",
                "ffmpeg_sha256": ffmpeg_sha256,
                "derived_assets": [
                    {
                        "source_name": "replay-overhead-c922.mkv",
                        "source_sha256": overhead_source["sha256"],
                        "name": symlink.name,
                        "operation": derivative_operation,
                        "size_bytes": symlink_target.stat().st_size,
                        "sha256": hashlib.sha256(symlink_target.read_bytes()).hexdigest(),
                    }
                ],
            },
        )
        symlink_gated = build_catalog(self.root)
        symlink_episode = next(
            episode for episode in symlink_gated["episodes"]
            if episode["id"].endswith("physical-release-fixture-release")
        )
        self.assertEqual(len(symlink_episode["recording_feeds"]), 1)

        self._write_json(integration_receipt_path, valid_integration_receipt)

        (splat_root / "IMG_5349-primary-real-splat.ply").write_bytes(
            b"ply\nfixture-splatX"
        )
        (replay_root / "source-episode-overhead-c922.mp4").write_bytes(
            b"tamper-video"
        )
        with self.assertRaisesRegex(ValueError, "not admitted by a verified release"):
            resolve_media_token(calibration["model"]["url"].split("/")[-1], self.root)
        gated = build_catalog(self.root)
        self.assertEqual(gated["calibrations"][0]["status"], "asset_missing")
        self.assertIsNone(gated["calibrations"][0]["model"])
        self.assertFalse(
            any(episode["id"].endswith("physical-release-fixture-release") for episode in gated["episodes"])
        )

    def test_private_media_streams_the_single_verified_open_descriptor(self) -> None:
        release_root = (
            self.root
            / "artifacts"
            / "private"
            / "releases"
            / "physical-replay-evidence-20260719"
        )
        release_root.mkdir(parents=True)
        trusted = b"tracked-private-media"
        attacker = b"x" * len(trusted)
        media_path = release_root / "tracked.mp4"
        media_path.write_bytes(trusted)
        self._write_json(
            self.root / "docs" / "reference" / "PHYSICAL_REPLAY_RELEASE_20260719.json",
            {
                "schema_version": "sim2claw.github_release_evidence_manifest.v1",
                "release_tag": "fixture-toctou",
                "assets": [
                    {
                        "name": media_path.name,
                        "size_bytes": len(trusted),
                        "sha256": hashlib.sha256(trusted).hexdigest(),
                    }
                ],
            },
        )
        token = media_token(media_path, self.root)
        original_open = studio_catalog_module._open_relative_no_follow

        server = create_server("127.0.0.1", 0, repo_root=self.root)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_address[1]}/media/{token}"
        try:
            for replacement_kind in ("regular", "symlink"):
                with self.subTest(replacement_kind=replacement_kind):
                    if media_path.exists() or media_path.is_symlink():
                        media_path.unlink()
                    media_path.write_bytes(trusted)
                    symlink_target = release_root / "replacement-target.mp4"
                    symlink_target.unlink(missing_ok=True)

                    def replace_after_open(repo_root: Path, relative: Path) -> int:
                        descriptor = original_open(repo_root, relative)
                        media_path.unlink()
                        if replacement_kind == "regular":
                            media_path.write_bytes(attacker)
                        else:
                            symlink_target.write_bytes(attacker)
                            media_path.symlink_to(symlink_target)
                        return descriptor

                    with patch.object(
                        studio_catalog_module,
                        "_open_relative_no_follow",
                        side_effect=replace_after_open,
                    ):
                        with urlopen(url, timeout=3) as response:
                            self.assertEqual(response.read(), trusted)
                            self.assertEqual(
                                int(response.headers["Content-Length"]), len(trusted)
                            )

            if media_path.exists() or media_path.is_symlink():
                media_path.unlink()
            symlink_target = release_root / "preexisting-target.mp4"
            symlink_target.write_bytes(attacker)
            media_path.symlink_to(symlink_target)
            with self.assertRaises(HTTPError) as raised:
                urlopen(url, timeout=3)
            self.assertEqual(raised.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_activity_progress_is_catalogued(self) -> None:
        run_root = self.root / "runs" / "studio" / "processes"
        activity = StudioActivity(
            kind="training",
            title="Test training",
            task_id="pick_v1",
            run_root=run_root,
        )
        activity.update(phase="Optimizing", current=3, total=10)
        catalog = build_catalog(self.root)
        process = next(row for row in catalog["processes"] if row["id"] == activity.id)
        self.assertEqual(process["status"], "running")
        self.assertEqual(process["progress"], 0.3)
        activity.complete(episode_id="pick_v1:episode-000000")

    def test_server_supports_catalog_and_byte_ranges(self) -> None:
        server = create_server("127.0.0.1", 0, repo_root=self.root)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urlopen(f"{base}/api/catalog", timeout=3) as response:
                payload = json.load(response)
            self.assertEqual(payload["summary"]["episodes"], 1)
            # The explicit historical full-board scene compiles 32 free bodies
            # on its cold compatibility path. The current sparse scene is the
            # interactive default; allow the legacy probe a wider CI budget.
            with urlopen(f"{base}/api/scene?layout=standard", timeout=10) as response:
                scene = json.load(response)
            self.assertEqual(scene["schema_version"], "sim2claw.mujoco_scene_manifest.v1")
            self.assertFalse(scene["authority"]["physical_authority"])
            self.assertNotIn("scene_synthesis", scene)
            with urlopen(f"{base}/api/scene-synthesis", timeout=3) as response:
                synthesis = json.load(response)
            self.assertEqual(
                synthesis["schema_version"],
                "sim2claw.studio_scene_synthesis_proposal.v1",
            )
            self.assertEqual(synthesis["proposal"]["hierarchy"]["id"], "workcell")
            self.assertEqual(len(synthesis["proposal_sha256"]), 64)
            proposal = synthesis["proposal"]
            provenance = proposal["provenance"]
            self.assertEqual(
                hashlib.sha256(provenance["prompt"].encode("utf-8")).hexdigest(),
                provenance["prompt_sha256"],
            )
            proposal_output = json.dumps(
                {
                    "analysis": proposal["analysis"],
                    "hierarchy": proposal["hierarchy"],
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            self.assertEqual(
                hashlib.sha256(proposal_output).hexdigest(),
                provenance["output_sha256"],
            )
            self.assertFalse(
                proposal["analysis"]["evidence_views"][0][
                    "hash_verifiable_in_repository"
                ]
            )
            self.assertFalse(proposal["representations"]["json_compiles_or_drives_geometry"])
            self.assertFalse(
                synthesis["authority"]["included_in_mujoco_manifest_revision"]
            )
            with urlopen(
                f"{base}{scene['meshes'][0]['asset_url']}", timeout=3
            ) as response:
                mesh = response.read()
            self.assertGreater(len(mesh), 1000)
            with urlopen(f"{base}/api/recorder", timeout=3) as response:
                recorder = json.load(response)
            self.assertEqual(
                recorder["schema_version"],
                "sim2claw.teleop_recorder_state.v1",
            )
            with urlopen(
                f"{base}/api/recorder/live-simulation", timeout=3
            ) as response:
                live_simulation = json.load(response)
            self.assertEqual(
                live_simulation["schema_version"],
                "sim2claw.live_simulation_recorder.v1",
            )
            self.assertFalse(live_simulation["active"])
            self.assertEqual(
                live_simulation["scene_url"],
                "/api/scene?layout=sparse_two_sided_pawns",
            )
            self.assertFalse(
                live_simulation["authority"]["physical_authority"]
            )
            preflight_request = Request(
                f"{base}/api/recorder/preflight",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(preflight_request, timeout=3) as response:
                preflight = json.load(response)
            self.assertTrue(preflight["ok"])
            self.assertEqual(
                preflight["recorder"]["preflight"]["required_physical_path"],
                "sim2claw.so101_physical_gateway.v2",
            )
            token = payload["episodes"][0]["media"]["url"].split("/")[-1]
            request = Request(f"{base}/media/{token}", headers={"Range": "bytes=2-5"})
            with urlopen(request, timeout=3) as response:
                self.assertEqual(response.status, 206)
                self.assertEqual(response.read(), b"2345")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_read_only_rejection_closes_connection_before_unread_body(self) -> None:
        server = create_server("127.0.0.1", 0, repo_root=self.root, read_only=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        try:
            with socket.create_connection((host, port), timeout=3) as connection:
                connection.sendall(
                    b"POST /api/recorder/start HTTP/1.1\r\n"
                    b"Host: localhost\r\n"
                    b"Content-Type: application/json\r\n"
                    b"Content-Length: 2\r\n"
                    b"Connection: keep-alive\r\n"
                    b"\r\n"
                    b"{}"
                    b"GET /api/health HTTP/1.1\r\n"
                    b"Host: localhost\r\n"
                    b"Connection: close\r\n"
                    b"\r\n"
                )
                response = bytearray()
                while chunk := connection.recv(4096):
                    response.extend(chunk)

            raw_response = bytes(response)
            self.assertTrue(raw_response.startswith(b"HTTP/1.1 403 Forbidden\r\n"))
            self.assertIn(b"Connection: close\r\n", raw_response)
            self.assertEqual(raw_response.count(b"HTTP/1.1 "), 1)
            self.assertNotIn(b'"service":"sim2claw-studio"', raw_response)

            with urlopen(f"http://{host}:{port}/api/health", timeout=3) as health:
                payload = json.load(health)
            self.assertTrue(payload["read_only"])
            self.assertEqual(payload["recorder_control"], "disabled")
            self.assertEqual(payload["live_workspace"], "disabled")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_server_serves_redesigned_frontend_and_local_fonts(self) -> None:
        server = create_server("127.0.0.1", 0, repo_root=self.root)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urlopen(f"{base}/", timeout=3) as response:
                html = response.read().decode("utf-8")
                content_security_policy = response.headers.get(
                    "Content-Security-Policy", ""
                )
            self.assertIn('data-view="replay"', html)
            self.assertIn('id="timeline-shell"', html)
            self.assertIn('id="mobile-nav-toggle"', html)
            self.assertIn('aria-controls="studio-view-switch"', html)
            self.assertIn('id="transport-phase"', html)
            self.assertIn('id="mobile-browser-label"', html)
            self.assertIn('id="process-drawer"', html)
            self.assertIn('data-view-panel="record"', html)
            self.assertIn('id="start-recording"', html)
            self.assertIn('id="record-camera"', html)
            self.assertIn('id="record-source-square"', html)
            self.assertIn('id="pawn-preview-board"', html)
            self.assertIn('id="pawn-board-instruction"', html)
            self.assertIn('role="group"', html)
            self.assertIn('id="sync-follower"', html)
            self.assertIn('id="three-canvas"', html)
            self.assertIn('id="comparison-lane-strip"', html)
            self.assertIn('id="visual-twin-canvas"', html)
            self.assertIn("Same-camera · no physics", html)
            self.assertIn("Studio will not invent one.", html)
            self.assertIn('data-route="calibration"', html)
            self.assertIn('id="calibration-canvas"', html)
            self.assertIn('id="recording-feed-switch"', html)
            self.assertIn('src="/studio3dgs.js"', html)
            self.assertIn("Robo Scanner + LLM scene inputs", html)
            self.assertIn(
                '<h1 id="calibration-heading">Scene input artifacts</h1>', html
            )
            self.assertIn('id="calibration-scene-toggle"', html)
            self.assertIn(
                'aria-pressed="false">Show reviewed geometry</button>', html
            )
            self.assertNotIn('id="calibration-frame-toggle"', html)
            self.assertNotIn('class="calibration-ruler', html)
            self.assertNotIn('class="calibration-crosshair', html)
            self.assertNotIn('class="calibration-axis-key', html)
            self.assertIn('id="scene-synthesis-status"', html)
            self.assertIn('id="scene-hierarchy"', html)
            self.assertIn("this JSON is not compiled, promoted, or used to drive either geometry layer", html)
            self.assertIn('id="live-simulation-canvas"', html)
            self.assertIn('id="live-simulation-status"', html)
            self.assertIn('id="live-workspace-drawer"', html)
            self.assertIn('id="live-workspace-canvas"', html)
            self.assertIn('data-camera-id="d405-wrist"', html)
            self.assertIn('data-camera-id="logitech-overhead"', html)
            self.assertIn('data-camera-id="logitech-workspace"', html)
            self.assertIn('class="live-camera-slot"', html)
            self.assertIn("Live streams", html)
            self.assertNotIn("Three physical views", html)
            self.assertNotIn("Metric depth, intrinsics, AprilTag pose", html)
            self.assertIn('src="/studio3d.js"', html)
            self.assertIn('src="/assets/workcell/studio-left.png"', html)
            self.assertIn('src="/assets/workcell/studio-right.png"', html)
            self.assertIn('<span id="pawn-preview-source">B1</span>', html)
            self.assertIn("canonical brown-pawn pattern A2, B1, C2", html)
            self.assertIn("Physical recording uses the reverse lower-side pattern A1, B2, C1", html)
            self.assertIn('<span id="pawn-preview-target">B2</span>', html)
            self.assertIn("tan pawns mirrored on A8, B7, C8", html)
            self.assertNotIn('id="record-piece"', html)
            self.assertIn("script-src 'self' 'wasm-unsafe-eval'", content_security_policy)
            self.assertIn("worker-src 'self' blob:", content_security_policy)

            with urlopen(f"{base}/studio.css", timeout=3) as response:
                css = response.read().decode("utf-8")
            self.assertIn('@font-face', css)
            self.assertIn('--motion: #ff5a1f', css)
            self.assertIn('@media (max-width: 1080px)', css)
            self.assertIn('scroll-behavior: auto', css)
            self.assertIn('data-recorder-status="awaiting_label"', css)
            self.assertIn('.pawn-board-cell.is-selectable', css)
            self.assertNotIn('.calibration-crosshair', css)
            self.assertNotIn('.calibration-ruler', css)
            self.assertNotIn('.calibration-axis-key', css)
            self.assertIn('.scene-synthesis-card', css)
            self.assertIn('.scene-hierarchy', css)
            self.assertIn('.recording-feed-switch', css)
            self.assertIn('/* Phone layout: the replay is an evidence instrument', css)
            self.assertIn('.masthead.nav-open .view-switch', css)
            self.assertIn('.transport-phase', css)
            self.assertIn('.comparison-lane-strip', css)
            self.assertIn('.physics-unavailable', css)
            self.assertIn('height: min(43dvh, 360px)', css)
            self.assertIn('left: calc(50% + 6px)', css)

            with urlopen(f"{base}/studio.js", timeout=3) as response:
                javascript = response.read().decode("utf-8")
            self.assertIn("document.body.dataset.recorderStatus = status", javascript)
            self.assertIn('"C922 REC"', javascript)
            self.assertIn('sim2claw.recorder.settings.v3', javascript)
            self.assertIn('lowerTwoRowSquares', javascript)
            self.assertIn('recordBrownPawnSquares', javascript)
            self.assertIn('recordTanPawnSquares', javascript)
            self.assertIn('reverse_sparse_lower_v1', javascript)
            self.assertIn('recorderSourceSquares()', javascript)
            self.assertIn('recorderDestinationSquares()', javascript)
            self.assertIn('pawnBoardSelectionStep: "source"', javascript)
            self.assertIn('selectPawnBoardSquare(cell.dataset.square)', javascript)
            self.assertIn('postRecorder("gateway-sync"', javascript)
            self.assertIn("server_owned_prestart_sequence: physical", javascript)
            self.assertIn("new AbortController()", javascript)
            self.assertNotIn("for (const count of [3, 2, 1])", javascript)
            self.assertIn('episode.inspection?.kind === "threejs_state_trace"', javascript)
            self.assertIn('episodeRecordingFeeds(episode)', javascript)
            self.assertNotIn('const mobileStack =', javascript)
            self.assertIn('window.Sim2ClawCalibration?.setActive', javascript)
            self.assertIn('episode.evaluator_verdict ? "Evaluator result" : "Evidence status"', javascript)
            self.assertIn('"Operator notes"', javascript)
            self.assertIn('fetch("/api/recorder/live-simulation"', javascript)
            self.assertIn("viewer.applyLiveState(liveState)", javascript)
            self.assertIn('elements.mobileNavToggle?.addEventListener', javascript)
            self.assertIn('elements.mobileBrowserLabel', javascript)
            self.assertIn('elements.transportPhase', javascript)
            self.assertIn('elements.browserRail.dataset.taskId', javascript)
            self.assertIn('"Ranked replays"', javascript)
            self.assertIn("sim2claw.studio_episode_comparison.v1", javascript)
            self.assertNotIn("VISUAL TWIN · IMAGE SPACE", javascript)
            self.assertIn("startVisualTwinLoop()", javascript)
            self.assertNotIn("elements.physicsUnavailable.innerHTML", javascript)

            with urlopen(f"{base}/studio3d.js", timeout=3) as response:
                replay_javascript = response.read().decode("utf-8")
            self.assertIn("portraitInspection", replay_javascript)
            self.assertIn("addScaledVector(portraitOffset, 0.96)", replay_javascript)
            self.assertIn("photoBackground.visible = !portraitInspection", replay_javascript)
            self.assertIn("portraitInspection ? 0xd7d7d5 : 0x111315", replay_javascript)

            spark_license = (STATIC_ROOT / "vendor" / "spark" / "LICENSE").read_bytes()
            self.assertEqual(
                hashlib.sha256(spark_license).hexdigest(),
                "51829693e5dccd9ca1daa093991faac3aaa93238eb8fd5f5cb4130af85791d64",
            )
            self.assertIn(b"WORLD LABS TECHNOLOGIES, INC.", spark_license)
            spark_source = (
                STATIC_ROOT / "vendor" / "spark" / "SOURCE.md"
            ).read_text(encoding="utf-8")
            self.assertIn("@sparkjsdev/spark", spark_source)
            self.assertIn("Adoption reason", spark_source)
            three_source = (
                STATIC_ROOT / "vendor" / "three" / "SOURCE.md"
            ).read_text(encoding="utf-8")
            self.assertIn("three add-ons", three_source)
            self.assertIn("postprocessing/Pass.js", three_source)
            self.assertIn("refreshLiveSimulation(), 50", javascript)
            self.assertIn('fetch("/api/live/session"', javascript)
            self.assertIn("/api/live/cameras/", javascript)
            self.assertIn("stopLiveCameraStreams()", javascript)
            self.assertIn("refreshLiveWorkspace(), 100", javascript)
            self.assertNotIn("window.confirm", javascript)

            with urlopen(f"{base}/studio3dgs.js", timeout=3) as response:
                calibration_javascript = response.read().decode("utf-8")
            self.assertNotIn("new THREE.GridHelper", calibration_javascript)
            self.assertNotIn("new THREE.AxesHelper", calibration_javascript)
            self.assertIn("this.sceneOverlay.visible = false", calibration_javascript)
            self.assertIn('"Show reviewed geometry"', calibration_javascript)

            font_path = (
                f"{base}/assets/fonts/"
                "barlow-semi-condensed-latin-600-normal.woff2"
            )
            with urlopen(font_path, timeout=3) as response:
                font = response.read()
                content_type = response.headers.get_content_type()
            self.assertEqual(content_type, "font/woff2")
            self.assertGreater(len(font), 20_000)

            with urlopen(
                f"{base}/assets/workcell/studio-overview.png", timeout=3
            ) as response:
                poster = response.read()
                poster_type = response.headers.get_content_type()
            self.assertEqual(poster_type, "image/png")
            self.assertGreater(len(poster), 50_000)

            with urlopen(
                f"{base}/assets/workcell/studio-mug.png", timeout=3
            ) as response:
                mug_poster = response.read()
                mug_poster_type = response.headers.get_content_type()
            self.assertEqual(mug_poster_type, "image/png")
            self.assertGreater(len(mug_poster), 20_000)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_gateway_failure_returns_stable_json_error(self) -> None:
        server = create_server("127.0.0.1", 0, repo_root=self.root)

        def fail_sync(_payload: dict[str, object]) -> dict[str, object]:
            raise PhysicalGatewayError("fixture sync guard refused motion")

        server.recorder.synchronize_physical_gateway = fail_sync  # type: ignore[method-assign]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        request = Request(
            f"{base}/api/recorder/gateway-sync",
            data=json.dumps({"physical_safety_acknowledged": True}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.assertRaises(HTTPError) as raised:
                urlopen(request, timeout=3)
            self.assertEqual(raised.exception.code, 400)
            payload = json.loads(raised.exception.read().decode("utf-8"))
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error"], "fixture sync guard refused motion")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_versioned_studio_posters_match_current_scene_sources(self) -> None:
        receipt = json.loads(
            (STUDIO_ASSET_ROOT / "receipt.json").read_text(encoding="utf-8")
        )
        sources = receipt["sources"]
        self.assertEqual(
            receipt["piece_layout_id"],
            "two_sided_sparse_pawns_rows_1_2_7_8_v1",
        )
        scene_path = Path(studio_assets.__file__).with_name("scene.py")
        mass_profile_path = Path(studio_assets.__file__).with_name(
            "mass_profile.py"
        )
        expected = {
            "scene_py_sha256": hashlib.sha256(scene_path.read_bytes()).hexdigest(),
            "mass_profile_py_sha256": hashlib.sha256(
                mass_profile_path.read_bytes()
            ).hexdigest(),
            "capture_config_sha256": hashlib.sha256(
                DEFAULT_CAPTURE_CONFIG.read_bytes()
            ).hexdigest(),
            "so101_mass_profile_sha256": hashlib.sha256(
                DEFAULT_SO101_MASS_PROFILE.read_bytes()
            ).hexdigest(),
            "so101_model_sha256": hashlib.sha256(
                SO101_MODEL_PATH.read_bytes()
            ).hexdigest(),
        }
        self.assertEqual(sources, expected)
        self.assertEqual(
            [artifact["camera"] for artifact in receipt["artifacts"]],
            ["studio_overview", "studio_left", "studio_right", "studio_mug"],
        )
        for artifact in receipt["artifacts"]:
            path = STUDIO_ASSET_ROOT / artifact["path"]
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                artifact["sha256"],
            )


if __name__ == "__main__":
    unittest.main()

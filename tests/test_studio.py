from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sim2claw import studio_assets
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
from sim2claw.studio_server import create_server


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

    def test_server_serves_redesigned_frontend_and_local_fonts(self) -> None:
        server = create_server("127.0.0.1", 0, repo_root=self.root)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urlopen(f"{base}/", timeout=3) as response:
                html = response.read().decode("utf-8")
            self.assertIn('data-view="replay"', html)
            self.assertIn('id="timeline-shell"', html)
            self.assertIn('id="process-drawer"', html)
            self.assertIn('data-view-panel="record"', html)
            self.assertIn('id="start-recording"', html)
            self.assertIn('id="record-camera"', html)
            self.assertIn('id="record-source-square"', html)
            self.assertIn('id="pawn-preview-board"', html)
            self.assertIn('id="sync-follower"', html)
            self.assertIn('id="three-canvas"', html)
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
            self.assertIn('<span id="pawn-preview-source">C8</span>', html)
            self.assertIn('<span id="pawn-preview-target">C6</span>', html)
            self.assertIn("Tan pawns begin at A8", html)
            self.assertNotIn('id="record-piece"', html)

            with urlopen(f"{base}/studio.css", timeout=3) as response:
                css = response.read().decode("utf-8")
            self.assertIn('@font-face', css)
            self.assertIn('--motion: #ff5a1f', css)
            self.assertIn('@media (max-width: 1080px)', css)
            self.assertIn('scroll-behavior: auto', css)
            self.assertIn('data-recorder-status="awaiting_label"', css)

            with urlopen(f"{base}/studio.js", timeout=3) as response:
                javascript = response.read().decode("utf-8")
            self.assertIn("document.body.dataset.recorderStatus = status", javascript)
            self.assertIn('"C922 REC"', javascript)
            self.assertIn('sim2claw.recorder.settings.v2', javascript)
            self.assertIn('postRecorder("gateway-sync"', javascript)
            self.assertIn("server_owned_prestart_sequence: physical", javascript)
            self.assertIn("new AbortController()", javascript)
            self.assertNotIn("for (const count of [3, 2, 1])", javascript)
            self.assertIn('episode.inspection?.kind === "threejs_state_trace"', javascript)
            self.assertIn('"Operator notes"', javascript)
            self.assertIn('fetch("/api/recorder/live-simulation"', javascript)
            self.assertIn("viewer.applyLiveState(liveState)", javascript)
            self.assertIn("refreshLiveSimulation(), 50", javascript)
            self.assertIn('fetch("/api/live/session"', javascript)
            self.assertIn("/api/live/cameras/", javascript)
            self.assertIn("stopLiveCameraStreams()", javascript)
            self.assertIn("refreshLiveWorkspace(), 100", javascript)
            self.assertNotIn("window.confirm", javascript)

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

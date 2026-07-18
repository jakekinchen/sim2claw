from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

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
        resolved = resolve_media_token(
            episode["media"]["url"].split("/")[-1],
            self.root,
        )
        self.assertEqual(resolved.name, "episode_000000.mp4")

    def test_media_tokens_cannot_escape_generated_storage(self) -> None:
        outside = self.root / "README.md"
        outside.write_text("private", encoding="utf-8")
        token = media_token(outside, self.root)
        with self.assertRaisesRegex(ValueError, "outside generated artifact storage"):
            resolve_media_token(token, self.root)

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

            with urlopen(f"{base}/studio.css", timeout=3) as response:
                css = response.read().decode("utf-8")
            self.assertIn('@font-face', css)
            self.assertIn('--motion: #ff5a1f', css)

            font_path = (
                f"{base}/assets/fonts/"
                "barlow-semi-condensed-latin-600-normal.woff2"
            )
            with urlopen(font_path, timeout=3) as response:
                font = response.read()
                content_type = response.headers.get_content_type()
            self.assertEqual(content_type, "font/woff2")
            self.assertGreater(len(font), 20_000)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()

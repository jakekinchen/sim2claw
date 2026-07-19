from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import mujoco

from sim2claw.grasp import run_grasp_probe
from sim2claw.scene import (
    CURRENT_TASK_PIECE_LAYOUT,
    TELEOP_PAWN_SOURCE_SQUARES,
    TELEOP_TAN_PAWN_SQUARES,
    build_scene_spec,
    initialize_robot_poses,
)
from sim2claw.state_trace import (
    EpisodeStateTraceRecorder,
    LIVE_STATE_SCHEMA,
    SCENE_MANIFEST_SCHEMA,
    STATE_TRACE_SCHEMA,
    build_scene_manifest,
)


class StateTraceTest(unittest.TestCase):
    def test_scene_manifest_exposes_only_visual_geometry_and_local_meshes(self) -> None:
        manifest = build_scene_manifest()
        self.assertEqual(manifest["schema_version"], SCENE_MANIFEST_SCHEMA)
        self.assertEqual(manifest["model"]["body_count"], len(manifest["bodies"]))
        self.assertEqual({geom["group"] for geom in manifest["geoms"]}, {0, 2})
        self.assertIn("left_base", {body["name"] for body in manifest["bodies"]})
        self.assertIn("right_base", {body["name"] for body in manifest["bodies"]})
        self.assertTrue(
            all(mesh["asset_url"].startswith("/scene-assets/") for mesh in manifest["meshes"])
        )
        self.assertEqual(manifest["authority"]["physics"], "mujoco")
        self.assertFalse(manifest["authority"]["physical_authority"])
        self.assertNotIn("scene_synthesis", manifest)
        self.assertNotIn("scene_synthesis_config", manifest["source"])

    def test_display_proposal_metadata_cannot_change_physics_revision(self) -> None:
        baseline = build_scene_manifest(piece_layout=CURRENT_TASK_PIECE_LAYOUT)
        display_only_proposal = {
            "schema_version": "sim2claw.llm_scene_synthesis.v1",
            "title": "arbitrarily changed display copy",
            "hierarchy": {"id": "different-proposal"},
        }
        self.assertNotIn("scene_synthesis", baseline)
        display_only_proposal["title"] = "changed again"
        rebuilt = build_scene_manifest(piece_layout=CURRENT_TASK_PIECE_LAYOUT)
        self.assertEqual(baseline["revision_sha256"], rebuilt["revision_sha256"])
        self.assertEqual(
            baseline["revision_sha256"],
            "c17fb371f8f798dab4ecb6ed56d9061d1667f8c79dbdaf7c59495f8bd482dd28",
        )

    def test_recorder_samples_mujoco_world_poses_and_writes_compact_trace(self) -> None:
        model = build_scene_spec().compile()
        data = mujoco.MjData(model)
        initialize_robot_poses(model, data)
        recorder = EpisodeStateTraceRecorder(model, fps=30)
        recorder.capture(data, phase="initial", force=True)
        for _ in range(25):
            mujoco.mj_step(model, data)
            recorder.capture(data, phase="advance")
        recorder.capture(data, phase="advance", force=True)
        live = recorder.live_snapshot()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state_trace.json"
            result = recorder.write(path)
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], STATE_TRACE_SCHEMA)
        self.assertGreaterEqual(payload["frame_count"], 4)
        self.assertEqual(len(payload["frames"][0]["p"]), model.nbody * 3)
        self.assertEqual(len(payload["frames"][0]["q"]), model.nbody * 4)
        self.assertEqual(payload["authority"]["pose_source"], "mujoco.MjData.xpos+xquat")
        self.assertFalse(payload["authority"]["physical_authority"])
        self.assertEqual(len(result["sha256"]), 64)
        self.assertEqual(live["schema_version"], LIVE_STATE_SCHEMA)
        self.assertEqual(live["frame_index"], payload["frame_count"] - 1)
        self.assertEqual(live["frame"]["p"], payload["frames"][-1]["p"])

    def test_grasp_probe_emits_smooth_state_trace_alongside_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = run_grasp_probe(
                output_root=Path(temporary),
                render_frames=False,
            )
            trace_path = Path(report.artifacts["state_trace"])
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
            receipt = json.loads(
                Path(report.artifacts["receipt"]).read_text(encoding="utf-8")
            )
        self.assertTrue(report.success)
        self.assertGreater(trace["frame_count"], 250)
        self.assertGreater(trace["duration_seconds"], 9.0)
        self.assertEqual(trace["scene"]["piece_layout"], CURRENT_TASK_PIECE_LAYOUT)
        pawn_names = {
            name
            for name in trace["body_names"]
            if name.startswith(("brown_pawn_", "tan_pawn_"))
        }
        self.assertEqual(
            pawn_names,
            {
                *(f"brown_pawn_{square}" for square in TELEOP_PAWN_SOURCE_SQUARES),
                *(f"tan_pawn_{square}" for square in TELEOP_TAN_PAWN_SQUARES),
            },
        )
        self.assertNotIn("black_rook_a8", trace["body_names"])
        self.assertEqual(receipt["artifacts"]["state_trace"], str(trace_path))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sim2claw.demo_loop_controller import DemoLoopController


class DemoLoopControllerTest(unittest.TestCase):
    def test_controller_runs_fixed_loop_in_background_and_reports_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            capture_calls: list[str] = []

            def capture(camera_id: str):
                capture_calls.append(camera_id)
                return {"camera_id": camera_id, "body": b"jpeg", "captured_at": "now"}

            controller = DemoLoopController(root, camera_capture=capture)

            def fake_run(_repo_root: Path, **kwargs):
                self.assertEqual(kwargs["checkpoint_mode"], "final_only")
                checkpoint = kwargs["checkpoint"](root / "attempt" / "frames" / "000.jpg")
                kwargs["progress"]({"event": "move_completed", "sequence": 12, "move_id": "g1_to_g2"})
                return {"attempt_directory": str(root / "attempt"), "checkpoint": checkpoint}

            with (
                patch("sim2claw.demo_loop_controller.build_loop_plan", return_value={}),
                patch("sim2claw.demo_loop_controller.run_owner_directed_base_loop", side_effect=fake_run),
            ):
                state = controller.start()
                self.assertIn(state["status"], {"running", "completed"})
                assert controller.thread is not None
                controller.thread.join(timeout=2)

            completed = controller.snapshot()
            self.assertEqual(completed["status"], "completed")
            self.assertEqual(completed["completed_moves"], 12)
            self.assertEqual(completed["attempt_directory"], str(root / "attempt"))
            self.assertEqual(capture_calls, ["logitech-overhead"])
            self.assertFalse(completed["task_success_verified"])

    def test_directional_action_selects_six_moves(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            controller = DemoLoopController(
                root,
                camera_capture=lambda camera_id: {"camera_id": camera_id, "body": b"jpeg"},
            )
            observed_move_counts: list[int] = []

            def fake_run(_repo_root: Path, **kwargs):
                observed_move_counts.append(len(kwargs["moves"]))
                return {"attempt_directory": str(root / "attempt")}

            with (
                patch("sim2claw.demo_loop_controller.build_loop_plan", return_value={}),
                patch("sim2claw.demo_loop_controller.run_owner_directed_base_loop", side_effect=fake_run),
            ):
                controller.start_action("base_to_inverse")
                assert controller.thread is not None
                controller.thread.join(timeout=2)

            state = controller.snapshot()
            self.assertEqual(observed_move_counts, [6])
            self.assertEqual(state["action"], "base_to_inverse")
            self.assertEqual(state["total_moves"], 6)
            self.assertEqual(state["completed_moves"], 6)


if __name__ == "__main__":
    unittest.main()

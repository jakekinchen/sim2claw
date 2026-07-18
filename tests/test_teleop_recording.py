from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from sim2claw.teleop_recording import (
    RecorderError,
    TeleopRecordingManager,
    discover_so101_devices,
)
from sim2claw.scene import CURRENT_TASK_LAYOUT_ID


class FakeBackend:
    def __init__(self, request: dict[str, Any], _preflight: dict[str, Any]):
        self.request = request
        self.closed = False
        self.sample_index = 0

    def open(self) -> dict[str, Any]:
        return {
            "proof_class": "simulation_teleoperation_source_fixture",
            "leader_port": "fixture-leader",
            "follower": "fixture-simulator",
            "physical_follower_torque_enabled": False,
            "pose_inputs_available": True,
        }

    def sample(self, elapsed_seconds: float) -> dict[str, Any]:
        self.sample_index += 1
        positions = [self.sample_index / 100.0] * 6
        return {
            "elapsed_seconds": elapsed_seconds,
            "leader_target_degrees": [0.0] * 6,
            "follower_command_rad": positions,
            "follower_actual_position_rad": positions,
            "follower_actual_velocity_rad_s": [0.0] * 6,
            "leader_follower_error_rad": [0.0] * 6,
            "selected_piece_pose_world": [0.0, 0.0, 0.1, 1.0, 0.0, 0.0, 0.0],
            "continuous_target_pose_world": [0.1, 0.1, 0.1, 1.0, 0.0, 0.0, 0.0],
            "pose_inputs_available": True,
            "available_motor_current": None,
            "physical_follower_torque_enabled": False,
        }

    def close(self) -> None:
        self.closed = True


class FakeVideoRecorder:
    def __init__(self, draft: Path):
        self.output_path = draft / "overhead_c922.mp4"
        self.log_path = draft / "overhead_c922.ffmpeg.log"
        self.started_monotonic: float | None = None
        self.finished = False

    def start(self) -> dict[str, Any]:
        self.started_monotonic = time.monotonic()
        self.output_path.write_bytes(b"fixture-c922-video")
        self.log_path.write_text("fixture camera log\n", encoding="utf-8")
        return {
            "schema_version": "sim2claw.overhead_diagnostic_video.v1",
            "status": "recording",
            "camera_name": "C922 Pro Stream Webcam",
            "configured_width": 640,
            "configured_height": 480,
            "configured_fps": 30,
            "diagnostic_only": True,
            "is_training_data": False,
        }

    def ensure_running(self) -> None:
        return

    def finish(
        self,
        *,
        action_started_monotonic: float | None,
        action_stopped_monotonic: float | None,
        post_roll_seconds: float,
    ) -> dict[str, Any]:
        self.finished = True
        assert self.started_monotonic is not None
        return {
            "schema_version": "sim2claw.overhead_diagnostic_video.v1",
            "status": "completed",
            "camera_name": "C922 Pro Stream Webcam",
            "configured_width": 640,
            "configured_height": 480,
            "configured_fps": 30,
            "video_path": "overhead_c922.mp4",
            "ffmpeg_log_path": "overhead_c922.ffmpeg.log",
            "action_start_video_offset_seconds": (
                action_started_monotonic - self.started_monotonic
                if action_started_monotonic is not None
                else None
            ),
            "action_stop_video_offset_seconds": (
                action_stopped_monotonic - self.started_monotonic
                if action_stopped_monotonic is not None
                else None
            ),
            "post_roll_seconds_configured": post_roll_seconds,
            "post_roll_seconds_observed": post_roll_seconds,
            "diagnostic_only": True,
            "is_training_data": False,
        }


class TeleopRecordingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        temporary_root = Path(self.temporary.name)
        self.repo_root = temporary_root / "repo"
        self.dev_root = temporary_root / "dev"
        self.calibration_root = temporary_root / "calibration"
        self.repo_root.mkdir()
        self.dev_root.mkdir()
        (self.dev_root / "cu.usbmodem5B3D0448141").touch()
        (self.dev_root / "cu.usbmodem5B3D0406411").touch()
        (self.dev_root / "cu.usbmodemSN234567892").touch()
        leader_calibration = (
            self.calibration_root
            / "teleoperators"
            / "so_leader"
            / "so101_leader.json"
        )
        follower_calibration = (
            self.calibration_root
            / "robots"
            / "so_follower"
            / "so101_follower.json"
        )
        leader_calibration.parent.mkdir(parents=True)
        follower_calibration.parent.mkdir(parents=True)
        leader_calibration.write_text("{}\n", encoding="utf-8")
        follower_calibration.write_text("{}\n", encoding="utf-8")
        self.backends: list[FakeBackend] = []
        self.videos: list[FakeVideoRecorder] = []

        def factory(request: dict[str, Any], preflight: dict[str, Any]) -> FakeBackend:
            backend = FakeBackend(request, preflight)
            self.backends.append(backend)
            return backend

        def video_factory(draft: Path) -> FakeVideoRecorder:
            video = FakeVideoRecorder(draft)
            self.videos.append(video)
            return video

        self.manager = TeleopRecordingManager(
            repo_root=self.repo_root,
            backend_factory=factory,
            video_recorder_factory=video_factory,
            dev_root=self.dev_root,
            calibration_root=self.calibration_root,
        )

    def tearDown(self) -> None:
        self.manager.shutdown()
        self.temporary.cleanup()

    def test_discovery_assigns_expected_buses_and_ignores_billboard(self) -> None:
        devices = discover_so101_devices(self.dev_root)
        self.assertTrue(devices["leader"]["connected"])
        self.assertTrue(devices["follower"]["connected"])
        self.assertEqual(len(devices["ignored_billboard_ports"]), 1)
        self.assertEqual(devices["unknown_serial_ports"], [])

    def test_sim_record_stop_and_label_writes_raw_source_receipt(self) -> None:
        started = self.manager.start(
            {
                "mode": "simulation_follower",
                "source_square": "a2",
                "target_square": "c3",
                "sample_hz": 20,
            }
        )
        self.assertEqual(started["status"], "recording")
        deadline = time.monotonic() + 2
        while self.manager.snapshot()["sample_count"] < 2 and time.monotonic() < deadline:
            time.sleep(0.02)
        stopped = self.manager.stop()
        self.assertEqual(stopped["status"], "awaiting_label")
        self.assertGreaterEqual(stopped["sample_count"], 2)
        saved = self.manager.finalize(
            {
                "label": "Pawn A2 to C3 clean lift",
                "skill": "grasp_lift",
                "outcome": "success",
                "notes": "Fixture only.",
            }
        )
        self.assertEqual(saved["status"], "saved")
        destination = self.repo_root / saved["saved_path"]
        rows = [
            json.loads(line)
            for line in (destination / "samples.jsonl").read_text().splitlines()
        ]
        receipt = json.loads((destination / "recording_receipt.json").read_text())
        self.assertGreaterEqual(len(rows), 2)
        self.assertEqual(receipt["outcome_label"], "success")
        self.assertEqual(
            receipt["training_admission"],
            "pending_deterministic_replay_and_separate_evaluator",
        )
        self.assertFalse(receipt["is_training_data"])
        self.assertFalse(receipt["held_out_membership"])
        self.assertEqual(receipt["piece_id"], "brown_pawn_a2")
        self.assertEqual(receipt["source_square"], "a2")
        self.assertEqual(receipt["destination_square"], "c3")
        self.assertEqual(receipt["initial_layout_id"], CURRENT_TASK_LAYOUT_ID)
        self.assertIn("overhead_video_time_seconds", rows[0])
        self.assertEqual(
            receipt["overhead_video"]["camera_name"],
            "C922 Pro Stream Webcam",
        )
        self.assertTrue(receipt["overhead_video"]["diagnostic_only"])
        self.assertFalse(receipt["overhead_video"]["is_training_data"])
        self.assertTrue((destination / "overhead_c922.mp4").is_file())
        self.assertTrue((destination / "overhead_video.json").is_file())
        self.assertTrue(self.videos[0].finished)
        self.assertTrue(self.backends[0].closed)

    def test_physical_mode_is_ready_but_requires_operator_acknowledgement(self) -> None:
        preflight = self.manager.preflight()
        self.assertTrue(preflight["modes"]["physical_follower"]["device_ready"])
        self.assertTrue(preflight["modes"]["physical_follower"]["ready"])
        with self.assertRaisesRegex(RecorderError, "acknowledgement"):
            self.manager.start(
                {
                    "mode": "physical_follower",
                    "source_square": "a2",
                    "target_square": "c3",
                    "sample_hz": 20,
                    "physical_safety_acknowledged": False,
                }
            )

    def test_legacy_error_state_returns_to_ready_automatically_on_start(self) -> None:
        self.manager.state = {
            **self.manager._idle_state(),
            "status": "error",
            "draft_path": None,
            "error": "fixture",
        }
        started = self.manager.start(
            {
                "mode": "simulation_follower",
                "source_square": "a2",
                "target_square": "c3",
                "sample_hz": 20,
            }
        )
        self.assertEqual(started["status"], "recording")
        self.manager.stop()
        self.manager.discard()

    def test_runtime_failure_is_archived_and_recorder_returns_to_ready(self) -> None:
        class FailingBackend(FakeBackend):
            def sample(self, elapsed_seconds: float) -> dict[str, Any]:
                raise RuntimeError("fixture gateway fault")

        self.manager.shutdown()
        self.manager = TeleopRecordingManager(
            repo_root=self.repo_root,
            backend_factory=lambda request, preflight: FailingBackend(request, preflight),
            video_recorder_factory=lambda draft: FakeVideoRecorder(draft),
            dev_root=self.dev_root,
            calibration_root=self.calibration_root,
        )
        try:
            self.manager.start(
                {
                    "mode": "simulation_follower",
                    "source_square": "b1",
                    "target_square": "b2",
                    "sample_hz": 20,
                }
            )
        except RecorderError as error:
            # The worker can fail before start() observes its initial state.
            self.assertIn("fixture gateway fault", str(error))
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            thread = self.manager.thread
            if self.manager.snapshot()["status"] == "idle" and (
                thread is None or not thread.is_alive()
            ):
                break
            time.sleep(0.01)
        state = self.manager.snapshot()
        self.assertEqual(state["status"], "idle")
        self.assertIn("fixture gateway fault", state["last_error"])
        self.assertTrue((self.repo_root / state["last_failed_attempt_path"]).is_dir())

    def test_sync_requires_safety_ack_and_retains_torque_off_report(self) -> None:
        with self.assertRaisesRegex(RecorderError, "acknowledgement"):
            self.manager.synchronize_physical_gateway({})
        report = {
            "passed": True,
            "paired_pose_registration_ready": True,
            "physical_follower_torque_enabled": False,
        }
        with patch(
            "sim2claw.teleop_recording.physical_gateway_sync",
            return_value=report,
        ):
            state = self.manager.synchronize_physical_gateway(
                {"physical_safety_acknowledged": True}
            )
        self.assertEqual(state["physical_gateway_sync"], report)
        self.assertFalse(state["physical_gateway_sync"]["physical_follower_torque_enabled"])

    def test_physical_mode_requires_prestart_countdown(self) -> None:
        with self.assertRaisesRegex(RecorderError, "countdown"):
            self.manager.start(
                {
                    "mode": "physical_follower",
                    "source_square": "a2",
                    "target_square": "c3",
                    "sample_hz": 20,
                    "physical_safety_acknowledged": True,
                    "physical_pose_match_acknowledged": True,
                    "prestart_countdown_completed": False,
                }
            )

    def test_physical_mode_requires_paired_pose_acknowledgement(self) -> None:
        with self.assertRaisesRegex(RecorderError, "Paired physical-pose"):
            self.manager.start(
                {
                    "mode": "physical_follower",
                    "source_square": "a2",
                    "target_square": "c3",
                    "sample_hz": 20,
                    "physical_safety_acknowledged": True,
                    "physical_pose_match_acknowledged": False,
                }
            )

    def test_pawn_metadata_rejects_unknown_source_and_occupied_destination(self) -> None:
        with self.assertRaisesRegex(RecorderError, "eight declared pawn"):
            self.manager.start(
                {
                    "mode": "simulation_follower",
                    "source_square": "a1",
                    "target_square": "b3",
                }
            )
        with self.assertRaisesRegex(RecorderError, "unoccupied destination"):
            self.manager.start(
                {
                    "mode": "simulation_follower",
                    "source_square": "a2",
                    "target_square": "b1",
                }
            )


if __name__ == "__main__":
    unittest.main()

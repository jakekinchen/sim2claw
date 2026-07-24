from __future__ import annotations

import io
import subprocess
import threading
import unittest
from typing import Any

from sim2claw.scene import CURRENT_TASK_PIECE_LAYOUT
from sim2claw.studio_live import (
    LIVE_CAMERA_SCHEMA,
    LIVE_CAMERAS,
    LIVE_WORKSPACE_SCHEMA,
    LiveWorkspaceService,
    PhysicalPoseMirror,
    _camera_rows,
)


def _camera_inventory() -> dict[str, Any]:
    return {
        "schema_version": LIVE_CAMERA_SCHEMA,
        "checked_at": "fixture",
        "ffmpeg_path": "/fixture/ffmpeg",
        "error": None,
        "cameras": _camera_rows(
            [
                {
                    "index": 2,
                    "name": "Intel(R) RealSense(TM) Depth Camera 405  Depth",
                },
                {"index": 0, "name": "C922 Pro Stream Webcam"},
                {"index": 3, "name": "USB Camera VID:1133 PID:2075"},
            ]
        ),
    }


class FakeRecorder:
    def __init__(self, *, ready: bool = True) -> None:
        self.lock = threading.RLock()
        self.state = {
            "status": "idle",
            "mode": "simulation_follower",
            "last_sample": None,
            "overhead_video": {"status": "idle"},
            "wrist_video": {"status": "idle"},
        }
        self.ready = ready

    def preflight(self) -> dict[str, Any]:
        return {
            "devices": {
                "leader": {"port": "/dev/leader"},
                "follower": {"port": "/dev/follower"},
            },
            "calibrations": {
                "leader": {"sha256": "a" * 64},
                "follower": {"sha256": "b" * 64},
            },
            "modes": {"physical_follower": {"ready": self.ready}},
        }


class FakeGateway:
    instances: list["FakeGateway"] = []

    def __init__(self, _identity: Any, *, configure_devices: bool) -> None:
        self.configure_devices = configure_devices
        self.closed = False
        self.open_calls: list[bool] = []
        self.__class__.instances.append(self)

    def open(self, *, enable_motion: bool) -> dict[str, Any]:
        self.open_calls.append(enable_motion)
        return {"physical_follower_torque_enabled": False}

    def sample_read_only(self) -> dict[str, Any]:
        return {
            "leader_degrees": [0.0, -10.0, 20.0, -30.0, 40.0, 0.0],
            "follower_degrees": [1.0, -11.0, 21.0, -31.0, 41.0, 5.0],
            "physical_follower_torque_enabled": False,
            "physical_motion_commanded": False,
        }

    def close(self) -> None:
        self.closed = True


class FakeMirror:
    def snapshot(self, values: list[float], *, pose_source: str) -> dict[str, Any]:
        return {
            "active": True,
            "scene_url": "/api/scene?layout=sparse_two_sided_pawns",
            "manifest_revision_sha256": "fixture",
            "follower_degrees": values,
            "authority": {"pose_source": pose_source, "physical_authority": False},
        }


class FakeProcess:
    def __init__(self) -> None:
        self.stdout = io.BytesIO(b"fixture")
        self.returncode: int | None = None
        self.terminated = False

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15

    def kill(self) -> None:
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        return int(self.returncode or 0)


class StudioLiveTest(unittest.TestCase):
    def setUp(self) -> None:
        FakeGateway.instances.clear()

    def test_camera_inventory_uses_stable_roles_and_current_indexes(self) -> None:
        cameras = _camera_inventory()["cameras"]
        self.assertEqual(
            [camera["id"] for camera in cameras],
            ["d405-wrist", "logitech-overhead", "logitech-workspace"],
        )
        self.assertEqual([camera["device_index"] for camera in cameras], [2, 0, 3])
        self.assertTrue(all(camera["available"] for camera in cameras))
        self.assertEqual(cameras[0]["role"], "wrist_gripper_upward")
        self.assertFalse(cameras[0]["metric_depth"])
        self.assertTrue(all(camera["stream_on_demand"] for camera in cameras))
        overhead = next(camera for camera in LIVE_CAMERAS if camera.id == "logitech-overhead")
        self.assertNotIn("hflip", overhead.video_filter)
        self.assertNotIn("vflip", overhead.video_filter)

    def test_pose_mirror_is_kinematic_and_keeps_contact_claim_closed(self) -> None:
        mirror = PhysicalPoseMirror()
        snapshot = mirror.snapshot([0.0, -20.0, 40.0, -10.0, 5.0, 25.0], pose_source="fixture")
        self.assertTrue(snapshot["active"])
        self.assertIn(f"layout={CURRENT_TASK_PIECE_LAYOUT}", snapshot["scene_url"])
        self.assertEqual(snapshot["frame"]["c"], [])
        self.assertEqual(len(snapshot["frame"]["p"]), len(snapshot["body_names"]) * 3)
        self.assertFalse(snapshot["authority"]["physical_authority"])
        self.assertEqual(snapshot["authority"]["physical_contact_state"], "not_observed")

    def test_session_samples_torque_off_and_releases_gateway(self) -> None:
        service = LiveWorkspaceService(
            FakeRecorder(),
            camera_discovery=_camera_inventory,
            gateway_factory=FakeGateway,
        )
        service.mirror = FakeMirror()  # type: ignore[assignment]
        try:
            live = service.start_session()
            self.assertEqual(live["schema_version"], LIVE_WORKSPACE_SCHEMA)
            self.assertEqual(live["arm"]["status"], "live")
            self.assertFalse(live["arm"]["physical_follower_torque_enabled"])
            self.assertFalse(live["authority"]["physical_authority"])
            self.assertTrue(live["simulator"]["active"])
            gateway = FakeGateway.instances[0]
            self.assertFalse(gateway.configure_devices)
            self.assertEqual(gateway.open_calls, [False])
            service.end_session(live["session_id"])
            self.assertTrue(gateway.closed)
        finally:
            service.shutdown()

    def test_camera_process_uses_numeric_index_and_dies_with_expired_lease(self) -> None:
        clock = [10.0]
        commands: list[list[str]] = []
        process = FakeProcess()

        def popen(command: list[str], **_kwargs: Any) -> FakeProcess:
            commands.append(command)
            return process

        service = LiveWorkspaceService(
            FakeRecorder(),
            camera_discovery=_camera_inventory,
            gateway_factory=FakeGateway,
            popen_factory=popen,  # type: ignore[arg-type]
            clock=lambda: clock[0],
        )
        service.mirror = FakeMirror()  # type: ignore[assignment]
        try:
            live = service.start_session()
            opened = service.open_camera("logitech-workspace", live["session_id"])
            self.assertIs(opened, process)
            command = commands[0]
            self.assertEqual(command[command.index("-i") + 1], "3:none")
            self.assertIn("uyvy422", command)
            clock[0] += 6.0
            service.snapshot()
            self.assertTrue(process.terminated)
            self.assertTrue(FakeGateway.instances[0].closed)
        finally:
            service.shutdown()

    def test_recorder_reserves_both_episode_cameras(self) -> None:
        recorder = FakeRecorder()
        recorder.state["overhead_video"]["status"] = "recording"
        recorder.state["wrist_video"]["status"] = "recording"
        service = LiveWorkspaceService(
            recorder,
            camera_discovery=_camera_inventory,
            gateway_factory=FakeGateway,
        )
        try:
            snapshot = service.snapshot()
            self.assertTrue(snapshot["recorder"]["owns_c922"])
            self.assertTrue(snapshot["recorder"]["owns_d405"])
            for camera_id in ("logitech-overhead", "d405-wrist"):
                status = service.camera_source_status(camera_id)
                self.assertTrue(status["busy"])
                self.assertEqual(status["busy_owner"], "recorder")
                with self.assertRaisesRegex(
                    Exception, "recorder currently owns"
                ):
                    session = service.start_session()
                    service.open_camera(camera_id, session["session_id"])
        finally:
            service.shutdown()

    def test_orchestrator_snapshot_uses_the_primary_overhead_inventory_role(self) -> None:
        commands: list[list[str]] = []

        def run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, stdout=b"fixture-jpeg", stderr=b"")

        service = LiveWorkspaceService(
            FakeRecorder(),
            camera_discovery=_camera_inventory,
            gateway_factory=FakeGateway,
            run_factory=run,
        )
        try:
            source = service.camera_source_status("logitech-overhead")
            self.assertTrue(source["ready"])
            self.assertEqual(source["role"], "overhead_workspace")
            captured = service.capture_camera_snapshot("logitech-overhead")
            self.assertEqual(captured["body"], b"fixture-jpeg")
            self.assertEqual(captured["camera_role"], "overhead_workspace")
            command = commands[0]
            self.assertEqual(command[command.index("-i") + 1], "0:none")
            self.assertEqual(command[command.index("-frames:v") + 1], "1")
            inventory = service.orchestrator_inventory()
            self.assertEqual(inventory["primary_camera_id"], "logitech-overhead")
            overhead = next(
                row for row in inventory["cameras"] if row["id"] == "logitech-overhead"
            )
            self.assertTrue(overhead["primary_for_orchestrator"])
            self.assertFalse(inventory["physical_authority"])
        finally:
            service.shutdown()

    def test_first_discovery_renews_lease_from_completed_snapshot(self) -> None:
        clock = [0.0]

        def slow_inventory() -> dict[str, Any]:
            clock[0] += 6.0
            return _camera_inventory()

        service = LiveWorkspaceService(
            FakeRecorder(),
            camera_discovery=slow_inventory,
            gateway_factory=FakeGateway,
            clock=lambda: clock[0],
        )
        service.mirror = FakeMirror()  # type: ignore[assignment]
        try:
            live = service.start_session()
            refreshed = service.snapshot(live["session_id"], sample=True)
            self.assertTrue(refreshed["active"])
            self.assertEqual(refreshed["arm"]["status"], "live")
        finally:
            service.shutdown()

    def test_cold_gateway_handshake_starts_lease_after_open(self) -> None:
        clock = [0.0]

        class SlowGateway(FakeGateway):
            def open(self, *, enable_motion: bool) -> dict[str, Any]:
                clock[0] += 6.0
                return super().open(enable_motion=enable_motion)

        service = LiveWorkspaceService(
            FakeRecorder(),
            camera_discovery=_camera_inventory,
            gateway_factory=SlowGateway,
            clock=lambda: clock[0],
        )
        service.mirror = FakeMirror()  # type: ignore[assignment]
        try:
            live = service.start_session()
            self.assertEqual(live["arm"]["status"], "live")
            self.assertGreater(service.leases[live["session_id"]], clock[0])
        finally:
            service.shutdown()

    def test_offline_status_does_not_open_a_gateway(self) -> None:
        service = LiveWorkspaceService(
            FakeRecorder(ready=False),
            camera_discovery=_camera_inventory,
            gateway_factory=FakeGateway,
        )
        try:
            status = service.snapshot()
            self.assertEqual(status["arm"]["status"], "offline")
            self.assertEqual(FakeGateway.instances, [])
        finally:
            service.shutdown()


if __name__ == "__main__":
    unittest.main()

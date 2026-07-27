from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from sim2claw.physical_canary import EXCITATION_CONTROL_SOURCE, GATEWAY_SCHEMA
from sim2claw.replay_eligibility import action_sha256
from sim2claw.scene import ROBOT_JOINTS
from sim2claw.wrist_view_reposition import (
    CAPTURE_MODE_C922_PI,
    CAPTURE_MODE_TRICAM,
    CAPTURE_HOLD_SAMPLES,
    MAX_STAGE_EXCURSION_DEGREES,
    SAMPLES_PER_STAGE,
    WRIST_VIEW_EXECUTION_SCHEMA,
    WRIST_VIEW_PACKET_SCHEMA,
    WRIST_VIEW_ROUTE_SCHEMA,
    WristViewRepositionError,
    compile_wrist_view_reposition_packet,
    execute_wrist_view_reposition_stage,
    preview_wrist_view_actions,
    review_wrist_view_reposition_packet,
)


PORT = "/dev/follower-fixture"
CALIBRATION = "a" * 64
PI_MOTION_CONTRACT_SHA256 = (
    "457f2c142671851ddd60a3f1be5487125605957e38c1b2730ab683e08488393f"
)
LOWER = np.asarray([-120.263736, -107.5, -102.5, -107.5, -180.0, 0.0])
UPPER = np.asarray([120.263736, 107.5, 102.5, 107.5, 180.0, 100.0])
ROUTE_ANCHOR = np.asarray(
    [-19.6923076923, -52.043956044, 97.8021978022, -15.2527472527, -74.5934065934, 2.9691211401]
)
ROUTE_TARGETS = np.asarray(
    [
        [-20.383827, -64.520994, 31.204886, 74.747, -74.5934065934, 2.9691211401],
        [-20.383827, -64.520994, 31.204886, 90.0, -74.5934065934, 2.9691211401],
    ]
)


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _candidate_manifest(path: Path) -> None:
    joints = []
    for index, name in enumerate(ROBOT_JOINTS):
        simulator_name = f"left_{name}"
        joints.append(
            {
                "source_joint": name,
                "simulator_joint": simulator_name,
                "input_unit": "percent" if index == 5 else "degree",
                "output_unit": "radian",
                "scale": 0.0191986 if index == 5 else np.pi / 180.0,
                "sign": 1,
                "zero_offset": -0.17453 if index == 5 else 0.0,
            }
        )
    _write(
        path,
        {
            "candidate_digest": "b" * 64,
            "candidate_config": {
                "model": {"kind": "current_chess_scene"},
                "bindings": {
                    "joint_names": [f"left_{name}" for name in ROBOT_JOINTS]
                },
                "physical_adapter": {
                    "joint_transform": {
                        "joints": joints,
                    }
                },
            },
        },
    )


def _route(path: Path) -> None:
    _write(
        path,
        {
            "schema_version": WRIST_VIEW_ROUTE_SCHEMA,
            "route_id": "fixture-route",
            "reviewed_anchor_degrees": ROUTE_ANCHOR.tolist(),
            "stage_targets_degrees": ROUTE_TARGETS.tolist(),
        },
    )


def _c922_route(path: Path) -> None:
    _write(
        path,
        {
            "schema_version": WRIST_VIEW_ROUTE_SCHEMA,
            "route_id": "fixture-c922-route",
            "capture_during_motion": True,
            "capture_mode": CAPTURE_MODE_C922_PI,
            "c922_capture": {
                "contract_path": "fixture-c922-contract.json",
                "camera_session_prefix": "fixture-c922-session",
                "fixed_mount_token": "fixture-fixed-mount",
            },
            "reviewed_anchor_degrees": ROUTE_ANCHOR.tolist(),
            "stage_targets_degrees": [ROUTE_TARGETS[0].tolist()],
        },
    )


def _tricam_route(path: Path) -> None:
    _write(
        path,
        {
            "schema_version": WRIST_VIEW_ROUTE_SCHEMA,
            "route_id": "fixture-motion-tricam-route",
            "capture_during_motion": True,
            "capture_mode": CAPTURE_MODE_TRICAM,
            "pi_motion_video": {
                "contract_path": (
                    "configs/acquisition/pi_imx708_motion_video_15s_v1.json"
                ),
                "contract_sha256": PI_MOTION_CONTRACT_SHA256,
            },
            "reviewed_anchor_degrees": ROUTE_ANCHOR.tolist(),
            "stage_targets_degrees": [ROUTE_TARGETS[0].tolist()],
        },
    )


def _tricam_round_trip_route(path: Path) -> None:
    midpoint = ROUTE_ANCHOR.copy()
    midpoint[1] += 4.0
    midpoint[2] -= 5.0
    midpoint[3] += 3.0
    _write(
        path,
        {
            "schema_version": WRIST_VIEW_ROUTE_SCHEMA,
            "route_id": "fixture-motion-tricam-round-trip-route",
            "capture_during_motion": True,
            "capture_mode": CAPTURE_MODE_TRICAM,
            "pi_motion_video": {
                "contract_path": (
                    "configs/acquisition/pi_imx708_motion_video_15s_v1.json"
                ),
                "contract_sha256": PI_MOTION_CONTRACT_SHA256,
            },
            "reviewed_anchor_degrees": ROUTE_ANCHOR.tolist(),
            "stage_waypoints_degrees": [
                [midpoint.tolist(), ROUTE_ANCHOR.tolist()]
            ],
        },
    )


def _setup_recovery_route(path: Path) -> None:
    _write(
        path,
        {
            "schema_version": WRIST_VIEW_ROUTE_SCHEMA,
            "route_id": "fixture-two-stage-setup-recovery-route",
            "setup_recovery_command_anchor_snap_limit_degrees": 3.0,
            "reviewed_anchor_degrees": ROUTE_ANCHOR.tolist(),
            "stage_targets_degrees": ROUTE_TARGETS.tolist(),
            "review_basis": {"physical_scope": "setup_recovery_only"},
        },
    )


def _preflight(
    anchor: np.ndarray = ROUTE_ANCHOR,
) -> dict[str, object]:
    return {
        "passed": True,
        "schema_version": GATEWAY_SCHEMA,
        "control_source": EXCITATION_CONTROL_SOURCE,
        "real_leader_opened": False,
        "follower_port": PORT,
        "follower_calibration_sha256": CALIBRATION,
        "follower_start_degrees": anchor.tolist(),
        "follower_calibrated_minimum": LOWER.tolist(),
        "follower_calibrated_maximum": UPPER.tolist(),
        "physical_follower_torque_enabled": False,
        "device_configuration_rewritten": False,
    }


class _Gateway:
    def __init__(self, anchor: np.ndarray) -> None:
        self.anchor = anchor
        self.samples: list[np.ndarray] = []
        self.closed = False
        self.open_setup_command_anchor_degrees: np.ndarray | None = None

    def open(
        self,
        *,
        enable_motion: bool,
        paired_pose_confirmed: bool,
        setup_command_anchor_degrees: np.ndarray | None = None,
    ) -> dict[str, object]:
        assert enable_motion and paired_pose_confirmed
        self.open_setup_command_anchor_degrees = (
            np.asarray(setup_command_anchor_degrees, dtype=np.float64)
            if setup_command_anchor_degrees is not None
            else None
        )
        return {"follower_start_degrees": self.anchor.tolist()}

    def sample(
        self, timestamp: float, *, exact_requested_degrees: np.ndarray
    ) -> dict[str, object]:
        del timestamp
        self.samples.append(exact_requested_degrees.copy())
        values = exact_requested_degrees.tolist()
        return {
            "follower_requested_degrees": values,
            "follower_command_degrees": values,
            "follower_actual_position_degrees": values,
            "tracking_error_limits": [6.0, 8.0, 6.0, 6.0, 8.0, 12.0],
            "rate_limited": False,
            "safety_clamped": False,
            "stalled": False,
            "stalled_joints": [],
            "assistance": False,
            "intervention": False,
        }

    def close(self) -> None:
        self.closed = True


class _GatewayOpenFailure(_Gateway):
    def open(
        self,
        *,
        enable_motion: bool,
        paired_pose_confirmed: bool,
        setup_command_anchor_degrees: np.ndarray | None = None,
    ) -> dict[str, object]:
        super().open(
            enable_motion=enable_motion,
            paired_pose_confirmed=paired_pose_confirmed,
            setup_command_anchor_degrees=setup_command_anchor_degrees,
        )
        raise RuntimeError("fixture gateway open failure")


class _UnsafeSampleGateway(_Gateway):
    def sample(
        self, timestamp: float, *, exact_requested_degrees: np.ndarray
    ) -> dict[str, object]:
        sample = super().sample(
            timestamp, exact_requested_degrees=exact_requested_degrees
        )
        sample["stalled"] = True
        sample["stalled_joints"] = ["elbow_flex"]
        return sample


class _Capture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.finished = False

    @staticmethod
    def _digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def start(self) -> dict[str, object]:
        self.root.mkdir(parents=True)
        return {"status": "recording"}

    def finish(self, **kwargs: object) -> dict[str, object]:
        del kwargs
        if self.finished:
            raise AssertionError("capture finished twice")
        self.finished = True
        paths = {
            "report": self.root / "report.json",
            "events": self.root / "events.jsonl",
            "overhead_source": self.root / "overhead.mov",
            "overhead_browser": self.root / "overhead.mp4",
            "wrist_source": self.root / "wrist.mov",
            "wrist_browser": self.root / "wrist.mp4",
        }
        _write(paths["report"], {"status": "completed"})
        paths["events"].write_text(
            "\n".join(
                json.dumps(
                    {
                        "role": "d405",
                        "kind": "output",
                        "appended_to_writer": True,
                        "host_continuous_ns": 0,
                        "sequence": index,
                        "pts_seconds": index / 5.0,
                    }
                )
                for index in (1, 2)
            )
            + "\n",
            encoding="utf-8",
        )
        for key in (
            "overhead_source",
            "overhead_browser",
            "wrist_source",
            "wrist_browser",
        ):
            paths[key].write_bytes(key.encode())
        return {
            "common_session": {
                "report_path": paths["report"].name,
                "report_sha256": self._digest(paths["report"]),
                "callback_timestamp_path": paths["events"].name,
                "callback_timestamp_sha256": self._digest(paths["events"]),
            },
            "overhead": {
                "video_path": paths["overhead_source"].name,
                "video_sha256": self._digest(paths["overhead_source"]),
                "browser_video_path": paths["overhead_browser"].name,
                "browser_video_sha256": self._digest(paths["overhead_browser"]),
            },
            "wrist": {
                "video_path": paths["wrist_source"].name,
                "video_sha256": self._digest(paths["wrist_source"]),
                "browser_video_path": paths["wrist_browser"].name,
                "browser_video_sha256": self._digest(paths["wrist_browser"]),
            },
        }


class _C922Capture(_Capture):
    def finish(self, **kwargs: object) -> dict[str, object]:
        del kwargs
        if self.finished:
            raise AssertionError("capture finished twice")
        self.finished = True
        final = self.root / "final.json"
        ledger = self.root / "frames.jsonl"
        frame_paths = [self.root / f"frame-{index}.png" for index in (1, 2)]
        _write(final, {"status": "completed"})
        for index, frame in enumerate(frame_paths, start=1):
            frame.write_bytes(f"frame-{index}".encode())
        ledger.write_text(
            "\n".join(
                json.dumps(
                    {
                        "schemaVersion": (
                            "sim2claw.c922_terminal_hold_frame_event.v1"
                        ),
                        "hostContinuousNS": 0,
                        "pngPath": frame.name,
                        "pngSHA256": self._digest(frame),
                        "sequence": index,
                    }
                )
                for index, frame in enumerate(frame_paths, start=1)
            )
            + "\n",
            encoding="utf-8",
        )
        return {
            "schema_version": "sim2claw.c922_motion_capture_receipt.v1",
            "status": "completed",
            "capture_mode": CAPTURE_MODE_C922_PI,
            "final_path": str(final),
            "final_sha256": self._digest(final),
            "ledger_path": str(ledger),
            "ledger_sha256": self._digest(ledger),
        }


class _TricamCapture(_Capture):
    def finish(self, **kwargs: object) -> dict[str, object]:
        result = super().finish(**kwargs)
        result["overhead"]["action_interval_enclosed_by_callback_frames"] = True
        result["wrist"]["action_interval_enclosed_by_callback_frames"] = True
        pi_root = self.root / "pi_motion"
        pi_root.mkdir()
        raw = pi_root / "pi_imx708.mjpeg"
        browser = pi_root / "pi_imx708.browser.mp4"
        pts = pi_root / "pi_imx708.pts"
        raw.write_bytes(b"pi-raw")
        browser.write_bytes(b"pi-browser")
        pts.write_text("0\n33333\n", encoding="utf-8")
        result["pi"] = {
            "schema_version": "sim2claw.pi_motion_video_capture.v1",
            "status": "completed",
            "action_interval_enclosed": True,
            "raw_video_path": str(raw),
            "raw_video_sha256": self._digest(raw),
            "browser_video_path": str(browser),
            "browser_video_sha256": self._digest(browser),
            "pts_path": str(pts),
            "pts_sha256": self._digest(pts),
        }
        return result


class _CaptureStartFailure:
    def start(self) -> dict[str, object]:
        raise RuntimeError("fixture camera failure")

    def finish(self, **kwargs: object) -> dict[str, object]:
        raise AssertionError("unstarted capture must not finish")


def test_compile_previews_exact_supplied_float64_route(tmp_path: Path) -> None:
    manifest_path = tmp_path / "candidate_manifest.json"
    route_path = tmp_path / "route.json"
    packet_path = tmp_path / "packet.json"
    _candidate_manifest(manifest_path)
    _route(route_path)

    packet = compile_wrist_view_reposition_packet(
        packet_path,
        candidate_manifest_path=manifest_path,
        route_path=route_path,
        preflight_fn=_preflight,
    )

    assert packet["schema_version"] == WRIST_VIEW_PACKET_SCHEMA
    assert packet["simulation_preview"]["external_contact_pairs"] == []
    assert packet["simulation_preview"]["no_new_or_worsened_kinematic_contact"]
    assert packet["action_assistance"] == {
        "inverse_kinematics": False,
        "clipping": False,
        "offsets": False,
        "suffix_or_corrective_action": False,
    }
    previous = ROUTE_ANCHOR
    for index, (stage, target) in enumerate(
        zip(packet["stages"], ROUTE_TARGETS, strict=True), start=1
    ):
        payload = stage["frozen_action_payload"]
        actions = np.frombuffer(
            base64.b64decode(payload["base64"]), dtype="<f8"
        ).reshape(payload["shape"])
        assert actions.shape == (SAMPLES_PER_STAGE, 6)
        assert actions[0].tobytes() == previous.astype("<f8").tobytes()
        assert actions[-1].tobytes() == target.astype("<f8").tobytes()
        assert action_sha256(actions) == stage["action_sha256"]
        assert stage["maximum_joint_excursion_degrees"] <= MAX_STAGE_EXCURSION_DEGREES
        assert stage["simulation_preview"]["exact_physical_action_sha256"] == stage[
            "action_sha256"
        ]
        hold_payload = stage["frozen_capture_hold_payload"]
        hold = np.frombuffer(
            base64.b64decode(hold_payload["base64"]), dtype="<f8"
        ).reshape(hold_payload["shape"])
        assert hold.shape == (CAPTURE_HOLD_SAMPLES, 6)
        assert np.all(hold == target)
        assert stage["inspect_wrist_camera_before_next_stage"] is (
            index < len(ROUTE_TARGETS)
        )
        assert stage["expected_anchor_degrees"] == previous.tolist()
        assert stage["command_anchor_degrees"] == actions[0].tolist()
        previous = target


def test_compile_supports_bounded_long_roundtrip_stage(tmp_path: Path) -> None:
    manifest_path = tmp_path / "candidate_manifest.json"
    route_path = tmp_path / "long-route.json"
    packet_path = tmp_path / "packet.json"
    _candidate_manifest(manifest_path)
    hover = ROUTE_ANCHOR.copy()
    hover[0] += 10.0
    _write(
        route_path,
        {
            "schema_version": WRIST_VIEW_ROUTE_SCHEMA,
            "route_id": "fixture-long-roundtrip-route",
            "samples_per_stage": 721,
            "reviewed_anchor_degrees": ROUTE_ANCHOR.tolist(),
            "stage_waypoints_degrees": [
                [hover.tolist(), ROUTE_ANCHOR.tolist()]
            ],
        },
    )

    packet = compile_wrist_view_reposition_packet(
        packet_path,
        candidate_manifest_path=manifest_path,
        route_path=route_path,
        preflight_fn=_preflight,
    )

    stage = packet["stages"][0]
    payload = stage["frozen_action_payload"]
    actions = np.frombuffer(
        base64.b64decode(payload["base64"]), dtype="<f8"
    ).reshape(payload["shape"])
    timestamps = np.asarray(stage["timestamps_seconds"], dtype="<f8")
    assert packet["samples_per_stage"] == 721
    assert stage["sample_count"] == 721
    assert actions.shape == (721, 6)
    assert np.array_equal(actions[360], hover)
    assert np.array_equal(actions[-1], ROUTE_ANCHOR)
    assert float(
        np.max(np.abs(np.diff(actions, axis=0) / np.diff(timestamps)[:, None]))
    ) <= packet["maximum_slew_degrees_s"]


def test_compile_binds_c922_plus_pi_capture_mode(tmp_path: Path) -> None:
    manifest_path = tmp_path / "candidate_manifest.json"
    route_path = tmp_path / "route.json"
    packet_path = tmp_path / "packet.json"
    _candidate_manifest(manifest_path)
    _c922_route(route_path)

    packet = compile_wrist_view_reposition_packet(
        packet_path,
        candidate_manifest_path=manifest_path,
        route_path=route_path,
        preflight_fn=_preflight,
    )

    assert packet["capture_mode"] == CAPTURE_MODE_C922_PI
    assert packet["execution_contract"]["motion_camera_owner"] == (
        "NativeC922StillRecorder"
    )
    assert packet["execution_contract"]["d405_required"] is False


def test_compile_rejects_tricam_stage_longer_than_bound_pi_capture(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "candidate_manifest.json"
    route_path = tmp_path / "route.json"
    packet_path = tmp_path / "packet.json"
    _candidate_manifest(manifest_path)
    _tricam_route(route_path)
    route = json.loads(route_path.read_text(encoding="utf-8"))
    route["samples_per_stage"] = 481
    _write(route_path, route)

    with pytest.raises(
        WristViewRepositionError,
        match="Pi motion-video duration cannot enclose",
    ):
        compile_wrist_view_reposition_packet(
            packet_path,
            candidate_manifest_path=manifest_path,
            route_path=route_path,
            preflight_fn=_preflight,
        )


def test_compile_and_execute_requires_three_motion_cameras(tmp_path: Path) -> None:
    manifest_path = tmp_path / "candidate_manifest.json"
    route_path = tmp_path / "route.json"
    packet_path = tmp_path / "packet.json"
    review_path = tmp_path / "review.json"
    _candidate_manifest(manifest_path)
    _tricam_route(route_path)

    packet = compile_wrist_view_reposition_packet(
        packet_path,
        candidate_manifest_path=manifest_path,
        route_path=route_path,
        preflight_fn=_preflight,
    )
    review_wrist_view_reposition_packet(
        packet_path,
        review_path,
        reviewer="fixture-reviewer",
        decision_id="fixture-decision",
    )
    receipt = execute_wrist_view_reposition_stage(
        packet_path,
        review_path,
        tmp_path / "execution-tricam-stage-1",
        stage_index=1,
        operator_acknowledged=True,
        preflight_fn=_preflight,
        gateway_factory=lambda identity: _Gateway(ROUTE_ANCHOR),
        capture_factory=lambda path: _TricamCapture(path),
        clock_fn=lambda: 0.0,
        sleep_fn=lambda delay: None,
    )

    assert packet["capture_mode"] == CAPTURE_MODE_TRICAM
    assert packet["execution_contract"]["motion_camera_owner"] == (
        "MotionTricamRecorder"
    )
    assert packet["execution_contract"]["d405_required"] is True
    assert receipt["capture_mode"] == CAPTURE_MODE_TRICAM
    assert receipt["frame_joint_alignment"]["camera_role"] == "d405"
    assert {row["kind"] for row in receipt["capture_artifacts"]} == {
        "native_report",
        "callback_ledger",
        "overhead_source_video",
        "overhead_browser_video",
        "wrist_source_video",
        "wrist_browser_video",
        "pi_source_video",
        "pi_browser_video",
        "pi_pts_ledger",
    }


def test_compile_freezes_one_tricam_round_trip_without_torque_off_midpoint(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "candidate_manifest.json"
    route_path = tmp_path / "route.json"
    packet_path = tmp_path / "packet.json"
    _candidate_manifest(manifest_path)
    _tricam_round_trip_route(route_path)

    packet = compile_wrist_view_reposition_packet(
        packet_path,
        candidate_manifest_path=manifest_path,
        route_path=route_path,
        preflight_fn=_preflight,
    )
    stage = packet["stages"][0]
    payload = stage["frozen_action_payload"]
    actions = np.frombuffer(
        base64.b64decode(payload["base64"]), dtype="<f8"
    ).reshape(payload["shape"])
    midpoint = np.asarray(stage["waypoints_degrees"][0], dtype="<f8")

    assert actions.shape == (SAMPLES_PER_STAGE, 6)
    assert actions[0].tobytes() == ROUTE_ANCHOR.astype("<f8").tobytes()
    assert actions[180].tobytes() == midpoint.tobytes()
    assert actions[-1].tobytes() == ROUTE_ANCHOR.astype("<f8").tobytes()
    assert stage["target_degrees"] == ROUTE_ANCHOR.tolist()
    assert packet["capture_mode"] == CAPTURE_MODE_TRICAM
    assert packet["execution_contract"]["one_stage_per_invocation"] is True


def test_execute_c922_mode_aligns_source_frames_and_never_requires_d405(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "candidate_manifest.json"
    route_path = tmp_path / "route.json"
    packet_path = tmp_path / "packet.json"
    review_path = tmp_path / "review.json"
    _candidate_manifest(manifest_path)
    _c922_route(route_path)
    compile_wrist_view_reposition_packet(
        packet_path,
        candidate_manifest_path=manifest_path,
        route_path=route_path,
        preflight_fn=_preflight,
    )
    review_wrist_view_reposition_packet(
        packet_path,
        review_path,
        reviewer="fixture-reviewer",
        decision_id="fixture-decision",
    )

    receipt = execute_wrist_view_reposition_stage(
        packet_path,
        review_path,
        tmp_path / "execution-c922-stage-1",
        stage_index=1,
        operator_acknowledged=True,
        preflight_fn=_preflight,
        gateway_factory=lambda identity: _Gateway(ROUTE_ANCHOR),
        capture_factory=lambda path: _C922Capture(path),
        clock_fn=lambda: 0.0,
        sleep_fn=lambda delay: None,
    )

    assert receipt["status"] == "completed_wrist_view_reposition_stage"
    assert receipt["capture_mode"] == CAPTURE_MODE_C922_PI
    assert receipt["frame_joint_alignment"]["camera_role"] == "c922"
    assert receipt["frame_joint_alignment"]["aligned_frame_count"] == 2
    assert len(receipt["capture_artifacts"]) == 2


@pytest.mark.parametrize(
    ("field", "message"),
    (
        ("expected_anchor_degrees", "stage expected anchor drifted"),
        ("command_anchor_degrees", "stage command anchor"),
    ),
)
def test_packet_rejects_tampered_later_stage_anchor_chain(
    tmp_path: Path,
    field: str,
    message: str,
) -> None:
    manifest_path = tmp_path / "candidate_manifest.json"
    route_path = tmp_path / "route.json"
    packet_path = tmp_path / "packet.json"
    review_path = tmp_path / "review.json"
    _candidate_manifest(manifest_path)
    _route(route_path)
    compile_wrist_view_reposition_packet(
        packet_path,
        candidate_manifest_path=manifest_path,
        route_path=route_path,
        preflight_fn=_preflight,
    )
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["stages"][1][field] = packet["compile_anchor_degrees"]
    packet["plan_sha256"] = hashlib.sha256(
        json.dumps(
            {
                key: value
                for key, value in packet.items()
                if key != "plan_sha256"
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    _write(packet_path, packet)

    with pytest.raises(WristViewRepositionError, match=message):
        review_wrist_view_reposition_packet(
            packet_path,
            review_path,
            reviewer="fixture-reviewer",
            decision_id="fixture-decision",
        )


def test_compile_allows_only_explicit_bounded_setup_recovery_snap(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "candidate_manifest.json"
    route_path = tmp_path / "route.json"
    packet_path = tmp_path / "packet.json"
    _candidate_manifest(manifest_path)
    recovery_anchor = ROUTE_ANCHOR.copy()
    recovery_anchor[1] = LOWER[1] - 5.5
    recovery_anchor[3] = LOWER[3] - 2.4
    recovery_target = recovery_anchor.copy()
    recovery_target[1] = -60.0
    recovery_target[3] = -20.0
    _write(
        route_path,
        {
            "schema_version": WRIST_VIEW_ROUTE_SCHEMA,
            "route_id": "fixture-recovery-route",
            "setup_recovery_command_anchor_snap_limit_degrees": 6.0,
            "reviewed_anchor_degrees": recovery_anchor.tolist(),
            "stage_targets_degrees": [recovery_target.tolist()],
            "review_basis": {"physical_scope": "setup_recovery_only"},
        },
    )

    packet = compile_wrist_view_reposition_packet(
        packet_path,
        candidate_manifest_path=manifest_path,
        route_path=route_path,
        preflight_fn=lambda: _preflight(recovery_anchor),
        preview_fn=lambda stages, manifest: {
            "candidate_digest": "b" * 64,
            "no_new_or_worsened_kinematic_contact": True,
            "external_contact_pairs": [],
            "stages": [
                {
                    "exact_physical_action_sha256": action_sha256(stages[0]),
                    "no_new_or_worsened_kinematic_contact": True,
                    "external_contact_pairs": [],
                }
            ],
        },
    )

    recovery = packet["setup_recovery_command_anchor"]
    assert recovery["enabled"] is True
    assert recovery["snap_delta_degrees"][1] == pytest.approx(5.5)
    assert recovery["snap_delta_degrees"][3] == pytest.approx(2.4)
    assert packet["stages"][0]["command_anchor_degrees"] == packet[
        "command_anchor_degrees"
    ]


def test_compile_allows_explicit_calibration_capture_setup_recovery(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "candidate_manifest.json"
    route_path = tmp_path / "route.json"
    packet_path = tmp_path / "packet.json"
    _candidate_manifest(manifest_path)
    recovery_anchor = ROUTE_ANCHOR.copy()
    recovery_anchor[1] = LOWER[1] - 0.5
    _write(
        route_path,
        {
            "schema_version": WRIST_VIEW_ROUTE_SCHEMA,
            "route_id": "fixture-calibration-capture-recovery-route",
            "capture_during_motion": True,
            "setup_recovery_command_anchor_snap_limit_degrees": 2.0,
            "reviewed_anchor_degrees": recovery_anchor.tolist(),
            "stage_targets_degrees": [ROUTE_TARGETS[0].tolist()],
            "review_basis": {
                "physical_scope": "calibration_capture_with_setup_recovery"
            },
        },
    )

    packet = compile_wrist_view_reposition_packet(
        packet_path,
        candidate_manifest_path=manifest_path,
        route_path=route_path,
        preflight_fn=lambda: _preflight(recovery_anchor),
        preview_fn=lambda stages, manifest: {
            "candidate_digest": "b" * 64,
            "no_new_or_worsened_kinematic_contact": True,
            "external_contact_pairs": [],
            "stages": [
                {
                    "exact_physical_action_sha256": action_sha256(stages[0]),
                    "no_new_or_worsened_kinematic_contact": True,
                    "external_contact_pairs": [],
                }
            ],
        },
    )

    recovery = packet["setup_recovery_command_anchor"]
    assert recovery["enabled"] is True
    assert recovery["setup_only"] is True
    assert recovery["sim_gap_evidence"] is False


def test_review_and_execute_one_stage_exactly_then_torque_off(tmp_path: Path) -> None:
    manifest_path = tmp_path / "candidate_manifest.json"
    route_path = tmp_path / "route.json"
    packet_path = tmp_path / "packet.json"
    review_path = tmp_path / "review.json"
    _candidate_manifest(manifest_path)
    _route(route_path)
    compile_wrist_view_reposition_packet(
        packet_path,
        candidate_manifest_path=manifest_path,
        route_path=route_path,
        preflight_fn=_preflight,
    )
    review_wrist_view_reposition_packet(
        packet_path,
        review_path,
        reviewer="fixture-reviewer",
        decision_id="fixture-decision",
    )
    gateway = _Gateway(ROUTE_ANCHOR)

    receipt = execute_wrist_view_reposition_stage(
        packet_path,
        review_path,
        tmp_path / "execution-stage-1",
        stage_index=1,
        operator_acknowledged=True,
        preflight_fn=_preflight,
        gateway_factory=lambda identity: gateway,
        capture_factory=lambda path: _Capture(path),
        clock_fn=lambda: 0.0,
        sleep_fn=lambda delay: None,
    )

    assert receipt["schema_version"] == WRIST_VIEW_EXECUTION_SCHEMA
    assert receipt["status"] == "completed_wrist_view_reposition_stage"
    assert receipt["completed_samples"] == SAMPLES_PER_STAGE + CAPTURE_HOLD_SAMPLES
    assert receipt["physical_follower_torque_enabled"] is False
    assert receipt["camera_opened"] is True
    assert receipt["camera_capture_completed_before_torque_off"] is True
    assert receipt["frame_joint_alignment"]["aligned_frame_count"] == 2
    assert len(receipt["capture_artifacts"]) == 6
    assert gateway.closed
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    expected = np.frombuffer(
        base64.b64decode(packet["stages"][0]["frozen_action_payload"]["base64"]),
        dtype="<f8",
    ).reshape((SAMPLES_PER_STAGE, 6))
    assert (
        np.asarray(gateway.samples[:SAMPLES_PER_STAGE], dtype="<f8").tobytes()
        == expected.tobytes()
    )
    with pytest.raises(WristViewRepositionError, match="overwrite"):
        execute_wrist_view_reposition_stage(
            packet_path,
            review_path,
            tmp_path / "execution-stage-1",
            stage_index=1,
            operator_acknowledged=True,
            preflight_fn=_preflight,
            gateway_factory=lambda identity: _Gateway(ROUTE_ANCHOR),
            capture_factory=lambda path: _Capture(path),
            clock_fn=lambda: 0.0,
            sleep_fn=lambda delay: None,
        )


def test_later_stage_requires_bound_prior_receipt(tmp_path: Path) -> None:
    manifest_path = tmp_path / "candidate_manifest.json"
    route_path = tmp_path / "route.json"
    packet_path = tmp_path / "packet.json"
    review_path = tmp_path / "review.json"
    _candidate_manifest(manifest_path)
    _route(route_path)
    compile_wrist_view_reposition_packet(
        packet_path,
        candidate_manifest_path=manifest_path,
        route_path=route_path,
        preflight_fn=_preflight,
    )
    review_wrist_view_reposition_packet(
        packet_path,
        review_path,
        reviewer="fixture-reviewer",
        decision_id="fixture-decision",
    )

    with pytest.raises(WristViewRepositionError, match="prior receipt"):
        execute_wrist_view_reposition_stage(
            packet_path,
            review_path,
            tmp_path / "execution-stage-2",
            stage_index=2,
            operator_acknowledged=True,
            preflight_fn=lambda: _preflight(ROUTE_TARGETS[0]),
            gateway_factory=lambda identity: _Gateway(ROUTE_TARGETS[0]),
        )


def test_later_stage_repreviews_the_frozen_route_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = tmp_path / "candidate_manifest.json"
    route_path = tmp_path / "route.json"
    packet_path = tmp_path / "packet.json"
    review_path = tmp_path / "review.json"
    _candidate_manifest(manifest_path)
    _route(route_path)
    compile_wrist_view_reposition_packet(
        packet_path,
        candidate_manifest_path=manifest_path,
        route_path=route_path,
        preflight_fn=_preflight,
    )
    review_wrist_view_reposition_packet(
        packet_path,
        review_path,
        reviewer="fixture-reviewer",
        decision_id="fixture-decision",
    )
    prior_path = tmp_path / "prior.json"
    _write(
        prior_path,
        {
            "schema_version": WRIST_VIEW_EXECUTION_SCHEMA,
            "status": "completed_wrist_view_reposition_stage",
            "packet_sha256": hashlib.sha256(packet_path.read_bytes()).hexdigest(),
            "stage_index": 1,
            "physical_follower_torque_enabled": False,
        },
    )
    preview_stage_counts: list[int] = []

    def preview_prefix(
        stages: list[np.ndarray], candidate_manifest: Path
    ) -> dict[str, object]:
        preview_stage_counts.append(len(stages))
        return {
            "no_new_or_worsened_kinematic_contact": True,
            "external_contact_pairs": [],
        }

    monkeypatch.setattr(
        "sim2claw.wrist_view_reposition.preview_wrist_view_actions",
        preview_prefix,
    )
    receipt = execute_wrist_view_reposition_stage(
        packet_path,
        review_path,
        tmp_path / "execution-stage-2",
        stage_index=2,
        prior_receipt_path=prior_path,
        operator_acknowledged=True,
        preflight_fn=lambda: _preflight(ROUTE_TARGETS[0]),
        gateway_factory=lambda identity: _Gateway(ROUTE_TARGETS[0]),
        capture_factory=lambda path: _Capture(path),
        clock_fn=lambda: 0.0,
        sleep_fn=lambda delay: None,
    )

    assert preview_stage_counts == [2]
    assert receipt["stage_index"] == 2
    assert receipt["physical_follower_torque_enabled"] is False


def test_later_setup_recovery_stage_opens_on_its_stage_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = tmp_path / "candidate_manifest.json"
    route_path = tmp_path / "route.json"
    packet_path = tmp_path / "packet.json"
    review_path = tmp_path / "review.json"
    prior_path = tmp_path / "prior.json"
    _candidate_manifest(manifest_path)
    _setup_recovery_route(route_path)
    compile_wrist_view_reposition_packet(
        packet_path,
        candidate_manifest_path=manifest_path,
        route_path=route_path,
        preflight_fn=_preflight,
    )
    review_wrist_view_reposition_packet(
        packet_path,
        review_path,
        reviewer="fixture-reviewer",
        decision_id="fixture-decision",
    )
    _write(
        prior_path,
        {
            "schema_version": WRIST_VIEW_EXECUTION_SCHEMA,
            "status": "completed_wrist_view_reposition_stage",
            "packet_sha256": hashlib.sha256(
                packet_path.read_bytes()
            ).hexdigest(),
            "stage_index": 1,
            "physical_follower_torque_enabled": False,
        },
    )
    monkeypatch.setattr(
        "sim2claw.wrist_view_reposition.preview_wrist_view_actions",
        lambda stages, manifest: {
            "no_new_or_worsened_kinematic_contact": True,
            "external_contact_pairs": [],
        },
    )
    gateway = _Gateway(ROUTE_TARGETS[0])

    receipt = execute_wrist_view_reposition_stage(
        packet_path,
        review_path,
        tmp_path / "execution-stage-2",
        stage_index=2,
        prior_receipt_path=prior_path,
        operator_acknowledged=True,
        preflight_fn=lambda: _preflight(ROUTE_TARGETS[0]),
        gateway_factory=lambda identity: gateway,
        capture_factory=lambda path: _Capture(path),
        clock_fn=lambda: 0.0,
        sleep_fn=lambda delay: None,
    )
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    stage_anchor = np.asarray(
        packet["stages"][1]["command_anchor_degrees"],
        dtype=np.float64,
    )

    assert np.array_equal(
        gateway.open_setup_command_anchor_degrees, stage_anchor
    )
    assert not np.array_equal(
        gateway.open_setup_command_anchor_degrees,
        np.asarray(packet["command_anchor_degrees"]),
    )
    assert receipt["gateway_open_setup_command_anchor_degrees"] == (
        stage_anchor.tolist()
    )
    assert receipt["gateway_open_setup_motion_commanded"] is True
    assert receipt["physical_motion_commanded"] is True


def test_tricam_starts_before_setup_recovery_gateway_motion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = tmp_path / "candidate_manifest.json"
    route_path = tmp_path / "route.json"
    packet_path = tmp_path / "packet.json"
    review_path = tmp_path / "review.json"
    _candidate_manifest(manifest_path)
    recovery_anchor = ROUTE_ANCHOR.copy()
    recovery_anchor[1] = LOWER[1] - 1.0
    _write(
        route_path,
        {
            "schema_version": WRIST_VIEW_ROUTE_SCHEMA,
            "route_id": "fixture-tricam-setup-recovery-route",
            "capture_during_motion": True,
            "capture_mode": CAPTURE_MODE_TRICAM,
            "pi_motion_video": {
                "contract_path": (
                    "configs/acquisition/pi_imx708_motion_video_15s_v1.json"
                ),
                "contract_sha256": PI_MOTION_CONTRACT_SHA256,
            },
            "setup_recovery_command_anchor_snap_limit_degrees": 2.0,
            "reviewed_anchor_degrees": recovery_anchor.tolist(),
            "stage_targets_degrees": [ROUTE_ANCHOR.tolist()],
            "review_basis": {
                "physical_scope": "calibration_capture_with_setup_recovery"
            },
        },
    )
    compile_wrist_view_reposition_packet(
        packet_path,
        candidate_manifest_path=manifest_path,
        route_path=route_path,
        preflight_fn=lambda: _preflight(recovery_anchor),
        preview_fn=lambda stages, manifest: {
            "candidate_digest": "b" * 64,
            "no_new_or_worsened_kinematic_contact": True,
            "external_contact_pairs": [],
            "stages": [
                {
                    "exact_physical_action_sha256": action_sha256(stages[0]),
                    "no_new_or_worsened_kinematic_contact": True,
                    "external_contact_pairs": [],
                }
            ],
        },
    )
    review_wrist_view_reposition_packet(
        packet_path,
        review_path,
        reviewer="fixture-reviewer",
        decision_id="fixture-decision",
    )
    monkeypatch.setattr(
        "sim2claw.wrist_view_reposition.preview_wrist_view_actions",
        lambda stages, manifest: {
            "no_new_or_worsened_kinematic_contact": True,
            "external_contact_pairs": [],
        },
    )
    events: list[str] = []

    class OrderedGateway(_Gateway):
        def open(self, **kwargs: object) -> dict[str, object]:
            events.append("gateway_open")
            return super().open(**kwargs)

    class OrderedCapture(_Capture):
        def start(self) -> dict[str, object]:
            events.append("capture_start")
            return super().start()

    receipt = execute_wrist_view_reposition_stage(
        packet_path,
        review_path,
        tmp_path / "execution-stage-1",
        stage_index=1,
        operator_acknowledged=True,
        preflight_fn=lambda: _preflight(recovery_anchor),
        gateway_factory=lambda identity: OrderedGateway(recovery_anchor),
        capture_factory=lambda path: OrderedCapture(path),
        clock_fn=lambda: 0.0,
        sleep_fn=lambda delay: None,
    )

    assert events[:2] == ["capture_start", "gateway_open"]
    assert receipt["gateway_open_setup_motion_commanded"] is True
    assert receipt["camera_started_before_gateway_open_setup_motion"] is True
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    frozen_setup_preview = packet["setup_recovery_simulation_preview"]
    assert (
        frozen_setup_preview["joint_progress_semantics"]
        == "nine_point_cartesian_hyperrectangle_per_changed_joint"
    )
    assert frozen_setup_preview["sample_count"] == 9
    fresh_setup_preview = receipt[
        "fresh_setup_recovery_simulation_preview"
    ]
    assert fresh_setup_preview["sample_count"] == 9
    assert (
        fresh_setup_preview["kinematic_action_sha256"]
        == frozen_setup_preview["kinematic_action_sha256"]
    )


def test_setup_open_failure_conservatively_accounts_motion_before_sample_zero(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "candidate_manifest.json"
    route_path = tmp_path / "route.json"
    packet_path = tmp_path / "packet.json"
    review_path = tmp_path / "review.json"
    output = tmp_path / "failed-setup-open"
    _candidate_manifest(manifest_path)
    _setup_recovery_route(route_path)
    compile_wrist_view_reposition_packet(
        packet_path,
        candidate_manifest_path=manifest_path,
        route_path=route_path,
        preflight_fn=_preflight,
    )
    review_wrist_view_reposition_packet(
        packet_path,
        review_path,
        reviewer="fixture-reviewer",
        decision_id="fixture-decision",
    )
    gateway = _GatewayOpenFailure(ROUTE_ANCHOR)

    with pytest.raises(
        WristViewRepositionError, match="fixture gateway open failure"
    ):
        execute_wrist_view_reposition_stage(
            packet_path,
            review_path,
            output,
            stage_index=1,
            operator_acknowledged=True,
            preflight_fn=_preflight,
            gateway_factory=lambda identity: gateway,
            clock_fn=lambda: 0.0,
            sleep_fn=lambda delay: None,
        )

    receipt = json.loads(
        (output / "execution_receipt.json").read_text(encoding="utf-8")
    )
    assert gateway.closed
    assert receipt["status"] == "stopped_safely"
    assert receipt["completed_samples"] == 0
    assert receipt["gateway_open_attempted"] is True
    assert receipt["gateway_open_completed"] is False
    assert receipt["gateway_open_setup_motion_commanded"] is True
    assert receipt["gateway_open_setup_command_anchor_degrees"] == (
        ROUTE_ANCHOR.tolist()
    )
    assert receipt["physical_motion_commanded"] is True


def test_non_setup_open_failure_still_reports_no_motion(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "candidate_manifest.json"
    route_path = tmp_path / "route.json"
    packet_path = tmp_path / "packet.json"
    review_path = tmp_path / "review.json"
    output = tmp_path / "failed-normal-open"
    _candidate_manifest(manifest_path)
    _route(route_path)
    compile_wrist_view_reposition_packet(
        packet_path,
        candidate_manifest_path=manifest_path,
        route_path=route_path,
        preflight_fn=_preflight,
    )
    review_wrist_view_reposition_packet(
        packet_path,
        review_path,
        reviewer="fixture-reviewer",
        decision_id="fixture-decision",
    )
    gateway = _GatewayOpenFailure(ROUTE_ANCHOR)

    with pytest.raises(
        WristViewRepositionError, match="fixture gateway open failure"
    ):
        execute_wrist_view_reposition_stage(
            packet_path,
            review_path,
            output,
            stage_index=1,
            operator_acknowledged=True,
            preflight_fn=_preflight,
            gateway_factory=lambda identity: gateway,
            clock_fn=lambda: 0.0,
            sleep_fn=lambda delay: None,
        )

    receipt = json.loads(
        (output / "execution_receipt.json").read_text(encoding="utf-8")
    )
    assert gateway.closed
    assert receipt["completed_samples"] == 0
    assert receipt["gateway_open_attempted"] is True
    assert receipt["gateway_open_completed"] is False
    assert receipt["gateway_open_setup_command_anchor_degrees"] is None
    assert receipt["gateway_open_setup_motion_commanded"] is False
    assert receipt["physical_motion_commanded"] is False


def test_camera_start_failure_still_closes_gateway_torque_off(tmp_path: Path) -> None:
    manifest_path = tmp_path / "candidate_manifest.json"
    route_path = tmp_path / "route.json"
    packet_path = tmp_path / "packet.json"
    review_path = tmp_path / "review.json"
    output = tmp_path / "failed-execution"
    _candidate_manifest(manifest_path)
    _route(route_path)
    compile_wrist_view_reposition_packet(
        packet_path,
        candidate_manifest_path=manifest_path,
        route_path=route_path,
        preflight_fn=_preflight,
    )
    review_wrist_view_reposition_packet(
        packet_path,
        review_path,
        reviewer="fixture-reviewer",
        decision_id="fixture-decision",
    )
    gateway = _Gateway(ROUTE_ANCHOR)

    with pytest.raises(WristViewRepositionError, match="camera failure"):
        execute_wrist_view_reposition_stage(
            packet_path,
            review_path,
            output,
            stage_index=1,
            operator_acknowledged=True,
            preflight_fn=_preflight,
            gateway_factory=lambda identity: gateway,
            capture_factory=lambda path: _CaptureStartFailure(),
            clock_fn=lambda: 0.0,
            sleep_fn=lambda delay: None,
        )

    receipt = json.loads(
        (output / "execution_receipt.json").read_text(encoding="utf-8")
    )
    assert gateway.closed
    assert receipt["status"] == "stopped_safely"
    assert receipt["physical_follower_torque_enabled"] is False


def test_reported_unsafe_sample_aborts_immediately_and_closes_torque_off(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "candidate_manifest.json"
    route_path = tmp_path / "route.json"
    packet_path = tmp_path / "packet.json"
    review_path = tmp_path / "review.json"
    output = tmp_path / "unsafe-sample-execution"
    _candidate_manifest(manifest_path)
    _route(route_path)
    compile_wrist_view_reposition_packet(
        packet_path,
        candidate_manifest_path=manifest_path,
        route_path=route_path,
        preflight_fn=_preflight,
    )
    review_wrist_view_reposition_packet(
        packet_path,
        review_path,
        reviewer="fixture-reviewer",
        decision_id="fixture-decision",
    )
    gateway = _UnsafeSampleGateway(ROUTE_ANCHOR)

    with pytest.raises(WristViewRepositionError, match="safely track"):
        execute_wrist_view_reposition_stage(
            packet_path,
            review_path,
            output,
            stage_index=1,
            operator_acknowledged=True,
            preflight_fn=_preflight,
            gateway_factory=lambda identity: gateway,
            capture_factory=lambda path: _Capture(path),
            clock_fn=lambda: 0.0,
            sleep_fn=lambda delay: None,
        )

    receipt = json.loads(
        (output / "execution_receipt.json").read_text(encoding="utf-8")
    )
    assert gateway.closed
    assert len(gateway.samples) == 1
    assert receipt["status"] == "stopped_safely"
    assert receipt["completed_samples"] == 0
    assert receipt["physical_follower_torque_enabled"] is False


def test_preview_rejects_new_external_contact_contract(tmp_path: Path) -> None:
    manifest_path = tmp_path / "candidate_manifest.json"
    _candidate_manifest(manifest_path)
    actions = [
        np.linspace(
            ROUTE_ANCHOR,
            ROUTE_TARGETS[0],
            SAMPLES_PER_STAGE,
        ).astype("<f8")
    ]
    preview = preview_wrist_view_actions(actions, manifest_path)
    assert preview["external_contact_pairs"] == []
    assert preview["contact_pairs_unchanged_or_removed_only"]
    assert preview["no_new_or_worsened_kinematic_contact"]

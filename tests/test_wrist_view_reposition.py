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

    def open(
        self, *, enable_motion: bool, paired_pose_confirmed: bool
    ) -> dict[str, object]:
        assert enable_motion and paired_pose_confirmed
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
            "rate_limited": False,
            "safety_clamped": False,
        }

    def close(self) -> None:
        self.closed = True


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
        previous = target


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

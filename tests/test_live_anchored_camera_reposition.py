from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from sim2claw.live_anchored_camera_reposition import (
    LiveAnchoredCameraRepositionError,
    execute_live_anchored_camera_reposition,
)
from sim2claw.physical_canary import EXCITATION_CONTROL_SOURCE, GATEWAY_SCHEMA
from sim2claw.replay_eligibility import action_sha256
from sim2claw.wrist_view_reposition import WRIST_VIEW_ROUTE_SCHEMA


PORT = "/dev/follower-fixture"
CALIBRATION = "a" * 64
TORQUE_OFF = np.asarray([10.0, -64.5, 102.0, 3.0, -82.0, 3.0])
SETTLED = np.asarray([10.0, -64.5, 92.0, 3.0, -82.0, 3.0])
TARGET = np.asarray([10.0, -64.5, 80.0, 0.0, -100.0, 3.0])
LOWER = np.asarray([-120.0, -107.5, -102.5, -107.5, -180.0, 0.0])
UPPER = np.asarray([120.0, 107.5, 102.5, 107.5, 180.0, 100.0])


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _inputs(
    tmp_path: Path,
    *,
    maximum_slew_degrees_s: float | None = None,
    elbow_tracking_limit_degrees: float | None = None,
    target_hold_seconds: float | None = None,
    stationary_capture_seconds: float | None = None,
) -> tuple[Path, Path]:
    route = tmp_path / "route.json"
    manifest = tmp_path / "candidate_manifest.json"
    route_value = {
        "schema_version": WRIST_VIEW_ROUTE_SCHEMA,
        "route_id": "fixture-live-route",
        "reviewed_anchor_degrees": TORQUE_OFF.tolist(),
        "stage_targets_degrees": [TARGET.tolist()],
    }
    if maximum_slew_degrees_s is not None:
        route_value["setup_maximum_slew_degrees_s"] = maximum_slew_degrees_s
    if elbow_tracking_limit_degrees is not None:
        route_value["setup_elbow_tracking_error_limit_degrees"] = (
            elbow_tracking_limit_degrees
        )
    if target_hold_seconds is not None:
        route_value["setup_target_hold_seconds"] = target_hold_seconds
    if stationary_capture_seconds is not None:
        route_value["stationary_capture_seconds"] = stationary_capture_seconds
    _write(route, route_value)
    _write(manifest, {"candidate_digest": "b" * 64})
    return route, manifest


def _preflight() -> dict[str, object]:
    return {
        "passed": True,
        "schema_version": GATEWAY_SCHEMA,
        "control_source": EXCITATION_CONTROL_SOURCE,
        "real_leader_opened": False,
        "follower_port": PORT,
        "follower_calibration_sha256": CALIBRATION,
        "follower_start_degrees": TORQUE_OFF.tolist(),
        "follower_calibrated_minimum": LOWER.tolist(),
        "follower_calibrated_maximum": UPPER.tolist(),
        "physical_follower_torque_enabled": False,
    }


class _Gateway:
    def __init__(self, *, fail_at: int | None = None) -> None:
        self.actions: list[np.ndarray] = []
        self.setup_elbow_limits: list[float | None] = []
        self.closed = False
        self.fail_at = fail_at

    def open_live_anchored_setup(self) -> dict[str, object]:
        return {
            "settled_torque_on_anchor_degrees": SETTLED.tolist(),
            "torque_off_start_degrees": TORQUE_OFF.tolist(),
            "follower_calibrated_minimum": LOWER.tolist(),
            "follower_calibrated_maximum": UPPER.tolist(),
            "physical_follower_torque_enabled": True,
            "setup_only": True,
        }

    def sample(
        self,
        elapsed_seconds: float,
        *,
        exact_requested_degrees: np.ndarray,
        setup_elbow_tracking_error_limit_degrees: float | None = None,
    ) -> dict[str, object]:
        if self.fail_at is not None and len(self.actions) == self.fail_at:
            raise RuntimeError("fixture bus failure")
        self.setup_elbow_limits.append(
            setup_elbow_tracking_error_limit_degrees
        )
        action = np.asarray(exact_requested_degrees, dtype=np.float64).copy()
        self.actions.append(action)
        return {
            "elapsed_seconds": elapsed_seconds,
            "follower_actual_position_degrees": action.tolist(),
            "physical_follower_torque_enabled": True,
            "precompiled_exact_action": True,
            "safety_clamped": False,
            "rate_limited": False,
            "tracking_error_limits": [
                6.0,
                8.0,
                setup_elbow_tracking_error_limit_degrees or 6.0,
                6.0,
                8.0,
                12.0,
            ],
        }

    def close(self) -> None:
        self.closed = True


class _Recorder:
    def __init__(self, output_path: Path) -> None:
        self.output_path = output_path
        self.started = False
        self.finished = False

    def start(self) -> dict[str, object]:
        self.started = True
        return {"status": "recording", "video_path": self.output_path.name}

    def finish(
        self,
        *,
        action_started_monotonic: float | None,
        action_stopped_monotonic: float | None,
        post_roll_seconds: float,
    ) -> dict[str, object]:
        assert self.started
        assert action_stopped_monotonic is not None
        assert post_roll_seconds == 0.0
        self.output_path.write_bytes(b"fixture-d405-video")
        self.output_path.with_suffix(".ffmpeg.log").write_text(
            "fixture capture complete", encoding="utf-8"
        )
        self.finished = True
        return {
            "status": "completed",
            "video_path": self.output_path.name,
        }


def _preview(actions: list[np.ndarray], manifest: Path) -> dict[str, object]:
    assert manifest.is_file()
    assert len(actions) == 1
    assert np.array_equal(actions[0][0], SETTLED)
    assert np.array_equal(actions[0][-1], TARGET)
    return {
        "candidate_digest": "b" * 64,
        "no_new_or_worsened_kinematic_contact": True,
        "external_contact_pairs": [],
        "stages": [
            {
                "exact_physical_action_sha256": action_sha256(actions[0]),
                "no_new_or_worsened_kinematic_contact": True,
                "external_contact_pairs": [],
            }
        ],
    }


def test_repositions_from_settled_live_anchor_and_remains_setup_only(
    tmp_path: Path,
) -> None:
    route, manifest = _inputs(tmp_path)
    gateway = _Gateway()

    receipt = execute_live_anchored_camera_reposition(
        route_path=route,
        candidate_manifest_path=manifest,
        output_root=tmp_path / "output",
        operator_acknowledged=True,
        preflight_fn=_preflight,
        gateway_factory=lambda identity: gateway,
        preview_fn=_preview,
        clock_fn=lambda: 0.0,
        sleep_fn=lambda delay: None,
    )

    assert receipt["status"] == "completed_live_anchored_camera_reposition"
    assert receipt["live_anchor_degrees"] == SETTLED.tolist()
    assert receipt["evidence_limits"]["action_frozen_before_torque_on"] is False
    assert receipt["evidence_limits"]["sim_gap_evidence"] is False
    assert receipt["trajectory"]["maximum_slew_degrees_s"] == 10.0
    assert receipt["trajectory"]["route_overrides_default_slew"] is False
    assert receipt["trajectory"]["setup_elbow_tracking_error_limit_degrees"] == 6.0
    assert receipt["trajectory"]["setup_tracking_override_applied"] is False
    assert (
        receipt["trajectory"]["action_sha256"]
        == receipt["cpu_preview"]["stages"][0]["exact_physical_action_sha256"]
    )
    assert np.array_equal(gateway.actions[0], SETTLED)
    assert np.array_equal(gateway.actions[-1], TARGET)
    assert gateway.closed


def test_route_can_reduce_setup_slew_without_widening_default(
    tmp_path: Path,
) -> None:
    route, manifest = _inputs(tmp_path, maximum_slew_degrees_s=3.0)
    gateway = _Gateway()

    receipt = execute_live_anchored_camera_reposition(
        route_path=route,
        candidate_manifest_path=manifest,
        output_root=tmp_path / "output",
        operator_acknowledged=True,
        preflight_fn=_preflight,
        gateway_factory=lambda identity: gateway,
        preview_fn=_preview,
        clock_fn=lambda: 0.0,
        sleep_fn=lambda delay: None,
    )

    trajectory = receipt["trajectory"]
    assert trajectory["maximum_slew_degrees_s"] == 3.0
    assert trajectory["default_maximum_slew_degrees_s"] == 10.0
    assert trajectory["route_overrides_default_slew"] is True
    assert trajectory["sample_count"] > 200
    assert (
        trajectory["action_sha256"]
        == receipt["cpu_preview"]["stages"][0]["exact_physical_action_sha256"]
    )


def test_route_cannot_widen_setup_slew_above_default(tmp_path: Path) -> None:
    route, manifest = _inputs(tmp_path, maximum_slew_degrees_s=10.1)

    with pytest.raises(
        LiveAnchoredCameraRepositionError,
        match="no greater than 10 degrees/s",
    ):
        execute_live_anchored_camera_reposition(
            route_path=route,
            candidate_manifest_path=manifest,
            output_root=tmp_path / "output",
            operator_acknowledged=True,
            preflight_fn=_preflight,
            gateway_factory=lambda identity: _Gateway(),
            preview_fn=_preview,
        )


def test_setup_only_seven_degree_elbow_envelope_and_stationary_capture(
    tmp_path: Path,
) -> None:
    route, manifest = _inputs(
        tmp_path,
        maximum_slew_degrees_s=1.5,
        elbow_tracking_limit_degrees=7.0,
        target_hold_seconds=0.1,
        stationary_capture_seconds=0.15,
    )
    gateway = _Gateway()
    recorders: list[_Recorder] = []

    def recorder_factory(path: Path) -> _Recorder:
        recorder = _Recorder(path)
        recorders.append(recorder)
        return recorder

    receipt = execute_live_anchored_camera_reposition(
        route_path=route,
        candidate_manifest_path=manifest,
        output_root=tmp_path / "output",
        operator_acknowledged=True,
        preflight_fn=_preflight,
        gateway_factory=lambda identity: gateway,
        preview_fn=_preview,
        recorder_factory=recorder_factory,
        clock_fn=lambda: 0.0,
        sleep_fn=lambda delay: None,
    )

    trajectory = receipt["trajectory"]
    assert trajectory["setup_elbow_tracking_error_limit_degrees"] == 7.0
    assert trajectory["global_body_tracking_error_limit_degrees"] == 6.0
    assert trajectory["setup_tracking_override_applied"] is True
    assert trajectory["target_hold_sample_count"] == 4
    assert trajectory["stationary_capture_sample_count"] == 6
    assert trajectory["target_hold_effective_command_seconds"] == 0.1
    assert trajectory["target_hold_maximum_seconds"] == 2.0
    assert trajectory["stationary_capture_effective_command_seconds"] == 0.15
    assert trajectory["stationary_capture_maximum_seconds"] == 4.0
    assert trajectory["sample_count"] == len(gateway.actions)
    assert (
        trajectory["action_sha256"]
        == receipt["cpu_preview"]["stages"][0]["exact_physical_action_sha256"]
    )
    assert all(
        row["setup_phase"] == "stationary_capture"
        for row in [
            json.loads(line)
            for line in (
                tmp_path / "output/telemetry.jsonl"
            ).read_text(encoding="utf-8").splitlines()[-6:]
        ]
    )
    capture = receipt["stationary_d405_capture"]
    assert capture["completed_before_gateway_close"] is True
    assert capture["artifacts"]["lossless_video"]["sha256"]
    assert capture["artifacts"]["ffmpeg_log"]["sha256"]
    assert receipt["telemetry"]["phase_sample_counts"] == {
        "motion": {
            "planned": trajectory["movement_sample_count"],
            "sent": trajectory["movement_sample_count"],
        },
        "target_hold": {"planned": 4, "sent": 4},
        "stationary_capture": {"planned": 6, "sent": 6},
    }
    assert recorders[0].finished
    assert gateway.closed


def test_fifteen_degree_elbow_envelope_is_bound_to_setup_samples(
    tmp_path: Path,
) -> None:
    route, manifest = _inputs(
        tmp_path,
        elbow_tracking_limit_degrees=15.0,
    )
    gateway = _Gateway()

    receipt = execute_live_anchored_camera_reposition(
        route_path=route,
        candidate_manifest_path=manifest,
        output_root=tmp_path / "output",
        operator_acknowledged=True,
        preflight_fn=_preflight,
        gateway_factory=lambda identity: gateway,
        preview_fn=_preview,
        clock_fn=lambda: 0.0,
        sleep_fn=lambda delay: None,
    )

    assert receipt["trajectory"]["setup_elbow_tracking_error_limit_degrees"] == 15.0
    assert set(gateway.setup_elbow_limits) == {15.0}


def test_setup_elbow_envelope_rejects_other_values(
    tmp_path: Path,
) -> None:
    route, manifest = _inputs(tmp_path, elbow_tracking_limit_degrees=7.1)

    with pytest.raises(
        LiveAnchoredCameraRepositionError,
        match="exactly 6.0, 7.0, 12.0, or 15.0",
    ):
        execute_live_anchored_camera_reposition(
            route_path=route,
            candidate_manifest_path=manifest,
            output_root=tmp_path / "output",
            operator_acknowledged=True,
            preflight_fn=_preflight,
            gateway_factory=lambda identity: _Gateway(),
            preview_fn=_preview,
        )


def test_route_rejects_duplicate_duration_keys(tmp_path: Path) -> None:
    route, manifest = _inputs(tmp_path)
    route.write_text(
        '{"schema_version":"sim2claw.wrist_view_reposition_route.v1",'
        '"route_id":"duplicate-route",'
        f'"stage_targets_degrees":[{TARGET.tolist()}],'
        '"setup_target_hold_seconds":2.0,'
        '"setup_target_hold_seconds":1.0}',
        encoding="utf-8",
    )

    with pytest.raises(
        LiveAnchoredCameraRepositionError,
        match="duplicate key: setup_target_hold_seconds",
    ):
        execute_live_anchored_camera_reposition(
            route_path=route,
            candidate_manifest_path=manifest,
            output_root=tmp_path / "output",
            operator_acknowledged=True,
            preflight_fn=_preflight,
            gateway_factory=lambda identity: _Gateway(),
            preview_fn=_preview,
        )


@pytest.mark.parametrize(
    ("hold_seconds", "capture_seconds", "message"),
    [
        (2.01, 0.0, "setup target hold seconds cannot exceed 2.0"),
        (0.0, 4.01, "stationary capture seconds cannot exceed 4.0"),
    ],
)
def test_route_cannot_expand_stationary_phase_maxima(
    tmp_path: Path,
    hold_seconds: float,
    capture_seconds: float,
    message: str,
) -> None:
    route, manifest = _inputs(
        tmp_path,
        target_hold_seconds=hold_seconds,
        stationary_capture_seconds=capture_seconds,
    )

    with pytest.raises(LiveAnchoredCameraRepositionError, match=message):
        execute_live_anchored_camera_reposition(
            route_path=route,
            candidate_manifest_path=manifest,
            output_root=tmp_path / "output",
            operator_acknowledged=True,
            preflight_fn=_preflight,
            gateway_factory=lambda identity: _Gateway(),
            preview_fn=_preview,
        )


def test_preview_rejection_sends_no_route_sample_and_releases_torque(
    tmp_path: Path,
) -> None:
    route, manifest = _inputs(tmp_path)
    gateway = _Gateway()

    with pytest.raises(
        LiveAnchoredCameraRepositionError, match="CPU preview rejected"
    ):
        execute_live_anchored_camera_reposition(
            route_path=route,
            candidate_manifest_path=manifest,
            output_root=tmp_path / "output",
            operator_acknowledged=True,
            preflight_fn=_preflight,
            gateway_factory=lambda identity: gateway,
            preview_fn=lambda actions, path: {
                "no_new_or_worsened_kinematic_contact": False,
                "external_contact_pairs": [["arm", "table"]],
            },
        )

    assert gateway.actions == []
    assert gateway.closed
    stored = json.loads(
        (tmp_path / "output/execution_receipt.json").read_text(encoding="utf-8")
    )
    assert stored["status"] == "stopped_safely_before_setup_motion"
    assert stored["physical_follower_torque_enabled"] is False


def test_bus_failure_preserves_partial_telemetry_and_releases_torque(
    tmp_path: Path,
) -> None:
    route, manifest = _inputs(tmp_path)
    gateway = _Gateway(fail_at=3)

    with pytest.raises(
        LiveAnchoredCameraRepositionError, match="fixture bus failure"
    ):
        execute_live_anchored_camera_reposition(
            route_path=route,
            candidate_manifest_path=manifest,
            output_root=tmp_path / "output",
            operator_acknowledged=True,
            preflight_fn=_preflight,
            gateway_factory=lambda identity: gateway,
            preview_fn=_preview,
            clock_fn=lambda: 0.0,
            sleep_fn=lambda delay: None,
        )

    assert gateway.closed
    stored = json.loads(
        (tmp_path / "output/execution_receipt.json").read_text(encoding="utf-8")
    )
    assert stored["status"] == "stopped_safely_after_partial_setup_motion"
    assert stored["telemetry"]["planned_sample_count"] > 3
    assert stored["telemetry"]["attempted_sample_count"] == 4
    assert stored["telemetry"]["sent_sample_count"] == 3
    assert stored["telemetry"]["partial_setup_motion_commanded"] is True
    assert stored["telemetry"]["last_sent_sample_index"] == 2
    assert stored["telemetry"]["first_unsent_sample_index"] == 3
    assert stored["telemetry"]["sha256"]
    assert stored["physical_follower_torque_enabled"] is False

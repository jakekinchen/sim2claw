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


def _inputs(tmp_path: Path) -> tuple[Path, Path]:
    route = tmp_path / "route.json"
    manifest = tmp_path / "candidate_manifest.json"
    _write(
        route,
        {
            "schema_version": WRIST_VIEW_ROUTE_SCHEMA,
            "route_id": "fixture-live-route",
            "reviewed_anchor_degrees": TORQUE_OFF.tolist(),
            "stage_targets_degrees": [TARGET.tolist()],
        },
    )
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
        self, elapsed_seconds: float, *, exact_requested_degrees: np.ndarray
    ) -> dict[str, object]:
        if self.fail_at is not None and len(self.actions) == self.fail_at:
            raise RuntimeError("fixture bus failure")
        action = np.asarray(exact_requested_degrees, dtype=np.float64).copy()
        self.actions.append(action)
        return {
            "elapsed_seconds": elapsed_seconds,
            "follower_actual_position_degrees": action.tolist(),
            "physical_follower_torque_enabled": True,
            "precompiled_exact_action": True,
            "safety_clamped": False,
            "rate_limited": False,
        }

    def close(self) -> None:
        self.closed = True


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
    assert np.array_equal(gateway.actions[0], SETTLED)
    assert np.array_equal(gateway.actions[-1], TARGET)
    assert gateway.closed


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
    assert stored["status"] == "stopped_safely"
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
    assert stored["telemetry"]["completed_samples"] == 3
    assert stored["telemetry"]["sha256"]
    assert stored["physical_follower_torque_enabled"] is False

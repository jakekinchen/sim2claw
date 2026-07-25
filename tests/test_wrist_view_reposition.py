from __future__ import annotations

import base64
import json
from pathlib import Path

import numpy as np
import pytest

from sim2claw.physical_canary import EXCITATION_CONTROL_SOURCE, GATEWAY_SCHEMA
from sim2claw.replay_eligibility import action_sha256
from sim2claw.scene import ROBOT_JOINTS
from sim2claw.wrist_view_reposition import (
    EXPECTED_LIVE_ANCHOR_DEGREES,
    MAX_STAGE_EXCURSION_DEGREES,
    SAMPLES_PER_STAGE,
    STAGE_TARGETS_DEGREES,
    WRIST_VIEW_EXECUTION_SCHEMA,
    WRIST_VIEW_PACKET_SCHEMA,
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


def _preflight(
    anchor: np.ndarray = EXPECTED_LIVE_ANCHOR_DEGREES,
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


def test_compile_previews_exact_three_stage_float64_path(tmp_path: Path) -> None:
    manifest_path = tmp_path / "candidate_manifest.json"
    packet_path = tmp_path / "packet.json"
    _candidate_manifest(manifest_path)

    packet = compile_wrist_view_reposition_packet(
        packet_path,
        candidate_manifest_path=manifest_path,
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
    previous = EXPECTED_LIVE_ANCHOR_DEGREES
    for index, (stage, target) in enumerate(
        zip(packet["stages"], STAGE_TARGETS_DEGREES, strict=True), start=1
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
        assert stage["inspect_wrist_camera_before_next_stage"] is (index < 3)
        previous = target


def test_review_and_execute_one_stage_exactly_then_torque_off(tmp_path: Path) -> None:
    manifest_path = tmp_path / "candidate_manifest.json"
    packet_path = tmp_path / "packet.json"
    review_path = tmp_path / "review.json"
    _candidate_manifest(manifest_path)
    compile_wrist_view_reposition_packet(
        packet_path,
        candidate_manifest_path=manifest_path,
        preflight_fn=_preflight,
    )
    review_wrist_view_reposition_packet(
        packet_path,
        review_path,
        reviewer="fixture-reviewer",
        decision_id="fixture-decision",
    )
    gateway = _Gateway(EXPECTED_LIVE_ANCHOR_DEGREES)

    receipt = execute_wrist_view_reposition_stage(
        packet_path,
        review_path,
        tmp_path / "execution-stage-1",
        stage_index=1,
        operator_acknowledged=True,
        preflight_fn=_preflight,
        gateway_factory=lambda identity: gateway,
        clock_fn=lambda: 0.0,
        sleep_fn=lambda delay: None,
    )

    assert receipt["schema_version"] == WRIST_VIEW_EXECUTION_SCHEMA
    assert receipt["status"] == "completed_wrist_view_reposition_stage"
    assert receipt["completed_samples"] == SAMPLES_PER_STAGE
    assert receipt["physical_follower_torque_enabled"] is False
    assert receipt["camera_opened"] is False
    assert gateway.closed
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    expected = np.frombuffer(
        base64.b64decode(packet["stages"][0]["frozen_action_payload"]["base64"]),
        dtype="<f8",
    ).reshape((SAMPLES_PER_STAGE, 6))
    assert np.asarray(gateway.samples, dtype="<f8").tobytes() == expected.tobytes()
    with pytest.raises(WristViewRepositionError, match="overwrite"):
        execute_wrist_view_reposition_stage(
            packet_path,
            review_path,
            tmp_path / "execution-stage-1",
            stage_index=1,
            operator_acknowledged=True,
            preflight_fn=_preflight,
            gateway_factory=lambda identity: _Gateway(
                EXPECTED_LIVE_ANCHOR_DEGREES
            ),
            clock_fn=lambda: 0.0,
            sleep_fn=lambda delay: None,
        )


def test_later_stage_requires_bound_prior_receipt(tmp_path: Path) -> None:
    manifest_path = tmp_path / "candidate_manifest.json"
    packet_path = tmp_path / "packet.json"
    review_path = tmp_path / "review.json"
    _candidate_manifest(manifest_path)
    compile_wrist_view_reposition_packet(
        packet_path,
        candidate_manifest_path=manifest_path,
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
            preflight_fn=lambda: _preflight(STAGE_TARGETS_DEGREES[0]),
            gateway_factory=lambda identity: _Gateway(STAGE_TARGETS_DEGREES[0]),
        )


def test_preview_rejects_new_external_contact_contract(tmp_path: Path) -> None:
    manifest_path = tmp_path / "candidate_manifest.json"
    _candidate_manifest(manifest_path)
    actions = [
        np.linspace(
            EXPECTED_LIVE_ANCHOR_DEGREES,
            STAGE_TARGETS_DEGREES[0],
            SAMPLES_PER_STAGE,
        ).astype("<f8")
    ]
    preview = preview_wrist_view_actions(actions, manifest_path)
    assert preview["external_contact_pairs"] == []
    assert preview["contact_pairs_unchanged_or_removed_only"]
    assert preview["no_new_or_worsened_kinematic_contact"]

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from sim2claw.physical_canary import (
    EXCITATION_CONTROL_SOURCE,
    GATEWAY_SCHEMA,
    EXECUTION_RECEIPT_SCHEMA,
    NORMALIZATION_PACKET_SCHEMA,
    NORMALIZATION_RECEIPT_SCHEMA,
    PHYSICAL_CANARY_PACKET_SCHEMA,
    PhysicalCanaryError,
    compile_physical_canary_normalization,
    compile_physical_canary_packet,
    execute_physical_canary_packet,
)
from sim2claw.replay_eligibility import MANIFEST_SCHEMA, action_sha256


PORT = "/dev/follower-fixture"
CALIBRATION = "a" * 64
ANCHOR_DEGREES = np.asarray(
    [-3.6923, -105.0, 99.9121, -105.0, -74.5934, 2.9691], dtype=np.float64
)


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _preflight() -> dict[str, object]:
    return {
        "schema_version": GATEWAY_SCHEMA,
        "control_source": EXCITATION_CONTROL_SOURCE,
        "real_leader_opened": False,
        "follower_port": PORT,
        "follower_calibration_sha256": CALIBRATION,
        "follower_start_degrees": ANCHOR_DEGREES.tolist(),
        "follower_calibrated_minimum": [-180.0] * 5 + [0.0],
        "follower_calibrated_maximum": [180.0] * 5 + [100.0],
        "physical_follower_torque_enabled": False,
        "device_configuration_rewritten": False,
    }


def _bundle(path: Path, *, elbow_variation: bool = False) -> dict[str, object]:
    degrees = np.repeat(ANCHOR_DEGREES[None, :], 8, axis=0)
    degrees[:, 0] += [0.0, 0.5, 1.0, 0.5, 0.0, -0.5, -1.0, 0.0]
    if elbow_variation:
        degrees[2, 2] += 0.5
    actions = np.deg2rad(degrees).astype("<f8", copy=False)
    raw = actions.tobytes(order="C")
    digest = action_sha256(actions)
    bundle = {
        "schema_version": MANIFEST_SCHEMA,
        "canary_schema_version": "sim2claw.zero_contact_canary_bundle.v1",
        "simulation_only": True,
        "evaluator_admission": False,
        "physical_authority": False,
        "candidate_digest": "b" * 64,
        "identity": {
            "robot": {
                "follower_port": PORT,
                "follower_calibration_sha256": CALIBRATION,
                "gateway_schema": GATEWAY_SCHEMA,
            }
        },
        "initial_state": {"joint_position": actions[0].tolist()},
        "timestamps_seconds": (np.arange(len(actions), dtype=np.float64) / 20.0).tolist(),
        "frozen_action_payload": {
            "encoding": "little_endian_float64_c_order",
            "shape": list(actions.shape),
            "base64": base64.b64encode(raw).decode("ascii"),
            "sha256": digest,
            "simulation_consumer_sha256": digest,
        },
        "requested_actions": actions.tolist(),
        "applied_actions": actions.tolist(),
        "requested_action_sha256": digest,
        "applied_action_sha256": digest,
    }
    _write(path, bundle)
    return bundle


def _receipts(tmp_path: Path, bundle: dict[str, object]) -> tuple[Path, Path]:
    contact_path = tmp_path / "contact.json"
    _write(
        contact_path,
        {
            "candidate_digest": bundle["candidate_digest"],
            "action_consumer_sha256": bundle["frozen_action_payload"]["sha256"],
            "status": "rejected_forbidden_contact",
            "simulation_no_contact_admitted": False,
            "physical_authority": False,
            "native_contact_audit": {
                "first_forbidden_contact": {
                    "body_a": "left_shoulder",
                    "body_b": "left_lower_arm",
                }
            },
        },
    )
    normalization_path = tmp_path / "normalization-result.json"
    _write(
        normalization_path,
        {
            "schema_version": NORMALIZATION_RECEIPT_SCHEMA,
            "status": "completed_follower_normalization",
            "hardware_identity": {
                "gateway_schema": GATEWAY_SCHEMA,
                "follower_port": PORT,
                "follower_calibration_sha256": CALIBRATION,
            },
            "final_actual_degrees": ANCHOR_DEGREES.tolist(),
            "target_degrees": ANCHOR_DEGREES.tolist(),
            "physical_follower_torque_enabled": False,
            "physical_motion_commanded": True,
        },
    )
    return contact_path, normalization_path


class _Gateway:
    def __init__(self) -> None:
        self.samples: list[np.ndarray] = []
        self.closed = False

    def open(self, *, enable_motion: bool, paired_pose_confirmed: bool) -> dict[str, object]:
        assert enable_motion and paired_pose_confirmed
        return {"follower_start_degrees": ANCHOR_DEGREES.tolist()}

    def sample(self, timestamp: float, *, exact_requested_degrees: np.ndarray) -> dict[str, object]:
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
    started = False
    finished = False

    def start(self) -> dict[str, object]:
        self.started = True
        return {"started": True}

    def finish(self, **kwargs: object) -> dict[str, object]:
        del kwargs
        self.finished = True
        return {"finished": True}


def _preview(
    actions: np.ndarray, bundle_path: Path, bundle: dict[str, object]
) -> dict[str, object]:
    del bundle_path, bundle
    return {
        "exact_physical_action_sha256": action_sha256(actions),
        "no_new_or_worsened_kinematic_contact": True,
        "external_contact_pairs": [],
    }


def test_physical_canary_freshly_freezes_post_normalization_pan_bytes(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle.json"
    bundle = _bundle(bundle_path)
    contact_path, normalization_path = _receipts(tmp_path, bundle)
    packet_path = tmp_path / "packet.json"
    packet = compile_physical_canary_packet(
        bundle_path,
        packet_path,
        contact_receipt_path=contact_path,
        normalization_receipt_path=normalization_path,
        preflight_fn=_preflight,
        preview_fn=_preview,
    )
    assert packet["schema_version"] == PHYSICAL_CANARY_PACKET_SCHEMA
    payload = packet["frozen_action_payload"]
    actions = np.frombuffer(
        base64.b64decode(payload["base64"]), dtype="<f8"
    ).reshape(payload["shape"])
    assert packet["source_pre_normalization_bundle"]["actions_used_for_hardware"] is False
    assert packet["action_sha256"] != bundle["frozen_action_payload"]["sha256"]
    assert action_sha256(actions) == packet["action_sha256"]
    assert np.array_equal(actions[-1], actions[0])
    assert np.all(actions[:, 1:] == actions[0, 1:])
    assert np.max(np.abs(actions[:, 0] - actions[0, 0])) == 1.0
    assert packet["post_normalization_simulation_preview"][
        "exact_physical_action_sha256"
    ] == packet["action_sha256"]


def test_normalization_plan_is_bounded_and_execution_is_torque_off(tmp_path: Path) -> None:
    plan_path = tmp_path / "normalization-plan.json"
    plan = compile_physical_canary_normalization(
        plan_path,
        preflight_fn=lambda: {
            **_preflight(),
            "follower_start_degrees": [-3.6923, -108.0, 99.9121, -108.0, -74.5934, 2.9691],
            "follower_calibrated_minimum": [-180.0, -107.0, -180.0, -107.0, -180.0, 0.0],
        },
    )
    assert plan["schema_version"] == NORMALIZATION_PACKET_SCHEMA
    assert plan["changed_joint_indices"] == [1, 3]
    assert plan["timestamps_seconds"][0] == 0.2
    assert np.all(np.asarray(plan["actions_degrees"])[0] >= np.asarray(plan["calibrated_minimum_degrees"]))
    assert plan["actions_degrees"][0][1] == -107.0
    assert plan["actions_degrees"][0][1] != plan["anchor_degrees"][1]
    assert max(abs(a - b) for a, b in zip(plan["anchor_degrees"], plan["target_degrees"])) <= 5.0
    assert plan["target_degrees"][1] == -107.0
    assert plan["target_degrees"][3] == -107.0


def test_physical_canary_execution_requires_admission_and_never_overwrites(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle.json"
    bundle = _bundle(bundle_path)
    contact_path, normalization_path = _receipts(tmp_path, bundle)
    packet_path = tmp_path / "packet.json"
    compile_physical_canary_packet(bundle_path, packet_path, contact_receipt_path=contact_path, normalization_receipt_path=normalization_path, preflight_fn=_preflight, preview_fn=_preview)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["physical_packet_execution_admitted"] = True
    packet["independent_review"] = {
        "reviewer": "fixture-reviewer",
        "reviewed_at": "2026-07-25T00:00:00Z",
        "decision_id": "fixture-canary",
        "frozen_action_reviewed": True,
        "hardware_clear_workspace_acknowledged": True,
        "hardware_readiness_acknowledged": True,
        "diagnostic_sim_model_mismatch_acknowledged": True,
    }
    packet["plan_sha256"] = hashlib.sha256(json.dumps({k: v for k, v in packet.items() if k != "plan_sha256"}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    packet_path.write_text(json.dumps(packet, sort_keys=True) + "\n", encoding="utf-8")
    gateway = _Gateway()
    capture = _Capture()
    result = execute_physical_canary_packet(packet_path, tmp_path / "execution", operator_acknowledged=True, preflight_fn=_preflight, gateway_factory=lambda identity: gateway, capture_factory=lambda path: capture, clock_fn=lambda: 0.0, sleep_fn=lambda delay: None)
    assert result["schema_version"] == EXECUTION_RECEIPT_SCHEMA
    assert result["physical_follower_torque_enabled"] is False
    assert result["physical_motion_commanded"] is True
    assert gateway.closed and capture.started and capture.finished
    with pytest.raises(PhysicalCanaryError, match="overwrite"):
        execute_physical_canary_packet(packet_path, tmp_path / "execution", operator_acknowledged=True, preflight_fn=_preflight, gateway_factory=lambda identity: _Gateway(), capture_factory=lambda path: _Capture(), clock_fn=lambda: 0.0, sleep_fn=lambda delay: None)

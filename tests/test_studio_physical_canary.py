from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from sim2claw.studio_catalog import _physical_canary_episodes, build_catalog


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _fixture(root: Path) -> Path:
    execution = (
        root
        / "runs/physical_excitation/fixture/physical-canary-v1/execution-v4"
    )
    camera = execution / "dual_camera"
    camera.mkdir(parents=True)
    overhead = camera / "overhead_c922.mp4"
    wrist = camera / "wrist_d405.browser.mp4"
    overhead.write_bytes(b"overhead")
    wrist.write_bytes(b"wrist")
    samples = execution / "joint_samples.jsonl"
    samples.write_text("{}\n{}\n", encoding="utf-8")
    raw = b"frozen-action-bytes" * 6
    action_sha = hashlib.sha256(raw).hexdigest()
    payload = {
        "base64": base64.b64encode(raw).decode("ascii"),
        "encoding": "little_endian_float64_c_order",
        "shape": [2, 6],
        "sha256": action_sha,
        "simulation_consumer_sha256": action_sha,
    }
    packet = {
        "schema_version": "sim2claw.physical_canary_packet.v1",
        "physical_authority": False,
        "physical_packet_execution_admitted": True,
        "frozen_action_payload": payload,
        "action_sha256": action_sha,
        "simulation_contact_classification": "diagnostic_sim_model_baseline_self_contact",
        "hardware_gate": "no_new_or_worsened_kinematic_contact_plus_clear_workspace_and_bounded_normalization",
        "independent_review": {
            "frozen_action_reviewed": True,
            "hardware_clear_workspace_acknowledged": True,
            "hardware_readiness_acknowledged": True,
            "diagnostic_sim_model_mismatch_acknowledged": True,
        },
    }
    packet_body = json.dumps(packet, sort_keys=True, separators=(",", ":"))
    packet["plan_sha256"] = hashlib.sha256(packet_body.encode()).hexdigest()
    packet_path = execution.parent / "physical-canary-packet-v2.json"
    _write(packet_path, packet)
    packet_sha = hashlib.sha256(packet_path.read_bytes()).hexdigest()

    def camera_report(path: Path, name: str) -> dict[str, object]:
        return {
            "browser_video_path": path.name,
            "browser_video_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "camera_name": name,
            "configured_fps": 30.0,
            "action_start_video_offset_seconds": 0.1,
            "action_stop_video_offset_seconds": 0.5,
            "diagnostic_only": True,
            "metric_depth": False,
            "orientation_rotation_degrees": 0,
            "status": "completed",
            "browser_frame_count": 12,
        }

    receipt = {
        "schema_version": "sim2claw.physical_canary_execution_receipt.v1",
        "status": "completed_physical_canary",
        "packet_sha256": packet_sha,
        "action_sha256": action_sha,
        "completed_samples": 2,
        "joint_samples_path": str(samples),
        "joint_samples_sha256": hashlib.sha256(samples.read_bytes()).hexdigest(),
        "camera_finished": {
            "overhead": camera_report(overhead, "C922"),
            "wrist": camera_report(wrist, "D405"),
        },
        "physical_motion_commanded": True,
        "physical_follower_torque_enabled": False,
        "physical_authority": False,
        "gateway_constructed": True,
        "stop_before_further_robot_command": True,
        "observed_pan_excursion_degrees": 0.6153846153846154,
    }
    receipt_path = execution / "execution_receipt.json"
    _write(receipt_path, receipt)
    return receipt_path


def test_catalog_surfaces_hash_bound_physical_canary_observation(tmp_path: Path) -> None:
    _fixture(tmp_path)
    rows = _physical_canary_episodes(tmp_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "observed"
    assert row["action_array_sha256"]
    assert len(row["recording_feeds"]) == 2
    assert row["physical_authority"] is False
    assert "task consequence" in row["missing_evidence"]
    catalog = build_catalog(tmp_path)
    assert any(item["task_id"] == "physical_canary_follower_only_v1" for item in catalog["episodes"])


def test_catalog_rejects_physical_canary_sample_hash_drift(tmp_path: Path) -> None:
    receipt_path = _fixture(tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["joint_samples_sha256"] = "0" * 64
    _write(receipt_path, receipt)
    assert _physical_canary_episodes(tmp_path) == []

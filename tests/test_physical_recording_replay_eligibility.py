from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from sim2claw.replay_eligibility import (
    PHYSICAL_SAMPLE_SCHEMA,
    action_sha256,
    materialize_physical_recording_exact_replay,
)
from sim2claw.scene import ROBOT_JOINTS


def _recording(tmp_path: Path, rows: list[dict[str, object]] | None = None) -> Path:
    recording = tmp_path / "recording"
    recording.mkdir(parents=True)
    if rows is None:
        rows = [
            {
                "schema_version": PHYSICAL_SAMPLE_SCHEMA,
                "episode_id": "fixture-physical-001",
                "sample_index": index,
                "timestamp_monotonic_seconds": 10.0 + (index * 0.05),
                "follower_requested_degrees": [index + joint for joint in range(6)],
                "follower_command_degrees": [index + joint for joint in range(6)],
                "follower_actual_position_degrees": [joint * 2.0 for joint in range(6)],
                "follower_actual_velocity_degrees_s": [joint * 0.1 for joint in range(6)],
                "assistance": 0,
                "intervention": 0,
                "rate_limited": False,
                "safety_clamped": False,
            }
            for index in range(3)
        ]
    samples = b"".join(
        (json.dumps(row, sort_keys=True) + "\n").encode("utf-8") for row in rows
    )
    (recording / "samples.jsonl").write_bytes(samples)
    receipt = {
        "schema_version": "sim2claw.manipulation_source_recording_receipt.v1",
        "source_sample_schema": PHYSICAL_SAMPLE_SCHEMA,
        "recording_id": "fixture-physical-001",
        "mode": "physical_follower",
        "proof_class": "physical_teleoperation_source_unqualified",
        "source_identity": {
            "kind": "leader_teleoperation",
            "proof_class": "physical_teleoperation_source_unqualified",
        },
        "backend": {"schema_version": "sim2claw.so101_physical_gateway.v2"},
        "sample_count": len(rows),
        "samples_path": "samples.jsonl",
        "samples_sha256": hashlib.sha256(samples).hexdigest(),
        "assistance_frames": 0,
        "intervention_frames": 0,
        "lineage": {
            "collection_kind": "original_source_episode",
            "corrective_suffix_parent_state_sha256": None,
        },
    }
    (recording / "recording_receipt.json").write_text(
        json.dumps(receipt), encoding="utf-8"
    )
    return recording


def _run(recording: Path, tmp_path: Path) -> tuple[dict[str, object], dict[str, object]]:
    manifest_path = tmp_path / "manifest.json"
    report = materialize_physical_recording_exact_replay(
        recording, manifest_path, tmp_path / "report.json"
    )
    return json.loads(manifest_path.read_text(encoding="utf-8")), report


def test_finalized_physical_recording_materializes_eligible_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden_access(*args: object, **kwargs: object) -> None:
        raise AssertionError("hardware access is forbidden")

    monkeypatch.setattr(
        "sim2claw.teleop_recording.PhysicalFollowerBackend.sample",
        forbidden_access,
    )
    manifest, report = _run(_recording(tmp_path), tmp_path)
    other_manifest, _ = _run(_recording(tmp_path / "other"), tmp_path / "other")

    requested = np.asarray(manifest["requested_actions"], dtype=np.float64)
    assert manifest == other_manifest
    assert manifest["conversion_provenance"]["recording_receipt_path"] == (
        "recording_receipt.json"
    )
    assert manifest["conversion_provenance"]["samples_path"] == "samples.jsonl"
    assert report["exact_replay_eligible"] is True
    assert manifest["joint_order"] == list(ROBOT_JOINTS)
    assert manifest["initial_state"]["joint_position"] == pytest.approx(
        np.deg2rad([0, 2, 4, 6, 8, 10])
    )
    assert manifest["initial_state"]["joint_velocity"] == pytest.approx(
        np.deg2rad([0, 0.1, 0.2, 0.3, 0.4, 0.5])
    )
    assert manifest["requested_action_sha256"] == action_sha256(requested)
    assert report["action_semantics"]["applied_field_compatibility_meaning"] == (
        "gateway_sent_command"
    )
    assert report["claim_limits"]["gateway_sent_is_actuator_ack"] is False
    assert report["physical_authority"] is False
    assert report["evaluator_admission"] is False


def test_requested_and_gateway_sent_divergence_is_rejected(tmp_path: Path) -> None:
    recording = _recording(tmp_path)
    rows = [
        json.loads(line)
        for line in (recording / "samples.jsonl").read_text().splitlines()
    ]
    rows[1]["follower_command_degrees"][0] += 0.1

    _, report = _run(_recording(tmp_path / "changed", rows), tmp_path / "changed")

    assert report["exact_replay_eligible"] is False
    assert "requested_applied_mismatch" in {
        reason["code"] for reason in report["rejection_reasons"]
    }


def test_nonproduction_recording_receipt_schema_is_rejected(tmp_path: Path) -> None:
    recording = _recording(tmp_path)
    receipt_path = recording / "recording_receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["schema_version"] = "sim2claw.teleop_recording_receipt.v1"
    receipt_path.write_text(json.dumps(receipt))

    with pytest.raises(ValueError, match="not finalized-recorder v1"):
        _run(recording, tmp_path)


@pytest.mark.parametrize("field", ("rate_limited", "safety_clamped"))
def test_rate_limit_or_clamp_fails_closed(tmp_path: Path, field: str) -> None:
    recording = _recording(tmp_path)
    rows = [
        json.loads(line)
        for line in (recording / "samples.jsonl").read_text().splitlines()
    ]
    rows[1][field] = True

    with pytest.raises(ValueError, match="rate limiting or safety clamping"):
        _run(_recording(tmp_path / field, rows), tmp_path / field)


def test_nonmonotonic_recorded_time_is_not_repaired(tmp_path: Path) -> None:
    recording = _recording(tmp_path)
    rows = [
        json.loads(line)
        for line in (recording / "samples.jsonl").read_text().splitlines()
    ]
    rows[2]["timestamp_monotonic_seconds"] = rows[1]["timestamp_monotonic_seconds"]

    with pytest.raises(ValueError, match="not strictly increasing"):
        _run(_recording(tmp_path / "time", rows), tmp_path / "time")


@pytest.mark.parametrize("velocity", (None, [0.0] * 5, [0, 0, 0, 0, 0, "bad"]))
def test_missing_or_invalid_initial_velocity_fails_closed(
    tmp_path: Path, velocity: object
) -> None:
    recording = _recording(tmp_path)
    rows = [
        json.loads(line)
        for line in (recording / "samples.jsonl").read_text().splitlines()
    ]
    if velocity is None:
        rows[0].pop("follower_actual_velocity_degrees_s")
    else:
        rows[0]["follower_actual_velocity_degrees_s"] = velocity

    with pytest.raises(ValueError, match="no valid measured follower velocity"):
        _run(_recording(tmp_path / "velocity", rows), tmp_path / "velocity")

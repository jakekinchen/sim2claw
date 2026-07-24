from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from sim2claw.current_workcell_measurement import (
    BASELINE_SCHEMA,
    CurrentWorkcellMeasurementError,
    RECEIPT_SCHEMA,
    capture_torque_off_baseline,
    load_measurement_contract,
)
from sim2claw.learning_factory_artifacts import canonical_digest, sha256_file


CONTRACT = (
    Path(__file__).parents[1]
    / "configs"
    / "evaluations"
    / "current_100mm_measurement_acquisition_v1.json"
)


def _preflight() -> dict[str, Any]:
    contract = load_measurement_contract(CONTRACT)
    hardware = contract["hardware_identity"]
    return {
        "devices": {
            "leader": {"port": hardware["leader_port"]},
            "follower": {"port": hardware["follower_port"]},
        },
        "calibrations": {
            "leader": {"sha256": hardware["leader_calibration_sha256"]},
            "follower": {"sha256": hardware["follower_calibration_sha256"]},
        },
        "modes": {"physical_follower": {"ready": True}},
    }


class FakeGateway:
    instances: list["FakeGateway"] = []

    def __init__(self, identity: Any, *, configure_devices: bool) -> None:
        self.identity = identity
        self.configure_devices = configure_devices
        self.closed = False
        self.samples = 0
        self.__class__.instances.append(self)

    def open(self, *, enable_motion: bool) -> dict[str, Any]:
        assert enable_motion is False
        return {
            "physical_follower_torque_enabled": False,
            "paired_pose_registration_ready": False,
        }

    def sample_read_only(self) -> dict[str, Any]:
        self.samples += 1
        return {
            "schema_version": "sim2claw.so101_read_only_telemetry.v1",
            "leader_degrees": [0.0] * 6,
            "follower_degrees": [1.0] * 6,
            "available_motor_current_raw": {"shoulder_pan": 2.0},
            "physical_follower_torque_enabled": False,
            "physical_motion_commanded": False,
        }

    def close(self) -> None:
        self.closed = True


class FakeVideo:
    def __init__(self, output_path: Path, **_: Any) -> None:
        self.output_path = output_path
        self.log_path = output_path.with_suffix(".ffmpeg.log")

    def start(self) -> dict[str, Any]:
        self.output_path.write_bytes(b"video")
        self.log_path.write_bytes(b"log")
        return {
            "status": "recording",
            "video_path": self.output_path.name,
            "ffmpeg_log_path": self.log_path.name,
        }

    def ensure_running(self) -> None:
        return None

    def finish(self, **_: Any) -> dict[str, Any]:
        return {
            "status": "completed",
            "video_path": self.output_path.name,
            "ffmpeg_log_path": self.log_path.name,
        }


class FailingFinalizeVideo(FakeVideo):
    def finish(self, **_: Any) -> dict[str, Any]:
        raise RuntimeError("camera finalization failed")


def test_torque_off_baseline_is_content_addressed_and_has_no_motion(
    tmp_path: Path,
) -> None:
    ticks = iter(float(index) / 1000.0 for index in range(100))
    receipt = capture_torque_off_baseline(
        tmp_path / "capture",
        contract_path=CONTRACT,
        sample_count=3,
        sample_interval_seconds=0.0,
        preflight_fn=_preflight,
        gateway_factory=FakeGateway,
        video_factory=FakeVideo,
        clock=lambda: next(ticks),
        wall_clock=lambda: "2026-07-23T00:00:00+00:00",
        sleep=lambda _: None,
    )

    assert receipt["schema_version"] == RECEIPT_SCHEMA
    assert receipt["proof_class"] == "physical_torque_off_read_only_baseline"
    assert receipt["sample_count"] == 3
    assert receipt["fresh_current_sample_count"] == 3
    assert receipt["authority"] == {
        "physical_motion_commanded": False,
        "physical_task_claim_admitted": False,
        "training_admission": False,
        "promotion_authority": False,
    }
    unsigned = dict(receipt)
    recorded = unsigned.pop("receipt_sha256")
    assert recorded == canonical_digest(unsigned)
    rows = [
        json.loads(line)
        for line in (tmp_path / "capture" / "torque_off_samples.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [row["sample_index"] for row in rows] == [0, 1, 2]
    assert all(row["schema_version"] == BASELINE_SCHEMA for row in rows)
    assert receipt["artifact_sha256"]["torque_off_samples.jsonl"] == sha256_file(
        tmp_path / "capture" / "torque_off_samples.jsonl"
    )
    assert FakeGateway.instances[-1].closed is True


def test_torque_off_baseline_rejects_identity_drift_and_output_replay(
    tmp_path: Path,
) -> None:
    drifted = _preflight()
    drifted["devices"]["follower"]["port"] = "/dev/wrong"
    with pytest.raises(CurrentWorkcellMeasurementError, match="identity changed"):
        capture_torque_off_baseline(
            tmp_path / "drift",
            contract_path=CONTRACT,
            sample_count=1,
            sample_interval_seconds=0.0,
            preflight_fn=lambda: drifted,
            gateway_factory=FakeGateway,
            video_factory=FakeVideo,
        )

    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "existing").write_text("do not overwrite", encoding="utf-8")
    with pytest.raises(CurrentWorkcellMeasurementError, match="not empty"):
        capture_torque_off_baseline(
            occupied,
            contract_path=CONTRACT,
            sample_count=1,
            sample_interval_seconds=0.0,
            preflight_fn=_preflight,
            gateway_factory=FakeGateway,
            video_factory=FakeVideo,
        )


def test_gateway_closes_when_camera_finalization_fails(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="camera finalization failed"):
        capture_torque_off_baseline(
            tmp_path / "capture",
            contract_path=CONTRACT,
            sample_count=1,
            sample_interval_seconds=0.0,
            preflight_fn=_preflight,
            gateway_factory=FakeGateway,
            video_factory=FailingFinalizeVideo,
        )
    assert FakeGateway.instances[-1].closed is True


def test_contract_rejects_authority_widening(tmp_path: Path) -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    widened = copy.deepcopy(contract)
    widened["authority"]["training_admission"] = True
    path = tmp_path / "widened.json"
    path.write_text(json.dumps(widened), encoding="utf-8")
    with pytest.raises(CurrentWorkcellMeasurementError, match="widened"):
        load_measurement_contract(path)

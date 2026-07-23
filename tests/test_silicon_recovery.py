from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sim2claw.studio_server import (
    SUPERVISED_REPLAY_RECORDING_ID,
    latest_supervised_replay,
)
from sim2claw.teleop_recording import RECEIPT_SCHEMA


def _write_bound_history(root: Path) -> tuple[Path, Path]:
    source = (
        root
        / "datasets"
        / "manipulation_source_recordings"
        / f"b2-to-b1__{SUPERVISED_REPLAY_RECORDING_ID}"
    )
    source.mkdir(parents=True)
    source_samples = b'{"sample_index":0}\n'
    (source / "samples.jsonl").write_bytes(source_samples)
    (source / "recording_receipt.json").write_text(
        json.dumps(
            {
                "schema_version": RECEIPT_SCHEMA,
                "recording_id": SUPERVISED_REPLAY_RECORDING_ID,
                "samples_sha256": hashlib.sha256(source_samples).hexdigest(),
            }
        ),
        encoding="utf-8",
    )

    replay = root / "runs" / "physical_replays" / "20260719T120000Z-fixture"
    replay.mkdir(parents=True)
    replay_samples = b'{"sample_index":0,"command_exact":true}\n'
    (replay / "replay_samples.jsonl").write_bytes(replay_samples)
    receipt = replay / "replay_receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "schema_version": "sim2claw.physical_trace_replay_attempt.v1",
                "run_id": replay.name,
                "source_recording_id": SUPERVISED_REPLAY_RECORDING_ID,
                "source_samples_sha256": hashlib.sha256(source_samples).hexdigest(),
                "replay_samples_path": "replay_samples.jsonl",
                "replay_samples_sha256": hashlib.sha256(replay_samples).hexdigest(),
                "commands_requested_from_source_trace": True,
                "status": "completed",
                "completed_at": "2026-07-19T12:00:00+00:00",
                "completed_sample_count": 1,
                "source_sample_count": 1,
                "exact_command_sample_count": 1,
                "safety_clamped_sample_count": 0,
                "physical_follower_torque_enabled": False,
                "task_success_verified": False,
                "learned_policy_verified": False,
                "failure_message": None,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return receipt, replay / "replay_samples.jsonl"


def test_historical_physical_replay_requires_source_and_output_byte_binding(
    tmp_path: Path,
) -> None:
    receipt, replay_samples = _write_bound_history(tmp_path)
    projected = latest_supervised_replay(tmp_path)
    assert projected is not None
    assert projected["proof_class"] == "unqualified_physical_command_replay"
    assert projected["task_success_verified"] is False
    assert projected["physical_authority"] is False
    assert projected["receipt_sha256"] == hashlib.sha256(receipt.read_bytes()).hexdigest()
    assert projected["replay_samples_sha256"] == hashlib.sha256(
        replay_samples.read_bytes()
    ).hexdigest()


def test_historical_physical_replay_fails_closed_on_replay_or_source_drift(
    tmp_path: Path,
) -> None:
    _receipt, replay_samples = _write_bound_history(tmp_path)
    replay_samples.write_bytes(replay_samples.read_bytes() + b"tamper\n")
    assert latest_supervised_replay(tmp_path) is None

    other = tmp_path / "source-drift"
    _receipt, _replay_samples = _write_bound_history(other)
    source_samples = next(
        (other / "datasets" / "manipulation_source_recordings").glob("*/samples.jsonl")
    )
    source_samples.write_bytes(source_samples.read_bytes() + b"tamper\n")
    assert latest_supervised_replay(other) is None

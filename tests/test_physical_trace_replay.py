from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

import numpy as np

from sim2claw.physical_gateway import GatewayIdentity
from sim2claw.physical_trace_replay import (
    PHYSICAL_TRACE_REPLAY_SCHEMA,
    PhysicalTraceReplayError,
    load_physical_trace_source,
    run_physical_trace_replay,
    validate_replay_envelope,
)
from sim2claw.teleop_recording import RECEIPT_SCHEMA


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def read(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += max(0.0, seconds)


class FakeReplayLeader:
    def __init__(self) -> None:
        self.target = np.zeros(6, dtype=np.float64)

    def set_target(self, values: np.ndarray) -> None:
        self.target = values.copy()


class FakeReplayGateway:
    def __init__(self) -> None:
        self.leader = FakeReplayLeader()
        self.lower_limits = np.asarray([-180.0] * 5 + [0.0])
        self.upper_limits = np.asarray([180.0] * 5 + [100.0])
        self.closed = False

    def open(
        self,
        *,
        enable_motion: bool,
        paired_pose_confirmed: bool = False,
    ) -> dict[str, Any]:
        assert enable_motion and paired_pose_confirmed
        return {
            "leader_start_degrees": [0.0] * 6,
            "follower_start_degrees": [0.0] * 6,
            "physical_follower_torque_enabled": True,
        }

    def sample(self, elapsed_seconds: float) -> dict[str, Any]:
        return {
            "elapsed_seconds": elapsed_seconds,
            "follower_command_degrees": self.leader.target.tolist(),
            "follower_actual_position_degrees": self.leader.target.tolist(),
            "safety_clamped": False,
        }

    def close(self) -> None:
        self.closed = True


class PhysicalTraceReplayTest(unittest.TestCase):
    def _recording(self, root: Path) -> Path:
        recording = root / "datasets" / "act_source_recordings" / "fixture"
        recording.mkdir(parents=True)
        rows = [
            {
                "sample_index": index,
                "timestamp_monotonic_seconds": 100.0 + index * 0.1,
                "follower_command_degrees": [float(index), 0, 0, 0, 0, 1],
            }
            for index in range(3)
        ]
        samples = "".join(json.dumps(row) + "\n" for row in rows)
        samples_path = recording / "samples.jsonl"
        samples_path.write_text(samples, encoding="utf-8")
        (recording / "recording_receipt.json").write_text(
            json.dumps(
                {
                    "schema_version": RECEIPT_SCHEMA,
                    "recording_id": "fixture-recording",
                    "mode": "physical_follower",
                    "label": "Fixture physical episode",
                    "sample_count": len(rows),
                    "samples_sha256": hashlib.sha256(
                        samples.encode("utf-8")
                    ).hexdigest(),
                }
            ),
            encoding="utf-8",
        )
        return recording

    def test_source_receipt_and_samples_must_match(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            recording = self._recording(root)
            source = load_physical_trace_source(
                recording,
                allowed_root=root / "datasets" / "act_source_recordings",
            )
            self.assertEqual(source.commands.shape, (3, 6))
            (recording / "samples.jsonl").write_text("changed\n", encoding="utf-8")
            with self.assertRaisesRegex(
                PhysicalTraceReplayError,
                "do not match",
            ):
                load_physical_trace_source(
                    recording,
                    allowed_root=root / "datasets" / "act_source_recordings",
                )

    def test_envelope_rejects_a_distant_start_pose(self) -> None:
        with self.assertRaisesRegex(PhysicalTraceReplayError, "too far"):
            validate_replay_envelope(
                np.asarray([[50.0, 0, 0, 0, 0, 0]]),
                np.zeros(6),
                lower_limits=np.asarray([-180.0] * 5 + [0.0]),
                upper_limits=np.asarray([180.0] * 5 + [100.0]),
            )

    def test_guarded_replay_writes_receipt_and_closes_gateway(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            recording = self._recording(root)
            clock = FakeClock()
            gateway = FakeReplayGateway()
            identity = GatewayIdentity("leader", "follower", "a" * 64, "b" * 64)
            report = run_physical_trace_replay(
                recording,
                operator_acknowledged=True,
                output_root=root / "runs",
                identity=identity,
                gateway_factory=lambda _identity: gateway,
                clock=clock.read,
                sleep=clock.sleep,
                allowed_source_root=root / "datasets" / "act_source_recordings",
            )
            self.assertEqual(report["schema_version"], PHYSICAL_TRACE_REPLAY_SCHEMA)
            self.assertEqual(report["status"], "completed")
            self.assertEqual(report["completed_sample_count"], 3)
            self.assertEqual(report["exact_command_sample_count"], 3)
            self.assertFalse(report["physical_follower_torque_enabled"])
            self.assertTrue(gateway.closed)
            receipt = Path(report["run_directory"]) / "replay_receipt.json"
            self.assertTrue(receipt.is_file())


if __name__ == "__main__":
    unittest.main()

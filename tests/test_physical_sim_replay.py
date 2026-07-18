from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from sim2claw.physical_sim_replay import (
    SIM_REPLAY_SCHEMA,
    physical_values_to_sim,
    replay_physical_recording,
)


class PhysicalSimulationReplayTest(unittest.TestCase):
    def test_gripper_and_body_conversion(self) -> None:
        converted = physical_values_to_sim(
            [0, 90, -90, 180, -180, 50],
            [-0.2, 1.8],
        )
        self.assertAlmostEqual(converted[0], 0.0)
        self.assertAlmostEqual(converted[1], 1.57079632679)
        self.assertAlmostEqual(converted[5], 0.8)

    def test_physical_trace_replays_and_writes_bounded_claim_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            samples_path = root / "samples.jsonl"
            rows = []
            for index in range(4):
                values = [index * 0.4, 0.0, 0.0, 0.0, 0.0, 20.0]
                rows.append(
                    {
                        "timestamp_monotonic_seconds": index * 0.05,
                        "follower_command_degrees": values,
                        "follower_actual_position_degrees": values,
                    }
                )
            samples_path.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            sample_hash = hashlib.sha256(samples_path.read_bytes()).hexdigest()
            (root / "recording_receipt.json").write_text(
                json.dumps(
                    {
                        "recording_id": "fixture-physical",
                        "mode": "physical_follower",
                        "sample_hz": 20,
                        "samples_sha256": sample_hash,
                    }
                ),
                encoding="utf-8",
            )
            report = replay_physical_recording(root)
            self.assertEqual(report["schema_version"], SIM_REPLAY_SCHEMA)
            self.assertEqual(report["sample_count"], 4)
            self.assertEqual(report["comparison_scope"], "joint_space_command_response_only")
            self.assertFalse(report["learned_policy_verified"])
            self.assertFalse(report["object_or_contact_dynamics_verified"])
            self.assertTrue((root / "sim_replay_trace.jsonl").is_file())
            self.assertTrue((root / "sim_replay_receipt.json").is_file())


if __name__ == "__main__":
    unittest.main()

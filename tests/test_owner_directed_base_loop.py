from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from sim2claw.owner_directed_base_loop import (
    LOOP_MOVES,
    OWNER_DIRECTED_LOOP_SCHEMA,
    OwnerDirectedLoopError,
    build_loop_plan,
    run_owner_directed_base_loop,
)
from sim2claw.teleop_recording import RECEIPT_SCHEMA


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def read(self) -> float:
        return self.now

    def advance(self, seconds: float = 1.0) -> None:
        self.now += seconds


class OwnerDirectedBaseLoopTest(unittest.TestCase):
    def _repo(self, root: Path) -> Path:
        source_root = root / "datasets" / "manipulation_source_recordings"
        for index, move in enumerate(LOOP_MOVES, start=1):
            recording = source_root / move.recording_directory_name
            if recording.is_dir():
                continue
            recording.mkdir(parents=True)
            rows = [
                {
                    "sample_index": sample,
                    "timestamp_monotonic_seconds": 100.0 + sample,
                    "follower_command_degrees": [float(sample), 0, 0, 0, 0, 1],
                }
                for sample in range(2)
            ]
            samples = "".join(json.dumps(row) + "\n" for row in rows)
            (recording / "samples.jsonl").write_text(samples, encoding="utf-8")
            (recording / "recording_receipt.json").write_text(
                json.dumps(
                    {
                        "schema_version": RECEIPT_SCHEMA,
                        "recording_id": f"fixture-{index:02d}",
                        "mode": "physical_follower",
                        "label": move.move_id,
                        "sample_count": len(rows),
                        "samples_sha256": hashlib.sha256(
                            samples.encode("utf-8")
                        ).hexdigest(),
                    }
                ),
                encoding="utf-8",
            )
        return root

    def test_plan_is_fixed_hash_validated_base_inverse_base_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self._repo(Path(temporary))
            plan = build_loop_plan(repo, duration_seconds=20)
            self.assertEqual(plan["move_count"], 12)
            self.assertEqual(plan["recorded_motion_seconds"], 12.0)
            self.assertEqual(plan["moves"][0]["move_id"], "b1_to_b2")
            self.assertTrue(plan["moves"][1]["reverse"])
            self.assertEqual(plan["moves"][5]["move_id"], "g2_to_g1")
            self.assertEqual(plan["moves"][6]["move_id"], "b2_to_b1")
            self.assertTrue(plan["moves"][6]["reverse"])
            self.assertFalse(plan["moves"][7]["reverse"])
            self.assertEqual(plan["moves"][-1]["move_id"], "g1_to_g2")
            self.assertFalse(plan["physical_task_success_verified"])

    def test_plan_rejects_a_horizon_shorter_than_recorded_motion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self._repo(Path(temporary))
            with self.assertRaisesRegex(OwnerDirectedLoopError, "exceeds"):
                build_loop_plan(repo, duration_seconds=11)

    def test_directional_plan_uses_only_the_requested_six_fixed_moves(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self._repo(Path(temporary))
            forward = build_loop_plan(repo, duration_seconds=20, moves=LOOP_MOVES[:6])
            reverse = build_loop_plan(repo, duration_seconds=20, moves=LOOP_MOVES[6:])
            self.assertEqual(forward["move_count"], 6)
            self.assertEqual(reverse["move_count"], 6)
            self.assertEqual(forward["moves"][0]["move_id"], "b1_to_b2")
            self.assertEqual(reverse["moves"][0]["move_id"], "b2_to_b1")

    def test_motion_requires_both_explicit_acknowledgements(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self._repo(Path(temporary))
            with self.assertRaisesRegex(OwnerDirectedLoopError, "--yes"):
                run_owner_directed_base_loop(
                    repo,
                    operator_acknowledged=False,
                    owner_directed_unqualified_labels=True,
                    duration_seconds=20,
                )
            with self.assertRaisesRegex(OwnerDirectedLoopError, "mapping flag"):
                run_owner_directed_base_loop(
                    repo,
                    operator_acknowledged=True,
                    owner_directed_unqualified_labels=False,
                    duration_seconds=20,
                )

    def test_loop_runs_twelve_guarded_replays_and_thirteen_checkpoints(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self._repo(Path(temporary))
            clock = FakeClock()
            replays: list[str] = []
            preflight_count = 0

            def preflight() -> dict[str, Any]:
                nonlocal preflight_count
                preflight_count += 1
                return {"passed": True, "physical_follower_torque_enabled": False}

            def checkpoint(destination: Path) -> dict[str, Any]:
                body = destination.name.encode("utf-8")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(body)
                return {
                    "frame_sha256": hashlib.sha256(body).hexdigest(),
                    "relative_path": destination.name,
                    "registration_state": "operator_registration_required",
                    "task_success_verified": False,
                }

            def replay(recording: Path, **kwargs: Any) -> dict[str, Any]:
                self.assertTrue(kwargs["operator_acknowledged"])
                self.assertEqual(
                    kwargs["allowed_source_root"],
                    (repo / "datasets" / "manipulation_source_recordings").resolve(),
                )
                replays.append(recording.name)
                clock.advance()
                return {
                    "run_id": f"run-{len(replays):02d}",
                    "run_directory": f"runs/replay-{len(replays):02d}",
                    "status": "completed",
                    "completed_sample_count": 2,
                    "source_sample_count": 2,
                    "safety_clamped_sample_count": 0,
                    "physical_follower_torque_enabled": False,
                }

            report = run_owner_directed_base_loop(
                repo,
                operator_acknowledged=True,
                owner_directed_unqualified_labels=True,
                duration_seconds=20,
                output_root=repo / "runs" / "loop",
                checkpoint=checkpoint,
                replay_runner=replay,
                preflight_runner=preflight,
                clock=clock.read,
            )
            self.assertEqual(report["schema_version"], OWNER_DIRECTED_LOOP_SCHEMA)
            self.assertEqual(
                report["status"], "completed_command_cycle_unverified_task_outcome"
            )
            self.assertEqual(len(replays), 12)
            self.assertEqual(len(report["replays"]), 12)
            self.assertEqual(len(report["checkpoints"]), 13)
            self.assertEqual(preflight_count, 2)
            self.assertFalse(report["torque_enabled_after"])
            self.assertFalse(report["physical_task_success_verified"])
            saved = json.loads(
                (Path(report["attempt_directory"]) / "attempt_receipt.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(saved["status"], report["status"])


if __name__ == "__main__":
    unittest.main()

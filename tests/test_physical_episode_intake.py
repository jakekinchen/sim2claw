from __future__ import annotations

import json
import unittest
from pathlib import Path


INTAKE_PATH = (
    Path(__file__).parents[1]
    / "configs"
    / "data"
    / "physical_teleop_episode_intake_20260718.json"
)


class PhysicalEpisodeIntakeContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.intake = json.loads(INTAKE_PATH.read_text(encoding="utf-8"))

    def test_cohort_is_versioned_and_never_self_promotes(self) -> None:
        self.assertEqual(
            self.intake["schema_version"],
            "sim2claw.physical_teleop_episode_intake.v1",
        )
        episodes = self.intake["episodes"]
        self.assertEqual(len(episodes), 5)
        self.assertEqual(
            len({episode["recording_id"] for episode in episodes}),
            len(episodes),
        )
        self.assertEqual(
            sum(episode["motion_trace"]["sample_count"] for episode in episodes),
            2186,
        )
        self.assertEqual(self.intake["cohort_summary"]["training_rows_admitted"], 0)
        self.assertFalse(self.intake["routing_decision"]["physical_task_success_proven"])
        self.assertFalse(self.intake["routing_decision"]["learned_policy_verified"])
        self.assertTrue(
            all(
                episode["training_admission"]
                != "admitted"
                for episode in episodes
            )
        )

    def test_paths_are_relative_ignored_artifact_pointers(self) -> None:
        for episode in self.intake["episodes"]:
            source = Path(episode["source_path"])
            replay = Path(episode["sim_replay"]["receipt_path"])
            self.assertFalse(source.is_absolute())
            self.assertFalse(replay.is_absolute())
            self.assertEqual(source.parts[:2], ("datasets", "act_source_recordings"))
            self.assertEqual(replay.parts[:2], ("datasets", "act_source_recordings"))
            self.assertEqual(len(episode["receipt_sha256"]), 64)
            self.assertEqual(len(episode["samples_sha256"]), 64)
            self.assertEqual(len(episode["overhead_video_sha256"]), 64)
            self.assertEqual(len(episode["sim_replay"]["receipt_sha256"]), 64)
            self.assertEqual(len(episode["sim_replay"]["state_trace_sha256"]), 64)
            self.assertEqual(
                episode["sim_replay"]["state_trace_frame_count"],
                episode["motion_trace"]["sample_count"],
            )

    def test_metadata_conflicts_and_lane_holds_are_explicit(self) -> None:
        statuses = [episode["metadata_status"] for episode in self.intake["episodes"]]
        self.assertEqual(sum(status.startswith("conflict_") for status in statuses), 3)
        self.assertEqual(
            sum(status.startswith("ambiguous_") for status in statuses),
            1,
        )
        self.assertEqual(
            sum(status.startswith("consistent_") for status in statuses),
            1,
        )
        self.assertTrue(
            all(
                "admitted" not in episode["groot_route"]
                or episode["groot_route"].startswith("not_admitted")
                for episode in self.intake["episodes"]
            )
        )
        self.assertEqual(
            self.intake["failed_attempt_diagnostics"]["same_session_sample_rows"],
            0,
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import unittest
from pathlib import Path


CATALOG_PATH = (
    Path(__file__).parents[1]
    / "configs"
    / "data"
    / "physical_pawn_move_catalog_20260719.json"
)


class PhysicalPawnMoveCatalogContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

    def test_latest_cohort_is_receipt_grounded_and_redo_is_kept(self) -> None:
        self.assertEqual(
            self.catalog["schema_version"],
            "sim2claw.physical_pawn_move_catalog.v1",
        )
        self.assertEqual(len(self.catalog["episodes"]), 16)
        self.assertEqual(len(self.catalog["moves"]), 9)
        self.assertEqual(
            self.catalog["moves"][7]["preferred_recording_id"],
            "20260719T032810Z-9e623c5e",
        )
        discarded = self.catalog["discarded_recordings"]
        self.assertEqual(len(discarded), 1)
        self.assertEqual(discarded[0]["recording_id"], "20260719T032722Z-84dc04de")
        self.assertEqual(discarded[0]["recovery_location"], "user_trash")

    def test_conflicting_folder_titles_are_visible(self) -> None:
        conflicts = [
            episode
            for episode in self.catalog["episodes"]
            if episode["metadata_status"].startswith("conflict_")
        ]
        self.assertEqual(len(conflicts), 9)
        self.assertTrue(all(episode["receipt_sha256"] for episode in conflicts))
        self.assertTrue(all(episode["samples_sha256"] for episode in conflicts))
        self.assertTrue(all(episode["overhead_video_sha256"] for episode in conflicts))

    def test_catalog_never_self_promotes_raw_physical_traces(self) -> None:
        self.assertFalse(self.catalog["routing_decision"]["callable_policy_authorized"])
        self.assertFalse(self.catalog["routing_decision"]["learned_policy_verified"])
        self.assertEqual(self.catalog["routing_decision"]["training_rows_admitted"], 0)
        self.assertTrue(all(not episode["callable_policy"] for episode in self.catalog["episodes"]))
        self.assertTrue(all(not move["callable_policy"] for move in self.catalog["moves"]))


if __name__ == "__main__":
    unittest.main()

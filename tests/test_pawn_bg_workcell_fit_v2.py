from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sim2claw.pawn_bg_workcell_fit import WorkcellFitError
from sim2claw.pawn_bg_workcell_fit_v2 import (
    CATALOG_PATH,
    SPLIT_PATH,
    _enforce_minimum_scope,
    _split_entries,
    classify_move,
    fresh_held_out_entries,
    load_workcell_contract_v2,
    move_suite_episodes,
)


def _catalog(labels: list[str]) -> dict[str, object]:
    return {
        "episodes": [
            {"recording_id": f"episode-{index}", "folder_label": label}
            for index, label in enumerate(labels)
        ]
    }


class PawnBGWorkcellFitV2Tests(unittest.TestCase):
    def test_contract_keeps_candidate_non_authorizing(self) -> None:
        contract = load_workcell_contract_v2()
        self.assertEqual(contract["schema_version"], "sim2claw.pawn_bg_workcell_fit.v2")
        self.assertTrue(contract["admission"]["declared_before_held_out_opened"])
        self.assertEqual(contract["admission"]["maximum_held_out_event_rms_m"], 0.06)
        self.assertTrue(contract["admission"]["previously_opened_episodes_are_reference_only"])
        self.assertTrue(all(value is False for value in contract["authority"].values()))

    def test_contract_schema_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            path.write_text(json.dumps({"schema_version": "unexpected"}), encoding="utf-8")
            with self.assertRaisesRegex(WorkcellFitError, "unexpected v2 workcell fit"):
                load_workcell_contract_v2(path)

    def test_move_classification_covers_rank_file_and_diagonal(self) -> None:
        self.assertEqual(classify_move("b1", "b2"), ("rank", 1))
        self.assertEqual(classify_move("e1", "f1"), ("file", 1))
        self.assertEqual(classify_move("c1", "d2"), ("diagonal", 1))
        self.assertEqual(classify_move("b1", "g2"), ("diagonal", 5))
        self.assertEqual(classify_move("b1", "b8"), ("rank", 7))
        with self.assertRaisesRegex(WorkcellFitError, "cannot start and end"):
            classify_move("d2", "d2")

    def test_scope_admits_cross_file_and_diagonal_moves(self) -> None:
        catalog = _catalog([
            "b1-to-b2", "e1-to-f1", "c1-to-d2", "g1-to-g2-redo",
            "not-a-move", "d2-to-d2",
        ])
        entries = move_suite_episodes(catalog)
        by_label = {entry.episode["folder_label"]: entry for entry in entries}
        self.assertEqual(
            set(by_label), {"b1-to-b2", "e1-to-f1", "c1-to-d2", "g1-to-g2-redo"}
        )
        self.assertEqual(by_label["e1-to-f1"].move_class, "file")
        self.assertEqual(by_label["c1-to-d2"].move_class, "diagonal")
        self.assertEqual(by_label["g1-to-g2-redo"].move_class, "rank")

    def test_destination_occupancy_flags_only_foreign_pieces(self) -> None:
        catalog = _catalog(["b2-to-b1", "b2-to-c2", "c1-to-d2", "e1-to-f1"])
        by_label = {
            entry.episode["folder_label"]: entry
            for entry in move_suite_episodes(catalog)
        }
        # b1 is the selected b-file piece's own baseline square: no conflict.
        self.assertFalse(by_label["b2-to-b1"].baseline_destination_square_occupied)
        # c2 and f1 hold other baseline pieces the replay does not relocate.
        self.assertTrue(by_label["b2-to-c2"].baseline_destination_square_occupied)
        self.assertTrue(by_label["e1-to-f1"].baseline_destination_square_occupied)
        # d2 is empty in the baseline sparse layout.
        self.assertFalse(by_label["c1-to-d2"].baseline_destination_square_occupied)

    def test_replay_support_requires_a_baseline_piece_file(self) -> None:
        entries = move_suite_episodes(_catalog(["a1-to-a2", "b1-to-b2"]))
        by_label = {entry.episode["folder_label"]: entry for entry in entries}
        self.assertFalse(by_label["a1-to-a2"].replay_supported)
        self.assertTrue(by_label["b1-to-b2"].replay_supported)

    def test_minimum_scope_fails_closed_without_diagonal_coverage(self) -> None:
        contract = load_workcell_contract_v2()
        rank_only = move_suite_episodes(_catalog(
            [f"{file_}1-to-{file_}2" for file_ in "bcdefg"] * 2
        ))
        with self.assertRaisesRegex(WorkcellFitError, "at least"):
            _enforce_minimum_scope(rank_only, contract)

    def test_frozen_catalog_and_split_provide_the_expected_v2_scope(self) -> None:
        contract = load_workcell_contract_v2()
        catalog = json.loads(CATALOG_PATH.read_bytes())
        split = json.loads(SPLIT_PATH.read_bytes())
        membership = {
            episode["episode_id"]: episode["split"] for episode in split["episodes"]
        }
        scope = move_suite_episodes(catalog)
        train = _split_entries(scope, membership, "train")
        counts = _enforce_minimum_scope(train, contract)
        self.assertEqual(counts, {"rank": 11, "file": 3, "diagonal": 1})
        fresh = fresh_held_out_entries(scope, membership, contract)
        self.assertEqual(
            [entry.episode["folder_label"] for entry in fresh], ["c1-to-d2"]
        )
        self.assertEqual(fresh[0].move_class, "diagonal")
        opened = set(
            contract["data_binding"]["previously_opened_held_out_recording_ids"]
        )
        for entry in fresh:
            self.assertNotIn(entry.episode["recording_id"], opened)


if __name__ == "__main__":
    unittest.main()

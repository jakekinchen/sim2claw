from __future__ import annotations

import unittest

from sim2claw.groot_multisource_dataset import load_groot_multisource_contract


class GrootMultisourceDatasetContractTests(unittest.TestCase):
    def test_contract_freezes_admitted_mixture_and_counts(self) -> None:
        contract = load_groot_multisource_contract()
        self.assertTrue(contract["frozen_before_export"])
        self.assertEqual(contract["dataset"]["unique_source_episode_count"], 73)
        self.assertEqual(contract["dataset"]["derived_dataset_episode_count"], 96)
        self.assertEqual(contract["dataset"]["frame_count"], 41088)
        self.assertEqual(
            contract["dataset"]["expected_effective_h16_start_count"], 39648
        )
        self.assertEqual(contract["dataset"]["held_out_rows"], 0)

    def test_current_pawn_weight_is_not_mislabeled_as_new_evidence(self) -> None:
        contract = load_groot_multisource_contract()
        pawn = contract["cohorts"][2]
        self.assertEqual(pawn["geometry_class"], "operator_updated_chess_workcell_v3_100mm")
        self.assertEqual(pawn["unique_source_episode_count"], 1)
        self.assertEqual(pawn["dataset_repetitions_per_source_episode"], 24)
        self.assertEqual(
            pawn["repetition_semantics"],
            "sampling_weight_only_not_independent_evidence",
        )

    def test_failure_physical_and_heldout_rows_are_excluded(self) -> None:
        contract = load_groot_multisource_contract()
        excluded = contract["excluded_evidence"]
        self.assertEqual(excluded["physical_training_rows"], 0)
        self.assertEqual(excluded["counterexample_training_rows"], 0)
        self.assertFalse(excluded["raw_failure_actions_may_enter_behavior_cloning"])
        self.assertEqual(contract["sealed_evidence"]["held_out_rows_used"], 0)
        self.assertFalse(contract["authority"]["physical_authority"])


if __name__ == "__main__":
    unittest.main()

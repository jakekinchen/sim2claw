from __future__ import annotations

import unittest

from sim2claw.groot_multisource_dataset import (
    load_groot_multisource_contract,
    validate_multisource_episode_alignment,
)


class GrootMultisourceDatasetContractTests(unittest.TestCase):
    @staticmethod
    def alignment_fields() -> dict[str, object]:
        return {
            "episode_index": 4,
            "row_count": 3,
            "parquet_row_count": 3,
            "parquet_episode_indices": [4, 4, 4],
            "global_indices": [10, 11, 12],
            "expected_global_index": 10,
            "task_indices": [2, 2, 2],
            "task_count": 3,
            "video": {"width": 256, "height": 256, "frames": 3, "fps": 20},
        }

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

    def test_preflight_rejects_video_frame_misalignment(self) -> None:
        fields = self.alignment_fields()
        fields["video"] = {"width": 256, "height": 256, "frames": 2, "fps": 20}
        with self.assertRaisesRegex(ValueError, "video alignment drifted"):
            validate_multisource_episode_alignment(**fields)  # type: ignore[arg-type]

    def test_preflight_rejects_task_misalignment(self) -> None:
        fields = self.alignment_fields()
        fields["task_indices"] = [2, 1, 2]
        with self.assertRaisesRegex(ValueError, "task schedule drifted"):
            validate_multisource_episode_alignment(**fields)  # type: ignore[arg-type]

    def test_preflight_rejects_index_misalignment(self) -> None:
        fields = self.alignment_fields()
        fields["global_indices"] = [10, 12, 13]
        with self.assertRaisesRegex(ValueError, "indices are not contiguous"):
            validate_multisource_episode_alignment(**fields)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()

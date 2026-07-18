from __future__ import annotations

import json
import hashlib
import unittest
from pathlib import Path


CONTRACT_PATH = (
    Path(__file__).parents[1]
    / "configs"
    / "evaluations"
    / "pawn_rank12_bidirectional_v1.json"
)


class PawnRank12EvaluationContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_core_cases_are_exhaustive_and_bidirectional(self) -> None:
        cases = self.contract["cases"]
        self.assertEqual(len(cases), 16)
        expected = {
            (file_name, source_rank, destination_rank)
            for file_name in "abcdefgh"
            for source_rank, destination_rank in (("1", "2"), ("2", "1"))
        }
        actual = {
            (
                case["file"],
                case["source_square"][1],
                case["destination_square"][1],
            )
            for case in cases
        }
        self.assertEqual(actual, expected)
        self.assertEqual(len({case["case_id"] for case in cases}), 16)
        self.assertEqual(
            {case["source_square"] for case in cases},
            {f"{file_name}{rank}" for file_name in "abcdefgh" for rank in "12"},
        )
        self.assertEqual(
            {case["destination_square"] for case in cases},
            {f"{file_name}{rank}" for file_name in "abcdefgh" for rank in "12"},
        )

    def test_simulation_realizations_are_frozen_zero_row_held_outs(self) -> None:
        cases = self.contract["cases"]
        seeds = [seed for case in cases for seed in case["simulation_seeds"]]
        self.assertEqual(len(seeds), 48)
        self.assertEqual(len(set(seeds)), 48)
        self.assertEqual(
            len(self.contract["simulation_realization_slots"]),
            3,
        )
        self.assertTrue(all(case["training_rows"] == 0 for case in cases))
        scope = self.contract["benchmark_scope"]
        self.assertEqual(scope["simulation_episode_count"], 48)
        self.assertEqual(scope["evaluation_training_rows"], 0)
        self.assertFalse(scope["exact_evaluation_realizations_may_appear_in_training"])

    def test_strategy_and_promotion_boundaries_are_explicit(self) -> None:
        strategy = self.contract["strategy_policy"]
        self.assertFalse(strategy["lift_required"])
        self.assertTrue(strategy["push_allowed"])
        self.assertTrue(strategy["pick_lift_place_allowed"])
        evaluator = self.contract["consequence_evaluator"]
        self.assertEqual(
            evaluator["owner"],
            "separate_cpu_fp32_consequence_evaluator",
        )
        self.assertTrue(evaluator["training_cannot_promote"])
        self.assertTrue(evaluator["diagnostic_reward_cannot_promote"])
        self.assertEqual(
            self.contract["scorecard"]["physical_denominator"],
            16,
        )

    def test_project_state_binds_the_frozen_contract_hash(self) -> None:
        project_state_path = (
            Path(__file__).parents[1]
            / "docs"
            / "autonomous-workflow"
            / "project_state.json"
        )
        project_state = json.loads(project_state_path.read_text(encoding="utf-8"))
        expected = hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest()
        locked = project_state["locked_product_evaluation"]
        self.assertEqual(locked["evaluation_set_id"], self.contract["evaluation_set_id"])
        self.assertEqual(locked["sha256"], expected)
        self.assertFalse(locked["training_or_policy_result_proven"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import hashlib
import unittest
from pathlib import Path


HISTORICAL_CONTRACT_PATH = (
    Path(__file__).parents[1]
    / "configs"
    / "evaluations"
    / "pawn_rank12_bidirectional_v1.json"
)
CONTRACT_PATH = (
    Path(__file__).parents[1]
    / "configs"
    / "evaluations"
    / "pawn_rank12_bidirectional_v2.json"
)


class PawnRank12EvaluationContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_core_cases_are_exhaustive_and_bidirectional(self) -> None:
        cases = self.contract["skills"]
        self.assertEqual(len(cases), 12)
        expected = {
            (file_name, source_rank, destination_rank)
            for file_name in "bcdefg"
            for source_rank, destination_rank in (("1", "2"), ("2", "1"))
        }
        actual = {
            (
                case["column"],
                case["source_square"][1],
                case["destination_square"][1],
            )
            for case in cases
        }
        self.assertEqual(actual, expected)
        self.assertEqual(len({case["skill_id"] for case in cases}), 12)
        self.assertEqual(
            {case["source_square"] for case in cases},
            {f"{file_name}{rank}" for file_name in "bcdefg" for rank in "12"},
        )
        self.assertEqual(
            {case["destination_square"] for case in cases},
            {f"{file_name}{rank}" for file_name in "bcdefg" for rank in "12"},
        )

    def test_retrospective_corpus_is_not_a_checkpoint_held_out(self) -> None:
        scope = self.contract["benchmark_scope"]
        self.assertEqual(scope["directed_skill_count"], 12)
        self.assertTrue(scope["retrospective_source_episodes_may_populate_scorecard"])
        self.assertFalse(scope["retrospective_source_episodes_are_held_out"])
        self.assertFalse(scope["retrospective_source_episodes_can_promote_a_checkpoint"])
        self.assertTrue(scope["future_checkpoint_promotion_requires_separately_frozen_trials"])

    def test_strategy_and_promotion_boundaries_are_explicit(self) -> None:
        authority = self.contract["authority"]
        self.assertTrue(authority["runner_is_product_scorecard"])
        self.assertFalse(authority["retrospective_source_episode_can_promote"])
        self.assertTrue(authority["separate_cpu_fp32_evaluator_required_for_checkpoint_promotion"])
        self.assertFalse(authority["physical_authority"])
        self.assertEqual(
            self.contract["scorecard"]["primary_metric"],
            "macro_composable_success_rate_across_12_directed_skills",
        )

    def test_historical_v1_is_immutable_and_explicitly_superseded(self) -> None:
        self.assertEqual(
            hashlib.sha256(HISTORICAL_CONTRACT_PATH.read_bytes()).hexdigest(),
            "f3dac8b86cd7b0252153d25c0d5c09204079003ac9780642992fd10bc08e0d43",
        )
        supersession = self.contract["supersession"]
        self.assertEqual(supersession["supersedes_evaluation_set_id"], "pawn_rank12_bidirectional_v1")
        self.assertTrue(supersession["superseded_file_is_immutable_historical_evidence"])

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

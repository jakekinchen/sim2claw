from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from sim2claw.pawn_bg_reward import (
    CONTRACT_PATH,
    PawnBGRewardError,
    aggregate_scores,
    load_reward_contract,
    score_episode,
)


def _row(
    xyz: list[float], *, contact: bool = False, wrong: bool = False,
    collateral: float = 0.0, upright: float = 1.0, speed: float = 0.0,
    finite: bool = True,
) -> dict[str, object]:
    return {
        "piece_position_xyz_m": xyz,
        "piece_upright_cosine": upright,
        "piece_linear_speed_m_s": speed,
        "selected_piece_jaw_contact": contact,
        "wrong_piece_robot_contact": wrong,
        "maximum_other_piece_displacement_m": collateral,
        "finite_state": finite,
    }


class PawnBGRewardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = load_reward_contract()
        self.good_trace = [
            _row([0.0, 0.0, 0.10]),
            _row([0.0, 0.02, 0.15], contact=True),
            _row([0.0, 0.04445, 0.10]),
        ]

    def _score(self, **overrides: object) -> dict[str, object]:
        arguments: dict[str, object] = {
            "skill_id": "pawn_b1_to_b2",
            "trace": self.good_trace,
            "target_position_xyz_m": [0.0, 0.04445, 0.10],
            "initial_piece_height_m": 0.10,
            "evaluation_mode": "learned_policy",
            "action_owner": "model",
            "assistance_used": False,
        }
        arguments.update(overrides)
        return score_episode(self.contract, **arguments)  # type: ignore[arg-type]

    def test_good_model_trace_passes_task_and_policy(self) -> None:
        score = self._score()
        self.assertTrue(score["task_consequence_success"])
        self.assertTrue(score["policy_success"])
        self.assertEqual(score["diagnostic_reward"], 1.0)

    def test_reward_cannot_override_a_hard_gate(self) -> None:
        trace = copy.deepcopy(self.good_trace)
        trace[-1]["piece_position_xyz_m"] = [0.0, 0.051, 0.10]
        score = self._score(trace=trace)
        self.assertGreater(score["diagnostic_reward"], 0.5)
        self.assertFalse(score["gate_results"]["composable_center"])
        self.assertFalse(score["task_consequence_success"])
        self.assertFalse(score["policy_success"])

    def test_wrong_contact_collateral_and_no_release_fail(self) -> None:
        trace = copy.deepcopy(self.good_trace)
        trace[1]["wrong_piece_robot_contact"] = True
        trace[-1]["selected_piece_jaw_contact"] = True
        trace[-1]["maximum_other_piece_displacement_m"] = 0.01
        score = self._score(trace=trace)
        self.assertFalse(score["gate_results"]["no_wrong_piece_contact"])
        self.assertFalse(score["gate_results"]["released"])
        self.assertFalse(score["gate_results"]["collateral_within_limit"])
        self.assertFalse(score["task_consequence_success"])

    def test_source_replay_never_reports_policy_success(self) -> None:
        score = self._score(
            evaluation_mode="source_demonstration_replay",
            action_owner="physical_teleoperator",
        )
        self.assertTrue(score["task_consequence_success"])
        self.assertFalse(score["policy_success_reportable"])
        self.assertFalse(score["policy_success"])

    def test_model_mode_rejects_human_action_ownership(self) -> None:
        score = self._score(action_owner="physical_teleoperator")
        self.assertFalse(score["model_owned_action_gate"])
        self.assertFalse(score["policy_success"])

    def test_aggregate_requires_exact_frozen_order(self) -> None:
        scores = []
        for skill in self.contract["ordered_skills"]:
            score = self._score(skill_id=skill["skill_id"])
            score["source_square"] = skill["source_square"]
            score["destination_square"] = skill["destination_square"]
            scores.append(score)
        aggregate = aggregate_scores(self.contract, scores)
        self.assertEqual(aggregate["macro_task_consequence_success_rate"], 1.0)
        with self.assertRaisesRegex(PawnBGRewardError, "frozen 12-skill order"):
            aggregate_scores(self.contract, list(reversed(scores)))

    def test_contract_tamper_is_fail_closed_and_type_strict(self) -> None:
        mutations = []
        extra = copy.deepcopy(self.contract)
        extra["unexpected"] = False
        mutations.append(extra)
        bool_numeric = copy.deepcopy(self.contract)
        bool_numeric["hard_gates"]["minimum_piece_rise_m"] = True
        mutations.append(bool_numeric)
        provenance = copy.deepcopy(self.contract)
        provenance["provenance"]["held_out_data_used"] = 0
        mutations.append(provenance)
        reordered = copy.deepcopy(self.contract)
        reordered["ordered_skills"][0], reordered["ordered_skills"][1] = (
            reordered["ordered_skills"][1], reordered["ordered_skills"][0]
        )
        mutations.append(reordered)
        duplicate = copy.deepcopy(self.contract)
        duplicate["ordered_skills"][1] = copy.deepcopy(duplicate["ordered_skills"][0])
        mutations.append(duplicate)
        missing = copy.deepcopy(self.contract)
        missing["ordered_skills"].pop()
        mutations.append(missing)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "contract.json"
            for payload in mutations:
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(PawnBGRewardError):
                    load_reward_contract(path)

    def test_bound_product_bytes_are_checked(self) -> None:
        payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        payload["product_binding"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "contract.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(PawnBGRewardError, "product binding drifted"):
                load_reward_contract(path)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import copy
import unittest

from sim2claw.groot_chess import groot_task_contract_sha256
from sim2claw.groot_chess_recovery import (
    RECOVERY_FAMILIES,
    collect_recovery_expert_episode,
    finalize_recovery_verdict,
    load_recovery_task_contract,
)


class GrootChessRecoveryContractTest(unittest.TestCase):
    def test_contract_freezes_disjoint_balanced_splits_without_mutating_v1(self) -> None:
        task = load_recovery_task_contract()
        self.assertEqual(
            task["base_task"]["contract_sha256"],
            groot_task_contract_sha256(),
        )
        self.assertEqual(len(task["training_episodes"]), 48)
        self.assertEqual(len(task["held_out_episodes"]), 24)
        self.assertEqual(
            {row["family"] for row in task["training_episodes"]},
            RECOVERY_FAMILIES,
        )
        self.assertEqual(
            {row["family"] for row in task["held_out_episodes"]},
            RECOVERY_FAMILIES,
        )
        self.assertTrue(
            all(row["training_rows"] == 0 for row in task["held_out_episodes"])
        )

    def test_representative_held_out_experts_pass_every_family_for_both_pieces(
        self,
    ) -> None:
        task = load_recovery_task_contract()
        episodes = [
            collect_recovery_expert_episode(
                task,
                split="held_out",
                episode_index=index,
                render_frames=False,
            )
            for index in (0, 1, 6, 7, 12, 13, 18, 19)
        ]
        self.assertEqual(
            {episode.perturbation["family"] for episode in episodes},
            RECOVERY_FAMILIES,
        )
        self.assertEqual(
            {episode.piece for episode in episodes},
            {"black_rook_a8", "black_king_e8"},
        )
        for episode in episodes:
            self.assertTrue(episode.verdict["success"])
            self.assertEqual(episode.states.shape[1], 6)
            self.assertEqual(episode.states.shape, episode.actions.shape)
            self.assertEqual(episode.contact_metrics["assistance_frames"], 0)

    def test_contact_recovery_is_declared_and_reacquires_after_fault(self) -> None:
        task = load_recovery_task_contract()
        episode = collect_recovery_expert_episode(
            task,
            split="training",
            episode_index=36,
            render_frames=False,
        )
        self.assertTrue(episode.verdict["success"])
        self.assertEqual(episode.contact_metrics["fault_injection_count"], 1)
        self.assertGreater(
            episode.contact_metrics["recovery_target_contact_events"],
            0,
        )
        self.assertIn("recover_clear", episode.phases)
        self.assertIn("recover_close", episode.phases)

    def test_negative_fixtures_reject_spills_contacts_capture_dragging_and_toppling(
        self,
    ) -> None:
        task = load_recovery_task_contract()
        base_verdict = {
            "gates": {
                "maximum_other_piece_displacement": {
                    "measured": 0.0,
                    "comparison": "<=",
                    "threshold": 0.006,
                    "passed": True,
                },
                "minimum_piece_rise": {
                    "measured": 0.09,
                    "comparison": ">=",
                    "threshold": 0.04,
                    "passed": True,
                },
                "final_xy_error": {
                    "measured": 0.0,
                    "comparison": "<=",
                    "threshold": 0.015,
                    "passed": True,
                },
                "final_upright_cosine": {
                    "measured": 1.0,
                    "comparison": ">=",
                    "threshold": 0.95,
                    "passed": True,
                },
            }
        }
        contacts = {
            "maximum_other_piece_displacement_m": 0.0,
            "first_piece_contact": "black_rook_a8",
            "wrong_piece_contacts": [],
            "fault_injection_count": 0,
            "recovery_target_contact_events": 0,
        }

        fixtures = {
            "failed_capture": ("minimum_piece_rise", 0.0),
            "dragging": ("final_xy_error", 0.08),
            "late_toppling": ("final_upright_cosine", 0.5),
        }
        for name, (gate_name, measured) in fixtures.items():
            with self.subTest(name=name):
                verdict_input = copy.deepcopy(base_verdict)
                verdict_input["gates"][gate_name]["measured"] = measured
                verdict_input["gates"][gate_name]["passed"] = False
                verdict = finalize_recovery_verdict(
                    verdict_input,
                    task,
                    perturbation_family="nominal",
                    target_piece="black_rook_a8",
                    contact_metrics=copy.deepcopy(contacts),
                )
                self.assertFalse(verdict["success"])

        spill = copy.deepcopy(contacts)
        spill["maximum_other_piece_displacement_m"] = 0.02
        verdict = finalize_recovery_verdict(
            copy.deepcopy(base_verdict),
            task,
            perturbation_family="nominal",
            target_piece="black_rook_a8",
            contact_metrics=spill,
        )
        self.assertFalse(verdict["success"])

        wrong_contact = copy.deepcopy(contacts)
        wrong_contact["first_piece_contact"] = "black_king_e8"
        wrong_contact["wrong_piece_contacts"] = ["black_king_e8"]
        verdict = finalize_recovery_verdict(
            copy.deepcopy(base_verdict),
            task,
            perturbation_family="nominal",
            target_piece="black_rook_a8",
            contact_metrics=wrong_contact,
        )
        self.assertFalse(verdict["success"])


if __name__ == "__main__":
    unittest.main()

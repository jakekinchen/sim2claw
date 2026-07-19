from __future__ import annotations

import unittest

from sim2claw.contact_prior import load_contact_prior_contract
from sim2claw.contact_sensitivity import summarize_contact_sensitivity


def _receipt(variant: str, *, success: bool, rise: float, action_hash: str) -> dict:
    return {
        "simulator_variant": {
            "variant_id": variant,
            "variant_sha256": variant * 8,
        },
        "success": success,
        "terminal_outcome": "held_rook_above_board" if success else "act_episode_failed",
        "failed_gates": [] if success else ["final_piece_rise"],
        "episode": {
            "maximum_piece_rise_m": rise,
            "final_piece_rise_m": rise,
            "longest_contact_control_steps": 100,
            "final_contact_fraction": 1.0,
            "contact_timing": {"first_contact_control_step": 900},
        },
        "artifacts": {
            "action_trace_sha256": action_hash,
            "state_trace_sha256": variant,
        },
        "stability": {"finite_state": True},
    }


class ContactSensitivitySummaryTest(unittest.TestCase):
    def test_contract_pins_the_only_accepted_rook_lift_checkpoint(self) -> None:
        contract = load_contact_prior_contract()
        self.assertEqual(
            contract["policy"]["accepted_checkpoint_sha256"],
            "f0a58e49dcaa320d3d0b86ef839b2e39893b65cf26a738954e2bb833dd3144fc",
        )
        self.assertFalse(contract["policy"]["weights_mutable"])

    def test_summary_separates_categorical_and_quantitative_sensitivity(self) -> None:
        report = summarize_contact_sensitivity(
            [
                _receipt("nominal", success=True, rise=0.09, action_hash="a"),
                _receipt("low", success=True, rise=0.08, action_hash="a"),
                _receipt("high", success=False, rise=0.01, action_hash="b"),
            ]
        )
        self.assertTrue(report["sensitivity"]["categorical_success_changed"])
        self.assertTrue(report["sensitivity"]["policy_actions_changed_with_contact_state"])
        self.assertAlmostEqual(report["sensitivity"]["maximum_piece_rise_range_m"], 0.08)
        self.assertTrue(report["rows"][0]["action_trace_matches_nominal"])
        self.assertFalse(report["rows"][2]["action_trace_matches_nominal"])


if __name__ == "__main__":
    unittest.main()

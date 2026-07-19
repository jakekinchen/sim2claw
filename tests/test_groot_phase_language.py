from __future__ import annotations

import unittest

from sim2claw.groot_chess import load_groot_task_contract
from sim2claw.groot_phase_language import (
    load_phase_language_contract,
    phase_for_sample_step,
    phase_language_contract_sha256,
    phase_prompt,
    phase_row_ranges,
)


class GrootPhaseLanguageTest(unittest.TestCase):
    def test_contract_is_bound_and_action_free(self) -> None:
        contract = load_phase_language_contract()
        self.assertEqual(len(phase_language_contract_sha256()), 64)
        self.assertFalse(contract["scheduler"]["uses_observation_geometry"])
        self.assertFalse(contract["scheduler"]["selects_or_modifies_actions"])
        self.assertEqual(contract["authority"]["action_assistance_frames"], 0)
        self.assertFalse(contract["authority"]["single_prompt_end_to_end_claim"])

    def test_phase_boundaries_cover_the_episode(self) -> None:
        base = load_groot_task_contract()
        ranges = phase_row_ranges(base)
        self.assertEqual(
            ranges,
            {
                "stand_off": (0, 42),
                "advance": (42, 80),
                "close": (80, 122),
                "lift": (122, 172),
                "transit": (172, 222),
                "lower": (222, 272),
                "release": (272, 298),
                "retreat": (298, 323),
                "settle": (323, 363),
            },
        )
        for phase, (start, end) in ranges.items():
            self.assertEqual(phase_for_sample_step(base, start), phase)
            self.assertEqual(phase_for_sample_step(base, end - 1), phase)
        with self.assertRaises(ValueError):
            phase_for_sample_step(base, 363)

    def test_prompt_exposes_only_current_language_subtask(self) -> None:
        base = load_groot_task_contract()
        contract = load_phase_language_contract()
        case = base["training_cases"][0]
        prompt = phase_prompt(contract, case, "transit")
        self.assertIn("black rook", prompt)
        self.assertIn("a8", prompt)
        self.assertIn("b6", prompt)
        self.assertIn("Current subtask: carry", prompt)


if __name__ == "__main__":
    unittest.main()

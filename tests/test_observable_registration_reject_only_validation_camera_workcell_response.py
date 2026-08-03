from __future__ import annotations

import json

from sim2claw.observable_registration_reject_only_validation_camera_workcell_response import (
    DEFAULT_CONTRACT,
)


def test_or87_contract_freezes_three_validation_episodes_and_328_frames() -> None:
    contract = json.loads(DEFAULT_CONTRACT.read_text())
    episodes = contract["validation_episodes"]
    assert len(episodes) == 3
    assert all(row["split_role"] == "validation" for row in episodes)
    assert len({row["recording_id"] for row in episodes}) == 3
    assert contract["gates"]["expected_total_frame_count"] == 328


def test_or87_is_reject_only_and_keeps_evaluator_heldout_closed() -> None:
    contract = json.loads(DEFAULT_CONTRACT.read_text())
    assert contract["frozen_candidate"]["refit_or_selection_allowed"] is False
    assert contract["frozen_candidate"]["uniform_camera_response"] == {
        "gain": 0.55,
        "bias": 48.0,
        "formula": "clip(round(gain_times_renderer_bgr_plus_bias),0,255)",
    }
    boundary = contract["resource_boundary"]
    assert boundary["fits_or_candidate_selections_allowed"] == 0
    assert boundary["development_reads_allowed"] == 0
    assert boundary["evaluator_heldout_reads_allowed"] == 0

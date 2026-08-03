from __future__ import annotations

import json
from pathlib import Path

from sim2claw.observable_registration_frozen_camera_development_residual_attribution import (
    select_mechanism,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/evaluations/observable_registration_frozen_camera_development_residual_attribution_v1.json"


def test_renderer_structure_rule_precedes_average_pixel_response() -> None:
    assert select_mechanism(
        motion_passes=True,
        edge_passes=False,
        static_final_edge_passes=False,
        edge_gap=0.11,
        mean_gap=0.02,
        phase_spread=0.02,
        episode_spread=0.002,
    ) == "renderer_structure"
    assert select_mechanism(
        motion_passes=True,
        edge_passes=True,
        static_final_edge_passes=True,
        edge_gap=0.0,
        mean_gap=0.02,
        phase_spread=0.02,
        episode_spread=0.002,
    ) == "appearance"


def test_contract_is_receipt_only_and_other_splits_closed() -> None:
    contract = json.loads(CONTRACT.read_text())
    boundary = contract["resource_boundary"]
    assert boundary["receipt_reads_allowed"] == 3
    assert boundary["physical_video_decodes_allowed"] == 0
    assert boundary["renderer_runs_allowed"] == 0
    assert boundary["candidate_outputs_allowed"] == 0
    assert boundary["parameter_fits_allowed"] == 0
    assert boundary["validation_reads_allowed"] == 0
    assert boundary["evaluator_heldout_reads_allowed"] == 0
    assert contract["decision_rule"]["priority_order"] == ["renderer_structure", "timing", "appearance"]

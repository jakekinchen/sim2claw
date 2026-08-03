from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/evaluations/observable_registration_board_anchored_scene_composition_residual_attribution_v1.json"


def test_contract_freezes_complementary_regions_and_decision_rule() -> None:
    contract = json.loads(CONTRACT.read_text())
    assert contract["regions"]["board_plus_margin"]["dilation_kernel_px"] == 15
    assert contract["regions"]["outside_board"]["definition"] == "pixelwise_complement_of_board_plus_margin"
    rule = contract["decision_rule"]["select_board_to_robot_world_registration_if"]
    assert rule["or82_minus_or81_board_edge_f1_positive_every_episode"] is True
    assert rule["or82_minus_or81_outside_board_edge_f1_negative_every_episode"] is True


def test_contract_is_evaluator_only_without_split_expansion() -> None:
    contract = json.loads(CONTRACT.read_text())
    boundary = contract["resource_boundary"]
    assert boundary["existing_candidate_image_reads_allowed"] == 8
    assert boundary["new_candidate_images_allowed"] == 0
    assert boundary["renders_allowed"] == 0
    assert boundary["parameter_fits_allowed"] == 0
    assert boundary["simulator_replays_allowed"] == 0
    assert boundary["validation_reads_allowed"] == 0
    assert boundary["evaluator_heldout_reads_allowed"] == 0

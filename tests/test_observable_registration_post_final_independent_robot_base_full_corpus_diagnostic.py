from __future__ import annotations

from sim2claw.observable_registration_post_final_independent_robot_base_full_corpus_diagnostic import (
    load_post_final_independent_robot_base_full_corpus_diagnostic_contract,
)


def test_or95_contract_freezes_full_corpus_and_candidate() -> None:
    contract = load_post_final_independent_robot_base_full_corpus_diagnostic_contract()

    assert contract["gates"]["expected_episode_count"] == 11
    assert contract["gates"]["expected_total_frame_count"] == 1210
    assert contract["frozen_candidate"]["refit_selection_threshold_change_or_retry_allowed"] is False
    assert contract["resource_boundary"]["fits_or_candidate_selections_allowed"] == 0
    assert contract["resource_boundary"]["retries_allowed"] == 0


def test_or95_same_video_gate_is_region_specific_and_claim_safe() -> None:
    contract = load_post_final_independent_robot_base_full_corpus_diagnostic_contract()
    acceptance = contract["same_video_acceptance"]

    assert acceptance["minimum_pooled_mean_outside_board_edge_f1"] == 0.60
    assert acceptance["minimum_each_episode_mean_outside_board_edge_f1"] == 0.50
    assert acceptance["minimum_pooled_mean_board_plus_margin_edge_f1"] == 0.60
    assert contract["claim_limits"]["untouched_cohort_remaining"] is False
    assert contract["claim_limits"]["physics_fidelity"] is False

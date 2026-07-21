from __future__ import annotations

import pytest

from sim2claw.pawn_bg_grasp_coordinate_descent import (
    _rank,
    _run_length_update,
    _summarize_retention_trace,
    load_grasp_coordinate_contract,
)


def test_grasp_coordinate_contract_is_bounded_action_frozen_and_non_authoritative() -> None:
    contract = load_grasp_coordinate_contract()
    assert len(contract["coordinates"]) == 14
    assert len(contract["episode_roles"]["adaptive_sentinel_recording_ids"]) == 3
    assert len(contract["episode_roles"]["campaign_held_evaluation_recording_ids"]) == 8
    assert all(contract["action_invariance"].values())
    assert not any(contract["authority"].values())
    assert contract["acceptance"]["minimum_all_episode_lift_and_transport"] == 6


def test_dense_run_length_and_lexicographic_rank_prioritize_consequence() -> None:
    current = maximum = 0
    for active in (False, True, True, False, True):
        current, maximum = _run_length_update(active, current, maximum)
    assert current == 1
    assert maximum == 2

    base = {
        "strict_successes": 0,
        "lift_and_transport": 1,
        "lifted": 3,
        "bilateral_lift_retention": 3,
        "mean_transport_progress_after_lift": 0.5,
        "mean_maximum_piece_rise_m": 0.04,
        "mean_final_target_distance_m": 0.02,
        "mean_post_grasp_slip_m": 0.01,
    }
    farther_but_successful = {
        **base,
        "strict_successes": 1,
        "mean_final_target_distance_m": 0.2,
    }
    assert _rank(farther_but_successful) > _rank(base)


def test_retention_trace_summary_orders_contact_loss_before_drop() -> None:
    trace = [
        {
            "episode_time_s": 1.0,
            "qualified_bilateral_contact": True,
            "bilateral_contact": True,
            "piece_rise_m": 0.021,
            "total_normal_force_n": 2.5,
        },
        {
            "episode_time_s": 1.1,
            "qualified_bilateral_contact": True,
            "bilateral_contact": True,
            "piece_rise_m": 0.024,
            "total_normal_force_n": 1.5,
        },
        {
            "episode_time_s": 1.12,
            "qualified_bilateral_contact": False,
            "bilateral_contact": False,
            "piece_rise_m": 0.023,
            "total_normal_force_n": 0.0,
        },
        {
            "episode_time_s": 1.3,
            "qualified_bilateral_contact": False,
            "bilateral_contact": False,
            "piece_rise_m": 0.019,
            "total_normal_force_n": 0.0,
        },
    ]

    summary = _summarize_retention_trace(trace, lift_threshold_m=0.02)

    assert summary["first_qualified_lift"]["episode_time_s"] == 1.0
    assert summary["pre_qualified_contact_loss"]["total_normal_force_n"] == 1.5
    assert (
        summary["first_qualified_contact_loss_after_lift"]["episode_time_s"]
        == 1.12
    )
    assert summary["qualified_lift_to_qualified_loss_seconds"] == pytest.approx(
        0.12
    )
    assert summary["qualified_loss_to_drop_seconds"] == pytest.approx(0.18)


def test_retention_trace_summary_handles_never_lifted_episode() -> None:
    trace = [
        {
            "episode_time_s": 0.0,
            "qualified_bilateral_contact": False,
            "bilateral_contact": False,
            "piece_rise_m": 0.0,
        }
    ]

    summary = _summarize_retention_trace(trace, lift_threshold_m=0.02)

    assert summary["first_qualified_lift"] is None
    assert summary["first_qualified_contact_loss_after_lift"] is None
    assert summary["first_drop_below_lift_threshold_after_lift"] is None

from __future__ import annotations

import numpy as np

from sim2claw.observable_c922_retained_cross_pose_corroboration import (
    aggregate_cross_episode,
    deterministic_sample_indices,
    load_cross_pose_contract,
)


def test_live_contract_preserves_cross_workspace_proof_ceiling() -> None:
    contract = load_cross_pose_contract()
    selection = contract["historical_episode_selection"]
    identity = contract["camera_identity_contract"]
    assert len(selection["included_episode_ids"]) == 14
    assert len(selection["preserved_historical_held_out_episode_ids"]) == 3
    assert selection["held_out_pixels_may_be_opened"] is False
    assert selection["task_outcomes_may_be_used"] is False
    assert identity["historical_workspace"] == "hackathon_era_workspace"
    assert identity["current_or10_workspace"] == "post_hackathon_home_workspace"
    assert identity["workspace_and_mount_match"] is False
    assert identity["camera_angle_match"] is False
    assert identity["same_physical_device_claimed"] is False
    assert not any(contract["proof_boundaries"].values())
    assert not any(contract["authority"].values())


def test_deterministic_samples_are_unique_and_pre_action() -> None:
    first_times, first_indices = deterministic_sample_indices(
        fps=30.0,
        action_start_seconds=7.6,
        start_seconds=1.0,
        count=12,
    )
    second_times, second_indices = deterministic_sample_indices(
        fps=30.0,
        action_start_seconds=7.6,
        start_seconds=1.0,
        count=12,
    )
    assert np.array_equal(first_times, second_times)
    assert np.array_equal(first_indices, second_indices)
    assert len(np.unique(first_indices)) == 12
    assert np.all(first_indices / 30.0 < 7.6)


def test_cross_episode_aggregation_is_bounded_and_deterministic() -> None:
    extraction = {"interior_indices": [[1, 1], [2, 1]]}
    episode_results = {
        "a": {
            (1, 1): {"accepted": True, "image_point_px": [100.0, 100.0]},
            (2, 1): {"accepted": True, "image_point_px": [200.0, 200.0]},
        },
        "b": {
            (1, 1): {"accepted": True, "image_point_px": [100.2, 99.9]},
            (2, 1): {"accepted": True, "image_point_px": [205.0, 200.0]},
        },
        "c": {
            (1, 1): {"accepted": True, "image_point_px": [99.9, 100.1]},
            (2, 1): {"accepted": True, "image_point_px": [195.0, 200.0]},
        },
    }
    first = aggregate_cross_episode(
        episode_results,
        extraction=extraction,
        minimum_support=3,
        maximum_dispersion_px=0.75,
    )
    second = aggregate_cross_episode(
        episode_results,
        extraction=extraction,
        minimum_support=3,
        maximum_dispersion_px=0.75,
    )
    assert first == second
    assert first[(1, 1)]["accepted"] is True
    assert first[(2, 1)]["accepted"] is False

from __future__ import annotations

import numpy as np

from sim2claw.observable_physical_episode import (
    admitted_callback_frames,
    bidirectional_point_tracks,
    load_observation_contract,
    load_schedule_contract,
    nearest_frame_binding,
)


def test_live_schedule_contract_is_telemetry_only_and_fail_closed() -> None:
    contract = load_schedule_contract()
    indices = [
        value
        for window in contract["telemetry_only_windows"]
        for value in window["sample_indices"]
    ]
    assert indices == sorted(set(indices))
    assert len(indices) == 49
    assert contract["experiment_id"] == "observable-physical-episode-schedule-v2"
    assert (
        contract["expected"]["maximum_c922_association_error_ms"] == 35.0
    )
    assert contract["successor_lineage"]["bound_derivation"][
        "uses_visual_outcome"
    ] is False
    assert contract["annotation_policy"][
        "schedule_may_change_after_visual_open"
    ] is False
    assert contract["annotation_policy"]["missing_depth_is_unknown"] is True
    assert not any(contract["proof_boundaries"].values())
    assert not any(contract["authority"].values())


def test_callback_admission_and_nearest_tie_break_are_deterministic() -> None:
    rows = [
        {
            "role": "c922",
            "appended_to_writer": False,
            "warmup_excluded": True,
            "sequence": 1,
            "host_continuous_ns": 50,
            "pts_seconds": 0.0,
        },
        {
            "role": "c922",
            "appended_to_writer": True,
            "warmup_excluded": False,
            "sequence": 2,
            "host_continuous_ns": 100,
            "pts_seconds": 1.0,
        },
        {
            "role": "d405",
            "appended_to_writer": True,
            "warmup_excluded": False,
            "sequence": 8,
            "host_continuous_ns": 150,
            "pts_seconds": 1.5,
        },
        {
            "role": "c922",
            "appended_to_writer": True,
            "warmup_excluded": False,
            "sequence": 3,
            "host_continuous_ns": 200,
            "pts_seconds": 2.0,
        },
    ]
    frames = admitted_callback_frames(rows, role="c922")
    assert [row["frame_index"] for row in frames] == [0, 1]
    assert [row["sequence"] for row in frames] == [2, 3]
    first = nearest_frame_binding(
        frames, sample_host_continuous_ns=150
    )
    second = nearest_frame_binding(
        frames, sample_host_continuous_ns=151
    )
    assert first["frame_index"] == 0
    assert second["frame_index"] == 1
    assert first["association_error_ms"] == 0.00005


def test_live_observation_contract_freezes_two_pass_limits() -> None:
    contract = load_observation_contract()
    assert contract["two_pass_visual_events"]["pass_a"] == contract[
        "two_pass_visual_events"
    ]["pass_b"]
    assert contract["two_pass_visual_events"][
        "same_system_two_pass_not_independent_humans"
    ] is True
    assert contract["tracking"]["failed_tracks_abstain"] is True
    assert contract["tracking"]["maximum_jaw_tip_pass_disagreement_px"] == 8.0
    assert not any(contract["proof_boundaries"].values())
    assert not any(contract["authority"].values())


def test_bidirectional_point_tracks_are_exact_on_static_synthetic_frames() -> None:
    frames = [
        np.zeros((32, 32), dtype=np.uint8)
        for _ in range(3)
    ]
    for frame in frames:
        frame[12:18, 12:18] = 255
    tracking = {
        "frame_range_inclusive": [0, 2],
        "labels": ["fixed_jaw_tip"],
        "pass_a": {"anchor_points_xy": [[14.0, 14.0]]},
        "pass_b": {"anchor_points_xy": [[14.0, 14.0]]},
        "opencv_parameters": {
            "window_size_px": [15, 15],
            "maximum_pyramid_level": 2,
            "maximum_iterations": 20,
            "epsilon": 0.001,
            "minimum_eigenvalue_threshold": 0.00001,
        },
        "maximum_jaw_tip_pass_disagreement_px": 1.0,
        "maximum_pawn_crown_pass_disagreement_px": 1.0,
    }
    rows = bidirectional_point_tracks(frames, tracking)
    assert list(rows) == [0, 1, 2]
    assert all(row["fixed_jaw_tip"]["accepted"] for row in rows.values())

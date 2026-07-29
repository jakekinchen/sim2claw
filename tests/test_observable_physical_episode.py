from __future__ import annotations

from sim2claw.observable_physical_episode import (
    admitted_callback_frames,
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

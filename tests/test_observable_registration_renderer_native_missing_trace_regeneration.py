from __future__ import annotations

from sim2claw.observable_registration_renderer_native_missing_trace_regeneration import (
    build_missing_trace_regeneration_plan,
    load_renderer_native_missing_trace_regeneration_contract,
)


def test_contract_freezes_exact_action_no_pixel_replay_boundary() -> None:
    contract = load_renderer_native_missing_trace_regeneration_contract()

    assert len(contract["episodes"]) == 4
    assert contract["shared_parameters"]["candidate_selection_allowed"] is False
    assert contract["shared_parameters"][
        "episode_specific_override_allowed"
    ] is False
    assert contract["physical_access"]["physical_video_byte_read_allowed"] is False
    assert contract["physical_access"]["physical_video_decode_allowed"] is False
    assert contract["execution"]["simulator_replays_allowed"] == 4
    assert contract["execution"]["renderer_runs_allowed"] == 0
    assert not any(contract["claim_limits"].values())
    assert not any(contract["authority"].values())


def test_plan_selects_only_or68_missing_traces_without_video_paths() -> None:
    plan = build_missing_trace_regeneration_plan()

    assert plan["parameter_digest"] == (
        "689cc4e245b3b7d500f9ea5ecb16003599cbcc0de9f0ca2a3d30b3f7b60389f7"
    )
    assert [row["recording_id"] for row in plan["episodes"]] == [
        "20260719T032315Z-d3c3cf0b",
        "20260719T030059Z-a26f8400",
        "20260719T030206Z-af661460",
        "20260719T031813Z-b147b429",
    ]
    assert [row["split_role"] for row in plan["episodes"]] == [
        "development",
        "development",
        "validation",
        "evaluator_heldout",
    ]
    assert plan["physical_video_paths_or_bytes_read"] == 0
    assert all("physical_video" not in row for row in plan["episodes"])

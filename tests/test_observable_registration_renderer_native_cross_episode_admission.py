from __future__ import annotations

from sim2claw.observable_registration_renderer_native_cross_episode_admission import (
    load_renderer_native_cross_episode_admission_contract,
    run_renderer_native_cross_episode_admission_once,
)


def test_contract_freezes_renderer_native_anti_leakage_boundary() -> None:
    contract = load_renderer_native_cross_episode_admission_contract()

    assert contract["split"]["expected_counts"] == {
        "development": 4,
        "validation": 3,
        "evaluator_heldout": 4,
    }
    assert contract["split"]["historical_outcome_rank_may_assign_roles"] is False
    assert contract["candidate_provenance"]["required_pixel_source"] == (
        "declared_3d_renderer_only"
    )
    assert contract["candidate_provenance"]["screen_space_geometry_allowed"] is False
    assert contract["physical_access"]["video_decode_allowed"] is False
    assert contract["execution"]["physical_frames_decoded_allowed"] == 0
    assert not any(contract["claim_limits"].values())
    assert not any(contract["authority"].values())


def test_admission_hash_splits_all_episodes_without_decoding_video(tmp_path) -> None:
    output = tmp_path / "or68"
    receipt = run_renderer_native_cross_episode_admission_once(
        output_directory=output
    )

    assert receipt["status"] == (
        "PASS_SPLIT_FROZEN_TRACE_REGENERATION_REQUIRED_RENDERER_NOT_READY"
    )
    assert all(receipt["gates"].values())
    assert receipt["result"]["episode_count"] == 11
    assert receipt["result"]["role_counts"] == {
        "development": 4,
        "validation": 3,
        "evaluator_heldout": 4,
    }
    assert receipt["result"]["published_shared_scene_state_trace_count"] == 7
    assert receipt["result"][
        "action_identical_trace_regeneration_required_count"
    ] == 4
    assert receipt["result"]["renderer_runtime_ready"] is False
    assert receipt["execution"] == {
        "physical_frames_decoded": 0,
        "simulator_replays": 0,
        "renderer_runs": 0,
        "candidate_videos": 0,
        "parameter_fits": 0,
        "hardware_actions": 0,
        "non_json_outputs": 0,
    }

    inventory = __import__("json").loads(
        (output / "pairing_inventory.json").read_text()
    )
    heldout = [
        row["recording_id"]
        for row in inventory["pairs"]
        if row["split_role"] == "evaluator_heldout"
    ]
    assert heldout == [
        "20260719T031813Z-b147b429",
        "20260719T032440Z-f728a18c",
        "20260719T031324Z-bf91502b",
        "20260719T031715Z-61ebb199",
    ]
    assert all(
        row["physical_video"]["access"] == "byte_hash_only_not_decoded"
        for row in inventory["pairs"]
    )
    assert inventory["physical_access"]["videos_decoded"] == 0

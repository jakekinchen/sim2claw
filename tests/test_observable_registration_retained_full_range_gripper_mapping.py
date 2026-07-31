from pathlib import Path

from sim2claw.observable_registration_retained_full_range_gripper_mapping import (
    CONTRACT_PATH,
    extract_full_range_gripper_observations,
    load_retained_full_range_gripper_mapping_contract,
    run_retained_full_range_gripper_mapping_once,
)


def test_contract_is_retained_cross_episode_and_replay_closed() -> None:
    contract = load_retained_full_range_gripper_mapping_contract()
    assert contract["source_audit"]["raw_row_count"] == 2401
    assert contract["source_audit"]["gripper_cycle_sample_range_inclusive"] == [
        430,
        546,
    ]
    assert contract["estimand"]["metric_aperture_claim_allowed"] is False
    assert contract["partition"]["validation_refit_allowed"] is False
    assert contract["replay"]["dynamic_replay_allowed"] is False
    assert not any(contract["authority"].values())


def test_full_range_visual_audit_is_deterministic_and_insufficient() -> None:
    contract = load_retained_full_range_gripper_mapping_contract()
    first, first_abstained = extract_full_range_gripper_observations(contract)
    second, second_abstained = extract_full_range_gripper_observations(contract)
    assert first == second
    assert first_abstained == second_abstained
    assert [row["frame_index"] for row in first] == [150, 156, 157, 170]
    assert {row["direction"] for row in first} == {"opening", "closing"}
    assert len(first_abstained) == 37


def test_live_full_range_clip_fails_closed_without_replay(
    tmp_path: Path,
) -> None:
    receipt = run_retained_full_range_gripper_mapping_once(
        CONTRACT_PATH,
        tmp_path / "or41",
    )
    assert (
        receipt["status"]
        == "TERMINAL_NEGATIVE_RETAINED_CROSS_EPISODE_DIRECTIONAL_PLAY"
    )
    assert receipt["mapping_gate_passed"] is False
    assert receipt["dynamic_replays_run"] == 0
    assert receipt["candidate"]["play_half_width_raw_degrees"] == 0.0
    assert receipt["observations"]["accepted_frame_count"] == 4
    assert receipt["terminal_task_outcome_used_for_fit_or_selection"] is False

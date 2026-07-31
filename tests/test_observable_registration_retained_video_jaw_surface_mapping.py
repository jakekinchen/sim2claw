from pathlib import Path

import numpy as np

from sim2claw.observable_registration_retained_video_jaw_surface_mapping import (
    CONTRACT_PATH,
    directional_play,
    extract_preterminal_observations,
    load_retained_video_jaw_surface_mapping_contract,
    run_retained_video_jaw_surface_mapping_once,
)


def test_contract_is_scale_free_fail_closed_retained_video() -> None:
    contract = load_retained_video_jaw_surface_mapping_contract()
    assert contract["estimand"]["metric_aperture_claim_allowed"] is False
    assert contract["estimand"]["camera_calibration_claim_allowed"] is False
    assert contract["partition"]["mapping_sample_range_inclusive"] == [110, 224]
    assert contract["partition"]["contact_and_terminal_samples_available_to_fit_or_selection"] is False
    assert contract["replay"]["maximum_dynamic_replays"] == 1
    assert contract["replay"]["permitted_only_if_mapping_gate_passes"] is True
    assert contract["replay"]["object_pose_injection_allowed"] is False


def test_directional_play_is_causal_and_bounded() -> None:
    raw = np.asarray([0.0, 1.0, 2.0, 1.5, 0.5, -0.5], dtype=np.float64)
    beta = 0.25
    mapped = directional_play(raw, beta)
    assert np.all(np.abs(mapped - raw) <= beta + 1e-12)
    assert mapped[0] == raw[0]
    for prefix in range(1, len(raw) + 1):
        assert np.array_equal(
            directional_play(raw[:prefix], beta),
            mapped[:prefix],
        )
    assert np.array_equal(directional_play(raw, 0.0), raw)


def test_retained_extraction_is_deterministic_and_preterminal() -> None:
    contract = load_retained_video_jaw_surface_mapping_contract()
    first, first_abstained = extract_preterminal_observations(contract)
    second, second_abstained = extract_preterminal_observations(contract)
    assert first == second
    assert first_abstained == second_abstained == [60, 61, 62, 63, 89]
    assert len(first) == 25
    assert {row["split"] for row in first} == {"fit", "validation"}
    assert min(row["sample_index"] for row in first) >= 110
    assert max(row["sample_index"] for row in first) <= 224


def test_live_retained_clip_fails_mapping_before_any_replay(
    tmp_path: Path,
) -> None:
    receipt = run_retained_video_jaw_surface_mapping_once(
        CONTRACT_PATH,
        tmp_path / "or40",
    )
    assert receipt["status"] == "DIRECTIONAL_PLAY_UNIDENTIFIABLE_NO_REPLAY"
    assert receipt["mapping_gate_passed"] is False
    assert receipt["dynamic_replays_run"] == 0
    assert receipt["dynamic_replay_permitted"] is False
    assert receipt["raw_measured_row_count"] == 531
    assert receipt["raw_measured_values_order_or_timestamps_changed"] is False
    assert receipt["contact_or_terminal_samples_used_for_fit_or_selection"] is False
    gates = receipt["mapping_gate_report"]
    assert gates["minimum_extracted_frames"] is True
    assert gates["minimum_validation_closing_frames"] is False
    assert gates["minimum_validation_improvement_over_zero_play"] is False

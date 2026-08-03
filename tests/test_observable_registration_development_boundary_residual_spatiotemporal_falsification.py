from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from sim2claw.observable_registration_development_boundary_residual_spatiotemporal_falsification import (
    DEFAULT_CONTRACT,
    _association,
    _boundary_components,
    _nearest_sample_signals,
    _null_shifts,
    evaluate_once,
    load_boundary_residual_falsification_contract,
)


def test_contract_rejects_semantic_intervention_and_closes_other_pixels() -> None:
    contract = load_boundary_residual_falsification_contract()
    assert contract["status"] == "owner_admitted_frozen_not_executed"
    assert contract["semantic_correction"]["or133a_label_rejected"] == "operator_or_cable_like"
    assert contract["semantic_correction"]["measured_class"] == "boundary_connected_nonshadow_residual"
    assert contract["semantic_correction"]["may_authorize_intervention"] is False
    assert contract["resource_boundary"]["candidate_intervention_renders_allowed"] == 0
    assert contract["resource_boundary"]["renderer_or_intervention_dof_allowed"] == 0
    assert contract["resource_boundary"]["positions_8_through_11_pixel_reads_allowed"] == 0
    assert contract["resource_boundary"]["sibling_pixel_reads_allowed"] == 0
    assert contract["claim_limits"]["operator_or_cable_identity"] is False
    assert contract["claim_limits"]["regional_target_progress"] is False
    assert not any(contract["authority"].values())


def test_frozen_null_shifts_are_unique_and_at_least_five_seconds_away() -> None:
    for frame_count in (94, 101, 107, 108, 112, 121):
        shifts = _null_shifts(frame_count, 40, 25)
        assert len(shifts) == len(set(shifts)) == 40
        assert all(min(shift, frame_count - shift) >= 25 for shift in shifts)


def test_association_detects_a_strong_nonperiodic_coupling_beyond_null() -> None:
    rng = np.random.default_rng(133)
    signal = rng.normal(size=121)
    outcome = np.roll(signal, 2) + rng.normal(scale=0.02, size=121)
    contract = load_boundary_residual_falsification_contract()["association_test"]
    result = _association(outcome.tolist(), signal.tolist(), contract)
    assert result["qualifies"] is True
    assert result["best_lag_frames"] == 2
    assert result["best_absolute_correlation"] > 0.99
    assert len(result["null_maximum_correlations"]) == 40


def test_nearest_sample_signals_zero_outside_recorded_window() -> None:
    samples = [
        {
            "overhead_video_time_seconds": 5.0,
            "follower_actual_velocity_degrees_s": [3.0, 4.0],
            "leader_relative_delta": [0.0, 2.0],
        },
        {
            "overhead_video_time_seconds": 6.0,
            "follower_actual_velocity_degrees_s": [0.0, 6.0],
            "leader_relative_delta": [3.0, 4.0],
        },
    ]
    follower, leader = _nearest_sample_signals(samples, [4.0, 5.1, 5.9, 7.0])
    assert follower == [0.0, 5.0, 6.0, 0.0]
    assert leader == [0.0, 2.0, 5.0, 0.0]


def test_boundary_components_name_sides_track_overlap_and_conserve_mass() -> None:
    staged = []
    for offset in (0, 1, 2):
        source = np.zeros((12, 16), bool)
        source[3 + offset : 7 + offset, 0:3] = True
        staged.append(
            {
                "boundary_source": source,
                "physical_gray": np.full((12, 16), 50, np.uint8),
                "left_distance": np.full((12, 16), 4.0),
                "right_distance": np.full((12, 16), 20.0),
                "arm_mask": np.zeros((12, 16), bool),
            }
        )
    contract = load_boundary_residual_falsification_contract()["component_tracking"]
    frames, mass, tracks = _boundary_components(
        staged, 100.0, np.asarray([1.0, 0.0]), contract
    )
    assert mass == [12, 12, 12]
    assert [frame[0]["border_sides"] for frame in frames] == [["left"], ["left"], ["left"]]
    assert len(tracks) == 1
    assert next(iter(tracks.values())) == {"frame_count": 3, "mass_pixels": 36}
    assert sum(sum(component["size_pixels"] for component in frame) for frame in frames) == sum(mass)


def test_evaluator_refuses_existing_receipt_before_any_pixel_read(tmp_path: Path) -> None:
    (tmp_path / "receipt.json").write_text("{}")
    with pytest.raises(ValueError, match="one-run receipt already exists"):
        evaluate_once(DEFAULT_CONTRACT, tmp_path)

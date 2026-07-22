from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pytest

from sim2claw.sail.contracts import phase_timing_error, verify_contract
from sim2claw.sail.phases import (
    PhaseAlignmentError,
    detect_events,
    finite_difference,
    phase_intervals,
    phase_labels,
    resample_masked_channel,
)
from sim2claw.sail.residuals import (
    ResidualCompilationError,
    summarize_samples,
    verify_residual_receipt,
    whole_episode_bootstrap,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
RESIDUAL_ROOT = REPO_ROOT / "outputs" / "sail" / "retired-bg-v1" / "residuals"


def _phase_settings() -> dict:
    return {
        "first_open_search_fraction": 0.5,
        "destination_open_search_start_fraction": 0.5,
        "transition_fraction_of_open_to_valley_range": 0.15,
        "minimum_gripper_amplitude": 0.01,
        "phase_order": [
            "approach_open",
            "closure_transition",
            "closed_transport_candidate",
            "release_transition",
            "retraction_open",
        ],
        "event_order": [
            "open_reference_peak",
            "closure_onset",
            "near_closed_crossing",
            "closed_valley",
            "release_onset",
            "destination_open_peak",
        ],
    }


def _signal() -> list[float]:
    return [1.0, 1.0, 0.9, 0.7, 0.4, 0.1, 0.0, 0.15, 0.4, 0.7, 1.0, 1.0]


def test_observable_phase_order_is_stable_and_covers_every_sample() -> None:
    settings = _phase_settings()
    events = detect_events(_signal(), settings)
    assert list(events) == settings["event_order"]
    assert list(events.values()) == sorted(events.values())
    intervals = phase_intervals(len(_signal()), events, settings["phase_order"])
    labels = phase_labels(len(_signal()), intervals)
    assert [row["phase"] for row in intervals] == settings["phase_order"]
    assert sum(row["sample_count"] for row in intervals) == len(_signal())
    assert len(labels) == len(_signal())
    assert set(labels) == set(settings["phase_order"])


def test_gold_04_shifted_trajectory_cannot_hide_behind_shared_minimum() -> None:
    reference = _signal()
    shifted = [reference[0], *reference[:-1]]
    assert min(reference) == min(shifted)
    assert phase_timing_error(reference, shifted) > 0.0
    settings = _phase_settings()
    reference_events = detect_events(reference, settings)
    shifted_events = detect_events(shifted, settings)
    times = np.arange(len(reference), dtype=np.float64) * 0.05
    residuals = {
        name: float(times[shifted_events[name]] - times[reference_events[name]])
        for name in settings["event_order"]
    }
    assert residuals["near_closed_crossing"] != 0.0
    assert residuals["release_onset"] != 0.0


def test_explicit_linear_resampling_never_fills_unavailable_gap() -> None:
    values, available, provenance = resample_masked_channel(
        [0.0, 1.0, 2.0],
        [0.0, None, 2.0],
        [True, False, True],
        [0.0, 0.5, 1.0, 1.5, 2.0, 3.0],
        method="linear",
    )
    assert values == [0.0, None, None, None, 2.0, None]
    assert available == [True, False, False, False, True, False]
    assert provenance == {
        "method": "linear",
        "source_time_count": 3,
        "target_time_count": 6,
        "gap_filling": False,
        "extrapolation": False,
    }
    with pytest.raises(PhaseAlignmentError, match="unsupported interpolation"):
        resample_masked_channel([0.0, 1.0], [0.0, 1.0], [True, True], [0.5], method="cubic")


def test_velocity_residual_uses_strict_source_time_base() -> None:
    values = [[0.0, 0.0], [0.5, 1.0], [1.5, 3.0]]
    derivative = finite_difference(values, [0.0, 0.5, 1.5])
    assert derivative.shape == (3, 2)
    assert np.allclose(derivative, np.asarray([[1.0, 2.0]] * 3))
    with pytest.raises(PhaseAlignmentError, match="strictly increasing"):
        finite_difference(values, [0.0, 0.5, 0.5])


def test_summaries_preserve_missing_masks_units_frames_and_provenance() -> None:
    samples = [
        {
            "episode_id": "episode-a",
            "phase": "approach_open",
            "time_seconds": 0.0,
            "channel": "joint_error",
            "unit": "radian",
            "frame": "robot_joint",
            "provenance": "source-a",
            "available": True,
            "value": 0.1,
        },
        {
            "episode_id": "episode-a",
            "phase": "approach_open",
            "time_seconds": 0.0,
            "channel": "physical_contact_force",
            "unit": "unavailable",
            "frame": None,
            "provenance": "missing-source-channel",
            "available": False,
            "value": None,
        },
    ]
    summaries = summarize_samples(samples)
    missing = next(
        row
        for row in summaries
        if row["phase"] == "all" and row["channel"] == "physical_contact_force"
    )
    assert missing["available_count"] == 0
    assert missing["missing_count"] == 1
    assert missing["rmse"] is None
    observed = next(
        row for row in summaries if row["phase"] == "all" and row["channel"] == "joint_error"
    )
    assert observed["unit"] == "radian"
    assert observed["frame"] == "robot_joint"
    assert observed["rmse"] == pytest.approx(0.1)


def test_whole_episode_bootstrap_is_seeded_and_order_stable() -> None:
    summaries = [
        {
            "episode_id": episode,
            "phase": "all",
            "channel": "joint_error",
            "unit": "radian",
            "rmse": value,
        }
        for episode, value in (("episode-c", 0.3), ("episode-a", 0.1), ("episode-b", 0.2))
    ]
    settings = {"seed": 42, "replicates": 1000, "confidence_level": 0.95}
    first = whole_episode_bootstrap(summaries, settings)
    second = whole_episode_bootstrap(list(reversed(summaries)), settings)
    assert first == second
    estimate = first["estimates"][0]
    assert estimate["episode_count"] == 3
    assert estimate["point_estimate_mean_episode_rmse"] == pytest.approx(0.2)
    assert estimate["interval_lower"] <= 0.2 <= estimate["interval_upper"]


@pytest.mark.skipif(
    not (RESIDUAL_ROOT / "residual_field.json").is_file(),
    reason="owner-local retained residual artifact is unavailable",
)
def test_gold_03_and_gold_04_retained_residual_artifact_verifies() -> None:
    field = verify_contract(json.loads((RESIDUAL_ROOT / "residual_field.json").read_text()))
    assert len(field["evidence_ids"]) == 22
    assert len(field["samples"]) == 213897
    assert len(field["bootstrap"]["estimates"]) == 57
    missing = [
        row
        for row in field["samples"]
        if row["channel"] in {"physical_contact", "physical_contact_force", "pawn_to_target"}
    ]
    assert missing
    assert all(row["available"] is False and row["value"] is None for row in missing)
    timing = [
        row
        for row in field["samples"]
        if row["channel"].startswith("selected_event_timing:")
    ]
    assert {row["channel"] for row in timing} == {
        "selected_event_timing:open_reference_peak",
        "selected_event_timing:closure_onset",
        "selected_event_timing:near_closed_crossing",
        "selected_event_timing:closed_valley",
        "selected_event_timing:release_onset",
        "selected_event_timing:destination_open_peak",
    }
    assert any(abs(float(row["value"])) > 0.0 for row in timing)
    receipt = json.loads((RESIDUAL_ROOT / "receipt.json").read_text())
    verify_residual_receipt(receipt, output_root=RESIDUAL_ROOT)


def test_receipt_authority_or_digest_change_fails_closed() -> None:
    if not (RESIDUAL_ROOT / "receipt.json").is_file():
        pytest.skip("owner-local retained residual artifact is unavailable")
    receipt = json.loads((RESIDUAL_ROOT / "receipt.json").read_text())
    changed = copy.deepcopy(receipt)
    changed["authority"]["training_admission"] = True
    with pytest.raises(ResidualCompilationError, match="digest mismatch|widened authority"):
        verify_residual_receipt(changed, output_root=RESIDUAL_ROOT)

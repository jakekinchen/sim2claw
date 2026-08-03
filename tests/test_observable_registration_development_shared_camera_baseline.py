from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from sim2claw.observable_registration_development_shared_camera_baseline import (
    evaluation_times,
    nearest_trace_indices,
    physical_frame_indices,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/evaluations/observable_registration_development_shared_camera_baseline_v1.json"


def test_frozen_timeline_indexing_is_bounded_and_nearest() -> None:
    times = evaluation_times(1.05, 5.0)
    assert np.allclose(times, [0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
    trace_indices = nearest_trace_indices(np.asarray([0.0, 0.3, 0.7, 1.1]), times)
    assert trace_indices.tolist() == [0, 1, 1, 2, 2, 3]
    video_indices = physical_frame_indices(times, frame_count=31, duration_seconds=1.0)
    assert video_indices.tolist() == [0, 6, 12, 18, 24, 30]


def test_contract_is_four_episode_development_only_and_untuned() -> None:
    contract = json.loads(CONTRACT.read_text())
    assert len(contract["episodes"]) == 4
    assert {episode["split_role"] for episode in contract["episodes"]} == {"development"}
    assert contract["timeline"]["time_offset_seconds"] == 0.0
    assert contract["renderer"]["camera_fit_allowed"] is False
    assert contract["renderer"]["appearance_fit_allowed"] is False
    assert contract["resource_boundary"]["validation_reads_allowed"] == 0
    assert contract["resource_boundary"]["evaluator_heldout_reads_allowed"] == 0
    assert contract["resource_boundary"]["parameter_fits_allowed"] == 0
    assert "physical_video_pixels" in contract["prohibited_candidate_inputs"]
    assert "or67_static_vector_candidate_video" in contract["prohibited_candidate_inputs"]

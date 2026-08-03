from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from sim2claw.observable_registration_development_initial_shared_3d_camera_fit import (
    camera_from_vector,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/evaluations/observable_registration_development_initial_shared_3d_camera_fit_v1.json"


def test_spherical_camera_vector_maps_to_declared_distance() -> None:
    vector = np.asarray([0.0, 0.5, 0.8, 0.0, 90.0, 1.2, 60.0])
    camera = camera_from_vector(vector)
    assert np.allclose(camera["target"], [0.0, 0.5, 0.8])
    assert np.allclose(camera["position"], [0.0, 0.5, 2.0])
    assert camera["fov_degrees"] == 60.0


def test_contract_is_static_camera_only_and_split_closed() -> None:
    contract = json.loads(CONTRACT.read_text())
    selection = contract["development_selection"]
    assert selection["episode_count"] == 4
    assert selection["physical_frame_index_each"] == 0
    assert selection["state_trace_frame_index_each"] == 0
    assert contract["camera_family"]["shared_across_all_episodes"] is True
    assert contract["camera_family"]["camera_only"] is True
    assert contract["renderer"]["appearance_fit_allowed"] is False
    assert contract["resource_boundary"]["time_fits_allowed"] == 0
    assert contract["resource_boundary"]["state_or_physics_fits_allowed"] == 0
    assert contract["resource_boundary"]["validation_reads_allowed"] == 0
    assert contract["resource_boundary"]["evaluator_heldout_reads_allowed"] == 0
    assert contract["search"]["maximum_candidate_evaluations"] == 336
    assert "physical_video_pixels" in contract["prohibited_candidate_inputs"]

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from sim2claw.observable_registration_host_native_analytic_3d_renderer_capability import (
    camera_basis,
    project_points,
    quaternion_matrix_wxyz,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/evaluations/observable_registration_host_native_analytic_3d_renderer_capability_v1.json"


def test_projection_math_is_right_handed_and_finite() -> None:
    rotation = quaternion_matrix_wxyz([1.0, 0.0, 0.0, 0.0])
    assert np.allclose(rotation, np.eye(3))
    camera = {
        "position": [0.0, -2.0, 1.0],
        "target": [0.0, 0.0, 1.0],
        "fov_degrees": 40.0,
    }
    position, right, up, forward = camera_basis(camera)
    assert np.all(np.isfinite(np.concatenate([position, right, up, forward])))
    pixels, depth = project_points(
        np.asarray([[0.0, 0.0, 1.0], [0.1, 0.0, 1.0]]),
        camera=camera,
        width=320,
        height=240,
    )
    assert np.all(depth > 0.0)
    assert np.allclose(pixels[0], [160.0, 120.0])
    assert pixels[1, 0] > pixels[0, 0]


def test_contract_is_footage_blind_and_split_closed() -> None:
    contract = json.loads(CONTRACT.read_text())
    assert contract["sources"]["development_state_trace"]["split_role"] == "development"
    assert contract["resource_boundary"]["physical_video_reads_allowed"] == 0
    assert contract["resource_boundary"]["validation_reads_allowed"] == 0
    assert contract["resource_boundary"]["evaluator_heldout_reads_allowed"] == 0
    assert contract["renderer"]["camera_fit_allowed"] is False
    assert contract["renderer"]["mesh_policy"] == "oriented_box_from_declared_manifest_geom_size"
    assert "physical_video_pixels" in contract["prohibited_candidate_inputs"]
    assert "or67_static_vector_candidate_video" in contract["prohibited_candidate_inputs"]

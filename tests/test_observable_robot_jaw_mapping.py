from __future__ import annotations

import numpy as np

from sim2claw.observable_robot_jaw_mapping import (
    apply_planar_rigid,
    fit_planar_rigid_mapping,
    load_mapping_contract,
    project_world_points,
)


def _camera_receipt() -> dict:
    return {
        "physical_pinhole": {
            "focal_px": 600.0,
            "principal_point_px": [320.0, 240.0],
            "task_world_extrinsic": {
                "rotation_world_to_camera": np.eye(3).tolist(),
                "translation_world_to_camera_m": [0.0, 0.0, 1.0],
            },
        }
    }


def test_live_contract_freezes_camera_and_split() -> None:
    contract = load_mapping_contract()
    assert contract["camera_policy"]["refit_allowed"] is False
    assert contract["split"]["fit_count"] == 6
    assert contract["split"]["validation_count"] == 4
    assert contract["split"]["fit_validation_overlap_allowed"] is False
    assert contract["split"]["sealed_d1_to_d2_episode_used"] is False
    assert not any(contract["proof_boundaries"].values())
    assert not any(contract["authority"].values())


def test_planar_rigid_fit_recovers_synthetic_mapping() -> None:
    model = np.asarray(
        [
            [[-0.1, 0.2, 0.2], [-0.06, 0.2, 0.2]],
            [[0.0, 0.25, 0.3], [0.04, 0.25, 0.3]],
            [[0.1, 0.3, 0.25], [0.14, 0.3, 0.25]],
            [[-0.08, 0.35, 0.4], [-0.04, 0.35, 0.4]],
            [[0.04, 0.4, 0.35], [0.08, 0.4, 0.35]],
            [[0.12, 0.45, 0.45], [0.16, 0.45, 0.45]],
        ],
        dtype=np.float64,
    )
    expected = np.asarray([0.07, 0.02, -0.03, 0.04])
    corrected = apply_planar_rigid(model, expected)
    observed, depths = project_world_points(corrected, _camera_receipt())
    assert np.all(depths > 0.0)
    first = fit_planar_rigid_mapping(
        model,
        observed,
        _camera_receipt(),
        lower=np.asarray([-0.3, -0.2, -0.2, -0.1]),
        upper=np.asarray([0.3, 0.2, 0.2, 0.1]),
    )
    second = fit_planar_rigid_mapping(
        model,
        observed,
        _camera_receipt(),
        lower=np.asarray([-0.3, -0.2, -0.2, -0.1]),
        upper=np.asarray([0.3, 0.2, 0.2, 0.1]),
    )
    assert first == second
    actual = np.asarray(
        [
            first["parameters"]["robot_board_yaw_rad"],
            *first["parameters"]["translation_xyz_m"],
        ]
    )
    np.testing.assert_allclose(actual, expected, atol=1e-7)
    assert first["tip_reprojection_rms_px"] < 1e-7
    assert first["solver"]["jacobian_rank"] == 4

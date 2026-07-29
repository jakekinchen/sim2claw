from __future__ import annotations

import numpy as np

from sim2claw.observable_camera_world import (
    decompose_projective_camera,
    fit_square_pixel_camera,
    load_camera_contract,
    project_points,
)


def test_live_contract_preserves_camera_proof_ceiling() -> None:
    contract = load_camera_contract()
    assert contract["validation_policy"]["pristine_heldout_available"] is False
    assert (
        contract["validation_policy"]["exact_intrinsic_calibration_possible"]
        is False
    )
    assert not any(contract["proof_boundaries"].values())
    assert not any(contract["authority"].values())
    assert "task_outcome" in contract["physical_pinhole_family"][
        "forbidden_fit_fields"
    ]


def test_square_pixel_fit_recovers_synthetic_planar_camera() -> None:
    coordinates = np.linspace(0.0, 0.3556, 5)
    board_xy = np.asarray([(x, y) for y in coordinates for x in coordinates])
    object_points = np.column_stack((board_xy, np.zeros(len(board_xy))))
    focal = 610.0
    principal = np.asarray([320.0, 240.0])
    rotation_vector = np.asarray([2.55, 0.18, -0.25])
    translation = np.asarray([-0.17, 0.08, 0.82])
    image, depths = project_points(
        object_points,
        focal,
        principal,
        rotation_vector,
        translation,
    )
    assert np.all(depths > 0.0)

    first = fit_square_pixel_camera(
        board_xy,
        image,
        principal_point_px=principal,
        initial_focal_px=635.0,
        minimum_focal_px=250.0,
        maximum_focal_px=1500.0,
    )
    second = fit_square_pixel_camera(
        board_xy,
        image,
        principal_point_px=principal,
        initial_focal_px=635.0,
        minimum_focal_px=250.0,
        maximum_focal_px=1500.0,
    )
    assert first == second
    np.testing.assert_allclose(first["focal_px"], focal, atol=1e-5)
    assert first["reprojection_rms_px"] < 1e-7
    assert first["solver"]["jacobian_rank"] == 7
    np.testing.assert_allclose(
        np.linalg.det(np.asarray(first["rotation_board_to_camera"])),
        1.0,
        atol=1e-9,
    )


def test_projective_decomposition_exposes_nonphysical_skew_and_aspect() -> None:
    camera = np.asarray(
        [
            [
                -382.81574442575516,
                135.84339079414346,
                -226.79176770591215,
                173.4728410566732,
            ],
            [
                13.015867894170384,
                137.0882645226421,
                -191.08541156257365,
                154.95080480844666,
            ],
            [
                -0.15319230439182546,
                -0.25857534549245886,
                -0.6563980867193302,
                1.0,
            ],
        ]
    )
    result = decompose_projective_camera(camera)
    np.testing.assert_allclose(result["rotation_determinant"], 1.0, atol=1e-9)
    assert result["absolute_skew_px"] > 100.0
    assert result["focal_aspect_ratio"] > 1.5

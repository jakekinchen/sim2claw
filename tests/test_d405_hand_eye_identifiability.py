from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from sim2claw.d405_hand_eye_identifiability import (
    D405HandEyeIdentifiabilityError,
    evaluate_d405_hand_eye_identifiability,
)
from sim2claw.physical_fk_frame import physical_fk_base_from_wrist


def _receipt(
    path: Path,
    joint: list[float],
    normal: list[float],
    offset: float,
    *,
    serial: str = "130322273474",
) -> Path:
    value = {
        "schema_version": "sim2claw.d405_pose_plane_capture_receipt.v1",
        "proof_class": "physical_calibration_setup_pose_plane_observations_only",
        "authority": {
            "camera_to_robot_extrinsic": False,
            "board_origin": False,
        },
        "identity": {
            "database": {
                "sdk_serial_number": serial,
                "asic_serial_number": "133323070214",
            }
        },
        "calibration_lineage": {
            "accepted_capture_receipt_sha256": "a" * 64
        },
        "terminal_hold": {"joint_pose": {"mean_degrees": joint}},
        "observations": [
            {
                "plane": {
                    "normal_camera_unit": normal,
                    "plane_equation": {"offset_m": offset},
                }
            },
            {
                "plane": {
                    "normal_camera_unit": normal,
                    "plane_equation": {"offset_m": offset + 0.0001},
                }
            },
        ],
        "verdict": {
            "passed": True,
            "camera_to_robot_extrinsic_fitted": False,
        },
    }
    path.write_text(json.dumps(value))
    return path


def test_repeated_pose_set_is_insufficient_without_transform(tmp_path: Path) -> None:
    paths = [
        _receipt(
            tmp_path / f"repeat-{index}.json",
            [10, -50, 90, 0, -75, 3],
            [0, 0, 1],
            -0.08,
        )
        for index in range(4)
    ]

    result = evaluate_d405_hand_eye_identifiability(paths)

    assert result["verdict"]["classification"] == "insufficient_observations"
    assert result["diversity_passed"] is False
    assert result["fit"]["attempted"] is False
    assert result["fit"]["wrist_from_d405_depth_optical_rotation_matrix"] is None
    assert result["fit"]["held_out_normal_residual_degrees"] is None


def test_diverse_consistent_set_fits_held_out_hand_eye(tmp_path: Path) -> None:
    if not Path(
        "runs/physical_excitation/20260725-follower-only-v1/"
        "simulation-canary-v1/candidate_manifest.json"
    ).is_file():
        pytest.skip("ignored bound candidate manifest is absent")
    joints = [
        [-12.5, -70, 75, -15, -100, 3],
        [-7.5, -56, 90, 15, -94, 3],
        [-2.5, -42, 105, 9, -88, 3],
        [2.5, -63, 85, 3, -82, 3],
        [7.5, -49, 100, -3, -76, 3],
        [12.5, -70, 80, -9, -70, 3],
        [17.5, -56, 95, -15, -64, 3],
        [22.5, -42, 75, 15, -58, 3],
        [27.5, -63, 90, 9, -52, 3],
        [32.5, -49, 105, 3, -46, 3],
    ]
    transforms = [physical_fk_base_from_wrist(joint) for joint in joints]
    wrist_from_camera = Rotation.from_euler(
        "xyz", [5, -7, 10], degrees=True
    ).as_matrix()
    first_camera_normal = np.asarray([-0.18, 0.17, 0.97])
    first_camera_normal /= np.linalg.norm(first_camera_normal)
    base_normal = (
        transforms[0][:3, :3] @ wrist_from_camera @ first_camera_normal
    )
    base_normal /= np.linalg.norm(base_normal)
    wrist_translation = np.asarray([0.03, -0.02, 0.04])
    base_offset = -0.75
    paths = []
    for index, (joint, transform) in enumerate(zip(joints, transforms, strict=True)):
        normal = (
            wrist_from_camera.T @ transform[:3, :3].T @ base_normal
        )
        offset = base_offset + base_normal @ (
            transform[:3, 3] + transform[:3, :3] @ wrist_translation
        )
        paths.append(
            _receipt(
                tmp_path / f"diverse-{index}.json",
                joint,
                normal.tolist(),
                float(offset),
            )
        )

    result = evaluate_d405_hand_eye_identifiability(paths)

    assert result["diversity_passed"] is True
    assert result["verdict"]["classification"] == (
        "hand_eye_extrinsic_fit_diagnostic_only"
    )
    assert result["rotation_identifiability_established"] is True
    assert result["translation_identifiability_established"] is True
    assert result["screening_rank_is_not_calibration_jacobian_rank"] is True
    assert result["fit"]["attempted"] is True
    assert max(result["fit"]["held_out_normal_residual_degrees"]) < 1e-5
    np.testing.assert_allclose(
        result["fit"]["wrist_from_d405_depth_optical_rotation_matrix"],
        wrist_from_camera,
        atol=1e-6,
    )
    np.testing.assert_allclose(
        result["fit"]["wrist_from_d405_depth_optical_translation_m"],
        wrist_translation,
        atol=1e-6,
    )
    assert result["verdict"]["camera_to_robot_extrinsic_fitted"] is True
    assert result["verdict"]["promotion_authority"] is False


def test_identity_drift_rejects_receipt_set(tmp_path: Path) -> None:
    first = _receipt(tmp_path / "first.json", [0] * 6, [0, 0, 1], -0.08)
    second = _receipt(
        tmp_path / "second.json",
        [1] * 6,
        [0, 0, 1],
        -0.08,
        serial="different",
    )

    with pytest.raises(
        D405HandEyeIdentifiabilityError, match="identity or calibration"
    ):
        evaluate_d405_hand_eye_identifiability([first, second])

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from sim2claw.d405_hand_eye_identifiability import (
    D405HandEyeIdentifiabilityError,
    evaluate_d405_hand_eye_identifiability,
)


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
    assert result["fit"]["wrist_camera_rotation"] is None
    assert result["fit"]["held_out_residuals"] is None


def test_diverse_set_seals_missing_fk_and_camera_frame_contracts(
    tmp_path: Path,
) -> None:
    paths = []
    for index in range(8):
        yaw, pitch = np.radians(index * 8), np.radians((index % 3) * 9)
        normal = [
            float(np.sin(yaw) * np.cos(pitch)),
            float(np.sin(pitch)),
            float(np.cos(yaw) * np.cos(pitch)),
        ]
        joint = [
            10 + index * 3,
            -60 + (index % 3) * 8,
            100 - index * 4,
            -8 + (index % 4) * 5,
            -85 + index * 2,
            3,
        ]
        paths.append(
            _receipt(
                tmp_path / f"diverse-{index}.json",
                joint,
                normal,
                -0.07 - index * 0.003,
            )
        )

    result = evaluate_d405_hand_eye_identifiability(paths)

    assert result["diversity_passed"] is True
    assert result["verdict"]["classification"] == (
        "diversity_passed_kinematic_camera_frame_contract_missing"
    )
    assert result["missing_prerequisites"] == [
        "approved_physical_joint_to_robot_fk_contract",
        "approved_d405_optical_to_wrist_mount_frame_contract",
    ]
    assert result["true_hand_eye_identifiability_established"] is False
    assert result["screening_rank_is_not_calibration_jacobian_rank"] is True
    assert result["fit"]["attempted"] is False
    assert result["verdict"]["camera_to_robot_extrinsic_fitted"] is False


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

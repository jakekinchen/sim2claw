from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from sim2claw.robot_anchored_overlay import (
    calibration_correspondences,
    camera_pose_in_robot_frame,
    fit_board_camera,
)


CONFIG_PATH = Path("configs/experiments/robot_anchored_camera_overlay_v1.json")


class RobotAnchoredOverlayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import json

        cls.contract = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    def test_contract_keeps_historical_and_current_authority_separate(self) -> None:
        self.assertEqual(
            self.contract["physical_source"]["recorded_board_pose_id"],
            "board_robotward_72mm_20260718_v2",
        )
        self.assertEqual(
            self.contract["transfer_preview"]["current_board_pose_id"],
            "board_robotward_100mm_20260718_v3",
        )
        self.assertEqual(
            self.contract["transfer_preview"][
                "historical_total_robotward_displacement_m"
            ],
            0.072,
        )
        self.assertEqual(
            self.contract["transfer_preview"][
                "current_total_robotward_displacement_m"
            ],
            0.100,
        )
        self.assertEqual(
            self.contract["transfer_preview"][
                "expected_increment_from_recording_m"
            ],
            0.028,
        )
        authority = self.contract["authority"]
        self.assertTrue(authority["visual_registration_only"])
        self.assertTrue(
            authority["historical_video_is_not_current_100mm_spatial_evidence"]
        )
        self.assertEqual(authority["training_rows_authorized"], 0)
        self.assertEqual(authority["held_out_rows_used"], 0)
        self.assertFalse(authority["pawn_policy_authority"])

    def test_grid_contract_builds_all_64_correspondences(self) -> None:
        object_points, image_points, evidence = calibration_correspondences(
            self.contract
        )
        self.assertEqual(object_points.shape, (64, 3))
        self.assertEqual(image_points.shape, (64, 2))
        self.assertEqual(len(evidence), 64)
        self.assertTrue(np.all(np.isfinite(object_points)))
        self.assertTrue(np.all(np.isfinite(image_points)))

    def test_board_camera_fit_is_deterministic(self) -> None:
        fit = fit_board_camera(self.contract)
        self.assertEqual(len(fit["correspondence_evidence"]), 64)
        self.assertAlmostEqual(fit["focal_length_px"], 946.572376, places=3)
        self.assertAlmostEqual(
            fit["vertical_fov_degrees"], 28.454647, places=3
        )
        self.assertAlmostEqual(fit["opencv_rms_source_px"], 11.302872, places=3)

    def test_camera_pose_is_stored_in_robot_mount_frame(self) -> None:
        pose = camera_pose_in_robot_frame(
            self.contract, fit_board_camera(self.contract)
        )
        self.assertEqual(pose["robot"], "left")
        self.assertEqual(pose["frame"], "left_robot_mount")
        self.assertEqual(pose["camera_position_robot_m"].shape, (3,))
        self.assertEqual(pose["camera_cv_to_robot_rotation"].shape, (3, 3))
        self.assertTrue(np.all(np.isfinite(pose["camera_position_robot_m"])))
        rotation = pose["camera_cv_to_robot_rotation"]
        np.testing.assert_allclose(rotation.T @ rotation, np.eye(3), atol=1e-8)


if __name__ == "__main__":
    unittest.main()

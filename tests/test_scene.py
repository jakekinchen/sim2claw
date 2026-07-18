from __future__ import annotations

import unittest

import mujoco

from sim2claw.capture import load_capture_config
from sim2claw.scene import (
    CURRENT_TASK_PIECE_LAYOUT,
    STUDIO_CAMERAS,
    TELEOP_PAWN_SOURCE_SQUARES,
    TELEOP_TAN_PAWN_SQUARES,
    build_scene_spec,
    initialize_robot_poses,
    scene_geometry,
    scene_summary,
)


class SceneContractTest(unittest.TestCase):
    def test_scene_summary_separates_measurement_and_estimate(self) -> None:
        summary = scene_summary()
        self.assertEqual(summary["piece_count"], 32)
        self.assertEqual(summary["robots"]["count"], 2)
        self.assertEqual(summary["table"]["measurement_confidence"], "high")
        self.assertEqual(
            summary["board"]["measurement_confidence"],
            "operator_measured_72mm_robotward_displacement_from_photo_registered_pose",
        )
        self.assertEqual(
            summary["board"]["pose_id"],
            "board_robotward_72mm_20260718_v2",
        )
        self.assertEqual(
            summary["board"]["center_in_table_frame_xy_m"],
            [0.04, -0.093],
        )
        self.assertAlmostEqual(
            summary["board"]["robotward_displacement_from_previous_pose_m"],
            0.072,
        )
        self.assertFalse(summary["physical_authority"])

    def test_scene_compiles_and_steps(self) -> None:
        spec = build_scene_spec()
        model = spec.compile()
        data = mujoco.MjData(model)
        initialize_robot_poses(model, data)
        for _ in range(10):
            mujoco.mj_step(model, data)
        self.assertEqual(model.njnt, 44)
        self.assertEqual(model.nu, 12)
        self.assertGreater(model.ngeom, 250)
        self.assertGreaterEqual(
            mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "left_base"), 0
        )
        self.assertGreaterEqual(
            mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "right_base"), 0
        )
        for camera in STUDIO_CAMERAS:
            self.assertGreaterEqual(
                mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, camera), 0
            )

    def test_board_fits_measured_table(self) -> None:
        geometry = scene_geometry(load_capture_config())
        self.assertLess(geometry.board_side, geometry.table_length)
        self.assertLess(geometry.board_side, geometry.table_width)
        self.assertAlmostEqual(geometry.square_size, 0.04445)
        self.assertAlmostEqual(geometry.board_total_side, 0.4064)

    def test_current_task_layout_contains_two_mirrored_sparse_pawn_sides(self) -> None:
        model = build_scene_spec(piece_layout=CURRENT_TASK_PIECE_LAYOUT).compile()
        self.assertEqual(model.njnt, 28)
        for square in TELEOP_PAWN_SOURCE_SQUARES:
            self.assertGreaterEqual(
                mujoco.mj_name2id(
                    model,
                    mujoco.mjtObj.mjOBJ_BODY,
                    f"brown_pawn_{square}",
                ),
                0,
            )
        for square in TELEOP_TAN_PAWN_SQUARES:
            self.assertGreaterEqual(
                mujoco.mj_name2id(
                    model,
                    mujoco.mjtObj.mjOBJ_BODY,
                    f"tan_pawn_{square}",
                ),
                0,
            )
        summary = scene_summary(piece_layout=CURRENT_TASK_PIECE_LAYOUT)
        self.assertEqual(summary["piece_count"], 16)

        pawn_body = mujoco.mj_name2id(
            model,
            mujoco.mjtObj.mjOBJ_BODY,
            "brown_pawn_a2",
        )
        pawn_geom_types = [
            mujoco.mjtGeom(int(model.geom_type[geom_id]))
            for geom_id in range(model.ngeom)
            if int(model.geom_bodyid[geom_id]) == pawn_body
        ]
        self.assertEqual(pawn_geom_types.count(mujoco.mjtGeom.mjGEOM_CYLINDER), 11)
        self.assertEqual(pawn_geom_types.count(mujoco.mjtGeom.mjGEOM_ELLIPSOID), 2)
        self.assertEqual(pawn_geom_types.count(mujoco.mjtGeom.mjGEOM_SPHERE), 1)
        self.assertNotIn(mujoco.mjtGeom.mjGEOM_CAPSULE, pawn_geom_types)

    def test_board_reaching_arm_tracks_board_length_centerline(self) -> None:
        summary = scene_summary()
        mounts = {
            row["name"]: row for row in summary["robots"]["mounts"]
        }
        self.assertLessEqual(
            mounts["left"]["board_centerline_offset_m"],
            summary["board"]["square_m"] * 2,
        )
        self.assertEqual(summary["studio_cameras"], list(STUDIO_CAMERAS))


if __name__ == "__main__":
    unittest.main()

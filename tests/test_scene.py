from __future__ import annotations

import unittest

import mujoco

from sim2claw.capture import load_capture_config
from sim2claw.scene import (
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
            "photo_registered_with_polycam_textured_mesh_size_cross_check",
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

    def test_board_fits_measured_table(self) -> None:
        geometry = scene_geometry(load_capture_config())
        self.assertLess(geometry.board_side, geometry.table_length)
        self.assertLess(geometry.board_side, geometry.table_width)
        self.assertAlmostEqual(geometry.square_size, 0.04445)
        self.assertAlmostEqual(geometry.board_total_side, 0.4064)


if __name__ == "__main__":
    unittest.main()

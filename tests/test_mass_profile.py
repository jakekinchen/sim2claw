from __future__ import annotations

import unittest

import mujoco

from sim2claw.chess_task import ChessRookLiftEnv, load_task_contract
from sim2claw.mass_profile import RIGID_BODY_NAMES, load_so101_mass_profile
from sim2claw.paths import DEFAULT_SO101_MASS_PROFILE
from sim2claw.scene import build_scene_spec, scene_summary


class SO101MassProfileTest(unittest.TestCase):
    def test_profile_totals_and_servo_conflict_are_explicit(self) -> None:
        profile = load_so101_mass_profile()
        self.assertEqual(profile["derived"]["printed_parts_total_g"], 547)
        self.assertEqual(profile["derived"]["servos_total_g"], 330)
        self.assertEqual(profile["derived"]["bare_arm_total_g"], 907)
        self.assertEqual(
            profile["uncertainty"]["component_bounded_left_total_range_g"],
            [977, 1035],
        )
        self.assertEqual(
            profile["uncertainty"]["reported_left_total_range_g"],
            [965, 1047],
        )
        self.assertEqual(profile["derived"]["left_arm_with_payload_total_g"], 1006)
        self.assertEqual(profile["conflicts"][0]["owner_note_value_g"], 28)
        self.assertEqual(profile["conflicts"][0]["selected_value_g"], 55)

    def test_scene_uses_measured_link_masses_and_left_d405_payload(self) -> None:
        profile = load_so101_mass_profile()
        model = build_scene_spec().compile()
        bare_masses = profile["derived"]["rigid_body_masses_g"]
        left_additions = profile["payloads"]["d405_wrist_v1"][
            "rigid_body_additions_g"
        ]

        left_total_kg = 0.0
        right_total_kg = 0.0
        for body_name in RIGID_BODY_NAMES:
            left_id = mujoco.mj_name2id(
                model, mujoco.mjtObj.mjOBJ_BODY, f"left_{body_name}"
            )
            right_id = mujoco.mj_name2id(
                model, mujoco.mjtObj.mjOBJ_BODY, f"right_{body_name}"
            )
            expected_bare_kg = bare_masses[body_name] / 1000.0
            expected_left_kg = (
                bare_masses[body_name] + left_additions.get(body_name, 0)
            ) / 1000.0
            self.assertAlmostEqual(model.body_mass[left_id], expected_left_kg)
            self.assertAlmostEqual(model.body_mass[right_id], expected_bare_kg)
            left_total_kg += model.body_mass[left_id]
            right_total_kg += model.body_mass[right_id]

        left_camera_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_BODY, "left_camera_mount"
        )
        right_camera_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_BODY, "right_camera_mount"
        )
        self.assertAlmostEqual(model.body_mass[left_camera_id], 0.083)
        self.assertAlmostEqual(model.body_mass[right_camera_id], 0.0)
        left_total_kg += model.body_mass[left_camera_id]
        right_total_kg += model.body_mass[right_camera_id]
        self.assertAlmostEqual(left_total_kg, 1.006)
        self.assertAlmostEqual(right_total_kg, 0.907)

        camera_geom_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_GEOM, "left_camera_box2"
        )
        self.assertAlmostEqual(model.geom_size[camera_geom_id][2], 0.0115)

    def test_summary_exposes_uncertainty_and_inertia_status(self) -> None:
        mass_summary = scene_summary()["robots"]["mass_profile"]
        self.assertEqual(mass_summary["left_arm_with_payload_total_g"], 1006)
        self.assertEqual(mass_summary["total_range_g"], [965, 1047])
        self.assertIn("CAD centers retained", mass_summary["com_and_inertia_status"])

    def test_new_chess_runs_can_explicitly_opt_into_mass_profile(self) -> None:
        contract = load_task_contract()
        env = ChessRookLiftEnv(
            contract,
            seed=int(contract["training_split"]["seeds"][0]),
            piece_offset_xy_m=(0.0, 0.0),
            mass_profile_path=DEFAULT_SO101_MASS_PROFILE,
        )
        base_id = mujoco.mj_name2id(
            env.model, mujoco.mjtObj.mjOBJ_BODY, "left_base"
        )
        self.assertAlmostEqual(float(env.model.body_mass[base_id]), 0.222, places=6)


if __name__ == "__main__":
    unittest.main()

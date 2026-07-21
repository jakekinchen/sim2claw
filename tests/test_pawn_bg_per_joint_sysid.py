from __future__ import annotations

import unittest

import numpy as np

from sim2claw.pawn_bg_actuator_sysid import (
    PER_JOINT_BOUNDS,
    PER_JOINT_NOMINAL,
    _per_joint_parameters_from_vector,
)


class PerJointSysidContractTests(unittest.TestCase):
    def test_parameter_vector_layout_is_stable(self) -> None:
        vector = np.concatenate([
            [0.05],
            np.full(5, 0.5),
            np.full(5, 0.1),
            np.full(5, 2.0),
        ])
        parameters = _per_joint_parameters_from_vector(vector)
        self.assertEqual(parameters["command_latency_seconds"], 0.05)
        self.assertEqual(parameters["forcerange_scale_per_joint"], [0.5] * 5)
        self.assertEqual(parameters["frictionloss_nm_per_joint"], [0.1] * 5)
        self.assertEqual(parameters["damping_scale_per_joint"], [2.0] * 5)

    def test_bounds_keep_torque_and_friction_physical(self) -> None:
        self.assertGreaterEqual(PER_JOINT_BOUNDS["forcerange_scale"][0], 0.1)
        self.assertLessEqual(PER_JOINT_BOUNDS["forcerange_scale"][1], 2.0)
        self.assertEqual(PER_JOINT_BOUNDS["frictionloss_nm"][0], 0.0)
        self.assertLessEqual(PER_JOINT_BOUNDS["frictionloss_nm"][1], 1.0)
        self.assertGreaterEqual(PER_JOINT_BOUNDS["command_latency_seconds"][0], 0.0)
        self.assertLessEqual(PER_JOINT_BOUNDS["command_latency_seconds"][1], 0.2)

    def test_nominal_starts_at_vendored_model_values(self) -> None:
        self.assertEqual(PER_JOINT_NOMINAL["forcerange_scale"], 1.0)
        self.assertEqual(PER_JOINT_NOMINAL["frictionloss_nm"], 0.052)
        self.assertEqual(PER_JOINT_NOMINAL["damping_scale"], 1.0)


class PerJointBindingTests(unittest.TestCase):
    def test_per_joint_binding_edits_only_left_arm_dofs(self) -> None:
        from sim2claw.pawn_bg_actuator_sysid import make_per_joint_binding
        from sim2claw.pawn_bg_workcell_fit import WorkcellCandidate, build_workcell_model

        candidate = WorkcellCandidate(
            board_yaw_relative_to_table_degrees=181.55,
            board_center_in_table_frame_xy_m=(0.04, -0.065),
            joint_zero_offsets_rad=(0.0,) * 5,
            joint_range_envelope_rad=tuple((0.0, 0.0) for _ in range(5)),
        )
        reference = build_workcell_model(candidate)
        parameters = {
            "command_latency_seconds": 0.05,
            "forcerange_scale_per_joint": [0.5] * 5,
            "frictionloss_nm_per_joint": [0.2] * 5,
            "damping_scale_per_joint": [2.0] * 5,
        }
        binding = make_per_joint_binding(candidate, parameters)
        model = binding["model"]
        reference_model = reference["model"]
        for index in range(5):
            actuator_id = binding["actuator_ids"][index]
            dof = int(model.jnt_dofadr[binding["joint_ids"][index]])
            self.assertAlmostEqual(
                float(model.actuator_forcerange[actuator_id, 1]),
                float(reference_model.actuator_forcerange[actuator_id, 1]) * 0.5,
            )
            self.assertAlmostEqual(float(model.dof_frictionloss[dof]), 0.2)
            self.assertAlmostEqual(
                float(model.dof_damping[dof]),
                float(reference_model.dof_damping[dof]) * 2.0,
            )
        untouched = np.delete(
            np.arange(model.nu),
            [binding["actuator_ids"][index] for index in range(5)],
        )
        np.testing.assert_array_equal(
            model.actuator_forcerange[untouched],
            reference_model.actuator_forcerange[untouched],
        )
        self.assertEqual(binding["parameters"]["command_latency_seconds"], 0.05)


if __name__ == "__main__":
    unittest.main()

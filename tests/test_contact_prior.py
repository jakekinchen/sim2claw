from __future__ import annotations

import copy
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import mujoco
import numpy as np

from sim2claw.contact_prior import (
    DYNAMICS_ARRAY_FIELDS,
    INERTIAL_CONTROL_ARRAY_FIELDS,
    VARIANT_ORDER,
    apply_contact_variant,
    compiled_contact_identity,
    compiled_dynamics_sha256,
    contact_prior_contract_sha256,
    load_contact_prior_contract,
    load_simulator_variant,
)
from sim2claw.scene import build_scene_spec


class RubberTipContactPriorTest(unittest.TestCase):
    def _assert_contract_tamper_rejected(self, mutate) -> None:
        contract = load_contact_prior_contract()
        mutate(contract)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            path.write_text(
                json.dumps(contract, indent=2, sort_keys=False) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_contact_prior_contract(path)

    def test_contract_freezes_exact_order_and_excludes_mass_effect(self) -> None:
        contract = load_contact_prior_contract()
        self.assertEqual(contract["evaluation_order"], list(VARIANT_ORDER))
        self.assertEqual(set(contract["variants"]), set(VARIANT_ORDER))
        self.assertFalse(contract["reported_modification"]["physical_measurements_available"])
        collision = contract["collision_approximation"]
        self.assertEqual(
            collision["mass_effect_mode"],
            "excluded_as_negligible_unmeasured_owner_assessment",
        )
        self.assertEqual(
            collision["physical_mass_acknowledgement"],
            "nonzero_unmeasured_intentionally_approximated_as_zero_for_dynamics",
        )
        for variant_id in VARIANT_ORDER[1:]:
            self.assertIn("effective_box_half_width_m", contract["variants"][variant_id])
            self.assertNotIn("effective_outer_radius_m", contract["variants"][variant_id])
            self.assertNotIn("added_mass_per_finger_kg", contract["variants"][variant_id])
        self.assertEqual(len(contact_prior_contract_sha256()), 64)
        identities = {
            load_simulator_variant(variant_id).variant_sha256
            for variant_id in contract["evaluation_order"]
        }
        self.assertEqual(len(identities), 4)

    def test_contract_rejects_extra_key_provenance_and_bool_numeric_tamper(self) -> None:
        mutations = (
            lambda value: value.update({"unexpected": True}),
            lambda value: value["variants"]["rubber_tip_low"].update(
                {"parameter_provenance": "measured"}
            ),
            lambda value: value["variants"]["rubber_tip_low"].update(
                {"effective_wrap_thickness_m": True}
            ),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self._assert_contract_tamper_rejected(mutate)

    def test_contract_rejects_duplicate_reordered_and_missing_variants(self) -> None:
        mutations = (
            lambda value: value.update(
                {
                    "evaluation_order": [
                        "nominal_uncalibrated",
                        "rubber_tip_low",
                        "rubber_tip_low",
                        "rubber_tip_high",
                    ]
                }
            ),
            lambda value: value.update(
                {"evaluation_order": list(reversed(value["evaluation_order"]))}
            ),
            lambda value: value["variants"].pop("rubber_tip_high"),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self._assert_contract_tamper_rejected(mutate)

    def test_nominal_variant_is_bitwise_compiled_dynamics_noop(self) -> None:
        baseline = build_scene_spec(mass_profile_path=None).compile()
        nominal_spec = build_scene_spec(mass_profile_path=None)
        application = apply_contact_variant(
            nominal_spec, load_simulator_variant("nominal_uncalibrated")
        )
        nominal = nominal_spec.compile()
        self.assertTrue(application["nominal_unchanged"])
        self.assertEqual(compiled_dynamics_sha256(baseline), compiled_dynamics_sha256(nominal))
        for field in DYNAMICS_ARRAY_FIELDS:
            with self.subTest(field=field):
                self.assertTrue(
                    np.array_equal(getattr(baseline, field), getattr(nominal, field))
                )

    def test_all_rubber_variants_change_only_collision_contact_arrays(self) -> None:
        baseline = build_scene_spec(mass_profile_path=None).compile()
        baseline_total_mass = np.asarray(np.sum(baseline.body_mass), dtype=np.float64)
        for variant_id in VARIANT_ORDER[1:]:
            with self.subTest(variant_id=variant_id):
                spec = build_scene_spec(mass_profile_path=None)
                variant = load_simulator_variant(variant_id)
                application = apply_contact_variant(spec, variant)
                model = spec.compile()
                identity = compiled_contact_identity(model, application)
                self.assertEqual(model.nbody, baseline.nbody)
                self.assertEqual(model.njnt, baseline.njnt)
                self.assertEqual(model.nv, baseline.nv)
                self.assertEqual(model.nu, baseline.nu)
                self.assertEqual(len(application["added_geoms"]), 2)
                self.assertEqual(len(identity["bindings"]), 2)
                self.assertEqual(identity["modeled_added_mass_kg"], 0.0)
                self.assertEqual(
                    np.asarray(np.sum(model.body_mass), dtype=np.float64).tobytes(),
                    baseline_total_mass.tobytes(),
                )
                for field in INERTIAL_CONTROL_ARRAY_FIELDS:
                    with self.subTest(variant_id=variant_id, field=field):
                        self.assertTrue(
                            np.array_equal(getattr(baseline, field), getattr(model, field))
                        )
                expected_friction = variant.payload["contact_friction"]
                expected_softness = variant.payload["contact_softness"]
                for binding in identity["bindings"]:
                    self.assertTrue(binding["identity_checks_passed"])
                    self.assertEqual(
                        binding["compiled_geom_body_id"], binding["parent_body_id"]
                    )
                    self.assertEqual(binding["modeled_added_mass_kg"], 0.0)
                    self.assertEqual(binding["geom_condim"], 6)
                    self.assertEqual(binding["geom_priority"], 2)
                    self.assertEqual(
                        binding["geom_friction"],
                        [
                            expected_friction["sliding_dimensionless"],
                            expected_friction["torsional_m"],
                            expected_friction["rolling_m"],
                        ],
                    )
                    self.assertEqual(
                        binding["geom_solref"],
                        [
                            expected_softness["solref_time_constant_s"],
                            expected_softness["solref_damping_ratio"],
                        ],
                    )

    def test_anchor_geometry_mismatch_fails_closed(self) -> None:
        variant = load_simulator_variant("rubber_tip_low")
        collision = copy.deepcopy(variant.collision_approximation)
        collision["fingers"][0]["anchor_geom_suffix"] = "missing_anchor"
        tampered = replace(variant, collision_approximation=collision)
        with self.assertRaisesRegex(ValueError, "anchor geom is missing"):
            apply_contact_variant(build_scene_spec(mass_profile_path=None), tampered)

    def test_rubber_wrap_ridges_layer_over_continuous_sleeve(self) -> None:
        base = load_simulator_variant("rubber_tip_high")
        payload = copy.deepcopy(base.payload)
        payload.update(
            {
                "wrap_ridge_count": 4,
                "wrap_ridge_height_m": 0.0005,
                "wrap_ridge_fill_fraction": 0.5,
            }
        )
        variant = replace(base, payload=payload, variant_id="ridge_test")
        spec = build_scene_spec(mass_profile_path=None)
        application = apply_contact_variant(spec, variant)
        model = spec.compile()

        self.assertEqual(len(application["added_geoms"]), 10)
        self.assertEqual(
            sum(
                row["contact_layer"] == "raised_wrap_ridge"
                for row in application["bindings"]
            ),
            8,
        )
        for finger in ("fixed", "moving"):
            core_name = f"left_rubber_tip_{finger}_ridge_test_geom"
            ridge_name = f"left_rubber_tip_{finger}_ridge_test_ridge_01_geom"
            core_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, core_name)
            ridge_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, ridge_name)
            self.assertGreaterEqual(core_id, 0)
            self.assertGreaterEqual(ridge_id, 0)
            self.assertGreater(model.geom_size[ridge_id, 0], model.geom_size[core_id, 0])

    def test_rubber_wrap_ridges_reject_gapped_base_sleeve(self) -> None:
        base = load_simulator_variant("rubber_tip_high")
        payload = copy.deepcopy(base.payload)
        payload.update(
            {
                "wrap_segment_count": 4,
                "wrap_segment_fill_fraction": 0.8,
                "wrap_ridge_count": 4,
                "wrap_ridge_height_m": 0.0005,
            }
        )
        variant = replace(base, payload=payload, variant_id="invalid_ridge_test")
        with self.assertRaisesRegex(ValueError, "continuous base sleeve"):
            apply_contact_variant(build_scene_spec(mass_profile_path=None), variant)

    def test_segmented_normal_compliance_adds_bounded_spring_pad_bodies(self) -> None:
        base = load_simulator_variant("rubber_tip_high")
        payload = copy.deepcopy(base.payload)
        payload.update(
            {
                "wrap_segment_count": 3,
                "wrap_segment_fill_fraction": 0.9,
                "normal_compliance": {
                    "enabled": True,
                    "travel_m": 0.002,
                    "stiffness_n_per_m": 1000.0,
                    "damping_n_s_per_m": 2.0,
                    "modeled_mass_per_finger_kg": 0.001,
                },
            }
        )
        variant = replace(base, payload=payload, variant_id="compliant_test")
        spec = build_scene_spec(mass_profile_path=None)
        application = apply_contact_variant(spec, variant)
        model = spec.compile()

        self.assertEqual(len(application["added_geoms"]), 6)
        self.assertEqual(len(application["added_bodies"]), 6)
        self.assertEqual(len(application["added_joints"]), 6)
        for binding in application["bindings"]:
            joint_id = mujoco.mj_name2id(
                model, mujoco.mjtObj.mjOBJ_JOINT, binding["added_joint"]
            )
            body_id = mujoco.mj_name2id(
                model, mujoco.mjtObj.mjOBJ_BODY, binding["added_body"]
            )
            geom_id = mujoco.mj_name2id(
                model, mujoco.mjtObj.mjOBJ_GEOM, binding["added_geom"]
            )
            dof_id = int(model.jnt_dofadr[joint_id])
            self.assertGreaterEqual(joint_id, 0)
            self.assertGreaterEqual(body_id, 0)
            self.assertEqual(int(model.geom_bodyid[geom_id]), body_id)
            self.assertTrue(np.allclose(model.jnt_range[joint_id], [-0.002, 0.002]))
            self.assertEqual(float(model.jnt_stiffness[joint_id]), 1000.0)
            self.assertEqual(float(model.dof_damping[dof_id]), 2.0)
            self.assertAlmostEqual(binding["modeled_added_mass_kg"], 1 / 3000)

    def test_compression_only_normal_compliance_uses_opposed_unilateral_ranges(self) -> None:
        base = load_simulator_variant("rubber_tip_high")
        payload = copy.deepcopy(base.payload)
        payload["normal_compliance"] = {
            "enabled": True,
            "travel_m": 0.001,
            "stiffness_n_per_m": 300.0,
            "damping_n_s_per_m": 1.095,
            "modeled_mass_per_finger_kg": 0.001,
            "compression_only": True,
            "limit_time_constant_s": 0.002,
            "limit_damping_ratio": 1.0,
        }
        variant = replace(base, payload=payload, variant_id="compression_only_test")
        spec = build_scene_spec(mass_profile_path=None)
        application = apply_contact_variant(spec, variant)
        model = spec.compile()

        for binding in application["bindings"]:
            joint_id = mujoco.mj_name2id(
                model, mujoco.mjtObj.mjOBJ_JOINT, binding["added_joint"]
            )
            expected = (
                [-0.001, 0.0]
                if binding["finger_id"] == "fixed"
                else [0.0, 0.001]
            )
            self.assertTrue(np.allclose(model.jnt_range[joint_id], expected))
            self.assertTrue(binding["normal_compliance"]["compression_only"])
            self.assertEqual(
                binding["normal_compliance"]["joint_range_m"], expected
            )


if __name__ == "__main__":
    unittest.main()

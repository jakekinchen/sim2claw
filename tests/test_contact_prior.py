from __future__ import annotations

import unittest

import mujoco

from sim2claw.contact_prior import (
    apply_contact_variant,
    contact_prior_contract_sha256,
    load_contact_prior_contract,
    load_simulator_variant,
)
from sim2claw.scene import build_scene_spec


class RubberTipContactPriorTest(unittest.TestCase):
    def test_contract_freezes_nominal_and_three_ordered_priors(self) -> None:
        contract = load_contact_prior_contract()
        self.assertEqual(
            contract["evaluation_order"],
            [
                "nominal_uncalibrated",
                "rubber_tip_low",
                "rubber_tip_nominal_prior",
                "rubber_tip_high",
            ],
        )
        self.assertFalse(contract["reported_modification"]["physical_measurements_available"])
        self.assertEqual(len(contact_prior_contract_sha256()), 64)
        identities = {
            load_simulator_variant(variant_id).variant_sha256
            for variant_id in contract["evaluation_order"]
        }
        self.assertEqual(len(identities), 4)

    def test_nominal_variant_is_strict_spec_noop(self) -> None:
        spec = build_scene_spec(mass_profile_path=None)
        before = len(list(spec.geoms))
        result = apply_contact_variant(spec, load_simulator_variant("nominal_uncalibrated"))
        self.assertTrue(result["nominal_unchanged"])
        self.assertEqual(len(list(spec.geoms)), before)

    def test_rubber_variant_adds_one_massive_sleeve_per_finger(self) -> None:
        spec = build_scene_spec(mass_profile_path=None)
        variant = load_simulator_variant("rubber_tip_nominal_prior")
        result = apply_contact_variant(spec, variant)
        self.assertFalse(result["nominal_unchanged"])
        self.assertEqual(len(result["added_geoms"]), 2)
        model = spec.compile()
        for name in result["added_geoms"]:
            geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, name)
            self.assertGreaterEqual(geom_id, 0)
            self.assertEqual(int(model.geom_condim[geom_id]), 6)
            self.assertEqual(int(model.geom_priority[geom_id]), 2)
            self.assertAlmostEqual(float(model.geom_friction[geom_id, 0]), 1.2)
            self.assertAlmostEqual(float(model.geom_solref[geom_id, 0]), 0.01)
            self.assertAlmostEqual(float(model.geom_solref[geom_id, 1]), 1.0)


if __name__ == "__main__":
    unittest.main()

from sim2claw.observable_registration_measured_state_single_surface import (
    load_measured_state_single_surface_contract,
)


def test_contract_preserves_exactly_one_mesh_per_jaw() -> None:
    contract = load_measured_state_single_surface_contract()
    baseline, candidate = contract["variants"]
    assert baseline["sts3215_force_limit_nm"] == 2.94
    assert candidate["sts3215_force_limit_nm"] == 2.94
    assert baseline["one_contact_bearing_mesh_per_jaw"] is False
    assert candidate["one_contact_bearing_mesh_per_jaw"] is True
    intervention = contract["single_surface_intervention"]
    assert intervention["preserved_collision_mesh_by_body"] == {
        "left_gripper": "mjobj_geom-483",
        "left_moving_jaw_so101_v1": "mjobj_geom-494",
    }
    assert (
        intervention[
            "disable_every_other_collision_enabled_geom_on_target_bodies"
        ]
        is True
    )
    assert (
        intervention[
            "preserve_selected_mesh_geometry_pose_material_friction_solref_solimp_and_condim"
        ]
        is True
    )
    assert contract["simulation"]["natural_pawn_dynamics_only"] is True
    assert contract["simulation"]["object_pose_injection_allowed"] is False
    assert not any(contract["claim_limits"].values())

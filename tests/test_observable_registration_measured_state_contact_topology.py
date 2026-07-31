from sim2claw.observable_registration_measured_state_contact_topology import (
    load_measured_state_contact_topology_contract,
)


def test_contract_changes_only_collision_bearing_jaw_mesh_topology() -> None:
    contract = load_measured_state_contact_topology_contract()
    baseline, candidate = contract["variants"]
    assert baseline["sts3215_force_limit_nm"] == 2.94
    assert candidate["sts3215_force_limit_nm"] == 2.94
    assert baseline["disable_collision_bearing_jaw_mesh_cores"] is False
    assert candidate["disable_collision_bearing_jaw_mesh_cores"] is True
    topology = contract["topology_intervention"]
    assert topology["disable_only_collision_enabled_mesh_geoms"] is True
    assert topology["preserve_all_existing_primitive_geoms"] is True
    assert (
        topology[
            "preserve_geom_size_pose_material_friction_solref_solimp_and_condim"
        ]
        is True
    )
    assert contract["trajectory"]["row_count"] == 531
    assert contract["simulation"]["natural_pawn_dynamics_only"] is True
    assert contract["simulation"]["object_pose_injection_allowed"] is False
    assert not any(contract["claim_limits"].values())
    assert contract["authority"]["simulator_replay"] is True
    assert not any(
        value
        for name, value in contract["authority"].items()
        if name != "simulator_replay"
    )

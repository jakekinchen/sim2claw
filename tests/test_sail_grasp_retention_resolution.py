from __future__ import annotations

from sim2claw.paths import REPO_ROOT
from sim2claw.sail.grasp_retention_resolution import (
    _anchor_result,
    candidate_parameters,
    load_grasp_retention_contract,
)


def test_frozen_grasp_retention_contract_and_bindings() -> None:
    contract = load_grasp_retention_contract()

    assert len(contract["frozen_candidate_family"]) == 18
    assert len(contract["verified_source_bindings"]) == 7
    assert not contract["proof_boundary"]["policy_actions_mutable"]
    assert not contract["proof_boundary"]["physical_authority"]


def test_candidate_parameters_do_not_mutate_frozen_base() -> None:
    contract = load_grasp_retention_contract()
    candidate = contract["frozen_candidate_family"][1]

    parameters = candidate_parameters(contract, candidate)

    assert parameters["tip_fixed_coverage_offset_m"] == 0.04
    assert "tip_fixed_coverage_offset_m" not in contract["base_parameters"]


def test_force_contact_followup_is_frozen_and_bound_to_first_result() -> None:
    contract = load_grasp_retention_contract(
        contract_path=(
            REPO_ROOT / "configs" / "sail" / "grasp_retention_force_contact_v1.json"
        )
    )

    assert len(contract["frozen_candidate_family"]) == 18
    assert contract["diagnosis_anchor"]["aligned_pad_contact_loss_delay_frames_over_baseline"] == 58
    assert contract["base_parameters"]["tip_fixed_coverage_offset_m"] == 0.04


def test_contact_compliance_followup_is_bounded() -> None:
    contract = load_grasp_retention_contract(
        contract_path=(
            REPO_ROOT
            / "configs"
            / "sail"
            / "grasp_retention_contact_compliance_v1.json"
        )
    )

    assert len(contract["frozen_candidate_family"]) == 12
    assert {
        row["overrides"].get("gripper_force_limit_multiplier", 1.0)
        for row in contract["frozen_candidate_family"]
    } == {1.0, 1.25}
    assert max(
        row["overrides"].get("solimp_width_m", 0.0005)
        for row in contract["frozen_candidate_family"]
    ) == 0.0015


def test_current_torque_followup_uses_manufacturer_scale() -> None:
    contract = load_grasp_retention_contract(
        contract_path=(
            REPO_ROOT
            / "configs"
            / "sail"
            / "grasp_retention_current_torque_v1.json"
        )
    )

    anchor = contract["diagnosis_anchor"]
    assert anchor["physical_loaded_median_raw_current"] == 7.0
    assert anchor["physical_loaded_current_amp"] == 0.0455
    assert abs(anchor["physical_to_mujoco_nominal_force_ratio"] - 0.011839) < 1e-6
    assert len(contract["frozen_candidate_family"]) == 12


def test_load_hold_followup_is_contact_triggered_and_action_frozen() -> None:
    contract = load_grasp_retention_contract(
        contract_path=(
            REPO_ROOT
            / "configs"
            / "sail"
            / "grasp_retention_load_hold_v1.json"
        )
    )

    assert contract["base_parameters"]["gripper_load_hold_enabled"]
    assert not contract["proof_boundary"]["policy_actions_mutable"]
    assert len(contract["frozen_candidate_family"]) == 12


def test_calibrated_hold_uses_frozen_physical_loaded_position() -> None:
    contract = load_grasp_retention_contract(
        contract_path=(
            REPO_ROOT
            / "configs"
            / "sail"
            / "grasp_retention_calibrated_hold_v1.json"
        )
    )

    assert contract["base_parameters"]["gripper_load_hold_latch_target_rad"] == (
        contract["diagnosis_anchor"]["physical_measured_median_rad"]
    )
    assert len(contract["frozen_candidate_family"]) == 8


def test_final_composite_only_crosses_established_mechanisms() -> None:
    contract = load_grasp_retention_contract(
        contract_path=(
            REPO_ROOT
            / "configs"
            / "sail"
            / "grasp_retention_composite_v1.json"
        )
    )

    assert len(contract["frozen_candidate_family"]) == 6
    assert {
        row["overrides"].get("tip_fixed_coverage_offset_m", 0.04)
        for row in contract["frozen_candidate_family"]
    } == {0.04, 0.045, 0.05}


def test_capsule_pad_family_matches_qualitative_video_shape() -> None:
    contract = load_grasp_retention_contract(
        contract_path=(
            REPO_ROOT
            / "configs"
            / "sail"
            / "grasp_retention_capsule_pad_v1.json"
        )
    )

    assert contract["base_parameters"]["rubber_tip_shape_capsule"]
    assert len(contract["frozen_candidate_family"]) == 12


def test_normal_compliance_family_is_frozen_and_action_invariant() -> None:
    contract = load_grasp_retention_contract(
        contract_path=(
            REPO_ROOT
            / "configs"
            / "sail"
            / "grasp_retention_normal_compliance_v1.json"
        )
    )

    assert len(contract["frozen_candidate_family"]) == 18
    assert not contract["proof_boundary"]["policy_actions_mutable"]
    assert not contract["base_parameters"]["gripper_load_hold_enabled"]
    assert not contract["base_parameters"]["rubber_tip_normal_compliance_enabled"]
    assert all(
        row["candidate_id"] == "baseline"
        or row["overrides"]["rubber_tip_normal_compliance_enabled"]
        for row in contract["frozen_candidate_family"]
    )


def test_compliant_footprint_followup_is_bound_to_first_negative() -> None:
    contract = load_grasp_retention_contract(
        contract_path=(
            REPO_ROOT
            / "configs"
            / "sail"
            / "grasp_retention_compliant_footprint_v1.json"
        )
    )

    assert len(contract["frozen_candidate_family"]) == 18
    assert contract["diagnosis_anchor"]["first_compliance_anchor_pass_count"] == 0
    assert contract["diagnosis_anchor"]["fixed_edge_contact_abs_y_m"] > 0.0064
    assert max(
        row["overrides"].get("tip_fixed_half_width_multiplier", 1.0)
        for row in contract["frozen_candidate_family"]
    ) == 1.75


def test_layered_cap_family_requires_rubber_load_path() -> None:
    contract = load_grasp_retention_contract(
        contract_path=(
            REPO_ROOT
            / "configs"
            / "sail"
            / "grasp_retention_layered_cap_v1.json"
        )
    )

    assert len(contract["frozen_candidate_family"]) == 18
    assert contract["diagnosis_anchor"]["free_surface_anchor_pass_count"] == 0
    assert contract["base_parameters"]["tip_segment_count"] == 1
    assert contract["acceptance"][
        "anchor_minimum_rubber_load_pair_fraction_after_lift"
    ] == 0.9


def test_core_anchored_cap_uses_true_distal_primitives() -> None:
    contract = load_grasp_retention_contract(
        contract_path=(
            REPO_ROOT
            / "configs"
            / "sail"
            / "grasp_retention_core_anchored_cap_v1.json"
        )
    )

    assert len(contract["frozen_candidate_family"]) == 18
    assert contract["base_parameters"][
        "rubber_tip_fixed_anchor_geom_suffix"
    ] == "fixed_jaw_box6"
    assert contract["base_parameters"][
        "rubber_tip_moving_anchor_geom_suffix"
    ] == "moving_jaw_box3"
    assert not contract["base_parameters"]["gripper_load_hold_enabled"]


def test_core_cap_load_response_cross_is_bounded() -> None:
    contract = load_grasp_retention_contract(
        contract_path=(
            REPO_ROOT
            / "configs"
            / "sail"
            / "grasp_retention_core_cap_load_response_v1.json"
        )
    )

    assert len(contract["frozen_candidate_family"]) == 18
    assert contract["diagnosis_anchor"]["core_cap_transport_preserved"]
    assert {
        row["overrides"].get("gripper_piece_contact_force_limit_multiplier")
        for row in contract["frozen_candidate_family"][1:13]
    } == {0.02, 0.05, 0.1, 0.2}
    assert max(
        row["overrides"].get("sliding_friction", 1.8)
        for row in contract["frozen_candidate_family"]
    ) == 3.5


def test_torque_latch_family_never_mutates_control_target() -> None:
    contract = load_grasp_retention_contract(
        contract_path=(
            REPO_ROOT
            / "configs"
            / "sail"
            / "grasp_retention_torque_latch_v1.json"
        )
    )

    assert len(contract["frozen_candidate_family"]) == 18
    assert not contract["base_parameters"]["gripper_load_hold_enabled"]
    assert all(
        row["candidate_id"] == "baseline"
        or row["overrides"]["gripper_contact_force_limit_latch_enabled"]
        for row in contract["frozen_candidate_family"]
    )
    assert contract["proof_boundary"]["simulator_ctrl_mutable"] is False


def test_long_wrap_family_covers_observed_fixed_bypass_path() -> None:
    contract = load_grasp_retention_contract(
        contract_path=(
            REPO_ROOT
            / "configs"
            / "sail"
            / "grasp_retention_long_wrap_torque_v1.json"
        )
    )

    assert len(contract["frozen_candidate_family"]) == 18
    assert contract["base_parameters"][
        "rubber_tip_fixed_anchor_geom_suffix"
    ] == "fixed_jaw_box5"
    assert contract["base_parameters"]["tip_coverage_m"] == 0.04
    assert contract["base_parameters"]["tip_moving_coverage_multiplier"] == 0.3
    assert contract["diagnosis_anchor"]["retained_transport_fixed_bypass_geom"] == (
        "left_fixed_jaw_box4"
    )


def test_collision_skin_hides_enclosed_rigid_primitives() -> None:
    contract = load_grasp_retention_contract(
        contract_path=(
            REPO_ROOT
            / "configs"
            / "sail"
            / "grasp_retention_collision_skin_v1.json"
        )
    )

    assert len(contract["frozen_candidate_family"]) == 18
    assert not contract["base_parameters"][
        "fixed_jaw_primitive_collision_enabled"
    ]
    assert not contract["base_parameters"][
        "moving_jaw_primitive_collision_enabled"
    ]
    assert contract["acceptance"][
        "anchor_minimum_rubber_load_pair_fraction_after_lift"
    ] == 1.0


def test_moving_overhang_family_targets_two_edge_corner() -> None:
    contract = load_grasp_retention_contract(
        contract_path=(
            REPO_ROOT
            / "configs"
            / "sail"
            / "grasp_retention_moving_overhang_v1.json"
        )
    )

    assert len(contract["frozen_candidate_family"]) == 18
    assert contract["diagnosis_anchor"]["moving_contact_abs_coverage_m"] > 0.0058
    assert contract["diagnosis_anchor"]["moving_contact_abs_width_m"] > 0.0049
    assert max(
        row["overrides"].get("tip_moving_coverage_multiplier", 0.3)
        for row in contract["frozen_candidate_family"]
    ) == 0.48
    assert max(
        row["overrides"].get("tip_moving_half_width_multiplier", 0.8333333333333334)
        for row in contract["frozen_candidate_family"]
    ) == 1.3333333333333333


def test_compliant_skin_cross_uses_corrected_footprint() -> None:
    contract = load_grasp_retention_contract(
        contract_path=(
            REPO_ROOT
            / "configs"
            / "sail"
            / "grasp_retention_compliant_skin_v1.json"
        )
    )

    assert len(contract["frozen_candidate_family"]) == 18
    assert contract["base_parameters"]["rubber_tip_normal_compliance_enabled"]
    assert contract["base_parameters"]["tip_moving_coverage_multiplier"] == 0.36
    assert contract["base_parameters"]["tip_moving_half_width_multiplier"] == (
        1.3333333333333333
    )
    assert {
        row["overrides"].get(
            "gripper_piece_contact_force_limit_multiplier",
            contract["base_parameters"][
                "gripper_piece_contact_force_limit_multiplier"
            ],
        )
        for row in contract["frozen_candidate_family"]
    } == {0.022, 0.024}


def test_stable_compliance_family_requires_clean_solver_state() -> None:
    contract = load_grasp_retention_contract(
        contract_path=(
            REPO_ROOT
            / "configs"
            / "sail"
            / "grasp_retention_stable_compliance_v1.json"
        )
    )

    assert len(contract["frozen_candidate_family"]) == 18
    assert contract["acceptance"]["anchor_simulation_stability_required"]
    assert min(
        row["overrides"].get(
            "simulation_timestep_multiplier",
            contract["base_parameters"]["simulation_timestep_multiplier"],
        )
        for row in contract["frozen_candidate_family"]
    ) == 0.1
    assert max(
        row["overrides"].get(
            "rubber_tip_compliance_stiffness_n_per_m",
            contract["base_parameters"][
                "rubber_tip_compliance_stiffness_n_per_m"
            ],
        )
        for row in contract["frozen_candidate_family"]
    ) == 1000.0


def test_contact_height_family_moves_stable_rubber_surface_distally() -> None:
    contract = load_grasp_retention_contract(
        contract_path=(
            REPO_ROOT
            / "configs"
            / "sail"
            / "grasp_retention_contact_height_v1.json"
        )
    )

    assert len(contract["frozen_candidate_family"]) == 18
    assert contract["acceptance"]["anchor_simulation_stability_required"]
    assert contract["base_parameters"]["tip_coverage_offset_m"] == 0.0
    offsets = {
        row["overrides"].get("tip_coverage_offset_m", 0.0)
        for row in contract["frozen_candidate_family"]
    }
    assert min(offsets) == -0.02
    assert max(offsets) == 0.0
    assert {
        row["overrides"].get(
            "gripper_piece_contact_force_limit_multiplier", 0.022
        )
        for row in contract["frozen_candidate_family"]
    } == {0.0215, 0.022, 0.0225}


def test_anchor_result_rejects_aperture_only_false_fit() -> None:
    contract = load_grasp_retention_contract()
    expected_action = contract["diagnosis_anchor"]["action_array_sha256"]
    episode = {
        "action_array_sha256": expected_action,
        "action_byte_identical": True,
        "retention_event_summary": {
            "first_bilateral_contact_loss_after_lift": {"source_index": 410}
        },
        "event_aligned_gripper_metrics": {
            "simulated_minus_measured_bias_degrees": 0.1
        },
        "maximum_post_grasp_slip_m": 0.01,
        "lift_and_transport": False,
        "piece_lifted": True,
        "bilateral_lift_retention": True,
        "maximum_bilateral_lift_retention_seconds": 1.0,
        "trace_metrics": {"overall_joint_rms_degrees": 1.0, "ee_rms_m": 0.01},
    }

    result = _anchor_result(
        episode=episode, contract=contract, baseline_slip_m=0.02
    )

    assert result["status"] == "rejected"
    assert result["reasons"] == ["anchor_transport_failure"]

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

from __future__ import annotations

from sim2claw.observable_c922_pixel_lattice_refinement import (
    evaluate_refinement,
    load_refinement_contract,
)


def test_live_contract_preserves_retrospective_proof_ceiling() -> None:
    contract = load_refinement_contract()
    assert (
        contract["evidence_role"]
        == "retrospective_outcome_informed_protocol_diagnostic"
    )
    assert [item["radial_term_count"] for item in contract["camera_families"]] == [
        0,
        1,
        2,
    ]
    assert not any(contract["proof_boundaries"].values())
    assert not any(contract["authority"].values())


def test_retained_pixel_refinement_is_cross_cohort_and_bounded() -> None:
    receipt = evaluate_refinement(load_refinement_contract())
    agreement = receipt["cross_cohort_agreement"]
    assert agreement["overlap_intersection_count"] >= 12
    assert agreement["rms_px"] <= 0.75
    assert agreement["max_px"] <= 1.5
    assert receipt["board_plane_diagnostic_accepted"] is True
    assert receipt["improvement_over_prior_model_fraction"] >= 0.5
    assert receipt["selected_family_id"] == "centered_square_pixel_zero_distortion"
    assert 35.0 < receipt["diagnostic_simulator_camera"]["vertical_fov_degrees"] < 40.0
    assert (
        receipt["diagnostic_simulator_camera"][
            "canonical_scene_replacement_authority"
        ]
        is False
    )
    assert receipt["exact_intrinsic_calibration_approved"] is False
    assert receipt["distortion_measured"] is False
    assert receipt["global_camera_or_robot_mapping_approved"] is False
    assert receipt["simulator_canonical_camera_replaced"] is False
    assert not any(receipt["authority"].values())


def test_retained_pixel_refinement_is_deterministic() -> None:
    contract = load_refinement_contract()
    first = evaluate_refinement(contract)
    second = evaluate_refinement(contract)
    assert first == second

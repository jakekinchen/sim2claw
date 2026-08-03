from __future__ import annotations

from sim2claw.observable_registration_post_final_visual_sanity_residual_attribution import (
    evaluate_once,
    load_post_final_visual_sanity_residual_attribution_contract,
)


def test_contract_freezes_post_final_diagnostic_boundary() -> None:
    contract = load_post_final_visual_sanity_residual_attribution_contract()

    assert len(contract["frame_pairs"]) == 6
    assert contract["regions"]["board_plus_margin"]["dilation_kernel_px"] == 15
    assert contract["resource_boundary"]["new_physical_video_decodes_allowed"] == 0
    assert contract["resource_boundary"]["parameter_fits_allowed"] == 0
    assert contract["claim_limits"]["same_video_semantic_match"] is False
    assert contract["claim_limits"]["untouched_cohort_remaining"] is False


def test_six_frame_audit_selects_robot_workcell_factorization(tmp_path) -> None:
    receipt = evaluate_once(output_directory=tmp_path / "or92")

    assert receipt["status"] == "PASS_ROBOT_WORKCELL_FACTORIZATION_SELECTED"
    assert all(receipt["gates"].values())
    assert receipt["summary"]["mean_board_plus_margin_edge_f1"] >= 0.5
    assert receipt["summary"]["maximum_outside_board_edge_f1"] < 0.4
    assert receipt["summary"]["selected_mechanism"] == "separate_robot_base_and_static_workcell_registration"
    assert receipt["execution"]["new_physical_video_decodes"] == 0

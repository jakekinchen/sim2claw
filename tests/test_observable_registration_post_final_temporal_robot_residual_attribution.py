from __future__ import annotations

from sim2claw.observable_registration_post_final_temporal_robot_residual_attribution import (
    evaluate_once,
    load_post_final_temporal_robot_residual_attribution_contract,
)


def test_or96_contract_is_receipt_only_and_claim_safe() -> None:
    contract = load_post_final_temporal_robot_residual_attribution_contract()

    assert contract["resource_boundary"]["physical_frame_reads_allowed"] == 0
    assert contract["resource_boundary"]["renders_allowed"] == 0
    assert contract["resource_boundary"]["fits_allowed"] == 0
    assert contract["claim_limits"]["same_video_semantic_match"] is False


def test_or96_selects_articulation_and_scene_content_factorization(tmp_path) -> None:
    receipt = evaluate_once(output_directory=tmp_path / "or96")

    assert receipt["status"] == "PASS_ROBOT_ARTICULATION_AND_SCENE_CONTENT_FACTORIZATION_SELECTED"
    assert all(receipt["gates"].values())
    assert receipt["selected_mechanism"] == "robot_articulation_and_renderer_native_scene_content_factorization"
    assert receipt["execution"]["renders"] == 0

import pytest

from sim2claw.bidirectional_registration_v4_label_audit import evaluate


def test_label_audit_preserves_original_but_removes_unsupported_decision() -> None:
    receipt = evaluate()
    assert receipt["status"] == "heldout_unscorable_label_authority_failure"
    assert receipt["original_q03"]["reported_physical_square"] == "b7"
    assert receipt["original_q03"]["reported_residual_mm"] == pytest.approx(
        164.35312826210378
    )
    assert receipt["original_q03"]["camera_owned"] is False
    assert receipt["original_q03"]["valid_heldout_decision"] is False
    assert receipt["corrected_heldout"]["physical_square"] is None
    assert receipt["corrected_heldout"]["residual_mm"] is None
    assert receipt["corrected_heldout"]["passed"] is None
    assert receipt["corrected_heldout"]["held_out_open_count"] == 1
    assert receipt["registration_admitted"] is False
    assert receipt["registration_rejected_by_heldout"] is False
    assert receipt["f1_trigger_supported"] is False
    assert receipt["new_data_opened"] is False
    assert receipt["new_robot_motion"] is False


def test_model_nearest_square_is_retained_only_as_non_authoritative_diagnostic() -> None:
    receipt = evaluate()
    with_offset = receipt["counterfactual_nearest_with_task_offset"][0]
    without_offset = receipt["counterfactual_nearest_without_task_offset"][0]
    assert with_offset["physical_square_if_assumed"] == "a3"
    assert with_offset["residual_mm"] == pytest.approx(22.337386033691228)
    assert with_offset["authoritative"] is False
    assert without_offset["physical_square_if_assumed"] == "a2"
    assert without_offset["horizontal_distance_mm"] == pytest.approx(
        19.71908627304198
    )
    assert without_offset["valid_heldout_score"] is False
    assert receipt["counterfactuals_are_not_labels_or_scores"] is True

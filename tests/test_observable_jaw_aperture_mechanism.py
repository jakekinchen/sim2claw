from __future__ import annotations

from sim2claw.observable_jaw_aperture_mechanism import (
    build_mechanism_receipt,
    evaluate_mechanism_declaration,
    load_mechanism_contract,
)


def test_or5_contract_is_narrow_and_nonphysical() -> None:
    contract = load_mechanism_contract()
    family = contract["model_family"]
    assert family["fit_parameters"] == ["gripper_zero_offset_rad"]
    assert family["gripper_gain_change_allowed"] is False
    assert family["camera_change_allowed"] is False
    assert family["contact_parameter_change_allowed"] is False
    assert contract["split"]["validation_annotations_may_open_in_or5"] is False
    assert contract["split"]["outcome_informed_v4_heldout_is_promotion_eligible"] is False
    assert not any(contract["authority"].values())


def test_or5_declaration_is_identifiable_without_validation_outcome() -> None:
    contract = load_mechanism_contract()
    receipt = evaluate_mechanism_declaration(contract)
    assert receipt["accepted"] is True
    assert receipt["result"] == (
        "SINGLE_GRIPPER_ZERO_OFFSET_APERTURE_MAPPING_IDENTIFIABLE"
    )
    assert receipt["fit"]["pose_count"] == 6
    assert receipt["fit"]["gripper_span_physical_units"] == 0.0
    assert (
        receipt["fit"]["minimum_aperture_sensitivity_px_per_rad"] >= 75.0
    )
    assert receipt["validation_reservation"]["pose_count"] == 4
    assert receipt["validation_reservation"]["annotations_opened"] is False
    assert receipt["checks"]["gain_unidentifiable_from_fit_span"] is True
    assert receipt["checks"]["offset_aperture_sensitivity"] is True


def test_or5_receipt_is_deterministic(tmp_path) -> None:
    first = build_mechanism_receipt(output_path=tmp_path / "first.json")
    second = build_mechanism_receipt(output_path=tmp_path / "second.json")
    assert first == second
    assert first["artifact_sha256"] == second["artifact_sha256"]

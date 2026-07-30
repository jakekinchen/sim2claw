from __future__ import annotations

from sim2claw.observable_body_joint_zero_offset_mechanism import (
    build_body_joint_mechanism_receipt,
    evaluate_body_joint_mechanism,
    load_body_joint_mechanism_contract,
)


def test_contract_freezes_only_pan_lift_offsets_and_no_authority() -> None:
    contract = load_body_joint_mechanism_contract()
    assert contract["model_family"]["fit_parameters"] == [
        "shoulder_pan_zero_offset_rad",
        "shoulder_lift_zero_offset_rad",
    ]
    assert contract["validation_policy"]["admissible_members"] == []
    assert contract["promotion"]["fit_parameter_values_authorized"] is False
    assert not any(contract["authority"].values())


def test_fit_is_identifiable_but_validation_reservation_fails_closed() -> None:
    contract = load_body_joint_mechanism_contract()
    receipt = evaluate_body_joint_mechanism(contract)
    assert receipt["fit_identifiability"]["accepted"] is True
    assert receipt["fit_identifiability"]["jacobian_rank"] == 2
    assert receipt["validation_reservation"]["accepted"] is False
    assert receipt["validation_reservation"]["images_opened"] is False
    assert receipt["fit_parameter_values_produced"] is False
    assert receipt["accepted"] is False
    assert receipt["result"] == (
        "FIT_IDENTIFIABLE_BUT_NO_ADMISSIBLE_UNOPENED_VALIDATION_COHORT"
    )


def test_receipt_is_deterministic(tmp_path) -> None:
    first = build_body_joint_mechanism_receipt(
        output_path=tmp_path / "first.json"
    )
    second = build_body_joint_mechanism_receipt(
        output_path=tmp_path / "second.json"
    )
    assert first == second
    assert first["artifact_sha256"] == second["artifact_sha256"]

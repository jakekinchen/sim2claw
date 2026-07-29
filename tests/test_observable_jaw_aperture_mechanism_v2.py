from __future__ import annotations

from sim2claw.observable_jaw_aperture_mechanism_v2 import (
    build_mechanism_v2_receipt,
    evaluate_mechanism_v2_declaration,
    load_mechanism_v2_contract,
)


def test_or5_v2_preserves_family_and_unopened_visual_outcomes() -> None:
    contract, base = load_mechanism_v2_contract()
    assert base["model_family"]["fit_parameters"] == [
        "gripper_zero_offset_rad"
    ]
    assert contract["method_successor"]["same_model_family"] is True
    assert (
        contract["method_successor"][
            "visual_validation_annotation_values_may_open_in_or5_v2"
        ]
        is False
    )
    assert contract["proof_boundaries"]["v1_negative_is_overwritten"] is False
    assert not any(contract["authority"].values())


def test_or5_v2_aggregate_rank_gate_accepts_identifiability() -> None:
    contract, base = load_mechanism_v2_contract()
    receipt = evaluate_mechanism_v2_declaration(contract, base)
    assert receipt["accepted"] is True
    assert receipt["result"] == (
        "SINGLE_GRIPPER_ZERO_OFFSET_APERTURE_MAPPING_IDENTIFIABLE"
    )
    assert receipt["v1_negative_preserved"]["overwritten"] is False
    assert receipt["fit"]["jacobian_rank"] == 1
    assert (
        receipt["fit"]["aggregate_jacobian_singular_value_px_per_rad"]
        >= 150.0
    )
    assert receipt["fit"]["visual_annotation_values_opened"] is False
    assert (
        receipt["validation_reservation"]["visual_annotation_values_opened"]
        is False
    )


def test_or5_v2_receipt_is_deterministic(tmp_path) -> None:
    first = build_mechanism_v2_receipt(output_path=tmp_path / "first.json")
    second = build_mechanism_v2_receipt(output_path=tmp_path / "second.json")
    assert first == second
    assert first["artifact_sha256"] == second["artifact_sha256"]

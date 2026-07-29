from __future__ import annotations

from sim2claw.observable_jaw_pawn_geometric_gap import (
    build_geometric_gap_receipt,
    evaluate_geometric_gap,
    load_gap_contract,
)


def test_or7a_contract_is_kinematic_and_nonphysical() -> None:
    contract, _ = load_gap_contract()
    assert contract["evaluation"]["physics_integration_allowed"] is False
    assert contract["evaluation"]["forward_kinematics_allowed"] is True
    assert contract["evaluation"]["parameter_fit_allowed"] is False
    assert contract["identity"]["evaluation_interval_samples"] == [228, 260]
    assert not any(contract["authority"].values())


def test_or7a_reports_signed_gap_without_fit() -> None:
    contract, c6 = load_gap_contract()
    receipt = evaluate_geometric_gap(contract, c6)
    assert receipt["identity"]["physics_steps"] == 0
    assert receipt["identity"]["parameters_fit"] == 0
    assert [row["sample_index"] for row in receipt["report_rows"]] == [
        228,
        232,
        260,
    ]
    assert receipt["classification"] in {
        "APERTURE_MAPPING_CLOSES_KINEMATIC_CONTACT_GAP",
        "LARGE_JAW_CENTER_OR_GLOBAL_WRIST_SPATIAL_GAP_REMAINS",
        "SUB_5MM_PAD_OR_CONTACT_BOUNDARY_REMAINS",
    }


def test_or7a_receipt_is_deterministic(tmp_path) -> None:
    first = build_geometric_gap_receipt(output_path=tmp_path / "first.json")
    second = build_geometric_gap_receipt(output_path=tmp_path / "second.json")
    assert first == second
    assert first["artifact_sha256"] == second["artifact_sha256"]

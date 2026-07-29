from __future__ import annotations

from sim2claw.observable_jaw_aperture_fit import (
    build_aperture_fit_receipt,
    evaluate_aperture_fit,
    load_aperture_fit_contract,
)


def test_or6_contract_changes_one_parameter_and_is_nonphysical() -> None:
    contract = load_aperture_fit_contract()
    assert contract["frozen_mechanisms"]["fit_parameter"] == (
        "gripper_zero_offset_rad"
    )
    assert contract["split"]["validation_candidate_refit_allowed"] is False
    assert contract["split"]["sealed_c6_contact_or_outcome_may_be_read"] is False
    assert contract["promotion"]["global_mapping_approved"] is False
    assert contract["promotion"]["dynamic_replay_authorized"] is False
    assert not any(contract["authority"].values())


def test_or6_fit_and_no_refit_validation_promote_task_bounded_candidate() -> None:
    contract = load_aperture_fit_contract()
    receipt, candidate = evaluate_aperture_fit(contract)
    assert receipt["accepted"] is True
    assert receipt["result"] == (
        "TASK_BOUNDED_JAW_APERTURE_CANDIDATE_PROMOTED_GLOBAL_MAPPING_FALSE"
    )
    assert receipt["validation"]["candidate_refit"] is False
    assert receipt["optimizer"]["candidate_fixed_before_validation_open"] is True
    assert receipt["checks"]["only_gripper_zero_offset_changed"] is True
    assert all(receipt["checks"].values())
    assert candidate["global_mapping_approved"] is False
    assert candidate["dynamic_replay_authorized"] is False


def test_or6_receipt_is_deterministic(tmp_path) -> None:
    first = build_aperture_fit_receipt(
        output_path=tmp_path / "first.json",
        candidate_path=tmp_path / "first-candidate.json",
    )
    second = build_aperture_fit_receipt(
        output_path=tmp_path / "second.json",
        candidate_path=tmp_path / "second-candidate.json",
    )
    assert first == second
    assert first["artifact_sha256"] == second["artifact_sha256"]

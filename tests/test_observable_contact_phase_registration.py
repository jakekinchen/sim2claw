from __future__ import annotations

from pathlib import Path

from sim2claw.observable_contact_phase_registration import (
    CONTRACT_PATH,
    build_contact_phase_receipt,
    load_contact_phase_contract,
)


def test_contract_is_fail_closed_and_task_rows_are_evaluation_only() -> None:
    contract, _ = load_contact_phase_contract(CONTRACT_PATH)
    assert contract["fit_policy"]["task_rows_allowed_in_fit"] is False
    assert contract["fit_policy"]["one_mechanism_family_only"] is True
    assert contract["phase_gate"]["last_definitely_separate_sample"] == 224
    assert contract["phase_gate"]["candidate_contact_samples"] == [228, 232]
    assert contract["authority"]["simulator_dynamic_replay"] is False
    assert not any(contract["authority"].values())


def test_retained_candidate_misses_named_contact_phase_without_dynamics(
    tmp_path: Path,
) -> None:
    receipt = build_contact_phase_receipt(
        CONTRACT_PATH,
        tmp_path / "receipt.json",
    )

    assert receipt["result"] == (
        "FROZEN_RETAINED_CANDIDATE_MISSES_NAMED_CONTACT_PHASE_NO_DYNAMICS"
    )
    assert receipt["identity"]["row_count"] == 531
    assert receipt["identity"]["source_hashes_unchanged"] is True
    assert receipt["static_admission"]["promotable_spatial_candidate"] is False
    assert receipt["phase"]["first_named_contact_source_sample"] is None
    assert receipt["phase"]["contact_at_expected_phase"] is False
    assert receipt["dynamics"]["run_count"] == 0
    assert receipt["dynamics"]["authorized"] is False

from pathlib import Path

from sim2claw.observable_registration_unilateral_push_contact import (
    build_unilateral_push_contact_receipt,
    load_unilateral_push_contact_contract,
)


def test_contract_is_fail_closed() -> None:
    contract = load_unilateral_push_contact_contract()
    assert contract["candidate"]["selection_used_task_contact_rows"] is True
    assert contract["candidate"]["globally_approved"] is False
    assert not any(contract["limits"].values())
    assert not any(contract["authority"].values())


def test_receipt_has_phase_correct_unilateral_contact(
    tmp_path: Path,
) -> None:
    receipt = build_unilateral_push_contact_receipt(
        output_directory=tmp_path
    )
    assert (
        receipt["status"]
        == "PASS_QUARANTINED_UNILATERAL_NAMED_CONTACT_NO_DYNAMICS"
    )
    assert receipt["evaluator"]["precontact_clear"] is True
    assert (
        receipt["evaluator"]["first_named_unilateral_contact_source_sample"]
        in range(228, 233)
    )
    assert receipt["evaluator"]["static_gate_passed"] is True
    assert receipt["actions_changed"] is False
    assert receipt["physics_integration_steps"] == 0
    assert receipt["dynamic_replays"] == 0
    assert receipt["global_mapping_approved"] is False
    assert receipt["transfer_claim"] is False

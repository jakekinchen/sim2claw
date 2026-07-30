from pathlib import Path

from sim2claw.contact_consequence_mechanism_discriminator import (
    build_contact_consequence_mechanism_discriminator,
    load_contact_consequence_mechanism_discriminator_contract,
)


def test_contract_requires_one_branch_or_insufficient() -> None:
    contract = load_contact_consequence_mechanism_discriminator_contract()
    assert contract["analysis"]["exactly_one_branch_or_insufficient"]
    assert not contract["analysis"]["terminal_task_outcome_allowed"]
    assert not contract["analysis"]["parameter_fit_allowed"]
    assert not contract["analysis"]["second_simulator_replay_allowed"]


def test_discriminator_fails_closed_without_physical_orientation(
    tmp_path: Path,
) -> None:
    receipt = build_contact_consequence_mechanism_discriminator(
        output_directory=tmp_path
    )
    assert receipt["status"] == "MECHANISM_NOT_IDENTIFIABLE"
    assert receipt["selected_branch"] is None
    assert len(receipt["branch_evaluations"]) == 4
    assert all(
        not branch["physical_discriminator_complete"]
        for branch in receipt["branch_evaluations"]
    )
    assert receipt["simulator_correction_allowed"] is False
    assert receipt["transfer_claim"] is False

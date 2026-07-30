from pathlib import Path

from sim2claw.observable_registration_contact_consequence_localization import (
    build_contact_consequence_localization_receipt,
    load_contact_consequence_localization_contract,
)


def test_contract_has_no_fit_or_external_authority() -> None:
    contract = load_contact_consequence_localization_contract()
    assert not any(contract["policy"].values())
    assert not any(contract["authority"].values())


def test_localization_finds_object_consequence_boundary(
    tmp_path: Path,
) -> None:
    receipt = build_contact_consequence_localization_receipt(
        output_directory=tmp_path
    )
    assert (
        receipt["status"]
        == "PASS_LOCALIZED_OBJECT_CONSEQUENCE_BLOCKED_IDENTIFIABILITY"
    )
    assert receipt["result"]["first_named_simulator_contact_sample"] == 231
    assert (
        receipt["result"][
            "first_simulator_planar_motion_over_1mm_sample"
        ]
        == 248
    )
    assert receipt["parameter_fit_allowed"] is False
    assert receipt["actions_changed"] is False
    assert receipt["global_mapping_approved"] is False
    assert receipt["transfer_claim"] is False

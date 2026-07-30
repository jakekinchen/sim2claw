from sim2claw.observable_registration_historical_mapping_composition import (
    build_historical_mapping_composition_receipt,
    load_historical_mapping_composition_contract,
)


def test_or16_is_static_and_quarantined(tmp_path) -> None:
    contract = load_historical_mapping_composition_contract()
    assert contract["frozen_mapping"]["refit_allowed"] is False
    first = build_historical_mapping_composition_receipt(
        output_directory=tmp_path / "a"
    )
    second = build_historical_mapping_composition_receipt(
        output_directory=tmp_path / "b"
    )
    assert first == second
    assert first["actions_changed"] is False
    assert first["mapping_refit"] is False
    assert first["physics_integration_steps"] == 0
    assert first["dynamic_replays"] == 0
    assert first["global_mapping_approved"] is False

from sim2claw.observable_registration_orientation_migrated_yaw import (
    build_orientation_migrated_yaw_receipt,
    load_orientation_migrated_yaw_contract,
)


def test_or17_is_frozen_static_only(tmp_path) -> None:
    contract = load_orientation_migrated_yaw_contract()
    assert contract["yaw_migration"]["fit_allowed"] is False
    first = build_orientation_migrated_yaw_receipt(output_directory=tmp_path / "a")
    second = build_orientation_migrated_yaw_receipt(output_directory=tmp_path / "b")
    assert first == second
    assert first["actions_changed"] is False
    assert first["yaw_fit"] is False
    assert first["physics_integration_steps"] == 0
    assert first["dynamic_replays"] == 0

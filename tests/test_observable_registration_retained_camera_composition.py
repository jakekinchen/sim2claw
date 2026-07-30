from __future__ import annotations

from sim2claw.observable_registration_retained_camera_composition import (
    build_retained_camera_composition_receipt,
    load_retained_camera_composition_contract,
)


def test_or15_contract_preserves_proof_boundaries() -> None:
    contract = load_retained_camera_composition_contract()
    assert contract["camera_cohort_policy"]["camera_refit_allowed"] is False
    assert contract["frozen_joint_candidate"]["refit_allowed"] is False
    assert contract["contact_phase_gate"]["dynamics_allowed"] is False
    assert not any(contract["authority"].values())


def test_or15_receipt_is_deterministic_and_static_only(tmp_path) -> None:
    first = build_retained_camera_composition_receipt(
        output_directory=tmp_path / "first"
    )
    second = build_retained_camera_composition_receipt(
        output_directory=tmp_path / "second"
    )
    assert first == second
    assert first["actions_changed"] is False
    assert first["joint_candidate_refit"] is False
    assert first["task_rows_used_for_fit"] == 0
    assert first["physics_integration_steps"] == 0
    assert first["dynamic_replays"] == 0
    assert first["promotion"]["global_mapping_approved"] is False

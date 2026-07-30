from __future__ import annotations

from pathlib import Path

from sim2claw.post_hackathon_home_workspace_metrology import (
    CONTRACT_PATH,
    build_metrology_receipt,
    load_metrology_contract,
)


def test_contract_binds_owner_metrology_without_dynamic_authority() -> None:
    contract, measurement = load_metrology_contract(CONTRACT_PATH)
    assert measurement["workspace"] == "post_hackathon_home_workspace"
    assert (
        measurement["board"]["outside_side_primary"]["value_m"] == 0.3937
    )
    assert measurement["board"]["thickness"]["value_m"] == 0.024
    assert contract["translation_fit"]["fit_yaw"] is False
    assert contract["translation_fit"]["fit_z"] is False
    assert contract["contact_phase_gate"]["dynamics_authorized"] is False
    assert not any(contract["authority"].values())


def test_owner_dimensions_verify_stl_and_fit_translation_only(
    tmp_path: Path,
) -> None:
    receipt = build_metrology_receipt(CONTRACT_PATH, tmp_path)
    assert receipt["stl_identity"]["identity_gate_passed"] is True
    assert receipt["stl_identity"]["scale_change_applied"] is False
    assert receipt["stl_identity"]["mesh_vertex_count"] > 1000
    dimensions = receipt["stl_identity"]["measurements"]
    assert abs(dimensions["front_tip_to_tip_width"]["stl_m"] - 0.065) < 0.003
    assert abs(dimensions["maximum_center_width"]["stl_m"] - 0.11) < 0.003
    assert abs(dimensions["rear_width"]["stl_m"] - 0.0855) < 0.003
    assert abs(dimensions["front_to_rear_length"]["stl_m"] - 0.086) < 0.003

    fit = receipt["translation_fit"]
    assert fit["yaw_fit_performed"] is False
    assert fit["rotation_gate_passed"] is False
    assert fit["global_mapping_approved"] is False
    assert fit["translation_gate_passed"] is True
    assert fit["standard_uncertainty_m"]["maximum"] <= 0.003
    assert abs(fit["translation_delta_table_xy_m"][0]) > 0.04
    assert abs(fit["translation_delta_table_xy_m"][1]) < 0.01


def test_candidate_updates_board_metrology_and_runs_no_dynamics(
    tmp_path: Path,
) -> None:
    receipt = build_metrology_receipt(CONTRACT_PATH, tmp_path)
    board = receipt["board_geometry"]
    assert board["candidate_outside_side_m"] == 0.3937
    assert board["candidate_playing_side_m"] == 0.3556
    assert abs(board["candidate_frame_width_m"] - 0.01905) < 1e-12
    assert board["candidate_thickness_m"] == 0.024
    assert board["orthogonal_consistency_gate_passed"] is True
    assert receipt["contact_phase"]["physics_integration_steps"] == 0
    assert receipt["contact_phase"]["dynamic_replays"] == 0
    assert receipt["contact_phase"]["dynamics_authorized"] is False
    sample = receipt["contact_phase"]["sample_232"]
    assert sample["midpoint_to_pawn_planar_distance_m"] < 0.03
    assert sample["midpoint_to_pawn_vector_m"][2] < -0.08
    assert receipt["fit_evidence"]["task_rows_used"] == 0
    assert receipt["fit_evidence"]["contact_rows_used"] == 0
    assert not any(receipt["authority"].values())

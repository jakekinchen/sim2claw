from __future__ import annotations

from pathlib import Path

import mujoco
import numpy as np

from sim2claw.post_hackathon_home_workspace_geometry_camera import (
    CONTRACT_PATH,
    build_geometry_camera_model,
    build_geometry_camera_receipt,
    load_geometry_camera_contract,
)


def test_contract_keeps_geometry_camera_successor_static() -> None:
    contract, measurement = load_geometry_camera_contract(CONTRACT_PATH)
    assert contract["stage_order"] == [
        "board_and_pawn_static_geometry",
        "camera_center_from_manual_ranges",
        "camera_orientation_from_retained_nonheldout_pixels",
    ]
    assert (
        measurement["board"]["square_side"]["selected_value_m"] == 0.0405
    )
    assert measurement["pawn"]["height"]["value_m"] == 0.034
    assert (
        measurement["logitech_camera"]["lens_height_above_desk"]["value_m"]
        == 0.305
    )
    assert not any(contract["authority"].values())


def test_board_pawn_and_camera_center_measurements_reconcile(
    tmp_path: Path,
) -> None:
    receipt = build_geometry_camera_receipt(CONTRACT_PATH, tmp_path)
    board = receipt["board_object_geometry"]
    assert board["playing_side_m"] == 0.324
    assert board["square_side_m"] == 0.0405
    assert abs(board["frame_width_m"] - 0.03485) < 1e-12
    assert board["border_consistency_gate_passed"] is True
    assert board["compiled_pawn"]["height_gate_passed"] is True
    assert abs(board["compiled_pawn"]["compiled_height_m"] - 0.034) < 1e-6

    center = receipt["camera"]["center"]
    assert abs(center["derived_planar_distance_m"] - 0.32) < 0.015
    assert center["planar_consistency_gate_passed"] is True
    assert (
        abs(
            receipt["camera"]["world_pose"]["height_above_desk_m"]
            - 0.305
        )
        < 1e-9
    )


def test_camera_candidate_compiles_without_dynamic_or_promotion_authority(
    tmp_path: Path,
) -> None:
    receipt = build_geometry_camera_receipt(CONTRACT_PATH, tmp_path)
    orientation = receipt["camera"]["retained_pixel_orientation"]
    assert orientation["orientation_diagnostic_gate_passed"] is True
    assert orientation["retrospective_nonheldout"] is True
    assert orientation["exact_intrinsics_approved"] is False
    assert orientation["mean_cross_cohort_validation_rms_px"] < 10.0
    assert receipt["camera"]["compiled_scene"]["pose_gate_passed"] is True
    assert receipt["contact_phase"]["physics_integration_steps"] == 0
    assert receipt["contact_phase"]["dynamic_replays"] == 0
    assert receipt["decision"]["canonical_scene_replaced"] is False
    assert receipt["decision"]["global_mapping_approved"] is False
    assert not any(receipt["authority"].values())

    scene_path = tmp_path / "derived_scene_config.json"
    model = build_geometry_camera_model(scene_path)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    camera_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_CAMERA, "workcell"
    )
    assert camera_id >= 0
    expected = np.asarray(
        receipt["camera"]["world_pose"]["camera_position_world_m"]
    )
    assert np.linalg.norm(data.cam_xpos[camera_id] - expected) < 1e-9

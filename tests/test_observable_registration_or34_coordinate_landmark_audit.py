from pathlib import Path

import numpy as np

from sim2claw.observable_registration_or34_coordinate_landmark_audit import (
    board_coordinate_to_scene_world,
    build_coordinate_landmark_audit,
    load_coordinate_landmark_audit_contract,
)


def test_contract_is_read_only_and_claim_limited() -> None:
    contract = load_coordinate_landmark_audit_contract()
    assert contract["audit"]["primary_coordinate_system"] == "board_file_rank_coordinates"
    assert contract["acceptance"]["mujoco_step_calls"] == 0
    assert not any(contract["claim_limits"].values())


def test_board_coordinate_transport_preserves_fractional_d1_offset() -> None:
    scene = Path("outputs/observable_registration_unilateral_push_contact_v1/derived_scene_config.json")
    world = board_coordinate_to_scene_world(
        np.asarray([3.568645477294922, 0.48760929703712463]), scene_path=scene
    )
    assert np.allclose(
        world,
        [-0.022827512874699283, 0.6200524179971307, 0.8088839412854517],
        atol=1e-12,
    )


def test_audit_confirms_mismatch_without_dynamics(tmp_path: Path) -> None:
    receipt = build_coordinate_landmark_audit(output_directory=tmp_path / "audit")
    assert receipt["status"] == "PASS_COORDINATE_FRAME_MISMATCH_CONFIRMED"
    assert receipt["execution"]["mujoco_step_calls"] == 0
    assert receipt["coordinate_audit"]["legacy_d1_planar_error_m"] > 0.014
    assert receipt["coordinate_audit"]["transported_d1_planar_error_m"] < 0.003
    assert receipt["coordinate_audit"]["required_initial_xy_change_m"] > 0.013
    assert receipt["landmark_audit"]["body_to_free_joint_translation_error_m"] < 1e-12
    assert all(receipt["gates"].values())

from __future__ import annotations

import math

import numpy as np

from sim2claw.observable_registration_factor_isolation import (
    apply_gripper_local_se3,
    apply_world_se3,
    build_factor_isolation_receipt,
    evaluate_factor_isolation,
    load_factor_isolation_contract,
    table_delta_to_world,
)


def test_contract_is_static_diagnostic_only_and_has_no_authority() -> None:
    contract = load_factor_isolation_contract()
    assert [item["block_id"] for item in contract["factor_blocks"]] == [
        "base_b6",
        "joint_j2",
        "tool_w6",
    ]
    assert contract["split"]["promotion_grade_heldout"] is False
    assert contract["split"]["sealed_task_episode_used"] is False
    assert contract["promotion"]["canonical_parameter_update_allowed"] is False
    assert contract["promotion"]["dynamic_replay_allowed"] is False
    assert not any(contract["authority"].values())
    assert all(
        token not in binding["path"].lower()
        for binding in contract["sources"].values()
        for token in ("d1-to-d2", "c6", "rp04", "action", "outcome")
    )


def test_table_frame_signs_match_left_and_backward_quadrant() -> None:
    yaw_degrees = -20.388574
    world = table_delta_to_world(
        np.asarray([0.11586409, 0.11881857, 0.04583097]),
        table_yaw_degrees=yaw_degrees,
    )
    np.testing.assert_allclose(
        world,
        np.asarray([0.15, 0.07100944, 0.04583097]),
        atol=1e-8,
    )
    assert world[0] > 0.0
    assert world[1] > 0.0


def test_world_and_gripper_se3_helpers_are_rigid_and_deterministic() -> None:
    points = np.asarray(
        [[[0.0, 0.0, 0.0], [0.02, 0.0, 0.0]]], dtype=np.float64
    )
    base_values = np.asarray(
        [0.01, 0.02, 0.03, math.radians(1.0), 0.0, 0.0]
    )
    first = apply_world_se3(
        points, base_values, table_yaw_degrees=-20.388574
    )
    second = apply_world_se3(
        points, base_values, table_yaw_degrees=-20.388574
    )
    np.testing.assert_allclose(first, second, atol=0.0)
    np.testing.assert_allclose(
        np.linalg.norm(first[:, 1] - first[:, 0], axis=1),
        [0.02],
        atol=1e-12,
    )
    pivot = np.asarray([0.2, 0.3, 0.4])
    pure_roll = apply_world_se3(
        np.asarray([[pivot, pivot + np.asarray([0.0, 0.0, 0.1])]]),
        np.asarray([0.0, 0.0, 0.0, math.radians(2.0), 0.0, 0.0]),
        table_yaw_degrees=-20.388574,
        pivot_world=pivot,
    )
    np.testing.assert_allclose(pure_roll[0, 0], pivot, atol=1e-12)

    origins = np.asarray([[0.1, 0.2, 0.3]])
    rotations = np.asarray([np.eye(3)])
    tool = apply_gripper_local_se3(
        points + origins[:, None, :],
        origins,
        rotations,
        np.asarray([0.01, -0.02, 0.03, 0.0, 0.0, math.radians(5.0)]),
    )
    np.testing.assert_allclose(
        np.linalg.norm(tool[:, 1] - tool[:, 0], axis=1),
        [0.02],
        atol=1e-12,
    )


def test_retained_data_factor_isolation_is_deterministic_and_fail_closed(
    tmp_path,
) -> None:
    contract = load_factor_isolation_contract()
    receipt = evaluate_factor_isolation(contract)
    assert receipt["source_roles"]["fit_pose_count"] == 6
    assert receipt["source_roles"]["known_outcome_validation_pose_count"] == 4
    assert receipt["source_roles"]["promotion_grade_heldout_pose_count"] == 0
    assert receipt["canonical_parameter_update_authorized"] is False
    assert receipt["dynamic_replay_authorized"] is False
    assert receipt["global_mapping_approved"] is False
    assert receipt["result"] == "CONFOUNDED_NO_PROMOTION"
    assert receipt["camera_results"]["or1"]["camera_prerequisite_passed"] is False
    assert receipt["camera_results"]["or1"]["admissible_winner"] is None
    assert (
        receipt["camera_results"]["or1"]["numeric_argmin_status"]
        == "numeric_argmin_inadmissible_camera_prerequisite"
    )
    assert all(
        branch["parameter_count"] in {2, 6}
        for camera in receipt["camera_results"].values()
        for branch in camera["branches"].values()
    )
    assert all(
        branch["known_outcome_validation"]["pristine_heldout"] is False
        and branch["known_outcome_validation"]["promotion_eligible"] is False
        for camera in receipt["camera_results"].values()
        for branch in camera["branches"].values()
    )
    first = build_factor_isolation_receipt(
        output_path=tmp_path / "first.json"
    )
    second = build_factor_isolation_receipt(
        output_path=tmp_path / "second.json"
    )
    assert first == second
    assert first["artifact_sha256"] == second["artifact_sha256"]

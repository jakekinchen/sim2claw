from __future__ import annotations

from sim2claw.realized_action_contact_identifiability import (
    load_contract,
    observable_flags,
)


def test_contract_rejects_missing_contact_evidence() -> None:
    contract = load_contract()
    assert len(contract["candidate_dimensions"]) == 5
    assert all(contract["rules"].values())
    assert not any(contract["authority"].values())


def test_motor_current_and_grasp_marker_are_not_contact_force() -> None:
    rows = [
        {
            "available_motor_current_raw": {"elbow_flex": 4.0},
            "gripper_contact_hold": True,
            "gripper_contact_deflection": True,
        }
    ]
    flags = observable_flags(rows)
    assert flags["known_contact_or_applied_force"] is False
    assert flags["per_sample_contact_state"] is False
    assert flags["metric_contact_deformation"] is False


def test_metric_paths_require_multiple_rows() -> None:
    one = observable_flags([{"selected_piece_pose_world": [0.0, 0.0, 0.0]}])
    two = observable_flags(
        [
            {"selected_piece_pose_world": [0.0, 0.0, 0.0]},
            {"selected_piece_pose_world": [0.1, 0.0, 0.0]},
        ]
    )
    assert one["metric_object_pose_path"] is False
    assert two["metric_object_pose_path"] is True

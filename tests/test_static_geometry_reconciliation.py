from __future__ import annotations

from sim2claw.static_geometry_reconciliation import (
    load_geometry_contract,
    reconcile_geometry,
)


def test_geometry_contract_preserves_channel_boundaries() -> None:
    contract = load_geometry_contract()
    assert contract["rules"]["preserve_accepted_task_plane"] is True
    assert contract["rules"]["joint_camera_robot_object_refit_allowed"] is False
    assert contract["rules"]["camera_pose_may_absorb_joint_or_link_error"] is False
    assert not any(contract["authority"].values())


def test_live_reconciliation_is_deterministic_and_honest() -> None:
    contract = load_geometry_contract()
    first = reconcile_geometry(contract)
    second = reconcile_geometry(contract)
    assert first == second
    assert first["summary"] == {
        "accepted_task_plane_preserved": True,
        "initial_pawn_within_frozen_gate": True,
        "global_physical_model_mapping_approved": False,
        "joint_refit_performed": False,
        "result": "PARTIAL_ACCEPTED_WITH_ROBOT_AND_FLOOR_GAPS",
    }
    channels = first["channels"]
    assert channels["task_plane_board_corners"]["status"] == "accepted"
    assert channels["pawn_base_endpoints"]["status"] == "accepted_endpoint_only"
    assert channels["fixed_base_robot"]["status"] == (
        "rejected_unreliable_constraint"
    )
    assert channels["articulated_keypoint_differential"]["status"] == (
        "rejected_partial_proximal_only"
    )
    assert channels["robot_silhouette"]["status"] == (
        "retrospective_numeric_pass_not_promotable"
    )
    assert channels["floor_and_support_plane"]["status"] == (
        "metric_residual_unavailable"
    )

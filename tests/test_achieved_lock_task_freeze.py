from __future__ import annotations

from sim2claw.achieved_lock_task_freeze import _achieved_seed


def test_achieved_seed_uses_torque_on_pose_and_held_elbow() -> None:
    receipt = {
        "passed": True,
        "physical_task_attempts": 0,
        "pawn_contact": False,
        "failure": None,
        "gateway_open": {
            "setup_command_anchor_degrees": [5, -85, 102, -12, -103, 2]
        },
        "ladder": {
            "outcome": "deep_request_success",
            "final_elbow_degrees": 92.44,
            "hold": {"passed": True},
        },
    }
    assert _achieved_seed(receipt) == [5, -85, 92.44, -12, -103, 2]

import pytest

from sim2claw.bidirectional_q06_scene_gate import evaluate


def test_all_preregistered_cases_fail_frozen_exclusion_clearance() -> None:
    receipt = evaluate()
    assert receipt["camera_availability"] == {
        "c922_rgb": True,
        "d405_color_rgb": True,
        "pi_imx708_rgb": True,
        "metric_depth_used": False,
    }
    assert len(receipt["case_results"]) == 10
    assert receipt["admitted_case_ids"] == []
    assert all(
        result["minimum_center_to_route_clearance_mm"] == pytest.approx(44.45)
        for result in receipt["case_results"]
    )
    assert all(result["admitted"] is False for result in receipt["case_results"])
    assert receipt["robot_gateway_constructed"] is False
    assert receipt["robot_motion_commands"] == 0
    assert receipt["counted_physical_attempts"] == 0
    assert receipt["status"] == "terminal_safety_boundary_no_admissible_case"

import math

import pytest

from sim2claw.bidirectional_off_source_feasibility_audit import evaluate


def test_frozen_two_square_exclusion_gate_was_structurally_infeasible() -> None:
    receipt = evaluate()
    geometry = receipt["geometry"]
    assert receipt["status"] == "preregistered_contract_structurally_infeasible"
    assert receipt["evaluator"]["mutated"] is False
    assert geometry["required_route_clearance_mm"] == pytest.approx(88.9)
    assert geometry["global_route_clearance_upper_bound_mm"] == pytest.approx(
        math.sqrt(2.0) * 44.45
    )
    assert geometry["contract_feasible"] is False
    assert len(geometry["source_bounds"]) == 16
    assert all(
        row["route_clearance_upper_bound_mm"] < 88.9
        for row in geometry["source_bounds"]
    )
    assert receipt["detected_before_q06_possible"] is True
    assert receipt["new_action_compiled"] is False
    assert receipt["robot_motion_commands"] == 0
    assert receipt["counted_physical_attempts"] == 0


def test_far_side_distance_rows_are_diagnostic_not_reachability_claims() -> None:
    receipt = evaluate()
    rows = receipt["far_side_planar_base_distance_diagnostic"]
    assert [row["case_id"] for row in rows] == [
        "S03_B7_B8",
        "S04_D7_D8",
        "S05_F7_F8",
    ]
    assert [row["planar_base_distance_m"] for row in rows] == pytest.approx(
        [0.4780915013609902, 0.485519155172378, 0.5086183602712289]
    )
    assert all(row["reachability_authority"] is False for row in rows)
    assert (
        receipt["far_side_reachability_conclusion"]
        == "not_adjudicated_by_this_distance_only_audit"
    )

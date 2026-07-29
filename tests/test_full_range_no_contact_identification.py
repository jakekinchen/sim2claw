from __future__ import annotations

import json
from pathlib import Path

from sim2claw.full_range_no_contact_identification import (
    compile_identification_route,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT / "configs/evaluations/full_range_no_contact_identification_v1.json"
)
CONTRACT_V2 = (
    ROOT / "configs/evaluations/full_range_no_contact_identification_v2.json"
)


def test_frozen_route_is_full_range_and_dual_scene_contact_free(
    tmp_path: Path,
) -> None:
    receipt = compile_identification_route(CONTRACT, tmp_path / "static")
    assert receipt["passed"] is True
    assert receipt["physical_route"]["shape"] == [1160, 6]
    assert receipt["minimum_elbow_degrees"] <= -0.8638219165683483
    assert receipt["registered_scene"]["passed"] is True
    assert receipt["uncorrected_scene"]["passed"] is True
    assert (
        receipt["registered_clearance"]["minimum_overall_clearance_m"]
        >= 0.075
    )
    assert (
        receipt["uncorrected_clearance"]["minimum_overall_clearance_m"]
        >= 0.075
    )
    assert receipt["physical_motion"] is False
    assert receipt["physical_task_attempts"] == 0
    assert receipt["mapping_approved"] is False


def test_contract_has_no_hardware_or_task_authority() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["route"]["contact_intent"] is False
    assert contract["route"]["task_execution"] is False
    assert contract["authority"]["camera"] is False
    assert contract["authority"]["gateway"] is False
    assert contract["authority"]["serial"] is False
    assert contract["authority"]["physical_motion"] is False
    assert contract["authority"]["physical_task_attempt"] is False
    assert contract["authority"]["mapping_approval"] is False


def test_reachable_pan_successor_remains_full_range_and_clear(
    tmp_path: Path,
) -> None:
    receipt = compile_identification_route(
        CONTRACT_V2, tmp_path / "static-v2"
    )
    assert receipt["passed"] is True
    assert receipt["physical_route"]["shape"] == [1105, 6]
    assert receipt["route_transform"]["shoulder_pan_target_degrees"] == -60.0
    assert receipt["minimum_elbow_degrees"] <= -0.8638219165683483
    assert (
        receipt["uncorrected_clearance"]["minimum_overall_clearance_m"]
        >= 0.07
    )
    assert receipt["physical_task_attempts"] == 0
    assert receipt["mapping_approved"] is False

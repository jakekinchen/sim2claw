from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/evaluations/observable_registration_board_grid_camera_sensor_roll_successor_v1.json"


def test_contract_adds_only_shared_sensor_roll_to_or81_camera_family() -> None:
    contract = json.loads(CONTRACT.read_text())
    or81 = json.loads((ROOT / contract["sources"]["or81_contract"]["path"]).read_text())
    assert contract["camera_family"]["parameter_order"][:-1] == or81["camera_family"]["parameter_order"]
    assert contract["camera_family"]["parameter_order"][-1] == "optical_axis_sensor_roll_degrees"
    assert contract["camera_family"]["added_parameter_count"] == 1
    assert contract["camera_family"]["one_shared_vector_required"] is True
    for key in contract["unchanged_or81_sections"]:
        assert key in or81


def test_contract_prohibits_other_camera_and_split_expansions() -> None:
    contract = json.loads(CONTRACT.read_text())
    boundary = contract["resource_boundary"]
    assert boundary["camera_fits_allowed"] == 1
    assert boundary["principal_point_fits_allowed"] == 0
    assert boundary["distortion_fits_allowed"] == 0
    assert boundary["appearance_fits_allowed"] == 0
    assert boundary["time_fits_allowed"] == 0
    assert boundary["state_or_physics_fits_allowed"] == 0
    assert boundary["validation_reads_allowed"] == 0
    assert boundary["evaluator_heldout_reads_allowed"] == 0

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = (
    ROOT
    / "configs/evaluations/directional_displacement_static_base_contact_offset_compensated_v4.json"
)
CONTRACT = (
    ROOT
    / "configs/evaluations/reachable_lock_80_stroke_66_contact_offset_compensated_static_v1.json"
)


def test_contact_offset_compensation_is_finite_and_fail_closed() -> None:
    base = json.loads(BASE.read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert base["grid"]["contact_heights_m"] == [
        0.0225,
        0.025,
        0.0275,
        0.03,
    ]
    assert base["grid"]["contact_offset_compensation_m"] == 0.0125
    assert base["gates"]["minimum_first_contact_height_m"] == 0.035
    assert base["grid"]["maximum_total_cells"] == 528
    assert base["family_universe"]["expected_postquarantine_count"] == 44
    assert base["quarantine"]["exact_count"] == 8
    assert base["grid"]["stroke_m"] == 0.066
    assert contract["live_seed"]["locked_value_degrees"] == 80.0
    assert all(contract["unchanged_from_base"].values())
    assert contract["authority"]["dynamic_simulation"] is False
    assert contract["authority"]["physical_motion"] is False
    assert contract["authority"]["physical_task_attempt"] is False

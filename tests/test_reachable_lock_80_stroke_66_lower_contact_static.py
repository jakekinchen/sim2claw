from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = (
    ROOT
    / "configs/evaluations/directional_displacement_static_base_lower_contact_v3.json"
)
CONTRACT = (
    ROOT
    / "configs/evaluations/reachable_lock_80_stroke_66_lower_contact_static_v1.json"
)


def test_lower_contact_successor_changes_only_declared_geometry_axis() -> None:
    base = json.loads(BASE.read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert base["grid"]["contact_heights_m"] == [
        0.035,
        0.0375,
        0.04,
        0.0425,
    ]
    assert base["grid"]["maximum_total_cells"] == 552
    assert base["family_universe"]["expected_postquarantine_count"] == 46
    assert base["quarantine"]["exact_count"] == 6
    assert base["grid"]["stroke_m"] == 0.066
    assert contract["live_seed"]["locked_value_degrees"] == 80.0
    assert all(contract["unchanged_from_base"].values())
    assert contract["authority"]["dynamic_simulation"] is False
    assert contract["authority"]["physical_motion"] is False
    assert contract["authority"]["physical_task_attempt"] is False

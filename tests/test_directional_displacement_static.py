from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_directional_displacement_contract_is_static_and_distinct() -> None:
    base = json.loads(
        (
            ROOT
            / "configs/evaluations/directional_displacement_static_base_v1.json"
        ).read_text(encoding="utf-8")
    )
    wrapper = json.loads(
        (
            ROOT / "configs/evaluations/directional_displacement_static_v1.json"
        ).read_text(encoding="utf-8")
    )
    assert base["grid"]["contact_heights_m"] == [0.045, 0.05, 0.055, 0.06]
    assert base["gates"]["minimum_first_contact_height_m"] == 0.035
    assert base["gates"]["maximum_first_contact_height_m"] == 0.065
    assert base["selection"]["selected_count"] == 2
    assert base["selection"]["minimum_per_direction"] == 1
    assert base["selection"]["dynamic_outcome_used"] is False
    assert wrapper["live_seed"]["locked_joint_name"] == "elbow_flex"
    assert all(
        not value
        for name, value in wrapper["authority"].items()
        if name not in {"model_loading", "static_simulation"}
    )
    assert "not straight sliding push" in wrapper["claim_boundary"].lower()

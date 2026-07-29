from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "configs/evaluations/reachable_lock_80_stroke_66_lower_contact_temporal_v1.json"
)


def test_lower_contact_temporal_binds_exact_static_selected_pair() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert len(contract["cases"]) == 2
    assert {row["direction"] for row in contract["cases"]} == {
        "REAL_TO_SIM",
        "SIM_TO_REAL",
    }
    assert {
        row["action_sha256"] for row in contract["cases"]
    } == {
        "20a2357f25db6b548c5b1194bf62401aa7c363ff518025b69a6298bd39cecf87",
        "cd86a98d379da3fb645fcd2147edc0e325c7a75940caa325d1da731491f700f8",
    }
    assert all(contract["unchanged_from_base"].values())
    assert contract["live_seed"]["follower_position_degrees"][2] == 80.0
    assert "lower_contact" in contract["proof_class"]

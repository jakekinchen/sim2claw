from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT / "configs/evaluations/reachable_lock_80_task_temporal_v1.json"
)


def test_reachable_lock_temporal_contract_is_two_direction_frozen() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert len(contract["cases"]) == 2
    assert {row["direction"] for row in contract["cases"]} == {
        "REAL_TO_SIM",
        "SIM_TO_REAL",
    }
    assert {
        row["action_sha256"] for row in contract["cases"]
    } == {
        "fd9fcd487ede52b40dbea30eeb7e830d99d96c21179dfe586484eef93c92c2bc",
        "b96e7bfb7b9d4f7a84c3acfedfb326ef7eb7dc5d645a672cd1d966e39482f477",
    }
    assert all(contract["unchanged_from_base"].values())
    assert contract["live_seed"]["follower_position_degrees"][2] == 80.0

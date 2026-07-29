from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "configs/evaluations/reachable_lock_80_stroke_66_temporal_v1.json"
)


def test_66mm_temporal_contract_binds_exact_static_selected_pair() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert len(contract["cases"]) == 2
    assert {row["direction"] for row in contract["cases"]} == {
        "REAL_TO_SIM",
        "SIM_TO_REAL",
    }
    assert {
        row["action_sha256"] for row in contract["cases"]
    } == {
        "8922b58f74af7aacf2afb5cac36fd5d29cdac0732285ce744d9c9721351cfe40",
        "9d6ff6126111d9940fd87c86fbc2139ad20433a1b0da3b12962e9a16c3071133",
    }
    assert all(contract["unchanged_from_base"].values())
    assert contract["live_seed"]["follower_position_degrees"][2] == 80.0
    assert "66mm" in contract["proof_class"]

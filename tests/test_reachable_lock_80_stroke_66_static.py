from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "configs/evaluations/reachable_lock_80_stroke_66_static_v1.json"
)


def test_66mm_successor_changes_only_declared_static_mechanism() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["live_seed"]["locked_value_degrees"] == 80.0
    assert contract["unchanged_from_base"][
        "only_stroke_changes_from_40mm_to_66mm"
    ] is True
    assert all(contract["unchanged_from_base"].values())
    assert contract["authority"]["dynamic_simulation"] is False
    assert contract["authority"]["physical_motion"] is False
    assert contract["authority"]["physical_task_attempt"] is False

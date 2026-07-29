from __future__ import annotations

import json
from pathlib import Path

from sim2claw.reachable_lock_task_certificate import enumerate_and_freeze


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT / "configs/evaluations/reachable_lock_task_certificate_v1.json"
)


def test_reachable_lock_static_screen_has_frozen_denominator() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["lock_grid_degrees"] == [85.0, 80.0, 77.5]
    assert contract["selection"]["preferred_lock_degrees"] == 80.0
    assert contract["selection"]["grid_expansion_after_run"] is False


def test_contract_preserves_false_hardware_authority() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["selection"]["dynamic_outcomes_used"] is False
    assert contract["selection"]["physical_task_outcomes_used"] is False
    assert contract["authority"]["dynamic_simulation"] is False
    assert contract["authority"]["physical_motion"] is False
    assert contract["authority"]["physical_task_attempt"] is False
    assert contract["authority"]["mapping_approval"] is False

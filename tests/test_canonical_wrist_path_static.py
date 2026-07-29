from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = Path("configs/evaluations/canonical_wrist_path_static_v2.json")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolved_contract() -> tuple[dict, dict]:
    successor = json.loads((ROOT / CONTRACT).read_text(encoding="utf-8"))
    predecessor = successor["predecessor_contract"]
    assert _sha(ROOT / predecessor["path"]) == predecessor["sha256"]
    assert all(successor["unchanged_from_v1"].values())
    for key in ("preexecution_closeout", "implementation"):
        binding = successor[key]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    return successor, json.loads(
        (ROOT / predecessor["path"]).read_text(encoding="utf-8")
    )


def test_canonical_wrist_path_contract_is_bounded_and_current() -> None:
    _, contract = _resolved_contract()
    assert contract["family_universe"]["prequarantine_count"] == 52
    assert contract["family_universe"]["expected_postquarantine_count"] == 48
    assert contract["grid"]["maximum_total_cells"] == 288
    assert contract["grid"]["finite_and_nonexpandable_after_freeze"]
    assert contract["selection"]["minimum_per_direction"] == 2
    assert not contract["selection"]["dynamic_outcome_used"]
    assert contract["gates"]["future_minimum_signed_progress_mm"] == 36.025
    assert (
        contract["gates"]["future_maximum_selected_vertical_rise_mm"] == 2.0
    )
    for name, binding in contract["inputs"].items():
        if name == "implementation":
            continue
        assert _sha(ROOT / binding["path"]) == binding["sha256"]


def test_canonical_wrist_path_contract_has_no_physical_authority() -> None:
    _, contract = _resolved_contract()
    assert contract["authority"]["model_loading"]
    assert contract["authority"]["static_simulation"]
    assert not any(
        value
        for name, value in contract["authority"].items()
        if name not in {"model_loading", "static_simulation"}
    )
    source = (
        ROOT / "src/sim2claw/canonical_wrist_path_static.py"
    ).read_text(encoding="utf-8")
    assert "serial" not in source.lower()
    assert "dynamixel" not in source.lower()

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_action_geometry_successor_authorization_v1.json"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_action_geometry_authorization_quarantines_outcomes_and_is_static_design_only() -> None:
    authorization = json.loads(AUTHORIZATION.read_text(encoding="utf-8"))
    for binding in authorization["immutable_predecessors"].values():
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert authorization["quarantine"]["case_ids"] == [
        "brown_pawn_b1__b1_b2",
        "brown_pawn_a2__a2_a1",
        "brown_pawn_a2__a2_a3",
        "brown_pawn_e2__e2_e3",
    ]
    assert authorization["quarantine"]["exact_count"] == 4
    assert authorization["quarantine"]["permitted_use"] == (
        "read_only_diagnostics_and_exact_quarantine_only"
    )
    invariants = authorization["frozen_invariants"]
    assert invariants["closed_jaw_rad"] == -0.1727003294848389
    assert invariants["sample_hz"] == 40.0
    assert invariants["minimum_signed_progress_mm"] == 36.025
    assert invariants["minimum_distinct_families_per_direction"] == 2
    assert authorization["authority"]["static_design"] is True
    assert not any(
        value
        for key, value in authorization["authority"].items()
        if key != "static_design"
    )

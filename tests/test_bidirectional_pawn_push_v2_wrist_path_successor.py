from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_wrist_path_successor_authorization_v1.json"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_wrist_path_authorization_preserves_quarantine_gates_and_false_authority() -> None:
    authorization = json.loads(AUTHORIZATION.read_text(encoding="utf-8"))
    for binding in authorization["immutable_predecessors"].values():
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert authorization["quarantine"]["case_ids"] == [
        "brown_pawn_b1__b1_b2",
        "brown_pawn_a2__a2_a1",
        "brown_pawn_a2__a2_a3",
        "brown_pawn_e2__e2_e3",
    ]
    assert authorization["v05_tk_selected_static_cases"][
        "dynamic_outcomes_observed"
    ] is False
    assert authorization["authorized_static_design"][
        "preserved_dimensions"
    ] == {
        "contact_center_offsets_m": [0.016, 0.019, 0.022],
        "contact_heights_m": [0.018, 0.024, 0.03],
        "stroke_lengths_m": [0.09, 0.105, 0.12],
    }
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

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "configs/evaluations/bidirectional_pawn_push_v2_sim_rehearsal_v1.json"
)


def test_v05_rehearsal_is_bounded_prospective_and_non_authoritative() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["status"] == (
        "preregistered_before_any_v05_nominal_task_outcome"
    )
    assert len(contract["cases"]) == 8
    assert contract["grid"]["stroke_lengths_m"] == [0.09, 0.105, 0.12]
    assert contract["grid"]["contact_heights_m"] == [0.018, 0.024, 0.03]
    assert len(contract["robustness_variants"]) == 5
    assert not any(contract["authority"].values())
    assert contract["selection_rule"]["physical_task_outcomes_used"] is False


def test_v05_rehearsal_implementation_is_hash_frozen() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    implementation = ROOT / contract["implementation"]["path"]
    digest = hashlib.sha256(implementation.read_bytes()).hexdigest()
    assert digest == contract["implementation"]["sha256"]

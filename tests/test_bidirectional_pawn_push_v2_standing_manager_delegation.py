from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DELEGATION = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_standing_manager_delegation_v1.json"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_standing_delegation_preserves_campaign_and_nondelegable_gates() -> None:
    delegation = json.loads(DELEGATION.read_text(encoding="utf-8"))
    predecessor = delegation["immutable_predecessor"]
    assert _sha(ROOT / predecessor["path"]) == predecessor["sha256"]
    assert delegation["initial_successor"]["milestone_id"] == "V05-TX"
    invariants = delegation["campaign_invariants"]
    assert invariants["minimum_signed_progress_mm"] == 36.025
    assert (
        invariants[
            "minimum_distinct_families_per_direction_before_v06_or_physical"
        ]
        == 2
    )
    assert invariants["predecessor_verdicts_immutable"] is True
    assert invariants["dynamically_evaluated_cases_quarantined"] is True
    assert invariants["contract_and_hashes_frozen_before_outcomes"] is True
    assert invariants["one_bounded_execution_per_freeze"] is True
    assert invariants["no_post_outcome_expansion_of_frozen_grid"] is True
    assert delegation["brev_policy"] == (
        "Brev remains empty unless separately explicitly authorized."
    )
    authority = delegation["authority"]
    assert authority["manager_authorization_receipts"] is True
    assert authority["successor_design"] is True
    assert authority["physical_packet_authorization_after_all_gates"] is True
    for key in (
        "credentials",
        "paid_compute",
        "destructive_actions",
        "public_external_actions",
        "unreviewed_physical_motion",
        "manual_user_intervention",
        "gate_weakening",
    ):
        assert authority[key] is False

from __future__ import annotations

import hashlib
import json

from sim2claw.paths import REPO_ROOT


DECISION = (
    REPO_ROOT
    / "configs/decisions/canonical_seeded_action_static_v1_defect_closeout.json"
)


def test_v1_apparent_pass_is_invalidated_before_dynamics() -> None:
    decision = json.loads(DECISION.read_text(encoding="utf-8"))
    receipt_path = REPO_ROOT / decision["receipt"]["path"]
    assert (
        hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        == decision["receipt"]["sha256"]
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "canonical_seeded_action_static_pass"
    assert min(
        row["compile"]["minimum_model_joint_margin_rad"]
        for row in receipt["selected"]
    ) < 0.0
    assert decision["decision"]["v1_actions_admitted"] is False
    assert decision["decision"]["v1_actions_may_enter_dynamic_replay"] is False
    assert decision["authority"]["dynamic_simulation"] is False
    assert decision["authority"]["physical_motion"] is False

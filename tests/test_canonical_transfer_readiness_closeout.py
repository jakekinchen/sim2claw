from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sim2claw.paths import REPO_ROOT


DECISION = (
    REPO_ROOT
    / "configs/decisions/canonical_transfer_readiness_closeout_v1.json"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_closeout_binds_reject_and_preserves_physical_ceiling() -> None:
    decision = json.loads(DECISION.read_text(encoding="utf-8"))
    receipt = REPO_ROOT / decision["receipt"]["path"]
    assert _sha(receipt) == decision["receipt"]["sha256"]
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["status"] == "canonical_transfer_readiness_reject"
    assert payload["passed"] is False
    assert payload["blockers"] == decision["blockers"]
    assert decision["authority"]["fresh_canonical_compiler"] is True
    assert decision["authority"]["static_simulator_screen"] is True
    for key in (
        "dynamic_simulator_replay",
        "camera_open",
        "gateway",
        "serial",
        "physical_packet",
        "physical_motion",
        "task_attempt",
        "transfer_claim",
    ):
        assert decision["authority"][key] is False

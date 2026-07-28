from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_temporal_jaw_successor_authorization_v1.json"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_jaw_successor_authorization_is_exact_and_nonphysical() -> None:
    authorization = json.loads(
        AUTHORIZATION.read_text(encoding="utf-8")
    )
    for binding in authorization["immutable_predecessors"].values():
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    for binding in authorization["jaw_target_provenance"].values():
        if isinstance(binding, dict):
            assert _sha(ROOT / binding["path"]) == binding["sha256"]
    identity = authorization["successor_action_identity"]
    assert identity["predecessor_closed_jaw_rad"] == -0.174533
    assert identity["successor_closed_jaw_rad"] == -0.1727003294848389
    assert identity["only_changed_column"] == "gripper"
    assert "C8-to-A6 action transplant" in identity["forbidden"]
    assert authorization["authority"]["static_simulation"] is True
    assert not any(
        value
        for key, value in authorization["authority"].items()
        if key != "static_simulation"
    )

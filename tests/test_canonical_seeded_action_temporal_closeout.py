from __future__ import annotations

import hashlib
import json

from sim2claw.observable_episode import validate_episode
from sim2claw.paths import REPO_ROOT


CLOSEOUT = (
    REPO_ROOT
    / "configs/decisions/canonical_seeded_action_temporal_v2_closeout.json"
)


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_official_temporal_reject_and_episode_inventory_are_bound() -> None:
    closeout = json.loads(CLOSEOUT.read_text(encoding="utf-8"))
    receipt_path = REPO_ROOT / closeout["receipt"]["path"]
    assert _sha(receipt_path) == closeout["receipt"]["sha256"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "canonical_seeded_action_temporal_reject"
    assert receipt["direction_counts"] == {
        "REAL_TO_SIM": 0,
        "SIM_TO_REAL": 0,
    }
    assert len(receipt["results"]) == 4
    episodes = [
        variant["observable_episode"]
        for case in receipt["results"]
        for path in case["plant_paths"]
        for variant in path["robustness"]
    ]
    assert len(episodes) == 40
    for binding in episodes:
        path = REPO_ROOT / binding["path"]
        assert _sha(path) == binding["sha256"]
        validate_episode(json.loads(path.read_text(encoding="utf-8")))


def test_temporal_negative_preserves_action_and_authority_boundaries() -> None:
    closeout = json.loads(CLOSEOUT.read_text(encoding="utf-8"))
    assert closeout["result"]["official_execution_count"] == 1
    assert closeout["result"]["task_outcome_check_pass_counts_of_40"][
        "no_lift"
    ] == 0
    assert closeout["action_integrity"][
        "requested_hash_matches_freeze_paths"
    ] == "8/8"
    assert (
        closeout["action_integrity"][
            "row_zero_maximum_absolute_roundtrip_delta_degrees"
        ]
        < 1e-12
    )
    assert not any(closeout["authority"].values())

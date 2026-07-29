from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sim2claw.observable_episode import validate_episode


ROOT = Path(__file__).resolve().parents[1]
CLOSEOUT = Path(
    "configs/decisions/canonical_proxy_contact_temporal_v3_closeout.json"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_proxy_contact_v3_closeout_binds_receipt_and_episodes() -> None:
    closeout = json.loads((ROOT / CLOSEOUT).read_text(encoding="utf-8"))
    receipt_path = ROOT / closeout["receipt"]["path"]
    assert _sha(receipt_path) == closeout["receipt"]["sha256"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["schema_version"] == (
        "sim2claw.canonical_proxy_contact_temporal_receipt.v1"
    )
    assert receipt["status"] == "canonical_seeded_action_temporal_reject"
    assert receipt["direction_counts"] == {
        "REAL_TO_SIM": 0,
        "SIM_TO_REAL": 0,
    }
    assert not receipt["physical_motion"]
    assert receipt["physical_task_attempts"] == 0
    episodes = []
    for case in receipt["results"]:
        for path in case["plant_paths"]:
            for variant in path["robustness"]:
                binding = variant["observable_episode"]
                episode_path = ROOT / binding["path"]
                assert _sha(episode_path) == binding["sha256"]
                episodes.append(
                    validate_episode(
                        json.loads(episode_path.read_text(encoding="utf-8"))
                    )
                )
    assert len(episodes) == 40


def test_proxy_contact_closeout_preserves_false_authority() -> None:
    closeout = json.loads((ROOT / CLOSEOUT).read_text(encoding="utf-8"))
    assert closeout["result"]["direction_counts"] == {
        "REAL_TO_SIM": 0,
        "SIM_TO_REAL": 0,
    }
    assert not any(closeout["authority"].values())
    assert (
        closeout["comparison_to_baseline"]["decision"]
        == "proxy-only jaw collision representation is not sufficient and is rejected as the primary no-lift mechanism"
    )

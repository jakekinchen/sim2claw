from __future__ import annotations

import json
from pathlib import Path

from sim2claw.coordinated_unloading_tracking_temporal import (
    replay_tracking_challenger,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "configs/evaluations/coordinated_unloading_tracking_temporal_v1.json"
)


def test_contract_is_one_shot_twenty_episode_diagnostic() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["acceptance"] == {
        "expected_case_count": 4,
        "expected_variants_per_case": 5,
        "expected_challenger_episode_count": 20,
        "minimum_passing_cases_per_direction": 2,
        "all_challenger_episodes_must_pass": True,
        "prior_v5_direct_and_zoh_40_of_40_must_remain_passed": True,
    }
    assert contract["plant"]["joint_index"] == 2
    assert contract["plant"]["non_elbow_path"] == "canonical_direct_target"
    assert contract["authority"]["physical_motion"] is False
    assert contract["authority"]["mapping_approval"] is False
    assert contract["authority"]["transfer_claim"] is False


def test_frozen_tracking_temporal_denominator(tmp_path: Path) -> None:
    receipt = replay_tracking_challenger(
        CONTRACT, tmp_path / "tracking-temporal"
    )
    assert receipt["challenger_episode_count"] == 20
    assert receipt["prior_v5_direct_zoh_episode_count"] == 40
    assert len(receipt["results"]) == 4
    assert all(len(row["robustness"]) == 5 for row in receipt["results"])
    assert all(
        row["identity_checks"]["requested_hash_matches_v5"]
        for row in receipt["results"]
    )
    assert all(
        row["identity_checks"]["requested_mapped_sent_byte_identical"]
        for row in receipt["results"]
    )
    assert receipt["physical_motion"] is False
    assert receipt["physical_task_attempts"] == 0
    assert receipt["mapping_approved"] is False

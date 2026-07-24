from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from sim2claw.hil_evidence import (
    SUMMARY_SCHEMA_V2,
    _best_lag,
    derive_hil_evidence_summary,
    verify_hil_evidence,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_V2 = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "current_100mm_hil_multilevel_v2.json"
)
CAMPAIGN_V2 = REPO_ROOT / "runs/current-100mm-hil-multilevel-20260724"
EVIDENCE_V2 = REPO_ROOT / "outputs/current-100mm-hil-evidence-v2"


def test_best_lag_recovers_delayed_signal() -> None:
    source = np.asarray([0.0, 0.0, 1.0, 2.0, 3.0, 3.0, 2.0, 1.0])
    target = np.asarray([0.0, 0.0, 0.0, 1.0, 2.0, 3.0, 3.0, 2.0])
    result = _best_lag(source, target, sample_hz=20.0)
    assert result["lag_samples"] == 1
    assert result["lag_seconds"] == 0.05
    assert result["lag_aligned_rmse"] == 0.0


def test_best_lag_breaks_ties_toward_zero() -> None:
    source = np.zeros(20)
    target = np.zeros(20)
    result = _best_lag(source, target, sample_hz=20.0)
    assert result["lag_samples"] == 0
    assert result["lag_seconds"] == 0.0


def test_v2_summary_uses_the_preregistered_six_packet_inventory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    contract = json.loads(CONTRACT_V2.read_text(encoding="utf-8"))
    events = [
        {
            "packet_id": packet["packet_id"],
            "replay_status": "completed",
        }
        for packet in contract["packets"]
    ]
    (tmp_path / "campaign_state.json").write_text(
        json.dumps(
            {
                "events": events,
                "budget": {"used_physical_packet_attempts": 6},
            }
        ),
        encoding="utf-8",
    )
    admitted_ids = {
        events[0]["packet_id"],
        events[2]["packet_id"],
        events[4]["packet_id"],
        events[5]["packet_id"],
    }

    def fake_packet_summary(
        _campaign_root,
        event,
        loaded_contract,
        _contract_path,
    ):
        packet = next(
            row
            for row in loaded_contract["packets"]
            if row["packet_id"] == event["packet_id"]
        )
        admitted = event["packet_id"] in admitted_ids
        return {
            "packet_id": event["packet_id"],
            "target_joint": packet["target_joint"],
            "admitted": admitted,
            "failures": [] if admitted else ["wrist_video_not_completed"],
        }

    monkeypatch.setattr(
        "sim2claw.hil_evidence._packet_summary",
        fake_packet_summary,
    )
    summary = derive_hil_evidence_summary(
        tmp_path,
        contract_path=CONTRACT_V2,
    )

    assert summary["schema_version"] == SUMMARY_SCHEMA_V2
    assert summary["physical_attempts"] == 6
    assert summary["completed_trajectories"] == 6
    assert summary["admitted_packet_count"] == 4
    assert summary["rejected_packet_count"] == 2
    assert (
        summary["conclusions"]["all_six_unloaded_joint_channels_admitted"]
        is False
    )
    assert summary["conclusions"]["rejected_packets_may_not_be_fit_or_replayed"]


@pytest.mark.skipif(
    not (CAMPAIGN_V2 / "campaign_state.json").is_file()
    or not (EVIDENCE_V2 / "receipt.json").is_file(),
    reason="local six-packet HIL evidence is unavailable",
)
def test_live_v2_evidence_rederives_and_verifies() -> None:
    verified = verify_hil_evidence(
        CAMPAIGN_V2,
        EVIDENCE_V2,
        contract_path=CONTRACT_V2,
    )
    assert verified["summary"]["physical_attempts"] == 6
    assert verified["summary"]["admitted_packet_count"] == 4
    assert verified["summary"]["rejected_packet_count"] == 2
    assert verified["receipt"]["adaptive_retries"] == 0

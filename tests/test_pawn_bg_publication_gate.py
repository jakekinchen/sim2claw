from __future__ import annotations

from pathlib import Path

import pytest

from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_publication_gate import (
    load_publication_contract,
    run_publication_gate,
)


EVIDENCE_SENTINEL = (
    REPO_ROOT
    / "outputs"
    / "pawn_bg_servo_deadband_v1"
    / "servo_deadband_receipt.json"
)


def test_publication_contract_is_fail_closed() -> None:
    contract = load_publication_contract()
    assert not any(contract["authority"].values())
    assert contract["bootstrap"]["resampling_unit"] == "whole_episode"
    assert contract["gates"]["minimum_lift_and_transport_episodes_to_open_training"] == 6


@pytest.mark.skipif(not EVIDENCE_SENTINEL.is_file(), reason="campaign evidence unavailable")
def test_live_publication_gate_binds_evidence_and_refuses_promotion(
    tmp_path: Path,
) -> None:
    receipt = run_publication_gate(repository_root=REPO_ROOT, output_root=tmp_path)
    assert receipt["gates"]["action_invariance"] is True
    assert receipt["gates"]["timing_diagnostic"] is True
    assert receipt["gates"]["actuator_model_diagnostic"] is True
    assert receipt["verdict"]["simulator_composite_promoted"] is False
    assert receipt["verdict"]["training_admitted"] is False
    assert receipt["verdict"]["physical_accuracy_established"] is False
    assert (tmp_path / "publication_summary.png").is_file()
    assert (tmp_path / "publication_gate_receipt.json").is_file()

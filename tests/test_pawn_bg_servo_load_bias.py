from __future__ import annotations

from pathlib import Path

import pytest

from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_servo_load_bias import (
    _candidate_grid,
    _candidate_id,
    load_servo_load_bias_contract,
    run_servo_load_bias_ablation,
)


SOURCE_SENTINEL = REPO_ROOT / "datasets" / "manipulation_source_recordings"


def test_load_bias_contract_is_bounded_action_frozen_and_non_authoritative() -> None:
    contract = load_servo_load_bias_contract()
    candidates = _candidate_grid(contract)
    assert len(candidates) == 63
    assert len({_candidate_id(candidate) for candidate in candidates}) == 63
    assert all(contract["action_invariance"].values())
    assert not any(contract["authority"].values())
    assert contract["acceptance"]["minimum_cross_validated_joint_rms_relative_improvement"] == 0.05


@pytest.mark.skipif(not SOURCE_SENTINEL.is_dir(), reason="physical source assets unavailable")
def test_live_load_bias_campaign_verifies_significant_action_frozen_advancement(
    tmp_path: Path,
) -> None:
    receipt = run_servo_load_bias_ablation(
        source_repository_root=REPO_ROOT, output_root=tmp_path
    )
    assert receipt["action_arrays_byte_identical_across_variants"] is True
    assert receipt["advancement_gates"]["verified_significant_rms_advancement"] is True
    assert receipt["advancement_gates"]["verified_significant_advancement"] is True
    assert receipt["advancement_gates"]["verified_significant_consequence_advancement"] in (True, False)
    assert (tmp_path / "servo_load_bias_receipt.json").is_file()

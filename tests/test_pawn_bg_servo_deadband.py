from __future__ import annotations

from pathlib import Path

import pytest

from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_servo_deadband import (
    _candidate_is_eligible,
    _select_candidate,
    load_servo_deadband_contract,
    run_servo_deadband_ablation,
)


SOURCE_SENTINEL = (
    REPO_ROOT
    / "datasets"
    / "manipulation_source_recordings"
    / "b1-to-b2__20260719T030059Z-a26f8400"
    / "samples.jsonl"
)


def test_deadband_contract_is_action_frozen_and_non_authoritative() -> None:
    contract = load_servo_deadband_contract()
    assert all(contract["action_invariance"].values())
    assert not any(contract["authority"].values())
    assert contract["mechanism"]["target_joints"] == ["shoulder_lift", "elbow_flex"]


def test_candidate_selection_obeys_stall_constraints_before_rms() -> None:
    contract = load_servo_deadband_contract()
    weak_stall = {
        "deadband_degrees": 1.0,
        "overall_joint_rms_degrees": 1.0,
        "stall_reproduction_fraction": {"shoulder_lift": 0.9, "elbow_flex": 0.2},
    }
    eligible = {
        "deadband_degrees": 2.0,
        "overall_joint_rms_degrees": 1.3,
        "stall_reproduction_fraction": {"shoulder_lift": 0.7, "elbow_flex": 0.6},
    }
    assert _candidate_is_eligible(weak_stall, contract) is False
    assert _candidate_is_eligible(eligible, contract) is True
    assert _select_candidate([weak_stall, eligible], contract) is eligible


@pytest.mark.skipif(not SOURCE_SENTINEL.is_file(), reason="physical source assets unavailable")
def test_live_servo_deadband_ablation_is_action_frozen_and_fail_closed(
    tmp_path: Path,
) -> None:
    receipt = run_servo_deadband_ablation(
        source_repository_root=REPO_ROOT, output_root=tmp_path
    )
    assert receipt["action_arrays_byte_identical_across_variants"] is True
    assert receipt["train_acceptance"]["accepted_as_actuator_model_diagnostic"] is True
    assert receipt["train_acceptance"]["accepted_as_composite_simulator_candidate"] is False
    assert receipt["selected_deadband_degrees"] > 0.0
    assert all(
        row["clipped_action_rows"] == 0
        for variant in receipt["action_frozen_consequence_replay"].values()
        for row in variant["episodes"]
    )
    assert (tmp_path / "servo_deadband_receipt.json").is_file()

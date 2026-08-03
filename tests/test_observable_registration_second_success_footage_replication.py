from __future__ import annotations

import hashlib
import json

import pytest

from sim2claw.learning_factory_artifacts import FactoryArtifactError
from sim2claw.observable_registration_second_success_footage_replication import (
    CONTRACT_PATH,
    REPO_ROOT,
    load_second_success_footage_replication_contract,
    run_second_success_footage_replication_once,
)


def test_or54_contract_is_fail_closed() -> None:
    contract = load_second_success_footage_replication_contract()
    assert contract["recording_policy"]["known_outcome_quarantine_permanent"]
    assert not contract["recording_policy"]["heldout_claim_allowed"]
    assert contract["tracking"]["minimum_accepted_rows_per_point"] == 20
    assert not contract["tracking"]["per_frame_manual_correction_allowed"]
    assert not any(contract["claim_limits"].values())
    assert not any(contract["authority"].values())


def test_or54_abstains_on_crown_but_retains_jaw_replication(tmp_path) -> None:
    output = tmp_path / "or54"
    receipt = run_second_success_footage_replication_once(
        CONTRACT_PATH, output, root=REPO_ROOT
    )
    assert receipt["status"] == (
        "TERMINAL_SECOND_SUCCESSFUL_EPISODE_JAW_TRACKS_REPLICATE_"
        "PAWN_CROWN_TWO_PASS_ABSTAINS"
    )
    assert receipt["recording_identity"]["directory_receipt_semantic_conflict"]
    assert receipt["closed_command_hold_interval_samples_inclusive"] == [226, 351]
    tracking = receipt["tracking"]
    assert tracking["frame_count"] == 26
    assert tracking["nearest_sample_range_inclusive"] == [230, 330]
    assert tracking["all_frames_inside_closed_command_hold"]
    assert tracking["accepted_counts"]["fixed_jaw_tip"] == 26
    assert tracking["accepted_counts"]["moving_jaw_tip"] == 26
    assert tracking["accepted_counts"]["selected_pawn_crown"] < 20
    assert tracking["point_gates"] == {
        "fixed_jaw_tip": True,
        "moving_jaw_tip": True,
        "selected_pawn_crown": False,
    }
    assert not tracking["two_pass_enclosure_replication_pass"]
    assert receipt["execution"] == {
        "endpoint_anchor_count": 6,
        "per_frame_manual_annotations": 0,
        "simulator_replays": 0,
        "new_candidates": 0,
        "parameter_changes": 0,
        "hardware_actions": 0,
        "heldout_opened": False,
    }
    rows_path = output / "tracking_rows.json"
    assert receipt["tracking_rows_sha256"] == hashlib.sha256(
        rows_path.read_bytes()
    ).hexdigest()
    rows = json.loads(rows_path.read_text())
    assert len(rows["rows"]) == 26
    with pytest.raises(FactoryArtifactError, match="one-run"):
        run_second_success_footage_replication_once(
            CONTRACT_PATH, output, root=REPO_ROOT
        )

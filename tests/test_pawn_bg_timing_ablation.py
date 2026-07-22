from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_timing_ablation import (
    _array_receipt,
    load_timing_contract,
    run_timing_ablation,
)


SOURCE_SENTINEL = (
    REPO_ROOT
    / "datasets"
    / "manipulation_source_recordings"
    / "b1-to-b2__20260719T030059Z-a26f8400"
    / "samples.jsonl"
)


def test_timing_contract_changes_only_application_timing() -> None:
    contract = load_timing_contract()
    assert all(contract["action_invariance"].values())
    assert all(value is False for value in contract["authority"].values())
    members = [item for fold in contract["grouped_cross_validation"]["folds"] for item in fold]
    assert len(members) == len(set(members)) == 11


def test_action_receipt_binds_exact_float64_bytes() -> None:
    actions = np.arange(24, dtype=np.float64).reshape(4, 6)
    receipt = _array_receipt(actions)
    assert receipt["shape"] == [4, 6]
    assert receipt["dtype"] == "float64"
    changed = actions.copy()
    changed[0, 0] += 1e-12
    assert _array_receipt(changed)["sha256"] != receipt["sha256"]


@pytest.mark.skipif(not SOURCE_SENTINEL.is_file(), reason="physical source assets unavailable")
def test_live_timing_ablation_reduces_joint_and_ee_error_without_action_changes(
    tmp_path: Path,
) -> None:
    receipt = run_timing_ablation(
        source_repository_root=REPO_ROOT, output_root=tmp_path
    )
    assert receipt["action_arrays_byte_identical_across_variants"] is True
    assert receipt["train_acceptance"]["accepted_as_timing_diagnostic"] is True
    assert receipt["train_acceptance"]["accepted_as_composite_simulator_candidate"] is False
    assert (
        receipt["selected_train_metrics"]["overall_joint_rms_degrees"]
        < receipt["legacy_step_then_record"]["overall_joint_rms_degrees"]
    )
    assert (
        receipt["selected_train_metrics"]["ee_rms_m"]
        < receipt["legacy_step_then_record"]["ee_rms_m"]
    )
    assert all(
        row["clipped_action_rows"] == 0
        for variant in receipt["action_frozen_consequence_replay"].values()
        for row in variant["episodes"]
    )
    assert (tmp_path / "timing_ablation_receipt.json").is_file()

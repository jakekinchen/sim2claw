from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from sim2claw.pawn_bg_action_frozen_gap import (
    _assert_same_actions,
    load_action_frozen_contract,
    run_action_frozen_confirmation,
    run_action_frozen_gap_fit,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_SENTINEL = (
    REPO_ROOT
    / "datasets"
    / "manipulation_source_recordings"
    / "b1-to-b2__20260719T030059Z-a26f8400"
    / "samples.jsonl"
)


def test_action_frozen_contract_excludes_all_controller_changes() -> None:
    contract = load_action_frozen_contract()
    invariance = contract["action_invariance"]
    assert invariance["no_ik_corrections"] is True
    assert invariance["no_post_policy_offsets"] is True
    assert invariance["no_candidate_specific_action_mapping"] is True
    assert invariance["no_clipping"] is True
    assert contract["geometry_candidate"]["parameters"] == [
        "board_center_in_table_frame_xy_m",
        "board_yaw_relative_to_table_degrees",
        "board_side_m",
    ]
    assert all(value is False for value in contract["authority"].values())


def test_action_receipt_requires_exact_shape_dtype_bytes() -> None:
    actions = np.arange(24, dtype=np.float64).reshape(4, 6)
    receipt = _assert_same_actions(actions, {"a": actions, "b": actions.copy()})
    expected = hashlib.sha256(actions.tobytes()).hexdigest()
    assert receipt["source"]["sha256"] == expected
    assert receipt["all_variants_byte_identical"] is True
    assert receipt["post_policy_transform"] is None
    with pytest.raises(Exception, match="byte-identical"):
        changed = actions.copy()
        changed[0, 0] += 1e-12
        _assert_same_actions(actions, {"changed": changed})


@pytest.mark.skipif(not SOURCE_SENTINEL.is_file(), reason="physical source assets unavailable")
def test_live_geometry_fit_keeps_adapter_and_actions_frozen(tmp_path: Path) -> None:
    fit = run_action_frozen_gap_fit(
        source_repository_root=REPO_ROOT,
        output_root=tmp_path,
    )
    assert fit["held_out_used_for_selection"] is False
    assert fit["frozen_adapter_identical_for_all_variants"] is True
    assert fit["train_acceptance"]["byte_identical_action_gate"] is True
    assert fit["train_acceptance"]["event_rms_gate"] is True
    assert (
        fit["geometry_only"]["event_metrics"]["event_rms_distance_m"]
        < fit["stage_d"]["event_metrics"]["event_rms_distance_m"]
    )
    stage_d_offsets = fit["stage_d"]["parameters"]["joint_zero_offsets_rad"]
    geometry_offsets = fit["geometry_only"]["parameters"]["joint_zero_offsets_rad"]
    assert geometry_offsets == stage_d_offsets
    for episode in fit["recorded_action_replays"]:
        invariance = episode["action_invariance"]
        assert invariance["all_variants_byte_identical"] is True
        hashes = {
            row["sha256"] for row in invariance["variants"].values()
        } | {invariance["source"]["sha256"]}
        assert len(hashes) == 1
        assert Path(episode["trace_path"]).is_file()
        assert Path(episode["relative_distance_overlay_png"]).is_file()
        assert Path(episode["end_effector_xy_path_png"]).is_file()

    confirmation = run_action_frozen_confirmation(
        source_repository_root=REPO_ROOT,
        fit_receipt_path=tmp_path / "train_fit.json",
        output_root=tmp_path,
    )
    assert confirmation["all_actions_byte_identical"] is True
    assert confirmation["selection_changed_from_confirmation"] is False

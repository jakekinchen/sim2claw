from __future__ import annotations

from pathlib import Path

import numpy as np

from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_action_frozen_gap import _load_partition, _reconstruct_stage_d
from sim2claw.pawn_bg_f2_deformable_cap import _array_sha256
from sim2claw.pawn_bg_f2_deformable_cap_source_boundary import load_contract
from sim2claw.pawn_bg_f2_deformable_cap_source_boundary_verify import (
    source_boundary_rows,
)
from sim2claw.pawn_bg_timing_ablation import _mapped_episode


def _source_timestamps() -> np.ndarray:
    train, events = _load_partition(Path(REPO_ROOT), "train")
    _parent, workcell, _parameters, _details = _reconstruct_stage_d(train, events)
    rows = [
        _mapped_episode(payload, workcell)
        for payload in train
        if str(payload[0]["recording_id"]) == "20260719T032620Z-0c7e3d86"
    ]
    assert len(rows) == 1
    return np.asarray(rows[0]["timestamps"], dtype=np.float64)


def test_source_boundary_reconstruction_matches_all_frozen_hashes() -> None:
    contract = load_contract()
    reconstruction = contract["source_boundary_reconstruction"]
    rows = source_boundary_rows(
        trace_time=np.arange(9932, dtype=np.float64) * 0.00225,
        source_timestamps=_source_timestamps(),
        timestep_seconds=0.00225,
        reconstruction=reconstruction,
    )
    assert _array_sha256(rows["interval_step_counts"]) == reconstruction[
        "interval_step_counts_sha256"
    ]
    assert _array_sha256(rows["action_boundary_indices"]) == reconstruction[
        "action_boundary_indices_sha256"
    ]
    assert _array_sha256(rows["legacy_rows"]) == reconstruction[
        "legacy_rows_including_terminal_sha256"
    ]
    assert rows["action_boundary_indices"][-1] == 9731
    assert rows["legacy_rows"][-1] == 9931


def test_source_boundary_rows_exclude_interior_full_step_peak() -> None:
    contract = load_contract()
    rows = source_boundary_rows(
        trace_time=np.arange(9932, dtype=np.float64) * 0.00225,
        source_timestamps=_source_timestamps(),
        timestep_seconds=0.00225,
        reconstruction=contract["source_boundary_reconstruction"],
    )
    positions = np.zeros((9932, 3), dtype=np.float64)
    positions[4805, 2] = 0.04667828504443183
    positions[int(rows["action_boundary_indices"][250]), 2] = 0.0423955399520729
    assert np.max(positions[:, 2]) == 0.04667828504443183
    assert np.max(positions[rows["legacy_rows"], 2]) == 0.0423955399520729

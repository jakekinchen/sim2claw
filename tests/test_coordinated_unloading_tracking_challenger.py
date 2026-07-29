from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from sim2claw.coordinated_unloading_tracking_challenger import (
    apply_elbow_tracking_challenger,
    fit_tracking_challenger,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "configs/evaluations/coordinated_unloading_tracking_fit_v1.json"
)


def test_frozen_fit_passes_untouched_chronological_tail(
    tmp_path: Path,
) -> None:
    receipt = fit_tracking_challenger(CONTRACT, tmp_path / "fit")
    assert receipt["passed"] is True
    assert receipt["source_rows"] == 434
    assert receipt["train_rows"] == 304
    assert receipt["heldout_rows"] == 130
    assert receipt["heldout"]["rmse_degrees"] <= 0.5
    assert receipt["heldout"]["maximum_absolute_error_degrees"] <= 1.0
    assert (
        receipt["heldout"]["relative_improvement_over_requested"] >= 0.8
    )
    assert receipt["task_outcomes_used"] is False
    assert receipt["dynamic_task_replay"] is False
    assert receipt["physical_task_attempts"] == 0
    assert receipt["mapping_approved"] is False


def test_apply_challenger_changes_only_elbow() -> None:
    manifest_path = ROOT / (
        "runs/physical_excitation/20260725-follower-only-v1/"
        "simulation-canary-v1/candidate_manifest.json"
    )
    candidate = json.loads(manifest_path.read_text(encoding="utf-8"))[
        "candidate_config"
    ]
    requested = np.asarray(
        [
            [0.1, -0.2, 1.0, -0.3, 0.4, 0.2],
            [0.11, -0.19, 0.9, -0.29, 0.41, 0.19],
        ],
        dtype="<f8",
    )
    applied, physical = apply_elbow_tracking_challenger(
        requested,
        candidate_config=candidate,
        alpha=0.1,
        bias_degrees_per_sample=0.0,
        initial_actual_degrees=58.0,
    )
    assert np.array_equal(applied[:, [0, 1, 3, 4, 5]], requested[:, [0, 1, 3, 4, 5]])
    assert not np.array_equal(applied[:, 2], requested[:, 2])
    assert physical.shape == requested.shape


def test_contract_preserves_false_task_and_mapping_authority() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["fit"]["joint_name"] == "elbow_flex"
    assert contract["fit"]["task_outcomes_used"] is False
    assert contract["authority"]["dynamic_task_replay"] is False
    assert contract["authority"]["physical_motion"] is False
    assert contract["authority"]["physical_task_attempt"] is False
    assert contract["authority"]["mapping_approval"] is False
    assert contract["authority"]["transfer_claim"] is False

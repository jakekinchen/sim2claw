from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_endpoint_motion import (
    load_endpoint_motion_contract,
    normalized_correlation,
    run_endpoint_motion_pipeline,
)


SOURCE_SENTINEL = (
    REPO_ROOT
    / "datasets"
    / "manipulation_source_recordings"
    / "b1-to-b2__20260719T030059Z-a26f8400"
    / "overhead_c922.mp4"
)
OWNER_SENTINEL = (
    REPO_ROOT
    / "outputs"
    / "pawn_composability"
    / "recovered_corpus_v2"
    / "product_scope_owner_visual_review.json"
)


def test_endpoint_motion_contract_is_training_only_and_nonmetric() -> None:
    contract = load_endpoint_motion_contract()
    assert contract["episode_selection"]["partition"] == "train"
    assert contract["episode_selection"]["held_out_video_reads_allowed"] is False
    assert all(value is False for value in contract["authority"].values())


def test_normalized_correlation_distinguishes_same_and_inverted_patches() -> None:
    patch = np.arange(25, dtype=np.float64).reshape(5, 5)
    assert normalized_correlation(patch, patch + 100.0) == pytest.approx(1.0)
    assert normalized_correlation(patch, -patch) == pytest.approx(-1.0)


@pytest.mark.skipif(
    not (SOURCE_SENTINEL.is_file() and OWNER_SENTINEL.is_file()),
    reason="retained product video evidence unavailable",
)
def test_live_training_pipeline_detects_qualified_intervals_without_contact_claim(
    tmp_path: Path,
) -> None:
    receipt = run_endpoint_motion_pipeline(output_root=tmp_path)
    assert receipt["episode_count"] == 11
    assert receipt["held_out_video_reads"] == 0
    assert receipt["summary"]["source_visibility_loss_detected_episodes"] == 11
    assert receipt["summary"]["destination_final_appearance_detected_episodes"] == 11
    assert all(episode["contact_claimed"] is False for episode in receipt["episodes"])
    assert all(
        episode["metric_trajectory_claimed"] is False for episode in receipt["episodes"]
    )
    assert (tmp_path / "endpoint_motion_receipt.json").is_file()

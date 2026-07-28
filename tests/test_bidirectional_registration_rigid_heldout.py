from __future__ import annotations

import inspect
import json
from pathlib import Path

from sim2claw import bidirectional_registration_rigid_heldout as heldout
from sim2claw.bidirectional_registration_rigid_heldout_recovery_review import (
    review,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "configs/evaluations/bidirectional_pawn_push_v2_registration_heldout_v4.json"
)
RECOVERY = (
    ROOT
    / "configs/evaluations/bidirectional_pawn_push_v2_registration_heldout_recovery_v4.json"
)


def test_heldout_contract_is_one_open_zero_refit_and_four_members() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert [row["opaque_id"] for row in contract["expected_members"]] == [
        "heldout-r4-01",
        "heldout-r4-02",
        "heldout-r4-03",
        "heldout-r4-04",
    ]
    assert contract["single_open_protocol"] == {
        "required_member_count": 4,
        "all_members_open_together": True,
        "maximum_open_count": 1,
        "raw_manifest_reads": 1,
        "raw_image_reads_per_member": 1,
        "annotation_surface": "one derived 2x2 contact sheet only",
        "refuse_if_marker_or_output_exists": True,
    }
    assert not any(contract["frozen_candidate_policy"].values())
    assert not any(contract["authority"].values())


def test_heldout_evaluator_has_no_optimizer_or_refit_path() -> None:
    source = inspect.getsource(heldout)
    assert "scipy" not in source
    assert "least_squares" not in source
    assert "minimize(" not in source
    assert "candidate_refit\": False" in source


def test_recovery_is_reviewed_without_heldout_content_access(
    tmp_path: Path,
) -> None:
    receipt = review(RECOVERY, tmp_path / "review.json")
    assert receipt["status"] == "CONTINUE_TO_VERSIONED_SINGLE_PIXEL_OPEN"
    assert receipt["recovery_open_authorized"]
    assert receipt["cumulative_manifest_read_count_before_recovery"] == 1
    assert receipt["heldout_pixel_open_count_before_recovery"] == 0
    assert all(receipt["checks"].values())

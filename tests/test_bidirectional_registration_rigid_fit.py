from __future__ import annotations

import json
from pathlib import Path

from sim2claw.bidirectional_registration_rigid_fit import evaluate


ROOT = Path(__file__).resolve().parents[1]
ANNOTATIONS = (
    ROOT
    / "configs/evaluations/"
    "bidirectional_pawn_push_v2_registration_fit_annotations_v4.json"
)


def test_v4_rigid_fit_is_fit_only_full_rank_and_bounded(tmp_path: Path) -> None:
    receipt = evaluate(ANNOTATIONS, tmp_path / "fit")

    assert receipt["status"] == "fit_candidate_frozen"
    assert receipt["heldout_open_count"] == 0
    assert receipt["heldout_content_read"] is False
    assert receipt["fit_admitted_for_sealed_heldout_open"] is True
    assert receipt["solver"]["jacobian_rank"] == 15
    assert receipt["solver"]["jacobian_condition_number"] < 100_000_000
    assert all(receipt["checks"].values())
    candidate = json.loads(
        Path(receipt["candidate_path"]).read_text(encoding="utf-8")
    )
    assert candidate["heldout_open_count"] == 0
    assert candidate["fit_only"] is True

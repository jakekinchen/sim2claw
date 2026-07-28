from pathlib import Path

from sim2claw.bidirectional_registration_rigid_review import review


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "configs/evaluations/"
    "bidirectional_pawn_push_v2_registration_fit_review_v4.json"
)


def test_independent_rigid_fit_review_authorizes_one_sealed_open(
    tmp_path: Path,
) -> None:
    receipt = review(CONTRACT, tmp_path / "review.json")

    assert receipt["status"] == "CONTINUE_TO_SINGLE_SEALED_HELDOUT_OPEN"
    assert receipt["heldout_open_count"] == 0
    assert receipt["heldout_content_read"] is False
    assert receipt["sealed_heldout_open_authorized"] is True
    assert receipt["independent_jacobian"]["rank"] == 15
    assert receipt["active_bound_risk"]["automatic_pass_expansion"] is False
    assert all(receipt["checks"].values())

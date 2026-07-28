from sim2claw.bidirectional_terminal_evidence import build
from sim2claw.studio_catalog import build_catalog


def test_terminal_package_keeps_zero_attempt_claim_boundary() -> None:
    receipt = build()
    assert receipt["status"] == "terminal_safety_boundary_no_admissible_case"
    assert receipt["counted_action_hashes"] == []
    assert receipt["denominator"] == {
        "real_to_sim": {"successful": 0, "attempted": 0},
        "sim_to_real": {"successful": 0, "attempted": 0},
        "physical_attempts": 0,
        "maximum_physical_attempts": 10,
    }
    assert len(receipt["case_results"]) == 10
    assert all(case["admitted"] is False for case in receipt["case_results"])
    assert receipt["browser_comparison"]["available"] is False
    assert receipt["raw_recordings_published"] is False


def test_studio_catalog_labels_terminal_package_without_success() -> None:
    catalog = build_catalog()
    episode = next(
        row
        for row in catalog["episodes"]
        if row["task_id"] == "bidirectional_pawn_push_terminal_boundary_v1"
    )
    assert episode["status"] == "blocked"
    assert episode["action_array_sha256"] is None
    assert episode["physical_task_success_verified"] is False
    assert episode["simulator_task_success_verified"] is False
    assert episode["bidirectional_transfer_verified"] is False

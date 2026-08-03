from __future__ import annotations

import pytest

from sim2claw.observable_registration_one_shot_final_evaluator_heldout_global_monotone_response import (
    evaluate_once,
    load_one_shot_final_evaluator_heldout_global_monotone_response_contract,
)


def test_contract_freezes_one_shot_final_heldout_boundary() -> None:
    contract = load_one_shot_final_evaluator_heldout_global_monotone_response_contract()

    assert [row["split_position"] for row in contract["final_evaluator_heldout_episodes"]] == [10, 11]
    assert contract["gates"]["expected_total_frame_count"] == 246
    assert contract["frozen_candidate"]["refit_selection_threshold_change_or_retry_allowed"] is False
    assert contract["resource_boundary"]["fits_or_candidate_selections_allowed"] == 0
    assert contract["resource_boundary"]["threshold_changes_allowed"] == 0
    assert contract["resource_boundary"]["retries_allowed"] == 0
    assert contract["resource_boundary"]["development_reads_allowed"] == 0
    assert contract["resource_boundary"]["fresh_validation_reads_allowed"] == 0
    assert not any(contract["authority"].values())


def test_existing_receipt_prohibits_retry(tmp_path) -> None:
    (tmp_path / "receipt.json").write_text("{}")
    with pytest.raises(ValueError, match="retry prohibited"):
        evaluate_once(output_directory=tmp_path)

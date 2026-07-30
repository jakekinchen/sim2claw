from pathlib import Path

from sim2claw.observable_registration_unilateral_push_dynamic_replay import (
    load_unilateral_push_dynamic_replay_contract,
    run_unilateral_push_dynamic_replay_once,
)


def test_contract_is_exact_action_and_fail_closed() -> None:
    contract, _ = load_unilateral_push_dynamic_replay_contract()
    assert contract["replay"]["canonical_rank1_near_piece_reset_required"]
    assert contract["replay"]["natural_contact_only"]
    assert not contract["replay"]["action_change_allowed"]
    assert not contract["reporting"]["transfer_claim_allowed"]
    assert not contract["candidate"]["global_mapping_approved"]


def test_dynamic_replay_is_deterministic_and_quarantined(
    tmp_path: Path,
) -> None:
    receipt = run_unilateral_push_dynamic_replay_once(
        output_directory=tmp_path
    )
    assert receipt["source_identity"]["row_count"] == 531
    assert receipt["source_identity"]["row_order_preserved"]
    assert receipt["initialization"]["canonical_rank1_near_piece_reset"]
    assert (
        receipt["initialization"]["selected_pawn_initial_nonboard_contacts"]
        == []
    )
    assert receipt["actions_changed"] is False
    assert receipt["dynamic_replays"] == 1
    assert receipt["task_rows_used_for_candidate_selection"] is True
    assert receipt["global_mapping_approved"] is False
    assert receipt["transfer_claim"] is False

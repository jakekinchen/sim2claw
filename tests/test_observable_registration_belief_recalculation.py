from __future__ import annotations

from sim2claw.observable_registration_belief_recalculation import (
    build_belief_recalculation_receipt,
    load_belief_recalculation_contract,
)


def test_or14_contract_is_fail_closed() -> None:
    contract = load_belief_recalculation_contract()
    assert contract["selection_policy"]["task_rows_allowed_in_fit"] is False
    assert contract["selection_policy"]["task_outcome_allowed_in_fit"] is False
    assert (
        contract["selection_policy"]["selected_candidate_may_enter_dynamics"]
        is False
    )
    assert not any(contract["authority"].values())
    assert contract["promotion"]["global_mapping_approved"] is False


def test_or14_receipt_is_deterministic_and_proof_bounded(tmp_path) -> None:
    first = build_belief_recalculation_receipt(
        output_path=tmp_path / "first.json"
    )
    second = build_belief_recalculation_receipt(
        output_path=tmp_path / "second.json"
    )
    assert first == second
    assert first["artifact_sha256"] == second["artifact_sha256"]
    assert first["observation_split"]["task_rows_used_for_fit"] == 0
    assert first["observation_split"]["task_outcome_used_for_fit"] is False
    assert first["camera"]["refit_performed"] is False
    assert first["belief_updates"]["global_mapping_approved"] is False
    assert first["belief_updates"]["dynamic_replay_authorized"] is False
    assert len(first["families"]) == 4
    assert first["base_support_stack"]["gate_passed"] is True

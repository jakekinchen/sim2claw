from __future__ import annotations

from sim2claw.observable_registration_existing_trace_footage_constraint_audit import (
    load_existing_trace_footage_constraint_audit_contract,
    run_existing_trace_footage_constraint_audit_once,
)


def test_contract_freezes_all_existing_candidates_and_zero_new_execution() -> None:
    contract = load_existing_trace_footage_constraint_audit_contract()

    assert [row["candidate_count"] for row in contract["population"]["cards"]] == [
        9,
        19,
        25,
    ]
    assert contract["population"]["total_candidate_count"] == 53
    assert contract["population"][
        "terminal_outcome_available_to_preterminal_ranking"
    ] is False
    assert contract["audit_policy"]["candidate_selection_allowed"] is False
    assert contract["audit_policy"][
        "unsampled_continuum_exhaustion_claim_allowed"
    ] is False
    assert not any(contract["claim_limits"].values())
    assert not any(contract["authority"].values())


def test_existing_fixed_pad_corpus_bifurcates_without_full_match(tmp_path) -> None:
    receipt = run_existing_trace_footage_constraint_audit_once(
        output_directory=tmp_path / "or53"
    )

    assert receipt["status"] == (
        "TERMINAL_EXISTING_FIXED_PAD_TRACE_CORPUS_BIFURCATES_"
        "BILATERAL_VS_TIMING_NO_FULL_EVENT_MATCH"
    )
    audit = receipt["population_audit"]
    assert audit["candidate_count"] == 53
    assert audit["candidate_count_by_card"] == {"OR38": 9, "OR49": 19, "OR50": 25}
    assert audit["unique_candidate_identity_count"] == 53
    assert audit["gate_pass_counts"] == {
        "contact_timing": 53,
        "no_early_motion": 6,
        "support_loss_timing": 6,
        "bilateral_contact_timing": 9,
        "upright_at_sample_260": 6,
    }
    assert audit["gate_count_histogram"] == {
        "0": 0,
        "1": 34,
        "2": 11,
        "3": 8,
        "4": 0,
        "5": 0,
    }
    assert audit["maximum_preterminal_gate_count"] == 3
    assert audit["maximum_preterminal_gate_candidate_count"] == 8
    assert audit["all_five_gate_candidate_count"] == 0
    assert audit["bilateral_timing_candidate_count"] == 9
    assert audit["motion_and_support_timing_candidate_count"] == 6
    assert audit["bilateral_motion_and_support_timing_candidate_count"] == 0
    assert audit["bilateral_and_upright_sample260_candidate_count"] == 2
    assert audit["numeric_task_success_candidate_count"] == 1
    assert audit["numeric_success_and_all_five_gate_candidate_count"] == 0

    branch = receipt["bifurcation"]
    assert branch["branches_intersect"] is False
    assert branch["timing_correct_but_unilateral_candidate_count"] == 6
    assert [row["variant_id"] for row in branch["bilateral_but_early_branch"]] == [
        "fixed_pad_breakpoint_00",
        "upright_basin_03",
    ]
    verdict = receipt["sampled_family_verdict"]
    assert verdict["existing_sampled_single_coordinate_family_closed"] is True
    assert verdict["unsampled_continuum_exhausted"] is False
    assert verdict["candidate_selected_or_promoted"] is False
    assert receipt["new_execution"] == {
        "simulator_replays": 0,
        "new_candidates": 0,
        "parameter_changes": 0,
        "hardware_actions": 0,
        "new_annotations": 0,
        "heldout_opened": False,
    }

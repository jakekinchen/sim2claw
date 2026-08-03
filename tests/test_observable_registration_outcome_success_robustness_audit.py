from __future__ import annotations

from sim2claw.observable_registration_outcome_success_robustness_audit import (
    load_outcome_success_robustness_audit_contract,
    run_outcome_success_robustness_audit_once,
)


def test_contract_freezes_zero_new_execution_audit() -> None:
    contract = load_outcome_success_robustness_audit_contract()

    assert contract["frozen_surface_audit"]["selected_index"] == 14
    assert contract["frozen_surface_audit"]["grid_step_m"] == 0.00001
    assert contract["execution"]["simulator_replays_allowed"] == 0
    assert contract["execution"]["hardware_actions_allowed"] == 0
    assert not any(contract["authority"].values())
    assert not any(contract["claim_limits"].values())


def test_audit_rejects_isolated_wrong_event_topology(tmp_path) -> None:
    receipt = run_outcome_success_robustness_audit_once(
        output_directory=tmp_path / "or51"
    )

    assert receipt["status"] == (
        "TERMINAL_ISOLATED_OUTCOME_SUCCESS_WRONG_EVENT_TOPOLOGY_"
        "EXTERNAL_METRIC_OBSERVATION_REQUIRED"
    )
    assert receipt["surface_audit"]["numeric_task_success_candidate_count"] == 1
    assert receipt["surface_audit"]["numeric_task_success_indices"] == [14]
    assert receipt["surface_audit"]["selected_contiguous_numeric_success_count"] == 1
    assert receipt["surface_audit"]["local_outcome_continuity_pass"] is False
    assert receipt["event_audit"]["preterminal_gate_pass_count"] == 1
    assert receipt["event_audit"]["preterminal_gate_total_count"] == 5
    contact = receipt["event_audit"]["trace_contact_audit"]
    assert contact["first_named_jaw_contact_sample"] == 229
    assert contact["first_bilateral_jaw_contact_sample"] is None
    assert contact["observed_named_jaw_bodies"] == [
        "left_moving_jaw_so101_v1"
    ]
    assert contact["both_named_jaw_surfaces_contact"] is False
    assert receipt["event_audit"]["motion_early_by_samples"] == 3
    assert receipt["event_audit"]["support_loss_early_by_samples"] == 4
    assert receipt["event_audit"]["tilt_excess_at_sample_260_degrees"] > 16.11
    assert receipt["or50_binding"]["selection_verification_digest_identity"] is True
    assert receipt["overall_gate_pass"] is False
    assert receipt["new_execution"] == {
        "simulator_replays": 0,
        "new_candidates": 0,
        "parameter_changes": 0,
        "hardware_actions": 0,
        "heldout_opened": False,
    }

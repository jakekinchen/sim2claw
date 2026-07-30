from pathlib import Path

from sim2claw.observable_registration_exact_replay_contact_introspection import (
    load_exact_replay_contact_introspection_contract,
    run_exact_replay_contact_introspection_once,
)


def test_contract_is_model_identical_and_fail_closed() -> None:
    contract = load_exact_replay_contact_introspection_contract()
    policy = contract["introspection"]
    assert policy["one_run_only"]
    assert not policy["model_change_allowed"]
    assert not policy["configuration_change_allowed"]
    assert not policy["action_change_allowed"]
    assert not policy["parameter_selection_allowed"]
    assert not contract["reporting"]["transfer_claim_allowed"]


def test_or19_reproduces_before_contact_trace_is_accepted(
    tmp_path: Path,
) -> None:
    receipt = run_exact_replay_contact_introspection_once(
        output_directory=tmp_path
    )
    assert receipt["status"] == "PASS_EXACT_REPRODUCTION_CONTACT_TRACE"
    assert receipt["or19_reproduction"]["exact_receipt_match"]
    assert receipt["source_identity"]["row_count"] == 531
    assert receipt["source_identity"]["actions_changed"] is False
    assert receipt["trace_summary"]["internal_step_count"] > 531
    assert (
        receipt["trace_summary"]["first_named_jaw_contact_source_sample"]
        == 231
    )
    assert receipt["global_mapping_approved"] is False
    assert receipt["transfer_claim"] is False

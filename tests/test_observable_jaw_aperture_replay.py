from __future__ import annotations

from sim2claw.observable_jaw_aperture_replay import (
    load_aperture_replay_contract,
    run_aperture_replay_once,
)


def test_or7_contract_is_exact_one_run_and_nonphysical() -> None:
    contract, c6 = load_aperture_replay_contract()
    assert contract["replay"]["one_run_only"] is True
    assert contract["replay"]["natural_contact_only"] is True
    assert contract["candidate_change"]["only_changed_parameter"] == (
        "gripper_zero_offset_rad"
    )
    assert contract["proof_policy"]["contact_material_validated"] is False
    assert contract["proof_policy"]["global_mapping_approved"] is False
    assert contract["authority"]["simulator_replay"] is True
    assert not any(
        value
        for key, value in contract["authority"].items()
        if key != "simulator_replay"
    )
    assert c6["source"]["gateway_sent"]["shape"] == [531, 6]


def test_or7_exact_replay_emits_identity_and_honest_result(tmp_path) -> None:
    output = tmp_path / "run"
    receipt = run_aperture_replay_once(output_directory=output)
    assert all(receipt["source_identity"][key] for key in (
        "recording_id",
        "requested",
        "gateway_sent",
        "timestamps",
        "identified_applied",
        "row_order",
    ))
    assert receipt["candidate_identity"]["only_gripper_zero_offset_changed"] is True
    assert receipt["trace"]["path"] == (output / "trace.json").resolve().as_posix()
    assert receipt["trace"]["row_count"] == 531
    assert receipt["runtime"]["natural_contact_only"] is True
    assert receipt["runtime"]["contact_material_validated"] is False
    assert receipt["full_contact_fidelity_promoted"] is False
    assert receipt["result"] in {
        "MATCHING_TASK_OUTCOME_CONTACT_MATERIAL_UNVALIDATED",
        "MATERIAL_CAUSAL_ADVANCEMENT_TASK_NEGATIVE",
        "NO_MATERIAL_CAUSAL_ADVANCEMENT_TASK_NEGATIVE",
    }


def test_or7_one_run_guard(tmp_path) -> None:
    output = tmp_path / "run"
    run_aperture_replay_once(output_directory=output)
    try:
        run_aperture_replay_once(output_directory=output)
    except Exception as error:
        assert "one-run receipt already exists" in str(error)
    else:
        raise AssertionError("OR7 one-run guard did not reject a rerun")

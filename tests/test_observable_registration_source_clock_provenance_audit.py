from pathlib import Path

import pytest

from sim2claw.learning_factory_artifacts import FactoryArtifactError
from sim2claw.observable_registration_source_clock_provenance_audit import (
    ALTERNATE_CLOCK,
    CLOSURE_SAMPLES,
    EXECUTION_BOUNDARY,
    PRIMARY_CLOCK,
    load_source_clock_provenance_audit_contract,
    run_source_clock_provenance_audit,
    verify_source_clock_provenance_audit,
)


def test_contract_is_known_result_read_only_and_fail_closed() -> None:
    contract = load_source_clock_provenance_audit_contract()

    assert contract["audit"]["known_result_reproduction"] is True
    assert contract["audit"]["primary_clock_field"] == PRIMARY_CLOCK
    assert contract["audit"]["alternate_clock_field"] == ALTERNATE_CLOCK
    assert contract["audit"]["closure_samples"] == list(CLOSURE_SAMPLES)
    assert contract["audit"]["outcome_or_task_metric_may_select_a_parameter"] is False
    assert contract["audit"]["admissible_successor_may_be_opened"] is False
    assert contract["execution"] == EXECUTION_BOUNDARY
    assert contract["execution"]["mujoco_step_calls"] == 0
    assert contract["execution"]["simulator_replays"] == 0
    assert contract["execution"]["fits"] == 0
    assert contract["execution"]["action_or_timestamp_mutations"] == 0
    assert not any(contract["claim_limits"].values())


def test_audit_bounds_clock_rebinding_and_preserves_closure_frame_bindings(
    tmp_path: Path,
) -> None:
    output = tmp_path / "or156"

    receipt = run_source_clock_provenance_audit(output_directory=output)
    verified = verify_source_clock_provenance_audit(output_directory=output)

    assert verified == receipt
    assert receipt["status"] == (
        "PASS_SOURCE_CLOCK_REBINDING_TOO_SMALL_AT_CLOSURE_NO_SUCCESSOR"
    )
    assert receipt["execution"] == EXECUTION_BOUNDARY
    clock = receipt["clock_provenance"]
    assert clock["maximum_direct_shift_sample_index"] == 220
    assert clock["direct_shift_sample_completion_minus_follower_read"][
        "maximum_ms"
    ] == pytest.approx(7.1715840604)
    assert clock["maximum_absolute_elapsed_delta_sample_index"] == 220
    assert clock["maximum_absolute_elapsed_delta_ms"] == pytest.approx(5.9980420629)
    assert clock["actuator_application_or_ack_timestamp_available_rows"] == 0
    assert clock["device_clock_synchronized_rows"] == 0

    closure = receipt["closure_window"]
    assert closure["sample_indices"] == list(CLOSURE_SAMPLES)
    assert closure["maximum_direct_source_clock_shift_ms"] == pytest.approx(
        0.0392079819
    )
    assert closure["maximum_absolute_elapsed_rebinding_delta_ms"] == pytest.approx(
        1.1423339602
    )
    assert closure["all_c922_and_d405_frame_bindings_unchanged"] is True
    rows = {row["sample_index"]: row for row in closure["rows"]}
    assert rows[224]["direct_source_clock_shift_ms"] == pytest.approx(0.0330840703)
    assert rows[228]["elapsed_rebinding_delta_ms"] == pytest.approx(1.1423339602)
    assert rows[232]["frame_associations"]["d405"]["primary_frame_index"] == 91
    assert rows[232]["frame_associations"]["d405"]["alternate_frame_index"] == 91
    assert rows[241]["frame_associations"]["c922"]["frame_binding_unchanged"] is True

    associations = receipt["frame_association"]
    assert associations["c922"]["full_trace_changed_frame_binding_samples"] == [
        86,
        92,
        183,
        210,
        377,
        382,
    ]
    assert associations["d405"]["full_trace_changed_frame_binding_samples"] == [
        59,
        359,
        519,
    ]
    assert associations["d405"]["maximum_primary_association_error_ms"] == pytest.approx(
        100.066125
    )

    diagnosis = receipt["diagnosis"]
    assert (
        diagnosis[
            "sample_completion_versus_follower_read_clock_explains_visible_closure_lead"
        ]
        is False
    )
    assert diagnosis["software_row_clock_candidate_exhausted"] is True
    assert diagnosis["camera_exposure_time_identified"] is False
    assert diagnosis["actuator_application_time_identified"] is False
    assert diagnosis["task_level_success_advanced_by_this_audit"] is False
    assert diagnosis["admissible_task_successor"] is False
    assert not any(receipt["claim_limits"].values())


def test_audit_output_is_write_once(tmp_path: Path) -> None:
    output = tmp_path / "or156"
    run_source_clock_provenance_audit(output_directory=output)

    with pytest.raises(FactoryArtifactError, match="write-once"):
        run_source_clock_provenance_audit(output_directory=output)

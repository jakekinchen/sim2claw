from pathlib import Path

import mujoco
import pytest

from sim2claw.learning_factory_artifacts import FactoryArtifactError
from sim2claw.observable_registration_or154_closure_locus_audit import (
    AUDIT_SAMPLES,
    CONTACT_SAMPLE,
    EXECUTION_BOUNDARY,
    load_closure_locus_audit_contract,
    run_closure_locus_audit,
    verify_closure_locus_audit,
)


def test_contract_is_known_result_zero_dynamics_and_fail_closed() -> None:
    contract = load_closure_locus_audit_contract()

    assert contract["audit"]["known_result_reproduction"] is True
    assert contract["audit"]["samples"] == list(AUDIT_SAMPLES)
    assert contract["audit"]["or154_first_broad_contact_sample"] == CONTACT_SAMPLE
    assert contract["audit"]["admissible_successor_may_be_opened"] is False
    assert contract["execution"] == EXECUTION_BOUNDARY
    assert contract["execution"]["mujoco_step_calls"] == 0
    assert contract["execution"]["simulator_replays"] == 0
    assert contract["execution"]["fits"] == 0
    assert not any(contract["claim_limits"].values())


def test_audit_reproduces_spatial_locus_and_non_named_mesh_contact_without_steps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden_step(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("OR155 may not step dynamics")

    monkeypatch.setattr(mujoco, "mj_step", forbidden_step)
    monkeypatch.setattr(mujoco, "mj_step1", forbidden_step)
    monkeypatch.setattr(mujoco, "mj_step2", forbidden_step)
    output = tmp_path / "or155"

    receipt = run_closure_locus_audit(output_directory=output)
    verified = verify_closure_locus_audit(output_directory=output)

    assert verified == receipt
    assert receipt["status"] == (
        "PASS_SPATIAL_CLOSURE_LOCUS_AND_NON_NAMED_MESH_CONTACT_ATTRIBUTED_NO_SUCCESSOR"
    )
    assert receipt["execution"] == EXECUTION_BOUNDARY
    assert receipt["timing"]["physical_first_definite_enclosure_sample"] == 232
    assert receipt["timing"]["requested_closed_hold_start_sample"] == 241
    assert receipt["timing"]["or154_first_broad_contact_sample"] == 271
    assert receipt["timing"]["raw_measured_more_open_than_sent_at_samples_224_232_241"] is True
    assert receipt["timing"]["maximum_d405_association_error_ms"] == pytest.approx(100.066125)
    assert receipt["timing"]["physical_enclosure_to_or154_contact_seconds"] == pytest.approx(1.949306584)

    closure = receipt["closure_locus"]
    assert closure["closed_hold_midpoint_planar_distance_to_exact_d1_m"] == pytest.approx(
        0.03448165764
    )
    assert closure["closed_hold_midpoint_minus_exact_d1_xy_m"] == pytest.approx(
        [-0.00812016136, 0.03351190375]
    )
    rows = {row["sample_index"]: row for row in closure["rows"]}
    assert rows[232]["midpoint_planar_distance_to_exact_d1_m"] == pytest.approx(
        0.03562267306
    )
    assert rows[241]["raw_measured_gripper_degrees"] > rows[241][
        "gateway_sent_gripper_degrees"
    ]

    provenance = receipt["contact_provenance"]
    assert provenance["recorded_body_pairs"] == [["brown_pawn_d1", "left_gripper"]]
    assert provenance["nearest_compiled_collision"]["signed_distance_m"] == pytest.approx(
        -0.00012971135
    )
    assert provenance["nearest_compiled_collision"]["gripper_mesh_name"] == (
        "left_wrist_roll_follower_so101_gripper_part0_v1"
    )
    assert provenance["nearest_compiled_collision"]["named_jaw_geom"] is False
    assert provenance["nearest_named_jaw_collision"]["gripper_geom_name"] == (
        "left_fixed_jaw_box5"
    )
    assert provenance["nearest_named_jaw_collision"]["signed_distance_m"] == pytest.approx(
        0.00452314268
    )
    assert provenance["named_jaw_pair_enclosure_proved"] is False

    ledger = receipt["exposure_ledger"]
    assert ledger["or2_rigid_fit_accepted"] is False
    assert ledger["retained_proxy_parameter_fit_allowed"] is False
    assert ledger["retained_proxy_first_accepted_crown_sample"] == 290
    assert ledger["retained_proxy_pawn_base_rows"] == 0
    assert ledger["second_episode_cross_episode_parameter_fit_allowed"] is False
    assert ledger["admissible_fit_rows"] == 0
    assert ledger["untouched_validation_cohorts"] == 0

    diagnosis = receipt["diagnosis"]
    assert diagnosis["early_actuator_closure_supported"] is False
    assert diagnosis["spatial_closure_locus_mismatch_reproduced"] is True
    assert diagnosis["or154_broad_contact_witness_proves_bilateral_grasp"] is False
    assert diagnosis["task_level_success_advanced_by_this_audit"] is False
    assert diagnosis["admissible_task_successor"] is False
    assert not any(receipt["claim_limits"].values())


def test_audit_output_is_write_once(tmp_path: Path) -> None:
    output = tmp_path / "or155"
    run_closure_locus_audit(output_directory=output)

    with pytest.raises(FactoryArtifactError, match="write-once"):
        run_closure_locus_audit(output_directory=output)

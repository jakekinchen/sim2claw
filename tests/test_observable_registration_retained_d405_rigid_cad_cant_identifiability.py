from pathlib import Path

from sim2claw.observable_registration_retained_d405_rigid_cad_cant_identifiability import (
    CONTRACT_PATH,
    derive_observable_partition,
    load_retained_d405_rigid_cad_cant_identifiability_contract,
    run_retained_d405_rigid_cad_cant_identifiability_once,
)


def test_contract_is_retained_only_and_denies_replay() -> None:
    contract = load_retained_d405_rigid_cad_cant_identifiability_contract()
    assert not any(contract["authority"].values())
    assert not any(contract["claim_limits"].values())
    assert contract["positive_observables"]["red_mask_may_be_positive_cad_target"] is False
    assert contract["diagnostic_model"]["candidate_parameter_emission_allowed"] is False
    assert contract["retained_corpus"]["contact_terminal_pawn_outcome_or_or36s_dynamic_result_allowed"] is False


def test_frozen_partition_is_deterministic_and_exposes_missing_folds() -> None:
    contract = load_retained_d405_rigid_cad_cant_identifiability_contract()
    first = derive_observable_partition(contract)
    second = derive_observable_partition(contract)
    assert first == second
    assert first["direction_counts"] == {"closing": 5, "hold": 11, "opening": 9}
    assert [first["fold_reports"][str(fold)]["frame_count"] for fold in range(5)] == [11, 8, 4, 1, 1]
    assert first["fold_reports"]["3"]["direction_counts"] == {"hold": 1}
    assert first["fold_reports"]["4"]["direction_counts"] == {"hold": 1}
    assert first["fold_reports"]["3"]["distinct_raw_gripper_values"] == 1
    assert first["fold_reports"]["4"]["distinct_raw_gripper_values"] == 1
    assert first["source_outcomes_used"] is False


def test_live_screen_fails_before_render_fit_or_replay(tmp_path: Path) -> None:
    receipt = run_retained_d405_rigid_cad_cant_identifiability_once(
        CONTRACT_PATH, tmp_path / "or46"
    )
    assert receipt["status"] == "RETAINED_RGB_CANT_PRACTICALLY_UNIDENTIFIABLE"
    assert receipt["prerender_gates_passed"] is False
    assert receipt["failed_before_cad_render"] is True
    assert receipt["failed_before_optimization"] is True
    assert receipt["cad_renders_run"] == 0
    assert receipt["optimizer_runs"] == 0
    assert receipt["candidate_parameter_emitted"] is False
    assert receipt["simulator_replays_run"] == 0
    assert receipt["simulator_replay_permitted"] is False
    assert receipt["contact_surface_cant_identified"] is False
    assert receipt["physical_task_attempt"] is False
    assert receipt["next_boundary"] == "TERMINAL_EXTERNAL_METRIC_PAD_OBSERVATION_REQUIRED"
    gates = receipt["prerender_gate_report"]
    assert gates["minimum_fit_frames"] is True
    assert gates["validation_has_opening"] is False
    assert gates["validation_has_closing"] is False
    assert gates["stress_has_opening"] is False
    assert gates["stress_has_closing"] is False
    assert gates["joint_validation_stress_distinct_gripper_values"] is False

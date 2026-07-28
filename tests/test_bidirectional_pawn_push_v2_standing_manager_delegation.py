from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DELEGATION = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_standing_manager_delegation_v1.json"
)
SUCCESSOR_AUTHORIZATION = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_multistart_approach_"
    "successor_authorization_v1.json"
)
STATIC_CONTRACT = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_multistart_approach_static_v1.json"
)
STATIC_RECEIPT = ROOT / (
    "runs/bidirectional-pawn-push-v2/"
    "20260728-v05-tx-multistart-approach-v1/static-freeze-v1/receipt.json"
)
TEMPORAL_CONTRACT = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_temporal_replay_multistart_approach_v1.json"
)
TEMPORAL_RECEIPT = ROOT / (
    "runs/bidirectional-pawn-push-v2/"
    "20260728-v05-tx-multistart-approach-v1/temporal-replay-v1/receipt.json"
)
PROGRESS_SUCCESSOR_AUTHORIZATION = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_progress_exclusion_"
    "successor_authorization_v1.json"
)
SLOW_ELEVATED_STATIC_CONTRACT = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_slow_elevated_static_v1.json"
)
SLOW_ELEVATED_STATIC_V1_FAILURE = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_slow_elevated_static_v1_binding_failure.json"
)
SLOW_ELEVATED_STATIC_V2_CONTRACT = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_slow_elevated_static_v2.json"
)
BOUNDED_STROKE_AUTHORIZATION = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_bounded_stroke_successor_authorization_v1.json"
)
BOUNDED_STROKE_STATIC_CONTRACT = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_bounded_stroke_static_v1.json"
)
BOUNDED_STROKE_STATIC_RECEIPT = ROOT / (
    "runs/bidirectional-pawn-push-v2/"
    "20260728-v05-tz-bounded-stroke-v1/static-freeze-v1/receipt.json"
)
BOUNDED_STROKE_TEMPORAL_CONTRACT = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_temporal_replay_bounded_stroke_v1.json"
)
BOUNDED_STROKE_TEMPORAL_RECEIPT = ROOT / (
    "runs/bidirectional-pawn-push-v2/"
    "20260728-v05-tz-bounded-stroke-v1/temporal-replay-v1/receipt.json"
)
LOW_CENTER_AUTHORIZATION = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_low_center_contact_"
    "successor_authorization_v1.json"
)
LOW_CENTER_STATIC_CONTRACT = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_low_center_contact_static_v3.json"
)
LOW_CENTER_STATIC_RECEIPT = ROOT / (
    "runs/bidirectional-pawn-push-v2/"
    "20260728-v05-ua-low-center-v3/static-freeze-v1/receipt.json"
)
NEIGHBOR_CORRIDOR_AUTHORIZATION = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_neighbor_corridor_"
    "successor_authorization_v1.json"
)
NEIGHBOR_CORRIDOR_STATIC_CONTRACT = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_neighbor_corridor_static_v1.json"
)
NEIGHBOR_CORRIDOR_STATIC_RECEIPT = ROOT / (
    "runs/bidirectional-pawn-push-v2/"
    "20260728-v05-ub-neighbor-corridor-v1/static-freeze-v1/receipt.json"
)
NEIGHBOR_CORRIDOR_TEMPORAL_CONTRACT = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_temporal_replay_neighbor_corridor_v1.json"
)
NEIGHBOR_CORRIDOR_TEMPORAL_RECEIPT = ROOT / (
    "runs/bidirectional-pawn-push-v2/"
    "20260728-v05-ub-neighbor-corridor-v1/temporal-replay-v1/receipt.json"
)
ORIENTATION_FUNNEL_AUTHORIZATION = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_orientation_funnel_"
    "successor_authorization_v1.json"
)
ORIENTATION_FUNNEL_STATIC_CONTRACT = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_orientation_funnel_static_v1.json"
)
ORIENTATION_FUNNEL_STATIC_RECEIPT = ROOT / (
    "runs/bidirectional-pawn-push-v2/"
    "20260728-v05-uc-orientation-funnel-v1/static-freeze-v1/receipt.json"
)
SEEDED_FUNNEL_AUTHORIZATION = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_seeded_funnel_"
    "successor_authorization_v1.json"
)
SEEDED_FUNNEL_STATIC_CONTRACT = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_seeded_funnel_static_v1.json"
)
SEEDED_FUNNEL_STATIC_RECEIPT = ROOT / (
    "runs/bidirectional-pawn-push-v2/"
    "20260728-v05-ud-seeded-funnel-v1/static-freeze-v1/receipt.json"
)
RAMPED_FUNNEL_AUTHORIZATION = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_ramped_funnel_"
    "successor_authorization_v1.json"
)
RAMPED_FUNNEL_STATIC_CONTRACT = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_ramped_funnel_static_v1.json"
)
RAMPED_FUNNEL_STATIC_RECEIPT = ROOT / (
    "runs/bidirectional-pawn-push-v2/"
    "20260728-v05-ue-ramped-funnel-v1/static-freeze-v1/receipt.json"
)
UNILATERAL_OPEN_JAW_AUTHORIZATION = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_unilateral_open_jaw_"
    "successor_authorization_v1.json"
)
UNILATERAL_OPEN_JAW_STATIC_CONTRACT = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_unilateral_open_jaw_static_v1.json"
)
UNILATERAL_OPEN_JAW_STATIC_RECEIPT = ROOT / (
    "runs/bidirectional-pawn-push-v2/"
    "20260728-v05-uf-unilateral-open-jaw-v1/static-freeze-v1/receipt.json"
)
UNILATERAL_OPEN_JAW_TEMPORAL_AUTHORIZATION = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_unilateral_open_jaw_"
    "temporal_authorization_v1.json"
)
UNILATERAL_OPEN_JAW_TEMPORAL_CONTRACT = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_temporal_replay_"
    "unilateral_open_jaw_v1.json"
)
UNILATERAL_OPEN_JAW_TEMPORAL_RECEIPT = ROOT / (
    "runs/bidirectional-pawn-push-v2/"
    "20260728-v05-uf-unilateral-open-jaw-v1/temporal-replay-v1/receipt.json"
)
LOW_PLANAR_OPEN_JAW_AUTHORIZATION = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_low_planar_open_jaw_"
    "successor_authorization_v1.json"
)
LOW_PLANAR_OPEN_JAW_STATIC_CONTRACT = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_low_planar_open_jaw_static_v1.json"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_standing_delegation_preserves_campaign_and_nondelegable_gates() -> None:
    delegation = json.loads(DELEGATION.read_text(encoding="utf-8"))
    predecessor = delegation["immutable_predecessor"]
    assert _sha(ROOT / predecessor["path"]) == predecessor["sha256"]
    assert delegation["initial_successor"]["milestone_id"] == "V05-TX"
    invariants = delegation["campaign_invariants"]
    assert invariants["minimum_signed_progress_mm"] == 36.025
    assert (
        invariants[
            "minimum_distinct_families_per_direction_before_v06_or_physical"
        ]
        == 2
    )
    assert invariants["predecessor_verdicts_immutable"] is True
    assert invariants["dynamically_evaluated_cases_quarantined"] is True
    assert invariants["contract_and_hashes_frozen_before_outcomes"] is True
    assert invariants["one_bounded_execution_per_freeze"] is True
    assert invariants["no_post_outcome_expansion_of_frozen_grid"] is True
    assert delegation["brev_policy"] == (
        "Brev remains empty unless separately explicitly authorized."
    )
    authority = delegation["authority"]
    assert authority["manager_authorization_receipts"] is True
    assert authority["successor_design"] is True
    assert authority["physical_packet_authorization_after_all_gates"] is True
    for key in (
        "credentials",
        "paid_compute",
        "destructive_actions",
        "public_external_actions",
        "unreviewed_physical_motion",
        "manual_user_intervention",
        "gate_weakening",
    ):
        assert authority[key] is False


def test_manager_authorization_is_static_design_only_and_source_bound() -> None:
    authorization = json.loads(
        SUCCESSOR_AUTHORIZATION.read_text(encoding="utf-8")
    )
    for binding in (
        authorization["standing_delegation"],
        *authorization["immutable_predecessors"].values(),
    ):
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert authorization["quarantine"]["case_ids"] == [
        "brown_pawn_b1__b1_b2",
        "brown_pawn_a2__a2_a1",
        "brown_pawn_a2__a2_a3",
        "brown_pawn_e2__e2_e3",
    ]
    design = authorization["authorized_static_design"]
    assert design["physical_pawn_layout_changed"] is False
    assert design["manual_intervention_required"] is False
    assert design["setup_posture_must_be_part_of_action_identity"] is True
    assert design["static_selection_only"] is True
    assert authorization["authority"]["static_design"] is True
    assert not any(
        value
        for key, value in authorization["authority"].items()
        if key != "static_design"
    )


def test_slow_elevated_static_contract_is_finite_and_fresh_only() -> None:
    contract = json.loads(
        SLOW_ELEVATED_STATIC_CONTRACT.read_text(encoding="utf-8")
    )
    for key in (
        "authorization",
        "base_static_contract",
        "previous_temporal_receipt",
        "base_implementation",
        "implementation",
    ):
        binding = contract[key]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    overrides = contract["frozen_overrides"]
    assert len(overrides["quarantine_case_ids"]) == 8
    assert overrides["expected_postquarantine_family_count"] == 40
    assert overrides["approach_lateral_offsets_m"] == [-0.05, 0.0, 0.05]
    assert overrides["maximum_total_cells"] == 360
    assert overrides["setup_joint_speed_physical_units_s"] == 1.5
    assert overrides["endpoint_geometry"]["contact_height_m"] == 0.024
    assert overrides["endpoint_geometry"]["stroke_m"] == 0.12
    assert (
        overrides["endpoint_geometry"][
            "precontact_clearance_height_above_pawn_base_m"
        ]
        == 0.075
    )
    assert contract["selection"]["fresh_nonquarantined_families_only"] is True
    assert contract["authority"]["model_loading"] is True
    assert contract["authority"]["static_simulation"] is True
    assert contract["authority"]["dynamic_replay"] is False
    assert contract["authority"]["physical_motion"] is False


def test_slow_elevated_v1_failure_and_v2_loader_fix_are_source_bound() -> None:
    failure = json.loads(
        SLOW_ELEVATED_STATIC_V1_FAILURE.read_text(encoding="utf-8")
    )
    for key in (
        "failed_contract",
        "failed_implementation",
        "derived_contract_artifact",
    ):
        binding = failure[key]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert failure["failure"]["model_loaded"] is False
    assert failure["failure"]["static_cells_evaluated"] == 0
    assert failure["failure"]["dynamic_replay_executed"] is False
    assert failure["failure"]["physical_motion"] is False

    contract = json.loads(
        SLOW_ELEVATED_STATIC_V2_CONTRACT.read_text(encoding="utf-8")
    )
    for key in ("authorization", "v1_binding_failure", "implementation"):
        binding = contract[key]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert contract["quarantine"]["exact_count"] == 8
    assert len(contract["quarantine"]["case_ids"]) == 8
    assert contract["family_grid"]["expected_postquarantine_family_count"] == 40
    assert contract["parameter_grid"]["maximum_total_cells"] == 360
    assert (
        contract["action_identity"]["setup_joint_speed_physical_units_s"]
        == 1.5
    )
    assert contract["endpoint_geometry"]["stroke_m"] == 0.12
    assert contract["authority"]["model_loading"] is True
    assert contract["authority"]["static_simulation"] is True
    assert contract["authority"]["dynamic_replay"] is False
    assert contract["authority"]["physical_motion"] is False


def test_bounded_stroke_successor_changes_only_static_stroke() -> None:
    authorization = json.loads(
        BOUNDED_STROKE_AUTHORIZATION.read_text(encoding="utf-8")
    )
    for binding in authorization["immutable_predecessors"].values():
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert authorization["quarantine"]["exact_count"] == 8
    assert authorization["authorized_static_design"]["sole_change"] == (
        "stroke_m_from_0.12_to_0.09"
    )
    assert authorization["authority"]["model_loading"] is False
    assert authorization["authority"]["static_simulation"] is False
    assert authorization["authority"]["physical_motion"] is False

    predecessor = json.loads(
        SLOW_ELEVATED_STATIC_V2_CONTRACT.read_text(encoding="utf-8")
    )
    contract = json.loads(
        BOUNDED_STROKE_STATIC_CONTRACT.read_text(encoding="utf-8")
    )
    for key in ("authorization", "v1_binding_failure", "implementation"):
        binding = contract[key]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert contract["endpoint_geometry"]["stroke_m"] == 0.09
    for key in (
        "contact_offset_m",
        "contact_height_m",
        "precontact_clearance_height_above_pawn_base_m",
    ):
        assert contract["endpoint_geometry"][key] == (
            predecessor["endpoint_geometry"][key]
        )
    assert contract["parameter_grid"] == predecessor["parameter_grid"]
    assert contract["action_identity"] == predecessor["action_identity"]
    assert contract["quarantine"] == predecessor["quarantine"]
    assert contract["selection"] == predecessor["selection"]
    assert contract["static_gates"] == predecessor["static_gates"]
    assert contract["authority"]["static_simulation"] is True
    assert contract["authority"]["dynamic_replay"] is False
    assert contract["authority"]["physical_motion"] is False


def test_bounded_stroke_static_pass_and_temporal_freeze_bind_exact_actions() -> None:
    receipt = json.loads(
        BOUNDED_STROKE_STATIC_RECEIPT.read_text(encoding="utf-8")
    )
    assert _sha(BOUNDED_STROKE_STATIC_RECEIPT) == (
        "35c3bea2db1098c424ce25c7663e25fde3df973a4ca3fd33a8f855a34df2cd12"
    )
    assert receipt["status"] == "slow_elevated_static_freeze_pass"
    assert receipt["grid_result_count"] == 360
    assert receipt["quarantine_leaked_into_candidates"] is False
    assert receipt["statically_eligible_family_count"] == 4
    assert receipt["selected_family_count"] == 4
    assert receipt["lane_counts"] == {
        "REAL_TO_SIM": 2,
        "SIM_TO_REAL": 2,
    }
    assert receipt["dynamic_replay_executed"] is False
    assert receipt["physical_motion"] is False

    contract = json.loads(
        BOUNDED_STROKE_TEMPORAL_CONTRACT.read_text(encoding="utf-8")
    )
    for key in (
        "standing_delegation",
        "manager_authorization",
        "static_contract",
        "static_receipt",
        "rehearsal_contract",
        "temporal_plan",
        "implementation",
    ):
        binding = contract[key]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert [row["direction_lane"] for row in contract["cases"]] == [
        "REAL_TO_SIM",
        "SIM_TO_REAL",
        "REAL_TO_SIM",
        "SIM_TO_REAL",
    ]
    assert [row["case_id"] for row in contract["cases"]] == [
        row["case_id"] for row in receipt["eligible_cases"]
    ]
    for case in contract["cases"]:
        assert _sha(ROOT / case["action_path"]) == case["action_sha256"]
    assert contract["acceptance"]["minimum_cases_per_direction"] == 2
    assert contract["authority"]["dynamic_simulation"] is True
    assert contract["authority"]["v06_evaluator_freeze"] is False
    assert contract["authority"]["physical_motion"] is False


def test_low_center_successor_quarantines_twelve_and_changes_contact_only() -> None:
    receipt = json.loads(
        BOUNDED_STROKE_TEMPORAL_RECEIPT.read_text(encoding="utf-8")
    )
    assert _sha(BOUNDED_STROKE_TEMPORAL_RECEIPT) == (
        "5617090dd0d7a1734d3a1d42df1e8048d102141a774f41b9b2375b5206c627a7"
    )
    assert receipt["status"] == "temporal_replay_reject"
    assert receipt["passing_case_ids"] == []
    assert receipt["lane_counts"] == {
        "REAL_TO_SIM": 0,
        "SIM_TO_REAL": 0,
    }
    assert receipt["physical_motion"] is False

    authorization = json.loads(
        LOW_CENTER_AUTHORIZATION.read_text(encoding="utf-8")
    )
    for binding in authorization["immutable_predecessors"].values():
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert authorization["quarantine"]["exact_count"] == 12
    assert authorization["quarantine"]["case_ids"][-4:] == [
        "tan_pawn_g8__g8_g7",
        "tan_pawn_g8__g8_h8",
        "tan_pawn_f7__f7_f6",
        "brown_pawn_e2__e2_f2",
    ]
    assert authorization["authority"]["static_design"] is True
    assert authorization["authority"]["model_loading"] is False
    assert authorization["authority"]["physical_motion"] is False

    predecessor = json.loads(
        BOUNDED_STROKE_STATIC_CONTRACT.read_text(encoding="utf-8")
    )
    contract = json.loads(
        LOW_CENTER_STATIC_CONTRACT.read_text(encoding="utf-8")
    )
    for key in ("authorization", "v1_binding_failure", "implementation"):
        binding = contract[key]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert contract["quarantine"]["exact_count"] == 12
    assert contract["family_grid"]["expected_postquarantine_family_count"] == 36
    assert contract["parameter_grid"]["maximum_total_cells"] == 324
    assert contract["endpoint_geometry"]["contact_height_m"] == 0.018
    assert contract["endpoint_geometry"]["contact_offset_m"] == 0.016
    for key in (
        "stroke_m",
        "precontact_clearance_height_above_pawn_base_m",
    ):
        assert contract["endpoint_geometry"][key] == (
            predecessor["endpoint_geometry"][key]
        )
    assert contract["parameter_grid"]["setup_branches"] == (
        predecessor["parameter_grid"]["setup_branches"]
    )
    assert contract["parameter_grid"]["approach_lateral_offsets_m"] == (
        predecessor["parameter_grid"]["approach_lateral_offsets_m"]
    )
    assert contract["action_identity"] == predecessor["action_identity"]
    assert contract["selection"] == predecessor["selection"]
    assert contract["static_gates"] == predecessor["static_gates"]
    assert contract["authority"]["static_simulation"] is True
    assert contract["authority"]["dynamic_replay"] is False
    assert contract["authority"]["physical_motion"] is False


def test_neighbor_corridor_successor_changes_only_stroke_after_ua_reject() -> None:
    receipt = json.loads(
        LOW_CENTER_STATIC_RECEIPT.read_text(encoding="utf-8")
    )
    assert _sha(LOW_CENTER_STATIC_RECEIPT) == (
        "171d634b577c4487ba8a8de1ee9ab14b21d6dc6c9633edd88ed8e00d3feb1f8a"
    )
    assert receipt["status"] == "low_center_contact_static_freeze_reject"
    assert receipt["grid_result_count"] == 324
    assert receipt["statically_eligible_family_count"] == 0
    assert receipt["dynamic_replay_executed"] is False
    assert receipt["physical_motion"] is False

    authorization = json.loads(
        NEIGHBOR_CORRIDOR_AUTHORIZATION.read_text(encoding="utf-8")
    )
    for binding in authorization["immutable_predecessors"].values():
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert authorization["quarantine"]["exact_count"] == 12
    assert authorization["authorized_static_design"]["sole_change"] == (
        "stroke_m_from_0.09_to_0.06"
    )
    assert authorization["authority"]["model_loading"] is False
    assert authorization["authority"]["physical_motion"] is False

    predecessor = json.loads(
        LOW_CENTER_STATIC_CONTRACT.read_text(encoding="utf-8")
    )
    contract = json.loads(
        NEIGHBOR_CORRIDOR_STATIC_CONTRACT.read_text(encoding="utf-8")
    )
    for key in ("authorization", "v1_binding_failure", "implementation"):
        binding = contract[key]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert contract["endpoint_geometry"]["stroke_m"] == 0.06
    for key in (
        "contact_offset_m",
        "contact_height_m",
        "precontact_clearance_height_above_pawn_base_m",
    ):
        assert contract["endpoint_geometry"][key] == (
            predecessor["endpoint_geometry"][key]
        )
    assert contract["parameter_grid"] == predecessor["parameter_grid"]
    assert contract["action_identity"] == predecessor["action_identity"]
    assert contract["quarantine"] == predecessor["quarantine"]
    assert contract["selection"] == predecessor["selection"]
    assert contract["static_gates"] == predecessor["static_gates"]
    assert contract["authority"]["static_simulation"] is True
    assert contract["authority"]["dynamic_replay"] is False
    assert contract["authority"]["physical_motion"] is False


def test_neighbor_corridor_static_pass_and_temporal_freeze_bind_actions() -> None:
    receipt = json.loads(
        NEIGHBOR_CORRIDOR_STATIC_RECEIPT.read_text(encoding="utf-8")
    )
    assert _sha(NEIGHBOR_CORRIDOR_STATIC_RECEIPT) == (
        "ed2a7aef30069330fcff83b9359b006f5999cbf4fe7478239c6394654bf02a2d"
    )
    assert receipt["status"] == "low_center_contact_static_freeze_pass"
    assert receipt["grid_result_count"] == 324
    assert receipt["statically_eligible_family_count"] == 4
    assert receipt["selected_family_count"] == 4
    assert receipt["lane_counts"] == {
        "REAL_TO_SIM": 2,
        "SIM_TO_REAL": 2,
    }
    assert receipt["dynamic_replay_executed"] is False
    assert receipt["physical_motion"] is False

    contract = json.loads(
        NEIGHBOR_CORRIDOR_TEMPORAL_CONTRACT.read_text(encoding="utf-8")
    )
    for key in (
        "standing_delegation",
        "manager_authorization",
        "static_contract",
        "static_receipt",
        "rehearsal_contract",
        "temporal_plan",
        "implementation",
    ):
        binding = contract[key]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert [row["direction_lane"] for row in contract["cases"]] == [
        "REAL_TO_SIM",
        "SIM_TO_REAL",
        "REAL_TO_SIM",
        "SIM_TO_REAL",
    ]
    assert [row["case_id"] for row in contract["cases"]] == [
        row["case_id"] for row in receipt["eligible_cases"]
    ]
    for case in contract["cases"]:
        assert _sha(ROOT / case["action_path"]) == case["action_sha256"]
    assert contract["acceptance"]["minimum_cases_per_direction"] == 2
    assert contract["authority"]["dynamic_simulation"] is True
    assert contract["authority"]["v06_evaluator_freeze"] is False
    assert contract["authority"]["physical_motion"] is False


def test_neighbor_corridor_temporal_receipt_closes_straight_push_family() -> None:
    receipt = json.loads(
        NEIGHBOR_CORRIDOR_TEMPORAL_RECEIPT.read_text(encoding="utf-8")
    )
    assert _sha(NEIGHBOR_CORRIDOR_TEMPORAL_RECEIPT) == (
        "9c3ea9b6d0ee79adbd007f87ad1badee218f923c181c18b1b477933a25834bb5"
    )
    assert receipt["status"] == "temporal_replay_reject"
    assert receipt["passing_case_ids"] == []
    assert receipt["lane_counts"] == {
        "REAL_TO_SIM": 0,
        "SIM_TO_REAL": 0,
    }
    for case in receipt["results"]:
        for path in case["plant_paths"]:
            assert all(path["identity_checks"].values())
            assert path["gateway"]["all_rows_inside_calibrated_limits"]
            assert path["gateway"]["all_rates_within_reviewed_gateway_limits"]
            assert path["gateway"]["requested_sent_byte_identical"]
    assert receipt["authority"]["v06_evaluator_freeze"] is False
    assert receipt["physical_motion"] is False
    assert receipt["physical_task_attempts"] == 0


def test_orientation_funnel_successor_is_finite_open_loop_and_fresh() -> None:
    authorization = json.loads(
        ORIENTATION_FUNNEL_AUTHORIZATION.read_text(encoding="utf-8")
    )
    for binding in authorization["immutable_predecessors"].values():
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert authorization["quarantine"]["exact_count"] == 16
    design = authorization["authorized_static_design"]
    assert design["cells_per_family"] == 18
    assert design["finite_maximum_cells"] == 576
    assert design["selected_pawn_grasped"] is False
    assert design["closed_loop_or_feedback"] is False
    assert authorization["authority"]["static_design"] is True
    assert authorization["authority"]["model_loading"] is False
    assert authorization["authority"]["physical_motion"] is False

    contract = json.loads(
        ORIENTATION_FUNNEL_STATIC_CONTRACT.read_text(encoding="utf-8")
    )
    for key in (
        "authorization",
        "v1_binding_failure",
        "standing_delegation",
        "rehearsal_contract",
        "temporal_plan",
        "geometry_source",
        "scene_implementation",
        "articulated_robot_model",
        "candidate_manifest",
        "registration_candidate",
        "implementation",
    ):
        binding = contract[key]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert contract["quarantine"]["exact_count"] == 16
    assert contract["family_grid"]["expected_postquarantine_family_count"] == 32
    assert contract["parameter_grid"]["cells_per_family"] == 18
    assert contract["parameter_grid"]["maximum_total_cells"] == 576
    assert len(contract["parameter_grid"]["wrist_roll_targets_rad"]) == 3
    assert contract["parameter_grid"]["guide_lateral_offsets_m"] == [
        -0.003,
        0.003,
    ]
    assert contract["endpoint_geometry"]["stroke_m"] == 0.075
    assert contract["action_identity"]["selected_pawn_grasped"] is False
    assert contract["action_identity"]["closed_loop_or_feedback"] is False
    assert contract["action_identity"]["sample_hz"] == 40.0
    assert contract["action_identity"]["closed_jaw_rad"] == (
        -0.1727003294848389
    )
    assert contract["authority"]["static_simulation"] is True
    assert contract["authority"]["dynamic_replay"] is False
    assert contract["authority"]["physical_motion"] is False


def test_orientation_funnel_static_reject_and_seeded_successor_freeze() -> None:
    receipt = json.loads(
        ORIENTATION_FUNNEL_STATIC_RECEIPT.read_text(encoding="utf-8")
    )
    assert _sha(ORIENTATION_FUNNEL_STATIC_RECEIPT) == (
        "127434f66157b4d090e4f971eae44e12e5ba6083c3a1ae6196ae9b2c85d6e6ff"
    )
    assert receipt["status"] == "orientation_funnel_static_freeze_reject"
    assert receipt["grid_result_count"] == 576
    assert sum(
        row["status"] == "compile_reject" for row in receipt["grid_results"]
    ) == 510
    assert sum(
        row["status"] == "static_reject" for row in receipt["grid_results"]
    ) == 66
    assert receipt["statically_eligible_family_count"] == 0
    assert receipt["lane_counts"] == {"REAL_TO_SIM": 0, "SIM_TO_REAL": 0}
    assert receipt["dynamic_replay_executed"] is False
    assert receipt["physical_motion"] is False

    authorization = json.loads(
        SEEDED_FUNNEL_AUTHORIZATION.read_text(encoding="utf-8")
    )
    for binding in authorization["immutable_predecessors"].values():
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert authorization["quarantine"]["exact_count"] == 16
    design = authorization["authorized_static_design"]
    assert design["cells_per_family"] == 18
    assert design["finite_maximum_cells"] == 576
    assert design["selected_pawn_grasped"] is False
    assert design["closed_loop_or_feedback"] is False
    assert authorization["authority"]["model_loading"] is False
    assert authorization["authority"]["physical_motion"] is False

    contract = json.loads(
        SEEDED_FUNNEL_STATIC_CONTRACT.read_text(encoding="utf-8")
    )
    for key in (
        "authorization",
        "base_static_contract",
        "v05_uc_static_receipt",
        "base_implementation",
        "multistart_implementation",
        "implementation",
    ):
        binding = contract[key]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    overrides = contract["frozen_overrides"]
    assert len(overrides["quarantine_case_ids"]) == 16
    assert overrides["postquarantine_family_count"] == 32
    assert overrides["cells_per_family"] == 18
    assert overrides["maximum_total_cells"] == 576
    assert overrides["endpoint_geometry"]["contact_offset_m"] == 0.022
    assert overrides["endpoint_geometry"]["contact_height_m"] == 0.024
    assert overrides["endpoint_geometry"]["stroke_m"] == 0.075
    assert contract["authority"]["static_simulation"] is True
    assert contract["authority"]["dynamic_replay"] is False
    assert contract["authority"]["physical_motion"] is False


def test_seeded_funnel_reject_and_ramped_successor_freeze() -> None:
    receipt = json.loads(
        SEEDED_FUNNEL_STATIC_RECEIPT.read_text(encoding="utf-8")
    )
    assert _sha(SEEDED_FUNNEL_STATIC_RECEIPT) == (
        "2196435cc8d21d245d2df6e6c099e9857cbc4c68f7e6a9d62665edd8e4ace7b4"
    )
    assert receipt["status"] == "orientation_funnel_static_freeze_reject"
    assert receipt["grid_result_count"] == 576
    assert sum(
        row["status"] == "compile_reject" for row in receipt["grid_results"]
    ) == 510
    assert sum(
        row["status"] == "static_reject" for row in receipt["grid_results"]
    ) == 66
    assert receipt["statically_eligible_family_count"] == 0
    assert receipt["dynamic_replay_executed"] is False
    assert receipt["physical_motion"] is False

    authorization = json.loads(
        RAMPED_FUNNEL_AUTHORIZATION.read_text(encoding="utf-8")
    )
    for binding in authorization["immutable_predecessors"].values():
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert authorization["quarantine"]["exact_count"] == 16
    design = authorization["authorized_static_design"]
    assert design["level_engagement_m"] == 0.01
    assert design["ramp_end_planar_progress_m"] == 0.025
    assert design["ramp_rise_m"] == 0.006
    assert design["finite_maximum_cells"] == 576
    assert design["selected_pawn_grasped"] is False
    assert design["closed_loop_or_feedback"] is False

    contract = json.loads(
        RAMPED_FUNNEL_STATIC_CONTRACT.read_text(encoding="utf-8")
    )
    for key in (
        "authorization",
        "base_static_contract",
        "v05_ud_static_receipt",
        "base_implementation",
        "multistart_implementation",
        "implementation",
    ):
        binding = contract[key]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    overrides = contract["frozen_overrides"]
    assert overrides["cells_per_family"] == 18
    assert overrides["maximum_total_cells"] == 576
    assert overrides["level_engagement_m"] == 0.01
    assert overrides["ramp_rise_m"] == 0.006
    assert contract["authority"]["static_simulation"] is True
    assert contract["authority"]["dynamic_replay"] is False
    assert contract["authority"]["physical_motion"] is False


def test_ramped_funnel_partial_result_stays_below_dynamic_gate() -> None:
    receipt = json.loads(
        RAMPED_FUNNEL_STATIC_RECEIPT.read_text(encoding="utf-8")
    )
    assert _sha(RAMPED_FUNNEL_STATIC_RECEIPT) == (
        "35442bc9afd5bb28f87f1ed4dab70d3b8b9eca4bf82b26e89a27a6b5c38a9b68"
    )
    assert receipt["status"] == "orientation_funnel_static_freeze_reject"
    assert receipt["grid_result_count"] == 576
    assert sum(
        row["status"] == "compile_reject" for row in receipt["grid_results"]
    ) == 510
    assert sum(
        row["status"] == "static_reject" for row in receipt["grid_results"]
    ) == 56
    assert sum(
        row["status"] == "static_eligible"
        for row in receipt["grid_results"]
    ) == 10
    assert receipt["statically_eligible_family_count"] == 1
    assert receipt["lane_counts"] == {"REAL_TO_SIM": 1, "SIM_TO_REAL": 0}
    assert [row["case_id"] for row in receipt["eligible_cases"]] == [
        "tan_pawn_h7__h7_g7"
    ]
    assert receipt["dynamic_replay_executed"] is False
    assert receipt["physical_motion"] is False


def test_unilateral_open_jaw_successor_is_finite_and_non_grasping() -> None:
    authorization = json.loads(
        UNILATERAL_OPEN_JAW_AUTHORIZATION.read_text(encoding="utf-8")
    )
    for binding in authorization["immutable_predecessors"].values():
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    opening = authorization["open_jaw_derivation"]
    assert opening["exact_model_target_rad"] == 1.2
    assert opening["modeled_open_aperture_m"] == 0.034
    assert opening["modeled_pawn_max_body_diameter_m"] == 0.0276
    assert opening["static_clearance_buffer_m"] == 0.0064
    assert opening["inside_calibrated_gateway_range"] is True
    assert opening["jaw_command_constant_during_setup_and_push"] is True
    assert opening["jaw_closing_forbidden"] is True
    assert authorization["quarantine"]["exact_count"] == 16
    design = authorization["authorized_static_design"]
    assert design["contact_sides"] == ["fixed_jaw", "moving_jaw"]
    assert design["cells_per_family"] == 18
    assert design["finite_maximum_cells"] == 576
    invariants = authorization["new_static_invariants"]
    assert all(invariants.values())
    assert authorization["authority"]["model_loading"] is False
    assert authorization["authority"]["physical_motion"] is False

    contract = json.loads(
        UNILATERAL_OPEN_JAW_STATIC_CONTRACT.read_text(encoding="utf-8")
    )
    for key in (
        "authorization",
        "base_static_contract",
        "v05_ue_static_receipt",
        "base_implementation",
        "multistart_implementation",
        "temporal_static_implementation",
        "implementation",
    ):
        binding = contract[key]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    overrides = contract["frozen_overrides"]
    assert len(overrides["quarantine_case_ids"]) == 16
    assert overrides["open_jaw_target_rad"] == 1.2
    assert overrides["contact_sides"] == ["fixed_jaw", "moving_jaw"]
    assert overrides["cells_per_family"] == 18
    assert overrides["maximum_total_cells"] == 576
    assert all(value == 0 for value in contract["new_static_gates"].values() if isinstance(value, int) and not isinstance(value, bool))
    assert contract["authority"]["static_simulation"] is True
    assert contract["authority"]["dynamic_replay"] is False
    assert contract["authority"]["physical_motion"] is False


def test_unilateral_open_jaw_static_pass_and_temporal_freeze() -> None:
    receipt = json.loads(
        UNILATERAL_OPEN_JAW_STATIC_RECEIPT.read_text(encoding="utf-8")
    )
    assert _sha(UNILATERAL_OPEN_JAW_STATIC_RECEIPT) == (
        "6235d6ab7b531c2119df6c70ec30e3e9a5dea2b1a445d9553fb196d5e3fa972e"
    )
    assert receipt["status"] == "unilateral_open_jaw_static_freeze_pass"
    assert receipt["grid_result_count"] == 576
    assert receipt["statically_eligible_family_count"] == 8
    assert receipt["selected_family_count"] == 4
    assert receipt["lane_counts"] == {"REAL_TO_SIM": 2, "SIM_TO_REAL": 2}
    assert receipt["bilateral_contact_allowed"] is False
    assert receipt["grasp_or_enclosure_allowed"] is False
    assert receipt["robot_board_contact_allowed"] is False
    assert receipt["selected_pawn_lift_allowed"] is False
    assert receipt["dynamic_replay_executed"] is False
    assert receipt["physical_motion"] is False

    authorization = json.loads(
        UNILATERAL_OPEN_JAW_TEMPORAL_AUTHORIZATION.read_text(
            encoding="utf-8"
        )
    )
    for binding in (
        authorization["standing_delegation"],
        *authorization["immutable_predecessors"].values(),
    ):
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert authorization["frozen_execution"] == {
        "canonical_direct_target": True,
        "diagnostic_zoh_delay_seconds": 0.11,
        "robustness_variant_count": 5,
        "minimum_signed_progress_mm": 36.025,
        "minimum_cases_per_direction": 2,
        "maximum_selected_vertical_rise_mm": 2.0,
        "one_bounded_execution": True,
    }
    assert authorization["authority"]["dynamic_simulation"] is True
    assert authorization["authority"]["physical_motion"] is False

    contract = json.loads(
        UNILATERAL_OPEN_JAW_TEMPORAL_CONTRACT.read_text(encoding="utf-8")
    )
    for key in (
        "standing_delegation",
        "manager_authorization",
        "static_contract",
        "static_receipt",
        "rehearsal_contract",
        "temporal_plan",
        "base_implementation",
        "implementation",
    ):
        binding = contract[key]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert contract["strict_extension"] == "unilateral_open_jaw_v1"
    assert len(contract["cases"]) == 4
    assert {
        case["direction_lane"] for case in contract["cases"]
    } == {"REAL_TO_SIM", "SIM_TO_REAL"}
    assert all(
        case["constant_open_jaw_start_row"] == 138
        for case in contract["cases"]
    )
    assert {
        case["expected_unilateral_contact_side"]
        for case in contract["cases"]
    } == {"fixed_jaw", "moving_jaw"}
    assert contract["strict_dynamic_gates"] == {
        "expected_unilateral_contact_required": True,
        "opposite_jaw_selected_contact_count": 0,
        "bilateral_selected_contact_count": 0,
        "selected_pawn_enclosure_or_grasp_count": 0,
        "robot_board_contact_count": 0,
        "maximum_selected_vertical_rise_mm": 2.0,
    }
    assert contract["authority"]["dynamic_simulation"] is True
    assert contract["authority"]["physical_motion"] is False


def test_unilateral_temporal_negative_and_low_planar_freeze() -> None:
    receipt = json.loads(
        UNILATERAL_OPEN_JAW_TEMPORAL_RECEIPT.read_text(encoding="utf-8")
    )
    assert _sha(UNILATERAL_OPEN_JAW_TEMPORAL_RECEIPT) == (
        "526e5f98acb1058d15bc61220f25fdc3fe7b14f96b1172de2df99a80da2455c4"
    )
    assert receipt["status"] == "unilateral_open_jaw_temporal_replay_reject"
    assert receipt["lane_counts"] == {"REAL_TO_SIM": 0, "SIM_TO_REAL": 0}
    variants = [
        variant
        for case in receipt["results"]
        for path in case["plant_paths"]
        for variant in path["robustness"]
    ]
    assert len(variants) == 40
    assert not any(row["checks"]["fully_off_source"] for row in variants)
    assert not any(
        row["checks"]["selected_pawn_not_lifted"] for row in variants
    )
    for key in (
        "expected_unilateral_contact",
        "opposite_jaw_contact_absent",
        "bilateral_contact_absent",
        "enclosure_or_grasp_absent",
        "robot_board_contact_absent",
        "excluded_contact",
        "excluded_displacement",
        "collision",
        "camera_margin",
    ):
        assert all(row["checks"][key] for row in variants)
    assert min(row["signed_progress_mm"] for row in variants) == (
        13.562589007493933
    )
    assert max(row["signed_progress_mm"] for row in variants) == (
        31.075921679879734
    )
    assert min(
        row["maximum_selected_vertical_rise_mm"] for row in variants
    ) == 12.275856073287406
    assert max(
        row["maximum_selected_vertical_rise_mm"] for row in variants
    ) == 14.06376936945275
    assert receipt["physical_motion"] is False

    authorization = json.loads(
        LOW_PLANAR_OPEN_JAW_AUTHORIZATION.read_text(encoding="utf-8")
    )
    for binding in (
        authorization["standing_delegation"],
        *authorization["immutable_predecessors"].values(),
    ):
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert authorization["geometry_derivation"]["contact_height_m"] == 0.018
    assert authorization["geometry_derivation"]["contact_offset_m"] == 0.016
    assert authorization["geometry_derivation"]["stroke_m"] == 0.09
    assert authorization["geometry_derivation"][
        "upward_or_rising_segment_count"
    ] == 0
    assert authorization["geometry_derivation"]["scalar_sweep"] is False
    assert authorization["quarantine"]["exact_count"] == 20
    assert len(authorization["quarantine"]["new_case_ids"]) == 4
    assert authorization["status"] == (
        "paused_orientation_migration_complete_awaiting_fable_"
        "no_resume_authority"
    )
    assert authorization["resume"] is False
    assert authorization["quarantine"]["case_ids_are_semantic_and_preserved"] is True
    assert authorization["authority"]["static_design"] is False
    assert authorization["authority"]["model_loading"] is False
    assert authorization["authority"]["physical_motion"] is False

    contract = json.loads(
        LOW_PLANAR_OPEN_JAW_STATIC_CONTRACT.read_text(encoding="utf-8")
    )
    for key in (
        "authorization",
        "v05_uf_temporal_receipt",
        "orientation_static_contract",
        "seeded_static_contract",
        "ramped_static_contract",
        "open_jaw_static_contract",
        "orientation_contract",
        "implementation",
    ):
        binding = contract[key]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    for binding in contract["base_implementations"].values():
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    frozen = contract["frozen_overrides"]
    assert frozen["cumulative_quarantine_count"] == 20
    assert frozen["postquarantine_family_count"] == 22
    assert frozen["cells_per_family"] == 18
    assert frozen["maximum_total_cells"] == 396
    assert frozen["contact_height_m"] == 0.018
    assert frozen["contact_offset_m"] == 0.016
    assert frozen["stroke_m"] == 0.09
    assert frozen["vertical_rise_m"] == 0.0
    assert contract["status"] == (
        "paused_orientation_migration_complete_awaiting_fable_"
        "no_resume_authority"
    )
    assert contract["resume"] is False
    assert frozen["case_ids_are_semantic_and_preserved"] is True
    assert contract["authority"]["model_loading"] is False
    assert contract["authority"]["static_simulation"] is False
    assert contract["authority"]["dynamic_replay"] is False
    assert contract["authority"]["physical_motion"] is False


def test_multistart_approach_static_contract_is_finite_and_fail_closed() -> None:
    contract = json.loads(STATIC_CONTRACT.read_text(encoding="utf-8"))
    for key in (
        "authorization",
        "standing_delegation",
        "predecessor_static_receipt",
        "gateway_admissible_route",
        "gateway_admissible_pose_family",
        "physical_no_contact_route_receipt",
        "rehearsal_contract",
        "temporal_plan",
        "geometry_source",
        "scene_implementation",
        "articulated_robot_model",
        "candidate_manifest",
        "registration_candidate",
        "implementation",
    ):
        binding = contract[key]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    grid = contract["parameter_grid"]
    assert len(grid["setup_branches"]) == 3
    assert grid["approach_lateral_offsets_m"] == [-0.035, 0.0, 0.035]
    assert grid["cells_per_family"] == 9
    assert grid["maximum_total_cells"] == 44 * 9
    assert grid["finite_and_nonexpandable_after_freeze"] is True
    assert contract["endpoint_geometry"] == {
        "contact_offset_m": 0.022,
        "contact_height_m": 0.03,
        "stroke_m": 0.09,
        "precontact_clearance_height_above_pawn_base_m": 0.06,
        "inside_v05_tk_bounds": True,
        "static_only_subset_rule": (
            "largest offset and height plus shortest stroke were the uniquely "
            "selected geometry of both V05-TW statically safe family winners; "
            "this uses no dynamic consequence and minimizes the new successor "
            "to the alternate-start, IK-branch, and approach mechanism"
        ),
    }
    assert contract["start_envelope"]["teleport_forbidden"] is True
    assert contract["selection"]["selected_family_count"] == 4
    assert (
        contract["selection"]["minimum_distinct_families_per_direction"]
        == 2
    )
    assert contract["selection"]["dynamic_outcome_used"] is False
    assert contract["authority"]["model_loading"] is True
    assert contract["authority"]["static_simulation"] is True
    assert contract["authority"]["dynamic_replay"] is False
    assert contract["authority"]["physical_motion"] is False


def test_multistart_approach_static_receipt_admits_four_families_only() -> None:
    receipt = json.loads(STATIC_RECEIPT.read_text(encoding="utf-8"))
    assert _sha(STATIC_RECEIPT) == (
        "60554324e566c3b53513cb207f8eb7890a35afc6c18be945be50c0a1f31c7d13"
    )
    assert receipt["status"] == "multistart_approach_static_freeze_pass"
    assert receipt["grid_result_count"] == 396
    assert receipt["quarantine_leaked_into_candidates"] is False
    assert receipt["selection_used_dynamic_outcomes"] is False
    assert receipt["statically_eligible_family_count"] == 5
    assert receipt["selected_family_count"] == 4
    assert receipt["lane_counts"] == {
        "REAL_TO_SIM": 2,
        "SIM_TO_REAL": 2,
    }
    assert len({row["family_id"] for row in receipt["eligible_cases"]}) == 4
    assert receipt["dynamic_replay_executed"] is False
    assert receipt["physical_motion"] is False
    assert receipt["physical_task_attempts"] == 0


def test_progress_exclusion_successor_authorization_quarantines_all_outcomes() -> None:
    authorization = json.loads(
        PROGRESS_SUCCESSOR_AUTHORIZATION.read_text(encoding="utf-8")
    )
    assert _sha(
        ROOT / authorization["standing_delegation"]["path"]
    ) == authorization["standing_delegation"]["sha256"]
    for binding in authorization["immutable_predecessors"].values():
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert authorization["quarantine"]["exact_count"] == 8
    assert authorization["quarantine"]["case_ids"][-4:] == [
        "tan_pawn_h7__h7_h8",
        "tan_pawn_h7__h7_h6",
        "brown_pawn_e2__e2_d2",
        "tan_pawn_f7__f7_f8",
    ]
    assert authorization["authority"]["static_design"] is True
    assert not any(
        value
        for key, value in authorization["authority"].items()
        if key != "static_design"
    )


def test_multistart_temporal_contract_binds_exact_actions_before_replay() -> None:
    contract = json.loads(TEMPORAL_CONTRACT.read_text(encoding="utf-8"))
    for key in (
        "standing_delegation",
        "manager_authorization",
        "static_contract",
        "static_receipt",
        "rehearsal_contract",
        "temporal_plan",
        "implementation",
    ):
        binding = contract[key]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert [row["direction_lane"] for row in contract["cases"]] == [
        "REAL_TO_SIM",
        "SIM_TO_REAL",
        "REAL_TO_SIM",
        "SIM_TO_REAL",
    ]
    for case in contract["cases"]:
        assert _sha(ROOT / case["action_path"]) == case["action_sha256"]
    assert contract["plant_paths"] == [
        {
            "path_id": "canonical_direct_target",
            "kind": "direct_target_mujoco",
            "delay_seconds": 0.0,
            "diagnostic_only": False,
        },
        {
            "path_id": "diagnostic_zoh_110ms",
            "kind": "zero_order_hold_command_delay",
            "delay_seconds": 0.11,
            "diagnostic_only": True,
            "not_physical_latency_or_calibrated_plant": True,
        },
    ]
    assert contract["acceptance"]["minimum_cases_per_direction"] == 2
    assert contract["authority"]["dynamic_simulation"] is True
    assert contract["authority"]["v06_evaluator_freeze"] is False
    assert contract["authority"]["physical_motion"] is False


def test_multistart_temporal_receipt_closes_without_v06_or_physical() -> None:
    receipt = json.loads(TEMPORAL_RECEIPT.read_text(encoding="utf-8"))
    assert _sha(TEMPORAL_RECEIPT) == (
        "50548090c8628aa0d85cd8a72696215a8a8fcbdb2f89dc9b230f9c3883bde37c"
    )
    assert receipt["status"] == "temporal_replay_reject"
    assert receipt["passing_case_ids"] == []
    assert receipt["lane_counts"] == {
        "REAL_TO_SIM": 0,
        "SIM_TO_REAL": 0,
    }
    for case in receipt["results"]:
        assert case["passed_both_paths"] is False
        for path in case["plant_paths"]:
            assert all(path["identity_checks"].values())
    assert receipt["candidate_refit"] is False
    assert receipt["task_outcomes_used_for_action_selection"] is False
    assert receipt["physical_motion"] is False
    assert receipt["physical_task_attempts"] == 0

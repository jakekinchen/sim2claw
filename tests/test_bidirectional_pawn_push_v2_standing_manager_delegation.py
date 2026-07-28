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

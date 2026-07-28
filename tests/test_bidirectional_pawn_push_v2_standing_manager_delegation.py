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

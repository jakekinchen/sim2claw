from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_wrist_path_successor_authorization_v1.json"
)
STATIC_CONTRACT = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_wrist_path_static_v1.json"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_wrist_path_authorization_preserves_quarantine_gates_and_false_authority() -> None:
    authorization = json.loads(AUTHORIZATION.read_text(encoding="utf-8"))
    for binding in authorization["immutable_predecessors"].values():
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert authorization["quarantine"]["case_ids"] == [
        "brown_pawn_b1__b1_b2",
        "brown_pawn_a2__a2_a1",
        "brown_pawn_a2__a2_a3",
        "brown_pawn_e2__e2_e3",
    ]
    assert authorization["v05_tk_selected_static_cases"][
        "dynamic_outcomes_observed"
    ] is False
    assert authorization["authorized_static_design"][
        "preserved_dimensions"
    ] == {
        "contact_center_offsets_m": [0.016, 0.019, 0.022],
        "contact_heights_m": [0.018, 0.024, 0.03],
        "stroke_lengths_m": [0.09, 0.105, 0.12],
    }
    invariants = authorization["frozen_invariants"]
    assert invariants["closed_jaw_rad"] == -0.1727003294848389
    assert invariants["sample_hz"] == 40.0
    assert invariants["minimum_signed_progress_mm"] == 36.025
    assert invariants["minimum_distinct_families_per_direction"] == 2
    assert authorization["authority"]["static_design"] is True
    assert not any(
        value
        for key, value in authorization["authority"].items()
        if key != "static_design"
    )


def test_wrist_path_static_contract_is_finite_static_only_and_hash_bound() -> None:
    contract = json.loads(STATIC_CONTRACT.read_text(encoding="utf-8"))
    for key in (
        "authorization",
        "predecessor_static_receipt",
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
    assert grid["wrist_roll_targets_rad"] == [
        -1.9562840850723129,
        -1.8036347566770476,
        -1.6509854282817824,
    ]
    assert grid["precontact_clearance_height_above_pawn_base_m"] == 0.06
    assert grid["contact_center_offsets_m"] == [0.016, 0.019, 0.022]
    assert grid["contact_heights_m"] == [0.018, 0.024, 0.03]
    assert grid["stroke_lengths_m"] == [0.09, 0.105, 0.12]
    assert grid["cells_per_family"] == 81
    assert grid["maximum_total_cells"] == 44 * 81
    assert grid["finite_and_nonexpandable_after_freeze"] is True
    assert contract["geometry_derivation"]["dynamic_consequence_used"] is False
    assert contract["selection"]["dynamic_outcome_used"] is False
    assert contract["selection"]["selected_family_count"] == 4
    assert (
        contract["selection"]["minimum_distinct_families_per_direction"]
        == 2
    )
    assert contract["authority"]["model_loading"] is True
    assert contract["authority"]["static_simulation"] is True
    assert not any(
        contract["authority"][key]
        for key in (
            "dynamic_replay",
            "v06_evaluator_freeze",
            "counted_action_compilation",
            "camera",
            "gateway",
            "serial",
            "physical_motion",
            "physical_task_attempt",
            "simulator_promotion",
            "transfer_claim",
        )
    )

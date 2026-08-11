from __future__ import annotations

from sim2claw.pawn_bg_e2_strict_baseline import load_contract, load_raw_contract


def test_or148_contract_is_exact_action_and_parameter_unchanged() -> None:
    raw = load_raw_contract()
    contract = load_contract()
    assert raw["source_bindings"]["action_sha256"] == (
        "a8121830d7a3284094ca0e109d621b7585e4692b86fe33f3fe42cd5c1f412bcc"
    )
    assert raw["action_invariance"]["shape"] == [418, 6]
    assert raw["candidate_order"] == [
        {
            "candidate_id": "e2_rank02_rigid_baseline",
            "kind": "retained_rank02_parameter_reproduction",
            "parameter_overrides": {},
        }
    ]
    assert contract["execution"]["simulator_replays"] == 1
    assert contract["execution"]["parameter_changes"] == 0
    assert not any(contract["authority"].values())


def test_or148_retains_strict_sequence_and_collision_gates() -> None:
    contract = load_contract()
    gates = contract["supplemental_gates"]
    assert gates["minimum_sustained_lift_m"] == 0.04
    assert gates["minimum_carry_toward_target_m"] == 0.022225
    assert gates["maximum_tilt_degrees_every_step"] == 10.0
    assert gates["require_no_robot_or_selected_contact_with_wrong_pawn"] is True
    assert gates["require_qualified_grasp_then_lift_then_carry_then_target_entry_then_release_then_settle"] is True

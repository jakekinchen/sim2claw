from __future__ import annotations

from sim2claw.observable_registration_measured_state_pad_bracket import (
    EXPECTED_LOCAL_Z,
    EXPECTED_OFFSETS,
    _selection_key,
    load_measured_state_pad_bracket_contract,
)


def test_pad_bracket_contract_is_exact_and_action_frozen() -> None:
    contract = load_measured_state_pad_bracket_contract()

    assert contract["fixed_pad_grid"]["fixed_coverage_offsets_m"] == EXPECTED_OFFSETS
    assert contract["fixed_pad_grid"]["implied_fixed_pad_local_z_m"] == EXPECTED_LOCAL_Z
    assert contract["trajectory"]["robot_driver"] == "raw_follower_actual_position_degrees"
    assert contract["simulation"]["object_pose_injection_allowed"] is False


def test_selector_ignores_terminal_outcome() -> None:
    base = {
        "fixed_coverage_offset_m": 0.02,
        "preterminal_report": {
            "gate_count": 4,
            "interval_residual_samples": 3,
            "tilt_at_sample_260_degrees": 8.0,
        },
    }
    changed_terminal = {
        **base,
        "result": {"natural_dynamics": {"outcome": {"numeric_task_success": True}}},
    }

    assert _selection_key(base) == _selection_key(changed_terminal)

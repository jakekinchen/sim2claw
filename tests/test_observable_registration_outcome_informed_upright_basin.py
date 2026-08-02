from __future__ import annotations

from sim2claw.observable_registration_outcome_informed_upright_basin import (
    EXPECTED_LOCAL_Z,
    EXPECTED_OFFSETS,
    _selection_key,
    load_outcome_informed_upright_basin_contract,
)


def _row(
    *,
    full: bool,
    numeric: bool,
    terminal_gate_count: int,
    planar_error: float,
    final_tilt: float,
    event_gate_count: int,
) -> dict[str, object]:
    terminal_gates = {
        f"gate_{index}": index < terminal_gate_count for index in range(7)
    }
    return {
        "fixed_pad_local_z_m": -0.113,
        "report": {
            "full_gate_pass": full,
            "preterminal": {
                "gate_count": event_gate_count,
                "interval_residual_samples": 0,
            },
            "terminal": {
                "numeric_task_success": numeric,
                "gates": terminal_gates,
                "final_planar_center_error_m": planar_error,
                "final_upright_tilt_degrees": final_tilt,
            },
        },
    }


def test_contract_refines_only_the_or49_upright_basin() -> None:
    contract = load_outcome_informed_upright_basin_contract()
    grid = contract["fixed_pad_upright_basin_grid"]

    assert grid["fixed_coverage_offsets_m"] == EXPECTED_OFFSETS
    assert grid["implied_fixed_pad_local_z_m"] == EXPECTED_LOCAL_Z
    assert len(EXPECTED_OFFSETS) == 25
    assert EXPECTED_LOCAL_Z[0] == -0.11312
    assert EXPECTED_LOCAL_Z[-1] == -0.11288
    assert contract["trajectory"]["action_or_state_assistance_allowed"] is False
    assert grid["outcome_informed_quarantine_permanent"] is True


def test_selector_prefers_full_then_numeric_then_closest_terminal() -> None:
    full = _row(
        full=True,
        numeric=True,
        terminal_gate_count=7,
        planar_error=0.005,
        final_tilt=5.0,
        event_gate_count=5,
    )
    numeric_only = _row(
        full=False,
        numeric=True,
        terminal_gate_count=7,
        planar_error=0.001,
        final_tilt=1.0,
        event_gate_count=1,
    )
    near_negative = _row(
        full=False,
        numeric=False,
        terminal_gate_count=6,
        planar_error=0.007,
        final_tilt=0.0,
        event_gate_count=4,
    )
    far_negative = _row(
        full=False,
        numeric=False,
        terminal_gate_count=6,
        planar_error=0.012,
        final_tilt=0.0,
        event_gate_count=5,
    )

    assert _selection_key(full) < _selection_key(numeric_only)
    assert _selection_key(numeric_only) < _selection_key(near_negative)
    assert _selection_key(near_negative) < _selection_key(far_negative)

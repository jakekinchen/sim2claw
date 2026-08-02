from __future__ import annotations

from sim2claw.observable_registration_outcome_informed_fixed_pad_breakpoint import (
    EXPECTED_LOCAL_Z,
    EXPECTED_OFFSETS,
    _selection_key,
    load_outcome_informed_fixed_pad_breakpoint_contract,
)


def _row(
    *,
    full: bool,
    gate_count: int,
    interval_residual: int,
    planar_error: float,
    tilt_260: float,
    final_tilt: float,
    height_error: float = 0.0,
    fixed_z: float = -0.113,
) -> dict[str, object]:
    return {
        "fixed_pad_local_z_m": fixed_z,
        "report": {
            "full_gate_pass": full,
            "preterminal": {
                "gate_count": gate_count,
                "interval_residual_samples": interval_residual,
                "tilt_at_sample_260_degrees": tilt_260,
            },
            "terminal": {
                "final_planar_center_error_m": planar_error,
                "final_upright_tilt_degrees": final_tilt,
                "final_height_error_m": height_error,
            },
        },
    }


def test_contract_freezes_one_exact_episode_geometry_coordinate() -> None:
    contract = load_outcome_informed_fixed_pad_breakpoint_contract()
    grid = contract["fixed_pad_breakpoint_grid"]

    assert grid["fixed_coverage_offsets_m"] == EXPECTED_OFFSETS
    assert grid["implied_fixed_pad_local_z_m"] == EXPECTED_LOCAL_Z
    assert len(EXPECTED_OFFSETS) == 19
    assert contract["trajectory"]["robot_driver"] == (
        "raw_follower_actual_position_degrees"
    )
    assert contract["simulation"]["object_pose_injection_allowed"] is False
    assert grid["terminal_position_or_task_outcome_used_for_selection"] is True
    assert grid["outcome_informed_quarantine_permanent"] is True


def test_selector_prefers_complete_replay_then_event_and_terminal_quality() -> None:
    incomplete = _row(
        full=False,
        gate_count=5,
        interval_residual=0,
        planar_error=0.0,
        tilt_260=0.0,
        final_tilt=0.0,
    )
    complete = _row(
        full=True,
        gate_count=5,
        interval_residual=0,
        planar_error=0.005,
        tilt_260=5.0,
        final_tilt=5.0,
    )
    stronger_event_timing = _row(
        full=False,
        gate_count=4,
        interval_residual=1,
        planar_error=0.004,
        tilt_260=3.0,
        final_tilt=4.0,
    )
    weaker_event_timing = _row(
        full=False,
        gate_count=3,
        interval_residual=0,
        planar_error=0.001,
        tilt_260=1.0,
        final_tilt=1.0,
    )

    assert _selection_key(complete) < _selection_key(incomplete)
    assert _selection_key(stronger_event_timing) < _selection_key(
        weaker_event_timing
    )

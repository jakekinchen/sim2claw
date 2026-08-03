from sim2claw.observable_registration_post_final_persistent_static_enclosure_boundary_line_identifiability import (
    _angle_delta,
    _segment,
    load_post_final_persistent_static_enclosure_boundary_line_identifiability_contract,
)


def test_contract_freezes_one_no_refit_line_family() -> None:
    contract = load_post_final_persistent_static_enclosure_boundary_line_identifiability_contract()
    assert contract["line_extractor"]["orientation_bin_width_degrees"] == 10
    assert contract["split"]["validation_never_changes_orientation_or_rho"] is True
    assert contract["resource_boundary"]["renders_allowed"] == 0
    assert contract["resource_boundary"]["geometry_values_produced_allowed"] == 0


def test_segment_orientation_and_wrapped_delta_are_deterministic() -> None:
    segment = _segment(10, 10, 30, 30, 10.0)
    assert segment["orientation_bin_degrees"] == 40.0
    assert abs(segment["length_px"] - 28.2842712475) < 1e-9
    assert _angle_delta(179.0, 1.0) == 2.0

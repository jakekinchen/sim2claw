import numpy as np

from sim2claw.observable_registration_post_final_two_material_shaft_terminal_calibration import (
    _interpolate_bgr,
    load_post_final_two_material_shaft_terminal_calibration_contract,
)


def test_contract_freezes_bounded_grid_and_validation_no_refit() -> None:
    contract = load_post_final_two_material_shaft_terminal_calibration_contract()
    assert contract["material_grid"]["candidate_count"] == 16
    assert contract["material_grid"]["validation_refit"] is False
    assert contract["frozen_geometry"]["total_triangle_count"] == 348
    assert contract["resource_boundary"]["simulator_replays_allowed"] == 0


def test_interpolation_is_deterministic_and_rounded() -> None:
    assert np.array_equal(_interpolate_bgr([100, 110, 120], [130, 140, 150], 1.0 / 3.0), [110, 120, 130])

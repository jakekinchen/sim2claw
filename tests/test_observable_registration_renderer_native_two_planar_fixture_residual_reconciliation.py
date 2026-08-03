from __future__ import annotations

from sim2claw.observable_registration_renderer_native_two_planar_fixture_residual_reconciliation import (
    _merged_or120_contract,
    load_two_planar_fixture_residual_reconciliation_contract,
)


def test_or132_contract_closes_render_fit_and_retry() -> None:
    contract = load_two_planar_fixture_residual_reconciliation_contract()

    assert contract["resource_boundary"]["renders_allowed"] == 0
    assert contract["resource_boundary"]["fits_allowed"] == 0
    assert contract["resource_boundary"]["retries_allowed"] == 0
    assert contract["resource_boundary"]["paid_compute_allowed"] is False


def test_or132_merged_contract_preserves_or120_measurement_rules() -> None:
    contract = load_two_planar_fixture_residual_reconciliation_contract()
    merged = _merged_or120_contract(contract)

    assert merged["edge_occupancy"]["persistent_minimum_frame_fraction"] == 0.80
    assert merged["edge_occupancy"]["dynamic_minimum_frame_fraction"] == 0.05
    assert merged["dominance_rule"]["minimum_adequate_factor_f1"] == 0.60
    assert merged["sources"]["or119_receipt"] == contract["sources"]["or131_receipt"]


def test_or132_binds_exact_full_timeline_frame_budget() -> None:
    contract = load_two_planar_fixture_residual_reconciliation_contract()

    assert contract["resource_boundary"]["physical_frames_read_allowed"] == 1210
    assert contract["resource_boundary"]["candidate_frames_read_allowed"] == 1210

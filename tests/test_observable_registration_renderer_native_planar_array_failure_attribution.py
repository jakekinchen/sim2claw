from __future__ import annotations

from sim2claw.observable_registration_renderer_native_planar_array_failure_attribution import (
    _select_failure_family,
    load_failure_attribution_contract,
)


def test_or123_contract_is_map_and_montage_only() -> None:
    contract = load_failure_attribution_contract()

    assert contract["montage_panels"]["row_count"] == 7
    assert contract["resource_boundary"]["source_video_decodes_allowed"] == 0
    assert contract["resource_boundary"]["candidate_video_decodes_allowed"] == 0
    assert contract["resource_boundary"]["renders_allowed"] == 0
    assert contract["resource_boundary"]["fits_allowed"] == 0
    assert contract["resource_boundary"]["searches_allowed"] == 0
    assert contract["claim_limits"]["specific_object_identity"] is False


def test_or123_selects_sparse_support_only_after_projection_and_material_pass() -> None:
    rules = {
        "projection_minimum_expected_line_coverage": 0.85,
        "projection_maximum_endpoint_reprojection_error_px": 1e-8,
        "material_minimum_mean_residual_improvement": 0.0,
        "material_minimum_mean_improved_pixel_fraction": 0.55,
        "support_detail_maximum_consensus_coverage": 0.65,
    }
    metrics = {
        "expected_line_coverage_by_added_support": 0.95,
        "maximum_endpoint_reprojection_error_px": 1e-13,
        "mean_added_support_residual_improvement": 3.0,
        "mean_improved_pixel_fraction": 0.7,
        "persistent_consensus_coverage_by_added_support": 0.3,
    }

    selected, gates = _select_failure_family(metrics, rules)

    assert selected == "sparse_boundary_support_and_missing_rectilinear_detail"
    assert all(gates.values())


def test_or123_projection_precedes_material_and_support_in_decision_tree() -> None:
    rules = {
        "projection_minimum_expected_line_coverage": 0.85,
        "projection_maximum_endpoint_reprojection_error_px": 1e-8,
        "material_minimum_mean_residual_improvement": 0.0,
        "material_minimum_mean_improved_pixel_fraction": 0.55,
        "support_detail_maximum_consensus_coverage": 0.65,
    }
    metrics = {
        "expected_line_coverage_by_added_support": 0.2,
        "maximum_endpoint_reprojection_error_px": 1e-13,
        "mean_added_support_residual_improvement": -1.0,
        "mean_improved_pixel_fraction": 0.1,
        "persistent_consensus_coverage_by_added_support": 0.1,
    }

    selected, _ = _select_failure_family(metrics, rules)

    assert selected == "tabletop_plane_or_projection_alignment_failure"

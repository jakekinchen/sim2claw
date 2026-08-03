from __future__ import annotations

import numpy as np

from sim2claw.observable_registration_post_object_full_timeline_residual_reconciliation_identity_reproduction import (
    _select_successor,
    _unmatched_residuals,
    load_identity_reproduction_contract,
)


def test_or120b_contract_binds_source_identities_and_zero_resource_boundary() -> None:
    contract = load_identity_reproduction_contract()

    assert set(contract["frozen_identities"]) == {"implementation", "test"}
    assert contract["edge_occupancy"]["persistent_minimum_frame_fraction"] == 0.80
    assert contract["decision_rule"]["minimum_dominant_deficit_ratio"] == 3.0
    assert contract["resource_boundary"]["renders_allowed"] == 0
    assert contract["resource_boundary"]["fits_allowed"] == 0
    assert contract["resource_boundary"]["retries_allowed"] == 0
    assert contract["claim_limits"]["same_video_semantic_match"] is False


def test_or120b_unmatched_residuals_respect_tolerance_and_region() -> None:
    physical = np.zeros((8, 8), dtype=bool)
    candidate = np.zeros((8, 8), dtype=bool)
    region = np.ones((8, 8), dtype=bool)
    physical[3, 3] = True
    physical[6, 6] = True
    candidate[3, 4] = True
    candidate[1, 1] = True
    region[1, 1] = False

    physical_only, candidate_only = _unmatched_residuals(physical, candidate, region, 3)

    assert physical_only.sum() == 1
    assert physical_only[6, 6]
    assert candidate_only.sum() == 0


def test_or120b_selects_only_cross_episode_three_x_dominance() -> None:
    rule = load_identity_reproduction_contract()["decision_rule"]
    selected = _select_successor([0.30] * 11, [0.56] * 11, rule)
    unresolved = _select_successor([0.30] * 8 + [0.58] * 3, [0.56] * 8 + [0.30] * 3, rule)

    assert selected["selected_residual_family"] == "post_object_persistent_static_spatial_decomposition"
    assert selected["episodes_persistent_deficit_dominant"] == 11
    assert unresolved["selected_residual_family"] == "retained_post_object_residual_lane_unresolved"

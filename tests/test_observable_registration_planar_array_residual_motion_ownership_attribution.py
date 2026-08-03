from __future__ import annotations

import numpy as np

from sim2claw.observable_registration_planar_array_residual_motion_ownership_attribution import (
    _classify_episode,
    _translation_measurement,
    load_motion_ownership_contract,
)


def test_or124_contract_freezes_development_gated_no_refit_corroboration() -> None:
    contract = load_motion_ownership_contract()

    assert contract["split"]["development_positions"] == list(range(1, 8))
    assert contract["split"]["corroboration_positions"] == list(range(8, 12))
    assert contract["split"]["corroboration_requires_decisive_development"] is True
    assert contract["split"]["corroboration_refit_allowed"] is False
    assert contract["resource_boundary"]["renders_allowed"] == 0
    assert contract["resource_boundary"]["geometry_or_material_fits_allowed"] == 0
    assert contract["claim_limits"]["specific_object_identity"] is False


def test_translation_measurement_recovers_known_shift() -> None:
    target = np.zeros((32, 32), dtype=bool)
    target[8:20, 10] = True
    target[19, 10:19] = True
    edges = np.zeros_like(target)
    edges[8:20, 14] = True
    edges[19, 14:23] = True

    result = _translation_measurement(target, edges, radius=8)

    assert result["best_translation_xy"] == [4, 0]
    assert result["best_support_fraction"] == 1.0
    assert result["fixed_support_fraction"] < 0.5


def test_episode_classifier_prefers_static_only_with_fixed_support_and_low_motion() -> None:
    decision = {
        "moving_minimum_translation_px": 3.0,
        "moving_minimum_translation_gain": 0.1,
        "static_minimum_median_fixed_support_fraction": 0.55,
        "static_maximum_moving_frame_fraction": 0.2,
        "attached_minimum_moving_frame_fraction": 0.5,
        "attached_minimum_median_best_support_fraction": 0.55,
    }
    rows = [
        {
            "best_translation_distance_px": 0.0,
            "translation_gain": 0.0,
            "fixed_support_fraction": 0.8,
            "best_support_fraction": 0.8,
        }
        for _ in range(10)
    ]

    label, summary = _classify_episode(rows, decision)

    assert label == "workcell_static"
    assert summary["moving_frame_fraction"] == 0.0

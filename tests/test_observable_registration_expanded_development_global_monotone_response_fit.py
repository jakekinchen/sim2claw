from __future__ import annotations

import numpy as np

from sim2claw.observable_registration_expanded_development_global_monotone_response_fit import (
    apply_monotone_response,
    load_expanded_development_global_monotone_response_fit_contract,
    response_lut,
)


def test_contract_freezes_expanded_development_and_seals_fresh_roles() -> None:
    contract = load_expanded_development_global_monotone_response_fit_contract()

    assert [row["split_position"] for row in contract["expanded_development_episodes"]] == list(range(1, 8))
    assert contract["response_family"]["candidate_count"] == 125
    assert contract["response_family"]["spatial_parameters"] == 0
    assert contract["response_family"]["per_channel_parameters"] == 0
    assert contract["acceptance"]["minimum_pooled_mean_tolerant_edge_f1"] == 0.42
    assert contract["resource_boundary"]["fresh_validation_reads_allowed"] == 0
    assert contract["resource_boundary"]["final_evaluator_heldout_reads_allowed"] == 0
    assert not any(contract["authority"].values())


def test_piecewise_response_is_global_channel_identical_and_monotone() -> None:
    lut = response_lut(bias=32.0, low_slope=0.85, high_slope=0.35, knot=128)
    assert lut.shape == (256,)
    assert np.all(np.diff(lut.astype(np.int16)) >= 0)
    frame = np.asarray([[[0, 64, 128], [128, 192, 255]]], dtype=np.uint8)
    transformed = apply_monotone_response(
        frame, bias=32.0, low_slope=0.85, high_slope=0.35, knot=128
    )
    assert np.array_equal(transformed, lut[frame])
    assert transformed.dtype == np.uint8

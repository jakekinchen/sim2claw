from __future__ import annotations

import numpy as np

from sim2claw.observable_registration_expanded_development_global_monotone_response_fit import apply_monotone_response
from sim2claw.observable_registration_reject_only_fresh_validation_global_monotone_response import load_reject_only_fresh_validation_global_monotone_response_contract


def test_contract_freezes_two_fresh_validation_episodes_and_final_holdout() -> None:
    contract = load_reject_only_fresh_validation_global_monotone_response_contract()

    assert [row["split_position"] for row in contract["fresh_validation_episodes"]] == [8, 9]
    assert contract["gates"]["expected_total_frame_count"] == 213
    assert contract["frozen_candidate"]["refit_or_selection_allowed"] is False
    assert contract["resource_boundary"]["fits_or_candidate_selections_allowed"] == 0
    assert contract["resource_boundary"]["final_evaluator_heldout_reads_allowed"] == 0
    assert not any(contract["authority"].values())


def test_frozen_validation_response_is_exact_or89_curve() -> None:
    contract = load_reject_only_fresh_validation_global_monotone_response_contract()
    response = contract["frozen_candidate"]["global_monotone_response"]
    frame = np.arange(256, dtype=np.uint8).reshape(1, 256, 1).repeat(3, axis=2)
    transformed = apply_monotone_response(
        frame,
        bias=response["bias"],
        low_slope=response["low_intensity_slope"],
        high_slope=response["high_intensity_slope"],
        knot=response["fixed_input_knot"],
    )
    assert np.all(np.diff(transformed[0, :, 0].astype(np.int16)) >= 0)
    assert np.array_equal(transformed[:, :, 0], transformed[:, :, 1])

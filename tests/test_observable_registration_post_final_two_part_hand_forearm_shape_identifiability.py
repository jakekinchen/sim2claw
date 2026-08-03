import numpy as np

from sim2claw.observable_registration_post_final_two_part_hand_forearm_shape_identifiability import (
    _two_part_capsules,
    load_post_final_two_part_hand_forearm_shape_identifiability_contract,
)


def test_contract_freezes_one_median_split_without_render_or_search() -> None:
    contract = load_post_final_two_part_hand_forearm_shape_identifiability_contract()
    assert contract["two_part_rule"]["split_quantile"] == 0.5
    assert contract["two_part_rule"]["split_search"] is False
    assert contract["resource_boundary"]["fits_or_candidate_searches_allowed"] == 0
    assert contract["resource_boundary"]["renders_allowed"] == 0


def test_two_part_capsules_are_deterministic_and_supported() -> None:
    component = np.zeros((80, 120), dtype=bool)
    component[35:45, 20:85] = True
    component[28:52, 75:105] = True
    spec = {"endpoint_percentiles": [5.0, 95.0], "radius_percentile_of_absolute_minor_projection": 90.0, "minimum_radius_px": 2}
    first = _two_part_capsules(component, spec)
    second = _two_part_capsules(component, spec)
    assert np.array_equal(first[0], second[0])
    assert len(first[1]) == 2
    assert first[2]["supported"] is True
    assert np.count_nonzero(first[0]) > 0

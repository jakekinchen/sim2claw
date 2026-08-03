from __future__ import annotations

import numpy as np

from sim2claw.observable_registration_post_final_single_capsule_dynamic_operator_shape_identifiability import (
    _capsule_mask,
    load_post_final_single_capsule_dynamic_operator_shape_identifiability_contract,
)


def test_or109_contract_freezes_deterministic_shape_without_renderer() -> None:
    contract = load_post_final_single_capsule_dynamic_operator_shape_identifiability_contract()
    assert contract["capsule_fit"]["endpoint_percentiles"] == [5.0, 95.0]
    assert contract["capsule_fit"]["optimization_or_search"] is False
    assert contract["resource_boundary"]["optimization_searches_allowed"] == 0
    assert contract["resource_boundary"]["renders_allowed"] == 0
    assert contract["resource_boundary"]["paid_compute_allowed"] is False
    assert not any(contract["authority"].values())


def test_or109_capsule_fit_is_deterministic_and_nonempty() -> None:
    component = np.zeros((80, 100), dtype=bool)
    component[30:50, 10:90] = True
    spec = load_post_final_single_capsule_dynamic_operator_shape_identifiability_contract()["capsule_fit"]
    first, first_meta = _capsule_mask(component, spec)
    second, second_meta = _capsule_mask(component, spec)
    assert np.array_equal(first, second)
    assert first_meta == second_meta
    assert first_meta["supported"] is True
    assert np.count_nonzero(first) > 0

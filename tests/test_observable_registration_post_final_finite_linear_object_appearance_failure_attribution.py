import numpy as np

from sim2claw.observable_registration_post_final_finite_linear_object_appearance_failure_attribution import (
    _partition_support,
    load_post_final_finite_linear_object_appearance_failure_attribution_contract,
)


def test_contract_is_development_montage_only_and_read_only() -> None:
    contract = load_post_final_finite_linear_object_appearance_failure_attribution_contract()
    assert contract["montage"]["development_only"] is True
    assert contract["resource_boundary"]["validation_pixel_reads_allowed"] == 0
    assert contract["resource_boundary"]["renders_allowed"] == 0
    assert contract["claim_limits"]["two_material_candidate_validated"] is False


def test_support_partition_is_disjoint_and_complete() -> None:
    baseline = np.zeros((20, 20, 3), dtype=np.uint8)
    candidate = baseline.copy()
    candidate[5:15, 2:18] = 50
    spec = {"candidate_minus_baseline_minimum_max_channel_difference": 1, "terminal_disk_radius_multiplier": 1.5}
    support, shaft, terminal = _partition_support(baseline, candidate, np.asarray([14.0, 10.0]), 3.0, spec)
    assert not np.any(shaft & terminal)
    assert np.array_equal(support, shaft | terminal)

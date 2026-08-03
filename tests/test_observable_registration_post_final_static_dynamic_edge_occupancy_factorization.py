from __future__ import annotations

import numpy as np

from sim2claw.observable_registration_post_final_static_dynamic_edge_occupancy_factorization import (
    _binary_tolerant_f1,
    load_post_final_static_dynamic_edge_occupancy_factorization_contract,
)


def test_or97_contract_freezes_occupancy_and_zero_render_boundary() -> None:
    contract = load_post_final_static_dynamic_edge_occupancy_factorization_contract()

    assert contract["edge_occupancy"]["persistent_minimum_frame_fraction"] == 0.80
    assert contract["edge_occupancy"]["dynamic_minimum_frame_fraction"] == 0.05
    assert contract["resource_boundary"]["renders_allowed"] == 0
    assert contract["resource_boundary"]["fits_allowed"] == 0
    assert contract["claim_limits"]["same_video_semantic_match"] is False


def test_binary_tolerant_f1_accepts_one_pixel_neighbor() -> None:
    physical = np.zeros((8, 8), dtype=bool)
    candidate = np.zeros((8, 8), dtype=bool)
    physical[3, 3] = True
    candidate[3, 4] = True
    region = np.ones((8, 8), dtype=bool)

    assert _binary_tolerant_f1(physical, candidate, region, 3)["f1"] == 1.0

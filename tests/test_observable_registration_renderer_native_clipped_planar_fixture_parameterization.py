from __future__ import annotations

import numpy as np

from sim2claw.observable_registration_renderer_native_clipped_planar_fixture_parameterization import (
    _pattern_score,
    _quad_is_valid,
    _rank_dictionary,
    load_clipped_planar_fixture_parameterization_contract,
)
from sim2claw.observable_registration_renderer_native_planar_fixture_parameterization import _procedural_cells


def test_or129_contract_keeps_corroboration_no_refit_and_image_borrowing_closed() -> None:
    contract = load_clipped_planar_fixture_parameterization_contract()

    assert contract["split"]["corroboration_refit_allowed"] is False
    assert contract["parameterization"]["physical_pixel_texture_projection"] is False
    assert contract["parameterization"]["screen_space_overlay"] is False
    assert contract["resource_boundary"]["renders_allowed"] == 0
    assert contract["claim_limits"]["metric_3d_geometry_calibrated"] is False


def test_or129_quad_gate_requires_one_clipped_corner() -> None:
    contract = load_clipped_planar_fixture_parameterization_contract()
    geometry = contract["geometry_bounds"]

    assert _quad_is_valid(np.asarray(geometry["initial_quad_px"], dtype=np.float64), geometry)
    visible_quad = np.asarray(geometry["initial_quad_px"], dtype=np.float64)
    visible_quad[2, 1] = 238.0
    assert not _quad_is_valid(visible_quad, geometry)


def test_or129_dictionary_rank_recovers_known_procedural_entry() -> None:
    contract = load_clipped_planar_fixture_parameterization_contract()
    search = dict(contract["development_search"])
    search["dictionary_entry_indices"] = [0, 1]
    search["rotations_quarter_turns"] = [0]
    cells = np.asarray(_procedural_cells(1), dtype=np.uint8)
    frame = np.zeros((240, 320), dtype=np.uint8)
    quad = np.asarray([[80, 40], [160, 40], [160, 120], [80, 120]], dtype=np.float32)
    for row in range(8):
        for column in range(8):
            y0, y1 = 40 + row * 10, 40 + (row + 1) * 10
            x0, x1 = 80 + column * 10, 80 + (column + 1) * 10
            frame[y0:y1, x0:x1] = int(cells[row, column]) * 255

    ranking = _rank_dictionary([frame], quad, search)

    assert ranking[0]["dictionary_entry_index"] == 1
    assert ranking[0]["balanced_accuracy"] == 1.0
    assert _pattern_score([frame], quad, cells, search)["score"] > 0.99

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from sim2claw.observable_registration_renderer_native_planar_fixture_static_comparison import _fixture_stream
from sim2claw.observable_registration_renderer_native_two_planar_fixture_static_comparison import (
    _mask_for_corners,
    load_two_planar_fixture_static_comparison_contract,
)


def test_or130_contract_requires_two_shared_zbuffer_procedural_fixtures() -> None:
    contract = load_two_planar_fixture_static_comparison_contract()

    assert contract["fixture"]["fixture_count"] == 2
    assert contract["fixture"]["total_fixture_triangle_count"] == 256
    assert contract["fixture"]["shared_zbuffer"] is True
    assert contract["fixture"]["physical_pixel_texture_projection"] is False
    assert contract["fixture"]["screen_space_overlay"] is False
    assert contract["split"]["corroboration_refit_allowed"] is False


def test_or130_complete_and_clipped_streams_each_have_128_triangles() -> None:
    root = Path(__file__).parents[1]
    contract = load_two_planar_fixture_static_comparison_contract()
    or119 = json.loads((root / contract["sources"]["or119_contract"]["path"]).read_text())
    or95 = json.loads((root / or119["sources"]["or95_contract"]["path"]).read_text())
    response = or95["frozen_candidate"]["global_monotone_response"]
    camera = or95["frozen_candidate"]["camera"]
    for source in ("or126_parameters", "or129_parameters"):
        parameters = json.loads((root / contract["sources"][source]["path"]).read_text())
        pixels, depths, colors = _fixture_stream(parameters, camera, contract, response)
        assert pixels.shape == (128, 3, 2)
        assert depths.shape == (128, 3)
        assert colors.shape == (128, 3)
        assert np.isfinite(pixels).all() and np.isfinite(depths).all()


def test_or130_clipped_fixture_mask_stays_image_bounded() -> None:
    root = Path(__file__).parents[1]
    contract = load_two_planar_fixture_static_comparison_contract()
    parameters = json.loads((root / contract["sources"]["or129_parameters"]["path"]).read_text())

    mask = _mask_for_corners(parameters["development_fitted_corners_px"], 9)

    assert mask.shape == (240, 320)
    assert mask.dtype == np.bool_
    assert 1500 < int(mask.sum()) < 5000

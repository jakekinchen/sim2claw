from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from sim2claw.observable_registration_renderer_native_planar_fixture_static_comparison import (
    _fixture_stream,
    load_planar_fixture_static_comparison_contract,
)


def test_or127_contract_requires_shared_zbuffer_and_no_texture() -> None:
    contract = load_planar_fixture_static_comparison_contract()

    assert contract["fixture"]["shared_zbuffer"] is True
    assert contract["fixture"]["physical_pixel_texture_projection"] is False
    assert contract["fixture"]["screen_space_overlay"] is False
    assert contract["resource_boundary"]["simulator_replays_allowed"] == 0


def test_or127_fixture_stream_has_exact_triangle_and_color_counts() -> None:
    contract = load_planar_fixture_static_comparison_contract()
    parameters = json.loads((Path(__file__).parents[1] / contract["sources"]["or126_parameters"]["path"]).read_text())
    or119 = json.loads((Path(__file__).parents[1] / contract["sources"]["or119_contract"]["path"]).read_text())
    response = or119["sources"] and json.loads((Path(__file__).parents[1] / or119["sources"]["or95_contract"]["path"]).read_text())["frozen_candidate"]["global_monotone_response"]
    camera = parameters["camera"]

    pixels, depths, colors = _fixture_stream(parameters, camera, contract, response)

    assert pixels.shape == (128, 3, 2)
    assert depths.shape == (128, 3)
    assert colors.shape == (128, 3)
    assert np.isfinite(pixels).all() and np.isfinite(depths).all()


def test_or127_fixture_uses_two_procedural_materials() -> None:
    contract = load_planar_fixture_static_comparison_contract()
    assert contract["fixture"]["black_target_bgr"] != contract["fixture"]["white_target_bgr"]

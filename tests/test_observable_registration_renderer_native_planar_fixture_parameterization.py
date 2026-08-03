from __future__ import annotations

import numpy as np

from sim2claw.observable_registration_renderer_native_planar_fixture_parameterization import (
    _procedural_cells,
    load_planar_fixture_parameterization_contract,
)


def test_or126_contract_forbids_pixel_texture_and_render() -> None:
    contract = load_planar_fixture_parameterization_contract()

    assert contract["parameterization"]["physical_pixel_texture_projection"] is False
    assert contract["resource_boundary"]["renders_allowed"] == 0
    assert contract["resource_boundary"]["physical_pixel_texture_projections_allowed"] == 0
    assert contract["claim_limits"]["metric_3d_geometry_calibrated"] is False


def test_or126_procedural_cells_are_binary_and_bordered() -> None:
    cells = np.asarray(_procedural_cells(0), dtype=np.uint8)

    assert cells.shape == (8, 8)
    assert set(np.unique(cells).tolist()) == {0, 1}
    assert np.all(cells[0] == 0) and np.all(cells[-1] == 0)
    assert np.all(cells[:, 0] == 0) and np.all(cells[:, -1] == 0)


def test_or126_procedural_entry_is_deterministic() -> None:
    assert _procedural_cells(0) == _procedural_cells(0)
    assert _procedural_cells(0) != _procedural_cells(1)

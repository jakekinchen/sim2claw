from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from sim2claw.post_cable_safe_return import _interpolate


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT / "configs/evaluations/post_cable_safe_return_static_v2.json"
)


def test_pan_away_return_is_exact_bounded_and_motion_free() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    route = contract["route"]
    waypoints = [np.asarray(row, dtype=float) for row in route["waypoints"]]
    parts = [
        _interpolate(start, target, route["maximum_step_degrees"])
        for start, target in zip(waypoints[:-1], waypoints[1:], strict=True)
    ]
    combined = np.vstack((parts[0], parts[1][1:], parts[2][1:]))
    assert list(combined.shape) == route["expected_shape"] == [270, 6]
    assert [
        len(parts[0]) - 1,
        len(parts[0]) + len(parts[1]) - 2,
        len(combined) - 1,
    ] == route["stage_boundary_rows"] == [90, 135, 269]
    assert np.array_equal(combined[0], waypoints[0])
    assert np.allclose(combined[-1], waypoints[-1], atol=1e-14, rtol=0.0)
    assert np.max(np.abs(np.diff(combined, axis=0))) <= 0.5
    assert contract["geometry"]["maximum_uncorrected_worsening_m"] == 0.0005
    assert contract["authority"]["physical_motion"] is False

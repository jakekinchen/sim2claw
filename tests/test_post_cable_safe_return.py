from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from sim2claw.post_cable_safe_return import _interpolate


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT / "configs/evaluations/post_cable_safe_return_static_v1.json"
)


def test_post_cable_return_route_is_bounded_two_stage_and_motion_free() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    route = contract["route"]
    start = np.asarray(route["start_degrees"], dtype=float)
    stage = np.asarray(route["stage_degrees"], dtype=float)
    target = np.asarray(route["target_degrees"], dtype=float)
    first = _interpolate(start, stage, route["maximum_step_degrees"])
    second = _interpolate(stage, target, route["maximum_step_degrees"])
    combined = np.vstack((first, second[1:]))
    assert list(combined.shape) == route["expected_shape"] == [90, 6]
    assert len(first) - 1 == route["stage_boundary_row"] == 45
    assert np.array_equal(combined[0], start)
    assert np.array_equal(combined[-1], target)
    assert np.max(np.abs(np.diff(combined, axis=0))) <= 0.5
    assert contract["authority"]["physical_motion"] is False
    assert contract["authority"]["physical_task_attempt"] is False

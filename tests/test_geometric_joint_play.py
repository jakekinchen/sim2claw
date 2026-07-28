from __future__ import annotations

import numpy as np
import pytest

from sim2claw.geometric_joint_play import (
    GeometricJointPlayError,
    _play_target,
)


def test_play_target_retains_bounded_directional_memory() -> None:
    previous = np.asarray([0.0, 0.0])
    rising = _play_target(
        previous,
        np.asarray([3.0, 8.0]),
        {0: 1.0},
        {0: 0.25},
    )
    reversing = _play_target(
        rising,
        np.asarray([2.5, 7.0]),
        {0: 1.0},
        {0: 0.25},
    )

    assert np.allclose(rising, [2.0, 8.0])
    assert np.allclose(reversing, [2.0, 7.0])


def test_play_target_rejects_negative_width() -> None:
    with pytest.raises(GeometricJointPlayError, match="negative"):
        _play_target(np.zeros(1), np.zeros(1), {0: -0.1}, {0: 0.1})

import numpy as np

from sim2claw.pawn_bg_f2_deformable_cap_verify import (
    _maximum_run,
    _quaternion_distance_degrees,
    _quaternion_tilt_degrees,
)


def test_continuous_upright_metric_rejects_mid_transfer_tip() -> None:
    angles = np.radians([0.0, 9.9, 10.1, 0.0])
    quaternions = np.column_stack(
        [
            np.cos(angles / 2.0),
            np.sin(angles / 2.0),
            np.zeros_like(angles),
            np.zeros_like(angles),
        ]
    )
    tilt = _quaternion_tilt_degrees(quaternions)
    np.testing.assert_allclose(tilt, [0.0, 9.9, 10.1, 0.0], atol=1e-10)
    assert float(np.max(tilt)) > 10.0


def test_run_length_requires_consecutive_steps() -> None:
    run, start, end = _maximum_run(
        np.asarray([False, True, True, False, True], dtype=bool)
    )
    assert (run, start, end) == (2, 1, 2)


def test_collateral_orientation_uses_quaternion_shortest_arc() -> None:
    initial = np.asarray([[[1.0, 0.0, 0.0, 0.0]]])
    observed = np.asarray(
        [
            [[1.0, 0.0, 0.0, 0.0]],
            [[-1.0, 0.0, 0.0, 0.0]],
            [[np.cos(np.radians(3.0)), 0.0, 0.0, np.sin(np.radians(3.0))]],
        ]
    )
    distances = _quaternion_distance_degrees(initial, observed)
    np.testing.assert_allclose(distances[:, 0], [0.0, 0.0, 6.0], atol=1e-10)

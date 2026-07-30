from __future__ import annotations

import numpy as np
import pytest

from sim2claw.exact_applied_state_schedule import (
    ExactAppliedStateScheduleError,
    build_exact_applied_state_schedule,
)


def test_schedule_matches_exact_replay_interpolation() -> None:
    states = np.asarray([[0.0, 1.0], [2.0, 3.0], [4.0, 7.0]])
    timestamps = np.asarray([10.0, 10.011, 10.021])

    schedule = build_exact_applied_state_schedule(
        states,
        timestamps,
        timestep_seconds=0.005,
    )

    assert len(schedule.rows) == 5
    assert schedule.interval_step_counts == [0, 2, 2]
    assert schedule.maximum_timestamp_quantization_error_seconds == pytest.approx(
        0.001
    )
    assert schedule.rows[0].source_sample_index == 0
    assert schedule.rows[1].source_sample_index == 1
    assert schedule.rows[1].alpha == pytest.approx(0.5)
    assert schedule.rows[1].qpos == pytest.approx((1.0, 2.0))
    assert schedule.rows[2].qpos == pytest.approx((2.0, 3.0))
    assert schedule.rows[3].qpos == pytest.approx((3.0, 5.0))
    assert schedule.rows[4].qpos == pytest.approx((4.0, 7.0))
    assert schedule.rows[1].qvel == pytest.approx(
        (2.0 / 0.011, 2.0 / 0.011)
    )


def test_schedule_rejects_invalid_identity() -> None:
    with pytest.raises(ExactAppliedStateScheduleError, match="strictly increasing"):
        build_exact_applied_state_schedule(
            np.zeros((2, 1)),
            np.asarray([0.0, 0.0]),
            timestep_seconds=0.005,
        )
    with pytest.raises(ExactAppliedStateScheduleError, match="row count"):
        build_exact_applied_state_schedule(
            np.zeros((2, 1)),
            np.asarray([0.0]),
            timestep_seconds=0.005,
        )

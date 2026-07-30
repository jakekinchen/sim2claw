"""Deterministically reproduce the exact applied-state interpolation schedule."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


class ExactAppliedStateScheduleError(ValueError):
    """The source identity cannot produce the frozen interpolation schedule."""


@dataclass(frozen=True)
class AppliedStateStep:
    source_sample_index: int
    interval_step_index: int
    interval_step_count: int
    alpha: float
    source_timestamp_seconds: float
    simulator_elapsed_seconds: float
    qpos: tuple[float, ...]
    qvel: tuple[float, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ExactAppliedStateSchedule:
    rows: tuple[AppliedStateStep, ...]
    interval_step_counts: list[int]
    timestep_seconds: float
    maximum_timestamp_quantization_error_seconds: float


def build_exact_applied_state_schedule(
    states: np.ndarray,
    timestamps: np.ndarray,
    *,
    timestep_seconds: float,
) -> ExactAppliedStateSchedule:
    values = np.asarray(states, dtype=np.float64)
    times = np.asarray(timestamps, dtype=np.float64)
    if values.ndim != 2 or values.shape[0] < 1:
        raise ExactAppliedStateScheduleError("states must be a nonempty matrix")
    if times.ndim != 1 or len(times) != len(values):
        raise ExactAppliedStateScheduleError(
            "timestamp row count does not match states"
        )
    if not np.all(np.isfinite(values)) or not np.all(np.isfinite(times)):
        raise ExactAppliedStateScheduleError("schedule inputs must be finite")
    if timestep_seconds <= 0.0 or not np.isfinite(timestep_seconds):
        raise ExactAppliedStateScheduleError("timestep must be positive")
    if len(times) > 1 and not np.all(np.diff(times) > 0.0):
        raise ExactAppliedStateScheduleError(
            "timestamps must be strictly increasing"
        )

    rows = [
        AppliedStateStep(
            source_sample_index=0,
            interval_step_index=0,
            interval_step_count=0,
            alpha=0.0,
            source_timestamp_seconds=float(times[0]),
            simulator_elapsed_seconds=0.0,
            qpos=tuple(float(value) for value in values[0]),
            qvel=tuple(0.0 for _ in values[0]),
        )
    ]
    interval_counts = [0]
    maximum_quantization_error = 0.0
    simulator_elapsed = 0.0
    for sample_index in range(1, len(values)):
        dt = float(times[sample_index] - times[sample_index - 1])
        nstep = max(1, round(dt / timestep_seconds))
        interval_counts.append(nstep)
        maximum_quantization_error = max(
            maximum_quantization_error,
            abs(nstep * timestep_seconds - dt),
        )
        previous = values[sample_index - 1]
        current = values[sample_index]
        velocity = (current - previous) / dt
        for interval_step_index in range(1, nstep + 1):
            alpha = interval_step_index / nstep
            pose = previous + alpha * (current - previous)
            simulator_elapsed += timestep_seconds
            rows.append(
                AppliedStateStep(
                    source_sample_index=sample_index,
                    interval_step_index=interval_step_index,
                    interval_step_count=nstep,
                    alpha=float(alpha),
                    source_timestamp_seconds=float(
                        times[sample_index - 1] + alpha * dt
                    ),
                    simulator_elapsed_seconds=float(simulator_elapsed),
                    qpos=tuple(float(value) for value in pose),
                    qvel=tuple(float(value) for value in velocity),
                )
            )
    return ExactAppliedStateSchedule(
        rows=tuple(rows),
        interval_step_counts=interval_counts,
        timestep_seconds=float(timestep_seconds),
        maximum_timestamp_quantization_error_seconds=float(
            maximum_quantization_error
        ),
    )


__all__ = [
    "AppliedStateStep",
    "ExactAppliedStateSchedule",
    "ExactAppliedStateScheduleError",
    "build_exact_applied_state_schedule",
]

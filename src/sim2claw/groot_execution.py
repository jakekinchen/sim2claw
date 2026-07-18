"""Deterministic execution adapters for GR00T action waypoints."""

from __future__ import annotations

from typing import Any

import numpy as np


ACTION_EXECUTION_ADAPTERS = frozenset({"sample_hold", "linear_same_phase"})


def sample_phase(contract: dict[str, Any], sample_step: int) -> str:
    """Resolve a sampled action row to the frozen generator phase schedule."""

    if sample_step < 0:
        raise ValueError("sample_step must be non-negative")
    stride = int(contract["episode"]["sample_every_physics_steps"])
    if stride < 1:
        raise ValueError("sample stride must be positive")
    cursor = 0
    for phase, physics_steps in contract["episode"]["phase_physics_steps"].items():
        count = int(physics_steps)
        if count % stride:
            raise ValueError(f"phase {phase} is not aligned to the sample stride")
        phase_samples = count // stride
        if sample_step < cursor + phase_samples:
            return str(phase)
        cursor += phase_samples
    settle_steps = int(contract["episode"]["settle_steps_after"])
    if settle_steps % stride:
        raise ValueError("settle phase is not aligned to the sample stride")
    if sample_step < cursor + settle_steps // stride:
        return "settle"
    raise ValueError(f"sample_step exceeds the frozen episode: {sample_step}")


def physics_targets_from_waypoints(
    contract: dict[str, Any],
    *,
    sample_step: int,
    current: np.ndarray,
    next_waypoint: np.ndarray | None,
    adapter: str,
) -> tuple[np.ndarray, dict[str, object]]:
    """Expand one model waypoint interval into deterministic physics targets.

    ``linear_same_phase`` reconstructs the clean-room generator's unsaved
    between-row ramp. At phase boundaries the current waypoint is held because
    the source generator completes the previous phase before computing the
    first target of the next phase.
    """

    if adapter not in ACTION_EXECUTION_ADAPTERS:
        raise ValueError(f"unsupported action execution adapter: {adapter}")
    current_array = np.asarray(current, dtype=np.float32)
    if current_array.ndim != 1 or not np.isfinite(current_array).all():
        raise ValueError("current waypoint must be a finite vector")
    stride = int(contract["episode"]["sample_every_physics_steps"])
    phase = sample_phase(contract, sample_step)
    interpolate = False
    next_array = current_array
    if adapter == "linear_same_phase" and next_waypoint is not None:
        candidate = np.asarray(next_waypoint, dtype=np.float32)
        if candidate.shape != current_array.shape or not np.isfinite(candidate).all():
            raise ValueError("next waypoint must match the finite current waypoint")
        try:
            next_phase = sample_phase(contract, sample_step + 1)
        except ValueError:
            next_phase = None
        if next_phase == phase:
            interpolate = True
            next_array = candidate

    targets = []
    for physics_substep in range(stride):
        if interpolate:
            blend = float(physics_substep) / float(stride)
            target = current_array + blend * (next_array - current_array)
        else:
            target = current_array
        targets.append(np.asarray(target, dtype=np.float32).copy())
    return np.stack(targets), {
        "adapter": adapter,
        "sample_phase": phase,
        "interpolated_to_next_waypoint": interpolate,
        "physics_substeps": stride,
        "blend_convention": (
            "physics_substep/sample_stride" if interpolate else "hold_current"
        ),
        "model_waypoints_only": True,
        "assistance_frames": 0,
    }

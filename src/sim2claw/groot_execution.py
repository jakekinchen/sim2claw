"""Deterministic execution adapters for GR00T action waypoints."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np


ACTION_EXECUTION_ADAPTERS = frozenset({"sample_hold", "linear_same_phase"})
TEMPORAL_ACTION_AGGREGATIONS = frozenset(
    {"latest", "mean", "median", "exponential"}
)


def rate_limit_action(
    target: np.ndarray,
    *,
    previous: np.ndarray,
    max_abs_delta: np.ndarray,
) -> tuple[np.ndarray, dict[str, object]]:
    """Apply a deterministic per-coordinate rate limit to a model target."""

    target_array = np.asarray(target, dtype=np.float32)
    previous_array = np.asarray(previous, dtype=np.float32)
    limit_array = np.asarray(max_abs_delta, dtype=np.float32)
    if target_array.ndim != 1 or not np.isfinite(target_array).all():
        raise ValueError("rate-limit target must be a finite vector")
    if previous_array.shape != target_array.shape or not np.isfinite(
        previous_array
    ).all():
        raise ValueError("rate-limit previous action must match the finite target")
    if limit_array.shape != target_array.shape or not np.isfinite(limit_array).all():
        raise ValueError("rate limits must match the finite target")
    if not np.all(limit_array > 0.0):
        raise ValueError("rate limits must be strictly positive")
    requested_delta = target_array - previous_array
    applied_delta = np.clip(requested_delta, -limit_array, limit_array)
    clipped = np.abs(requested_delta) > limit_array
    action = np.asarray(previous_array + applied_delta, dtype=np.float32)
    return action, {
        "coordinate_clipped": [bool(value) for value in clipped],
        "clipped_coordinate_count": int(np.count_nonzero(clipped)),
        "requested_abs_delta": np.abs(requested_delta).astype(float).tolist(),
        "applied_abs_delta": np.abs(applied_delta).astype(float).tolist(),
        "model_target_only": True,
        "assistance_frames": 0,
    }


def aggregate_temporal_action(
    chunks: Sequence[tuple[int, np.ndarray]],
    *,
    sample_step: int,
    method: str,
    exponential_decay: float = 0.5,
) -> tuple[np.ndarray, dict[str, object]]:
    """Aggregate causal model predictions for one absolute sample step."""

    if sample_step < 0:
        raise ValueError("sample_step must be non-negative")
    if method not in TEMPORAL_ACTION_AGGREGATIONS:
        raise ValueError(f"unsupported temporal action aggregation: {method}")
    if not 0.0 < exponential_decay <= 1.0:
        raise ValueError("exponential_decay must be in (0, 1]")
    if not chunks:
        raise ValueError("at least one model action chunk is required")

    candidates: list[np.ndarray] = []
    source_query_steps: list[int] = []
    previous_start = -1
    action_width: int | None = None
    for start_step, chunk in chunks:
        if start_step < 0 or start_step <= previous_start:
            raise ValueError("chunk start steps must be non-negative and increasing")
        previous_start = start_step
        array = np.asarray(chunk, dtype=np.float32)
        if array.ndim != 2 or not array.shape[0] or not array.shape[1]:
            raise ValueError("each action chunk must be a non-empty matrix")
        if not np.isfinite(array).all():
            raise ValueError("action chunks must contain only finite values")
        if action_width is None:
            action_width = int(array.shape[1])
        elif array.shape[1] != action_width:
            raise ValueError("action chunks must share one action width")
        relative_step = sample_step - start_step
        if 0 <= relative_step < array.shape[0]:
            candidates.append(array[relative_step])
            source_query_steps.append(start_step)

    if not candidates:
        raise ValueError(f"no model chunk predicts sample step {sample_step}")
    stacked = np.stack(candidates).astype(np.float32, copy=False)
    normalized_weights: list[float] | None = None
    if method == "latest":
        selected = stacked[-1]
    elif method == "mean":
        selected = np.mean(stacked, axis=0, dtype=np.float64)
    elif method == "median":
        selected = np.median(stacked, axis=0)
    else:
        ages = np.arange(len(candidates) - 1, -1, -1, dtype=np.float64)
        weights = np.power(float(exponential_decay), ages)
        weights /= np.sum(weights)
        normalized_weights = [float(value) for value in weights]
        selected = np.sum(stacked.astype(np.float64) * weights[:, None], axis=0)
    action = np.asarray(selected, dtype=np.float32).copy()
    if not np.isfinite(action).all():
        raise ValueError("temporal aggregation produced a non-finite action")
    return action, {
        "method": method,
        "exponential_decay": float(exponential_decay),
        "candidate_count": len(candidates),
        "source_query_steps": source_query_steps,
        "normalized_weights_oldest_to_newest": normalized_weights,
        "model_chunks_only": True,
        "causal": True,
        "assistance_frames": 0,
    }


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

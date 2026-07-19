"""Auditable array identities and contact transitions for learned rollouts."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np


def array_sha256(value: np.ndarray) -> str:
    """Hash an array's dtype, shape, and contiguous byte payload."""

    array = np.ascontiguousarray(value)
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("utf-8"))
    digest.update(
        json.dumps(array.shape, separators=(",", ":")).encode("utf-8")
    )
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def contact_transition_events(
    values: np.ndarray,
    *,
    physics_steps: np.ndarray,
    times_seconds: np.ndarray,
    contact_name: str,
) -> list[dict[str, Any]]:
    """Describe every start/end edge in a retained boolean contact trace."""

    contacts = np.asarray(values, dtype=np.bool_)
    steps = np.asarray(physics_steps, dtype=np.int64)
    times = np.asarray(times_seconds, dtype=np.float64)
    if contacts.ndim != 1:
        raise ValueError("contact trace must be one-dimensional")
    if steps.shape != contacts.shape or times.shape != contacts.shape:
        raise ValueError("contact trace timing arrays are misaligned")
    events: list[dict[str, Any]] = []
    previous = False
    for contact, step, time_seconds in zip(
        contacts, steps, times, strict=True
    ):
        current = bool(contact)
        if current != previous:
            events.append(
                {
                    "event": f"{contact_name}_{'started' if current else 'ended'}",
                    "physics_step": int(step),
                    "time_seconds": float(time_seconds),
                }
            )
        previous = current
    return events


def validate_integration_state_digests(
    states: np.ndarray,
    digests: np.ndarray,
) -> None:
    """Require every retained integration-state digest to match its row."""

    state_array = np.asarray(states)
    digest_array = np.asarray(digests)
    if state_array.ndim != 2 or digest_array.shape != (state_array.shape[0],):
        raise ValueError("integration-state digest rows are misaligned")
    for index, (state, recorded) in enumerate(
        zip(state_array, digest_array, strict=True)
    ):
        if array_sha256(state) != str(recorded):
            raise ValueError(f"integration-state digest drifted at row {index}")


def validate_rollout_trace_lengths(
    *,
    sample_count: int,
    requested_actions: np.ndarray,
    applied_actions: np.ndarray,
    integration_states: np.ndarray,
    integration_state_digests: np.ndarray,
    pawn_positions: np.ndarray,
    pawn_rotations: np.ndarray,
    end_effector_positions: np.ndarray,
) -> None:
    """Reject missing or misaligned per-action replay evidence."""

    named = {
        "requested actions": requested_actions,
        "applied actions": applied_actions,
        "integration states": integration_states,
        "integration state digests": integration_state_digests,
        "pawn positions": pawn_positions,
        "pawn rotations": pawn_rotations,
        "end-effector positions": end_effector_positions,
    }
    for label, value in named.items():
        if np.asarray(value).shape[0] != sample_count:
            raise ValueError(f"{label} trace length differs from sample count")
    if requested_actions.shape != applied_actions.shape:
        raise ValueError("requested and applied action traces have different shapes")
    if requested_actions.shape != (sample_count, 6):
        raise ValueError("action traces must be sample_count by six")
    if integration_state_digests.shape != (sample_count,):
        raise ValueError("integration-state digest trace must be one-dimensional")
    validate_integration_state_digests(
        integration_states,
        integration_state_digests,
    )
    if pawn_positions.ndim != 3 or pawn_positions.shape[2] != 3:
        raise ValueError("pawn positions must be sample by piece by three")
    expected_rotation_shape = (
        sample_count,
        pawn_positions.shape[1],
        3,
        3,
    )
    if pawn_rotations.shape != expected_rotation_shape:
        raise ValueError("pawn position and rotation traces are misaligned")
    if end_effector_positions.shape != (sample_count, 3):
        raise ValueError("end-effector trace must be sample_count by three")

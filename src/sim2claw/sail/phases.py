"""Observable, deterministic phase and time-base helpers for SAIL residuals."""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import numpy as np

from .contracts import SailContractError


class PhaseAlignmentError(SailContractError):
    """Observable phase or interpolation provenance is invalid."""


def _finite_vector(
    values: Sequence[float], *, label: str, minimum_size: int = 6
) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1 or array.size < minimum_size or not np.all(np.isfinite(array)):
        raise PhaseAlignmentError(
            f"{label} must be a finite vector with at least {minimum_size} samples"
        )
    return array


def detect_events(
    gripper_values: Sequence[float], settings: Mapping[str, Any]
) -> dict[str, int]:
    """Find observable open/close/release landmarks without contact claims."""

    gripper = _finite_vector(gripper_values, label="gripper signal")
    minimum_amplitude = float(settings["minimum_gripper_amplitude"])
    amplitude = float(np.max(gripper) - np.min(gripper))
    if not math.isfinite(minimum_amplitude) or amplitude <= minimum_amplitude:
        raise PhaseAlignmentError("gripper signal has no usable amplitude")
    first_fraction = float(settings["first_open_search_fraction"])
    destination_fraction = float(settings["destination_open_search_start_fraction"])
    transition_fraction = float(settings["transition_fraction_of_open_to_valley_range"])
    if not 0.0 < first_fraction <= destination_fraction < 1.0:
        raise PhaseAlignmentError("phase search fractions are invalid")
    if not 0.0 < transition_fraction < 0.5:
        raise PhaseAlignmentError("phase transition fraction is invalid")
    search_end = max(2, int(gripper.size * first_fraction))
    destination_start = max(search_end, int(gripper.size * destination_fraction))
    if destination_start >= gripper.size - 1:
        raise PhaseAlignmentError("destination-open search is empty")
    open_reference = int(np.argmax(gripper[:search_end]))
    destination_open = destination_start + int(np.argmax(gripper[destination_start:]))
    if destination_open <= open_reference + 2:
        raise PhaseAlignmentError("opening peaks are not ordered")
    closed_valley = open_reference + 1 + int(
        np.argmin(gripper[open_reference + 1 : destination_open])
    )
    source_range = float(gripper[open_reference] - gripper[closed_valley])
    destination_range = float(gripper[destination_open] - gripper[closed_valley])
    if source_range <= minimum_amplitude or destination_range <= minimum_amplitude:
        raise PhaseAlignmentError("open-close event range is invalid")
    closure_candidates = np.flatnonzero(
        gripper[open_reference : closed_valley + 1]
        <= gripper[open_reference] - transition_fraction * source_range
    )
    near_closed_candidates = np.flatnonzero(
        gripper[open_reference : closed_valley + 1]
        <= gripper[closed_valley] + transition_fraction * source_range
    )
    release_candidates = np.flatnonzero(
        gripper[closed_valley : destination_open + 1]
        >= gripper[closed_valley] + transition_fraction * destination_range
    )
    if not closure_candidates.size or not near_closed_candidates.size or not release_candidates.size:
        raise PhaseAlignmentError("gripper transition threshold was not crossed")
    closure_onset = open_reference + int(closure_candidates[0])
    near_closed = open_reference + int(near_closed_candidates[0])
    release_onset = closed_valley + int(release_candidates[0])
    ordered = (
        open_reference,
        closure_onset,
        near_closed,
        closed_valley,
        release_onset,
        destination_open,
    )
    if list(ordered) != sorted(ordered):
        raise PhaseAlignmentError("event indices are not ordered")
    if not closure_onset < near_closed < release_onset < destination_open:
        raise PhaseAlignmentError("event intervals collapsed")
    names = list(settings["event_order"])
    if len(names) != len(ordered) or len(set(names)) != len(names):
        raise PhaseAlignmentError("event inventory changed")
    return dict(zip(names, ordered, strict=True))


def phase_intervals(
    sample_count: int, events: Mapping[str, int], phase_order: Sequence[str]
) -> list[dict[str, Any]]:
    boundaries = (
        0,
        int(events["closure_onset"]),
        int(events["near_closed_crossing"]) + 1,
        int(events["release_onset"]),
        int(events["destination_open_peak"]) + 1,
        int(sample_count),
    )
    if list(boundaries) != sorted(boundaries):
        raise PhaseAlignmentError("phase boundaries are not ordered")
    if len(phase_order) != 5 or len(set(phase_order)) != 5:
        raise PhaseAlignmentError("phase inventory changed")
    result: list[dict[str, Any]] = []
    for phase, start, end in zip(phase_order, boundaries[:-1], boundaries[1:], strict=True):
        if end <= start:
            raise PhaseAlignmentError(f"phase is empty: {phase}")
        result.append(
            {
                "phase": str(phase),
                "start_sample_index_inclusive": start,
                "end_sample_index_exclusive": end,
                "sample_count": end - start,
            }
        )
    if sum(row["sample_count"] for row in result) != sample_count:
        raise PhaseAlignmentError("phases do not cover every sample")
    return result


def phase_labels(sample_count: int, intervals: Sequence[Mapping[str, Any]]) -> list[str]:
    labels = [""] * sample_count
    for interval in intervals:
        start = int(interval["start_sample_index_inclusive"])
        end = int(interval["end_sample_index_exclusive"])
        for index in range(start, end):
            if index < 0 or index >= sample_count or labels[index]:
                raise PhaseAlignmentError("phase intervals overlap or exceed sample bounds")
            labels[index] = str(interval["phase"])
    if any(not label for label in labels):
        raise PhaseAlignmentError("phase intervals leave uncovered samples")
    return labels


def event_phase(event_name: str) -> str:
    mapping = {
        "open_reference_peak": "approach_open",
        "closure_onset": "closure_transition",
        "near_closed_crossing": "closure_transition",
        "closed_valley": "closed_transport_candidate",
        "release_onset": "release_transition",
        "destination_open_peak": "release_transition",
    }
    try:
        return mapping[event_name]
    except KeyError as error:
        raise PhaseAlignmentError(f"unknown event: {event_name}") from error


def finite_difference(values: Sequence[Sequence[float]], times: Sequence[float]) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    time = _finite_vector(times, label="time base", minimum_size=2)
    if array.ndim != 2 or array.shape[0] != time.size or not np.all(np.isfinite(array)):
        raise PhaseAlignmentError("finite-difference values do not match the time base")
    if np.any(np.diff(time) <= 0.0):
        raise PhaseAlignmentError("time base is not strictly increasing")
    return np.asarray(np.gradient(array, time, axis=0, edge_order=1), dtype=np.float64)


def resample_masked_channel(
    source_times: Sequence[float],
    values: Sequence[float | None],
    available: Sequence[bool],
    target_times: Sequence[float],
    *,
    method: str,
) -> tuple[list[float | None], list[bool], dict[str, Any]]:
    """Explicit linear interpolation that never crosses an unavailable gap."""

    if method != "linear":
        raise PhaseAlignmentError(f"unsupported interpolation method: {method}")
    source = _finite_vector(source_times, label="source time base", minimum_size=2)
    target = np.asarray(target_times, dtype=np.float64)
    if target.ndim != 1 or not np.all(np.isfinite(target)):
        raise PhaseAlignmentError("target time base is invalid")
    if len(values) != source.size or len(available) != source.size:
        raise PhaseAlignmentError("availability mask changed length")
    if np.any(np.diff(source) <= 0.0) or np.any(np.diff(target) < 0.0):
        raise PhaseAlignmentError("resampling time bases must be ordered")
    numeric = np.asarray(
        [0.0 if value is None else float(value) for value in values], dtype=np.float64
    )
    if not np.all(np.isfinite(numeric)):
        raise PhaseAlignmentError("resampling source contains a non-finite scalar")
    mask = np.asarray(available, dtype=np.bool_)
    result_values: list[float | None] = []
    result_available: list[bool] = []
    for item in target:
        if item < source[0] or item > source[-1]:
            result_values.append(None)
            result_available.append(False)
            continue
        right = int(np.searchsorted(source, item, side="left"))
        if right < source.size and source[right] == item:
            if mask[right]:
                result_values.append(float(numeric[right]))
                result_available.append(True)
            else:
                result_values.append(None)
                result_available.append(False)
            continue
        left = max(0, right - 1)
        if right >= source.size or not mask[left] or not mask[right]:
            result_values.append(None)
            result_available.append(False)
            continue
        fraction = float((item - source[left]) / (source[right] - source[left]))
        result_values.append(float(numeric[left] + fraction * (numeric[right] - numeric[left])))
        result_available.append(True)
    provenance = {
        "method": "linear",
        "source_time_count": int(source.size),
        "target_time_count": int(target.size),
        "gap_filling": False,
        "extrapolation": False,
    }
    return result_values, result_available, provenance

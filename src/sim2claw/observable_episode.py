"""ObservableEpisode.v2-min validation, adapters, and divergence extraction."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


SCHEMA_VERSION = "sim2claw.observable_episode.v2-min"
ACTION_WIDTH = 6
CONTACT_STATES = {"unavailable", "none", "possible", "confirmed"}
CLOCK_STATES = {"mapped", "device_only", "host_only", "unavailable"}
SOURCE_KINDS = {"simulator", "physical_source"}


class ObservableEpisodeError(RuntimeError):
    """An observable episode violates its causal evidence contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ObservableEpisodeError(message)


def _float64_rows(values: Any, name: str) -> np.ndarray:
    array = np.asarray(values, dtype="<f8", order="C")
    _require(
        array.ndim == 2
        and array.shape[1] == ACTION_WIDTH
        and len(array) > 0
        and np.all(np.isfinite(array)),
        f"{name} must be finite Nx{ACTION_WIDTH} float64 rows",
    )
    return array


def _action_sha(values: np.ndarray) -> str:
    return hashlib.sha256(
        np.asarray(values, dtype="<f8", order="C").tobytes(order="C")
    ).hexdigest()


def _finite_vector(
    value: Any,
    length: int,
    name: str,
) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64)
    _require(
        result.shape == (length,) and np.all(np.isfinite(result)),
        f"{name} must be a finite length-{length} vector",
    )
    return result


def _covariance(value: Any, name: str) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64)
    _require(
        result.shape == (3, 3)
        and np.all(np.isfinite(result))
        and np.allclose(result, result.T, atol=1e-12, rtol=0.0),
        f"{name} must be a finite symmetric 3x3 matrix",
    )
    eigenvalues = np.linalg.eigvalsh(result)
    _require(
        float(np.min(eigenvalues)) >= -1e-12,
        f"{name} must be positive semidefinite",
    )
    return result


def _validate_link_poses(value: Any, name: str) -> None:
    _require(isinstance(value, dict), f"{name} must be an object")
    for link, pose in value.items():
        _require(isinstance(link, str) and link, f"{name} link is invalid")
        _finite_vector(pose, 7, f"{name}.{link}")


def _validate_sample(
    sample: Mapping[str, Any],
    index: int,
    requested: np.ndarray,
) -> None:
    expected = {
        "sample_index",
        "host_monotonic_time",
        "device_timestamp_by_camera",
        "clock_mapping_status",
        "command_requested",
        "command_mapped",
        "command_sent",
        "command_applied_or_missing",
        "command_applied_time_or_missing",
        "measured_joint_state",
        "estimated_link_poses",
        "object_state_board_se2",
        "object_state_covariance",
        "object_observation_available",
        "contact_state_or_probability",
        "first_object_motion_event",
        "task_outcome",
    }
    _require(
        set(sample) == expected,
        f"sample {index} fields differ from ObservableEpisode.v2-min",
    )
    _require(sample["sample_index"] == index, "sample index is not canonical")
    requested_row = _finite_vector(
        sample["command_requested"],
        ACTION_WIDTH,
        f"sample {index}.command_requested",
    )
    _require(
        np.array_equal(requested_row, requested[index]),
        "sample requested action differs from frozen action tensor",
    )
    for name in (
        "command_mapped",
        "command_sent",
        "command_applied_or_missing",
        "measured_joint_state",
    ):
        value = sample[name]
        if value is not None:
            _finite_vector(value, ACTION_WIDTH, f"sample {index}.{name}")
    applied_time = sample["command_applied_time_or_missing"]
    _require(
        applied_time is None
        or (isinstance(applied_time, (int, float)) and np.isfinite(applied_time)),
        "command applied time must be finite or explicitly missing",
    )
    host_time = sample["host_monotonic_time"]
    _require(
        isinstance(host_time, (int, float)) and np.isfinite(host_time),
        "host monotonic time must be finite",
    )
    device_times = sample["device_timestamp_by_camera"]
    clock_status = sample["clock_mapping_status"]
    _require(
        isinstance(device_times, dict)
        and isinstance(clock_status, dict)
        and set(device_times) == set(clock_status),
        "camera timestamps and clock states must have identical keys",
    )
    for camera_id, timestamp in device_times.items():
        _require(
            isinstance(camera_id, str) and camera_id,
            "camera timestamp key is invalid",
        )
        _require(
            timestamp is None
            or (
                isinstance(timestamp, (int, float))
                and np.isfinite(timestamp)
            ),
            "device timestamp must be finite or missing",
        )
        _require(
            clock_status[camera_id] in CLOCK_STATES,
            "camera clock mapping status is invalid",
        )
        if timestamp is None:
            _require(
                clock_status[camera_id] in {"host_only", "unavailable"},
                "missing device time cannot claim a device mapping",
            )
    links = sample["estimated_link_poses"]
    if links is not None:
        _validate_link_poses(links, f"sample {index}.estimated_link_poses")
    observed = sample["object_observation_available"]
    _require(isinstance(observed, bool), "object availability must be boolean")
    object_state = sample["object_state_board_se2"]
    object_covariance = sample["object_state_covariance"]
    if observed:
        _finite_vector(
            object_state, 3, f"sample {index}.object_state_board_se2"
        )
        _covariance(
            object_covariance,
            f"sample {index}.object_state_covariance",
        )
    else:
        _require(
            object_state is None and object_covariance is None,
            "missing object observation must retain null state and covariance",
        )
    contact = sample["contact_state_or_probability"]
    _require(
        isinstance(contact, dict)
        and set(contact) == {"state", "probability", "source"},
        "contact evidence fields are invalid",
    )
    _require(contact["state"] in CONTACT_STATES, "contact state is invalid")
    probability = contact["probability"]
    _require(
        probability is None
        or (
            isinstance(probability, (int, float))
            and np.isfinite(probability)
            and 0.0 <= probability <= 1.0
        ),
        "contact probability must be in [0,1] or missing",
    )
    _require(
        isinstance(contact["source"], str) and contact["source"],
        "contact source is missing",
    )
    if contact["state"] == "unavailable":
        _require(
            probability is None,
            "unavailable contact cannot have a fabricated probability",
        )
    _require(
        isinstance(sample["first_object_motion_event"], bool),
        "first object motion event must be boolean",
    )
    _require(
        sample["task_outcome"] is None
        or (
            isinstance(sample["task_outcome"], str)
            and bool(sample["task_outcome"])
        ),
        "task outcome must be a nonempty string or missing",
    )


def validate_episode(episode: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize one ObservableEpisode.v2-min payload."""

    expected = {
        "schema_version",
        "episode_id",
        "proof_class",
        "source_kind",
        "action",
        "camera_roles",
        "samples",
        "events",
        "provenance",
        "claim_boundary",
    }
    _require(
        isinstance(episode, Mapping) and set(episode) == expected,
        "episode top-level fields differ from ObservableEpisode.v2-min",
    )
    _require(
        episode["schema_version"] == SCHEMA_VERSION,
        "unexpected observable episode schema",
    )
    _require(
        isinstance(episode["episode_id"], str) and episode["episode_id"],
        "episode id is missing",
    )
    _require(
        isinstance(episode["proof_class"], str) and episode["proof_class"],
        "episode proof class is missing",
    )
    _require(
        episode["source_kind"] in SOURCE_KINDS,
        "episode source kind is invalid",
    )
    action = episode["action"]
    _require(
        isinstance(action, Mapping)
        and set(action)
        == {
            "dtype",
            "sample_hz",
            "shape",
            "requested_sha256",
            "mapped_sha256_or_missing",
            "sent_sha256_or_missing",
            "applied_sha256_or_missing",
        },
        "episode action identity fields are invalid",
    )
    _require(
        action["dtype"] == "little_endian_float64",
        "episode action dtype changed",
    )
    _require(
        isinstance(action["sample_hz"], (int, float))
        and np.isfinite(action["sample_hz"])
        and float(action["sample_hz"]) > 0.0,
        "episode sample rate is invalid",
    )
    shape = action["shape"]
    _require(
        isinstance(shape, list)
        and len(shape) == 2
        and shape[1] == ACTION_WIDTH
        and shape[0] > 0,
        "episode action shape is invalid",
    )
    samples = episode["samples"]
    _require(
        isinstance(samples, list) and len(samples) == shape[0],
        "episode sample count differs from action shape",
    )
    requested = _float64_rows(
        [sample["command_requested"] for sample in samples],
        "requested action",
    )
    _require(
        _action_sha(requested) == action["requested_sha256"],
        "requested action hash differs from sample rows",
    )
    for index, sample in enumerate(samples):
        _require(isinstance(sample, Mapping), "episode sample is not an object")
        _validate_sample(sample, index, requested)
    host_times = np.asarray(
        [sample["host_monotonic_time"] for sample in samples],
        dtype=np.float64,
    )
    _require(
        len(host_times) == 1 or np.all(np.diff(host_times) > 0.0),
        "host monotonic timestamps are not strictly increasing",
    )
    for field, sample_field in (
        ("mapped_sha256_or_missing", "command_mapped"),
        ("sent_sha256_or_missing", "command_sent"),
        ("applied_sha256_or_missing", "command_applied_or_missing"),
    ):
        rows = [sample[sample_field] for sample in samples]
        if action[field] is None:
            _require(
                all(row is None for row in rows),
                f"{sample_field} rows exist without a bound hash",
            )
        else:
            _require(
                all(row is not None for row in rows),
                f"{sample_field} has partial missingness",
            )
            _require(
                _action_sha(_float64_rows(rows, sample_field))
                == action[field],
                f"{sample_field} hash differs from rows",
            )
    for field in (
        "requested_sha256",
        "mapped_sha256_or_missing",
        "sent_sha256_or_missing",
        "applied_sha256_or_missing",
    ):
        value = action[field]
        _require(
            value is None
            or (
                isinstance(value, str)
                and len(value) == 64
                and all(character in "0123456789abcdef" for character in value)
            ),
            f"{field} must be a lowercase SHA-256 or missing",
        )
    events = episode["events"]
    _require(
        isinstance(events, Mapping)
        and set(events)
        == {
            "first_contact_sample_or_missing",
            "first_object_motion_sample_or_missing",
            "final_task_outcome_or_missing",
        },
        "episode event fields are invalid",
    )
    for event_name in (
        "first_contact_sample_or_missing",
        "first_object_motion_sample_or_missing",
    ):
        value = events[event_name]
        _require(
            value is None
            or (isinstance(value, int) and 0 <= value < len(samples)),
            f"{event_name} is invalid",
        )
    motion_indices = [
        index
        for index, sample in enumerate(samples)
        if sample["first_object_motion_event"]
    ]
    _require(
        len(motion_indices) <= 1,
        "first object motion event may occur only once",
    )
    _require(
        (motion_indices[0] if motion_indices else None)
        == events["first_object_motion_sample_or_missing"],
        "first object motion event disagrees with summary",
    )
    _require(
        isinstance(episode["camera_roles"], dict),
        "camera roles must be an object",
    )
    camera_roles = episode["camera_roles"]
    for camera_id, role in camera_roles.items():
        _require(
            isinstance(camera_id, str)
            and bool(camera_id)
            and isinstance(role, str)
            and bool(role),
            "camera roles contain an invalid camera or role",
        )
    for sample in samples:
        _require(
            set(sample["device_timestamp_by_camera"]) == set(camera_roles),
            "sample camera timestamps differ from declared camera roles",
        )
    for camera_id in camera_roles:
        available_device_times = [
            sample["device_timestamp_by_camera"][camera_id]
            for sample in samples
            if sample["device_timestamp_by_camera"][camera_id] is not None
        ]
        _require(
            len(available_device_times) < 2
            or np.all(np.diff(available_device_times) >= 0.0),
            f"{camera_id} device timestamps are not monotonic",
        )
    applied_times = [
        sample["command_applied_time_or_missing"]
        for sample in samples
        if sample["command_applied_time_or_missing"] is not None
    ]
    _require(
        len(applied_times) < 2 or np.all(np.diff(applied_times) >= 0.0),
        "command applied timestamps are not monotonic",
    )
    confirmed_contacts = [
        index
        for index, sample in enumerate(samples)
        if sample["contact_state_or_probability"]["state"] == "confirmed"
    ]
    _require(
        (confirmed_contacts[0] if confirmed_contacts else None)
        == events["first_contact_sample_or_missing"],
        "first contact event disagrees with samples",
    )
    _require(
        samples[-1]["task_outcome"]
        == events["final_task_outcome_or_missing"],
        "final task outcome disagrees with final sample",
    )
    _require(
        all(sample["task_outcome"] is None for sample in samples[:-1]),
        "task outcome may only appear on the final sample",
    )
    _require(
        isinstance(episode["provenance"], dict)
        and bool(episode["provenance"]),
        "episode provenance is missing",
    )
    _require(
        isinstance(episode["claim_boundary"], str)
        and episode["claim_boundary"],
        "episode claim boundary is missing",
    )
    return json.loads(json.dumps(episode, sort_keys=True))


def _contact_value(
    state: str,
    probability: float | None,
    source: str,
) -> dict[str, Any]:
    return {
        "state": state,
        "probability": probability,
        "source": source,
    }


def build_simulator_episode(
    *,
    episode_id: str,
    requested: np.ndarray,
    applied: np.ndarray,
    sample_hz: float,
    joint_states: np.ndarray,
    link_poses: Sequence[Mapping[str, Sequence[float]]],
    object_states_board_se2: np.ndarray,
    object_covariances: np.ndarray,
    contact_states: Sequence[bool],
    task_outcome: str,
    first_object_motion_sample: int | None,
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a deterministic simulator-owned causal episode."""

    requested = _float64_rows(requested, "requested")
    applied = _float64_rows(applied, "applied")
    joints = _float64_rows(joint_states, "joint states")
    count = len(requested)
    _require(
        len(applied) == len(joints) == len(link_poses)
        == len(object_states_board_se2)
        == len(object_covariances)
        == len(contact_states)
        == count,
        "simulator adapter channel lengths differ",
    )
    contact_indices = [
        index for index, state in enumerate(contact_states) if state
    ]
    samples = []
    for index in range(count):
        samples.append(
            {
                "sample_index": index,
                "host_monotonic_time": index / sample_hz,
                "device_timestamp_by_camera": {},
                "clock_mapping_status": {},
                "command_requested": requested[index].tolist(),
                "command_mapped": requested[index].tolist(),
                "command_sent": requested[index].tolist(),
                "command_applied_or_missing": applied[index].tolist(),
                "command_applied_time_or_missing": index / sample_hz,
                "measured_joint_state": joints[index].tolist(),
                "estimated_link_poses": {
                    str(name): list(pose)
                    for name, pose in link_poses[index].items()
                },
                "object_state_board_se2": np.asarray(
                    object_states_board_se2[index], dtype=np.float64
                ).tolist(),
                "object_state_covariance": np.asarray(
                    object_covariances[index], dtype=np.float64
                ).tolist(),
                "object_observation_available": True,
                "contact_state_or_probability": _contact_value(
                    "confirmed" if contact_states[index] else "none",
                    1.0 if contact_states[index] else 0.0,
                    "mujoco_contact_witness",
                ),
                "first_object_motion_event": (
                    index == first_object_motion_sample
                ),
                "task_outcome": task_outcome if index == count - 1 else None,
            }
        )
    episode = {
        "schema_version": SCHEMA_VERSION,
        "episode_id": episode_id,
        "proof_class": "cpu_fp64_simulator_causal_observation",
        "source_kind": "simulator",
        "action": {
            "dtype": "little_endian_float64",
            "sample_hz": sample_hz,
            "shape": list(requested.shape),
            "requested_sha256": _action_sha(requested),
            "mapped_sha256_or_missing": _action_sha(requested),
            "sent_sha256_or_missing": _action_sha(requested),
            "applied_sha256_or_missing": _action_sha(applied),
        },
        "camera_roles": {},
        "samples": samples,
        "events": {
            "first_contact_sample_or_missing": (
                contact_indices[0] if contact_indices else None
            ),
            "first_object_motion_sample_or_missing": (
                first_object_motion_sample
            ),
            "final_task_outcome_or_missing": task_outcome,
        },
        "provenance": dict(provenance),
        "claim_boundary": (
            "Simulator-owned link, contact, object, and outcome observations; "
            "no physical task or transfer authority."
        ),
    }
    return validate_episode(episode)


def build_physical_source_episode(
    *,
    episode_id: str,
    source_rows: Sequence[Mapping[str, Any]],
    requested_field: str,
    mapped_field: str | None,
    sent_field: str | None,
    applied_field: str | None,
    joint_field: str,
    host_time_field: str,
    sample_hz: float,
    camera_ids: Sequence[str],
    object_observations: Sequence[Mapping[str, Any] | None] | None,
    contact_observations: Sequence[Mapping[str, Any] | None] | None,
    task_outcome: str | None,
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    """Adapt recorded physical-source rows while retaining missingness."""

    _require(bool(source_rows), "physical source rows are empty")
    requested = _float64_rows(
        [row[requested_field] for row in source_rows],
        "physical requested",
    )
    mapped_rows = (
        None
        if mapped_field is None
        else _float64_rows(
            [row[mapped_field] for row in source_rows],
            "physical mapped",
        )
    )
    sent_rows = (
        None
        if sent_field is None
        else _float64_rows(
            [row[sent_field] for row in source_rows],
            "physical sent",
        )
    )
    applied_rows = (
        None
        if applied_field is None
        else _float64_rows(
            [row[applied_field] for row in source_rows],
            "physical applied",
        )
    )
    joints = _float64_rows(
        [row[joint_field] for row in source_rows],
        "physical joints",
    )
    count = len(source_rows)
    _require(
        object_observations is None or len(object_observations) == count,
        "physical object observation length differs",
    )
    _require(
        contact_observations is None or len(contact_observations) == count,
        "physical contact observation length differs",
    )
    first_motion = None
    samples = []
    for index, row in enumerate(source_rows):
        object_row = (
            None if object_observations is None else object_observations[index]
        )
        contact_row = (
            None
            if contact_observations is None
            else contact_observations[index]
        )
        motion = bool(object_row and object_row.get("first_motion_event"))
        if motion:
            _require(
                first_motion is None,
                "physical source has multiple first-motion events",
            )
            first_motion = index
        device_times = {
            camera_id: (
                row.get(f"{camera_id}_device_timestamp")
                if row.get(f"{camera_id}_device_timestamp") is not None
                else None
            )
            for camera_id in camera_ids
        }
        clock_status = {
            camera_id: (
                row.get(f"{camera_id}_clock_mapping_status")
                or (
                    "device_only"
                    if device_times[camera_id] is not None
                    else "unavailable"
                )
            )
            for camera_id in camera_ids
        }
        samples.append(
            {
                "sample_index": index,
                "host_monotonic_time": float(row[host_time_field]),
                "device_timestamp_by_camera": device_times,
                "clock_mapping_status": clock_status,
                "command_requested": requested[index].tolist(),
                "command_mapped": (
                    None
                    if mapped_rows is None
                    else mapped_rows[index].tolist()
                ),
                "command_sent": (
                    None if sent_rows is None else sent_rows[index].tolist()
                ),
                "command_applied_or_missing": (
                    None
                    if applied_rows is None
                    else applied_rows[index].tolist()
                ),
                "command_applied_time_or_missing": row.get(
                    "command_applied_time"
                ),
                "measured_joint_state": joints[index].tolist(),
                "estimated_link_poses": row.get("estimated_link_poses"),
                "object_state_board_se2": (
                    None if object_row is None else object_row["state_se2"]
                ),
                "object_state_covariance": (
                    None if object_row is None else object_row["covariance"]
                ),
                "object_observation_available": object_row is not None,
                "contact_state_or_probability": (
                    _contact_value(
                        "unavailable",
                        None,
                        "missing_physical_contact_observation",
                    )
                    if contact_row is None
                    else {
                        "state": contact_row["state"],
                        "probability": contact_row.get("probability"),
                        "source": contact_row["source"],
                    }
                ),
                "first_object_motion_event": motion,
                "task_outcome": (
                    task_outcome if index == count - 1 else None
                ),
            }
        )
    contact_indices = [
        index
        for index, sample in enumerate(samples)
        if sample["contact_state_or_probability"]["state"] == "confirmed"
    ]
    episode = {
        "schema_version": SCHEMA_VERSION,
        "episode_id": episode_id,
        "proof_class": "physical_source_observation_explicit_missingness",
        "source_kind": "physical_source",
        "action": {
            "dtype": "little_endian_float64",
            "sample_hz": sample_hz,
            "shape": list(requested.shape),
            "requested_sha256": _action_sha(requested),
            "mapped_sha256_or_missing": (
                None if mapped_rows is None else _action_sha(mapped_rows)
            ),
            "sent_sha256_or_missing": (
                None if sent_rows is None else _action_sha(sent_rows)
            ),
            "applied_sha256_or_missing": (
                None if applied_rows is None else _action_sha(applied_rows)
            ),
        },
        "camera_roles": {
            camera_id: (
                "task_outcome_owner"
                if camera_id == "c922"
                else "supporting_rgb"
            )
            for camera_id in camera_ids
        },
        "samples": samples,
        "events": {
            "first_contact_sample_or_missing": (
                contact_indices[0] if contact_indices else None
            ),
            "first_object_motion_sample_or_missing": first_motion,
            "final_task_outcome_or_missing": task_outcome,
        },
        "provenance": dict(provenance),
        "claim_boundary": (
            "Physical-source causal observation with explicit unavailable "
            "channels; no simulator agreement or transfer authority."
        ),
    }
    return validate_episode(episode)


def write_episode(episode: Mapping[str, Any], path: Path) -> dict[str, Any]:
    """Validate and atomically write one immutable episode."""

    _require(not path.exists(), "immutable observable episode already exists")
    normalized = validate_episode(episode)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(normalized, indent=2, sort_keys=True) + "\n"
    path.write_text(payload, encoding="utf-8")
    return {
        "path": str(path),
        "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "sample_count": len(normalized["samples"]),
        "schema_version": normalized["schema_version"],
    }


def first_divergence(
    reference: Mapping[str, Any],
    challenger: Mapping[str, Any],
    *,
    joint_threshold: float,
    link_position_threshold_m: float,
    object_position_threshold_m: float,
    object_yaw_threshold_rad: float,
) -> dict[str, Any]:
    """Return the earliest available causal-channel divergence."""

    first = validate_episode(reference)
    second = validate_episode(challenger)
    _require(
        len(first["samples"]) == len(second["samples"]),
        "divergence episodes have different sample counts",
    )
    if (
        first["action"]["requested_sha256"]
        != second["action"]["requested_sha256"]
    ):
        return {
            "status": "diverged",
            "channel": "requested_action",
            "sample_index": 0,
            "reference_time": first["samples"][0]["host_monotonic_time"],
            "challenger_time": second["samples"][0]["host_monotonic_time"],
            "residual": None,
            "threshold": 0.0,
        }
    for index, (left, right) in enumerate(
        zip(first["samples"], second["samples"], strict=True)
    ):
        left_applied = left["command_applied_or_missing"]
        right_applied = right["command_applied_or_missing"]
        if left_applied is not None and right_applied is not None:
            residual = float(
                np.max(
                    np.abs(
                        np.asarray(left_applied)
                        - np.asarray(right_applied)
                    )
                )
            )
            if residual > 0.0:
                return _divergence_row(
                    "applied_action",
                    index,
                    left,
                    right,
                    residual,
                    0.0,
                )
        left_joint = left["measured_joint_state"]
        right_joint = right["measured_joint_state"]
        if left_joint is not None and right_joint is not None:
            residual = float(
                np.max(
                    np.abs(
                        np.asarray(left_joint) - np.asarray(right_joint)
                    )
                )
            )
            if residual > joint_threshold:
                return _divergence_row(
                    "joint_state",
                    index,
                    left,
                    right,
                    residual,
                    joint_threshold,
                )
        left_links = left["estimated_link_poses"]
        right_links = right["estimated_link_poses"]
        if left_links is not None and right_links is not None:
            for link in sorted(set(left_links) & set(right_links)):
                residual = float(
                    np.linalg.norm(
                        np.asarray(left_links[link][:3])
                        - np.asarray(right_links[link][:3])
                    )
                )
                if residual > link_position_threshold_m:
                    return _divergence_row(
                        f"link_pose:{link}",
                        index,
                        left,
                        right,
                        residual,
                        link_position_threshold_m,
                    )
        left_contact = left["contact_state_or_probability"]["state"]
        right_contact = right["contact_state_or_probability"]["state"]
        if (
            left_contact != "unavailable"
            and right_contact != "unavailable"
            and left_contact != right_contact
        ):
            return _divergence_row(
                "contact_state", index, left, right, None, None
            )
        if (
            left["object_observation_available"]
            and right["object_observation_available"]
        ):
            left_object = np.asarray(left["object_state_board_se2"])
            right_object = np.asarray(right["object_state_board_se2"])
            position = float(
                np.linalg.norm(left_object[:2] - right_object[:2])
            )
            if position > object_position_threshold_m:
                return _divergence_row(
                    "object_position",
                    index,
                    left,
                    right,
                    position,
                    object_position_threshold_m,
                )
            yaw = float(
                abs(
                    np.arctan2(
                        np.sin(left_object[2] - right_object[2]),
                        np.cos(left_object[2] - right_object[2]),
                    )
                )
            )
            if yaw > object_yaw_threshold_rad:
                return _divergence_row(
                    "object_yaw",
                    index,
                    left,
                    right,
                    yaw,
                    object_yaw_threshold_rad,
                )
    left_outcome = first["events"]["final_task_outcome_or_missing"]
    right_outcome = second["events"]["final_task_outcome_or_missing"]
    if (
        left_outcome is not None
        and right_outcome is not None
        and left_outcome != right_outcome
    ):
        index = len(first["samples"]) - 1
        return _divergence_row(
            "task_outcome",
            index,
            first["samples"][index],
            second["samples"][index],
            None,
            None,
        )
    return {
        "status": "no_observed_divergence",
        "channel": None,
        "sample_index": None,
        "reference_time": None,
        "challenger_time": None,
        "residual": None,
        "threshold": None,
    }


def _divergence_row(
    channel: str,
    index: int,
    reference: Mapping[str, Any],
    challenger: Mapping[str, Any],
    residual: float | None,
    threshold: float | None,
) -> dict[str, Any]:
    return {
        "status": "diverged",
        "channel": channel,
        "sample_index": index,
        "reference_time": reference["host_monotonic_time"],
        "challenger_time": challenger["host_monotonic_time"],
        "residual": residual,
        "threshold": threshold,
    }


__all__ = [
    "ObservableEpisodeError",
    "SCHEMA_VERSION",
    "build_physical_source_episode",
    "build_simulator_episode",
    "first_divergence",
    "validate_episode",
    "write_episode",
]

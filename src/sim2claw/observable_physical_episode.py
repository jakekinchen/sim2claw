"""Compile timestamp-bound physical RGB observations without inventing depth."""

from __future__ import annotations

import bisect
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .paths import REPO_ROOT


SCHEDULE_SCHEMA = "sim2claw.observable_physical_episode_schedule_contract.v1"
SCHEDULE_SUCCESSOR_SCHEMA = (
    "sim2claw.observable_physical_episode_schedule_successor_contract.v1"
)
SCHEDULE_RECEIPT_SCHEMA = (
    "sim2claw.observable_physical_episode_schedule_receipt.v1"
)
SCHEDULE_V1_CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "observable_physical_episode_schedule_v1.json"
)
SCHEDULE_CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "observable_physical_episode_schedule_v2.json"
)
SCHEDULE_OUTPUT_PATH = (
    REPO_ROOT
    / "outputs"
    / "observable_physical_episode_schedule_v2"
    / "receipt.json"
)
FRAME_OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs"
    / "observable_physical_episode_schedule_v2"
    / "frames"
)
OBSERVATION_SCHEMA = (
    "sim2claw.observable_physical_episode_observation_contract.v1"
)
OBSERVATION_RECEIPT_SCHEMA = (
    "sim2claw.observable_physical_episode_observation_receipt.v1"
)
OBSERVATION_CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "observable_physical_episode_observations_v1.json"
)
OBSERVATION_OUTPUT_PATH = (
    REPO_ROOT
    / "outputs"
    / "observable_physical_episode_observations_v1"
    / "receipt.json"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _bound_path(
    binding: dict[str, Any], *, root: Path, label: str
) -> Path:
    path = root / str(binding.get("path", ""))
    expected = str(binding.get("sha256", ""))
    _require(path.is_file(), f"{label} source is missing")
    _require(
        len(expected) == 64 and sha256_file(path) == expected,
        f"{label} hash drifted",
    )
    return path


def _load_jsonl(path: Path, *, label: str) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as error:
        raise FactoryArtifactError(f"cannot read {label}: {error}") from error
    _require(rows and all(isinstance(row, dict) for row in rows), f"{label} is empty")
    return rows


def load_schedule_contract(
    path: Path = SCHEDULE_CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="physical observation schedule")
    if contract.get("schema_version") == SCHEDULE_SUCCESSOR_SCHEMA:
        base_path = _bound_path(
            contract["base_contract"],
            root=root,
            label="schedule v1 base contract",
        )
        _bound_path(
            contract["predecessor_closeout"],
            root=root,
            label="schedule v1 closeout",
        )
        invariants = contract.get("invariants")
        _require(
            isinstance(invariants, dict)
            and invariants
            and all(
                invariants.get(field) is True
                for field in (
                    "source_bindings_unchanged",
                    "telemetry_only_windows_unchanged",
                    "annotation_policy_unchanged",
                    "d405_association_bound_unchanged",
                    "proof_boundaries_unchanged",
                    "authority_unchanged",
                )
            )
            and invariants.get("visual_frames_opened_before_freeze") is False
            and invariants.get("visual_labels_created_before_freeze") is False,
            "schedule successor invariant changed",
        )
        override = contract.get("override")
        _require(
            isinstance(override, dict)
            and set(override) == {"maximum_c922_association_error_ms"}
            and float(override["maximum_c922_association_error_ms"]) == 35.0,
            "schedule successor override changed",
        )
        derivation = contract.get("bound_derivation")
        _require(
            isinstance(derivation, dict)
            and derivation.get("uses_visual_outcome") is False
            and derivation.get("uses_task_success") is False,
            "schedule successor used visual outcome",
        )
        base = load_json_object(base_path, label="physical observation base")
        _require(
            base.get("schema_version") == SCHEDULE_SCHEMA,
            "schedule successor base schema changed",
        )
        base["experiment_id"] = contract["experiment_id"]
        base["frozen_date"] = contract["frozen_date"]
        base["expected"]["maximum_c922_association_error_ms"] = float(
            override["maximum_c922_association_error_ms"]
        )
        base["successor_lineage"] = {
            "base_contract": contract["base_contract"],
            "predecessor_closeout": contract["predecessor_closeout"],
            "invariants": invariants,
            "bound_derivation": derivation,
        }
        contract = base
    _require(
        contract.get("schema_version") == SCHEDULE_SCHEMA,
        "unsupported physical observation schedule schema",
    )
    sources = contract.get("sources")
    _require(isinstance(sources, dict) and sources, "schedule sources are missing")
    for source_id, binding in sources.items():
        _require(isinstance(binding, dict), f"invalid schedule source: {source_id}")
        _bound_path(binding, root=root, label=source_id)
    association = contract.get("association")
    _require(
        isinstance(association, dict)
        and association.get("selection")
        == "nearest_host_continuous_timestamp"
        and association.get("tie_break") == "lower_frame_index"
        and association.get("camera_exposure_synchronized") is False
        and association.get("cross_camera_exposure_synchronized") is False,
        "timestamp association changed",
    )
    windows = contract.get("telemetry_only_windows")
    _require(isinstance(windows, list) and windows, "schedule windows are missing")
    indices: list[int] = []
    for window in windows:
        start, end = [int(value) for value in window["sample_range_inclusive"]]
        members = [int(value) for value in window["sample_indices"]]
        _require(
            members == sorted(set(members))
            and all(start <= value <= end for value in members),
            "schedule window membership changed",
        )
        indices.extend(members)
    _require(indices == sorted(set(indices)), "schedule membership overlaps or is unordered")
    policy = contract.get("annotation_policy")
    _require(
        isinstance(policy, dict)
        and policy.get("schedule_may_change_after_visual_open") is False
        and policy.get("ambiguous_rows_abstain") is True
        and policy.get("occluded_rows_abstain") is True
        and policy.get("missing_depth_is_unknown") is True,
        "annotation policy widened",
    )
    boundaries = contract.get("proof_boundaries")
    authority = contract.get("authority")
    _require(
        isinstance(boundaries, dict) and boundaries and not any(boundaries.values()),
        "schedule proof boundary widened",
    )
    _require(
        isinstance(authority, dict) and authority and not any(authority.values()),
        "schedule authority widened",
    )
    return contract


def admitted_callback_frames(
    callback_rows: list[dict[str, Any]], *, role: str
) -> list[dict[str, Any]]:
    selected = [
        row
        for row in callback_rows
        if row.get("role") == role
        and row.get("appended_to_writer") is True
        and row.get("warmup_excluded") is False
    ]
    _require(selected, f"no admitted callback frames for {role}")
    sequences = [int(row["sequence"]) for row in selected]
    host_ns = [int(row["host_continuous_ns"]) for row in selected]
    _require(
        sequences == sorted(set(sequences)),
        f"{role} callback sequence is not strict",
    )
    _require(
        host_ns == sorted(set(host_ns)),
        f"{role} callback host time is not strict",
    )
    return [
        {
            "frame_index": index,
            "sequence": int(row["sequence"]),
            "host_continuous_ns": int(row["host_continuous_ns"]),
            "source_pts_seconds": float(row["pts_seconds"]),
        }
        for index, row in enumerate(selected)
    ]


def nearest_frame_binding(
    frames: list[dict[str, Any]], *, sample_host_continuous_ns: int
) -> dict[str, Any]:
    host_values = [int(row["host_continuous_ns"]) for row in frames]
    position = bisect.bisect_left(host_values, int(sample_host_continuous_ns))
    candidates = []
    if position > 0:
        candidates.append(frames[position - 1])
    if position < len(frames):
        candidates.append(frames[position])
    _require(candidates, "cannot associate sample to frame")
    selected = min(
        candidates,
        key=lambda row: (
            abs(int(row["host_continuous_ns"]) - sample_host_continuous_ns),
            int(row["frame_index"]),
        ),
    )
    error_ns = abs(
        int(selected["host_continuous_ns"]) - sample_host_continuous_ns
    )
    return {
        **selected,
        "association_error_ms": float(error_ns / 1_000_000.0),
    }


def _sample_host_ns(row: dict[str, Any]) -> int:
    timestamp = row["observability_timestamps"][
        "sample_completed_monotonic_seconds"
    ]
    _require(timestamp is not None, "sample completion timestamp is missing")
    return int(round(float(timestamp) * 1_000_000_000.0))


def compile_schedule(
    contract: dict[str, Any],
    *,
    root: Path = REPO_ROOT,
    contract_sha256: str | None = None,
) -> dict[str, Any]:
    sources = contract["sources"]
    samples = _load_jsonl(
        _bound_path(sources["samples"], root=root, label="samples"),
        label="physical samples",
    )
    callbacks = _load_jsonl(
        _bound_path(
            sources["camera_callbacks"], root=root, label="camera callbacks"
        ),
        label="camera callbacks",
    )
    expected = contract["expected"]
    sample_indices = [int(row["sample_index"]) for row in samples]
    _require(
        len(samples) == int(expected["sample_count"])
        and sample_indices
        == list(
            range(
                int(expected["first_sample_index"]),
                int(expected["last_sample_index"]) + 1,
            )
        ),
        "physical sample membership changed",
    )
    sample_host = [_sample_host_ns(row) for row in samples]
    _require(
        sample_host == sorted(set(sample_host)),
        "sample completion timestamps are not strict",
    )
    roles = {
        "c922": str(expected["c922_role"]),
        "d405": str(expected["d405_role"]),
    }
    frames = {
        stream: admitted_callback_frames(callbacks, role=role)
        for stream, role in roles.items()
    }
    _require(
        len(frames["c922"]) == int(expected["c922_frame_count"])
        and len(frames["d405"]) == int(expected["d405_frame_count"]),
        "admitted callback frame count changed",
    )
    bindings = []
    for row, host_ns in zip(samples, sample_host, strict=True):
        bindings.append(
            {
                "sample_index": int(row["sample_index"]),
                "sample_time_seconds": float(
                    row["timestamp_monotonic_seconds"]
                ),
                "sample_host_continuous_ns": host_ns,
                "recorded_overhead_video_time_seconds": float(
                    row["overhead_video_time_seconds"]
                ),
                "recorded_wrist_video_time_seconds": float(
                    row["wrist_video_time_seconds"]
                ),
                "c922": nearest_frame_binding(
                    frames["c922"], sample_host_continuous_ns=host_ns
                ),
                "d405": nearest_frame_binding(
                    frames["d405"], sample_host_continuous_ns=host_ns
                ),
                "diagnostics": {
                    "gripper_requested_degrees": float(
                        row["follower_requested_degrees"][-1]
                    ),
                    "gripper_command_degrees": float(
                        row["follower_command_degrees"][-1]
                    ),
                    "gripper_measured_degrees": float(
                        row["follower_actual_position_degrees"][-1]
                    ),
                    "gripper_contact_deflection": float(
                        row["gripper_contact_deflection"]
                    ),
                    "gripper_motor_current_raw": float(
                        row["available_motor_current_raw"]["gripper"]
                    ),
                    "gripper_contact_hold_flag": bool(
                        row["gripper_contact_hold"]
                    ),
                },
            }
        )
    max_errors = {
        stream: max(
            float(row[stream]["association_error_ms"]) for row in bindings
        )
        for stream in roles
    }
    _require(
        max_errors["c922"]
        <= float(expected["maximum_c922_association_error_ms"])
        and max_errors["d405"]
        <= float(expected["maximum_d405_association_error_ms"]),
        "sample/frame timestamp association exceeds frozen bounds",
    )
    phase_by_sample: dict[int, str] = {}
    for window in contract["telemetry_only_windows"]:
        for sample_index in window["sample_indices"]:
            phase_by_sample[int(sample_index)] = str(window["window_id"])
    schedule = [
        {
            **bindings[sample_index],
            "telemetry_window_id": phase_by_sample[sample_index],
        }
        for sample_index in sorted(phase_by_sample)
    ]
    unsigned = {
        "schema_version": SCHEDULE_RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "contract_sha256": contract_sha256 or canonical_digest(contract),
        "source_sample_count": len(samples),
        "source_frame_counts": {
            stream: len(items) for stream, items in frames.items()
        },
        "sample_frame_bindings": bindings,
        "schedule": schedule,
        "schedule_sample_count": len(schedule),
        "unique_schedule_frame_counts": {
            stream: len(
                {int(row[stream]["frame_index"]) for row in schedule}
            )
            for stream in roles
        },
        "maximum_association_error_ms": max_errors,
        "association": contract["association"],
        "annotation_policy": contract["annotation_policy"],
        "successor_lineage": contract.get("successor_lineage"),
        "proof_boundaries": contract["proof_boundaries"],
        "authority": contract["authority"],
        "result": "TIMESTAMP_BOUND_TELEMETRY_SCHEDULE_FROZEN_VISUAL_LABELS_UNOPENED",
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def build_schedule_receipt(
    contract_path: Path = SCHEDULE_CONTRACT_PATH,
    output_path: Path = SCHEDULE_OUTPUT_PATH,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_schedule_contract(contract_path, root=root)
    receipt = compile_schedule(
        contract,
        root=root,
        contract_sha256=sha256_file(contract_path),
    )
    atomic_write_json(output_path, receipt)
    return receipt


def extract_schedule_frames(
    receipt: dict[str, Any],
    contract: dict[str, Any],
    output_directory: Path = FRAME_OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    output_directory.mkdir(parents=True, exist_ok=True)
    video_bindings = {
        "c922": contract["sources"]["c922_video"],
        "d405": contract["sources"]["d405_video"],
    }
    selected_by_stream = {
        stream: sorted(
            {int(row[stream]["frame_index"]) for row in receipt["schedule"]}
        )
        for stream in video_bindings
    }
    manifest: dict[str, Any] = {"streams": {}}
    for stream, binding in video_bindings.items():
        video_path = _bound_path(
            binding, root=root, label=f"{stream} browser video"
        )
        selected = set(selected_by_stream[stream])
        capture = cv2.VideoCapture(str(video_path))
        _require(capture.isOpened(), f"cannot open {stream} browser video")
        frame_index = 0
        members = []
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame_index in selected:
                path = output_directory / f"{stream}-frame-{frame_index:04d}.png"
                _require(cv2.imwrite(str(path), frame), f"cannot write {path.name}")
                members.append(
                    {
                        "frame_index": frame_index,
                        "path": str(path.relative_to(root)),
                        "sha256": sha256_file(path),
                    }
                )
            frame_index += 1
        capture.release()
        _require(
            [row["frame_index"] for row in members]
            == selected_by_stream[stream],
            f"{stream} frame extraction is incomplete",
        )
        manifest["streams"][stream] = {
            "source_video_sha256": binding["sha256"],
            "decoded_frame_count": frame_index,
            "members": members,
        }
    unsigned = {
        "schema_version": "sim2claw.observable_physical_episode_frame_manifest.v1",
        "schedule_artifact_sha256": receipt["artifact_sha256"],
        **manifest,
    }
    result = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_directory / "manifest.json", result)
    return result


def load_observation_contract(
    path: Path = OBSERVATION_CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="physical episode observations")
    _require(
        contract.get("schema_version") == OBSERVATION_SCHEMA,
        "unsupported physical observation schema",
    )
    sources = contract.get("sources")
    _require(
        isinstance(sources, dict) and sources,
        "physical observation sources are missing",
    )
    for source_id, binding in sources.items():
        _require(
            isinstance(binding, dict),
            f"invalid physical observation source: {source_id}",
        )
        _bound_path(binding, root=root, label=source_id)
    tracking = contract.get("tracking")
    _require(
        isinstance(tracking, dict)
        and tracking.get("algorithm")
        == "opencv_pyramidal_lucas_kanade"
        and tracking.get("failed_tracks_abstain") is True
        and tracking.get("labels")
        == [
            "fixed_jaw_tip",
            "moving_jaw_tip",
            "selected_pawn_crown",
        ],
        "physical observation tracking family changed",
    )
    events = contract.get("two_pass_visual_events")
    _require(
        isinstance(events, dict)
        and events.get("same_system_two_pass_not_independent_humans") is True
        and events.get("exact_contact_visible") is False
        and events.get("metric_contact_point_visible") is False
        and events.get("pass_a") == events.get("pass_b"),
        "physical event review changed",
    )
    boundaries = contract.get("proof_boundaries")
    authority = contract.get("authority")
    _require(
        isinstance(boundaries, dict)
        and boundaries
        and not any(boundaries.values()),
        "physical observation proof boundary widened",
    )
    _require(
        isinstance(authority, dict) and authority and not any(authority.values()),
        "physical observation authority widened",
    )
    return contract


def _decode_grayscale_video(path: Path) -> list[np.ndarray]:
    capture = cv2.VideoCapture(str(path))
    _require(capture.isOpened(), "cannot open physical observation video")
    frames: list[np.ndarray] = []
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    capture.release()
    _require(frames, "physical observation video is empty")
    return frames


def _flow_parameters(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "winSize": tuple(int(value) for value in config["window_size_px"]),
        "maxLevel": int(config["maximum_pyramid_level"]),
        "criteria": (
            cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
            int(config["maximum_iterations"]),
            float(config["epsilon"]),
        ),
        "minEigThreshold": float(config["minimum_eigenvalue_threshold"]),
    }


def bidirectional_point_tracks(
    frames: list[np.ndarray], tracking: dict[str, Any]
) -> dict[int, dict[str, Any]]:
    start, end = [int(value) for value in tracking["frame_range_inclusive"]]
    _require(
        0 <= start < end < len(frames),
        "physical tracking frame range is invalid",
    )
    labels = [str(value) for value in tracking["labels"]]
    first = np.asarray(
        tracking["pass_a"]["anchor_points_xy"], dtype=np.float32
    ).reshape(-1, 1, 2)
    last = np.asarray(
        tracking["pass_b"]["anchor_points_xy"], dtype=np.float32
    ).reshape(-1, 1, 2)
    _require(
        first.shape == last.shape == (len(labels), 1, 2),
        "physical tracking anchor shape changed",
    )
    parameters = _flow_parameters(tracking["opencv_parameters"])
    pass_a = {start: first.copy()}
    current = first
    for frame_index in range(start, end):
        following, status, _ = cv2.calcOpticalFlowPyrLK(
            frames[frame_index],
            frames[frame_index + 1],
            current,
            None,
            **parameters,
        )
        _require(
            following is not None
            and status is not None
            and bool(np.all(status == 1)),
            "ascending physical point track failed",
        )
        current = following
        pass_a[frame_index + 1] = current.copy()
    pass_b = {end: last.copy()}
    current = last
    for frame_index in range(end, start, -1):
        preceding, status, _ = cv2.calcOpticalFlowPyrLK(
            frames[frame_index],
            frames[frame_index - 1],
            current,
            None,
            **parameters,
        )
        _require(
            preceding is not None
            and status is not None
            and bool(np.all(status == 1)),
            "descending physical point track failed",
        )
        current = preceding
        pass_b[frame_index - 1] = current.copy()
    result: dict[int, dict[str, Any]] = {}
    for frame_index in range(start, end + 1):
        first_points = pass_a[frame_index][:, 0].astype(np.float64)
        second_points = pass_b[frame_index][:, 0].astype(np.float64)
        rows = {}
        for label_index, label in enumerate(labels):
            disagreement = float(
                np.linalg.norm(
                    first_points[label_index] - second_points[label_index]
                )
            )
            threshold = (
                float(tracking["maximum_pawn_crown_pass_disagreement_px"])
                if label == "selected_pawn_crown"
                else float(tracking["maximum_jaw_tip_pass_disagreement_px"])
            )
            accepted = disagreement <= threshold
            rows[label] = {
                "pass_a_xy": first_points[label_index].tolist(),
                "pass_b_xy": second_points[label_index].tolist(),
                "consensus_xy": (
                    np.mean(
                        np.stack(
                            (
                                first_points[label_index],
                                second_points[label_index],
                            )
                        ),
                        axis=0,
                    ).tolist()
                    if accepted
                    else None
                ),
                "pass_disagreement_px": disagreement,
                "accepted": accepted,
                "missing_reason": (
                    None
                    if accepted
                    else "two_pass_disagreement_exceeds_frozen_gate"
                ),
            }
        result[frame_index] = rows
    return result


def _sample_time_lookup(
    schedule_receipt: dict[str, Any],
) -> dict[int, dict[str, Any]]:
    return {
        int(row["sample_index"]): row
        for row in schedule_receipt["sample_frame_bindings"]
    }


def _event_with_time(
    value: int | list[int],
    sample_rows: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    members = [int(value)] if isinstance(value, int) else [int(v) for v in value]
    _require(
        len(members) in (1, 2)
        and all(member in sample_rows for member in members),
        "physical event sample is missing",
    )
    return {
        "sample_indices": members,
        "time_seconds": [
            float(sample_rows[member]["sample_time_seconds"])
            for member in members
        ],
        "d405_frame_indices": [
            int(sample_rows[member]["d405"]["frame_index"])
            for member in members
        ],
        "c922_frame_indices": [
            int(sample_rows[member]["c922"]["frame_index"])
            for member in members
        ],
    }


def evaluate_physical_observations(
    contract: dict[str, Any], *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    sources = contract["sources"]
    schedule = load_json_object(
        _bound_path(
            sources["schedule_receipt"], root=root, label="schedule receipt"
        ),
        label="schedule receipt",
    )
    frame_manifest = load_json_object(
        _bound_path(
            sources["frame_manifest"], root=root, label="frame manifest"
        ),
        label="frame manifest",
    )
    _require(
        frame_manifest["schedule_artifact_sha256"]
        == schedule["artifact_sha256"],
        "schedule/frame-manifest lineage changed",
    )
    video_path = _bound_path(
        sources["d405_video"], root=root, label="D405 browser video"
    )
    frames = _decode_grayscale_video(video_path)
    _require(
        len(frames)
        == int(schedule["source_frame_counts"]["d405"])
        == int(frame_manifest["streams"]["d405"]["decoded_frame_count"]),
        "D405 decoded frame count changed",
    )
    tracks = bidirectional_point_tracks(frames, contract["tracking"])
    sample_rows = _sample_time_lookup(schedule)
    scheduled_tracks = []
    accepted_counts = {
        label: 0 for label in contract["tracking"]["labels"]
    }
    for row in schedule["schedule"]:
        frame_index = int(row["d405"]["frame_index"])
        if frame_index not in tracks:
            continue
        points = tracks[frame_index]
        for label, point in points.items():
            accepted_counts[label] += int(point["accepted"])
        scheduled_tracks.append(
            {
                "sample_index": int(row["sample_index"]),
                "sample_time_seconds": float(row["sample_time_seconds"]),
                "d405_frame_index": frame_index,
                "association_error_ms": float(
                    row["d405"]["association_error_ms"]
                ),
                "points": points,
            }
        )
    events_config = contract["two_pass_visual_events"]
    event_rows = {
        key: _event_with_time(value, sample_rows)
        for key, value in events_config["pass_a"].items()
    }
    endpoint = load_json_object(
        _bound_path(
            sources["endpoint_receipt"], root=root, label="endpoint receipt"
        ),
        label="endpoint receipt",
    )
    endpoint_checks = endpoint["observations"]["gates"]
    or0 = load_json_object(
        _bound_path(sources["or0_receipt"], root=root, label="OR0 receipt"),
        label="OR0 receipt",
    )
    acceptance = contract["acceptance"]
    checks = {
        "fixed_jaw_track_count": accepted_counts["fixed_jaw_tip"]
        >= int(acceptance["minimum_accepted_fixed_jaw_track_samples"]),
        "moving_jaw_track_count": accepted_counts["moving_jaw_tip"]
        >= int(acceptance["minimum_accepted_moving_jaw_track_samples"]),
        "pawn_crown_track_count": accepted_counts["selected_pawn_crown"]
        >= int(acceptance["minimum_accepted_pawn_crown_track_samples"]),
        "contact_interval_consensus": (
            events_config["pass_a"]["candidate_contact_interval_samples"]
            == events_config["pass_b"]["candidate_contact_interval_samples"]
        ),
        "carried_motion_interval_consensus": (
            events_config["pass_a"][
                "definite_carried_motion_interval_samples"
            ]
            == events_config["pass_b"][
                "definite_carried_motion_interval_samples"
            ]
        ),
        "release_interval_consensus": (
            events_config["pass_a"]["candidate_release_interval_samples"]
            == events_config["pass_b"]["candidate_release_interval_samples"]
        ),
        "terminal_d2_upright_endpoint": bool(
            endpoint_checks["terminal_d2_metric_endpoint"]
            and endpoint_checks["terminal_upright_reviewed"]
        ),
        "schedule_frozen_before_visual_open": bool(
            schedule["successor_lineage"]["invariants"][
                "visual_frames_opened_before_freeze"
            ]
            is False
        ),
    }
    accepted = bool(all(checks.values()))
    observable_episode = {
        "schema_version": contract["observable_episode"]["schema_version"],
        "recording_id": contract["observable_episode"]["recording_id"],
        "instruction": contract["observable_episode"]["instruction"],
        "time_base": {
            "sample_clock": schedule["association"]["sample_clock_field"],
            "frame_clock": schedule["association"]["frame_clock_field"],
            "camera_exposure_synchronized": False,
            "cross_camera_exposure_synchronized": False,
        },
        "actions": {
            "count": int(or0["sealed_episode"]["sample_count"]),
            "requested_float32_sha256": or0["sealed_episode"][
                "requested_float32_sha256"
            ],
            "gateway_sent_float32_sha256": or0["sealed_episode"][
                "gateway_sent_float32_sha256"
            ],
            "measured_float64_sha256": or0["sealed_episode"][
                "measured_float64_sha256"
            ],
            "timestamps_float64_sha256": or0["sealed_episode"][
                "timestamps_float64_sha256"
            ],
        },
        "object_observations": {
            "selected_object": contract["observable_episode"][
                "selected_object"
            ],
            "wrist_rgb_tracks": scheduled_tracks,
            "accepted_track_counts": accepted_counts,
            "metric_depth_available": False,
            "metric_object_pose_available": False,
            "terminal_board_endpoint": endpoint["observations"]["terminal"],
        },
        "contact_and_motion_events": event_rows,
        "outcome": {
            "source_square": contract["observable_episode"]["source_square"],
            "destination_square": contract["observable_episode"][
                "destination_square"
            ],
            "terminal_d2_metric_endpoint": endpoint_checks[
                "terminal_d2_metric_endpoint"
            ],
            "terminal_upright_reviewed": endpoint_checks[
                "terminal_upright_reviewed"
            ],
            "physical_action_trajectory_to_physical_task_outcome": True,
            "physical_action_trajectory_to_matching_simulator_outcome": False,
        },
        "missingness": {
            "metric_wrist_depth": "unavailable",
            "instrumented_contact_state": "unavailable",
            "metric_contact_point": "unavailable",
            "calibrated_grasp_force": "unavailable",
            "camera_exposure_time": "unavailable",
            "cross_camera_exposure_sync": "unavailable",
        },
    }
    unsigned = {
        "schema_version": OBSERVATION_RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "contract_sha256": sha256_file(OBSERVATION_CONTRACT_PATH),
        "schedule_artifact_sha256": schedule["artifact_sha256"],
        "frame_manifest_artifact_sha256": frame_manifest["artifact_sha256"],
        "tracking": {
            "frame_range_inclusive": contract["tracking"][
                "frame_range_inclusive"
            ],
            "accepted_counts": accepted_counts,
            "scheduled_track_rows": len(scheduled_tracks),
            "rows": scheduled_tracks,
        },
        "events": event_rows,
        "two_pass_event_consensus": True,
        "observable_episode": observable_episode,
        "checks": checks,
        "accepted": accepted,
        "result": (
            "OBSERVABLE_PHYSICAL_EPISODE_ACCEPTED"
            if accepted
            else "OBSERVABLE_PHYSICAL_EPISODE_REJECTED"
        ),
        "proof_boundaries": contract["proof_boundaries"],
        "authority": contract["authority"],
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def build_observation_receipt(
    contract_path: Path = OBSERVATION_CONTRACT_PATH,
    output_path: Path = OBSERVATION_OUTPUT_PATH,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_observation_contract(contract_path, root=root)
    receipt = evaluate_physical_observations(contract, root=root)
    atomic_write_json(output_path, receipt)
    return receipt


__all__ = [
    "FRAME_OUTPUT_DIRECTORY",
    "OBSERVATION_CONTRACT_PATH",
    "OBSERVATION_OUTPUT_PATH",
    "SCHEDULE_CONTRACT_PATH",
    "SCHEDULE_OUTPUT_PATH",
    "SCHEDULE_V1_CONTRACT_PATH",
    "admitted_callback_frames",
    "bidirectional_point_tracks",
    "build_observation_receipt",
    "build_schedule_receipt",
    "compile_schedule",
    "extract_schedule_frames",
    "evaluate_physical_observations",
    "load_observation_contract",
    "load_schedule_contract",
    "nearest_frame_binding",
]

"""Compile timestamp-bound physical RGB observations without inventing depth."""

from __future__ import annotations

import bisect
import json
from pathlib import Path
from typing import Any

import cv2

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .paths import REPO_ROOT


SCHEDULE_SCHEMA = "sim2claw.observable_physical_episode_schedule_contract.v1"
SCHEDULE_RECEIPT_SCHEMA = (
    "sim2claw.observable_physical_episode_schedule_receipt.v1"
)
SCHEDULE_CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "observable_physical_episode_schedule_v1.json"
)
SCHEDULE_OUTPUT_PATH = (
    REPO_ROOT
    / "outputs"
    / "observable_physical_episode_schedule_v1"
    / "receipt.json"
)
FRAME_OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs"
    / "observable_physical_episode_schedule_v1"
    / "frames"
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
    contract: dict[str, Any], *, root: Path = REPO_ROOT
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
        "contract_sha256": (
            sha256_file(SCHEDULE_CONTRACT_PATH)
            if root == REPO_ROOT and SCHEDULE_CONTRACT_PATH.is_file()
            else canonical_digest(contract)
        ),
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
    receipt = compile_schedule(contract, root=root)
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


__all__ = [
    "FRAME_OUTPUT_DIRECTORY",
    "SCHEDULE_CONTRACT_PATH",
    "SCHEDULE_OUTPUT_PATH",
    "admitted_callback_frames",
    "build_schedule_receipt",
    "compile_schedule",
    "extract_schedule_frames",
    "load_schedule_contract",
    "nearest_frame_binding",
]

"""Qualified endpoint-appearance evidence from retained C922 videos.

The compiler intentionally does not call a source- or destination-appearance
transition a grasp, contact, lift, or metric object pose. The robot commonly
occludes the source before the gripper closes. These curves are useful because
they bound what the video can and cannot say about the gripper plateau.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np

from .interaction_events import extract_event_indices, load_event_contract
from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT


CONTRACT_PATH = REPO_ROOT / "configs" / "vision" / "pawn_bg_endpoint_motion_v1.json"
SCHEMA = "sim2claw.pawn_bg_endpoint_motion.v1"
RECEIPT_SCHEMA = "sim2claw.pawn_bg_endpoint_motion_receipt.v1"
TRACE_SCHEMA = "sim2claw.pawn_bg_endpoint_appearance_trace.v1"


class EndpointMotionError(RuntimeError):
    """The source evidence or fail-closed appearance contract is invalid."""


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EndpointMotionError(f"cannot read {label} {path}: {error}") from error
    if not isinstance(value, dict):
        raise EndpointMotionError(f"{label} must be a JSON object")
    return value


def load_endpoint_motion_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = _load_object(path, "endpoint motion contract")
    if contract.get("schema_version") != SCHEMA:
        raise EndpointMotionError("unexpected endpoint motion contract schema")
    authority = contract.get("authority")
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise EndpointMotionError("endpoint motion authority widened")
    selection = contract.get("episode_selection", {})
    if (
        selection.get("partition") != "train"
        or selection.get("held_out_video_reads_allowed") is not False
        or int(selection.get("expected_episode_count", 0)) != 11
    ):
        raise EndpointMotionError("training-only episode boundary changed")
    interpretation = contract.get("interpretation", {})
    prohibited = (
        "contact_claim_allowed",
        "grasp_claim_allowed",
        "lift_claim_allowed",
        "metric_trajectory_claim_allowed",
    )
    if any(interpretation.get(key) is not False for key in prohibited):
        raise EndpointMotionError("appearance event claim boundary widened")
    for binding in contract.get("bindings", {}).values():
        source = (REPO_ROOT / str(binding["path"])).resolve()
        if not source.is_file() or sha256_file(source) != binding["sha256"]:
            raise EndpointMotionError(f"bound source changed: {source}")
    return contract


def _load_sample_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    previous_time: float | None = None
    with path.open("r", encoding="utf-8") as handle:
        for expected_index, line in enumerate(handle):
            raw = json.loads(line)
            if raw.get("sample_index") != expected_index:
                raise EndpointMotionError(f"sample index changed in {path}")
            video_time = float(raw["overhead_video_time_seconds"])
            if not math.isfinite(video_time) or (
                previous_time is not None and video_time <= previous_time
            ):
                raise EndpointMotionError(f"video timestamps are invalid in {path}")
            previous_time = video_time
            rows.append(raw)
    if len(rows) < 10:
        raise EndpointMotionError(f"too few source rows in {path}")
    return rows


def _roi_gray(image: np.ndarray, center: Sequence[float], radius: int) -> np.ndarray:
    if image is None or image.ndim != 3:
        raise EndpointMotionError("decoded frame is invalid")
    x, y = (int(round(float(value))) for value in center)
    if x - radius < 0 or y - radius < 0 or x + radius >= image.shape[1] or y + radius >= image.shape[0]:
        raise EndpointMotionError("endpoint ROI falls outside the decoded frame")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return gray[y - radius : y + radius + 1, x - radius : x + radius + 1].astype(
        np.float64
    )


def normalized_correlation(first: np.ndarray, second: np.ndarray) -> float:
    """Return zero-mean normalized correlation, including degenerate guards."""

    left = np.asarray(first, dtype=np.float64)
    right = np.asarray(second, dtype=np.float64)
    if left.shape != right.shape or left.size == 0:
        raise EndpointMotionError("appearance patches must have one non-empty shape")
    left = left.ravel() - float(np.mean(left))
    right = right.ravel() - float(np.mean(right))
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator <= 1e-12:
        return 1.0 if np.allclose(left, right) else 0.0
    return float(np.clip((left @ right) / denominator, -1.0, 1.0))


def _first_sustained(
    values: Sequence[float],
    *,
    start_index: int,
    count: int,
    predicate: Any,
) -> int | None:
    for index in range(start_index, len(values) - count + 1):
        if all(predicate(float(value)) for value in values[index : index + count]):
            return index
    return None


def _decode_sample_frames(
    video_path: Path, video_times: Sequence[float]
) -> tuple[list[np.ndarray], float, list[int], list[float]]:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise EndpointMotionError(f"could not open source video {video_path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    if not math.isfinite(fps) or fps <= 0.0:
        capture.release()
        raise EndpointMotionError(f"invalid source FPS for {video_path}")
    target_indices = [int(round(float(value) * fps)) for value in video_times]
    unique_indices = sorted(set(target_indices))
    decoded: dict[int, np.ndarray] = {}
    capture.set(cv2.CAP_PROP_POS_FRAMES, unique_indices[0])
    position = unique_indices[0]
    try:
        for target in unique_indices:
            while position <= target:
                ok, frame = capture.read()
                if not ok:
                    raise EndpointMotionError(
                        f"frame decode failed for {video_path} at index {position}"
                    )
                if position == target:
                    decoded[target] = frame
                position += 1
    finally:
        capture.release()
    frames = [decoded[index] for index in target_indices]
    decoded_times = [index / fps for index in target_indices]
    return frames, fps, target_indices, decoded_times


def _event_by_name(events: Mapping[str, int], name: str) -> int:
    if name not in events:
        raise EndpointMotionError(f"missing kinematic event {name}")
    return int(events[name])


def _draw_trace(
    *,
    source_values: Sequence[float],
    destination_values: Sequence[float],
    events: Mapping[str, int],
    source_loss: int,
    destination_appearance: int,
    contract: Mapping[str, Any],
    output_path: Path,
) -> None:
    width, height = 1500, 720
    left, right, top, bottom = 95, 45, 70, 100
    canvas = np.full((height, width, 3), 250, dtype=np.uint8)
    plot_width = width - left - right
    plot_height = height - top - bottom
    count = len(source_values)

    def xy(index: int, value: float) -> tuple[int, int]:
        x = left + int(round(index * plot_width / max(1, count - 1)))
        y = top + int(round((1.0 - (value + 1.0) / 2.0) * plot_height))
        return x, y

    cv2.rectangle(canvas, (left, top), (left + plot_width, top + plot_height), (40, 40, 40), 2)
    for value in (-1.0, -0.5, 0.0, 0.5, 1.0):
        y = xy(0, value)[1]
        cv2.line(canvas, (left, y), (left + plot_width, y), (220, 220, 220), 1)
        cv2.putText(canvas, f"{value:+.1f}", (15, y + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (30, 30, 30), 1, cv2.LINE_AA)
    for values, color in ((source_values, (220, 90, 30)), (destination_values, (40, 150, 40))):
        points = np.asarray([xy(index, float(value)) for index, value in enumerate(values)], dtype=np.int32)
        cv2.polylines(canvas, [points.reshape(-1, 1, 2)], False, color, 2, cv2.LINE_AA)
    thresholds = contract["appearance_model"]
    for value, color in (
        (float(thresholds["source_loss_maximum_normalized_correlation"]), (220, 90, 30)),
        (float(thresholds["destination_appearance_minimum_normalized_correlation"]), (40, 150, 40)),
    ):
        y = xy(0, value)[1]
        cv2.line(canvas, (left, y), (left + plot_width, y), color, 1, cv2.LINE_AA)
    event_colors = {
        "closure_onset": (120, 0, 180),
        "near_closed_crossing": (160, 50, 200),
        "release_onset": (0, 110, 220),
        "destination_open_peak": (0, 170, 240),
    }
    for name, color in event_colors.items():
        index = _event_by_name(events, name)
        x = xy(index, 0.0)[0]
        cv2.line(canvas, (x, top), (x, top + plot_height), color, 2, cv2.LINE_AA)
        cv2.putText(canvas, name, (x + 4, top + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 1, cv2.LINE_AA)
    for index, label, color in (
        (source_loss, "source visibility loss", (220, 90, 30)),
        (destination_appearance, "destination final appearance", (40, 150, 40)),
    ):
        x = xy(index, 0.0)[0]
        cv2.line(canvas, (x, top), (x, top + plot_height), color, 3, cv2.LINE_AA)
        cv2.putText(canvas, label, (x + 4, top + plot_height - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
    cv2.putText(canvas, "endpoint appearance correlation vs owner-reviewed initial/final frames", (left, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (25, 25, 25), 2, cv2.LINE_AA)
    cv2.putText(canvas, "blue=source reference  green=destination final reference; transitions are interval evidence, not contact", (left, height - 38), cv2.FONT_HERSHEY_SIMPLEX, 0.64, (25, 25, 25), 1, cv2.LINE_AA)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), canvas):
        raise EndpointMotionError(f"could not write trace plot {output_path}")


def _selected_episode_inputs(
    contract: Mapping[str, Any]
) -> list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]:
    bindings = contract["bindings"]
    catalog = _load_object(REPO_ROOT / bindings["catalog"]["path"], "catalog")
    split = _load_object(REPO_ROOT / bindings["split"]["path"], "split")
    owner = _load_object(
        REPO_ROOT / bindings["owner_endpoint_manifest"]["path"], "owner endpoint manifest"
    )
    roles = {str(row["episode_id"]): str(row["split"]) for row in split["episodes"]}
    markers: dict[str, dict[str, dict[str, Any]]] = {}
    for marker in owner["accepted_markers"]:
        recording_id = str(marker["source_recording_id"])
        markers.setdefault(recording_id, {})[str(marker["phase"])] = dict(marker)
    selected = []
    for episode in catalog["episodes"]:
        recording_id = str(episode["recording_id"])
        if roles.get(recording_id) != "train" or recording_id not in markers:
            continue
        phases = markers[recording_id]
        if set(phases) != {"initial", "final"}:
            raise EndpointMotionError(f"endpoint marker phases changed for {recording_id}")
        selected.append((dict(episode), phases["initial"], phases["final"]))
    expected = int(contract["episode_selection"]["expected_episode_count"])
    if len(selected) != expected:
        raise EndpointMotionError(f"expected {expected} product train episodes, found {len(selected)}")
    return selected


def run_endpoint_motion_pipeline(
    *, output_root: Path, contract_path: Path = CONTRACT_PATH
) -> dict[str, Any]:
    contract = load_endpoint_motion_contract(contract_path)
    event_contract = load_event_contract(
        REPO_ROOT / contract["bindings"]["event_contract"]["path"], repo_root=REPO_ROOT
    )
    episodes = _selected_episode_inputs(contract)
    settings = contract["appearance_model"]
    radius = int(settings["grayscale_roi_radius_px"])
    sustained = int(settings["minimum_sustained_samples"])
    source_threshold = float(settings["source_loss_maximum_normalized_correlation"])
    destination_threshold = float(
        settings["destination_appearance_minimum_normalized_correlation"]
    )
    episode_receipts: list[dict[str, Any]] = []
    all_source_deltas: list[float] = []
    all_destination_deltas: list[float] = []
    for episode, initial_marker, final_marker in episodes:
        recording_id = str(episode["recording_id"])
        samples_path = (REPO_ROOT / episode["assets"]["samples"]).resolve()
        video_path = (REPO_ROOT / episode["assets"]["overhead_video"]).resolve()
        if sha256_file(samples_path) != episode["samples_sha256"]:
            raise EndpointMotionError(f"sample digest changed for {recording_id}")
        if sha256_file(video_path) != episode["overhead_video_sha256"]:
            raise EndpointMotionError(f"video digest changed for {recording_id}")
        initial_path = Path(initial_marker["frame_path"]).resolve()
        final_path = Path(final_marker["frame_path"]).resolve()
        if sha256_file(initial_path) != initial_marker["frame_sha256"]:
            raise EndpointMotionError(f"initial marker frame changed for {recording_id}")
        if sha256_file(final_path) != final_marker["frame_sha256"]:
            raise EndpointMotionError(f"final marker frame changed for {recording_id}")
        initial_image = cv2.imread(str(initial_path), cv2.IMREAD_COLOR)
        final_image = cv2.imread(str(final_path), cv2.IMREAD_COLOR)
        source_center = initial_marker["visual_fiducial_center_px"]
        destination_center = final_marker["visual_fiducial_center_px"]
        source_reference = _roi_gray(initial_image, source_center, radius)
        destination_reference = _roi_gray(final_image, destination_center, radius)
        rows = _load_sample_rows(samples_path)
        video_times = [float(row["overhead_video_time_seconds"]) for row in rows]
        frames, fps, frame_indices, decoded_times = _decode_sample_frames(video_path, video_times)
        source_values: list[float] = []
        destination_values: list[float] = []
        trace_rows: list[dict[str, Any]] = []
        for index, (row, frame, frame_index, decoded_time) in enumerate(
            zip(rows, frames, frame_indices, decoded_times, strict=True)
        ):
            source_patch = _roi_gray(frame, source_center, radius)
            destination_patch = _roi_gray(frame, destination_center, radius)
            source_correlation = normalized_correlation(source_reference, source_patch)
            destination_correlation = normalized_correlation(
                destination_reference, destination_patch
            )
            source_values.append(source_correlation)
            destination_values.append(destination_correlation)
            trace_rows.append(
                {
                    "schema_version": TRACE_SCHEMA,
                    "recording_id": recording_id,
                    "sample_index": index,
                    "timestamp_monotonic_seconds": float(row["timestamp_monotonic_seconds"]),
                    "requested_video_time_seconds": float(row["overhead_video_time_seconds"]),
                    "decoded_frame_index": int(frame_index),
                    "decoded_video_time_seconds": float(decoded_time),
                    "decode_time_error_seconds": float(
                        decoded_time - float(row["overhead_video_time_seconds"])
                    ),
                    "source_reference_correlation": source_correlation,
                    "destination_final_reference_correlation": destination_correlation,
                    "metric_pose_available": False,
                    "contact_observed": False,
                }
            )
        source_loss = _first_sustained(
            source_values,
            start_index=int(len(rows) * float(settings["source_search_start_fraction"])),
            count=sustained,
            predicate=lambda value: value < source_threshold,
        )
        destination_appearance = _first_sustained(
            destination_values,
            start_index=int(
                len(rows) * float(settings["destination_search_start_fraction"])
            ),
            count=sustained,
            predicate=lambda value: value >= destination_threshold,
        )
        if source_loss is None or destination_appearance is None:
            raise EndpointMotionError(
                f"appearance transition abstained for {recording_id}: "
                f"source={source_loss}, destination={destination_appearance}"
            )
        events = extract_event_indices(rows, event_contract)
        closure_onset = _event_by_name(events, "closure_onset")
        release_onset = _event_by_name(events, "release_onset")
        destination_open = _event_by_name(events, "destination_open_peak")
        source_delta = float(
            rows[source_loss]["timestamp_monotonic_seconds"]
            - rows[closure_onset]["timestamp_monotonic_seconds"]
        )
        destination_delta = float(
            rows[destination_appearance]["timestamp_monotonic_seconds"]
            - rows[release_onset]["timestamp_monotonic_seconds"]
        )
        all_source_deltas.append(source_delta)
        all_destination_deltas.append(destination_delta)
        episode_root = output_root.resolve() / "episodes" / recording_id
        episode_root.mkdir(parents=True, exist_ok=True)
        trace_path = episode_root / "endpoint_appearance_trace.jsonl"
        trace_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in trace_rows),
            encoding="utf-8",
        )
        plot_path = episode_root / "endpoint_appearance_vs_gripper.png"
        _draw_trace(
            source_values=source_values,
            destination_values=destination_values,
            events=events,
            source_loss=source_loss,
            destination_appearance=destination_appearance,
            contract=contract,
            output_path=plot_path,
        )
        episode_receipts.append(
            {
                "recording_id": recording_id,
                "folder_label": episode["folder_label"],
                "source_square": initial_marker["square"],
                "destination_square": final_marker["square"],
                "sample_count": len(rows),
                "source_fps": fps,
                "source_visibility_loss": {
                    "sample_index": source_loss,
                    "video_time_seconds": video_times[source_loss],
                    "correlation": source_values[source_loss],
                    "seconds_relative_to_gripper_closure_onset": source_delta,
                    "semantics": contract["interpretation"]["source_loss_semantics"],
                },
                "destination_final_appearance": {
                    "sample_index": destination_appearance,
                    "video_time_seconds": video_times[destination_appearance],
                    "correlation": destination_values[destination_appearance],
                    "seconds_relative_to_gripper_release_onset": destination_delta,
                    "seconds_relative_to_destination_open_peak": float(
                        rows[destination_appearance]["timestamp_monotonic_seconds"]
                        - rows[destination_open]["timestamp_monotonic_seconds"]
                    ),
                    "semantics": contract["interpretation"][
                        "destination_appearance_semantics"
                    ],
                },
                "gripper_event_indices": events,
                "source_assets": {
                    "samples_path": str(samples_path),
                    "samples_sha256": episode["samples_sha256"],
                    "video_path": str(video_path),
                    "video_sha256": episode["overhead_video_sha256"],
                    "initial_marker_frame_sha256": initial_marker["frame_sha256"],
                    "final_marker_frame_sha256": final_marker["frame_sha256"],
                },
                "trace_path": str(trace_path),
                "trace_sha256": sha256_file(trace_path),
                "plot_path": str(plot_path),
                "plot_sha256": sha256_file(plot_path),
                "contact_claimed": False,
                "metric_trajectory_claimed": False,
            }
        )
    source_array = np.asarray(all_source_deltas, dtype=np.float64)
    destination_array = np.asarray(all_destination_deltas, dtype=np.float64)
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "proof_class": "training_only_qualitative_endpoint_appearance_intervals",
        "contract": {
            "path": str(contract_path.resolve()),
            "sha256": sha256_file(contract_path),
        },
        "implementation": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "partition": "train",
        "episode_count": len(episode_receipts),
        "held_out_video_reads": 0,
        "episodes": episode_receipts,
        "summary": {
            "source_visibility_loss_detected_episodes": len(episode_receipts),
            "destination_final_appearance_detected_episodes": len(episode_receipts),
            "mean_source_visibility_loss_relative_to_closure_onset_seconds": float(
                np.mean(source_array)
            ),
            "minimum_source_visibility_loss_relative_to_closure_onset_seconds": float(
                np.min(source_array)
            ),
            "maximum_source_visibility_loss_relative_to_closure_onset_seconds": float(
                np.max(source_array)
            ),
            "mean_destination_appearance_relative_to_release_onset_seconds": float(
                np.mean(destination_array)
            ),
            "minimum_destination_appearance_relative_to_release_onset_seconds": float(
                np.min(destination_array)
            ),
            "maximum_destination_appearance_relative_to_release_onset_seconds": float(
                np.max(destination_array)
            ),
            "interpretation": (
                "Source visibility is generally lost before gripper closure because the arm "
                "occludes the pawn. Destination final appearance is a post-release/settling "
                "anchor. The interval between them does not identify contact or lift."
            ),
        },
        "provider_calls": 0,
        "physical_actions": 0,
        "source_rows_mutated": False,
        "authority": contract["authority"],
        "limitations": [
            "owner_endpoint_markers_are_qualitative_image_space_anchors",
            "final_endpoint_frame_is_a_reference_not_an_independent_validation_label",
            "source_visibility_loss_conflates_departure_occlusion_and_lighting",
            "destination_appearance_does_not_reveal_grasp_contact_or_lift",
            "camera_has_no_admitted_metric_calibration",
            "held_out_videos_are_not_read_by_this_pipeline",
        ],
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    atomic_write_json(output_root.resolve() / "endpoint_motion_receipt.json", receipt)
    return receipt

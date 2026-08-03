"""Untuned four-development-episode baseline for the analytic 3D renderer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_host_native_analytic_3d_renderer_capability import (
    REPO_ROOT,
    render_capability_frame,
    sha256_file,
)
from .observable_registration_temporal_pixel_similarity import (
    _linear_similarity,
    _tolerant_edge_f1,
)


DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_development_shared_camera_baseline_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_development_shared_camera_baseline_v1"


def _summary(values: list[float]) -> dict[str, float | int]:
    if not values:
        raise ValueError("metric population is empty")
    array = np.asarray(values, dtype=np.float64)
    return {
        "count": int(array.size),
        "minimum": float(np.min(array)),
        "p10": float(np.quantile(array, 0.1)),
        "median": float(np.median(array)),
        "mean": float(np.mean(array)),
        "maximum": float(np.max(array)),
    }


def evaluation_times(duration_seconds: float, fps: float) -> np.ndarray:
    if duration_seconds < 0.0 or fps <= 0.0:
        raise ValueError("invalid evaluation timeline")
    count = int(np.floor(duration_seconds * fps + 1e-9)) + 1
    return np.arange(count, dtype=np.float64) / fps


def nearest_trace_indices(trace_times: np.ndarray, target_times: np.ndarray) -> np.ndarray:
    insertion = np.searchsorted(trace_times, target_times, side="left")
    insertion = np.clip(insertion, 0, len(trace_times) - 1)
    previous = np.maximum(insertion - 1, 0)
    choose_previous = np.abs(trace_times[previous] - target_times) <= np.abs(trace_times[insertion] - target_times)
    return np.where(choose_previous, previous, insertion).astype(np.int64)


def physical_frame_indices(
    target_times: np.ndarray, *, frame_count: int, duration_seconds: float
) -> np.ndarray:
    scale = (frame_count - 1) / duration_seconds
    return np.clip(np.rint(target_times * scale), 0, frame_count - 1).astype(np.int64)


def _decode_selected_frames(
    path: Path,
    *,
    selected_indices: np.ndarray,
    expected_frame_count: int,
    expected_width: int,
    expected_height: int,
    output_width: int,
    output_height: int,
) -> list[np.ndarray]:
    wanted = {int(index): slot for slot, index in enumerate(selected_indices.tolist())}
    frames: list[np.ndarray | None] = [None] * len(selected_indices)
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError(f"cannot open development video: {path}")
    decoded = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if frame.shape != (expected_height, expected_width, 3):
            raise ValueError("physical frame shape drifted")
        slot = wanted.get(decoded)
        if slot is not None:
            frames[slot] = cv2.resize(frame, (output_width, output_height), interpolation=cv2.INTER_AREA)
        decoded += 1
    capture.release()
    if decoded != expected_frame_count or any(frame is None for frame in frames):
        raise ValueError("physical timeline decode or selected-frame coverage drifted")
    return [frame for frame in frames if frame is not None]


def _motion_union_similarity(
    physical: np.ndarray,
    simulator: np.ndarray,
    previous_physical: np.ndarray | None,
    previous_simulator: np.ndarray | None,
    config: dict[str, Any],
) -> tuple[float | None, int]:
    if previous_physical is None or previous_simulator is None:
        return None, 0
    kernel = int(config["grayscale_gaussian_kernel_px"])
    physical_gray = cv2.GaussianBlur(cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY), (kernel, kernel), 0)
    simulator_gray = cv2.GaussianBlur(cv2.cvtColor(simulator, cv2.COLOR_BGR2GRAY), (kernel, kernel), 0)
    previous_physical_gray = cv2.GaussianBlur(cv2.cvtColor(previous_physical, cv2.COLOR_BGR2GRAY), (kernel, kernel), 0)
    previous_simulator_gray = cv2.GaussianBlur(cv2.cvtColor(previous_simulator, cv2.COLOR_BGR2GRAY), (kernel, kernel), 0)
    physical_motion = cv2.absdiff(physical_gray, previous_physical_gray) >= int(config["physical_difference_threshold"])
    simulator_motion = cv2.absdiff(simulator_gray, previous_simulator_gray) >= int(config["simulator_difference_threshold"])
    union = physical_motion | simulator_motion
    dilation = int(config["dilation_kernel_px"])
    union = cv2.dilate(union.astype(np.uint8), np.ones((dilation, dilation), dtype=np.uint8)) > 0
    pixel_count = int(union.sum())
    if pixel_count < int(config["minimum_union_pixels"]):
        return None, pixel_count
    return _linear_similarity(physical, simulator, union), pixel_count


def _render_trace_frame(
    scene: dict[str, Any], trace: dict[str, Any], trace_index: int, contract: dict[str, Any]
) -> np.ndarray:
    renderer_contract = {
        "renderer": {
            "width_px": contract["renderer"]["width_px"],
            "height_px": contract["renderer"]["height_px"],
            "recognized_geom_types": ["plane", "box", "sphere", "ellipsoid", "cylinder", "capsule", "mesh"],
            "background_rgb": contract["renderer"]["background_rgb"],
        },
        "sources": {"development_state_trace": {"frame_index": 0}},
    }
    one_frame_trace = {"body_names": trace["body_names"], "frames": [trace["frames"][trace_index]]}
    frame, _ = render_capability_frame(scene, one_frame_trace, renderer_contract)
    return frame


def evaluate_once(
    contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR72 one-run receipt already exists")
    contract = json.loads(contract_path.read_text())
    for source in contract["sources"].values():
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    if len(contract["episodes"]) != 4 or any(row["split_role"] != "development" for row in contract["episodes"]):
        raise ValueError("development split boundary drifted")
    for episode in contract["episodes"]:
        for binding in (episode["physical_video"], episode["state_trace"]):
            if sha256_file(REPO_ROOT / binding["path"]) != binding["sha256"]:
                raise ValueError(f"episode source hash mismatch: {binding['path']}")

    scene_binding = contract["sources"]["shared_scene_manifest"]
    scene = json.loads((REPO_ROOT / scene_binding["path"]).read_text())
    if scene["revision_sha256"] != scene_binding["revision_sha256"]:
        raise ValueError("scene revision mismatch")
    output_directory.mkdir(parents=True, exist_ok=True)
    width = int(contract["renderer"]["width_px"])
    height = int(contract["renderer"]["height_px"])
    fps = float(contract["timeline"]["evaluation_fps"])
    all_rows: list[dict[str, Any]] = []
    episode_summaries: list[dict[str, Any]] = []
    candidate_videos: list[dict[str, Any]] = []

    for episode in contract["episodes"]:
        recording_id = episode["recording_id"]
        trace = json.loads((REPO_ROOT / episode["state_trace"]["path"]).read_text())
        if trace["frame_count"] != episode["state_trace"]["frame_count"]:
            raise ValueError("trace frame count drifted")
        times = evaluation_times(float(episode["state_trace"]["duration_seconds"]), fps)
        trace_times = np.asarray([float(row["t"]) for row in trace["frames"]], dtype=np.float64)
        trace_indices = nearest_trace_indices(trace_times, times)
        physical_binding = episode["physical_video"]
        video_indices = physical_frame_indices(
            times,
            frame_count=int(physical_binding["frame_count"]),
            duration_seconds=float(physical_binding["duration_seconds"]),
        )
        physical_frames = _decode_selected_frames(
            REPO_ROOT / physical_binding["path"],
            selected_indices=video_indices,
            expected_frame_count=int(physical_binding["frame_count"]),
            expected_width=int(physical_binding["width_px"]),
            expected_height=int(physical_binding["height_px"]),
            output_width=width,
            output_height=height,
        )
        candidate_path = output_directory / f"{recording_id}.mp4"
        writer = cv2.VideoWriter(str(candidate_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
        if not writer.isOpened():
            raise RuntimeError("cannot open candidate video writer")
        episode_rows: list[dict[str, Any]] = []
        previous_physical: np.ndarray | None = None
        previous_simulator: np.ndarray | None = None
        try:
            for slot, (time_seconds, trace_index, video_index, physical) in enumerate(
                zip(times, trace_indices, video_indices, physical_frames, strict=True)
            ):
                simulator = _render_trace_frame(scene, trace, int(trace_index), contract)
                writer.write(simulator)
                physical_gray = cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY)
                simulator_gray = cv2.cvtColor(simulator, cv2.COLOR_BGR2GRAY)
                motion_similarity, motion_pixels = _motion_union_similarity(
                    physical,
                    simulator,
                    previous_physical,
                    previous_simulator,
                    contract["metric"]["motion_union"],
                )
                row = {
                    "recording_id": recording_id,
                    "split_role": "development",
                    "evaluation_index": slot,
                    "time_seconds": float(time_seconds),
                    "physical_frame_index": int(video_index),
                    "state_trace_frame_index": int(trace_index),
                    "phase": trace["frames"][int(trace_index)]["phase"],
                    "full_frame_linear_pixel_similarity": _linear_similarity(physical, simulator),
                    "motion_union_linear_pixel_similarity": motion_similarity,
                    "motion_union_pixel_count": motion_pixels,
                    "tolerant_edge_f1": _tolerant_edge_f1(physical_gray, simulator_gray, contract["metric"]["edge"]),
                }
                episode_rows.append(row)
                all_rows.append(row)
                previous_physical = physical
                previous_simulator = simulator
        finally:
            writer.release()
        if not candidate_path.is_file() or candidate_path.stat().st_size == 0:
            raise RuntimeError("candidate video was not emitted")
        primary_values = [float(row["full_frame_linear_pixel_similarity"]) for row in episode_rows]
        edge_values = [float(row["tolerant_edge_f1"]) for row in episode_rows]
        motion_values = [float(row["motion_union_linear_pixel_similarity"]) for row in episode_rows if row["motion_union_linear_pixel_similarity"] is not None]
        episode_summaries.append(
            {
                "recording_id": recording_id,
                "sample_count": len(episode_rows),
                "duration_seconds": float(times[-1]),
                "full_frame_linear_pixel_similarity": _summary(primary_values),
                "motion_union_linear_pixel_similarity": _summary(motion_values),
                "tolerant_edge_f1": _summary(edge_values),
            }
        )
        candidate_videos.append(
            {
                "recording_id": recording_id,
                "path": str(candidate_path.relative_to(REPO_ROOT)),
                "sha256": sha256_file(candidate_path),
                "frame_count": len(episode_rows),
                "fps": fps,
            }
        )

    primary_values = [float(row["full_frame_linear_pixel_similarity"]) for row in all_rows]
    edge_values = [float(row["tolerant_edge_f1"]) for row in all_rows]
    motion_values = [float(row["motion_union_linear_pixel_similarity"]) for row in all_rows if row["motion_union_linear_pixel_similarity"] is not None]
    phases: dict[str, dict[str, float | int]] = {}
    for phase in sorted({str(row["phase"]) for row in all_rows}):
        phases[phase] = _summary([float(row["full_frame_linear_pixel_similarity"]) for row in all_rows if row["phase"] == phase])
    pooled = {
        "full_frame_linear_pixel_similarity": _summary(primary_values),
        "motion_union_linear_pixel_similarity": _summary(motion_values),
        "tolerant_edge_f1": _summary(edge_values),
        "phase_full_frame_linear_pixel_similarity": phases,
    }
    acceptance = contract["acceptance"]
    gates = {
        "pooled_mean_full_frame_linear_pixel_similarity": pooled["full_frame_linear_pixel_similarity"]["mean"] >= acceptance["minimum_pooled_mean_full_frame_linear_pixel_similarity"],
        "pooled_p10_full_frame_linear_pixel_similarity": pooled["full_frame_linear_pixel_similarity"]["p10"] >= acceptance["minimum_pooled_p10_full_frame_linear_pixel_similarity"],
        "pooled_mean_motion_union_linear_pixel_similarity": pooled["motion_union_linear_pixel_similarity"]["mean"] >= acceptance["minimum_pooled_mean_motion_union_linear_pixel_similarity"],
        "each_phase_mean_full_frame_linear_pixel_similarity": all(value["mean"] >= acceptance["minimum_each_phase_mean_full_frame_linear_pixel_similarity"] for value in phases.values()),
        "pooled_mean_tolerant_edge_f1": pooled["tolerant_edge_f1"]["mean"] >= acceptance["minimum_pooled_mean_tolerant_edge_f1"],
        "each_development_episode_mean_full_frame_linear_pixel_similarity": all(row["full_frame_linear_pixel_similarity"]["mean"] >= acceptance["minimum_each_development_episode_mean_full_frame_linear_pixel_similarity"] for row in episode_summaries),
    }
    rows_artifact = {
        "schema_version": "sim2claw.observable_registration_development_shared_camera_baseline_rows.v1",
        "rows": all_rows,
    }
    rows_artifact["artifact_sha256"] = canonical_digest(rows_artifact)
    atomic_write_json(output_directory / "rows.json", rows_artifact)
    passed = all(gates.values())
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_development_shared_camera_baseline_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": "PASS_UNTUNED_DEVELOPMENT_TEMPORAL_PIXEL_TARGET" if passed else "TERMINAL_UNTUNED_DEVELOPMENT_BASELINE_BELOW_TARGET",
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "renderer": contract["renderer"],
        "timeline": contract["timeline"],
        "episode_summaries": episode_summaries,
        "pooled": pooled,
        "gates": gates,
        "rows": {
            "path": str((output_directory / "rows.json").relative_to(REPO_ROOT)),
            "sha256": sha256_file(output_directory / "rows.json"),
            "artifact_sha256": rows_artifact["artifact_sha256"],
            "row_count": len(all_rows),
        },
        "candidate_videos": candidate_videos,
        "execution": {
            "development_episode_reads": 4,
            "development_physical_video_decodes": 4,
            "physical_frames_compared": len(all_rows),
            "analytic_frames_rendered": len(all_rows),
            "candidate_videos": 4,
            "validation_reads": 0,
            "evaluator_heldout_reads": 0,
            "simulator_replays": 0,
            "parameter_fits": 0,
            "hardware_actions": 0,
            "paid_compute": False,
            "prohibited_candidate_inputs_read": [],
        },
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": "FREEZE_BOUNDED_SHARED_CAMERA_APPEARANCE_FAMILY_ON_DEVELOPMENT" if not passed else "VERIFY_UNTOUCHED_VECTOR_ON_VALIDATION_WITHOUT_REFIT",
        "next_transition": "freeze_or73_bounded_shared_camera_appearance_family" if not passed else "freeze_validation_reject_only_untuned_vector",
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

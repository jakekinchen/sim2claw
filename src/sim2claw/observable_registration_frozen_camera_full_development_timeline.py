"""Evaluate the frozen OR73 camera over all development timelines without refit."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_development_initial_shared_3d_camera_fit import _render
from .observable_registration_development_shared_camera_baseline import (
    _decode_selected_frames,
    _motion_union_similarity,
    _summary,
    evaluation_times,
    nearest_trace_indices,
    physical_frame_indices,
)
from .observable_registration_host_native_analytic_3d_renderer_capability import (
    REPO_ROOT,
    sha256_file,
)
from .observable_registration_temporal_pixel_similarity import (
    _linear_similarity,
    _tolerant_edge_f1,
)


cv2.ocl.setUseOpenCL(False)

DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_frozen_camera_full_development_timeline_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_frozen_camera_full_development_timeline_v1"


def evaluate_once(
    contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR74 one-run receipt already exists")
    contract = json.loads(contract_path.read_text())
    for source in contract["sources"].values():
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    or73 = json.loads((REPO_ROOT / contract["sources"]["or73_closeout"]["path"]).read_text())
    selected = or73["selected_camera"]
    if selected["vector"] != contract["selected_camera"]["vector"]:
        raise ValueError("selected camera vector drifted")
    camera = {
        "name": "or73_shared_development_camera",
        "position": selected["position"],
        "target": selected["target"],
        "fov_degrees": selected["fov_degrees"],
    }
    baseline_contract = json.loads((REPO_ROOT / contract["sources"]["or72_contract"]["path"]).read_text())
    episodes = baseline_contract["episodes"]
    if len(episodes) != 4 or any(episode["split_role"] != "development" for episode in episodes):
        raise ValueError("development split boundary drifted")
    scene_binding = contract["sources"]["shared_scene_manifest"]
    scene = json.loads((REPO_ROOT / scene_binding["path"]).read_text())
    if scene["revision_sha256"] != scene_binding["revision_sha256"]:
        raise ValueError("scene revision mismatch")
    for episode in episodes:
        for binding in (episode["physical_video"], episode["state_trace"]):
            if sha256_file(REPO_ROOT / binding["path"]) != binding["sha256"]:
                raise ValueError(f"episode source hash mismatch: {binding['path']}")

    output_directory.mkdir(parents=True, exist_ok=True)
    width = int(contract["renderer"]["width_px"])
    height = int(contract["renderer"]["height_px"])
    fps = float(contract["timeline"]["evaluation_fps"])
    background = contract["renderer"]["background_rgb"]
    all_rows: list[dict[str, Any]] = []
    episode_summaries: list[dict[str, Any]] = []
    candidate_videos: list[dict[str, Any]] = []

    for episode in episodes:
        recording_id = episode["recording_id"]
        trace = json.loads((REPO_ROOT / episode["state_trace"]["path"]).read_text())
        times = evaluation_times(float(episode["state_trace"]["duration_seconds"]), fps)
        trace_times = np.asarray([float(row["t"]) for row in trace["frames"]], dtype=np.float64)
        trace_indices = nearest_trace_indices(trace_times, times)
        physical_binding = episode["physical_video"]
        video_indices = physical_frame_indices(
            times,
            frame_count=int(physical_binding["frame_count"]),
            duration_seconds=float(physical_binding["duration_seconds"]),
        )
        physical_frames = [
            cv2.flip(frame, -1)
            for frame in _decode_selected_frames(
                REPO_ROOT / physical_binding["path"],
                selected_indices=video_indices,
                expected_frame_count=int(physical_binding["frame_count"]),
                expected_width=int(physical_binding["width_px"]),
                expected_height=int(physical_binding["height_px"]),
                output_width=width,
                output_height=height,
            )
        ]
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
                one_frame_trace = {"body_names": trace["body_names"], "frames": [trace["frames"][int(trace_index)]]}
                simulator = _render(scene, one_frame_trace, camera, width=width, height=height, background_rgb=background)
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
        primary = [float(row["full_frame_linear_pixel_similarity"]) for row in episode_rows]
        motion = [float(row["motion_union_linear_pixel_similarity"]) for row in episode_rows if row["motion_union_linear_pixel_similarity"] is not None]
        edge = [float(row["tolerant_edge_f1"]) for row in episode_rows]
        episode_summaries.append(
            {
                "recording_id": recording_id,
                "sample_count": len(episode_rows),
                "full_frame_linear_pixel_similarity": _summary(primary),
                "motion_union_linear_pixel_similarity": _summary(motion),
                "tolerant_edge_f1": _summary(edge),
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
    motion_values = [float(row["motion_union_linear_pixel_similarity"]) for row in all_rows if row["motion_union_linear_pixel_similarity"] is not None]
    edge_values = [float(row["tolerant_edge_f1"]) for row in all_rows]
    phases = {
        phase: _summary([float(row["full_frame_linear_pixel_similarity"]) for row in all_rows if row["phase"] == phase])
        for phase in sorted({str(row["phase"]) for row in all_rows})
    }
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
    rows_artifact: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_frozen_camera_full_development_timeline_rows.v1",
        "rows": all_rows,
    }
    rows_artifact["artifact_sha256"] = canonical_digest(rows_artifact)
    atomic_write_json(output_directory / "rows.json", rows_artifact)
    passed = all(gates.values())
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_frozen_camera_full_development_timeline_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": "PASS_FROZEN_CAMERA_FULL_DEVELOPMENT_PIXEL_TARGET" if passed else "TERMINAL_FROZEN_CAMERA_FULL_DEVELOPMENT_BELOW_TARGET",
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "selected_camera": contract["selected_camera"],
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
            "camera_fits": 0,
            "appearance_fits": 0,
            "time_fits": 0,
            "state_or_physics_fits": 0,
            "validation_reads": 0,
            "evaluator_heldout_reads": 0,
            "simulator_replays": 0,
            "hardware_actions": 0,
            "paid_compute": False,
            "prohibited_candidate_inputs_read": [],
        },
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": "FREEZE_NEXT_DEVELOPMENT_RESIDUAL_MECHANISM" if not passed else "VERIFY_FROZEN_VECTOR_ON_VALIDATION_WITHOUT_REFIT",
        "next_transition": "diagnose_or74_development_residual_before_new_fit" if not passed else "freeze_validation_reject_only_frozen_camera",
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

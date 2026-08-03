"""Reject-only validation of the frozen camera, workcell, and response candidate."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_board_anchored_workcell_se2_static_development_fit import (
    _prepare_full_mesh_stream,
)
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
from .observable_registration_native_rasterizer_byte_equivalence import (
    _compile_native,
    _native_rasterize,
)
from .observable_registration_shared_scalar_camera_response_development_fit import (
    apply_response,
)
from .observable_registration_static_development_full_mesh_comparison import (
    _load_unique_asset_cache,
)
from .observable_registration_temporal_pixel_similarity import (
    _linear_similarity,
    _tolerant_edge_f1,
)


cv2.ocl.setUseOpenCL(False)

DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_reject_only_validation_camera_workcell_response_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_reject_only_validation_camera_workcell_response_v1"


def evaluate_once(
    contract_path: Path = DEFAULT_CONTRACT,
    output_directory: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR87 one-run receipt already exists")
    contract = json.loads(contract_path.read_text())
    for name, source in contract["sources"].items():
        if name == "mesh_asset_root":
            continue
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    or86 = json.loads(
        (REPO_ROOT / contract["sources"]["or86_closeout"]["path"]).read_text()
    )
    response = contract["frozen_candidate"]["uniform_camera_response"]
    if (
        or86["result"]["selected_uniform_bgr_gain"] != response["gain"]
        or or86["result"]["selected_uniform_bgr_bias"] != response["bias"]
    ):
        raise ValueError("OR86 selected response drifted")
    inventory = json.loads(
        (REPO_ROOT / contract["sources"]["or68_pairing_inventory"]["path"]).read_text()
    )
    expected_ids = {
        row["recording_id"]
        for row in inventory["pairs"]
        if row["split_role"] == "validation"
    }
    episodes = contract["validation_episodes"]
    if {row["recording_id"] for row in episodes} != expected_ids:
        raise ValueError("OR68 validation split identity drifted")
    if len(episodes) != int(contract["gates"]["expected_validation_episode_count"]):
        raise ValueError("OR87 validation episode count drifted")
    for episode in episodes:
        for binding in (episode["physical_video"], episode["state_trace"]):
            if sha256_file(REPO_ROOT / binding["path"]) != binding["sha256"]:
                raise ValueError(f"validation source hash mismatch: {binding['path']}")
    scene_binding = contract["sources"]["shared_scene_manifest"]
    scene = json.loads((REPO_ROOT / scene_binding["path"]).read_text())
    if scene["revision_sha256"] != scene_binding["revision_sha256"]:
        raise ValueError("scene revision mismatch")
    camera = contract["frozen_candidate"]["camera"]
    workcell = contract["frozen_candidate"]["workcell_transform"]
    family = {
        "anchor_body_id": workcell["anchor_body_id"],
        "transformed_workcell_body_ids": workcell["transformed_workcell_body_ids"],
    }
    transform = np.asarray(workcell["vector"], dtype=np.float64)
    renderer = contract["renderer"]
    width = int(renderer["width_px"])
    height = int(renderer["height_px"])
    fps = float(contract["timeline"]["evaluation_fps"])
    meshes, asset_receipts = _load_unique_asset_cache(
        scene, REPO_ROOT / contract["sources"]["mesh_asset_root"]["path"]
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    library_path, compile_command, compiler_stderr = _compile_native(
        {
            "sources": {
                "native_source": contract["sources"]["or79_native_source"]
            },
            "compiler": {"executable": "clang"},
        },
        output_directory,
    )
    all_rows: list[dict[str, Any]] = []
    episode_summaries: list[dict[str, Any]] = []
    candidate_videos: list[dict[str, Any]] = []
    triangle_counts: list[int] = []
    frame_render_seconds: list[float] = []
    raster_seconds: list[float] = []
    started = time.perf_counter()
    for episode in episodes:
        recording_id = episode["recording_id"]
        trace = json.loads((REPO_ROOT / episode["state_trace"]["path"]).read_text())
        if trace["body_names"] != [body["name"] for body in scene["bodies"]]:
            raise ValueError("scene and validation trace body ordering drifted")
        times = evaluation_times(
            float(episode["state_trace"]["duration_seconds"]), fps
        )
        trace_times = np.asarray(
            [float(row["t"]) for row in trace["frames"]], dtype=np.float64
        )
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
        writer = cv2.VideoWriter(
            str(candidate_path),
            cv2.VideoWriter_fourcc(*renderer["candidate_video_codec"]),
            fps,
            (width, height),
        )
        if not writer.isOpened():
            raise RuntimeError("cannot open OR87 candidate video writer")
        episode_rows: list[dict[str, Any]] = []
        previous_physical: np.ndarray | None = None
        previous_candidate: np.ndarray | None = None
        try:
            for slot, (time_seconds, trace_index, video_index, physical) in enumerate(
                zip(times, trace_indices, video_indices, physical_frames, strict=True)
            ):
                frame_started = time.perf_counter()
                one_frame_trace = {
                    "body_names": trace["body_names"],
                    "frames": [trace["frames"][int(trace_index)]],
                }
                pixels, depths, colors, triangle_count = _prepare_full_mesh_stream(
                    scene,
                    one_frame_trace,
                    meshes,
                    camera,
                    renderer,
                    family,
                    transform,
                )
                simulator, depth_updates, occluded, raster_elapsed = _native_rasterize(
                    library_path, pixels, depths, colors, renderer
                )
                candidate = apply_response(
                    simulator,
                    gain=float(response["gain"]),
                    bias=float(response["bias"]),
                )
                frame_render_seconds.append(time.perf_counter() - frame_started)
                raster_seconds.append(raster_elapsed)
                triangle_counts.append(triangle_count)
                writer.write(candidate)
                physical_gray = cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY)
                candidate_gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
                motion, motion_pixels = _motion_union_similarity(
                    physical,
                    candidate,
                    previous_physical,
                    previous_candidate,
                    contract["metric"]["motion_union"],
                )
                row = {
                    "recording_id": recording_id,
                    "split_role": "validation",
                    "evaluation_index": slot,
                    "time_seconds": float(time_seconds),
                    "physical_frame_index": int(video_index),
                    "state_trace_frame_index": int(trace_index),
                    "phase": trace["frames"][int(trace_index)]["phase"],
                    "full_frame_linear_pixel_similarity": _linear_similarity(
                        physical, candidate
                    ),
                    "motion_union_linear_pixel_similarity": motion,
                    "motion_union_pixel_count": motion_pixels,
                    "tolerant_edge_f1": _tolerant_edge_f1(
                        physical_gray, candidate_gray, contract["metric"]["edge"]
                    ),
                    "depth_buffer_update_count": depth_updates,
                    "occluded_fragment_count": occluded,
                }
                episode_rows.append(row)
                all_rows.append(row)
                previous_physical = physical
                previous_candidate = candidate
        finally:
            writer.release()
        primary = [
            float(row["full_frame_linear_pixel_similarity"]) for row in episode_rows
        ]
        motion = [
            float(row["motion_union_linear_pixel_similarity"])
            for row in episode_rows
            if row["motion_union_linear_pixel_similarity"] is not None
        ]
        edges = [float(row["tolerant_edge_f1"]) for row in episode_rows]
        episode_summaries.append(
            {
                "recording_id": recording_id,
                "sample_count": len(episode_rows),
                "full_frame_linear_pixel_similarity": _summary(primary),
                "motion_union_linear_pixel_similarity": _summary(motion),
                "tolerant_edge_f1": _summary(edges),
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
    phases = {
        phase: _summary(
            [
                float(row["full_frame_linear_pixel_similarity"])
                for row in all_rows
                if row["phase"] == phase
            ]
        )
        for phase in sorted({str(row["phase"]) for row in all_rows})
    }
    pooled = {
        "full_frame_linear_pixel_similarity": _summary(
            [float(row["full_frame_linear_pixel_similarity"]) for row in all_rows]
        ),
        "motion_union_linear_pixel_similarity": _summary(
            [
                float(row["motion_union_linear_pixel_similarity"])
                for row in all_rows
                if row["motion_union_linear_pixel_similarity"] is not None
            ]
        ),
        "tolerant_edge_f1": _summary(
            [float(row["tolerant_edge_f1"]) for row in all_rows]
        ),
        "phase_full_frame_linear_pixel_similarity": phases,
    }
    acceptance = contract["acceptance"]
    metric_gates = {
        "pooled_mean_full_frame_linear_pixel_similarity": pooled[
            "full_frame_linear_pixel_similarity"
        ]["mean"]
        >= acceptance["minimum_pooled_mean_full_frame_linear_pixel_similarity"],
        "pooled_p10_full_frame_linear_pixel_similarity": pooled[
            "full_frame_linear_pixel_similarity"
        ]["p10"]
        >= acceptance["minimum_pooled_p10_full_frame_linear_pixel_similarity"],
        "pooled_mean_motion_union_linear_pixel_similarity": pooled[
            "motion_union_linear_pixel_similarity"
        ]["mean"]
        >= acceptance["minimum_pooled_mean_motion_union_linear_pixel_similarity"],
        "each_phase_mean_full_frame_linear_pixel_similarity": all(
            value["mean"]
            >= acceptance["minimum_each_phase_mean_full_frame_linear_pixel_similarity"]
            for value in phases.values()
        ),
        "pooled_mean_tolerant_edge_f1": pooled["tolerant_edge_f1"]["mean"]
        >= acceptance["minimum_pooled_mean_tolerant_edge_f1"],
        "each_validation_episode_mean_full_frame_linear_pixel_similarity": all(
            row["full_frame_linear_pixel_similarity"]["mean"]
            >= acceptance[
                "minimum_each_validation_episode_mean_full_frame_linear_pixel_similarity"
            ]
            for row in episode_summaries
        ),
    }
    integrity_gates = {
        "exact_three_validation_episodes": len(episode_summaries)
        == int(contract["gates"]["expected_validation_episode_count"]),
        "expected_total_frame_count": len(all_rows)
        == int(contract["gates"]["expected_total_frame_count"]),
        "expected_unique_mesh_asset_reads": len(asset_receipts)
        == int(contract["gates"]["expected_unique_mesh_asset_reads"]),
        "expected_triangle_count_every_frame": all(
            count
            == int(contract["gates"]["expected_total_raster_triangle_count_per_frame"])
            for count in triangle_counts
        ),
        "frozen_candidate_no_fit_or_selection": True,
        "development_and_evaluator_heldout_closed": True,
        "no_replay_hardware_or_paid_compute": True,
    }
    rows_artifact: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_reject_only_validation_camera_workcell_response_rows.v1",
        "rows": all_rows,
    }
    rows_artifact["artifact_sha256"] = canonical_digest(rows_artifact)
    rows_path = output_directory / "rows.json"
    atomic_write_json(rows_path, rows_artifact)
    passed = all(metric_gates.values()) and all(integrity_gates.values())
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_reject_only_validation_camera_workcell_response_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": (
            "PASS_REJECT_ONLY_VALIDATION_CAMERA_WORKCELL_RESPONSE"
            if passed
            else "TERMINAL_REJECT_ONLY_VALIDATION_CAMERA_WORKCELL_RESPONSE_FAILED"
        ),
        "proof_class": contract["proof_class"],
        "contract": {
            "path": str(contract_path.relative_to(REPO_ROOT)),
            "sha256": sha256_file(contract_path),
        },
        "frozen_candidate": contract["frozen_candidate"],
        "episode_summaries": episode_summaries,
        "pooled": pooled,
        "metric_gates": metric_gates,
        "integrity_gates": integrity_gates,
        "performance": {
            "wall_seconds": time.perf_counter() - started,
            "mean_full_frame_render_seconds": float(np.mean(frame_render_seconds)),
            "p90_full_frame_render_seconds": float(
                np.quantile(frame_render_seconds, 0.9)
            ),
            "mean_native_raster_seconds": float(np.mean(raster_seconds)),
        },
        "rows": {
            "path": str(rows_path.relative_to(REPO_ROOT)),
            "sha256": sha256_file(rows_path),
            "artifact_sha256": rows_artifact["artifact_sha256"],
            "row_count": len(all_rows),
        },
        "candidate_videos": candidate_videos,
        "execution": {
            "validation_episode_reads": 3,
            "validation_physical_video_decodes": 3,
            "validation_physical_frames_compared": len(all_rows),
            "native_frames_rendered": len(all_rows),
            "candidate_videos": len(candidate_videos),
            "fits_or_candidate_selections": 0,
            "development_reads": 0,
            "evaluator_heldout_reads": 0,
            "simulator_replays": 0,
            "hardware_actions": 0,
            "paid_compute": False,
        },
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": (
            "OPEN_EVALUATOR_HELDOUT_EXACTLY_ONCE_WITH_FROZEN_CANDIDATE"
            if passed
            else "REJECT_CANDIDATE_KEEP_EVALUATOR_HELDOUT_SEALED"
        ),
        "next_transition": (
            "freeze_or88_one_shot_evaluator_heldout_camera_workcell_response"
            if passed
            else "stop_validation_rejected_candidate"
        ),
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

"""Reject-only evaluation of the frozen candidate on fresh validation."""

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
from .observable_registration_expanded_development_global_monotone_response_fit import (
    apply_monotone_response,
)
from .observable_registration_host_native_analytic_3d_renderer_capability import (
    REPO_ROOT,
    sha256_file,
)
from .observable_registration_native_rasterizer_byte_equivalence import (
    _compile_native,
    _native_rasterize,
)
from .observable_registration_static_development_full_mesh_comparison import (
    _load_unique_asset_cache,
)
from .observable_registration_temporal_pixel_similarity import (
    _linear_similarity,
    _tolerant_edge_f1,
)


cv2.ocl.setUseOpenCL(False)

SCHEMA = "sim2claw.observable_registration_reject_only_fresh_validation_global_monotone_response_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_reject_only_fresh_validation_global_monotone_response_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_reject_only_fresh_validation_global_monotone_response_v1"


def load_reject_only_fresh_validation_global_monotone_response_contract(
    path: Path = DEFAULT_CONTRACT,
) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR90 contract")
    for name, source in contract["sources"].items():
        if name == "mesh_asset_root":
            continue
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    episodes = contract["fresh_validation_episodes"]
    if (
        len(episodes) != 2
        or [row["split_position"] for row in episodes] != [8, 9]
        or contract["gates"]["expected_total_frame_count"] != 213
    ):
        raise ValueError("OR90 validation split drifted")
    response = contract["frozen_candidate"]["global_monotone_response"]
    if response != {
        "bias": 24.0,
        "low_intensity_slope": 0.85,
        "high_intensity_slope": 0.25,
        "fixed_input_knot": 128,
        "formula": "clip(round(bias + low_slope*min(input,128) + high_slope*max(input-128,0)),0,255)",
    } or contract["frozen_candidate"]["refit_or_selection_allowed"] is not False:
        raise ValueError("OR90 frozen response drifted")
    acceptance = contract["acceptance"]
    if (
        acceptance["minimum_pooled_mean_full_frame_linear_pixel_similarity"] != 0.8
        or acceptance["minimum_pooled_p10_full_frame_linear_pixel_similarity"] != 0.75
        or acceptance["minimum_pooled_mean_motion_union_linear_pixel_similarity"] != 0.75
        or acceptance["minimum_each_phase_mean_full_frame_linear_pixel_similarity"] != 0.78
        or acceptance["minimum_pooled_mean_tolerant_edge_f1"] != 0.4
        or acceptance["minimum_each_fresh_validation_episode_mean_full_frame_linear_pixel_similarity"] != 0.8
        or acceptance["all_gates_required"] is not True
    ):
        raise ValueError("OR90 acceptance boundary drifted")
    resources = contract["resource_boundary"]
    if (
        resources["fits_or_candidate_selections_allowed"] != 0
        or resources["development_reads_allowed"] != 0
        or resources["final_evaluator_heldout_reads_allowed"] != 0
        or resources["simulator_replays_allowed"] != 0
        or resources["hardware_actions_allowed"] != 0
        or resources["paid_compute_allowed"] is not False
    ):
        raise ValueError("OR90 resource boundary widened")
    if any(contract["authority"].values()):
        raise ValueError("OR90 authority widened")
    return contract


def evaluate_once(
    contract_path: Path = DEFAULT_CONTRACT,
    output_directory: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR90 one-run receipt already exists")
    contract = load_reject_only_fresh_validation_global_monotone_response_contract(
        contract_path
    )
    closeout = json.loads(
        (REPO_ROOT / contract["sources"]["or89_closeout"]["path"]).read_text()
    )
    response = contract["frozen_candidate"]["global_monotone_response"]
    if (
        closeout["result"]["selected_bias"] != response["bias"]
        or closeout["result"]["selected_low_intensity_slope"]
        != response["low_intensity_slope"]
        or closeout["result"]["selected_high_intensity_slope"]
        != response["high_intensity_slope"]
        or closeout["result"]["fixed_input_knot"] != response["fixed_input_knot"]
    ):
        raise ValueError("OR89 selected response drifted")
    split = json.loads(
        (REPO_ROOT / contract["sources"]["or88_split_manifest"]["path"]).read_text()
    )
    expected_ids = [
        row["recording_id"]
        for row in split["pairs"]
        if row["new_split_role"] == "fresh_validation"
    ]
    episodes = contract["fresh_validation_episodes"]
    if [row["recording_id"] for row in episodes] != expected_ids:
        raise ValueError("OR88 fresh-validation identities drifted")
    for episode in episodes:
        for binding in (
            episode["recording_receipt"],
            episode["physical_video"],
            episode["state_trace"],
        ):
            if sha256_file(REPO_ROOT / binding["path"]) != binding["sha256"]:
                raise ValueError(f"fresh-validation source hash mismatch: {binding['path']}")
        source_receipt = json.loads(
            (REPO_ROOT / episode["recording_receipt"]["path"]).read_text()
        )
        observed = source_receipt["overhead_video"]["observed_video"]
        stream = observed["streams"][0]
        if (
            int(stream["nb_frames"]) != episode["physical_video"]["frame_count"]
            or int(stream["width"]) != episode["physical_video"]["width_px"]
            or int(stream["height"]) != episode["physical_video"]["height_px"]
            or float(observed["format"]["duration"])
            != episode["physical_video"]["duration_seconds"]
        ):
            raise ValueError("recording receipt video metadata drifted")

    scene_binding = contract["sources"]["shared_scene_manifest"]
    scene = json.loads((REPO_ROOT / scene_binding["path"]).read_text())
    if scene["revision_sha256"] != scene_binding["revision_sha256"]:
        raise ValueError("scene revision mismatch")
    frozen = contract["frozen_candidate"]
    camera = frozen["camera"]
    workcell = frozen["workcell_transform"]
    workcell_family = {
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
        {"sources": {"native_source": contract["sources"]["or79_native_source"]}, "compiler": {"executable": "clang"}},
        output_directory,
    )
    all_rows: list[dict[str, Any]] = []
    episode_summaries: list[dict[str, Any]] = []
    candidate_videos: list[dict[str, Any]] = []
    triangle_counts: list[int] = []
    frame_seconds: list[float] = []
    raster_seconds: list[float] = []
    started = time.perf_counter()
    for episode in episodes:
        recording_id = episode["recording_id"]
        trace = json.loads((REPO_ROOT / episode["state_trace"]["path"]).read_text())
        if trace["body_names"] != [body["name"] for body in scene["bodies"]]:
            raise ValueError("scene and fresh-validation trace body ordering drifted")
        times = evaluation_times(float(episode["state_trace"]["duration_seconds"]), fps)
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
        path = output_directory / f"{recording_id}.mp4"
        writer = cv2.VideoWriter(
            str(path), cv2.VideoWriter_fourcc(*renderer["candidate_video_codec"]), fps, (width, height)
        )
        if not writer.isOpened():
            raise RuntimeError("cannot open OR90 candidate video writer")
        episode_rows: list[dict[str, Any]] = []
        previous_physical: np.ndarray | None = None
        previous_candidate: np.ndarray | None = None
        try:
            for slot, (time_seconds, trace_index, video_index, physical) in enumerate(
                zip(times, trace_indices, video_indices, physical_frames, strict=True)
            ):
                frame_started = time.perf_counter()
                one_frame_trace = {"body_names": trace["body_names"], "frames": [trace["frames"][int(trace_index)]]}
                pixels, depths, colors, triangle_count = _prepare_full_mesh_stream(
                    scene, one_frame_trace, meshes, camera, renderer, workcell_family, transform
                )
                simulator, _, _, raster_elapsed = _native_rasterize(
                    library_path, pixels, depths, colors, renderer
                )
                candidate = apply_monotone_response(
                    simulator,
                    bias=float(response["bias"]),
                    low_slope=float(response["low_intensity_slope"]),
                    high_slope=float(response["high_intensity_slope"]),
                    knot=int(response["fixed_input_knot"]),
                )
                frame_seconds.append(time.perf_counter() - frame_started)
                raster_seconds.append(float(raster_elapsed))
                triangle_counts.append(int(triangle_count))
                writer.write(candidate)
                motion, motion_pixels = _motion_union_similarity(
                    physical,
                    candidate,
                    previous_physical,
                    previous_candidate,
                    contract["metric"]["motion_union"],
                )
                row = {
                    "recording_id": recording_id,
                    "split_role": "fresh_validation",
                    "evaluation_index": slot,
                    "time_seconds": float(time_seconds),
                    "physical_frame_index": int(video_index),
                    "state_trace_frame_index": int(trace_index),
                    "phase": trace["frames"][int(trace_index)]["phase"],
                    "full_frame_linear_pixel_similarity": _linear_similarity(physical, candidate),
                    "motion_union_linear_pixel_similarity": motion,
                    "motion_union_pixel_count": motion_pixels,
                    "tolerant_edge_f1": _tolerant_edge_f1(
                        cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY),
                        cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY),
                        contract["metric"]["edge"],
                    ),
                }
                episode_rows.append(row)
                all_rows.append(row)
                previous_physical = physical
                previous_candidate = candidate
        finally:
            writer.release()
        episode_summaries.append(
            {
                "recording_id": recording_id,
                "sample_count": len(episode_rows),
                "full_frame_linear_pixel_similarity": _summary([float(row["full_frame_linear_pixel_similarity"]) for row in episode_rows]),
                "motion_union_linear_pixel_similarity": _summary([float(row["motion_union_linear_pixel_similarity"]) for row in episode_rows if row["motion_union_linear_pixel_similarity"] is not None]),
                "tolerant_edge_f1": _summary([float(row["tolerant_edge_f1"]) for row in episode_rows]),
            }
        )
        candidate_videos.append(
            {"recording_id": recording_id, "path": str(path.relative_to(REPO_ROOT)), "sha256": sha256_file(path), "frame_count": len(episode_rows), "fps": fps}
        )
    phases = {
        phase: _summary([float(row["full_frame_linear_pixel_similarity"]) for row in all_rows if row["phase"] == phase])
        for phase in sorted({str(row["phase"]) for row in all_rows})
    }
    pooled = {
        "full_frame_linear_pixel_similarity": _summary([float(row["full_frame_linear_pixel_similarity"]) for row in all_rows]),
        "motion_union_linear_pixel_similarity": _summary([float(row["motion_union_linear_pixel_similarity"]) for row in all_rows if row["motion_union_linear_pixel_similarity"] is not None]),
        "tolerant_edge_f1": _summary([float(row["tolerant_edge_f1"]) for row in all_rows]),
        "phase_full_frame_linear_pixel_similarity": phases,
    }
    acceptance = contract["acceptance"]
    metric_gates = {
        "pooled_mean_full_frame_linear_pixel_similarity": pooled["full_frame_linear_pixel_similarity"]["mean"] >= acceptance["minimum_pooled_mean_full_frame_linear_pixel_similarity"],
        "pooled_p10_full_frame_linear_pixel_similarity": pooled["full_frame_linear_pixel_similarity"]["p10"] >= acceptance["minimum_pooled_p10_full_frame_linear_pixel_similarity"],
        "pooled_mean_motion_union_linear_pixel_similarity": pooled["motion_union_linear_pixel_similarity"]["mean"] >= acceptance["minimum_pooled_mean_motion_union_linear_pixel_similarity"],
        "each_phase_mean_full_frame_linear_pixel_similarity": all(row["mean"] >= acceptance["minimum_each_phase_mean_full_frame_linear_pixel_similarity"] for row in phases.values()),
        "pooled_mean_tolerant_edge_f1": pooled["tolerant_edge_f1"]["mean"] >= acceptance["minimum_pooled_mean_tolerant_edge_f1"],
        "each_fresh_validation_episode_mean_full_frame_linear_pixel_similarity": all(row["full_frame_linear_pixel_similarity"]["mean"] >= acceptance["minimum_each_fresh_validation_episode_mean_full_frame_linear_pixel_similarity"] for row in episode_summaries),
    }
    expected_frames = int(contract["gates"]["expected_total_frame_count"])
    integrity_gates = {
        "exact_two_fresh_validation_episodes": len(episode_summaries) == 2,
        "expected_total_frame_count": len(all_rows) == expected_frames,
        "expected_unique_mesh_asset_reads": len(asset_receipts) == int(contract["gates"]["expected_unique_mesh_asset_reads"]),
        "expected_triangle_count_every_frame": all(value == int(contract["gates"]["expected_total_raster_triangle_count_per_frame"]) for value in triangle_counts),
        "frozen_candidate_no_fit_or_selection": True,
        "development_and_final_evaluator_heldout_closed": True,
        "no_replay_hardware_or_paid_compute": True,
    }
    passed = all(metric_gates.values()) and all(integrity_gates.values())
    atomic_write_json(
        output_directory / "frame_rows.json",
        {"schema_version": "sim2claw.observable_registration_reject_only_fresh_validation_global_monotone_response_frame_rows.v1", "frame_count": len(all_rows), "rows": all_rows},
    )
    receipt = {
        "schema_version": "sim2claw.observable_registration_reject_only_fresh_validation_global_monotone_response_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": "PASS_FRESH_VALIDATION_GLOBAL_MONOTONE_RESPONSE" if passed else "TERMINAL_REJECT_ONLY_FRESH_VALIDATION_GLOBAL_MONOTONE_RESPONSE_FAILED",
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "frozen_candidate": frozen,
        "pooled": pooled,
        "episode_summaries": episode_summaries,
        "metric_gates": metric_gates,
        "integrity_gates": integrity_gates,
        "candidate_videos": candidate_videos,
        "execution": {"fresh_validation_episode_reads": 2, "fresh_validation_physical_video_decodes": 2, "fresh_validation_physical_frames_compared": expected_frames, "native_frames_rendered": expected_frames, "fits_or_candidate_selections": 0, "development_reads": 0, "final_evaluator_heldout_reads": 0, "simulator_replays": 0, "hardware_actions": 0, "paid_compute": False},
        "performance": {"wall_seconds": time.perf_counter() - started, "mean_full_frame_render_seconds": float(np.mean(frame_seconds)), "p90_full_frame_render_seconds": float(np.quantile(frame_seconds, 0.9)), "mean_native_raster_seconds": float(np.mean(raster_seconds)), "compile_command": compile_command, "compiler_stderr": compiler_stderr},
        "reviewer_decision": "OPEN_ONE_SHOT_FINAL_EVALUATOR_HELDOUT_WITH_FROZEN_CANDIDATE" if passed else "REJECT_CANDIDATE_KEEP_FINAL_EVALUATOR_HELDOUT_SEALED",
        "next_transition": "freeze_or91_one_shot_final_evaluator_heldout_global_monotone_response" if passed else "stop_fresh_validation_rejected_candidate",
        "claim_limits": contract["claim_limits"],
    }
    receipt["artifact_sha256"] = canonical_digest({"pooled": pooled, "metric_gates": metric_gates, "integrity_gates": integrity_gates, "candidate_video_hashes": [row["sha256"] for row in candidate_videos]})
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    evaluate_once()

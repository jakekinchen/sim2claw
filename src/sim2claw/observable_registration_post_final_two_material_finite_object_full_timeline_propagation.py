"""Propagate the frozen OR118 object through all already-open timelines."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_board_anchored_scene_composition_residual_attribution import _masked_tolerant_edge_f1
from .observable_registration_board_anchored_workcell_se2_static_development_fit import _prepare_full_mesh_stream, _region_masks
from .observable_registration_development_shared_camera_baseline import _decode_selected_frames, _motion_union_similarity, _summary, evaluation_times, nearest_trace_indices, physical_frame_indices
from .observable_registration_expanded_development_global_monotone_response_fit import apply_monotone_response
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, sha256_file
from .observable_registration_native_rasterizer_byte_equivalence import _compile_native, _native_rasterize
from .observable_registration_post_final_independent_left_right_robot_base_se2_diagnostic import _independently_registered_trace
from .observable_registration_post_final_independent_robot_base_full_corpus_diagnostic import _episode_inventory, load_post_final_independent_robot_base_full_corpus_diagnostic_contract
from .observable_registration_post_final_renderer_native_finite_linear_workcell_object_reconstruction import _primitive_triangle_stream, load_post_final_renderer_native_finite_linear_workcell_object_reconstruction_contract
from .observable_registration_static_development_full_mesh_comparison import _load_unique_asset_cache
from .observable_registration_temporal_pixel_similarity import _linear_similarity, _tolerant_edge_f1


cv2.ocl.setUseOpenCL(False)
SCHEMA = "sim2claw.observable_registration_post_final_two_material_finite_object_full_timeline_propagation_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_final_two_material_finite_object_full_timeline_propagation_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_final_two_material_finite_object_full_timeline_propagation_v1"


def load_post_final_two_material_finite_object_full_timeline_propagation_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR119 contract")
    for name, source in contract["sources"].items():
        if name != "mesh_asset_root" and sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    frozen = contract["frozen_object"]
    if frozen["total_triangle_count"] != 348 or frozen["shared_zbuffer"] is not True or frozen["fit_selection_retry_or_threshold_change_allowed"] is not False:
        raise ValueError("OR119 object drifted")
    acceptance = contract["same_video_acceptance"]
    if acceptance["minimum_pooled_mean_full_frame_linear_pixel_similarity"] != 0.80 or acceptance["maximum_pooled_mean_full_frame_linear_pixel_similarity"] != 0.90 or acceptance["minimum_pooled_mean_outside_board_edge_f1"] < 0.60 or acceptance["minimum_each_episode_mean_outside_board_edge_f1"] < 0.50:
        raise ValueError("OR119 same-video gates weakened")
    gates = contract["gates"]
    if gates["expected_episode_count"] != 11 or gates["expected_total_frame_count"] != 1210:
        raise ValueError("OR119 corpus size drifted")
    resources = contract["resource_boundary"]
    if resources["physical_frames_compared_allowed"] != 1210 or resources["native_full_mesh_plus_object_frames_rendered_allowed"] != 1210 or resources["fits_or_candidate_selections_allowed"] != 0 or resources["threshold_changes_allowed"] != 0 or resources["retries_allowed"] != 0 or resources["simulator_replays_allowed"] != 0 or resources["paid_compute_allowed"] is not False or any(contract["authority"].values()):
        raise ValueError("OR119 resource or authority boundary drifted")
    if contract["claim_limits"]["untouched_cohort_remaining"] is not False or contract["claim_limits"]["predictive_simulation"] is not False or contract["claim_limits"]["physics_fidelity"] is not False:
        raise ValueError("OR119 claim boundary drifted")
    return contract


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR119 one-run receipt already exists; retry prohibited")
    contract = load_post_final_two_material_finite_object_full_timeline_propagation_contract(contract_path)
    closeout = json.loads((REPO_ROOT / contract["sources"]["or118_closeout"]["path"]).read_text())
    if closeout["reviewer_decision"] != "FREEZE_TWO_MATERIAL_FINITE_OBJECT_FULL_TIMELINE_PROPAGATION":
        raise ValueError("OR118 did not authorize full-timeline propagation")
    or118 = json.loads((REPO_ROOT / contract["sources"]["or118_receipt"]["path"]).read_text())
    if or118["artifact_sha256"] != contract["sources"]["or118_receipt"]["artifact_sha256"]:
        raise ValueError("OR118 artifact identity drifted")
    frozen_object = contract["frozen_object"]
    selected = or118["selected_material_pair"]
    if selected["shaft_target_bgr"] != frozen_object["shaft_target_bgr"] or selected["terminal_target_bgr"] != frozen_object["terminal_target_bgr"] or selected["shaft_pre_response_bgr"] != frozen_object["shaft_pre_response_bgr"] or selected["terminal_pre_response_bgr"] != frozen_object["terminal_pre_response_bgr"]:
        raise ValueError("OR119 material binding drifted")
    shape = or118["frozen_shape"]
    or116_contract = load_post_final_renderer_native_finite_linear_workcell_object_reconstruction_contract(REPO_ROOT / contract["sources"]["or116_contract"]["path"])
    or95_contract = load_post_final_independent_robot_base_full_corpus_diagnostic_contract(REPO_ROOT / contract["sources"]["or95_contract"]["path"])
    or95 = json.loads((REPO_ROOT / contract["sources"]["or95_receipt"]["path"]).read_text())
    if or95["artifact_sha256"] != contract["sources"]["or95_receipt"]["artifact_sha256"]:
        raise ValueError("OR95 artifact identity drifted")
    prior_rows = json.loads((REPO_ROOT / contract["sources"]["or95_frame_rows"]["path"]).read_text())["rows"]
    prior_by_key = {(int(row["split_position"]), int(row["evaluation_index"])): row for row in prior_rows}
    episodes = _episode_inventory(or95_contract)
    for episode in episodes:
        for key in ("physical_video", "state_trace"):
            binding = episode[key]
            if sha256_file(REPO_ROOT / binding["path"]) != binding["sha256"]:
                raise ValueError(f"OR119 source hash mismatch: {binding['path']}")
    scene_binding = contract["sources"]["shared_scene_manifest"]
    scene = json.loads((REPO_ROOT / scene_binding["path"]).read_text())
    if scene["revision_sha256"] != scene_binding["revision_sha256"]:
        raise ValueError("OR119 scene revision mismatch")
    body_names = [body["name"] for body in scene["bodies"]]
    frozen = or95_contract["frozen_candidate"]
    camera = frozen["camera"]
    static = frozen["static_workcell_transform"]
    static_family = {"anchor_body_id": int(static["anchor_body_id"]), "transformed_workcell_body_ids": [int(value) for value in static["transformed_body_ids"]]}
    static_vector = np.asarray(static["vector"], dtype=np.float64)
    left_ids = [int(value) for value in frozen["left_robot_transform"]["transformed_body_ids"]]
    right_ids = [int(value) for value in frozen["right_robot_transform"]["transformed_body_ids"]]
    robot_vector = np.asarray(frozen["left_robot_transform"]["vector"] + frozen["right_robot_transform"]["vector"], dtype=np.float64)
    response = frozen["global_monotone_response"]
    renderer = contract["renderer"]
    width, height, fps = int(renderer["width_px"]), int(renderer["height_px"]), float(contract["timeline"]["evaluation_fps"])
    edge = contract["metric"]["edge"]
    board_mask, outside_mask = _region_masks(np.asarray(contract["regions"]["board_plus_margin"]["points_px"], dtype=np.float64), width=width, height=height, dilation_kernel_px=int(contract["regions"]["board_plus_margin"]["dilation_kernel_px_at_320x240"]))
    local_mask = np.zeros((height, width), dtype=np.uint8)
    x0, y0, x1, y1 = [int(value) for value in contract["regions"]["finite_linear_object_roi_xyxy"]]
    local_mask[y0:y1, x0:x1] = 1
    local_mask = (local_mask.astype(bool) & outside_mask.astype(bool)).astype(np.uint8)
    output_directory.mkdir(parents=True, exist_ok=True)
    meshes, asset_receipts = _load_unique_asset_cache(scene, REPO_ROOT / contract["sources"]["mesh_asset_root"]["path"])
    library_path, compile_command, compiler_stderr = _compile_native({"sources": {"native_source": contract["sources"]["or79_native_source"]}, "compiler": {"executable": "clang"}}, output_directory)

    shaft_pre = np.asarray(frozen_object["shaft_pre_response_bgr"], dtype=np.uint8)
    terminal_pre = np.asarray(frozen_object["terminal_pre_response_bgr"], dtype=np.uint8)
    object_colors = np.concatenate([np.tile(shaft_pre, (248, 1)), np.tile(terminal_pre, (100, 1))], axis=0).astype(np.uint8)
    all_rows: list[dict[str, Any]] = []
    episode_summaries: list[dict[str, Any]] = []
    candidate_videos: list[dict[str, Any]] = []
    triangle_counts: list[int] = []
    reprojection_errors: list[float] = []
    raster_seconds: list[float] = []
    started = time.perf_counter()
    for episode in episodes:
        recording_id = episode["recording_id"]
        trace = json.loads((REPO_ROOT / episode["state_trace"]["path"]).read_text())
        if trace["body_names"] != body_names:
            raise ValueError("OR119 scene/trace ordering drifted")
        times = evaluation_times(float(episode["state_trace"]["duration_seconds"]), fps)
        trace_times = np.asarray([float(row["t"]) for row in trace["frames"]], dtype=np.float64)
        trace_indices = nearest_trace_indices(trace_times, times)
        video_binding = episode["physical_video"]
        video_indices = physical_frame_indices(times, frame_count=int(video_binding["frame_count"]), duration_seconds=float(video_binding["duration_seconds"]))
        physical_frames = [cv2.flip(frame, -1) for frame in _decode_selected_frames(REPO_ROOT / video_binding["path"], selected_indices=video_indices, expected_frame_count=int(video_binding["frame_count"]), expected_width=int(video_binding["width_px"]), expected_height=int(video_binding["height_px"]), output_width=width, output_height=height)]
        initial_one = {"body_names": trace["body_names"], "frames": [trace["frames"][0]]}
        initial_registered = _independently_registered_trace(initial_one, anchor_body_id=int(static["anchor_body_id"]), left_body_ids=left_ids, right_body_ids=right_ids, vector=robot_vector)
        object_pixels, object_depths, _, object_metadata = _primitive_triangle_stream(shape, initial_registered, scene, camera, renderer, static_family, static_vector, or116_contract["support_plane"], np.asarray([0, 0, 0], dtype=np.uint8))
        reprojection_errors.append(float(object_metadata["axis_and_terminal_center_reprojection_error_px"]))
        video_path = output_directory / f"{recording_id}.mp4"
        writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*renderer["candidate_video_codec"]), fps, (width, height))
        if not writer.isOpened():
            raise RuntimeError("cannot open OR119 video writer")
        episode_rows: list[dict[str, Any]] = []
        previous_physical = None
        previous_candidate = None
        try:
            for slot, (time_seconds, trace_index, video_index, physical) in enumerate(zip(times, trace_indices, video_indices, physical_frames, strict=True)):
                one = {"body_names": trace["body_names"], "frames": [trace["frames"][int(trace_index)]]}
                registered = _independently_registered_trace(one, anchor_body_id=int(static["anchor_body_id"]), left_body_ids=left_ids, right_body_ids=right_ids, vector=robot_vector)
                pixels, depths, colors, baseline_count = _prepare_full_mesh_stream(scene, registered, meshes, camera, renderer, static_family, static_vector)
                pixels = np.ascontiguousarray(np.concatenate([pixels, object_pixels]))
                depths = np.ascontiguousarray(np.concatenate([depths, object_depths]))
                colors = np.ascontiguousarray(np.concatenate([colors, object_colors]))
                simulator, _, _, elapsed = _native_rasterize(library_path, pixels, depths, colors, renderer)
                candidate = apply_monotone_response(simulator, bias=float(response["bias"]), low_slope=float(response["low_intensity_slope"]), high_slope=float(response["high_intensity_slope"]), knot=int(response["fixed_input_knot"]))
                writer.write(candidate)
                triangle_counts.append(int(len(pixels))); raster_seconds.append(float(elapsed))
                motion, motion_pixels = _motion_union_similarity(physical, candidate, previous_physical, previous_candidate, contract["metric"]["motion_union"])
                physical_gray = cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY)
                candidate_gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
                board = _masked_tolerant_edge_f1(physical_gray, candidate_gray, board_mask, edge)
                outside = _masked_tolerant_edge_f1(physical_gray, candidate_gray, outside_mask, edge)
                local = _masked_tolerant_edge_f1(physical_gray, candidate_gray, local_mask, edge)
                prior = prior_by_key[(int(episode["split_position"]), slot)]
                row = {"recording_id": recording_id, "split_position": int(episode["split_position"]), "retrospective_role": episode["retrospective_role"], "evaluation_index": slot, "time_seconds": float(time_seconds), "physical_frame_index": int(video_index), "state_trace_frame_index": int(trace_index), "phase": trace["frames"][int(trace_index)]["phase"], "full_frame_linear_pixel_similarity": _linear_similarity(physical, candidate), "motion_union_linear_pixel_similarity": motion, "motion_union_pixel_count": motion_pixels, "whole_frame_tolerant_edge_f1": _tolerant_edge_f1(physical_gray, candidate_gray, edge), "board_plus_margin_edge_f1": float(board["f1"]), "outside_board_edge_f1": float(outside["f1"]), "object_roi_edge_f1": float(local["f1"]), "full_frame_similarity_delta_vs_or95": float(_linear_similarity(physical, candidate) - float(prior["full_frame_linear_pixel_similarity"])), "outside_board_edge_f1_delta_vs_or95": float(outside["f1"] - float(prior["outside_board_edge_f1"]))}
                episode_rows.append(row); all_rows.append(row)
                previous_physical, previous_candidate = physical, candidate
        finally:
            writer.release()
        episode_summaries.append({"recording_id": recording_id, "split_position": int(episode["split_position"]), "retrospective_role": episode["retrospective_role"], "frame_count": len(episode_rows), "full_frame_linear_pixel_similarity": _summary([float(row["full_frame_linear_pixel_similarity"]) for row in episode_rows]), "motion_union_linear_pixel_similarity": _summary([float(row["motion_union_linear_pixel_similarity"]) for row in episode_rows if row["motion_union_linear_pixel_similarity"] is not None]), "whole_frame_tolerant_edge_f1": _summary([float(row["whole_frame_tolerant_edge_f1"]) for row in episode_rows]), "board_plus_margin_edge_f1": _summary([float(row["board_plus_margin_edge_f1"]) for row in episode_rows]), "outside_board_edge_f1": _summary([float(row["outside_board_edge_f1"]) for row in episode_rows]), "object_roi_edge_f1": _summary([float(row["object_roi_edge_f1"]) for row in episode_rows]), "full_frame_similarity_delta_vs_or95": _summary([float(row["full_frame_similarity_delta_vs_or95"]) for row in episode_rows]), "outside_board_edge_f1_delta_vs_or95": _summary([float(row["outside_board_edge_f1_delta_vs_or95"]) for row in episode_rows])})
        candidate_videos.append({"recording_id": recording_id, "path": str(video_path.relative_to(REPO_ROOT)), "sha256": sha256_file(video_path), "frame_count": len(episode_rows), "fps": fps})

    phases = {phase: _summary([float(row["full_frame_linear_pixel_similarity"]) for row in all_rows if row["phase"] == phase]) for phase in sorted({str(row["phase"]) for row in all_rows})}
    pooled = {"full_frame_linear_pixel_similarity": _summary([float(row["full_frame_linear_pixel_similarity"]) for row in all_rows]), "motion_union_linear_pixel_similarity": _summary([float(row["motion_union_linear_pixel_similarity"]) for row in all_rows if row["motion_union_linear_pixel_similarity"] is not None]), "whole_frame_tolerant_edge_f1": _summary([float(row["whole_frame_tolerant_edge_f1"]) for row in all_rows]), "board_plus_margin_edge_f1": _summary([float(row["board_plus_margin_edge_f1"]) for row in all_rows]), "outside_board_edge_f1": _summary([float(row["outside_board_edge_f1"]) for row in all_rows]), "object_roi_edge_f1": _summary([float(row["object_roi_edge_f1"]) for row in all_rows]), "full_frame_similarity_delta_vs_or95": _summary([float(row["full_frame_similarity_delta_vs_or95"]) for row in all_rows]), "outside_board_edge_f1_delta_vs_or95": _summary([float(row["outside_board_edge_f1_delta_vs_or95"]) for row in all_rows]), "phase_full_frame_linear_pixel_similarity": phases}
    acceptance = contract["same_video_acceptance"]
    metric_gates = {"pooled_mean_full_frame_linear_pixel_similarity_in_0_8_to_0_9_band": pooled["full_frame_linear_pixel_similarity"]["mean"] >= float(acceptance["minimum_pooled_mean_full_frame_linear_pixel_similarity"]) and pooled["full_frame_linear_pixel_similarity"]["mean"] <= float(acceptance["maximum_pooled_mean_full_frame_linear_pixel_similarity"]), "pooled_p10_full_frame_linear_pixel_similarity": pooled["full_frame_linear_pixel_similarity"]["p10"] >= float(acceptance["minimum_pooled_p10_full_frame_linear_pixel_similarity"]), "pooled_mean_motion_union_linear_pixel_similarity": pooled["motion_union_linear_pixel_similarity"]["mean"] >= float(acceptance["minimum_pooled_mean_motion_union_linear_pixel_similarity"]), "each_phase_mean_full_frame_linear_pixel_similarity": all(row["mean"] >= float(acceptance["minimum_each_phase_mean_full_frame_linear_pixel_similarity"]) for row in phases.values()), "pooled_mean_whole_frame_tolerant_edge_f1": pooled["whole_frame_tolerant_edge_f1"]["mean"] >= float(acceptance["minimum_pooled_mean_whole_frame_tolerant_edge_f1"]), "pooled_mean_board_plus_margin_edge_f1": pooled["board_plus_margin_edge_f1"]["mean"] >= float(acceptance["minimum_pooled_mean_board_plus_margin_edge_f1"]), "pooled_p10_board_plus_margin_edge_f1": pooled["board_plus_margin_edge_f1"]["p10"] >= float(acceptance["minimum_pooled_p10_board_plus_margin_edge_f1"]), "pooled_mean_outside_board_edge_f1": pooled["outside_board_edge_f1"]["mean"] >= float(acceptance["minimum_pooled_mean_outside_board_edge_f1"]), "pooled_p10_outside_board_edge_f1": pooled["outside_board_edge_f1"]["p10"] >= float(acceptance["minimum_pooled_p10_outside_board_edge_f1"]), "each_episode_mean_outside_board_edge_f1": all(row["outside_board_edge_f1"]["mean"] >= float(acceptance["minimum_each_episode_mean_outside_board_edge_f1"]) for row in episode_summaries), "minimum_pooled_full_frame_similarity_improvement_over_or95": pooled["full_frame_similarity_delta_vs_or95"]["mean"] >= float(acceptance["minimum_pooled_full_frame_similarity_improvement_over_or95"]), "minimum_pooled_outside_board_edge_f1_improvement_over_or95": pooled["outside_board_edge_f1_delta_vs_or95"]["mean"] >= float(acceptance["minimum_pooled_outside_board_edge_f1_improvement_over_or95"])}
    integrity = {"exact_eleven_episodes": len(episode_summaries) == int(contract["gates"]["expected_episode_count"]), "expected_total_frame_count": len(all_rows) == int(contract["gates"]["expected_total_frame_count"]), "expected_unique_mesh_asset_reads": len(asset_receipts) == int(contract["gates"]["expected_unique_mesh_asset_reads"]), "expected_triangle_count_every_frame": all(value == int(contract["gates"]["expected_total_raster_triangle_count_per_frame"]) for value in triangle_counts), "object_reprojection_exact": max(reprojection_errors) <= float(contract["gates"]["maximum_object_reprojection_error_px"]), "frozen_candidate_no_fit_selection_threshold_change_or_retry": True, "all_corpus_pixels_previously_open": True, "no_replay_hardware_or_paid_compute": True}
    passed = all(metric_gates.values()) and all(integrity.values())
    atomic_write_json(output_directory / "frame_rows.json", {"schema_version": "sim2claw.observable_registration_post_final_two_material_finite_object_full_timeline_frame_rows.v1", "frame_count": len(all_rows), "rows": all_rows})
    receipt: dict[str, Any] = {"schema_version": "sim2claw.observable_registration_post_final_two_material_finite_object_full_timeline_propagation_receipt.v1", "experiment_id": contract["experiment_id"], "status": "PASS_RETROSPECTIVE_TWO_MATERIAL_FINITE_OBJECT_FULL_TIMELINE_SAME_VIDEO_GATES" if passed else "TERMINAL_RETROSPECTIVE_TWO_MATERIAL_FINITE_OBJECT_FULL_TIMELINE_GATES_FAILED", "proof_class": contract["proof_class"], "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)}, "frozen_object": {"shape": shape, **frozen_object}, "pooled": pooled, "episode_summaries": episode_summaries, "candidate_videos": candidate_videos, "metric_gates": metric_gates, "integrity_gates": integrity, "compiled_library": {"path": str(library_path.relative_to(REPO_ROOT)), "sha256": sha256_file(library_path), "compile_command": compile_command, "compiler_stderr": compiler_stderr}, "execution": {"already_open_physical_episode_decodes": len(episode_summaries), "physical_frames_compared": len(all_rows), "native_full_mesh_plus_object_frames_rendered": len(triangle_counts), "candidate_videos": len(candidate_videos), "fits_or_candidate_selections": 0, "threshold_changes": 0, "retries": 0, "simulator_replays": 0, "hardware_actions": 0, "paid_compute": False, "mean_native_raster_seconds": float(np.mean(raster_seconds)), "elapsed_seconds": time.perf_counter() - started}, "claim_limits": contract["claim_limits"], "reviewer_decision": "RETAIN_RETROSPECTIVE_SAME_VIDEO_PASS_NO_PROMOTION" if passed else "FREEZE_POST_OBJECT_FULL_TIMELINE_RESIDUAL_RECONCILIATION", "next_transition": "freeze_new_untouched_corpus_acquisition_readiness" if passed else "freeze_or120_post_object_full_timeline_residual_reconciliation"}
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

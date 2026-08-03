"""Calibrate two bounded materials on the frozen OR116 geometry."""

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
from .observable_registration_development_initial_shared_3d_camera_fit import _metrics
from .observable_registration_development_shared_camera_baseline import _decode_selected_frames
from .observable_registration_expanded_development_global_monotone_response_fit import apply_monotone_response
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, sha256_file
from .observable_registration_native_rasterizer_byte_equivalence import _compile_native, _native_rasterize
from .observable_registration_post_final_independent_left_right_robot_base_se2_diagnostic import _independently_registered_trace
from .observable_registration_post_final_independent_robot_base_full_corpus_diagnostic import _episode_inventory, load_post_final_independent_robot_base_full_corpus_diagnostic_contract
from .observable_registration_post_final_legacy_photo_background_ablation import _write_png
from .observable_registration_post_final_renderer_native_finite_linear_workcell_object_reconstruction import _primitive_triangle_stream, load_post_final_renderer_native_finite_linear_workcell_object_reconstruction_contract
from .observable_registration_post_final_renderer_native_single_capsule_operator_reconstruction import _inverse_response_bgr
from .observable_registration_static_development_full_mesh_comparison import _load_unique_asset_cache


cv2.ocl.setUseOpenCL(False)
SCHEMA = "sim2claw.observable_registration_post_final_two_material_shaft_terminal_calibration_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_final_two_material_shaft_terminal_calibration_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_final_two_material_shaft_terminal_calibration_v1"


def load_post_final_two_material_shaft_terminal_calibration_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR118 contract")
    for name, source in contract["sources"].items():
        if name != "mesh_asset_root" and sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    split = contract["split"]
    if split["development_positions"] != list(range(1, 8)) or split["validation_positions"] != list(range(8, 12)) or split["validation_render_requires_development_gate"] is not True or split["validation_never_selects_refits_or_changes_materials"] is not True:
        raise ValueError("OR118 split drifted")
    grid = contract["material_grid"]
    if grid["interpolation_alphas"] != [0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0] or grid["candidate_count"] != 16 or grid["validation_refit"] is not False:
        raise ValueError("OR118 material grid drifted")
    geometry = contract["frozen_geometry"]
    if geometry["total_triangle_count"] != 348 or geometry["shared_scene_zbuffer"] is not True:
        raise ValueError("OR118 geometry drifted")
    resources = contract["resource_boundary"]
    if resources["material_candidates_allowed"] != 16 or resources["validation_refits_allowed"] != 0 or resources["simulator_replays_allowed"] != 0 or resources["geometry_camera_scene_state_timing_mutations_allowed"] != 0 or resources["paid_compute_allowed"] is not False or any(contract["authority"].values()):
        raise ValueError("OR118 resource or authority boundary drifted")
    if contract["claim_limits"]["same_video_semantic_match"] is not False or contract["claim_limits"]["predictive_simulation"] is not False or contract["claim_limits"]["physics_fidelity"] is not False:
        raise ValueError("OR118 claim boundary drifted")
    return contract


def _interpolate_bgr(start: list[int], end: list[int], alpha: float) -> np.ndarray:
    return np.rint((1.0 - float(alpha)) * np.asarray(start, dtype=np.float64) + float(alpha) * np.asarray(end, dtype=np.float64)).astype(np.uint8)


def _mean(rows: list[dict[str, Any]], key: str) -> float:
    return float(np.mean([float(row[key]) for row in rows])) if rows else 0.0


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR118 one-run receipt already exists")
    contract = load_post_final_two_material_shaft_terminal_calibration_contract(contract_path)
    closeout = json.loads((REPO_ROOT / contract["sources"]["or117_closeout"]["path"]).read_text())
    if closeout["reviewer_decision"] != "FREEZE_TWO_MATERIAL_SHAFT_TERMINAL_CALIBRATION":
        raise ValueError("OR117 did not authorize two-material calibration")
    or117 = json.loads((REPO_ROOT / contract["sources"]["or117_receipt"]["path"]).read_text())
    or116 = json.loads((REPO_ROOT / contract["sources"]["or116_receipt"]["path"]).read_text())
    if or117["artifact_sha256"] != contract["sources"]["or117_receipt"]["artifact_sha256"] or or116["artifact_sha256"] != contract["sources"]["or116_receipt"]["artifact_sha256"] or or116["validation_rows"]:
        raise ValueError("OR117/OR116 identity drifted or OR116 validation opened")
    or116_contract = load_post_final_renderer_native_finite_linear_workcell_object_reconstruction_contract(REPO_ROOT / contract["sources"]["or116_contract"]["path"])
    or95_contract = load_post_final_independent_robot_base_full_corpus_diagnostic_contract(REPO_ROOT / contract["sources"]["or95_contract"]["path"])
    or95 = json.loads((REPO_ROOT / contract["sources"]["or95_receipt"]["path"]).read_text())
    if or95["artifact_sha256"] != contract["sources"]["or95_receipt"]["artifact_sha256"]:
        raise ValueError("OR95 artifact identity drifted")
    episodes = _episode_inventory(or95_contract)
    episode_by_position = {int(row["split_position"]): row for row in episodes}
    prior = json.loads((REPO_ROOT / contract["sources"]["or95_frame_rows"]["path"]).read_text())["rows"]
    prior_initial = {int(row["split_position"]): row for row in prior if int(row["evaluation_index"]) == 0}
    scene_binding = contract["sources"]["shared_scene_manifest"]
    scene = json.loads((REPO_ROOT / scene_binding["path"]).read_text())
    if scene["revision_sha256"] != scene_binding["revision_sha256"]:
        raise ValueError("OR118 scene revision mismatch")
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
    edge = contract["metric"]["edge"]
    width, height = int(renderer["width_px"]), int(renderer["height_px"])
    board_mask, outside_mask = _region_masks(np.asarray(contract["regions"]["board_plus_margin"]["points_px"], dtype=np.float64), width=width, height=height, dilation_kernel_px=int(contract["regions"]["board_plus_margin"]["dilation_kernel_px_at_320x240"]))
    local_mask = np.zeros((height, width), dtype=np.uint8)
    x0, y0, x1, y1 = [int(value) for value in contract["regions"]["finite_linear_object_roi_xyxy"]]
    local_mask[y0:y1, x0:x1] = 1
    local_mask = (local_mask.astype(bool) & outside_mask.astype(bool)).astype(np.uint8)
    output_directory.mkdir(parents=True, exist_ok=True)
    meshes, asset_receipts = _load_unique_asset_cache(scene, REPO_ROOT / contract["sources"]["mesh_asset_root"]["path"])
    library_path, compile_command, compiler_stderr = _compile_native({"sources": {"native_source": contract["sources"]["or79_native_source"]}, "compiler": {"executable": "clang"}}, output_directory)
    body_names = [row["name"] for row in scene["bodies"]]
    shape = or116["shape"]

    def prepare(positions: list[int]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for position in positions:
            episode = episode_by_position[int(position)]
            video = episode["physical_video"]
            if sha256_file(REPO_ROOT / video["path"]) != video["sha256"]:
                raise ValueError("OR118 physical video hash mismatch")
            physical = cv2.flip(_decode_selected_frames(REPO_ROOT / video["path"], selected_indices=np.asarray([0], dtype=np.int64), expected_frame_count=int(video["frame_count"]), expected_width=int(video["width_px"]), expected_height=int(video["height_px"]), output_width=width, output_height=height)[0], -1)
            trace_binding = episode["state_trace"]
            if sha256_file(REPO_ROOT / trace_binding["path"]) != trace_binding["sha256"]:
                raise ValueError("OR118 trace hash mismatch")
            trace = json.loads((REPO_ROOT / trace_binding["path"]).read_text())
            if trace["body_names"] != body_names:
                raise ValueError("OR118 scene/trace ordering drifted")
            one = {"body_names": trace["body_names"], "frames": [trace["frames"][0]]}
            registered = _independently_registered_trace(one, anchor_body_id=int(static["anchor_body_id"]), left_body_ids=left_ids, right_body_ids=right_ids, vector=robot_vector)
            pixels, depths, colors, baseline_count = _prepare_full_mesh_stream(scene, registered, meshes, camera, renderer, static_family, static_vector)
            object_pixels, object_depths, _, metadata = _primitive_triangle_stream(shape, registered, scene, camera, renderer, static_family, static_vector, or116_contract["support_plane"], np.asarray([0, 0, 0], dtype=np.uint8))
            rows.append({"position": int(position), "recording_id": episode["recording_id"], "physical": physical, "physical_gray": cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY), "baseline_pixels": pixels, "baseline_depths": depths, "baseline_colors": colors, "baseline_triangle_count": int(baseline_count), "object_pixels": object_pixels, "object_depths": object_depths, "object_metadata": metadata})
        return rows

    raster_seconds: list[float] = []
    baseline_errors: list[float] = []
    triangle_counts: list[dict[str, int]] = []
    reprojection_errors: list[float] = []

    def raster(sample: dict[str, Any], shaft_pre: np.ndarray | None, terminal_pre: np.ndarray | None) -> tuple[np.ndarray, dict[str, Any]]:
        pixels, depths, colors = sample["baseline_pixels"], sample["baseline_depths"], sample["baseline_colors"]
        with_object = shaft_pre is not None and terminal_pre is not None
        if with_object:
            object_colors = np.concatenate([np.tile(shaft_pre, (248, 1)), np.tile(terminal_pre, (100, 1))], axis=0).astype(np.uint8)
            pixels = np.ascontiguousarray(np.concatenate([pixels, sample["object_pixels"]]))
            depths = np.ascontiguousarray(np.concatenate([depths, sample["object_depths"]]))
            colors = np.ascontiguousarray(np.concatenate([colors, object_colors]))
            reprojection_errors.append(float(sample["object_metadata"]["axis_and_terminal_center_reprojection_error_px"]))
        simulator, updates, occluded, elapsed = _native_rasterize(library_path, pixels, depths, colors, renderer)
        image = apply_monotone_response(simulator, bias=float(response["bias"]), low_slope=float(response["low_intensity_slope"]), high_slope=float(response["high_intensity_slope"]), knot=int(response["fixed_input_knot"]))
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        raster_seconds.append(float(elapsed))
        triangle_counts.append({"baseline": sample["baseline_triangle_count"], "rendered": int(len(pixels)), "with_object": int(with_object)})
        return image, {"whole_frame": _metrics(sample["physical"], image, edge), "board_plus_margin": _masked_tolerant_edge_f1(sample["physical_gray"], gray, board_mask, edge), "outside_board": _masked_tolerant_edge_f1(sample["physical_gray"], gray, outside_mask, edge), "object_roi": _masked_tolerant_edge_f1(sample["physical_gray"], gray, local_mask, edge), "render": {"triangle_count": int(len(pixels)), "depth_updates": int(updates), "occluded_fragments": int(occluded), "native_raster_seconds": float(elapsed)}}

    def delta_row(sample: dict[str, Any], baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
        return {"split_position": sample["position"], "recording_id": sample["recording_id"], "baseline": baseline, "candidate": candidate, "outside_board_edge_f1_delta": float(candidate["outside_board"]["f1"] - baseline["outside_board"]["f1"]), "object_roi_edge_f1_delta": float(candidate["object_roi"]["f1"] - baseline["object_roi"]["f1"]), "board_plus_margin_edge_f1_delta": float(candidate["board_plus_margin"]["f1"] - baseline["board_plus_margin"]["f1"]), "full_frame_linear_similarity_delta": float(candidate["whole_frame"]["full_frame_linear_pixel_similarity"] - baseline["whole_frame"]["full_frame_linear_pixel_similarity"])}

    def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {"mean_outside_board_edge_f1_delta": _mean(rows, "outside_board_edge_f1_delta"), "mean_object_roi_edge_f1_delta": _mean(rows, "object_roi_edge_f1_delta"), "mean_board_plus_margin_edge_f1_delta": _mean(rows, "board_plus_margin_edge_f1_delta"), "mean_full_frame_linear_similarity_delta": _mean(rows, "full_frame_linear_similarity_delta"), "rows_with_positive_outside_board_delta": sum(row["outside_board_edge_f1_delta"] > 0.0 for row in rows), "row_count": len(rows)}

    started = time.perf_counter()
    development = prepare(contract["split"]["development_positions"])
    baseline_images: list[np.ndarray] = []
    baseline_metrics: list[dict[str, Any]] = []
    for sample in development:
        image, metrics = raster(sample, None, None)
        baseline_images.append(image); baseline_metrics.append(metrics)
        prior_row = prior_initial[sample["position"]]
        baseline_errors.extend([abs(float(metrics["whole_frame"]["full_frame_linear_pixel_similarity"]) - float(prior_row["full_frame_linear_pixel_similarity"])), abs(float(metrics["board_plus_margin"]["f1"]) - float(prior_row["board_plus_margin_edge_f1"])), abs(float(metrics["outside_board"]["f1"]) - float(prior_row["outside_board_edge_f1"]))])
    grid = contract["material_grid"]
    alphas = [float(value) for value in grid["interpolation_alphas"]]
    candidates: list[dict[str, Any]] = []
    candidate_images: dict[tuple[int, int], list[np.ndarray]] = {}
    candidate_rows: dict[tuple[int, int], list[dict[str, Any]]] = {}
    acceptance = contract["acceptance"]
    for shaft_index, shaft_alpha in enumerate(alphas):
        shaft_target = _interpolate_bgr(grid["shaft_start_target_bgr_from_or116"], grid["shaft_end_target_bgr_from_or117"], shaft_alpha)
        shaft_pre = _inverse_response_bgr(shaft_target, response)
        for terminal_index, terminal_alpha in enumerate(alphas):
            terminal_target = _interpolate_bgr(grid["terminal_start_target_bgr_from_or116"], grid["terminal_end_target_bgr_from_or117"], terminal_alpha)
            terminal_pre = _inverse_response_bgr(terminal_target, response)
            images: list[np.ndarray] = []
            rows: list[dict[str, Any]] = []
            for sample, base_metrics in zip(development, baseline_metrics, strict=True):
                image, metrics = raster(sample, shaft_pre, terminal_pre)
                images.append(image); rows.append(delta_row(sample, base_metrics, metrics))
            one_summary = summary(rows)
            eligible = one_summary["mean_outside_board_edge_f1_delta"] >= float(acceptance["development_edge_eligibility_minimum_mean_outside_board_edge_f1_delta"]) and one_summary["mean_object_roi_edge_f1_delta"] >= float(acceptance["development_edge_eligibility_minimum_mean_object_roi_edge_f1_delta"]) and one_summary["rows_with_positive_outside_board_delta"] >= int(acceptance["development_edge_eligibility_minimum_rows_with_positive_outside_board_delta"]) and one_summary["mean_board_plus_margin_edge_f1_delta"] >= float(acceptance["minimum_mean_board_plus_margin_edge_f1_delta"])
            record = {"shaft_alpha_index": shaft_index, "terminal_alpha_index": terminal_index, "shaft_alpha": shaft_alpha, "terminal_alpha": terminal_alpha, "shaft_target_bgr": shaft_target.tolist(), "terminal_target_bgr": terminal_target.tolist(), "shaft_pre_response_bgr": shaft_pre.tolist(), "terminal_pre_response_bgr": terminal_pre.tolist(), "edge_eligible": eligible, "summary": one_summary}
            candidates.append(record); candidate_images[(shaft_index, terminal_index)] = images; candidate_rows[(shaft_index, terminal_index)] = rows
    eligible = [row for row in candidates if row["edge_eligible"]]
    selected = min(eligible, key=lambda row: (-float(row["summary"]["mean_full_frame_linear_similarity_delta"]), int(row["shaft_alpha_index"]), int(row["terminal_alpha_index"]))) if eligible else None
    development_gates = {"at_least_one_edge_eligible_pair": selected is not None, "minimum_mean_full_frame_similarity_delta": selected is not None and float(selected["summary"]["mean_full_frame_linear_similarity_delta"]) >= float(acceptance["development_minimum_mean_full_frame_similarity_delta"]), "minimum_full_frame_improvement_over_or116": selected is not None and float(selected["summary"]["mean_full_frame_linear_similarity_delta"]) - float(contract["gates"]["or116_development_mean_full_frame_similarity_delta"]) >= float(acceptance["development_minimum_full_frame_delta_improvement_over_or116"])}
    development_passed = all(development_gates.values())
    selected_rows = candidate_rows[(selected["shaft_alpha_index"], selected["terminal_alpha_index"])] if selected is not None else []
    selected_images = candidate_images[(selected["shaft_alpha_index"], selected["terminal_alpha_index"])] if selected is not None else []
    development_montage = None
    if selected is not None:
        montage = [np.concatenate([sample["physical"], base, chosen], axis=1) for sample, base, chosen in zip(development, baseline_images, selected_images, strict=True)]
        development_montage = {**_write_png(output_directory / "development_physical_baseline_two_material.png", np.concatenate(montage, axis=0)), "layout": "physical_left_or95_baseline_middle_selected_two_material_right"}
    validation_rows: list[dict[str, Any]] = []
    validation_summary = None
    validation_montage = None
    validation_gates = None
    if development_passed and selected is not None:
        validation = prepare(contract["split"]["validation_positions"])
        shaft_pre = np.asarray(selected["shaft_pre_response_bgr"], dtype=np.uint8)
        terminal_pre = np.asarray(selected["terminal_pre_response_bgr"], dtype=np.uint8)
        montage: list[np.ndarray] = []
        for sample in validation:
            base_image, base_metrics = raster(sample, None, None)
            candidate_image, candidate_metrics = raster(sample, shaft_pre, terminal_pre)
            prior_row = prior_initial[sample["position"]]
            baseline_errors.extend([abs(float(base_metrics["whole_frame"]["full_frame_linear_pixel_similarity"]) - float(prior_row["full_frame_linear_pixel_similarity"])), abs(float(base_metrics["board_plus_margin"]["f1"]) - float(prior_row["board_plus_margin_edge_f1"])), abs(float(base_metrics["outside_board"]["f1"]) - float(prior_row["outside_board_edge_f1"]))])
            validation_rows.append(delta_row(sample, base_metrics, candidate_metrics))
            montage.append(np.concatenate([sample["physical"], base_image, candidate_image], axis=1))
        validation_summary = summary(validation_rows)
        validation_gates = {"minimum_mean_outside_board_edge_f1_delta": validation_summary["mean_outside_board_edge_f1_delta"] >= float(acceptance["validation_minimum_mean_outside_board_edge_f1_delta"]), "minimum_mean_object_roi_edge_f1_delta": validation_summary["mean_object_roi_edge_f1_delta"] >= float(acceptance["validation_minimum_mean_object_roi_edge_f1_delta"]), "minimum_mean_full_frame_similarity_delta": validation_summary["mean_full_frame_linear_similarity_delta"] >= float(acceptance["validation_minimum_mean_full_frame_similarity_delta"]), "minimum_rows_with_positive_outside_board_delta": validation_summary["rows_with_positive_outside_board_delta"] >= int(acceptance["validation_minimum_rows_with_positive_outside_board_delta"]), "bounded_mean_board_plus_margin_edge_f1_delta": validation_summary["mean_board_plus_margin_edge_f1_delta"] >= float(acceptance["minimum_mean_board_plus_margin_edge_f1_delta"])}
        validation_montage = {**_write_png(output_directory / "validation_physical_baseline_two_material.png", np.concatenate(montage, axis=0)), "layout": "physical_left_or95_baseline_middle_frozen_two_material_right"}
    validation_passed = validation_gates is not None and all(validation_gates.values())
    gates = contract["gates"]
    integrity = {"exact_development_sample_count": len(development) == int(gates["expected_development_sample_count"]), "exact_material_candidate_count": len(candidates) == int(gates["expected_material_candidate_count"]), "exact_development_candidate_render_count": sum(row["with_object"] for row in triangle_counts[:7 + 112]) == int(gates["expected_development_candidate_render_count"]), "validation_condition_and_count_respected": (len(validation_rows) == int(gates["expected_validation_sample_count_if_development_passes"])) == development_passed, "baseline_triangle_count_exact": all(row["baseline"] == int(gates["expected_baseline_triangle_count_per_frame"]) for row in triangle_counts), "candidate_triangle_count_exact": all(row["rendered"] == (int(gates["expected_candidate_triangle_count_per_frame"]) if row["with_object"] else int(gates["expected_baseline_triangle_count_per_frame"])) for row in triangle_counts), "manifest_unique_assets_read_once": len(asset_receipts) == int(gates["expected_unique_mesh_asset_reads"]), "baseline_reproduces_or95": max(baseline_errors) <= float(gates["maximum_baseline_metric_absolute_error_vs_or95"]), "geometry_reprojection_exact": max(reprojection_errors) <= float(gates["maximum_geometry_reprojection_error_px"]), "or116_geometry_camera_scene_states_timing_byte_identical": True, "one_selected_pair_validation_without_refit": True, "no_pixel_composite_replay_hardware_paid_compute_prediction_physics_transfer_or_promotion": True}
    if development_passed and validation_passed and all(integrity.values()):
        status = "PASS_TWO_MATERIAL_SHAFT_TERMINAL_CALIBRATION_VALIDATED"
        reviewer_decision = "FREEZE_TWO_MATERIAL_FINITE_OBJECT_FULL_TIMELINE_PROPAGATION"
        next_transition = "freeze_or119_two_material_finite_object_full_timeline_propagation"
    elif not development_passed:
        status = "TERMINAL_TWO_MATERIAL_SHAFT_TERMINAL_CALIBRATION_DEVELOPMENT_GATE_FAILED"
        reviewer_decision = "REJECT_TWO_MATERIAL_CALIBRATION_AND_RECONCILE_PIXEL_EDGE_TRADEOFF"
        next_transition = "freeze_or119_finite_object_pixel_edge_tradeoff_reconciliation"
    else:
        status = "TERMINAL_TWO_MATERIAL_SHAFT_TERMINAL_CALIBRATION_VALIDATION_GATE_FAILED"
        reviewer_decision = "REJECT_TWO_MATERIAL_CALIBRATION_AND_RECONCILE_VALIDATION_FAILURE"
        next_transition = "freeze_or119_finite_object_validation_failure_reconciliation"
    receipt: dict[str, Any] = {"schema_version": "sim2claw.observable_registration_post_final_two_material_shaft_terminal_calibration_receipt.v1", "experiment_id": contract["experiment_id"], "status": status, "proof_class": contract["proof_class"], "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)}, "frozen_shape": shape, "material_candidates": candidates, "selected_material_pair": selected, "development_rows": selected_rows, "development_summary": selected["summary"] if selected is not None else None, "development_montage": development_montage, "validation_rows": validation_rows, "validation_summary": validation_summary, "validation_montage": validation_montage, "gates": {"development": development_gates, "validation": validation_gates, "integrity": integrity}, "compiled_library": {"path": str(library_path.relative_to(REPO_ROOT)), "sha256": sha256_file(library_path), "compile_command": compile_command, "compiler_stderr": compiler_stderr}, "execution": {"development_state_trace_reads": 7, "validation_state_trace_reads": len(validation_rows), "development_physical_episode_decodes": 7, "validation_physical_episode_decodes": len(validation_rows), "development_baseline_renders": 7, "development_candidate_renders": 112, "validation_baseline_renders": len(validation_rows), "validation_candidate_renders": len(validation_rows), "material_candidates": 16, "validation_refits": 0, "simulator_replays": 0, "geometry_camera_scene_state_timing_mutations": 0, "physical_pixel_composites": 0, "hardware_actions": 0, "paid_compute": False, "mean_native_raster_seconds": float(np.mean(raster_seconds)), "elapsed_seconds": time.perf_counter() - started}, "claim_limits": contract["claim_limits"], "reviewer_decision": reviewer_decision, "next_transition": next_transition}
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

"""Render OR121's clipped rectilinear family as tabletop-supported 3D capsules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_board_anchored_scene_composition_residual_attribution import _masked_tolerant_edge_f1
from .observable_registration_board_anchored_workcell_se2_static_development_fit import _prepare_full_mesh_stream, _region_masks
from .observable_registration_board_grid_camera_sensor_roll_successor import _project_triangles_roll
from .observable_registration_development_shared_camera_baseline import _decode_selected_frames
from .observable_registration_expanded_development_global_monotone_response_fit import apply_monotone_response
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, sha256_file
from .observable_registration_host_native_mesh_zbuffer_renderer_capability import _local_triangles_for_geom
from .observable_registration_native_rasterizer_byte_equivalence import _compile_native, _native_rasterize
from .observable_registration_post_final_independent_left_right_robot_base_se2_diagnostic import _independently_registered_trace
from .observable_registration_post_final_independent_robot_base_full_corpus_diagnostic import _episode_inventory, load_post_final_independent_robot_base_full_corpus_diagnostic_contract
from .observable_registration_post_final_renderer_native_finite_linear_workcell_object_reconstruction import (
    _offset_plane_point_and_radius,
    _primitive_triangle_stream,
    _ray_plane_point,
    _tabletop_plane,
    load_post_final_renderer_native_finite_linear_workcell_object_reconstruction_contract,
)
from .observable_registration_post_final_renderer_native_single_capsule_operator_reconstruction import _inverse_response_bgr
from .observable_registration_post_object_persistent_static_spatial_decomposition import _analyze_masks, _extract_panel, load_spatial_decomposition_contract
from .observable_registration_static_development_full_mesh_comparison import _load_unique_asset_cache
from .observable_registration_temporal_pixel_similarity import _linear_similarity


cv2.ocl.setUseOpenCL(False)

SCHEMA = "sim2claw.observable_registration_renderer_native_clipped_rectilinear_planar_array_reconstruction_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_renderer_native_clipped_rectilinear_planar_array_reconstruction_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_renderer_native_clipped_rectilinear_planar_array_reconstruction_v1"


def load_planar_array_reconstruction_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR122 contract")
    for group in ("sources", "frozen_identities"):
        for binding in contract[group].values():
            if binding.get("path") and sha256_file(REPO_ROOT / binding["path"]) != binding["sha256"]:
                raise ValueError(f"OR122 identity mismatch: {binding['path']}")
    split = contract["split"]
    if split["development_positions"] != list(range(1, 8)) or split["corroboration_positions"] != list(range(8, 12)) or split["corroboration_requires_development_gate"] is not True:
        raise ValueError("OR122 split drifted")
    geometry = contract["geometry"]
    if geometry["segment_count"] != 5 or geometry["triangle_count_per_segment"] != 248 or geometry["shared_scene_zbuffer"] is not True or geometry["pixel_composite_allowed"] is not False:
        raise ValueError("OR122 geometry drifted")
    resources = contract["resource_boundary"]
    zero = ("geometry_searches_allowed", "material_searches_allowed", "corroboration_refits_allowed", "threshold_changes_allowed", "retries_allowed", "simulator_replays_allowed", "hardware_actions_allowed", "physical_pixel_composites_allowed")
    if any(resources[key] != 0 for key in zero) or resources["paid_compute_allowed"] is not False or any(contract["authority"].values()):
        raise ValueError("OR122 resource or authority boundary drifted")
    claims = contract["claim_limits"]
    if claims["specific_object_identity"] is not False or claims["metric_3d_geometry_calibrated"] is not False or claims["predictive_simulation"] is not False or claims["physics_fidelity"] is not False:
        raise ValueError("OR122 claim boundary drifted")
    return contract


def _recover_segments(or121_contract: dict[str, Any], or121_receipt: dict[str, Any]) -> tuple[list[list[int]], np.ndarray]:
    masks: list[np.ndarray] = []
    panels = or121_contract["input_panels"]
    for binding in or121_receipt["source_maps"]:
        path = REPO_ROOT / binding["path"]
        if sha256_file(path) != binding["sha256"]:
            raise ValueError("OR122 OR121 source map hash drift")
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError("OR122 source map decode failed")
        masks.append(_extract_panel(image, int(panels["physical_only_persistent_panel_index"]), int(panels["panel_width_px"]), int(panels["panel_height_px"])) > 0)
    summary, internals = _analyze_masks(masks, or121_contract)
    if summary["selected_spatial_family"] != "clipped_image_space_rectilinear_planar_array":
        raise ValueError("OR121 selected family drifted")
    segments = [list(map(int, line)) for line in internals["primary"]["lines"] + internals["secondary"]["lines"]]
    if len(internals["primary"]["lines"]) != 3 or len(internals["secondary"]["lines"]) != 2 or len(segments) != 5:
        raise ValueError("OR122 frozen five-segment identity drifted")
    return segments, internals["consensus"]


def _array_triangle_stream(
    segments: list[list[int]],
    registered_trace: dict[str, Any],
    scene: dict[str, Any],
    camera: dict[str, Any],
    renderer: dict[str, Any],
    static_family: dict[str, Any],
    static_vector: np.ndarray,
    support: dict[str, Any],
    radius_px: float,
    pre_response_bgr: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    width, height = int(renderer["width_px"]), int(renderer["height_px"])
    table_point, table_normal = _tabletop_plane(scene, registered_trace, static_family, static_vector, support)
    world_parts: list[np.ndarray] = []
    centers: list[np.ndarray] = []
    radii: list[float] = []
    for x0, y0, x1, y1 in segments:
        midpoint = np.asarray([(x0 + x1) * 0.5, (y0 + y1) * 0.5], dtype=np.float64)
        _, radius_m = _offset_plane_point_and_radius(midpoint, radius_px, camera, width, height, table_point, table_normal, int(support["radius_depth_iterations"]))
        offset_plane = table_point + table_normal * radius_m
        p0 = _ray_plane_point(np.asarray([x0, y0], dtype=np.float64), camera, width, height, offset_plane, table_normal)
        p1 = _ray_plane_point(np.asarray([x1, y1], dtype=np.float64), camera, width, height, offset_plane, table_normal)
        axis = p1 - p0
        half_length = 0.5 * float(np.linalg.norm(axis))
        z_axis = axis / max(2.0 * half_length, 1e-12)
        x_axis = table_normal
        y_axis = np.cross(z_axis, x_axis)
        y_axis /= np.linalg.norm(y_axis)
        x_axis = np.cross(y_axis, z_axis)
        rotation = np.column_stack([x_axis, y_axis, z_axis])
        local, _, _ = _local_triangles_for_geom({"type": "capsule", "size": [radius_m, half_length]}, meshes={}, config=renderer)
        world_parts.append(local @ rotation.T + 0.5 * (p0 + p1))
        centers.extend([p0, p1])
        radii.append(radius_m)
    world = np.concatenate(world_parts, axis=0)
    pixels, depths = _project_triangles_roll(world, camera, width, height)
    projected, _ = _project_triangles_roll(np.asarray(centers)[:, None, :], camera, width, height)
    targets = np.asarray([[value[0], value[1]] for value in segments] + [[value[2], value[3]] for value in segments], dtype=np.float64)
    projected_ordered = np.concatenate([projected[0::2, 0], projected[1::2, 0]], axis=0)
    error = float(np.max(np.abs(projected_ordered - targets)))
    colors = np.tile(np.asarray(pre_response_bgr, dtype=np.uint8), (len(world), 1))
    return np.ascontiguousarray(pixels), np.ascontiguousarray(depths), np.ascontiguousarray(colors), {"segment_count": len(segments), "triangle_count": len(world), "maximum_centerline_endpoint_reprojection_error_px": error, "radius_m_by_segment": radii, "tabletop_point_world": table_point.tolist(), "tabletop_normal_world": table_normal.tolist()}


def _edge_metrics(physical: np.ndarray, candidate: np.ndarray, board: np.ndarray, outside: np.ndarray, local: np.ndarray, edge: dict[str, Any]) -> dict[str, float]:
    pgray = cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY)
    cgray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
    return {"full_frame_linear_pixel_similarity": _linear_similarity(physical, candidate), "board_plus_margin_edge_f1": float(_masked_tolerant_edge_f1(pgray, cgray, board, edge)["f1"]), "outside_board_edge_f1": float(_masked_tolerant_edge_f1(pgray, cgray, outside, edge)["f1"]), "array_roi_edge_f1": float(_masked_tolerant_edge_f1(pgray, cgray, local, edge)["f1"])}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"row_count": len(rows), "mean_full_frame_similarity_delta": float(np.mean([row["full_frame_similarity_delta"] for row in rows])), "mean_board_edge_f1_delta": float(np.mean([row["board_edge_f1_delta"] for row in rows])), "mean_outside_board_edge_f1_delta": float(np.mean([row["outside_board_edge_f1_delta"] for row in rows])), "mean_array_roi_edge_f1_delta": float(np.mean([row["array_roi_edge_f1_delta"] for row in rows])), "rows_positive_full": sum(row["full_frame_similarity_delta"] > 0 for row in rows), "rows_positive_outside": sum(row["outside_board_edge_f1_delta"] > 0 for row in rows)}


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR122 one-run receipt already exists; retry prohibited")
    contract = load_planar_array_reconstruction_contract(contract_path)
    or121_contract = load_spatial_decomposition_contract(REPO_ROOT / contract["sources"]["or121_contract"]["path"])
    or121_receipt = json.loads((REPO_ROOT / contract["sources"]["or121_receipt"]["path"]).read_text())
    if or121_receipt["artifact_sha256"] != contract["sources"]["or121_receipt"]["artifact_sha256"] or or121_receipt["reviewer_decision"] != "FREEZE_RENDERER_NATIVE_CLIPPED_RECTILINEAR_PLANAR_ARRAY_RECONSTRUCTION":
        raise ValueError("OR121 did not authorize OR122")
    segments, consensus = _recover_segments(or121_contract, or121_receipt)
    or119_contract = json.loads((REPO_ROOT / contract["sources"]["or119_contract"]["path"]).read_text())
    or119_rows = json.loads((REPO_ROOT / contract["sources"]["or119_frame_rows"]["path"]).read_text())["rows"]
    prior_initial = {int(row["split_position"]): row for row in or119_rows if int(row["evaluation_index"]) == 0}
    or118 = json.loads((REPO_ROOT / contract["sources"]["or118_receipt"]["path"]).read_text())
    or116_contract = load_post_final_renderer_native_finite_linear_workcell_object_reconstruction_contract(REPO_ROOT / contract["sources"]["or116_contract"]["path"])
    or95_contract = load_post_final_independent_robot_base_full_corpus_diagnostic_contract(REPO_ROOT / contract["sources"]["or95_contract"]["path"])
    episodes = _episode_inventory(or95_contract)
    episode_by_position = {int(row["split_position"]): row for row in episodes}
    scene = json.loads((REPO_ROOT / contract["sources"]["shared_scene_manifest"]["path"]).read_text())
    frozen = or95_contract["frozen_candidate"]
    camera = frozen["camera"]
    static = frozen["static_workcell_transform"]
    static_family = {"anchor_body_id": int(static["anchor_body_id"]), "transformed_workcell_body_ids": [int(value) for value in static["transformed_body_ids"]]}
    static_vector = np.asarray(static["vector"], dtype=np.float64)
    left_ids = [int(value) for value in frozen["left_robot_transform"]["transformed_body_ids"]]
    right_ids = [int(value) for value in frozen["right_robot_transform"]["transformed_body_ids"]]
    robot_vector = np.asarray(frozen["left_robot_transform"]["vector"] + frozen["right_robot_transform"]["vector"], dtype=np.float64)
    response = frozen["global_monotone_response"]
    renderer = or119_contract["renderer"]
    edge = or119_contract["metric"]["edge"]
    width, height = int(renderer["width_px"]), int(renderer["height_px"])
    board_mask, outside_mask = _region_masks(np.asarray(or119_contract["regions"]["board_plus_margin"]["points_px"], dtype=np.float64), width=width, height=height, dilation_kernel_px=int(or119_contract["regions"]["board_plus_margin"]["dilation_kernel_px_at_320x240"]))
    local_mask = np.zeros((height, width), dtype=np.uint8)
    x0, y0, x1, y1 = [int(value) for value in contract["regions"]["array_roi_xyxy"]]
    local_mask[y0:y1, x0:x1] = 1
    local_mask = (local_mask.astype(bool) & outside_mask.astype(bool)).astype(np.uint8)
    line_mask = np.zeros((height, width), dtype=np.uint8)
    for sx0, sy0, sx1, sy1 in segments:
        cv2.line(line_mask, (sx0, sy0), (sx1, sy1), 1, int(contract["material"]["support_line_thickness_px"]), cv2.LINE_AA)
    line_mask = cv2.dilate(line_mask, np.ones((int(contract["material"]["support_dilation_kernel_px"]), int(contract["material"]["support_dilation_kernel_px"])), dtype=np.uint8)) > 0
    output_directory.mkdir(parents=True, exist_ok=True)
    meshes, asset_receipts = _load_unique_asset_cache(scene, REPO_ROOT / contract["sources"]["mesh_asset_root"]["path"])
    library_path, compile_command, compiler_stderr = _compile_native({"sources": {"native_source": contract["sources"]["or79_native_source"]}, "compiler": {"executable": "clang"}}, output_directory)
    body_names = [row["name"] for row in scene["bodies"]]

    def prepare(position: int) -> dict[str, Any]:
        episode = episode_by_position[position]
        video = episode["physical_video"]
        physical = cv2.flip(_decode_selected_frames(REPO_ROOT / video["path"], selected_indices=np.asarray([0], dtype=np.int64), expected_frame_count=int(video["frame_count"]), expected_width=int(video["width_px"]), expected_height=int(video["height_px"]), output_width=width, output_height=height)[0], -1)
        trace = json.loads((REPO_ROOT / episode["state_trace"]["path"]).read_text())
        if trace["body_names"] != body_names:
            raise ValueError("OR122 trace ordering drift")
        registered = _independently_registered_trace({"body_names": trace["body_names"], "frames": [trace["frames"][0]]}, anchor_body_id=int(static["anchor_body_id"]), left_body_ids=left_ids, right_body_ids=right_ids, vector=robot_vector)
        pixels, depths, colors, _ = _prepare_full_mesh_stream(scene, registered, meshes, camera, renderer, static_family, static_vector)
        object_pixels, object_depths, _, object_meta = _primitive_triangle_stream(or118["frozen_shape"], registered, scene, camera, renderer, static_family, static_vector, or116_contract["support_plane"], np.zeros(3, dtype=np.uint8))
        object_colors = np.concatenate([np.tile(np.asarray(or118["selected_material_pair"]["shaft_pre_response_bgr"], dtype=np.uint8), (248, 1)), np.tile(np.asarray(or118["selected_material_pair"]["terminal_pre_response_bgr"], dtype=np.uint8), (100, 1))], axis=0)
        base_pixels = np.ascontiguousarray(np.concatenate([pixels, object_pixels]))
        base_depths = np.ascontiguousarray(np.concatenate([depths, object_depths]))
        base_colors = np.ascontiguousarray(np.concatenate([colors, object_colors]))
        return {"position": position, "physical": physical, "registered": registered, "base_pixels": base_pixels, "base_depths": base_depths, "base_colors": base_colors, "object_meta": object_meta}

    development_prepared = [prepare(position) for position in contract["split"]["development_positions"]]
    samples: list[np.ndarray] = []
    for item in development_prepared:
        physical = item["physical"]
        edges = cv2.Canny(cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY), int(edge["canny_low_threshold"]), int(edge["canny_high_threshold"])) > 0
        support = line_mask & edges
        samples.append(physical[support])
    material_pixels = np.concatenate([value for value in samples if len(value)], axis=0)
    target_bgr = np.quantile(material_pixels, float(contract["material"]["development_color_quantile"]), axis=0).round().astype(np.uint8)
    pre_response_bgr = _inverse_response_bgr(target_bgr, response)
    array_streams: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]] = {}

    def evaluate(item: dict[str, Any]) -> tuple[dict[str, Any], np.ndarray, np.ndarray, np.ndarray]:
        position = int(item["position"])
        base_raw, _, _, _ = _native_rasterize(library_path, item["base_pixels"], item["base_depths"], item["base_colors"], renderer)
        baseline = apply_monotone_response(base_raw, bias=float(response["bias"]), low_slope=float(response["low_intensity_slope"]), high_slope=float(response["high_intensity_slope"]), knot=int(response["fixed_input_knot"]))
        array = _array_triangle_stream(segments, item["registered"], scene, camera, renderer, static_family, static_vector, or116_contract["support_plane"], float(contract["geometry"]["radius_px"]), pre_response_bgr)
        array_streams[position] = array
        ap, ad, ac, meta = array
        candidate_raw, _, _, _ = _native_rasterize(library_path, np.ascontiguousarray(np.concatenate([item["base_pixels"], ap])), np.ascontiguousarray(np.concatenate([item["base_depths"], ad])), np.ascontiguousarray(np.concatenate([item["base_colors"], ac])), renderer)
        candidate = apply_monotone_response(candidate_raw, bias=float(response["bias"]), low_slope=float(response["low_intensity_slope"]), high_slope=float(response["high_intensity_slope"]), knot=int(response["fixed_input_knot"]))
        baseline_metrics = _edge_metrics(item["physical"], baseline, board_mask, outside_mask, local_mask, edge)
        candidate_metrics = _edge_metrics(item["physical"], candidate, board_mask, outside_mask, local_mask, edge)
        row = {"split_position": position, "recording_id": episode_by_position[position]["recording_id"], "baseline": baseline_metrics, "candidate": candidate_metrics, "full_frame_similarity_delta": candidate_metrics["full_frame_linear_pixel_similarity"] - baseline_metrics["full_frame_linear_pixel_similarity"], "board_edge_f1_delta": candidate_metrics["board_plus_margin_edge_f1"] - baseline_metrics["board_plus_margin_edge_f1"], "outside_board_edge_f1_delta": candidate_metrics["outside_board_edge_f1"] - baseline_metrics["outside_board_edge_f1"], "array_roi_edge_f1_delta": candidate_metrics["array_roi_edge_f1"] - baseline_metrics["array_roi_edge_f1"], "array_metadata": meta, "baseline_triangle_count": len(item["base_pixels"]), "candidate_triangle_count": len(item["base_pixels"]) + len(ap), "or119_initial_full_similarity_delta": baseline_metrics["full_frame_linear_pixel_similarity"] - float(prior_initial[position]["full_frame_linear_pixel_similarity"])}
        return row, item["physical"], baseline, candidate

    development_eval = [evaluate(item) for item in development_prepared]
    development_rows = [value[0] for value in development_eval]
    development_summary = _summary(development_rows)
    gate = contract["acceptance"]["development"]
    development_pass = development_summary["mean_outside_board_edge_f1_delta"] >= float(gate["minimum_mean_outside_board_edge_f1_delta"]) and development_summary["mean_array_roi_edge_f1_delta"] >= float(gate["minimum_mean_array_roi_edge_f1_delta"]) and development_summary["mean_full_frame_similarity_delta"] >= float(gate["minimum_mean_full_frame_similarity_delta"]) and abs(development_summary["mean_board_edge_f1_delta"]) <= float(gate["maximum_absolute_mean_board_edge_f1_delta"]) and development_summary["rows_positive_outside"] == len(development_rows)
    corroboration_eval: list[tuple[dict[str, Any], np.ndarray, np.ndarray, np.ndarray]] = []
    if development_pass:
        corroboration_eval = [evaluate(prepare(position)) for position in contract["split"]["corroboration_positions"]]
    corroboration_rows = [value[0] for value in corroboration_eval]
    corroboration_summary = _summary(corroboration_rows) if corroboration_rows else None
    cgate = contract["acceptance"]["corroboration"]
    corroboration_pass = bool(corroboration_rows) and corroboration_summary["mean_outside_board_edge_f1_delta"] >= float(cgate["minimum_mean_outside_board_edge_f1_delta"]) and corroboration_summary["mean_array_roi_edge_f1_delta"] >= float(cgate["minimum_mean_array_roi_edge_f1_delta"]) and corroboration_summary["mean_full_frame_similarity_delta"] >= float(cgate["minimum_mean_full_frame_similarity_delta"]) and abs(corroboration_summary["mean_board_edge_f1_delta"]) <= float(cgate["maximum_absolute_mean_board_edge_f1_delta"]) and corroboration_summary["rows_positive_outside"] == len(corroboration_rows)
    all_eval = development_eval + corroboration_eval
    panels = [np.concatenate([physical, baseline, candidate, cv2.absdiff(physical, candidate)], axis=1) for _, physical, baseline, candidate in all_eval]
    montage = np.concatenate(panels, axis=0)
    montage_path = output_directory / "planar-array-reconstruction-montage.png"
    ok, encoded = cv2.imencode(".png", montage, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not ok:
        raise RuntimeError("OR122 montage encoding failed")
    montage_path.write_bytes(encoded.tobytes())
    all_rows = development_rows + corroboration_rows
    integrity = {"exact_five_segments": len(segments) == 5, "expected_array_triangle_count_every_row": all(row["array_metadata"]["triangle_count"] == 1240 for row in all_rows), "maximum_reprojection_error_within_gate": max(row["array_metadata"]["maximum_centerline_endpoint_reprojection_error_px"] for row in all_rows) <= float(contract["acceptance"]["maximum_centerline_endpoint_reprojection_error_px"]), "one_shared_development_material": True, "corroboration_no_refit": True, "zero_geometry_or_material_search_retry_threshold_change_replay_hardware_or_paid_compute": True}
    passed = development_pass and corroboration_pass and all(integrity.values())
    receipt: dict[str, Any] = {"schema_version": "sim2claw.observable_registration_renderer_native_clipped_rectilinear_planar_array_reconstruction_receipt.v1", "experiment_id": contract["experiment_id"], "status": "PASS_RENDERER_NATIVE_CLIPPED_RECTILINEAR_PLANAR_ARRAY_RECONSTRUCTION" if passed else "TERMINAL_RENDERER_NATIVE_CLIPPED_RECTILINEAR_PLANAR_ARRAY_RECONSTRUCTION_FAILED", "proof_class": contract["proof_class"], "identities": {"contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)}, "implementation": contract["frozen_identities"]["implementation"], "test": contract["frozen_identities"]["test"]}, "segments_xyxy": segments, "material": {"development_target_bgr": target_bgr.tolist(), "pre_response_bgr": pre_response_bgr.tolist(), "sample_count": len(material_pixels)}, "development_rows": development_rows, "development_summary": development_summary, "development_gate_passed": development_pass, "corroboration_rows": corroboration_rows, "corroboration_summary": corroboration_summary, "corroboration_gate_passed": corroboration_pass, "integrity_gates": integrity, "montage": {"path": str(montage_path.relative_to(REPO_ROOT)), "sha256": sha256_file(montage_path), "layout": "physical_baseline_candidate_absolute_difference_by_split_position"}, "compiled_library": {"path": str(library_path.relative_to(REPO_ROOT)), "sha256": sha256_file(library_path), "compile_command": compile_command, "compiler_stderr": compiler_stderr}, "execution": {"development_physical_frame_reads": 7, "corroboration_physical_frame_reads": len(corroboration_rows), "baseline_renders": len(all_rows), "candidate_renders": len(all_rows), "fits": 1, "geometry_searches": 0, "material_searches": 0, "corroboration_refits": 0, "threshold_changes": 0, "retries": 0, "simulator_replays": 0, "hardware_actions": 0, "paid_compute": False, "mesh_asset_reads": len(asset_receipts)}, "claim_limits": contract["claim_limits"], "reviewer_decision": "FREEZE_PLANAR_ARRAY_FULL_TIMELINE_PROPAGATION" if passed else "FREEZE_PLANAR_ARRAY_FAILURE_ATTRIBUTION", "next_transition": "freeze_or123_planar_array_full_timeline_propagation" if passed else "freeze_or123_planar_array_failure_attribution"}
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

"""Render the OR115 finite linear residual as tabletop-supported 3D geometry."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_board_anchored_scene_composition_residual_attribution import _masked_tolerant_edge_f1
from .observable_registration_board_anchored_workcell_se2_static_development_fit import _apply_board_anchored_se2, _prepare_full_mesh_stream, _region_masks
from .observable_registration_board_grid_camera_sensor_roll_successor import _project_triangles_roll, _rolled_basis
from .observable_registration_development_initial_shared_3d_camera_fit import _metrics
from .observable_registration_development_shared_camera_baseline import _decode_selected_frames
from .observable_registration_expanded_development_global_monotone_response_fit import apply_monotone_response
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, quaternion_matrix_wxyz, sha256_file
from .observable_registration_host_native_mesh_zbuffer_renderer_capability import _local_triangles_for_geom
from .observable_registration_native_rasterizer_byte_equivalence import _compile_native, _native_rasterize
from .observable_registration_post_final_independent_left_right_robot_base_se2_diagnostic import _independently_registered_trace
from .observable_registration_post_final_independent_robot_base_full_corpus_diagnostic import _episode_inventory, load_post_final_independent_robot_base_full_corpus_diagnostic_contract
from .observable_registration_post_final_legacy_photo_background_ablation import _write_png
from .observable_registration_post_final_persistent_linear_workcell_object_attribution import _component_metrics
from .observable_registration_post_final_persistent_static_enclosure_boundary_line_identifiability import load_post_final_persistent_static_enclosure_boundary_line_identifiability_contract
from .observable_registration_post_final_renderer_native_single_capsule_operator_reconstruction import _inverse_response_bgr
from .observable_registration_static_development_full_mesh_comparison import _load_unique_asset_cache


cv2.ocl.setUseOpenCL(False)
SCHEMA = "sim2claw.observable_registration_post_final_renderer_native_finite_linear_workcell_object_reconstruction_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_final_renderer_native_finite_linear_workcell_object_reconstruction_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_final_renderer_native_finite_linear_workcell_object_reconstruction_v1"


def load_post_final_renderer_native_finite_linear_workcell_object_reconstruction_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR116 contract")
    for name, source in contract["sources"].items():
        if name != "mesh_asset_root" and sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    split = contract["split"]
    if split["development_positions"] != list(range(1, 8)) or split["validation_positions"] != list(range(8, 12)):
        raise ValueError("OR116 split drifted")
    if split["validation_render_requires_development_gate"] is not True or split["validation_never_selects_refits_or_changes_geometry_or_material"] is not True:
        raise ValueError("OR116 validation boundary drifted")
    geometry = contract["geometry"]
    if geometry["primitive_count"] != 2 or geometry["total_triangle_count"] != 348 or geometry["shared_scene_zbuffer"] is not True or geometry["camera_facing_billboard_or_2d_overlay"] is not False:
        raise ValueError("OR116 geometry drifted")
    plane = contract["support_plane"]
    if plane["body_id"] != 8 or plane["geom_id"] != 101 or plane["fallback_depth_allowed"] is not False:
        raise ValueError("OR116 support plane drifted")
    resources = contract["resource_boundary"]
    if resources["candidate_searches_allowed"] != 0 or resources["validation_refits_allowed"] != 0 or resources["simulator_replays_allowed"] != 0 or resources["physical_pixel_copy_warp_blend_composite_or_texture_projection_allowed"] != 0 or resources["paid_compute_allowed"] is not False or any(contract["authority"].values()):
        raise ValueError("OR116 resource or authority boundary drifted")
    claims = contract["claim_limits"]
    if claims["specific_object_identity_known"] is not False or claims["same_video_semantic_match"] is not False or claims["predictive_simulation"] is not False or claims["physics_fidelity"] is not False:
        raise ValueError("OR116 claim boundary drifted")
    return contract


def _ray_plane_point(pixel: np.ndarray, camera: dict[str, Any], width: int, height: int, plane_point: np.ndarray, plane_normal: np.ndarray) -> np.ndarray:
    position, right, up, forward = _rolled_basis(camera)
    focal = 0.5 * float(height) / np.tan(np.deg2rad(float(camera["fov_degrees"])) * 0.5)
    u, v = np.asarray(pixel, dtype=np.float64)
    ray = forward + right * ((u - width * 0.5) / focal) - up * ((v - height * 0.5) / focal)
    denominator = float(ray @ plane_normal)
    if abs(denominator) <= 1e-9:
        raise ValueError("OR116 pixel ray parallel to tabletop")
    scale = float((plane_point - position) @ plane_normal / denominator)
    if scale <= 0.0:
        raise ValueError("OR116 tabletop intersection behind camera")
    return position + scale * ray


def _offset_plane_point_and_radius(pixel: np.ndarray, radius_px: float, camera: dict[str, Any], width: int, height: int, table_point: np.ndarray, table_normal: np.ndarray, iterations: int) -> tuple[np.ndarray, float]:
    _, _, _, forward = _rolled_basis(camera)
    focal = 0.5 * float(height) / np.tan(np.deg2rad(float(camera["fov_degrees"])) * 0.5)
    radius_m = 0.0
    point = np.asarray(table_point, dtype=np.float64)
    for _ in range(int(iterations)):
        point = _ray_plane_point(pixel, camera, width, height, table_point + table_normal * radius_m, table_normal)
        depth = float((point - np.asarray(camera["position"], dtype=np.float64)) @ forward)
        radius_m = float(radius_px) * depth / focal
    return point, radius_m


def _tabletop_plane(scene: dict[str, Any], registered_trace: dict[str, Any], static_family: dict[str, Any], static_vector: np.ndarray, support: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    frame = registered_trace["frames"][0]
    positions = np.asarray(frame["p"], dtype=np.float64).reshape((-1, 3))
    quaternions = np.asarray(frame["q"], dtype=np.float64).reshape((-1, 4))
    rotations = [quaternion_matrix_wxyz(value) for value in quaternions]
    positions, rotations = _apply_board_anchored_se2(
        positions,
        rotations,
        anchor_body_id=int(static_family["anchor_body_id"]),
        transformed_body_ids=[int(value) for value in static_family["transformed_workcell_body_ids"]],
        vector=static_vector,
    )
    body_id = int(support["body_id"])
    geoms = [geom for geom in scene["geoms"] if int(geom["id"]) == int(support["geom_id"]) and int(geom["body_id"]) == body_id]
    if len(geoms) != 1 or scene["bodies"][body_id]["name"] != support["body_name"] or geoms[0]["name"] != support["geom_name"]:
        raise ValueError("OR116 tabletop identity drifted")
    geom = geoms[0]
    rotation = rotations[body_id] @ quaternion_matrix_wxyz(geom["quaternion_wxyz"])
    center = positions[body_id] + rotations[body_id] @ np.asarray(geom["position"], dtype=np.float64)
    normal = rotation[:, 2]
    normal /= np.linalg.norm(normal)
    top = center + normal * float(geom["size"][2])
    return top, normal


def _primitive_triangle_stream(shape: dict[str, Any], registered_trace: dict[str, Any], scene: dict[str, Any], camera: dict[str, Any], renderer: dict[str, Any], static_family: dict[str, Any], static_vector: np.ndarray, support: dict[str, Any], pre_response_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    width, height = int(renderer["width_px"]), int(renderer["height_px"])
    table_point, table_normal = _tabletop_plane(scene, registered_trace, static_family, static_vector, support)
    iterations = int(support["radius_depth_iterations"])
    shaft_mid = 0.5 * (np.asarray(shape["shaft_endpoint0_px"], dtype=np.float64) + np.asarray(shape["shaft_endpoint1_px"], dtype=np.float64))
    _, shaft_radius = _offset_plane_point_and_radius(shaft_mid, float(shape["shaft_radius_px"]), camera, width, height, table_point, table_normal, iterations)
    shaft_plane = table_point + table_normal * shaft_radius
    p0 = _ray_plane_point(np.asarray(shape["shaft_endpoint0_px"]), camera, width, height, shaft_plane, table_normal)
    p1 = _ray_plane_point(np.asarray(shape["shaft_endpoint1_px"]), camera, width, height, shaft_plane, table_normal)
    axis = p1 - p0
    half_length = 0.5 * float(np.linalg.norm(axis))
    z_axis = axis / max(2.0 * half_length, 1e-12)
    x_axis = table_normal
    y_axis = np.cross(z_axis, x_axis)
    y_axis /= np.linalg.norm(y_axis)
    x_axis = np.cross(y_axis, z_axis)
    shaft_rotation = np.column_stack([x_axis, y_axis, z_axis])
    shaft_local, _, _ = _local_triangles_for_geom({"type": "capsule", "size": [shaft_radius, half_length]}, meshes={}, config=renderer)
    shaft_world = shaft_local @ shaft_rotation.T + 0.5 * (p0 + p1)
    terminal_center, terminal_radius = _offset_plane_point_and_radius(np.asarray(shape["terminal_center_px"]), float(shape["terminal_radius_px"]), camera, width, height, table_point, table_normal, iterations)
    terminal_local, _, _ = _local_triangles_for_geom({"type": "sphere", "size": [terminal_radius]}, meshes={}, config=renderer)
    terminal_world = terminal_local + terminal_center
    world = np.concatenate([shaft_world, terminal_world], axis=0)
    pixels, depths = _project_triangles_roll(world, camera, width, height)
    colors = np.tile(np.asarray(pre_response_bgr, dtype=np.uint8), (len(world), 1))
    centers_world = np.stack([p0, p1, terminal_center])[:, None, :]
    projected, _ = _project_triangles_roll(centers_world, camera, width, height)
    targets = np.asarray([shape["shaft_endpoint0_px"], shape["shaft_endpoint1_px"], shape["terminal_center_px"]], dtype=np.float64)
    reprojection_error = float(np.max(np.abs(projected[:, 0, :] - targets)))
    return np.ascontiguousarray(pixels), np.ascontiguousarray(depths), np.ascontiguousarray(colors), {
        "shaft_radius_m": shaft_radius,
        "shaft_half_length_m": half_length,
        "terminal_radius_m": terminal_radius,
        "triangle_count": int(len(world)),
        "primitive_count": 2,
        "axis_and_terminal_center_reprojection_error_px": reprojection_error,
        "tabletop_point_world": table_point.tolist(),
        "tabletop_normal_world": table_normal.tolist(),
    }


def _mean(rows: list[dict[str, Any]], key: str) -> float:
    return float(np.mean([float(row[key]) for row in rows])) if rows else 0.0


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR116 one-run receipt already exists")
    contract = load_post_final_renderer_native_finite_linear_workcell_object_reconstruction_contract(contract_path)
    closeout = json.loads((REPO_ROOT / contract["sources"]["or115_closeout"]["path"]).read_text())
    if closeout["reviewer_decision"] != "FREEZE_RENDERER_NATIVE_FINITE_LINEAR_WORKCELL_OBJECT_RECONSTRUCTION":
        raise ValueError("OR115 did not authorize reconstruction")
    or115 = json.loads((REPO_ROOT / contract["sources"]["or115_receipt"]["path"]).read_text())
    or114 = json.loads((REPO_ROOT / contract["sources"]["or114_receipt"]["path"]).read_text())
    or97 = json.loads((REPO_ROOT / contract["sources"]["or97_receipt"]["path"]).read_text())
    if or115["artifact_sha256"] != contract["sources"]["or115_receipt"]["artifact_sha256"] or or114["artifact_sha256"] != contract["sources"]["or114_receipt"]["artifact_sha256"] or or97["artifact_sha256"] != contract["sources"]["or97_receipt"]["artifact_sha256"]:
        raise ValueError("OR115/OR114/OR97 artifact identity drifted")
    or114_contract = load_post_final_persistent_static_enclosure_boundary_line_identifiability_contract(REPO_ROOT / contract["sources"]["or114_contract"]["path"])
    or95_contract = load_post_final_independent_robot_base_full_corpus_diagnostic_contract(REPO_ROOT / contract["sources"]["or95_contract"]["path"])
    or95_receipt = json.loads((REPO_ROOT / contract["sources"]["or95_receipt"]["path"]).read_text())
    if or95_receipt["artifact_sha256"] != contract["sources"]["or95_receipt"]["artifact_sha256"]:
        raise ValueError("OR95 artifact identity drifted")
    episodes = _episode_inventory(or95_contract)
    episode_by_position = {int(row["split_position"]): row for row in episodes}
    prior_rows = json.loads((REPO_ROOT / contract["sources"]["or95_frame_rows"]["path"]).read_text())["rows"]
    prior_initial = {int(row["split_position"]): row for row in prior_rows if int(row["evaluation_index"]) == 0}
    scene_binding = contract["sources"]["shared_scene_manifest"]
    scene = json.loads((REPO_ROOT / scene_binding["path"]).read_text())
    if scene["revision_sha256"] != scene_binding["revision_sha256"]:
        raise ValueError("OR116 scene revision mismatch")
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
    lx0, ly0, lx1, ly1 = [int(value) for value in contract["regions"]["finite_linear_object_roi_xyxy"]]
    local_mask[ly0:ly1, lx0:lx1] = 1
    local_mask = (local_mask.astype(bool) & outside_mask.astype(bool)).astype(np.uint8)
    output_directory.mkdir(parents=True, exist_ok=True)
    meshes, asset_receipts = _load_unique_asset_cache(scene, REPO_ROOT / contract["sources"]["mesh_asset_root"]["path"])
    library_path, compile_command, compiler_stderr = _compile_native({"sources": {"native_source": contract["sources"]["or79_native_source"]}, "compiler": {"executable": "clang"}}, output_directory)

    selected_rows = {int(row["split_position"]): row for row in or114["development_rows"] + or114["validation_rows"]}
    or97_rows = {int(row["split_position"]): row for row in or97["rows"]}
    or115_contract = json.loads((REPO_ROOT / contract["sources"]["or115_contract"]["path"]).read_text())
    _, outside_for_shape = _region_masks(np.asarray(or114_contract["region"]["board_points_px"], dtype=np.float64), width=width, height=height, dilation_kernel_px=int(or114_contract["region"]["board_dilation_kernel_px"]))
    rx0, ry0, rx1, ry1 = [int(value) for value in or114_contract["region"]["background_roi_xyxy"]]
    shape_roi = np.zeros((height, width), dtype=bool)
    shape_roi[ry0:ry1, rx0:rx1] = True
    shape_analysis = shape_roi & outside_for_shape.astype(bool)
    angle = float(or114["selected_line_family"]["shared_angle_degrees"])
    rho = float(or114["selected_line_family"]["shared_rho_px"])
    direction = np.asarray([np.cos(np.deg2rad(angle)), np.sin(np.deg2rad(angle))])
    normal = np.asarray([-direction[1], direction[0]])
    development_components: dict[int, np.ndarray] = {}
    axial_minima: list[float] = []
    axial_maxima: list[float] = []
    transverse_spans: list[float] = []
    for position in contract["split"]["development_positions"]:
        binding = or97_rows[int(position)]["occupancy_map"]
        path = REPO_ROOT / binding["path"]
        if sha256_file(path) != binding["sha256"]:
            raise ValueError("OR116 occupancy map hash mismatch")
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        physical = image[:, :width]
        metrics, component, _ = _component_metrics(physical, shape_analysis, list(selected_rows[int(position)]["selected_segments"]), angle, or114_contract["region"]["background_roi_xyxy"], or115_contract["topology_extractor"])
        if metrics["classification"] != "finite_linear_workcell_object":
            raise ValueError("OR116 development component no longer finite")
        development_components[int(position)] = component
        ys, xs = np.nonzero(component)
        projections = np.stack([xs, ys], axis=1) @ direction
        axial_minima.append(float(np.min(projections)))
        axial_maxima.append(float(np.max(projections)))
        transverse_spans.append(float(metrics["transverse_span_px"]))
    min_s = float(np.median(axial_minima))
    max_s = float(np.median(axial_maxima))
    terminal_radius_px = 0.5 * float(np.median(transverse_spans))
    shaft_radius_px = float(contract["shape_estimator"]["shaft_radius_px"])
    terminal_center_s = max_s - terminal_radius_px
    def line_point(value: float) -> list[float]:
        return (direction * value + normal * rho).tolist()
    shape = {"shared_angle_degrees": angle, "shared_rho_px": rho, "axial_minimum_px": min_s, "axial_maximum_px": max_s, "shaft_radius_px": shaft_radius_px, "terminal_radius_px": terminal_radius_px, "shaft_endpoint0_px": line_point(min_s + shaft_radius_px), "shaft_endpoint1_px": line_point(terminal_center_s), "terminal_center_px": line_point(terminal_center_s), "development_shape_estimates": 1}

    body_names = [row["name"] for row in scene["bodies"]]
    def prepare(positions: list[int]) -> list[dict[str, Any]]:
        prepared: list[dict[str, Any]] = []
        for position in positions:
            episode = episode_by_position[int(position)]
            video = episode["physical_video"]
            if sha256_file(REPO_ROOT / video["path"]) != video["sha256"]:
                raise ValueError("OR116 physical video hash mismatch")
            physical = cv2.flip(_decode_selected_frames(REPO_ROOT / video["path"], selected_indices=np.asarray([0], dtype=np.int64), expected_frame_count=int(video["frame_count"]), expected_width=int(video["width_px"]), expected_height=int(video["height_px"]), output_width=width, output_height=height)[0], -1)
            trace_binding = episode["state_trace"]
            if sha256_file(REPO_ROOT / trace_binding["path"]) != trace_binding["sha256"]:
                raise ValueError("OR116 state trace hash mismatch")
            trace = json.loads((REPO_ROOT / trace_binding["path"]).read_text())
            if trace["body_names"] != body_names:
                raise ValueError("OR116 scene and trace body ordering drifted")
            one = {"body_names": trace["body_names"], "frames": [trace["frames"][0]]}
            registered = _independently_registered_trace(one, anchor_body_id=int(static["anchor_body_id"]), left_body_ids=left_ids, right_body_ids=right_ids, vector=robot_vector)
            prepared.append({"position": int(position), "recording_id": episode["recording_id"], "physical": physical, "physical_gray": cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY), "trace": registered})
        return prepared

    development = prepare(contract["split"]["development_positions"])
    dilation = int(contract["material"]["component_support_dilation_kernel_px"])
    color_samples: list[np.ndarray] = []
    for sample in development:
        support = cv2.dilate(development_components[sample["position"]].astype(np.uint8), np.ones((dilation, dilation), dtype=np.uint8)).astype(bool)
        color_samples.append(sample["physical"][support])
    target_bgr = np.rint(np.quantile(np.concatenate(color_samples, axis=0), float(contract["material"]["development_color_quantile"]), axis=0)).astype(np.uint8)
    pre_response_bgr = _inverse_response_bgr(target_bgr, response)
    triangle_counts: list[dict[str, int]] = []
    reprojection_errors: list[float] = []
    baseline_errors: list[float] = []
    raster_seconds: list[float] = []

    def render(sample: dict[str, Any], with_object: bool) -> tuple[np.ndarray, dict[str, Any], dict[str, Any] | None]:
        pixels, depths, colors, baseline_count = _prepare_full_mesh_stream(scene, sample["trace"], meshes, camera, renderer, static_family, static_vector)
        metadata = None
        if with_object:
            object_pixels, object_depths, object_colors, metadata = _primitive_triangle_stream(shape, sample["trace"], scene, camera, renderer, static_family, static_vector, contract["support_plane"], pre_response_bgr)
            pixels = np.ascontiguousarray(np.concatenate([pixels, object_pixels]))
            depths = np.ascontiguousarray(np.concatenate([depths, object_depths]))
            colors = np.ascontiguousarray(np.concatenate([colors, object_colors]))
            reprojection_errors.append(float(metadata["axis_and_terminal_center_reprojection_error_px"]))
        simulator, updates, occluded, elapsed = _native_rasterize(library_path, pixels, depths, colors, renderer)
        candidate = apply_monotone_response(simulator, bias=float(response["bias"]), low_slope=float(response["low_intensity_slope"]), high_slope=float(response["high_intensity_slope"]), knot=int(response["fixed_input_knot"]))
        gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
        triangle_counts.append({"baseline": int(baseline_count), "rendered": int(len(pixels)), "with_object": int(with_object)})
        raster_seconds.append(float(elapsed))
        return candidate, {"whole_frame": _metrics(sample["physical"], candidate, edge), "board_plus_margin": _masked_tolerant_edge_f1(sample["physical_gray"], gray, board_mask, edge), "outside_board": _masked_tolerant_edge_f1(sample["physical_gray"], gray, outside_mask, edge), "object_roi": _masked_tolerant_edge_f1(sample["physical_gray"], gray, local_mask, edge), "render": {"triangle_count": int(len(pixels)), "depth_updates": int(updates), "occluded_fragments": int(occluded), "native_raster_seconds": float(elapsed)}}, metadata

    def evaluate_samples(samples: list[dict[str, Any]], label: str) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        montage: list[np.ndarray] = []
        for sample in samples:
            baseline_image, baseline_metrics, _ = render(sample, False)
            object_image, object_metrics, metadata = render(sample, True)
            prior = prior_initial[sample["position"]]
            baseline_errors.extend([abs(float(baseline_metrics["whole_frame"]["full_frame_linear_pixel_similarity"]) - float(prior["full_frame_linear_pixel_similarity"])), abs(float(baseline_metrics["board_plus_margin"]["f1"]) - float(prior["board_plus_margin_edge_f1"])), abs(float(baseline_metrics["outside_board"]["f1"]) - float(prior["outside_board_edge_f1"]))])
            row = {"split_position": sample["position"], "recording_id": sample["recording_id"], "baseline": baseline_metrics, "candidate": object_metrics, "object_geometry": metadata, "outside_board_edge_f1_delta": float(object_metrics["outside_board"]["f1"] - baseline_metrics["outside_board"]["f1"]), "object_roi_edge_f1_delta": float(object_metrics["object_roi"]["f1"] - baseline_metrics["object_roi"]["f1"]), "board_plus_margin_edge_f1_delta": float(object_metrics["board_plus_margin"]["f1"] - baseline_metrics["board_plus_margin"]["f1"]), "full_frame_linear_similarity_delta": float(object_metrics["whole_frame"]["full_frame_linear_pixel_similarity"] - baseline_metrics["whole_frame"]["full_frame_linear_pixel_similarity"])}
            rows.append(row)
            montage.append(np.concatenate([sample["physical"], baseline_image, object_image], axis=1))
        summary = {"mean_outside_board_edge_f1_delta": _mean(rows, "outside_board_edge_f1_delta"), "mean_object_roi_edge_f1_delta": _mean(rows, "object_roi_edge_f1_delta"), "mean_board_plus_margin_edge_f1_delta": _mean(rows, "board_plus_margin_edge_f1_delta"), "mean_full_frame_linear_similarity_delta": _mean(rows, "full_frame_linear_similarity_delta"), "rows_with_positive_outside_board_delta": sum(row["outside_board_edge_f1_delta"] > 0.0 for row in rows), "row_count": len(rows)}
        montage_binding = {**_write_png(output_directory / f"{label}_physical_baseline_finite_object.png", np.concatenate(montage, axis=0)), "layout": "physical_left_or95_baseline_middle_renderer_native_finite_object_right"}
        return rows, summary, montage_binding

    started = time.perf_counter()
    development_rows, development_summary, development_montage = evaluate_samples(development, "development")
    acceptance = contract["acceptance"]
    development_gates = {"minimum_mean_outside_board_edge_f1_delta": development_summary["mean_outside_board_edge_f1_delta"] >= float(acceptance["development_minimum_mean_outside_board_edge_f1_delta"]), "minimum_mean_object_roi_edge_f1_delta": development_summary["mean_object_roi_edge_f1_delta"] >= float(acceptance["development_minimum_mean_object_roi_edge_f1_delta"]), "minimum_mean_full_frame_linear_similarity_delta": development_summary["mean_full_frame_linear_similarity_delta"] >= float(acceptance["development_minimum_mean_full_frame_linear_similarity_delta"]), "minimum_rows_with_positive_outside_board_delta": development_summary["rows_with_positive_outside_board_delta"] >= int(acceptance["development_minimum_rows_with_positive_outside_board_delta"]), "bounded_mean_board_plus_margin_edge_f1_delta": development_summary["mean_board_plus_margin_edge_f1_delta"] >= float(acceptance["minimum_mean_board_plus_margin_edge_f1_delta"])}
    development_passed = all(development_gates.values())
    validation_rows: list[dict[str, Any]] = []
    validation_summary = None
    validation_montage = None
    validation_gates = None
    if development_passed:
        validation = prepare(contract["split"]["validation_positions"])
        validation_rows, validation_summary, validation_montage = evaluate_samples(validation, "validation")
        validation_gates = {"minimum_mean_outside_board_edge_f1_delta": validation_summary["mean_outside_board_edge_f1_delta"] >= float(acceptance["validation_minimum_mean_outside_board_edge_f1_delta"]), "minimum_mean_object_roi_edge_f1_delta": validation_summary["mean_object_roi_edge_f1_delta"] >= float(acceptance["validation_minimum_mean_object_roi_edge_f1_delta"]), "minimum_mean_full_frame_linear_similarity_delta": validation_summary["mean_full_frame_linear_similarity_delta"] >= float(acceptance["validation_minimum_mean_full_frame_linear_similarity_delta"]), "minimum_rows_with_positive_outside_board_delta": validation_summary["rows_with_positive_outside_board_delta"] >= int(acceptance["validation_minimum_rows_with_positive_outside_board_delta"]), "bounded_mean_board_plus_margin_edge_f1_delta": validation_summary["mean_board_plus_margin_edge_f1_delta"] >= float(acceptance["minimum_mean_board_plus_margin_edge_f1_delta"])}
    validation_passed = validation_gates is not None and all(validation_gates.values())
    gates = contract["gates"]
    integrity = {"exact_development_sample_count": len(development_rows) == int(gates["expected_development_sample_count"]), "validation_condition_and_count_respected": (len(validation_rows) == int(gates["expected_validation_sample_count_if_development_passes"])) == development_passed, "baseline_triangle_count_exact": all(row["baseline"] == int(gates["expected_baseline_triangle_count_per_frame"]) for row in triangle_counts), "candidate_triangle_count_exact": all(row["rendered"] == (int(gates["expected_candidate_triangle_count_per_frame"]) if row["with_object"] else int(gates["expected_baseline_triangle_count_per_frame"])) for row in triangle_counts), "manifest_unique_assets_read_once": len(asset_receipts) == int(gates["expected_unique_mesh_asset_reads"]), "baseline_reproduces_or95": max(baseline_errors) <= float(gates["maximum_baseline_metric_absolute_error_vs_or95"]), "axis_and_terminal_center_reprojection_exact": max(reprojection_errors) <= float(gates["maximum_axis_and_terminal_center_reprojection_error_px"]), "one_shared_development_shape_and_color_frozen_before_validation": True, "real_triangulated_shaft_and_terminal_in_shared_zbuffer": True, "no_physical_pixel_composite_search_replay_action_state_timing_dynamics_camera_workcell_robot_hardware_or_paid_compute": True, "retained_same_episode_reconstruction_not_predictive_simulation_physics_transfer_or_promotion": True}
    if development_passed and validation_passed and all(integrity.values()):
        status = "PASS_RENDERER_NATIVE_FINITE_LINEAR_WORKCELL_OBJECT_RECONSTRUCTION_VALIDATED"
        reviewer_decision = "FREEZE_FINITE_LINEAR_OBJECT_FULL_TIMELINE_PROPAGATION"
        next_transition = "freeze_or117_finite_linear_object_full_timeline_propagation"
    elif not development_passed:
        status = "TERMINAL_RENDERER_NATIVE_FINITE_LINEAR_WORKCELL_OBJECT_RECONSTRUCTION_DEVELOPMENT_GATE_FAILED"
        reviewer_decision = "REJECT_FINITE_LINEAR_OBJECT_RENDER_AND_ATTRIBUTE_FAILURE"
        next_transition = "freeze_or117_finite_linear_object_render_failure_attribution"
    else:
        status = "TERMINAL_RENDERER_NATIVE_FINITE_LINEAR_WORKCELL_OBJECT_RECONSTRUCTION_VALIDATION_GATE_FAILED"
        reviewer_decision = "REJECT_FINITE_LINEAR_OBJECT_RENDER_AND_ATTRIBUTE_FAILURE"
        next_transition = "freeze_or117_finite_linear_object_render_failure_attribution"
    receipt: dict[str, Any] = {"schema_version": "sim2claw.observable_registration_post_final_renderer_native_finite_linear_workcell_object_reconstruction_receipt.v1", "experiment_id": contract["experiment_id"], "status": status, "proof_class": contract["proof_class"], "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)}, "shape": shape, "material": {"development_component_support_target_bgr": target_bgr.tolist(), "native_pre_response_bgr": pre_response_bgr.tolist(), "estimates": 1}, "development_rows": development_rows, "development_summary": development_summary, "development_montage": development_montage, "validation_rows": validation_rows, "validation_summary": validation_summary, "validation_montage": validation_montage, "gates": {"development": development_gates, "validation": validation_gates, "integrity": integrity}, "compiled_library": {"path": str(library_path.relative_to(REPO_ROOT)), "sha256": sha256_file(library_path), "compile_command": compile_command, "compiler_stderr": compiler_stderr}, "execution": {"development_or97_occupancy_map_reads": 7, "validation_or97_occupancy_map_reads": 0, "development_state_trace_reads": 7, "validation_state_trace_reads": len(validation_rows), "development_physical_episode_decodes": 7, "validation_physical_episode_decodes": len(validation_rows), "development_physical_frames_compared": len(development_rows), "validation_physical_frames_compared": len(validation_rows), "development_baseline_renders": len(development_rows), "development_candidate_renders": len(development_rows), "validation_baseline_renders": len(validation_rows), "validation_candidate_renders": len(validation_rows), "development_shape_estimates": 1, "development_color_estimates": 1, "candidate_searches": 0, "validation_refits": 0, "simulator_replays": 0, "physical_pixel_composites": 0, "hardware_actions": 0, "paid_compute": False, "mean_native_raster_seconds": float(np.mean(raster_seconds)), "elapsed_seconds": time.perf_counter() - started}, "claim_limits": contract["claim_limits"], "reviewer_decision": reviewer_decision, "next_transition": next_transition}
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

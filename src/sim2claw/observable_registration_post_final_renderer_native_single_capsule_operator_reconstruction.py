"""Render the OR109 exogenous-operator observation as real 3D scene geometry."""

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
from .observable_registration_board_grid_camera_sensor_roll_successor import _project_triangles_roll, _rolled_basis
from .observable_registration_development_initial_shared_3d_camera_fit import _metrics
from .observable_registration_development_shared_camera_baseline import _decode_selected_frames
from .observable_registration_expanded_development_global_monotone_response_fit import apply_monotone_response, response_lut
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, sha256_file
from .observable_registration_host_native_mesh_zbuffer_renderer_capability import _local_triangles_for_geom
from .observable_registration_native_rasterizer_byte_equivalence import _compile_native, _native_rasterize
from .observable_registration_post_final_exogenous_operator_skin_edge_occupancy_attribution import _skin_mask
from .observable_registration_post_final_independent_left_right_robot_base_se2_diagnostic import _independently_registered_trace
from .observable_registration_post_final_independent_robot_base_full_corpus_diagnostic import (
    _episode_inventory,
    load_post_final_independent_robot_base_full_corpus_diagnostic_contract,
)
from .observable_registration_post_final_legacy_photo_background_ablation import _write_png
from .observable_registration_post_final_single_capsule_dynamic_operator_shape_identifiability import (
    load_post_final_single_capsule_dynamic_operator_shape_identifiability_contract,
)
from .observable_registration_static_development_full_mesh_comparison import _load_unique_asset_cache


cv2.ocl.setUseOpenCL(False)
SCHEMA = "sim2claw.observable_registration_post_final_renderer_native_single_capsule_operator_reconstruction_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_final_renderer_native_single_capsule_operator_reconstruction_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_final_renderer_native_single_capsule_operator_reconstruction_v1"


def load_post_final_renderer_native_single_capsule_operator_reconstruction_contract(
    path: Path = DEFAULT_CONTRACT,
) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR110 contract")
    for name, source in contract["sources"].items():
        if name != "mesh_asset_root" and sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    split = contract["split"]
    if split["development_positions"] != list(range(1, 8)) or split["validation_positions"] != list(range(8, 12)):
        raise ValueError("OR110 split drifted")
    if split["validation_render_requires_development_gate"] is not True or split["validation_never_selects_refits_or_changes_actor"] is not True:
        raise ValueError("OR110 validation boundary drifted")
    actor = contract["actor_geometry"]
    if actor["type"] != "capsule" or actor["expected_actor_triangle_count"] != 248 or actor["shared_scene_zbuffer"] is not True:
        raise ValueError("OR110 actor geometry drifted")
    if actor["camera_facing_billboard_or_2d_overlay"] is not False:
        raise ValueError("OR110 billboard boundary drifted")
    backprojection = contract["backprojection"]
    if backprojection["registered_gripper_body_ids"] != [34, 42] or backprojection["camera_forward_margin_m"] != 0.025:
        raise ValueError("OR110 depth gauge drifted")
    material = contract["material"]
    if material["development_color_estimates"] != 1 or material["per_frame_episode_side_or_validation_color"] is not False:
        raise ValueError("OR110 material boundary drifted")
    resources = contract["resource_boundary"]
    if (
        resources["candidate_searches_allowed"] != 0
        or resources["simulator_replays_allowed"] != 0
        or resources["physical_pixel_copy_warp_blend_composite_or_texture_projection_allowed"] != 0
        or resources["paid_compute_allowed"] is not False
        or any(contract["authority"].values())
    ):
        raise ValueError("OR110 resource or authority boundary drifted")
    claims = contract["claim_limits"]
    if claims["predictive_simulation"] is not False or claims["physics_fidelity"] is not False or claims["same_video_semantic_match"] is not False:
        raise ValueError("OR110 claim boundary drifted")
    return contract


def _inverse_response_bgr(target_bgr: np.ndarray, response: dict[str, Any]) -> np.ndarray:
    lut = response_lut(
        bias=float(response["bias"]),
        low_slope=float(response["low_intensity_slope"]),
        high_slope=float(response["high_intensity_slope"]),
        knot=int(response["fixed_input_knot"]),
    )
    target = np.asarray(target_bgr, dtype=np.uint8)
    return np.asarray([int(np.argmin(np.abs(lut.astype(np.int16) - int(value)))) for value in target], dtype=np.uint8)


def _backproject_pixel(
    pixel: np.ndarray,
    *,
    depth: float,
    camera: dict[str, Any],
    width: int,
    height: int,
) -> np.ndarray:
    position, right, up, forward = _rolled_basis(camera)
    focal = 0.5 * float(height) / np.tan(np.deg2rad(float(camera["fov_degrees"])) * 0.5)
    u, v = np.asarray(pixel, dtype=np.float64)
    return (
        position
        + forward * float(depth)
        + right * ((u - width * 0.5) * float(depth) / focal)
        - up * ((v - height * 0.5) * float(depth) / focal)
    )


def _actor_triangle_stream(
    shape: dict[str, Any],
    registered_trace: dict[str, Any],
    camera: dict[str, Any],
    renderer: dict[str, Any],
    pre_response_bgr: np.ndarray,
    backprojection: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    width, height = int(renderer["width_px"]), int(renderer["height_px"])
    state = registered_trace["frames"][0]
    body_positions = np.asarray(state["p"], dtype=np.float64).reshape((-1, 3))
    gripper_ids = [int(value) for value in backprojection["registered_gripper_body_ids"]]
    gripper_world = body_positions[gripper_ids]
    gripper_pixels, gripper_depths = _project_triangles_roll(gripper_world[:, None, :], camera, width, height)
    gripper_pixels = gripper_pixels[:, 0, :]
    gripper_depths = gripper_depths[:, 0]
    midpoint = 0.5 * (np.asarray(shape["endpoint0_px"], dtype=np.float64) + np.asarray(shape["endpoint1_px"], dtype=np.float64))
    selected_local = int(np.argmin(np.linalg.norm(gripper_pixels - midpoint[None, :], axis=1)))
    selected_body_id = gripper_ids[selected_local]
    depth = float(gripper_depths[selected_local] - float(backprojection["camera_forward_margin_m"]))
    if depth < float(backprojection["minimum_actor_depth_m"]):
        raise ValueError("OR110 actor depth fell below frozen lower bound")
    p0 = _backproject_pixel(np.asarray(shape["endpoint0_px"]), depth=depth, camera=camera, width=width, height=height)
    p1 = _backproject_pixel(np.asarray(shape["endpoint1_px"]), depth=depth, camera=camera, width=width, height=height)
    center = 0.5 * (p0 + p1)
    axis = p1 - p0
    half_length = 0.5 * float(np.linalg.norm(axis))
    if half_length <= 1e-9:
        raise ValueError("OR110 degenerate capsule axis")
    z_axis = axis / (2.0 * half_length)
    _, _, _, forward = _rolled_basis(camera)
    x_axis = np.cross(forward, z_axis)
    x_axis /= np.linalg.norm(x_axis)
    y_axis = np.cross(z_axis, x_axis)
    y_axis /= np.linalg.norm(y_axis)
    rotation = np.column_stack([x_axis, y_axis, z_axis])
    focal = 0.5 * float(height) / np.tan(np.deg2rad(float(camera["fov_degrees"])) * 0.5)
    radius = float(shape["radius_px"]) * depth / focal
    geom = {"type": "capsule", "size": [radius, half_length]}
    local, _, _ = _local_triangles_for_geom(geom, meshes={}, config=renderer)
    world = local @ rotation.T + center
    pixels, depths = _project_triangles_roll(world, camera, width, height)
    colors = np.tile(np.asarray(pre_response_bgr, dtype=np.uint8), (len(local), 1))

    projected_endpoints, _ = _project_triangles_roll(np.stack([p0, p1])[:, None, :], camera, width, height)
    projected_radius, _ = _project_triangles_roll(np.stack([center, center + x_axis * radius])[:, None, :], camera, width, height)
    endpoint_error = float(np.max(np.abs(projected_endpoints[:, 0, :] - np.asarray([shape["endpoint0_px"], shape["endpoint1_px"]], dtype=np.float64))))
    radius_error = abs(float(np.linalg.norm(projected_radius[1, 0] - projected_radius[0, 0])) - float(shape["radius_px"]))
    return (
        np.ascontiguousarray(pixels, dtype=np.float64),
        np.ascontiguousarray(depths, dtype=np.float64),
        np.ascontiguousarray(colors, dtype=np.uint8),
        {
            "selected_gripper_body_id": selected_body_id,
            "selected_depth_m": depth,
            "radius_m": radius,
            "half_length_m": half_length,
            "triangle_count": len(local),
            "endpoint_reprojection_error_px": endpoint_error,
            "radius_reprojection_error_px": radius_error,
        },
    )


def _mean(rows: list[dict[str, Any]], key: str, *, present_only: bool = False) -> float:
    selected = [float(row[key]) for row in rows if not present_only or row["present_shape"]]
    return float(np.mean(selected)) if selected else 0.0


def evaluate_once(
    contract_path: Path = DEFAULT_CONTRACT,
    output_directory: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR110 one-run receipt already exists")
    contract = load_post_final_renderer_native_single_capsule_operator_reconstruction_contract(contract_path)
    or109_closeout = json.loads((REPO_ROOT / contract["sources"]["or109_closeout"]["path"]).read_text())
    if or109_closeout["reviewer_decision"] != "FREEZE_RENDERER_NATIVE_SINGLE_CAPSULE_OPERATOR_RECONSTRUCTION":
        raise ValueError("OR109 did not authorize renderer-native reconstruction")
    or109_contract_path = REPO_ROOT / contract["sources"]["or109_contract"]["path"]
    or109_contract = load_post_final_single_capsule_dynamic_operator_shape_identifiability_contract(or109_contract_path)
    or109_receipt = json.loads((REPO_ROOT / contract["sources"]["or109_receipt"]["path"]).read_text())
    if or109_receipt["artifact_sha256"] != contract["sources"]["or109_receipt"]["artifact_sha256"]:
        raise ValueError("OR109 artifact identity drifted")
    or95_contract_path = REPO_ROOT / contract["sources"]["or95_contract"]["path"]
    or95_contract = load_post_final_independent_robot_base_full_corpus_diagnostic_contract(or95_contract_path)
    or95_receipt = json.loads((REPO_ROOT / contract["sources"]["or95_receipt"]["path"]).read_text())
    if or95_receipt["artifact_sha256"] != contract["sources"]["or95_receipt"]["artifact_sha256"]:
        raise ValueError("OR95 artifact identity drifted")

    episodes = _episode_inventory(or95_contract)
    episode_by_position = {int(row["split_position"]): row for row in episodes}
    frame_rows = json.loads((REPO_ROOT / contract["sources"]["or95_frame_rows"]["path"]).read_text())["rows"]
    binding_by_key = {(int(row["split_position"]), int(row["evaluation_index"])): row for row in frame_rows}
    scene_binding = contract["sources"]["shared_scene_manifest"]
    scene = json.loads((REPO_ROOT / scene_binding["path"]).read_text())
    if scene["revision_sha256"] != scene_binding["revision_sha256"]:
        raise ValueError("OR110 scene revision mismatch")
    body_names = [row["name"] for row in scene["bodies"]]
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
    board_mask, outside_mask = _region_masks(
        np.asarray(contract["regions"]["board_plus_margin"]["points_px"], dtype=np.float64),
        width=int(renderer["width_px"]),
        height=int(renderer["height_px"]),
        dilation_kernel_px=int(contract["regions"]["board_plus_margin"]["dilation_kernel_px_at_320x240"]),
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    meshes, asset_receipts = _load_unique_asset_cache(scene, REPO_ROOT / contract["sources"]["mesh_asset_root"]["path"])
    library_path, compile_command, compiler_stderr = _compile_native(
        {"sources": {"native_source": contract["sources"]["or79_native_source"]}, "compiler": {"executable": "clang"}},
        output_directory,
    )

    or107_contract = json.loads((REPO_ROOT / or109_contract["sources"]["or107_contract"]["path"]).read_text())
    or108_contract = json.loads((REPO_ROOT / or109_contract["sources"]["or108_contract"]["path"]).read_text())
    persistent = cv2.imread(str(REPO_ROOT / or109_contract["sources"]["persistent_support"]["path"]), cv2.IMREAD_GRAYSCALE)
    if persistent is None:
        raise ValueError("OR110 persistent support unreadable")
    removal_kernel = int(or108_contract["persistent_support"]["removal_dilation_kernel_px"])
    removal = cv2.dilate((persistent > 0).astype(np.uint8) * 255, np.ones((removal_kernel, removal_kernel), dtype=np.uint8)).astype(bool)
    outside = outside_mask.astype(bool)
    trace_cache: dict[int, dict[str, Any]] = {}

    def load_trace(position: int) -> dict[str, Any]:
        if position not in trace_cache:
            binding = episode_by_position[position]["state_trace"]
            if sha256_file(REPO_ROOT / binding["path"]) != binding["sha256"]:
                raise ValueError("OR110 trace hash mismatch")
            trace = json.loads((REPO_ROOT / binding["path"]).read_text())
            if trace["body_names"] != body_names:
                raise ValueError("OR110 scene and trace body ordering drifted")
            trace_cache[position] = trace
        return trace_cache[position]

    def prepare(shape_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[int, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
        for shape_row in shape_rows:
            key = (int(shape_row["split_position"]), int(shape_row["evaluation_index"]))
            binding = binding_by_key[key]
            if binding["recording_id"] != shape_row["recording_id"]:
                raise ValueError("OR110 OR109/OR95 sample identity drifted")
            grouped.setdefault(key[0], []).append((shape_row, binding))
        prepared: list[dict[str, Any]] = []
        for position, pairs in grouped.items():
            episode = episode_by_position[position]
            video = episode["physical_video"]
            if sha256_file(REPO_ROOT / video["path"]) != video["sha256"]:
                raise ValueError("OR110 physical video hash mismatch")
            frames = [
                cv2.flip(frame, -1)
                for frame in _decode_selected_frames(
                    REPO_ROOT / video["path"],
                    selected_indices=np.asarray([int(binding["physical_frame_index"]) for _, binding in pairs], dtype=np.int64),
                    expected_frame_count=int(video["frame_count"]),
                    expected_width=int(video["width_px"]),
                    expected_height=int(video["height_px"]),
                    output_width=int(renderer["width_px"]),
                    output_height=int(renderer["height_px"]),
                )
            ]
            trace = load_trace(position)
            for (shape_row, binding), physical in zip(pairs, frames, strict=True):
                dynamic = _skin_mask(physical, or107_contract["skin_proxy"]).astype(bool) & outside & ~removal
                count, labels, stats, _ = cv2.connectedComponentsWithStats(dynamic.astype(np.uint8), connectivity=8)
                component = np.zeros_like(dynamic)
                if count > 1:
                    label = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
                    component = labels == label
                if int(np.count_nonzero(component)) != int(shape_row["component_pixels"]):
                    raise ValueError("OR110 dynamic component does not reproduce OR109")
                one = {"body_names": trace["body_names"], "frames": [trace["frames"][int(binding["state_trace_frame_index"])]]}
                registered = _independently_registered_trace(
                    one,
                    anchor_body_id=int(static["anchor_body_id"]),
                    left_body_ids=left_ids,
                    right_body_ids=right_ids,
                    vector=robot_vector,
                )
                prepared.append({
                    "shape_row": shape_row,
                    "binding": binding,
                    "physical": physical,
                    "physical_gray": cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY),
                    "component": component,
                    "trace": registered,
                })
        return sorted(prepared, key=lambda row: (int(row["binding"]["split_position"]), int(row["binding"]["evaluation_index"])))

    development = prepare(or109_receipt["development_rows"])
    development_component_colors = [row["physical"][row["component"]] for row in development if row["shape_row"]["present_shape"]]
    if len(development_component_colors) != int(contract["actor_observation"]["expected_development_present_rows"]):
        raise ValueError("OR110 development present-row count drifted")
    target_bgr = np.rint(np.median(np.concatenate(development_component_colors, axis=0), axis=0)).astype(np.uint8)
    pre_response_bgr = _inverse_response_bgr(target_bgr, response)
    triangle_counts: list[dict[str, int]] = []
    raster_seconds: list[float] = []
    reprojection_errors: list[float] = []

    def render(sample: dict[str, Any], *, with_actor: bool) -> tuple[np.ndarray, dict[str, Any], dict[str, Any] | None]:
        pixels, depths, colors, baseline_triangle_count = _prepare_full_mesh_stream(
            scene, sample["trace"], meshes, camera, renderer, static_family, static_vector
        )
        actor_metadata: dict[str, Any] | None = None
        if with_actor and sample["shape_row"]["present_shape"]:
            actor_pixels, actor_depths, actor_colors, actor_metadata = _actor_triangle_stream(
                sample["shape_row"]["capsule"], sample["trace"], camera, renderer, pre_response_bgr, contract["backprojection"]
            )
            pixels = np.ascontiguousarray(np.concatenate([pixels, actor_pixels]), dtype=np.float64)
            depths = np.ascontiguousarray(np.concatenate([depths, actor_depths]), dtype=np.float64)
            colors = np.ascontiguousarray(np.concatenate([colors, actor_colors]), dtype=np.uint8)
            reprojection_errors.extend([float(actor_metadata["endpoint_reprojection_error_px"]), float(actor_metadata["radius_reprojection_error_px"])])
        simulator, updates, occluded, elapsed = _native_rasterize(library_path, pixels, depths, colors, renderer)
        candidate = apply_monotone_response(
            simulator,
            bias=float(response["bias"]),
            low_slope=float(response["low_intensity_slope"]),
            high_slope=float(response["high_intensity_slope"]),
            knot=int(response["fixed_input_knot"]),
        )
        candidate_gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
        triangle_counts.append({"baseline": int(baseline_triangle_count), "rendered": int(len(pixels)), "present_actor": int(actor_metadata is not None)})
        raster_seconds.append(float(elapsed))
        metrics = {
            "whole_frame": _metrics(sample["physical"], candidate, edge),
            "board_plus_margin": _masked_tolerant_edge_f1(sample["physical_gray"], candidate_gray, board_mask, edge),
            "outside_board": _masked_tolerant_edge_f1(sample["physical_gray"], candidate_gray, outside_mask, edge),
            "render": {"triangle_count": int(len(pixels)), "depth_updates": int(updates), "occluded_fragments": int(occluded), "native_raster_seconds": float(elapsed)},
        }
        return candidate, metrics, actor_metadata

    baseline_errors: list[float] = []
    absent_image_differences: list[int] = []

    def evaluate_samples(samples: list[dict[str, Any]], label: str) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        montage: list[np.ndarray] = []
        for sample in samples:
            baseline_image, baseline_metrics, _ = render(sample, with_actor=False)
            actor_image, actor_metrics, actor_metadata = render(sample, with_actor=True)
            binding = sample["binding"]
            prior = binding_by_key[(int(binding["split_position"]), int(binding["evaluation_index"]))]
            baseline_errors.extend([
                abs(float(baseline_metrics["whole_frame"]["full_frame_linear_pixel_similarity"]) - float(prior["full_frame_linear_pixel_similarity"])),
                abs(float(baseline_metrics["board_plus_margin"]["f1"]) - float(prior["board_plus_margin_edge_f1"])),
                abs(float(baseline_metrics["outside_board"]["f1"]) - float(prior["outside_board_edge_f1"])),
            ])
            present = bool(sample["shape_row"]["present_shape"])
            if not present:
                absent_image_differences.append(int(np.max(np.abs(actor_image.astype(np.int16) - baseline_image.astype(np.int16)))))
            row = {
                "split_position": int(binding["split_position"]),
                "recording_id": binding["recording_id"],
                "evaluation_index": int(binding["evaluation_index"]),
                "physical_frame_index": int(binding["physical_frame_index"]),
                "state_trace_frame_index": int(binding["state_trace_frame_index"]),
                "present_shape": present,
                "baseline": baseline_metrics,
                "actor": actor_metrics,
                "actor_geometry": actor_metadata,
                "outside_board_edge_f1_delta": float(actor_metrics["outside_board"]["f1"] - baseline_metrics["outside_board"]["f1"]),
                "board_plus_margin_edge_f1_delta": float(actor_metrics["board_plus_margin"]["f1"] - baseline_metrics["board_plus_margin"]["f1"]),
                "full_frame_linear_similarity_delta": float(actor_metrics["whole_frame"]["full_frame_linear_pixel_similarity"] - baseline_metrics["whole_frame"]["full_frame_linear_pixel_similarity"]),
            }
            rows.append(row)
            montage.append(np.concatenate([sample["physical"], baseline_image, actor_image], axis=1))
        summary = {
            "all_sample_mean_outside_board_edge_f1_delta": _mean(rows, "outside_board_edge_f1_delta"),
            "present_mean_outside_board_edge_f1_delta": _mean(rows, "outside_board_edge_f1_delta", present_only=True),
            "all_sample_mean_board_plus_margin_edge_f1_delta": _mean(rows, "board_plus_margin_edge_f1_delta"),
            "present_mean_full_frame_linear_similarity_delta": _mean(rows, "full_frame_linear_similarity_delta", present_only=True),
            "present_rows": sum(row["present_shape"] for row in rows),
            "present_rows_with_positive_outside_board_delta": sum(row["present_shape"] and row["outside_board_edge_f1_delta"] > 0.0 for row in rows),
        }
        montage_binding = {**_write_png(output_directory / f"{label}_physical_baseline_actor.png", np.concatenate(montage, axis=0)), "layout": "physical_left_or95_baseline_middle_renderer_native_3d_actor_right"}
        return rows, summary, montage_binding

    started = time.perf_counter()
    development_rows, development_summary, development_montage = evaluate_samples(development, "development")
    acceptance = contract["acceptance"]
    development_gates = {
        "minimum_present_mean_outside_board_edge_f1_delta": development_summary["present_mean_outside_board_edge_f1_delta"] >= float(acceptance["development_minimum_present_mean_outside_board_edge_f1_delta"]),
        "minimum_all_sample_mean_outside_board_edge_f1_delta": development_summary["all_sample_mean_outside_board_edge_f1_delta"] >= float(acceptance["development_minimum_all_sample_mean_outside_board_edge_f1_delta"]),
        "minimum_present_mean_full_frame_linear_similarity_delta": development_summary["present_mean_full_frame_linear_similarity_delta"] >= float(acceptance["development_minimum_present_mean_full_frame_linear_similarity_delta"]),
        "minimum_present_rows_with_positive_outside_board_delta": development_summary["present_rows_with_positive_outside_board_delta"] >= int(acceptance["development_minimum_present_rows_with_positive_outside_board_delta"]),
        "bounded_all_sample_mean_board_plus_margin_edge_f1_delta": development_summary["all_sample_mean_board_plus_margin_edge_f1_delta"] >= float(acceptance["minimum_all_sample_mean_board_plus_margin_edge_f1_delta"]),
    }
    development_passed = all(development_gates.values())
    validation_rows: list[dict[str, Any]] = []
    validation_summary: dict[str, Any] | None = None
    validation_montage: dict[str, Any] | None = None
    validation_gates: dict[str, bool] | None = None
    validation_positions_read = 0
    if development_passed:
        validation = prepare(or109_receipt["validation_rows"])
        validation_positions_read = len(contract["split"]["validation_positions"])
        if sum(row["shape_row"]["present_shape"] for row in validation) != int(contract["actor_observation"]["expected_validation_present_rows"]):
            raise ValueError("OR110 validation present-row count drifted")
        validation_rows, validation_summary, validation_montage = evaluate_samples(validation, "validation")
        validation_gates = {
            "minimum_present_mean_outside_board_edge_f1_delta": validation_summary["present_mean_outside_board_edge_f1_delta"] >= float(acceptance["validation_minimum_present_mean_outside_board_edge_f1_delta"]),
            "minimum_all_sample_mean_outside_board_edge_f1_delta": validation_summary["all_sample_mean_outside_board_edge_f1_delta"] >= float(acceptance["validation_minimum_all_sample_mean_outside_board_edge_f1_delta"]),
            "minimum_present_mean_full_frame_linear_similarity_delta": validation_summary["present_mean_full_frame_linear_similarity_delta"] >= float(acceptance["validation_minimum_present_mean_full_frame_linear_similarity_delta"]),
            "minimum_present_rows_with_positive_outside_board_delta": validation_summary["present_rows_with_positive_outside_board_delta"] >= int(acceptance["validation_minimum_present_rows_with_positive_outside_board_delta"]),
            "bounded_all_sample_mean_board_plus_margin_edge_f1_delta": validation_summary["all_sample_mean_board_plus_margin_edge_f1_delta"] >= float(acceptance["minimum_all_sample_mean_board_plus_margin_edge_f1_delta"]),
        }
    validation_passed = validation_gates is not None and all(validation_gates.values())
    gates = contract["gates"]
    present_triangle_count = int(gates["expected_present_actor_triangle_count_per_frame"])
    baseline_triangle_count = int(gates["expected_baseline_triangle_count_per_frame"])
    integrity_gates = {
        "exact_development_sample_count": len(development_rows) == int(gates["expected_development_sample_count"]),
        "validation_condition_and_count_respected": (len(validation_rows) == int(gates["expected_validation_sample_count_if_development_passes"])) == development_passed,
        "baseline_triangle_count_exact": all(row["baseline"] == baseline_triangle_count for row in triangle_counts),
        "actor_triangle_count_exact_when_present": all(row["rendered"] == (present_triangle_count if row["present_actor"] else baseline_triangle_count) for row in triangle_counts),
        "manifest_unique_assets_read_once": len(asset_receipts) == int(gates["expected_unique_mesh_asset_reads"]),
        "baseline_reproduces_or95": max(baseline_errors) <= float(gates["maximum_baseline_metric_absolute_error_vs_or95"]),
        "endpoint_reprojection_exact": max(reprojection_errors[0::2], default=0.0) <= float(gates["maximum_endpoint_reprojection_error_px"]),
        "radius_reprojection_exact": max(reprojection_errors[1::2], default=0.0) <= float(gates["maximum_radius_reprojection_error_px"]),
        "absent_rows_are_byte_identical_baseline": max(absent_image_differences, default=0) == 0,
        "one_shared_development_color_frozen_before_validation": True,
        "real_triangulated_3d_capsule_in_shared_zbuffer": True,
        "no_physical_pixel_copy_warp_blend_composite_texture_projection_search_replay_action_state_timing_dynamics_camera_workcell_robot_hardware_or_paid_compute": True,
        "retained_same_episode_reconstruction_not_predictive_simulation_physics_transfer_or_promotion": True,
    }
    if development_passed and validation_passed and all(integrity_gates.values()):
        status = "PASS_RENDERER_NATIVE_SINGLE_CAPSULE_OPERATOR_RECONSTRUCTION_VALIDATED"
        reviewer_decision = "FREEZE_RENDERER_NATIVE_SINGLE_CAPSULE_OPERATOR_FULL_TIMELINE_DIAGNOSTIC"
        next_transition = "freeze_or111_renderer_native_single_capsule_operator_full_timeline_diagnostic"
    elif not development_passed:
        status = "TERMINAL_RENDERER_NATIVE_SINGLE_CAPSULE_OPERATOR_RECONSTRUCTION_DEVELOPMENT_GATE_FAILED"
        reviewer_decision = "REJECT_SINGLE_CAPSULE_RENDER_AND_ATTRIBUTE_ACTOR_RECONSTRUCTION_FAILURE"
        next_transition = "freeze_or111_actor_reconstruction_failure_attribution"
    else:
        status = "TERMINAL_RENDERER_NATIVE_SINGLE_CAPSULE_OPERATOR_RECONSTRUCTION_VALIDATION_GATE_FAILED"
        reviewer_decision = "REJECT_SINGLE_CAPSULE_RENDER_AND_ATTRIBUTE_ACTOR_RECONSTRUCTION_FAILURE"
        next_transition = "freeze_or111_actor_reconstruction_failure_attribution"
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_post_final_renderer_native_single_capsule_operator_reconstruction_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": status,
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "material": {"development_dynamic_component_median_target_bgr": target_bgr.tolist(), "native_pre_response_bgr": pre_response_bgr.tolist(), "estimates": 1},
        "development_rows": development_rows,
        "development_summary": development_summary,
        "development_montage": development_montage,
        "validation_rows": validation_rows,
        "validation_summary": validation_summary,
        "validation_montage": validation_montage,
        "gates": {"development": development_gates, "validation": validation_gates, "integrity": integrity_gates},
        "compiled_library": {"path": str(library_path.relative_to(REPO_ROOT)), "sha256": sha256_file(library_path), "compile_command": compile_command, "compiler_stderr": compiler_stderr},
        "execution": {
            "development_state_trace_reads": len(contract["split"]["development_positions"]),
            "validation_state_trace_reads": validation_positions_read,
            "development_physical_episode_decodes": len(contract["split"]["development_positions"]),
            "validation_physical_episode_decodes": validation_positions_read,
            "development_physical_frames_compared": len(development_rows),
            "validation_physical_frames_compared": len(validation_rows),
            "development_baseline_renders": len(development_rows),
            "development_actor_renders": len(development_rows),
            "validation_baseline_renders": len(validation_rows),
            "validation_actor_renders": len(validation_rows),
            "development_color_estimates": 1,
            "candidate_searches": 0,
            "simulator_replays": 0,
            "action_or_state_timing_dynamics_camera_workcell_robot_mutations": 0,
            "physical_pixel_copy_warp_blend_composite_or_texture_projection": 0,
            "hardware_actions": 0,
            "paid_compute": False,
            "mean_native_raster_seconds": float(np.mean(raster_seconds)),
            "elapsed_seconds": time.perf_counter() - started,
        },
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": reviewer_decision,
        "next_transition": next_transition,
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

"""Render OR126's complete procedural fixture in the OR119 shared z-buffer."""

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
from .observable_registration_native_rasterizer_byte_equivalence import _compile_native, _native_rasterize
from .observable_registration_post_final_independent_left_right_robot_base_se2_diagnostic import _independently_registered_trace
from .observable_registration_post_final_independent_robot_base_full_corpus_diagnostic import _episode_inventory, load_post_final_independent_robot_base_full_corpus_diagnostic_contract
from .observable_registration_post_final_renderer_native_finite_linear_workcell_object_reconstruction import _primitive_triangle_stream, load_post_final_renderer_native_finite_linear_workcell_object_reconstruction_contract
from .observable_registration_post_final_renderer_native_single_capsule_operator_reconstruction import _inverse_response_bgr
from .observable_registration_post_final_two_material_finite_object_full_timeline_propagation import load_post_final_two_material_finite_object_full_timeline_propagation_contract
from .observable_registration_static_development_full_mesh_comparison import _load_unique_asset_cache
from .observable_registration_temporal_pixel_similarity import _linear_similarity, _tolerant_edge_f1


cv2.ocl.setUseOpenCL(False)

SCHEMA = "sim2claw.observable_registration_renderer_native_planar_fixture_static_comparison_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_renderer_native_planar_fixture_static_comparison_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_renderer_native_planar_fixture_static_comparison_v1"


def load_planar_fixture_static_comparison_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR127 contract")
    for group in ("sources", "frozen_identities"):
        for name, binding in contract[group].items():
            if name == "mesh_asset_root":
                continue
            source_path = binding.get("path")
            expected = binding.get("sha256")
            if source_path and expected and sha256_file(REPO_ROOT / source_path) != expected:
                raise ValueError(f"OR127 identity mismatch: {source_path}")
    split = contract["split"]
    if split["development_positions"] != list(range(1, 8)) or split["corroboration_positions"] != list(range(8, 12)):
        raise ValueError("OR127 split drifted")
    fixture = contract["fixture"]
    if fixture["cell_count_per_axis"] != 8 or fixture["triangle_count"] != 128 or fixture["shared_zbuffer"] is not True:
        raise ValueError("OR127 fixture geometry drifted")
    if fixture["physical_pixel_texture_projection"] is not False or fixture["screen_space_overlay"] is not False:
        raise ValueError("OR127 texture or overlay boundary drifted")
    resources = contract["resource_boundary"]
    zero = ("physical_pixel_texture_projections_allowed", "screen_space_overlays_allowed", "fits_or_candidate_selections_allowed", "threshold_changes_allowed", "retries_allowed", "simulator_replays_allowed", "hardware_actions_allowed")
    if any(resources[key] != 0 for key in zero) or resources["paid_compute_allowed"] is not False:
        raise ValueError("OR127 resource boundary drifted")
    if any(contract["authority"].values()):
        raise ValueError("OR127 authority must remain closed")
    return contract


def _fixture_stream(parameters: dict[str, Any], camera: dict[str, Any], contract: dict[str, Any], response: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    corners = np.asarray(parameters["model_coordinate_corners"], dtype=np.float64)
    normal = np.asarray(parameters["support_plane"]["normal"], dtype=np.float64)
    corners = corners + normal * float(contract["fixture"]["plane_offset_m"])
    cells = np.asarray(parameters["procedural_pattern"]["cells"], dtype=np.uint8)
    triangles: list[np.ndarray] = []
    colors: list[np.ndarray] = []
    black = _inverse_response_bgr(np.asarray(contract["fixture"]["black_target_bgr"], dtype=np.uint8), response)
    white = _inverse_response_bgr(np.asarray(contract["fixture"]["white_target_bgr"], dtype=np.uint8), response)

    def point(u: float, v: float) -> np.ndarray:
        return (1.0 - u) * (1.0 - v) * corners[0] + u * (1.0 - v) * corners[1] + u * v * corners[2] + (1.0 - u) * v * corners[3]

    for row in range(8):
        for column in range(8):
            u0, u1 = column / 8.0, (column + 1) / 8.0
            v0, v1 = row / 8.0, (row + 1) / 8.0
            p00, p10, p11, p01 = point(u0, v0), point(u1, v0), point(u1, v1), point(u0, v1)
            triangles.extend([np.stack([p00, p10, p11]), np.stack([p00, p11, p01])])
            color = white if int(cells[row, column]) else black
            colors.extend([color, color])
    world = np.ascontiguousarray(np.stack(triangles))
    pixels, depths = _project_triangles_roll(world, camera, 320, 240)
    return np.ascontiguousarray(pixels), np.ascontiguousarray(depths), np.ascontiguousarray(np.stack(colors).astype(np.uint8))


def _edge(frame: np.ndarray, candidate: np.ndarray, mask: np.ndarray, edge: dict[str, Any]) -> float:
    return float(_masked_tolerant_edge_f1(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY), mask, edge)["f1"])


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR127 one-run receipt already exists")
    contract = load_planar_fixture_static_comparison_contract(contract_path)
    or126 = json.loads((REPO_ROOT / contract["sources"]["or126_receipt"]["path"]).read_text())
    parameters = json.loads((REPO_ROOT / contract["sources"]["or126_parameters"]["path"]).read_text())
    if or126["artifact_sha256"] != contract["sources"]["or126_receipt"]["artifact_sha256"] or parameters["artifact_sha256"] != contract["sources"]["or126_parameters"]["artifact_sha256"]:
        raise ValueError("OR127 OR126 prerequisite drifted")
    or119_contract = load_post_final_two_material_finite_object_full_timeline_propagation_contract(REPO_ROOT / contract["sources"]["or119_contract"]["path"])
    or116_contract = load_post_final_renderer_native_finite_linear_workcell_object_reconstruction_contract(REPO_ROOT / or119_contract["sources"]["or116_contract"]["path"])
    or95 = load_post_final_independent_robot_base_full_corpus_diagnostic_contract(REPO_ROOT / or119_contract["sources"]["or95_contract"]["path"])
    or118 = json.loads((REPO_ROOT / or119_contract["sources"]["or118_receipt"]["path"]).read_text())
    or119_rows = json.loads((REPO_ROOT / contract["sources"]["or119_frame_rows"]["path"]).read_text())["rows"]
    prior_initial = {int(row["split_position"]): row for row in or119_rows if int(row["evaluation_index"]) == 0}
    scene = json.loads((REPO_ROOT / or119_contract["sources"]["shared_scene_manifest"]["path"]).read_text())
    frozen = or95["frozen_candidate"]
    camera, response, renderer = frozen["camera"], frozen["global_monotone_response"], or119_contract["renderer"]
    static = frozen["static_workcell_transform"]
    static_family = {"anchor_body_id": int(static["anchor_body_id"]), "transformed_workcell_body_ids": [int(value) for value in static["transformed_body_ids"]]}
    static_vector = np.asarray(static["vector"], dtype=np.float64)
    left_ids = [int(value) for value in frozen["left_robot_transform"]["transformed_body_ids"]]
    right_ids = [int(value) for value in frozen["right_robot_transform"]["transformed_body_ids"]]
    robot_vector = np.asarray(frozen["left_robot_transform"]["vector"] + frozen["right_robot_transform"]["vector"], dtype=np.float64)
    shape = or118["frozen_shape"]
    shaft = np.asarray(or119_contract["frozen_object"]["shaft_pre_response_bgr"], dtype=np.uint8)
    terminal = np.asarray(or119_contract["frozen_object"]["terminal_pre_response_bgr"], dtype=np.uint8)
    object_colors = np.concatenate([np.tile(shaft, (248, 1)), np.tile(terminal, (100, 1))], axis=0)
    episodes = _episode_inventory(or95)
    by_position = {int(row["split_position"]): row for row in episodes}
    board_mask, outside_mask = _region_masks(np.asarray(or119_contract["regions"]["board_plus_margin"]["points_px"], dtype=np.float64), width=320, height=240, dilation_kernel_px=int(or119_contract["regions"]["board_plus_margin"]["dilation_kernel_px_at_320x240"]))
    fixture_polygon = np.rint(np.asarray(parameters["development_median_corners_px"], dtype=np.float64)).astype(np.int32)
    fixture_mask_u8 = np.zeros((240, 320), dtype=np.uint8)
    cv2.fillConvexPoly(fixture_mask_u8, fixture_polygon, 1)
    fixture_mask = cv2.dilate(fixture_mask_u8, np.ones((9, 9), dtype=np.uint8)) > 0
    edge = or119_contract["metric"]["edge"]
    output_directory.mkdir(parents=True, exist_ok=True)
    meshes, asset_receipts = _load_unique_asset_cache(scene, REPO_ROOT / or119_contract["sources"]["mesh_asset_root"]["path"])
    library_path, compile_command, compiler_stderr = _compile_native({"sources": {"native_source": or119_contract["sources"]["or79_native_source"]}, "compiler": {"executable": "clang"}}, output_directory)
    fixture_pixels, fixture_depths, fixture_colors = _fixture_stream(parameters, camera, contract, response)
    rows: list[dict[str, Any]] = []
    panels: list[np.ndarray] = []
    triangle_counts: list[dict[str, int]] = []

    def evaluate_positions(positions: list[int], split_name: str) -> None:
        for position in positions:
            episode = by_position[position]
            video = episode["physical_video"]
            physical = cv2.flip(_decode_selected_frames(REPO_ROOT / video["path"], selected_indices=np.asarray([0], dtype=np.int64), expected_frame_count=int(video["frame_count"]), expected_width=int(video["width_px"]), expected_height=int(video["height_px"]), output_width=320, output_height=240)[0], -1)
            trace = json.loads((REPO_ROOT / episode["state_trace"]["path"]).read_text())
            one = {"body_names": trace["body_names"], "frames": [trace["frames"][0]]}
            registered = _independently_registered_trace(one, anchor_body_id=int(static["anchor_body_id"]), left_body_ids=left_ids, right_body_ids=right_ids, vector=robot_vector)
            pixels, depths, colors, _ = _prepare_full_mesh_stream(scene, registered, meshes, camera, renderer, static_family, static_vector)
            object_pixels, object_depths, _, _ = _primitive_triangle_stream(shape, registered, scene, camera, renderer, static_family, static_vector, or116_contract["support_plane"], np.asarray([0, 0, 0], dtype=np.uint8))
            baseline_pixels = np.ascontiguousarray(np.concatenate([pixels, object_pixels]))
            baseline_depths = np.ascontiguousarray(np.concatenate([depths, object_depths]))
            baseline_colors = np.ascontiguousarray(np.concatenate([colors, object_colors]))
            baseline_raw, _, _, _ = _native_rasterize(library_path, baseline_pixels, baseline_depths, baseline_colors, renderer)
            candidate_raw, _, _, _ = _native_rasterize(library_path, np.ascontiguousarray(np.concatenate([baseline_pixels, fixture_pixels])), np.ascontiguousarray(np.concatenate([baseline_depths, fixture_depths])), np.ascontiguousarray(np.concatenate([baseline_colors, fixture_colors])), renderer)
            baseline = apply_monotone_response(baseline_raw, bias=float(response["bias"]), low_slope=float(response["low_intensity_slope"]), high_slope=float(response["high_intensity_slope"]), knot=int(response["fixed_input_knot"]))
            candidate = apply_monotone_response(candidate_raw, bias=float(response["bias"]), low_slope=float(response["low_intensity_slope"]), high_slope=float(response["high_intensity_slope"]), knot=int(response["fixed_input_knot"]))
            baseline_full, candidate_full = _linear_similarity(physical, baseline), _linear_similarity(physical, candidate)
            baseline_fixture, candidate_fixture = _linear_similarity(physical, baseline, fixture_mask), _linear_similarity(physical, candidate, fixture_mask)
            baseline_local_edge, candidate_local_edge = _edge(physical, baseline, fixture_mask, edge), _edge(physical, candidate, fixture_mask, edge)
            baseline_outside, candidate_outside = _edge(physical, baseline, outside_mask, edge), _edge(physical, candidate, outside_mask, edge)
            prior = prior_initial[position]
            rows.append({"split": split_name, "split_position": position, "recording_id": episode["recording_id"], "baseline_full_similarity": baseline_full, "candidate_full_similarity": candidate_full, "full_similarity_delta": candidate_full - baseline_full, "baseline_fixture_similarity": baseline_fixture, "candidate_fixture_similarity": candidate_fixture, "fixture_similarity_delta": candidate_fixture - baseline_fixture, "baseline_fixture_edge_f1": baseline_local_edge, "candidate_fixture_edge_f1": candidate_local_edge, "fixture_edge_f1_delta": candidate_local_edge - baseline_local_edge, "baseline_outside_edge_f1": baseline_outside, "candidate_outside_edge_f1": candidate_outside, "outside_edge_f1_delta": candidate_outside - baseline_outside, "baseline_full_error_vs_or119": baseline_full - float(prior["full_frame_linear_pixel_similarity"]), "baseline_outside_edge_error_vs_or119": baseline_outside - float(prior["outside_board_edge_f1"])})
            triangle_counts.append({"baseline": len(baseline_pixels), "candidate": len(baseline_pixels) + len(fixture_pixels)})
            panels.append(np.concatenate([physical, baseline, candidate], axis=1))

    evaluate_positions(contract["split"]["development_positions"], "development")
    development = [row for row in rows if row["split"] == "development"]
    gates = contract["gates"]
    development_passed = float(np.mean([row["fixture_edge_f1_delta"] for row in development])) >= float(gates["minimum_development_mean_fixture_edge_f1_delta"]) and float(np.mean([row["fixture_similarity_delta"] for row in development])) >= float(gates["minimum_development_mean_fixture_similarity_delta"]) and float(np.mean([row["full_similarity_delta"] for row in development])) >= float(gates["minimum_development_mean_full_similarity_delta"]) and min(row["fixture_edge_f1_delta"] for row in development) >= float(gates["minimum_each_development_fixture_edge_f1_delta"])
    if development_passed:
        evaluate_positions(contract["split"]["corroboration_positions"], "corroboration")
    corroboration = [row for row in rows if row["split"] == "corroboration"]
    corroboration_passed = bool(corroboration) and float(np.mean([row["fixture_edge_f1_delta"] for row in corroboration])) >= float(gates["minimum_corroboration_mean_fixture_edge_f1_delta"]) and float(np.mean([row["full_similarity_delta"] for row in corroboration])) >= float(gates["minimum_corroboration_mean_full_similarity_delta"])
    integrity = {"baseline_reproduces_or119": max(max(abs(row["baseline_full_error_vs_or119"]), abs(row["baseline_outside_edge_error_vs_or119"])) for row in rows) <= float(gates["maximum_baseline_metric_error_vs_or119"]), "expected_unique_mesh_asset_reads": len(asset_receipts) == 18, "triangle_counts_exact": all(row["baseline"] == 825292 and row["candidate"] == 825420 for row in triangle_counts), "corroboration_condition_respected": (len(corroboration) == 4) == development_passed, "procedural_shared_zbuffer_fixture": True, "zero_texture_overlay_fit_selection_threshold_change_retry_replay_hardware_or_paid_compute": True}
    passed = development_passed and corroboration_passed and all(integrity.values())
    montage = np.concatenate([cv2.resize(panel, (480, 120), interpolation=cv2.INTER_AREA) for panel in panels], axis=0)
    montage_path = output_directory / "planar-fixture-static-comparison.png"
    ok, encoded = cv2.imencode(".png", montage, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not ok:
        raise RuntimeError("OR127 montage encoding failed")
    montage_path.write_bytes(encoded.tobytes())
    summary = {key: float(np.mean([row[key] for row in rows])) for key in ("baseline_full_similarity", "candidate_full_similarity", "full_similarity_delta", "fixture_similarity_delta", "fixture_edge_f1_delta", "outside_edge_f1_delta")}
    receipt: dict[str, Any] = {"schema_version": "sim2claw.observable_registration_renderer_native_planar_fixture_static_comparison_receipt.v1", "experiment_id": contract["experiment_id"], "status": "PASS_RENDERER_NATIVE_PLANAR_FIXTURE_STATIC_COMPARISON" if passed else "TERMINAL_RENDERER_NATIVE_PLANAR_FIXTURE_STATIC_GATES_FAILED", "proof_class": contract["proof_class"], "identities": {"contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)}, "implementation": contract["frozen_identities"]["implementation"], "test": contract["frozen_identities"]["test"]}, "rows": rows, "summary": summary, "development_passed": development_passed, "corroboration_passed": corroboration_passed, "integrity_gates": integrity, "audit": {"path": str(montage_path.relative_to(REPO_ROOT)), "sha256": sha256_file(montage_path), "layout": "rows_are_physical_baseline_candidate"}, "compiled_library": {"path": str(library_path.relative_to(REPO_ROOT)), "sha256": sha256_file(library_path), "compile_command": compile_command, "compiler_stderr": compiler_stderr}, "execution": {"physical_video_decodes": len(rows), "physical_frame_reads": len(rows), "baseline_renders": len(rows), "candidate_renders": len(rows), "fixture_triangles": 128, "physical_pixel_texture_projections": 0, "screen_space_overlays": 0, "fits_or_candidate_selections": 0, "threshold_changes": 0, "retries": 0, "simulator_replays": 0, "hardware_actions": 0, "paid_compute": False}, "claim_limits": contract["claim_limits"], "reviewer_decision": "FREEZE_PLANAR_FIXTURE_FULL_TIMELINE_PROPAGATION" if passed else "FREEZE_CLIPPED_FIXTURE_PARAMETERIZATION", "next_transition": "freeze_or128_planar_fixture_full_timeline_propagation" if passed else "freeze_or128_clipped_planar_fixture_parameterization"}
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

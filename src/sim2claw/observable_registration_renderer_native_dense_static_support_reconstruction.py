"""Render OR123's dense workcell-static support as bounded 3D contour segments."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_board_anchored_workcell_se2_static_development_fit import _prepare_full_mesh_stream, _region_masks
from .observable_registration_development_shared_camera_baseline import _decode_selected_frames
from .observable_registration_expanded_development_global_monotone_response_fit import apply_monotone_response
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, sha256_file
from .observable_registration_native_rasterizer_byte_equivalence import _compile_native, _native_rasterize
from .observable_registration_post_final_independent_left_right_robot_base_se2_diagnostic import _independently_registered_trace
from .observable_registration_post_final_independent_robot_base_full_corpus_diagnostic import _episode_inventory, load_post_final_independent_robot_base_full_corpus_diagnostic_contract
from .observable_registration_post_final_renderer_native_finite_linear_workcell_object_reconstruction import _primitive_triangle_stream, load_post_final_renderer_native_finite_linear_workcell_object_reconstruction_contract
from .observable_registration_renderer_native_clipped_rectilinear_planar_array_reconstruction import _array_triangle_stream, _edge_metrics, _summary
from .observable_registration_static_development_full_mesh_comparison import _load_unique_asset_cache


cv2.ocl.setUseOpenCL(False)

SCHEMA = "sim2claw.observable_registration_renderer_native_dense_static_support_reconstruction_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_renderer_native_dense_static_support_reconstruction_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_renderer_native_dense_static_support_reconstruction_v1"


def load_dense_static_support_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR125 contract")
    for group in ("sources", "frozen_identities"):
        for binding in contract[group].values():
            source_path, expected = binding.get("path"), binding.get("sha256")
            if source_path and expected and sha256_file(REPO_ROOT / source_path) != expected:
                raise ValueError(f"OR125 identity mismatch: {source_path}")
            if source_path and binding.get("hash_source") and not (REPO_ROOT / source_path).is_dir():
                raise ValueError(f"OR125 asset root missing: {source_path}")
    split = contract["split"]
    if split["development_positions"] != list(range(1, 8)) or split["corroboration_positions"] != list(range(8, 12)):
        raise ValueError("OR125 split drifted")
    if split["corroboration_requires_development_gate"] is not True or split["corroboration_refit_allowed"] is not False:
        raise ValueError("OR125 corroboration boundary drifted")
    if any(contract["authority"].values()):
        raise ValueError("OR125 authority must remain closed")
    resources = contract["resource_boundary"]
    zero = ("contour_or_parameter_searches_allowed", "material_refits_allowed", "plane_or_camera_changes_allowed", "threshold_changes_allowed", "retries_allowed", "simulator_replays_allowed", "physical_pixel_composites_allowed", "hardware_actions_allowed")
    if any(resources[key] != 0 for key in zero) or resources["paid_compute_allowed"] is not False:
        raise ValueError("OR125 resource boundary drifted")
    return contract


def _dense_segments_from_audit(audit: np.ndarray, vectorization: dict[str, Any]) -> tuple[list[list[int]], dict[str, Any]]:
    width, height = int(vectorization["panel_width_px"]), int(vectorization["panel_height_px"])
    if audit.shape != (height, width * 4, 3):
        raise ValueError("OR125 OR123 audit layout drifted")
    panel = audit[:, 3 * width : 4 * width]
    uncovered = (panel[:, :, 2] > 0) & (panel[:, :, 1] == 0) & (panel[:, :, 0] == 0)
    kernel_size = int(vectorization["component_dilation_kernel_px"])
    dilated = cv2.dilate(uncovered.astype(np.uint8), np.ones((kernel_size, kernel_size), dtype=np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(dilated, connectivity=8)
    segments: set[tuple[int, int, int, int]] = set()
    retained_components = 0
    for label in range(1, count):
        if int(stats[label, cv2.CC_STAT_AREA]) < int(vectorization["minimum_dilated_component_area_px"]):
            continue
        ys, xs = np.where(labels == label)
        points = np.column_stack([xs, ys]).astype(np.float32)
        box = np.rint(cv2.boxPoints(cv2.minAreaRect(points))).astype(np.int32)
        box[:, 0] = np.clip(box[:, 0], 0, width - 1)
        box[:, 1] = np.clip(box[:, 1], 0, height - 1)
        component_segments = 0
        for index in range(4):
            p0 = tuple(int(value) for value in box[index])
            p1 = tuple(int(value) for value in box[(index + 1) % 4])
            if float(np.hypot(p1[0] - p0[0], p1[1] - p0[1])) < float(vectorization["minimum_segment_length_px"]):
                continue
            segment = (p0[0], p0[1], p1[0], p1[1])
            reverse = (p1[0], p1[1], p0[0], p0[1])
            segments.add(min(segment, reverse))
            component_segments += 1
        if component_segments:
            retained_components += 1
    ordered = [list(segment) for segment in sorted(segments)]
    meta = {
        "uncovered_pixel_count": int(uncovered.sum()),
        "dilated_component_count": int(count - 1),
        "retained_component_count": retained_components,
        "dense_segment_count": len(ordered),
    }
    return ordered, meta


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR125 one-run receipt already exists; retry prohibited")
    contract = load_dense_static_support_contract(contract_path)
    or124 = json.loads((REPO_ROOT / contract["sources"]["or124_receipt"]["path"]).read_text())
    if or124["artifact_sha256"] != contract["sources"]["or124_receipt"]["artifact_sha256"] or or124["selected_ownership_family"] != "workcell_static":
        raise ValueError("OR124 did not authorize OR125")
    or123_audit = cv2.imread(str(REPO_ROOT / contract["sources"]["or123_audit"]["path"]), cv2.IMREAD_COLOR)
    if or123_audit is None:
        raise ValueError("OR125 audit decode failed")
    dense_segments, vector_meta = _dense_segments_from_audit(or123_audit, contract["vectorization"])
    if vector_meta != contract["expected_vectorization"]:
        raise ValueError("OR125 frozen vectorization drifted")
    or122b = json.loads((REPO_ROOT / contract["sources"]["or122b_receipt"]["path"]).read_text())
    segments = [list(map(int, segment)) for segment in or122b["segments_xyxy"]] + dense_segments
    pre_response_bgr = np.asarray(or122b["material"]["pre_response_bgr"], dtype=np.uint8)
    or119_contract = json.loads((REPO_ROOT / contract["sources"]["or119_contract"]["path"]).read_text())
    or119_rows = json.loads((REPO_ROOT / contract["sources"]["or119_frame_rows"]["path"]).read_text())["rows"]
    prior_initial = {int(row["split_position"]): row for row in or119_rows if int(row["evaluation_index"]) == 0}
    or118 = json.loads((REPO_ROOT / contract["sources"]["or118_receipt"]["path"]).read_text())
    or116 = load_post_final_renderer_native_finite_linear_workcell_object_reconstruction_contract(REPO_ROOT / contract["sources"]["or116_contract"]["path"])
    or95 = load_post_final_independent_robot_base_full_corpus_diagnostic_contract(REPO_ROOT / contract["sources"]["or95_contract"]["path"])
    episodes = {int(row["split_position"]): row for row in _episode_inventory(or95)}
    scene = json.loads((REPO_ROOT / contract["sources"]["shared_scene_manifest"]["path"]).read_text())
    frozen = or95["frozen_candidate"]
    camera, renderer, response = frozen["camera"], or119_contract["renderer"], frozen["global_monotone_response"]
    static = frozen["static_workcell_transform"]
    static_family = {"anchor_body_id": int(static["anchor_body_id"]), "transformed_workcell_body_ids": [int(value) for value in static["transformed_body_ids"]]}
    static_vector = np.asarray(static["vector"], dtype=np.float64)
    left_ids = [int(value) for value in frozen["left_robot_transform"]["transformed_body_ids"]]
    right_ids = [int(value) for value in frozen["right_robot_transform"]["transformed_body_ids"]]
    robot_vector = np.asarray(frozen["left_robot_transform"]["vector"] + frozen["right_robot_transform"]["vector"], dtype=np.float64)
    width, height = int(renderer["width_px"]), int(renderer["height_px"])
    board, outside = _region_masks(np.asarray(or119_contract["regions"]["board_plus_margin"]["points_px"], dtype=np.float64), width=width, height=height, dilation_kernel_px=int(or119_contract["regions"]["board_plus_margin"]["dilation_kernel_px_at_320x240"]))
    local = np.zeros((height, width), dtype=np.uint8)
    x0, y0, x1, y1 = [int(value) for value in contract["regions"]["dense_support_roi_xyxy"]]
    local[y0:y1, x0:x1] = 1
    local = (local.astype(bool) & outside.astype(bool)).astype(np.uint8)
    consensus_panel = or123_audit[:, :width]
    consensus = cv2.cvtColor(consensus_panel, cv2.COLOR_BGR2GRAY) > 0
    output_directory.mkdir(parents=True, exist_ok=True)
    meshes, assets = _load_unique_asset_cache(scene, REPO_ROOT / contract["sources"]["mesh_asset_root"]["path"])
    library, compile_command, compiler_stderr = _compile_native({"sources": {"native_source": contract["sources"]["or79_native_source"]}, "compiler": {"executable": "clang"}}, output_directory)
    body_names = [row["name"] for row in scene["bodies"]]

    def prepare(position: int) -> dict[str, Any]:
        episode = episodes[position]
        video = episode["physical_video"]
        physical = cv2.flip(_decode_selected_frames(REPO_ROOT / video["path"], selected_indices=np.asarray([0], dtype=np.int64), expected_frame_count=int(video["frame_count"]), expected_width=int(video["width_px"]), expected_height=int(video["height_px"]), output_width=width, output_height=height)[0], -1)
        trace = json.loads((REPO_ROOT / episode["state_trace"]["path"]).read_text())
        if trace["body_names"] != body_names:
            raise ValueError("OR125 trace ordering drifted")
        registered = _independently_registered_trace({"body_names": trace["body_names"], "frames": [trace["frames"][0]]}, anchor_body_id=int(static["anchor_body_id"]), left_body_ids=left_ids, right_body_ids=right_ids, vector=robot_vector)
        pixels, depths, colors, _ = _prepare_full_mesh_stream(scene, registered, meshes, camera, renderer, static_family, static_vector)
        op, od, _, _ = _primitive_triangle_stream(or118["frozen_shape"], registered, scene, camera, renderer, static_family, static_vector, or116["support_plane"], np.zeros(3, dtype=np.uint8))
        oc = np.concatenate([np.tile(np.asarray(or118["selected_material_pair"]["shaft_pre_response_bgr"], dtype=np.uint8), (248, 1)), np.tile(np.asarray(or118["selected_material_pair"]["terminal_pre_response_bgr"], dtype=np.uint8), (100, 1))], axis=0)
        return {"position": position, "physical": physical, "registered": registered, "pixels": np.ascontiguousarray(np.concatenate([pixels, op])), "depths": np.ascontiguousarray(np.concatenate([depths, od])), "colors": np.ascontiguousarray(np.concatenate([colors, oc]))}

    def evaluate(item: dict[str, Any]) -> tuple[dict[str, Any], np.ndarray, np.ndarray, np.ndarray]:
        base_raw, _, _, _ = _native_rasterize(library, item["pixels"], item["depths"], item["colors"], renderer)
        baseline = apply_monotone_response(base_raw, bias=float(response["bias"]), low_slope=float(response["low_intensity_slope"]), high_slope=float(response["high_intensity_slope"]), knot=int(response["fixed_input_knot"]))
        ap, ad, ac, meta = _array_triangle_stream(segments, item["registered"], scene, camera, renderer, static_family, static_vector, or116["support_plane"], float(contract["geometry"]["radius_px"]), pre_response_bgr)
        candidate_raw, _, _, _ = _native_rasterize(library, np.ascontiguousarray(np.concatenate([item["pixels"], ap])), np.ascontiguousarray(np.concatenate([item["depths"], ad])), np.ascontiguousarray(np.concatenate([item["colors"], ac])), renderer)
        candidate = apply_monotone_response(candidate_raw, bias=float(response["bias"]), low_slope=float(response["low_intensity_slope"]), high_slope=float(response["high_intensity_slope"]), knot=int(response["fixed_input_knot"]))
        bm = _edge_metrics(item["physical"], baseline, board, outside, local, or119_contract["metric"]["edge"])
        cm = _edge_metrics(item["physical"], candidate, board, outside, local, or119_contract["metric"]["edge"])
        changed = np.max(cv2.absdiff(candidate, baseline), axis=2) > 0
        coverage = float((consensus & (cv2.dilate(changed.astype(np.uint8), np.ones((3, 3), dtype=np.uint8)) > 0)).sum() / max(int(consensus.sum()), 1))
        position = int(item["position"])
        row = {"split_position": position, "recording_id": episodes[position]["recording_id"], "baseline": bm, "candidate": cm, "full_frame_similarity_delta": cm["full_frame_linear_pixel_similarity"] - bm["full_frame_linear_pixel_similarity"], "board_edge_f1_delta": cm["board_plus_margin_edge_f1"] - bm["board_plus_margin_edge_f1"], "outside_board_edge_f1_delta": cm["outside_board_edge_f1"] - bm["outside_board_edge_f1"], "array_roi_edge_f1_delta": cm["array_roi_edge_f1"] - bm["array_roi_edge_f1"], "consensus_change_coverage": coverage, "geometry": meta, "baseline_triangle_count": len(item["pixels"]), "candidate_triangle_count": len(item["pixels"]) + len(ap), "or119_initial_similarity_delta": bm["full_frame_linear_pixel_similarity"] - float(prior_initial[position]["full_frame_linear_pixel_similarity"])}
        return row, item["physical"], baseline, candidate

    development_eval = [evaluate(prepare(position)) for position in contract["split"]["development_positions"]]
    development_rows = [value[0] for value in development_eval]
    development_summary = _summary(development_rows)
    development_summary["mean_consensus_change_coverage"] = float(np.mean([row["consensus_change_coverage"] for row in development_rows]))
    gate = contract["acceptance"]["development"]
    development_pass = development_summary["mean_outside_board_edge_f1_delta"] >= float(gate["minimum_mean_outside_board_edge_f1_delta"]) and development_summary["mean_array_roi_edge_f1_delta"] >= float(gate["minimum_mean_array_roi_edge_f1_delta"]) and development_summary["mean_full_frame_similarity_delta"] >= float(gate["minimum_mean_full_frame_similarity_delta"]) and abs(development_summary["mean_board_edge_f1_delta"]) <= float(gate["maximum_absolute_mean_board_edge_f1_delta"]) and development_summary["mean_consensus_change_coverage"] >= float(gate["minimum_mean_consensus_change_coverage"]) and development_summary["rows_positive_outside"] == len(development_rows)
    corroboration_eval = [evaluate(prepare(position)) for position in contract["split"]["corroboration_positions"]] if development_pass else []
    corroboration_rows = [value[0] for value in corroboration_eval]
    corroboration_summary = _summary(corroboration_rows) if corroboration_rows else None
    if corroboration_summary is not None:
        corroboration_summary["mean_consensus_change_coverage"] = float(np.mean([row["consensus_change_coverage"] for row in corroboration_rows]))
    cgate = contract["acceptance"]["corroboration"]
    corroboration_pass = bool(corroboration_rows) and corroboration_summary["mean_outside_board_edge_f1_delta"] >= float(cgate["minimum_mean_outside_board_edge_f1_delta"]) and corroboration_summary["mean_array_roi_edge_f1_delta"] >= float(cgate["minimum_mean_array_roi_edge_f1_delta"]) and corroboration_summary["mean_full_frame_similarity_delta"] >= float(cgate["minimum_mean_full_frame_similarity_delta"]) and abs(corroboration_summary["mean_board_edge_f1_delta"]) <= float(cgate["maximum_absolute_mean_board_edge_f1_delta"]) and corroboration_summary["mean_consensus_change_coverage"] >= float(cgate["minimum_mean_consensus_change_coverage"]) and corroboration_summary["rows_positive_outside"] == len(corroboration_rows)
    all_eval = development_eval + corroboration_eval
    montage = np.concatenate([np.concatenate([physical, baseline, candidate, cv2.absdiff(physical, candidate)], axis=1) for _, physical, baseline, candidate in all_eval], axis=0)
    montage_path = output_directory / "dense-static-support-montage.png"
    ok, encoded = cv2.imencode(".png", montage, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not ok:
        raise RuntimeError("OR125 montage encoding failed")
    montage_path.write_bytes(encoded.tobytes())
    all_rows = development_rows + corroboration_rows
    passed = development_pass and corroboration_pass
    receipt: dict[str, Any] = {"schema_version": "sim2claw.observable_registration_renderer_native_dense_static_support_reconstruction_receipt.v1", "experiment_id": contract["experiment_id"], "status": "PASS_RENDERER_NATIVE_DENSE_STATIC_SUPPORT_RECONSTRUCTION" if passed else "TERMINAL_RENDERER_NATIVE_DENSE_STATIC_SUPPORT_RECONSTRUCTION_FAILED", "proof_class": contract["proof_class"], "identities": {"contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)}, "implementation": contract["frozen_identities"]["implementation"], "test": contract["frozen_identities"]["test"]}, "vectorization": vector_meta, "segment_count_including_or122b": len(segments), "material": {"pre_response_bgr": pre_response_bgr.tolist(), "refits": 0}, "development_rows": development_rows, "development_summary": development_summary, "development_gate_passed": development_pass, "corroboration_rows": corroboration_rows, "corroboration_summary": corroboration_summary, "corroboration_gate_passed": corroboration_pass, "integrity_gates": {"expected_vectorization_exact": vector_meta == contract["expected_vectorization"], "triangle_count_exact_every_row": all(row["geometry"]["triangle_count"] == len(segments) * 248 for row in all_rows), "maximum_reprojection_error_within_gate": all(row["geometry"]["maximum_centerline_endpoint_reprojection_error_px"] <= float(contract["acceptance"]["maximum_endpoint_reprojection_error_px"]) for row in all_rows), "or119_baseline_exact": all(abs(row["or119_initial_similarity_delta"]) <= 1e-8 for row in all_rows), "zero_search_refit_plane_camera_action_timing_retry_replay_hardware_or_paid_compute": True}, "montage": {"path": str(montage_path.relative_to(REPO_ROOT)), "sha256": sha256_file(montage_path), "layout": "physical_or119_baseline_dense_candidate_absolute_difference"}, "execution": {"physical_frame_reads": len(all_rows), "baseline_renders": len(all_rows), "candidate_renders": len(all_rows), "mesh_asset_reads": len(assets), "contour_or_parameter_searches": 0, "material_refits": 0, "plane_or_camera_changes": 0, "threshold_changes": 0, "retries": 0, "simulator_replays": 0, "physical_pixel_composites": 0, "hardware_actions": 0, "paid_compute": False}, "claim_limits": contract["claim_limits"], "reviewer_decision": "FREEZE_DENSE_STATIC_SUPPORT_FULL_TIMELINE_PROPAGATION" if passed else "FREEZE_DENSE_STATIC_SUPPORT_FAILURE_ATTRIBUTION", "next_transition": "freeze_or126_dense_static_support_full_timeline_propagation" if passed else "freeze_or126_dense_static_support_failure_attribution"}
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

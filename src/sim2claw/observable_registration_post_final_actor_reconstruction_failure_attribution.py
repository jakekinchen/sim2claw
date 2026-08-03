"""Attribute OR110 failure to projection, occlusion, or single-proxy detail."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, sha256_file
from .observable_registration_native_rasterizer_byte_equivalence import _compile_native, _native_rasterize
from .observable_registration_post_final_independent_left_right_robot_base_se2_diagnostic import _independently_registered_trace
from .observable_registration_post_final_independent_robot_base_full_corpus_diagnostic import _episode_inventory
from .observable_registration_post_final_legacy_photo_background_ablation import _write_png
from .observable_registration_post_final_renderer_native_single_capsule_operator_reconstruction import _actor_triangle_stream


cv2.ocl.setUseOpenCL(False)
SCHEMA = "sim2claw.observable_registration_post_final_actor_reconstruction_failure_attribution_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_final_actor_reconstruction_failure_attribution_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_final_actor_reconstruction_failure_attribution_v1"


def load_post_final_actor_reconstruction_failure_attribution_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR111 contract")
    for source in contract["sources"].values():
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    cohort = contract["cohort"]
    if cohort != {"development_present_rows_only": True, "expected_row_count": 13, "validation_rows_or_pixels_allowed": 0}:
        raise ValueError("OR111 cohort drifted")
    tree = contract["decision_tree"]
    if tree["minimum_mean_target_vs_isolated_silhouette_iou"] != 0.85 or tree["minimum_mean_visible_vs_isolated_coverage"] != 0.8:
        raise ValueError("OR111 decision tree drifted")
    resources = contract["resource_boundary"]
    if (
        resources["physical_video_decodes_allowed"] != 0
        or resources["candidate_video_decodes_allowed"] != 0
        or resources["full_scene_renders_allowed"] != 0
        or resources["fits_or_candidate_searches_allowed"] != 0
        or resources["validation_pixels_allowed"] != 0
        or resources["paid_compute_allowed"] is not False
        or any(contract["authority"].values())
    ):
        raise ValueError("OR111 resource or authority boundary drifted")
    if contract["claim_limits"]["predictive_simulation"] is not False or contract["claim_limits"]["physics_fidelity"] is not False:
        raise ValueError("OR111 claim boundary drifted")
    return contract


def _capsule_mask(shape: dict[str, Any], *, width: int, height: int) -> np.ndarray:
    mask = np.zeros((height, width), dtype=np.uint8)
    p0 = tuple(np.rint(shape["endpoint0_px"]).astype(int))
    p1 = tuple(np.rint(shape["endpoint1_px"]).astype(int))
    radius = int(shape["radius_px"])
    cv2.line(mask, p0, p1, 255, 2 * radius, cv2.LINE_8)
    cv2.circle(mask, p0, radius, 255, -1, cv2.LINE_8)
    cv2.circle(mask, p1, radius, 255, -1, cv2.LINE_8)
    return mask.astype(bool)


def _iou(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.count_nonzero(left & right) / max(np.count_nonzero(left | right), 1))


def _local_edge_f1(physical: np.ndarray, mask: np.ndarray, spec: dict[str, Any]) -> dict[str, float | int]:
    gray = cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY)
    physical_edge = cv2.Canny(gray, int(spec["canny_low_threshold"]), int(spec["canny_high_threshold"])) > 0
    local = cv2.dilate(mask.astype(np.uint8) * 255, np.ones((int(spec["local_support_dilation_px"]),) * 2, dtype=np.uint8)) > 0
    physical_edge &= local
    boundary = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), dtype=np.uint8)) > 0
    tolerance = np.ones((int(spec["tolerance_dilation_px"]),) * 2, dtype=np.uint8)
    physical_dilated = cv2.dilate(physical_edge.astype(np.uint8) * 255, tolerance) > 0
    boundary_dilated = cv2.dilate(boundary.astype(np.uint8) * 255, tolerance) > 0
    precision = float(np.count_nonzero(boundary & physical_dilated) / max(np.count_nonzero(boundary), 1))
    recall = float(np.count_nonzero(physical_edge & boundary_dilated) / max(np.count_nonzero(physical_edge), 1))
    f1 = 0.0 if precision + recall <= 0.0 else float(2.0 * precision * recall / (precision + recall))
    return {"precision": precision, "recall": recall, "f1": f1, "physical_local_edge_pixels": int(np.count_nonzero(physical_edge)), "shape_boundary_pixels": int(np.count_nonzero(boundary))}


def _attribute(mean_silhouette_iou: float, mean_visible_coverage: float, tree: dict[str, Any]) -> tuple[str, str, str]:
    if mean_silhouette_iou < float(tree["minimum_mean_target_vs_isolated_silhouette_iou"]):
        return "PROJECTED_3D_SILHOUETTE_LOSS", "FREEZE_3D_CAPSULE_PROJECTION_CORRECTION", "freeze_or112_renderer_native_3d_capsule_projection_correction"
    if mean_visible_coverage < float(tree["minimum_mean_visible_vs_isolated_coverage"]):
        return "SCENE_OCCLUSION_OR_DEPTH_GAUGE_LOSS", "FREEZE_ACTOR_DEPTH_GAUGE_CORRECTION", "freeze_or112_renderer_native_actor_depth_gauge_correction"
    return "SINGLE_PROXY_BOUNDARY_DETAIL_LOSS", "FREEZE_PREREGISTERED_TWO_PART_HAND_FOREARM_ACTOR", "freeze_or112_preregistered_two_part_hand_forearm_actor"


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR111 one-run receipt already exists")
    contract = load_post_final_actor_reconstruction_failure_attribution_contract(contract_path)
    or110_closeout = json.loads((REPO_ROOT / contract["sources"]["or110_closeout"]["path"]).read_text())
    if or110_closeout["reviewer_decision"] != "REJECT_SINGLE_CAPSULE_RENDER_AND_ATTRIBUTE_ACTOR_RECONSTRUCTION_FAILURE":
        raise ValueError("OR110 did not authorize failure attribution")
    or110_contract = json.loads((REPO_ROOT / contract["sources"]["or110_contract"]["path"]).read_text())
    or110_receipt = json.loads((REPO_ROOT / contract["sources"]["or110_receipt"]["path"]).read_text())
    if or110_receipt["artifact_sha256"] != contract["sources"]["or110_receipt"]["artifact_sha256"]:
        raise ValueError("OR110 artifact identity drifted")
    or109_receipt = json.loads((REPO_ROOT / contract["sources"]["or109_receipt"]["path"]).read_text())
    if or109_receipt["artifact_sha256"] != contract["sources"]["or109_receipt"]["artifact_sha256"]:
        raise ValueError("OR109 artifact identity drifted")
    or95_contract = json.loads((REPO_ROOT / contract["sources"]["or95_contract"]["path"]).read_text())
    episodes = _episode_inventory(or95_contract)
    episode_by_position = {int(row["split_position"]): row for row in episodes}
    shape_by_key = {(int(row["split_position"]), int(row["evaluation_index"])): row for row in or109_receipt["development_rows"]}
    montage = cv2.imread(str(REPO_ROOT / contract["sources"]["or110_development_montage"]["path"]), cv2.IMREAD_COLOR)
    if montage is None:
        raise ValueError("OR111 montage unreadable")
    width, height = int(contract["renderer"]["width_px"]), int(contract["renderer"]["height_px"])
    if montage.shape != (int(contract["gates"]["expected_montage_height_px"]), int(contract["gates"]["expected_montage_width_px"]), 3):
        raise ValueError("OR111 montage dimensions drifted")
    camera = or95_contract["frozen_candidate"]["camera"]
    static = or95_contract["frozen_candidate"]["static_workcell_transform"]
    left_ids = [int(value) for value in or95_contract["frozen_candidate"]["left_robot_transform"]["transformed_body_ids"]]
    right_ids = [int(value) for value in or95_contract["frozen_candidate"]["right_robot_transform"]["transformed_body_ids"]]
    robot_vector = np.asarray(or95_contract["frozen_candidate"]["left_robot_transform"]["vector"] + or95_contract["frozen_candidate"]["right_robot_transform"]["vector"], dtype=np.float64)
    pre_response_bgr = np.asarray(or110_receipt["material"]["native_pre_response_bgr"], dtype=np.uint8)
    output_directory.mkdir(parents=True, exist_ok=True)
    library_path, compile_command, compiler_stderr = _compile_native(
        {"sources": {"native_source": contract["sources"]["or79_native_source"]}, "compiler": {"executable": "clang"}}, output_directory
    )
    trace_cache: dict[int, dict[str, Any]] = {}

    def trace_for(position: int) -> dict[str, Any]:
        if position not in trace_cache:
            binding = episode_by_position[position]["state_trace"]
            if sha256_file(REPO_ROOT / binding["path"]) != binding["sha256"]:
                raise ValueError("OR111 trace hash mismatch")
            trace_cache[position] = json.loads((REPO_ROOT / binding["path"]).read_text())
        return trace_cache[position]

    rows: list[dict[str, Any]] = []
    montage_rows: list[np.ndarray] = []
    triangle_counts: list[int] = []
    present_index = 0
    for row_index, or110_row in enumerate(or110_receipt["development_rows"]):
        if not or110_row["present_shape"]:
            continue
        position = int(or110_row["split_position"])
        evaluation_index = int(or110_row["evaluation_index"])
        shape_row = shape_by_key[(position, evaluation_index)]
        physical = montage[row_index * height : (row_index + 1) * height, :width].copy()
        baseline = montage[row_index * height : (row_index + 1) * height, width : 2 * width].copy()
        actor = montage[row_index * height : (row_index + 1) * height, 2 * width : 3 * width].copy()
        visible = np.any(actor != baseline, axis=2)
        trace = trace_for(position)
        one = {"body_names": trace["body_names"], "frames": [trace["frames"][int(or110_row["state_trace_frame_index"])]]}
        registered = _independently_registered_trace(
            one,
            anchor_body_id=int(static["anchor_body_id"]),
            left_body_ids=left_ids,
            right_body_ids=right_ids,
            vector=robot_vector,
        )
        pixels, depths, colors, geometry = _actor_triangle_stream(
            shape_row["capsule"], registered, camera, or110_contract["renderer"], pre_response_bgr, or110_contract["backprojection"]
        )
        colors[:] = 255
        isolated_frame, _, _, _ = _native_rasterize(library_path, pixels, depths, colors, contract["renderer"])
        isolated = np.any(isolated_frame != 0, axis=2)
        target = _capsule_mask(shape_row["capsule"], width=width, height=height)
        target_isolated_iou = _iou(target, isolated)
        visible_coverage = float(np.count_nonzero(visible & isolated) / max(np.count_nonzero(isolated), 1))
        visible_precision = float(np.count_nonzero(visible & isolated) / max(np.count_nonzero(visible), 1))
        edge_spec = contract["measurements"]["physical_edge"]
        target_edge = _local_edge_f1(physical, target, edge_spec)
        isolated_edge = _local_edge_f1(physical, isolated, edge_spec)
        visible_edge = _local_edge_f1(physical, visible, edge_spec)
        rows.append({
            "split_position": position,
            "recording_id": or110_row["recording_id"],
            "evaluation_index": evaluation_index,
            "target_vs_isolated_silhouette_iou": target_isolated_iou,
            "visible_vs_isolated_coverage": visible_coverage,
            "visible_vs_isolated_precision": visible_precision,
            "target_local_physical_edge": target_edge,
            "isolated_local_physical_edge": isolated_edge,
            "visible_local_physical_edge": visible_edge,
            "geometry": geometry,
            "target_pixels": int(np.count_nonzero(target)),
            "isolated_pixels": int(np.count_nonzero(isolated)),
            "visible_pixels": int(np.count_nonzero(visible)),
        })
        triangle_counts.append(int(geometry["triangle_count"]))
        target_overlay = physical.copy()
        target_overlay[target] = np.rint(0.5 * target_overlay[target] + 0.5 * np.asarray([255, 0, 255])).astype(np.uint8)
        isolated_overlay = physical.copy()
        isolated_overlay[isolated] = np.rint(0.5 * isolated_overlay[isolated] + 0.5 * np.asarray([0, 255, 255])).astype(np.uint8)
        visible_overlay = physical.copy()
        visible_overlay[visible] = np.rint(0.5 * visible_overlay[visible] + 0.5 * np.asarray([0, 255, 0])).astype(np.uint8)
        montage_rows.append(np.concatenate([physical, target_overlay, isolated_overlay, visible_overlay], axis=1))
        present_index += 1

    expected_rows = int(contract["cohort"]["expected_row_count"])
    summary = {
        "row_count": len(rows),
        "mean_target_vs_isolated_silhouette_iou": float(np.mean([row["target_vs_isolated_silhouette_iou"] for row in rows])),
        "minimum_target_vs_isolated_silhouette_iou": float(np.min([row["target_vs_isolated_silhouette_iou"] for row in rows])),
        "mean_visible_vs_isolated_coverage": float(np.mean([row["visible_vs_isolated_coverage"] for row in rows])),
        "minimum_visible_vs_isolated_coverage": float(np.min([row["visible_vs_isolated_coverage"] for row in rows])),
        "mean_visible_vs_isolated_precision": float(np.mean([row["visible_vs_isolated_precision"] for row in rows])),
        "mean_target_local_physical_edge_f1": float(np.mean([row["target_local_physical_edge"]["f1"] for row in rows])),
        "mean_isolated_local_physical_edge_f1": float(np.mean([row["isolated_local_physical_edge"]["f1"] for row in rows])),
        "mean_visible_local_physical_edge_f1": float(np.mean([row["visible_local_physical_edge"]["f1"] for row in rows])),
    }
    attribution, reviewer_decision, next_transition = _attribute(
        summary["mean_target_vs_isolated_silhouette_iou"], summary["mean_visible_vs_isolated_coverage"], contract["decision_tree"]
    )
    integrity = {
        "exact_development_present_row_count": len(rows) == expected_rows,
        "exact_isolated_triangle_count": all(value == int(contract["gates"]["expected_isolated_triangle_count_per_row"]) for value in triangle_counts),
        "one_lossless_montage_read": True,
        "zero_source_or_candidate_video_decodes": True,
        "zero_validation_pixels": True,
        "zero_full_scene_renders": True,
        "zero_fit_search_replay_action_state_timing_dynamics_camera_workcell_robot_actor_mutation_hardware_or_paid_compute": True,
        "attribution_not_predictive_simulation_physics_transfer_or_promotion": True,
    }
    passed = all(integrity.values())
    montage_binding = {**_write_png(output_directory / "development_present_actor_failure_attribution.png", np.concatenate(montage_rows, axis=0)), "layout": "physical_target_capsule_isolated_3d_visible_in_scene"}
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_post_final_actor_reconstruction_failure_attribution_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": f"PASS_ACTOR_RECONSTRUCTION_FAILURE_ATTRIBUTED_{attribution}" if passed else "TERMINAL_ACTOR_RECONSTRUCTION_ATTRIBUTION_INTEGRITY_FAILED",
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "rows": rows,
        "summary": summary,
        "attribution": attribution if passed else None,
        "montage": montage_binding,
        "gates": {"integrity": integrity},
        "compiled_library": {"path": str(library_path.relative_to(REPO_ROOT)), "sha256": sha256_file(library_path), "compile_command": compile_command, "compiler_stderr": compiler_stderr},
        "execution": {"development_state_trace_reads": len(trace_cache), "development_montage_reads": 1, "physical_video_decodes": 0, "candidate_video_decodes": 0, "isolated_actor_renders": len(rows), "full_scene_renders": 0, "fits_or_candidate_searches": 0, "validation_pixels": 0, "simulator_replays": 0, "hardware_actions": 0, "paid_compute": False},
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": reviewer_decision if passed else "STOP_ACTOR_RECONSTRUCTION_LANE",
        "next_transition": next_transition if passed else "stop_actor_reconstruction_lane",
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

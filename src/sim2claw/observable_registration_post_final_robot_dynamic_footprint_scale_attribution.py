"""Attribute robot footprint scale from immutable dynamic occupancy maps."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_board_anchored_workcell_se2_static_development_fit import _region_masks
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, sha256_file


SCHEMA = "sim2claw.observable_registration_post_final_robot_dynamic_footprint_scale_attribution_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_final_robot_dynamic_footprint_scale_attribution_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_final_robot_dynamic_footprint_scale_attribution_v1"


def load_post_final_robot_dynamic_footprint_scale_attribution_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR101 contract")
    for source in contract["sources"].values():
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    if contract["input"]["panel_order"] != ["physical_persistent", "candidate_persistent", "physical_dynamic", "candidate_dynamic"]:
        raise ValueError("OR101 panel order drifted")
    resources = contract["resource_boundary"]
    if any(resources[key] != 0 for key in ("physical_video_decodes_allowed", "renders_allowed", "fits_allowed", "parameter_selections_allowed", "simulator_replays_allowed", "hardware_actions_allowed")):
        raise ValueError("OR101 resource boundary drifted")
    if resources["paid_compute_allowed"] is not False or any(contract["authority"].values()):
        raise ValueError("OR101 authority boundary drifted")
    if contract["claim_limits"]["same_video_semantic_match"] is not False:
        raise ValueError("OR101 claim boundary drifted")
    return contract


def _footprint(mask: np.ndarray) -> dict[str, Any]:
    ys, xs = np.nonzero(mask)
    if xs.size == 0:
        raise ValueError("OR101 empty dynamic occupancy panel")
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    width, height = x1 - x0 + 1, y1 - y0 + 1
    return {
        "occupied_pixels": int(xs.size),
        "bbox_xywh": [x0, y0, width, height],
        "bbox_diagonal_px": float(np.hypot(width, height)),
        "centroid_xy_px": [float(xs.mean()), float(ys.mean())],
    }


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR101 one-run receipt already exists")
    contract = load_post_final_robot_dynamic_footprint_scale_attribution_contract(contract_path)
    or97 = json.loads((REPO_ROOT / contract["sources"]["or97_receipt"]["path"]).read_text())
    if or97["artifact_sha256"] != contract["sources"]["or97_receipt"]["artifact_sha256"]:
        raise ValueError("OR97 artifact identity drifted")
    or97_contract_path = REPO_ROOT / or97["contract"]["path"]
    if sha256_file(or97_contract_path) != or97["contract"]["sha256"]:
        raise ValueError("OR97 contract identity drifted")
    or97_contract = json.loads(or97_contract_path.read_text())
    rows: list[dict[str, Any]] = []
    width = int(contract["input"]["panel_width_px"])
    height = int(contract["input"]["panel_height_px"])
    threshold = int(contract["input"]["binary_threshold"])
    _, outside_mask = _region_masks(
        np.asarray(or97_contract["regions"]["board_plus_margin"]["points_px"], dtype=np.float64),
        width=width,
        height=height,
        dilation_kernel_px=int(or97_contract["regions"]["board_plus_margin"]["dilation_kernel_px_at_320x240"]),
    )
    for source_row in or97["rows"]:
        binding = source_row["occupancy_map"]
        path = REPO_ROOT / binding["path"]
        if sha256_file(path) != binding["sha256"]:
            raise ValueError("OR101 occupancy map hash mismatch")
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None or image.shape != (height, width * 4):
            raise ValueError("OR101 occupancy map shape drifted")
        physical = (image[:, width * 2 : width * 3] > threshold) & outside_mask
        candidate = (image[:, width * 3 : width * 4] > threshold) & outside_mask
        physical_fp = _footprint(physical)
        candidate_fp = _footprint(candidate)
        if physical_fp["occupied_pixels"] != int(source_row["dynamic_outside_board"]["physical_pixels"]):
            raise ValueError("OR101 physical occupancy count mismatch")
        if candidate_fp["occupied_pixels"] != int(source_row["dynamic_outside_board"]["candidate_pixels"]):
            raise ValueError("OR101 candidate occupancy count mismatch")
        rows.append({
            "recording_id": source_row["recording_id"],
            "split_position": int(source_row["split_position"]),
            "physical_dynamic": physical_fp,
            "candidate_dynamic": candidate_fp,
            "physical_to_candidate_area_ratio": float(physical_fp["occupied_pixels"] / candidate_fp["occupied_pixels"]),
            "physical_to_candidate_bbox_diagonal_ratio": float(physical_fp["bbox_diagonal_px"] / candidate_fp["bbox_diagonal_px"]),
            "physical_minus_candidate_centroid_xy_px": [float(physical_fp["centroid_xy_px"][0] - candidate_fp["centroid_xy_px"][0]), float(physical_fp["centroid_xy_px"][1] - candidate_fp["centroid_xy_px"][1])],
            "dynamic_outside_board_edge_occupancy_f1": float(source_row["dynamic_outside_board"]["f1"]),
            "occupancy_map": binding,
        })
    area_ratios = np.asarray([row["physical_to_candidate_area_ratio"] for row in rows], dtype=np.float64)
    diagonal_ratios = np.asarray([row["physical_to_candidate_bbox_diagonal_ratio"] for row in rows], dtype=np.float64)
    centroids = np.asarray([row["physical_minus_candidate_centroid_xy_px"] for row in rows], dtype=np.float64)
    mean_dynamic_f1 = float(np.mean([row["dynamic_outside_board_edge_occupancy_f1"] for row in rows]))
    summary = {
        "median_physical_to_candidate_area_ratio": float(np.median(area_ratios)),
        "minimum_physical_to_candidate_area_ratio": float(area_ratios.min()),
        "maximum_physical_to_candidate_area_ratio": float(area_ratios.max()),
        "episodes_with_area_ratio_at_least_1p5": int(np.sum(area_ratios >= 1.5)),
        "median_physical_to_candidate_bbox_diagonal_ratio": float(np.median(diagonal_ratios)),
        "median_physical_minus_candidate_centroid_xy_px": [float(value) for value in np.median(centroids, axis=0)],
        "mean_dynamic_outside_board_edge_occupancy_f1": mean_dynamic_f1,
    }
    rule = contract["decision_tree"]["camera_ray_depth_registration_if"]
    scale_selected = (
        summary["median_physical_to_candidate_area_ratio"] >= float(rule["minimum_median_physical_to_candidate_area_ratio"])
        and summary["episodes_with_area_ratio_at_least_1p5"] >= int(rule["minimum_episodes_with_area_ratio_at_least_1p5"])
        and summary["median_physical_to_candidate_bbox_diagonal_ratio"] >= float(rule["minimum_median_physical_to_candidate_bbox_diagonal_ratio"])
    )
    if scale_selected:
        selected = "independent_robot_camera_ray_depth_and_image_plane_translation"
        next_transition = "freeze_or102_independent_robot_camera_ray_depth_registration_fit"
    elif mean_dynamic_f1 < float(contract["decision_tree"]["otherwise_if_mean_dynamic_f1_below"]):
        selected = "robot_articulation_and_timing"
        next_transition = "freeze_or102_robot_articulation_timing_residual_successor"
    else:
        selected = "no_robot_footprint_successor_selected"
        next_transition = "stop_robot_footprint_lane"
    gates = {
        "exact_eleven_occupancy_maps": len(rows) == int(contract["input"]["occupancy_map_count"]),
        "all_map_hashes_match": True,
        "all_panel_shapes_match": True,
        "all_occupancy_counts_reproduce_or97": True,
        "decision_tree_decidable": selected != "no_robot_footprint_successor_selected",
        "zero_video_decode_render_fit_parameter_selection_replay_hardware_or_paid_compute": True,
        "post_final_diagnostic_not_promotion": True,
    }
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_post_final_robot_dynamic_footprint_scale_attribution_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": "PASS_ROBOT_DYNAMIC_FOOTPRINT_MECHANISM_SELECTED" if all(gates.values()) else "TERMINAL_ROBOT_DYNAMIC_FOOTPRINT_MECHANISM_UNDECIDABLE",
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "rows": rows,
        "summary": summary,
        "selected_mechanism": selected,
        "gates": gates,
        "execution": {"occupancy_png_reads": len(rows), "physical_video_decodes": 0, "renders": 0, "fits": 0, "parameter_selections": 0, "simulator_replays": 0, "hardware_actions": 0, "paid_compute": False},
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": "FREEZE_SELECTED_ROBOT_FOOTPRINT_SUCCESSOR" if all(gates.values()) else "STOP_ROBOT_FOOTPRINT_LANE",
        "next_transition": next_transition,
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    output_directory.mkdir(parents=True, exist_ok=True)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

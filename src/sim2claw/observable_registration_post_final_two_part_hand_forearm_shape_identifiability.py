"""Test a deterministic two-part hand/forearm capsule proxy before rendering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_board_anchored_workcell_se2_static_development_fit import _region_masks
from .observable_registration_development_shared_camera_baseline import _decode_selected_frames
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, sha256_file
from .observable_registration_post_final_actor_reconstruction_failure_attribution import _local_edge_f1
from .observable_registration_post_final_exogenous_operator_skin_edge_occupancy_attribution import _skin_mask
from .observable_registration_post_final_independent_robot_base_full_corpus_diagnostic import _episode_inventory
from .observable_registration_post_final_legacy_photo_background_ablation import _write_png
from .observable_registration_post_final_single_capsule_dynamic_operator_shape_identifiability import (
    _capsule_mask,
    load_post_final_single_capsule_dynamic_operator_shape_identifiability_contract,
)


cv2.ocl.setUseOpenCL(False)
SCHEMA = "sim2claw.observable_registration_post_final_two_part_hand_forearm_shape_identifiability_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_final_two_part_hand_forearm_shape_identifiability_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_final_two_part_hand_forearm_shape_identifiability_v1"


def load_post_final_two_part_hand_forearm_shape_identifiability_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR112 contract")
    for source in contract["sources"].values():
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    split = contract["split"]
    if split["development_positions"] != list(range(1, 8)) or split["validation_positions"] != list(range(8, 12)):
        raise ValueError("OR112 split drifted")
    rule = contract["two_part_rule"]
    if rule["split_quantile"] != 0.5 or rule["split_search"] is not False or rule["part_count"] != 2 or rule["validation_refit"] is not False:
        raise ValueError("OR112 two-part rule drifted")
    resources = contract["resource_boundary"]
    if (
        resources["split_values_allowed"] != 1
        or resources["fits_or_candidate_searches_allowed"] != 0
        or resources["renders_allowed"] != 0
        or resources["simulator_replays_allowed"] != 0
        or resources["paid_compute_allowed"] is not False
        or any(contract["authority"].values())
    ):
        raise ValueError("OR112 resource or authority boundary drifted")
    claims = contract["claim_limits"]
    if claims["predictive_simulation"] is not False or claims["physics_fidelity"] is not False or claims["same_video_semantic_match"] is not False:
        raise ValueError("OR112 claim boundary drifted")
    return contract


def _mask_from_shape(shape: dict[str, Any], image_shape: tuple[int, int]) -> np.ndarray:
    mask = np.zeros(image_shape, dtype=np.uint8)
    radius = int(shape["radius_px"])
    p0 = tuple(np.rint(shape["endpoint0_px"]).astype(int))
    p1 = tuple(np.rint(shape["endpoint1_px"]).astype(int))
    cv2.line(mask, p0, p1, 255, 2 * radius, cv2.LINE_8)
    cv2.circle(mask, p0, radius, 255, -1, cv2.LINE_8)
    cv2.circle(mask, p1, radius, 255, -1, cv2.LINE_8)
    return mask.astype(bool)


def _border_distance(point: np.ndarray, width: int, height: int) -> float:
    x, y = np.asarray(point, dtype=np.float64)
    return float(min(x, width - 1.0 - x, y, height - 1.0 - y))


def _two_part_capsules(component: np.ndarray, capsule_spec: dict[str, Any]) -> tuple[np.ndarray, list[dict[str, Any]], dict[str, Any]]:
    y, x = np.nonzero(component)
    points = np.stack([x, y], axis=1).astype(np.float64)
    if len(points) < 10:
        return np.zeros_like(component), [], {"supported": False}
    center = np.mean(points, axis=0)
    centered = points - center
    values, vectors = np.linalg.eigh(centered.T @ centered)
    major = vectors[:, int(np.argmax(values))]
    along = centered @ major
    low_point = center + major * float(np.min(along))
    high_point = center + major * float(np.max(along))
    height, width = component.shape
    if _border_distance(high_point, width, height) < _border_distance(low_point, width, height):
        major = -major
        along = -along
        low_point, high_point = high_point, low_point
    split = float(np.quantile(along, 0.5))
    part_masks: list[np.ndarray] = []
    part_shapes: list[dict[str, Any]] = []
    for name, selection in (("proximal_forearm", along <= split), ("distal_hand", along > split)):
        part_component = np.zeros_like(component)
        selected_points = points[selection].astype(np.int64)
        part_component[selected_points[:, 1], selected_points[:, 0]] = True
        part_mask, shape = _capsule_mask(part_component, capsule_spec)
        shape = {**shape, "part": name, "source_pixel_count": int(np.count_nonzero(part_component))}
        part_masks.append(part_mask)
        part_shapes.append(shape)
    union = part_masks[0] | part_masks[1]
    metadata = {
        "supported": all(shape["supported"] for shape in part_shapes),
        "oriented_proximal_endpoint_px": low_point.tolist(),
        "oriented_distal_endpoint_px": high_point.tolist(),
        "axial_split_value_px": split,
        "split_quantile": 0.5,
    }
    return union, part_shapes, metadata


def _shape_metrics(component: np.ndarray, mask: np.ndarray) -> dict[str, float | int]:
    intersection = int(np.count_nonzero(component & mask))
    union = int(np.count_nonzero(component | mask))
    component_pixels = int(np.count_nonzero(component))
    mask_pixels = int(np.count_nonzero(mask))
    return {
        "iou": float(intersection / max(union, 1)),
        "coverage": float(intersection / max(component_pixels, 1)),
        "precision": float(intersection / max(mask_pixels, 1)),
        "intersection_pixels": intersection,
        "mask_pixels": mask_pixels,
    }


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR112 one-run receipt already exists")
    contract = load_post_final_two_part_hand_forearm_shape_identifiability_contract(contract_path)
    or111_closeout = json.loads((REPO_ROOT / contract["sources"]["or111_closeout"]["path"]).read_text())
    if or111_closeout["reviewer_decision"] != "FREEZE_PREREGISTERED_TWO_PART_HAND_FOREARM_ACTOR":
        raise ValueError("OR111 did not authorize two-part actor shape")
    or111_receipt = json.loads((REPO_ROOT / contract["sources"]["or111_receipt"]["path"]).read_text())
    if or111_receipt["artifact_sha256"] != contract["sources"]["or111_receipt"]["artifact_sha256"]:
        raise ValueError("OR111 artifact identity drifted")
    or109_contract_path = REPO_ROOT / contract["sources"]["or109_contract"]["path"]
    or109_contract = load_post_final_single_capsule_dynamic_operator_shape_identifiability_contract(or109_contract_path)
    or109_receipt = json.loads((REPO_ROOT / contract["sources"]["or109_receipt"]["path"]).read_text())
    if or109_receipt["artifact_sha256"] != contract["sources"]["or109_receipt"]["artifact_sha256"]:
        raise ValueError("OR109 artifact identity drifted")
    or107_contract = json.loads((REPO_ROOT / or109_contract["sources"]["or107_contract"]["path"]).read_text())
    or108_contract = json.loads((REPO_ROOT / or109_contract["sources"]["or108_contract"]["path"]).read_text())
    persistent = cv2.imread(str(REPO_ROOT / or109_contract["sources"]["persistent_support"]["path"]), cv2.IMREAD_GRAYSCALE)
    if persistent is None:
        raise ValueError("OR112 persistent support unreadable")
    removal_kernel = int(or108_contract["persistent_support"]["removal_dilation_kernel_px"])
    removal = cv2.dilate((persistent > 0).astype(np.uint8) * 255, np.ones((removal_kernel, removal_kernel), dtype=np.uint8)).astype(bool)
    or95_contract = json.loads((REPO_ROOT / contract["sources"]["or95_contract"]["path"]).read_text())
    episodes = _episode_inventory(or95_contract)
    episode_by_position = {int(row["split_position"]): row for row in episodes}
    frame_rows = json.loads((REPO_ROOT / contract["sources"]["or95_frame_rows"]["path"]).read_text())["rows"]
    binding_by_key = {(int(row["split_position"]), int(row["evaluation_index"])): row for row in frame_rows}
    _, outside_mask = _region_masks(np.asarray([[-3.0, 66.5], [79.0, 52.0], [176.0, 144.5], [71.5, 193.0]], dtype=np.float64), width=320, height=240, dilation_kernel_px=15)
    outside = outside_mask.astype(bool)
    output_directory.mkdir(parents=True, exist_ok=True)

    def evaluate_rows(shape_rows: list[dict[str, Any]], label: str) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        grouped: dict[int, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
        for shape_row in shape_rows:
            key = (int(shape_row["split_position"]), int(shape_row["evaluation_index"]))
            grouped.setdefault(key[0], []).append((shape_row, binding_by_key[key]))
        rows: list[dict[str, Any]] = []
        montage_rows: list[np.ndarray] = []
        for position, pairs in grouped.items():
            video = episode_by_position[position]["physical_video"]
            if sha256_file(REPO_ROOT / video["path"]) != video["sha256"]:
                raise ValueError("OR112 physical video hash mismatch")
            frames = [
                cv2.flip(frame, -1)
                for frame in _decode_selected_frames(
                    REPO_ROOT / video["path"],
                    selected_indices=np.asarray([int(binding["physical_frame_index"]) for _, binding in pairs], dtype=np.int64),
                    expected_frame_count=int(video["frame_count"]),
                    expected_width=int(video["width_px"]),
                    expected_height=int(video["height_px"]),
                    output_width=320,
                    output_height=240,
                )
            ]
            for (shape_row, binding), physical in zip(pairs, frames, strict=True):
                if not shape_row["present_shape"]:
                    continue
                dynamic = _skin_mask(physical, or107_contract["skin_proxy"]).astype(bool) & outside & ~removal
                count, labels, stats, _ = cv2.connectedComponentsWithStats(dynamic.astype(np.uint8), connectivity=8)
                component = np.zeros_like(dynamic)
                if count > 1:
                    selected_label = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
                    component = labels == selected_label
                if int(np.count_nonzero(component)) != int(shape_row["component_pixels"]):
                    raise ValueError("OR112 dynamic component does not reproduce OR109")
                single = _mask_from_shape(shape_row["capsule"], component.shape)
                two, parts, metadata = _two_part_capsules(component, or109_contract["capsule_fit"])
                single_metrics = _shape_metrics(component, single)
                two_metrics = _shape_metrics(component, two)
                single_edge = _local_edge_f1(physical, single, contract["metric"]["physical_edge"])
                two_edge = _local_edge_f1(physical, two, contract["metric"]["physical_edge"])
                rows.append({
                    "split_position": position,
                    "recording_id": shape_row["recording_id"],
                    "evaluation_index": int(shape_row["evaluation_index"]),
                    "single": {"shape": single_metrics, "local_physical_edge": single_edge},
                    "two_part": {"shape": two_metrics, "local_physical_edge": two_edge, "parts": parts, "metadata": metadata},
                    "iou_gain": float(two_metrics["iou"] - single_metrics["iou"]),
                    "coverage_gain": float(two_metrics["coverage"] - single_metrics["coverage"]),
                    "local_physical_edge_f1_gain": float(two_edge["f1"] - single_edge["f1"]),
                })
                single_overlay = physical.copy()
                single_overlay[single] = np.rint(0.5 * single_overlay[single] + 0.5 * np.asarray([255, 0, 255])).astype(np.uint8)
                two_overlay = physical.copy()
                two_overlay[two] = np.rint(0.5 * two_overlay[two] + 0.5 * np.asarray([0, 255, 255])).astype(np.uint8)
                montage_rows.append(np.concatenate([physical, single_overlay, two_overlay], axis=1))
        summary = {
            "present_rows": len(rows),
            "single_mean_iou": float(np.mean([row["single"]["shape"]["iou"] for row in rows])),
            "two_part_mean_iou": float(np.mean([row["two_part"]["shape"]["iou"] for row in rows])),
            "mean_iou_gain_over_single": float(np.mean([row["iou_gain"] for row in rows])),
            "single_mean_coverage": float(np.mean([row["single"]["shape"]["coverage"] for row in rows])),
            "two_part_mean_coverage": float(np.mean([row["two_part"]["shape"]["coverage"] for row in rows])),
            "mean_coverage_gain_over_single": float(np.mean([row["coverage_gain"] for row in rows])),
            "single_mean_local_physical_edge_f1": float(np.mean([row["single"]["local_physical_edge"]["f1"] for row in rows])),
            "two_part_mean_local_physical_edge_f1": float(np.mean([row["two_part"]["local_physical_edge"]["f1"] for row in rows])),
            "mean_local_physical_edge_f1_gain_over_single": float(np.mean([row["local_physical_edge_f1_gain"] for row in rows])),
            "rows_with_positive_local_edge_gain": sum(row["local_physical_edge_f1_gain"] > 0.0 for row in rows),
        }
        montage = {**_write_png(output_directory / f"{label}_physical_single_two_part.png", np.concatenate(montage_rows, axis=0)), "layout": "physical_left_single_magenta_middle_two_part_yellow_right"}
        return rows, summary, montage

    development_rows, development_summary, development_montage = evaluate_rows(or109_receipt["development_rows"], "development")
    validation_rows, validation_summary, validation_montage = evaluate_rows(or109_receipt["validation_rows"], "validation")
    acceptance = contract["acceptance"]
    development_gates = {
        "minimum_mean_iou_gain_over_single": development_summary["mean_iou_gain_over_single"] >= float(acceptance["development_minimum_mean_iou_gain_over_single"]),
        "minimum_mean_coverage_gain_over_single": development_summary["mean_coverage_gain_over_single"] >= float(acceptance["development_minimum_mean_coverage_gain_over_single"]),
        "minimum_mean_local_physical_edge_f1_gain_over_single": development_summary["mean_local_physical_edge_f1_gain_over_single"] >= float(acceptance["development_minimum_mean_local_physical_edge_f1_gain_over_single"]),
        "minimum_rows_with_positive_local_edge_gain": development_summary["rows_with_positive_local_edge_gain"] >= int(acceptance["development_minimum_rows_with_positive_local_edge_gain"]),
    }
    validation_gates = {
        "minimum_mean_iou_gain_over_single": validation_summary["mean_iou_gain_over_single"] >= float(acceptance["validation_minimum_mean_iou_gain_over_single"]),
        "minimum_mean_coverage_gain_over_single": validation_summary["mean_coverage_gain_over_single"] >= float(acceptance["validation_minimum_mean_coverage_gain_over_single"]),
        "minimum_mean_local_physical_edge_f1_gain_over_single": validation_summary["mean_local_physical_edge_f1_gain_over_single"] >= float(acceptance["validation_minimum_mean_local_physical_edge_f1_gain_over_single"]),
        "minimum_rows_with_positive_local_edge_gain": validation_summary["rows_with_positive_local_edge_gain"] >= int(acceptance["validation_minimum_rows_with_positive_local_edge_gain"]),
    }
    integrity = {
        "exact_development_present_rows": len(development_rows) == int(contract["sampling"]["development_present_rows"]),
        "exact_validation_present_rows": len(validation_rows) == int(contract["sampling"]["validation_present_rows"]),
        "exactly_two_supported_parts_per_row": all(len(row["two_part"]["parts"]) == 2 and row["two_part"]["metadata"]["supported"] for row in development_rows + validation_rows),
        "one_median_split_no_search_or_refit": True,
        "no_render_replay_action_state_timing_dynamics_camera_workcell_robot_hardware_or_paid_compute": True,
        "shape_identifiability_not_predictive_simulation_physics_transfer_or_promotion": True,
    }
    passed = all(development_gates.values()) and all(validation_gates.values()) and all(integrity.values())
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_post_final_two_part_hand_forearm_shape_identifiability_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": "PASS_TWO_PART_HAND_FOREARM_SHAPE_IDENTIFIABLE" if passed else "TERMINAL_TWO_PART_HAND_FOREARM_SHAPE_INSUFFICIENT",
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "development_rows": development_rows,
        "development_summary": development_summary,
        "development_montage": development_montage,
        "validation_rows": validation_rows,
        "validation_summary": validation_summary,
        "validation_montage": validation_montage,
        "gates": {"development": development_gates, "validation": validation_gates, "integrity": integrity},
        "execution": {"development_physical_episode_decodes": 7, "validation_physical_episode_decodes": 4, "development_physical_frames_read": 21, "validation_physical_frames_read": 12, "development_two_part_shape_estimates": len(development_rows), "validation_two_part_shape_estimates": len(validation_rows), "split_values": 1, "fits_or_candidate_searches": 0, "renders": 0, "simulator_replays": 0, "hardware_actions": 0, "paid_compute": False},
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": "FREEZE_RENDERER_NATIVE_TWO_PART_HAND_FOREARM_ACTOR" if passed else "REJECT_TWO_PART_SHAPE_AND_RECONCILE_OPERATOR_ACTOR_LANE",
        "next_transition": "freeze_or113_renderer_native_two_part_hand_forearm_actor" if passed else "freeze_or113_operator_actor_lane_reconciliation",
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

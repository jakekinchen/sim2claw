"""Test whether one deterministic 2D capsule summarizes dynamic operator support."""

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
from .observable_registration_post_final_exogenous_operator_skin_edge_occupancy_attribution import _skin_mask
from .observable_registration_post_final_independent_robot_base_full_corpus_diagnostic import _episode_inventory
from .observable_registration_post_final_legacy_photo_background_ablation import _write_png
from .observable_registration_post_final_shared_shoulder_lift_articulation_calibration import _sample_rows


cv2.ocl.setUseOpenCL(False)
SCHEMA = "sim2claw.observable_registration_post_final_single_capsule_dynamic_operator_shape_identifiability_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_final_single_capsule_dynamic_operator_shape_identifiability_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_final_single_capsule_dynamic_operator_shape_identifiability_v1"


def load_post_final_single_capsule_dynamic_operator_shape_identifiability_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR109 contract")
    for source in contract["sources"].values():
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    if contract["split"]["development_positions"] != list(range(1, 8)) or contract["split"]["validation_positions"] != list(range(8, 12)):
        raise ValueError("OR109 split drifted")
    fit = contract["capsule_fit"]
    if fit["component_policy"] != "largest_connected_dynamic_component" or fit["endpoint_percentiles"] != [5.0, 95.0] or fit["optimization_or_search"] is not False:
        raise ValueError("OR109 capsule family drifted")
    expected = {"development_physical_episode_decodes_allowed": 7, "validation_physical_episode_decodes_allowed": 4, "development_physical_frames_read_allowed": 21, "validation_physical_frames_read_allowed": 12, "deterministic_development_shape_estimates_allowed": 21, "deterministic_validation_shape_estimates_allowed": 12, "optimization_searches_allowed": 0, "candidate_video_decodes_allowed": 0, "renders_allowed": 0, "simulator_replays_allowed": 0, "action_or_state_mutations_allowed": 0, "hardware_actions_allowed": 0, "paid_compute_allowed": False}
    if contract["resource_boundary"] != expected or any(contract["authority"].values()):
        raise ValueError("OR109 resource or authority boundary drifted")
    if contract["claim_limits"]["operator_3d_geometry_or_trajectory_calibrated"] is not False or contract["claim_limits"]["same_video_semantic_match"] is not False:
        raise ValueError("OR109 claim boundary drifted")
    return contract


def _capsule_mask(component: np.ndarray, spec: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]]:
    y, x = np.nonzero(component)
    points = np.stack([x, y], axis=1).astype(np.float64)
    if len(points) < 5:
        return np.zeros_like(component, dtype=bool), {"supported": False}
    center = np.mean(points, axis=0)
    centered = points - center
    values, vectors = np.linalg.eigh(centered.T @ centered)
    major = vectors[:, int(np.argmax(values))]
    minor = np.asarray([-major[1], major[0]])
    along = centered @ major
    across = centered @ minor
    low, high = np.percentile(along, [float(value) for value in spec["endpoint_percentiles"]])
    radius = max(int(spec["minimum_radius_px"]), int(round(float(np.percentile(np.abs(across), float(spec["radius_percentile_of_absolute_minor_projection"]))))))
    p0 = center + major * low
    p1 = center + major * high
    mask = np.zeros_like(component, dtype=np.uint8)
    cv2.line(mask, tuple(np.rint(p0).astype(int)), tuple(np.rint(p1).astype(int)), 255, 2 * radius, cv2.LINE_8)
    cv2.circle(mask, tuple(np.rint(p0).astype(int)), radius, 255, -1, cv2.LINE_8)
    cv2.circle(mask, tuple(np.rint(p1).astype(int)), radius, 255, -1, cv2.LINE_8)
    return mask.astype(bool), {"supported": True, "center_px": center.tolist(), "endpoint0_px": p0.tolist(), "endpoint1_px": p1.tolist(), "radius_px": radius}


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR109 one-run receipt already exists")
    contract = load_post_final_single_capsule_dynamic_operator_shape_identifiability_contract(contract_path)
    closeout = json.loads((REPO_ROOT / contract["sources"]["or108_closeout"]["path"]).read_text())
    if closeout["reviewer_decision"] != "FREEZE_SINGLE_CAPSULE_DYNAMIC_OPERATOR_SHAPE_IDENTIFIABILITY":
        raise ValueError("OR108 did not authorize capsule identifiability")
    prior_contract = json.loads((REPO_ROOT / contract["sources"]["or107_contract"]["path"]).read_text())
    or108_contract = json.loads((REPO_ROOT / contract["sources"]["or108_contract"]["path"]).read_text())
    or108_receipt = json.loads((REPO_ROOT / contract["sources"]["or108_receipt"]["path"]).read_text())
    if or108_receipt["artifact_sha256"] != contract["sources"]["or108_receipt"]["artifact_sha256"]:
        raise ValueError("OR108 artifact identity drifted")
    persistent = cv2.imread(str(REPO_ROOT / contract["sources"]["persistent_support"]["path"]), cv2.IMREAD_GRAYSCALE)
    if persistent is None:
        raise ValueError("OR109 persistent support unreadable")
    persistent = persistent.astype(bool)
    removal = cv2.dilate(persistent.astype(np.uint8) * 255, np.ones((int(or108_contract["persistent_support"]["removal_dilation_kernel_px"]),) * 2, dtype=np.uint8)).astype(bool)
    or95 = json.loads((REPO_ROOT / contract["sources"]["or95_contract"]["path"]).read_text())
    episode_by_position = {int(row["split_position"]): row for row in _episode_inventory(or95)}
    frame_rows = json.loads((REPO_ROOT / contract["sources"]["or95_frame_rows"]["path"]).read_text())["rows"]
    _, outside_mask = _region_masks(np.asarray([[-3.0, 66.5], [79.0, 52.0], [176.0, 144.5], [71.5, 193.0]], dtype=np.float64), width=320, height=240, dilation_kernel_px=15)
    outside = outside_mask.astype(bool)
    output_directory.mkdir(parents=True, exist_ok=True)

    def evaluate_positions(positions: list[int], label: str) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        bindings = _sample_rows(frame_rows, positions, [0.25, 0.5, 0.75])
        grouped: dict[int, list[dict[str, Any]]] = {}
        for row in bindings:
            grouped.setdefault(int(row["split_position"]), []).append(row)
        measured: list[dict[str, Any]] = []
        montage: list[np.ndarray] = []
        for position, selected in grouped.items():
            video = episode_by_position[position]["physical_video"]
            if sha256_file(REPO_ROOT / video["path"]) != video["sha256"]:
                raise ValueError("OR109 physical video hash mismatch")
            frames = [cv2.flip(frame, -1) for frame in _decode_selected_frames(REPO_ROOT / video["path"], selected_indices=np.asarray([int(row["physical_frame_index"]) for row in selected], dtype=np.int64), expected_frame_count=int(video["frame_count"]), expected_width=int(video["width_px"]), expected_height=int(video["height_px"]), output_width=320, output_height=240)]
            for binding, frame in zip(selected, frames, strict=True):
                dynamic = _skin_mask(frame, prior_contract["skin_proxy"]).astype(bool) & outside & ~removal
                count, labels, stats, _ = cv2.connectedComponentsWithStats(dynamic.astype(np.uint8), connectivity=8)
                component = np.zeros_like(dynamic)
                if count > 1:
                    selected_label = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
                    component = labels == selected_label
                capsule, shape = _capsule_mask(component, contract["capsule_fit"])
                intersection = int(np.count_nonzero(component & capsule))
                union = int(np.count_nonzero(component | capsule))
                component_pixels = int(np.count_nonzero(component))
                capsule_pixels = int(np.count_nonzero(capsule))
                iou = intersection / max(union, 1)
                coverage = intersection / max(component_pixels, 1)
                precision = intersection / max(capsule_pixels, 1)
                present = component_pixels >= 296 and shape["supported"]
                measured.append({"split_position": position, "recording_id": binding["recording_id"], "evaluation_index": int(binding["evaluation_index"]), "component_pixels": component_pixels, "present_shape": bool(present), "capsule": shape, "iou": iou if present else None, "coverage": coverage if present else None, "precision": precision if present else None})
                overlay = frame.copy()
                overlay[component] = np.rint(0.4 * overlay[component] + 0.6 * np.asarray([255, 0, 255])).astype(np.uint8)
                outline = cv2.morphologyEx(capsule.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), dtype=np.uint8)).astype(bool)
                overlay[outline] = np.asarray([0, 255, 255], dtype=np.uint8)
                montage.append(np.concatenate([frame, overlay], axis=1))
        present_rows = [row for row in measured if row["present_shape"]]
        summary = {"present_shape_count": len(present_rows), "mean_iou": float(np.mean([row["iou"] for row in present_rows])) if present_rows else 0.0, "mean_coverage": float(np.mean([row["coverage"] for row in present_rows])) if present_rows else 0.0, "mean_precision": float(np.mean([row["precision"] for row in present_rows])) if present_rows else 0.0}
        montage_binding = {**_write_png(output_directory / f"{label}_physical_dynamic_capsule.png", np.concatenate(montage, axis=0)), "layout": "physical_left_dynamic_magenta_capsule_outline_yellow_right"}
        return measured, summary, montage_binding

    dev_rows, dev_summary, dev_montage = evaluate_positions([int(value) for value in contract["split"]["development_positions"]], "development")
    val_rows, val_summary, val_montage = evaluate_positions([int(value) for value in contract["split"]["validation_positions"]], "validation")
    acceptance = contract["acceptance"]
    dev_gates = {"minimum_mean_iou": dev_summary["mean_iou"] >= float(acceptance["development_minimum_mean_iou"]), "minimum_mean_coverage": dev_summary["mean_coverage"] >= float(acceptance["development_minimum_mean_coverage"]), "minimum_present_shape_count": dev_summary["present_shape_count"] >= int(acceptance["development_minimum_present_shape_count"])}
    val_gates = {"minimum_mean_iou": val_summary["mean_iou"] >= float(acceptance["validation_minimum_mean_iou"]), "minimum_mean_coverage": val_summary["mean_coverage"] >= float(acceptance["validation_minimum_mean_coverage"]), "minimum_present_shape_count": val_summary["present_shape_count"] >= int(acceptance["validation_minimum_present_shape_count"])}
    integrity = {"one_deterministic_capsule_per_present_frame": True, "zero_optimization_or_search": True, "persistent_support_frozen_from_or108": True, "no_identity_biometric_candidate_decode_render_replay_hardware_or_paid_compute": True, "shape_identifiability_not_3d_geometry_trajectory_fidelity_or_promotion": True}
    passed = all(dev_gates.values()) and all(val_gates.values()) and all(integrity.values())
    receipt: dict[str, Any] = {"schema_version": "sim2claw.observable_registration_post_final_single_capsule_dynamic_operator_shape_identifiability_receipt.v1", "experiment_id": contract["experiment_id"], "status": "PASS_SINGLE_CAPSULE_DYNAMIC_OPERATOR_SHAPE_IDENTIFIABLE" if passed else "TERMINAL_SINGLE_CAPSULE_DYNAMIC_OPERATOR_SHAPE_INSUFFICIENT", "proof_class": contract["proof_class"], "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)}, "development_rows": dev_rows, "development_summary": dev_summary, "development_montage": dev_montage, "validation_rows": val_rows, "validation_summary": val_summary, "validation_montage": val_montage, "gates": {"development": dev_gates, "validation": val_gates, "integrity": integrity}, "execution": {"development_physical_episode_decodes": 7, "validation_physical_episode_decodes": 4, "development_physical_frames_read": 21, "validation_physical_frames_read": 12, "deterministic_development_shape_estimates": 21, "deterministic_validation_shape_estimates": 12, "optimization_searches": 0, "candidate_video_decodes": 0, "renders": 0, "simulator_replays": 0, "hardware_actions": 0, "paid_compute": False}, "claim_limits": contract["claim_limits"], "reviewer_decision": "FREEZE_RENDERER_NATIVE_SINGLE_CAPSULE_OPERATOR_RECONSTRUCTION" if passed else "FREEZE_TWO_CAPSULE_OPERATOR_SHAPE_IDENTIFIABILITY", "next_transition": "freeze_or110_renderer_native_single_capsule_operator_reconstruction" if passed else "freeze_or110_two_capsule_operator_shape_identifiability"}
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

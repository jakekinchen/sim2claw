"""Subtract development-persistent color support before operator-content attribution."""

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
SCHEMA = "sim2claw.observable_registration_post_final_persistence_subtracted_dynamic_operator_proxy_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_final_persistence_subtracted_dynamic_operator_proxy_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_final_persistence_subtracted_dynamic_operator_proxy_v1"


def load_post_final_persistence_subtracted_dynamic_operator_proxy_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR108 contract")
    for source in contract["sources"].values():
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    split = contract["split"]
    if split["development_positions"] != list(range(1, 8)) or split["validation_positions"] != list(range(8, 12)):
        raise ValueError("OR108 split drifted")
    if split["persistent_support_fit_on_development_only"] is not True or split["validation_uses_frozen_persistent_support"] is not True:
        raise ValueError("OR108 fit/validation boundary drifted")
    support = contract["persistent_support"]
    if support != {"minimum_development_occupancy_fraction": 0.8, "removal_dilation_kernel_px": 5, "one_global_pixel_support": True, "validation_refit": False}:
        raise ValueError("OR108 persistent-support family drifted")
    expected = {"development_physical_episode_decodes_allowed": 7, "validation_physical_episode_decodes_allowed": 4, "development_physical_frames_read_allowed": 21, "validation_physical_frames_read_allowed": 12, "persistent_support_fits_allowed": 1, "validation_refits_allowed": 0, "candidate_video_decodes_allowed": 0, "renders_allowed": 0, "simulator_replays_allowed": 0, "action_or_state_mutations_allowed": 0, "hardware_actions_allowed": 0, "paid_compute_allowed": False}
    if contract["resource_boundary"] != expected or any(contract["authority"].values()):
        raise ValueError("OR108 resource or authority boundary drifted")
    if contract["claim_limits"]["operator_geometry_or_trajectory_calibrated"] is not False or contract["claim_limits"]["same_video_semantic_match"] is not False:
        raise ValueError("OR108 claim boundary drifted")
    return contract


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR108 one-run receipt already exists")
    contract = load_post_final_persistence_subtracted_dynamic_operator_proxy_contract(contract_path)
    closeout = json.loads((REPO_ROOT / contract["sources"]["or107_closeout"]["path"]).read_text())
    if closeout["reviewer_decision"] != "REJECT_GENERIC_PROXY_AND_FREEZE_DEVELOPMENT_PERSISTENCE_SUBTRACTED_DYNAMIC_PROXY":
        raise ValueError("OR107 did not authorize persistence subtraction")
    prior_contract = json.loads((REPO_ROOT / contract["sources"]["or107_contract"]["path"]).read_text())
    proxy = prior_contract["skin_proxy"]
    or95 = json.loads((REPO_ROOT / contract["sources"]["or95_contract"]["path"]).read_text())
    episode_by_position = {int(row["split_position"]): row for row in _episode_inventory(or95)}
    frame_rows = json.loads((REPO_ROOT / contract["sources"]["or95_frame_rows"]["path"]).read_text())["rows"]
    _, outside_mask = _region_masks(np.asarray([[-3.0, 66.5], [79.0, 52.0], [176.0, 144.5], [71.5, 193.0]], dtype=np.float64), width=320, height=240, dilation_kernel_px=15)
    outside = outside_mask.astype(bool)
    output_directory.mkdir(parents=True, exist_ok=True)

    def decode(positions: list[int]) -> list[dict[str, Any]]:
        bindings = _sample_rows(frame_rows, positions, [0.25, 0.5, 0.75])
        grouped: dict[int, list[dict[str, Any]]] = {}
        for row in bindings:
            grouped.setdefault(int(row["split_position"]), []).append(row)
        result: list[dict[str, Any]] = []
        for position, selected in grouped.items():
            video = episode_by_position[position]["physical_video"]
            if sha256_file(REPO_ROOT / video["path"]) != video["sha256"]:
                raise ValueError("OR108 physical video hash mismatch")
            frames = [cv2.flip(frame, -1) for frame in _decode_selected_frames(REPO_ROOT / video["path"], selected_indices=np.asarray([int(row["physical_frame_index"]) for row in selected], dtype=np.int64), expected_frame_count=int(video["frame_count"]), expected_width=int(video["width_px"]), expected_height=int(video["height_px"]), output_width=320, output_height=240)]
            for binding, frame in zip(selected, frames, strict=True):
                result.append({"binding": binding, "frame": frame, "skin": _skin_mask(frame, proxy).astype(bool) & outside})
        return sorted(result, key=lambda row: (int(row["binding"]["split_position"]), int(row["binding"]["evaluation_index"])))

    development_positions = [int(value) for value in contract["split"]["development_positions"]]
    validation_positions = [int(value) for value in contract["split"]["validation_positions"]]
    development = decode(development_positions)
    occupancy = np.mean(np.stack([row["skin"] for row in development], axis=0), axis=0)
    persistent = (occupancy >= float(contract["persistent_support"]["minimum_development_occupancy_fraction"])) & outside
    removal = cv2.dilate(persistent.astype(np.uint8) * 255, np.ones((int(contract["persistent_support"]["removal_dilation_kernel_px"]),) * 2, dtype=np.uint8)).astype(bool) & outside
    persistent_fraction = float(np.count_nonzero(persistent) / max(np.count_nonzero(outside), 1))
    persistent_binding = _write_png(output_directory / "development_persistent_support.png", persistent.astype(np.uint8) * 255)
    edge_spec = contract["metric"]["physical_edge"]
    presence = contract["metric"]["presence"]
    association_kernel = np.ones((int(contract["metric"]["dynamic_edge_association_dilation_kernel_px"]),) * 2, dtype=np.uint8)

    def measure(rows: list[dict[str, Any]], label: str) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        measured: list[dict[str, Any]] = []
        montages: list[np.ndarray] = []
        for row in rows:
            dynamic = row["skin"] & ~removal
            associated = cv2.dilate(dynamic.astype(np.uint8) * 255, association_kernel).astype(bool) & outside
            gray = cv2.cvtColor(row["frame"], cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, int(edge_spec["canny_low_threshold"]), int(edge_spec["canny_high_threshold"])).astype(bool) & outside
            area_fraction = float(np.count_nonzero(dynamic) / max(np.count_nonzero(outside), 1))
            edge_fraction = float(np.count_nonzero(edges & associated) / max(np.count_nonzero(edges), 1))
            binding = row["binding"]
            measured.append({"split_position": int(binding["split_position"]), "recording_id": binding["recording_id"], "evaluation_index": int(binding["evaluation_index"]), "dynamic_proxy_pixels": int(np.count_nonzero(dynamic)), "dynamic_area_fraction_outside_board": area_fraction, "dynamic_edge_fraction_outside_board": edge_fraction, "dynamic_operator_proxy_present": bool(area_fraction >= float(presence["minimum_dynamic_area_fraction"]) and edge_fraction >= float(presence["minimum_dynamic_edge_fraction"]))})
            overlay = row["frame"].copy()
            overlay[persistent] = np.rint(0.55 * overlay[persistent] + 0.45 * np.asarray([255, 255, 0])).astype(np.uint8)
            overlay[dynamic] = np.rint(0.35 * overlay[dynamic] + 0.65 * np.asarray([255, 0, 255])).astype(np.uint8)
            montages.append(np.concatenate([row["frame"], overlay], axis=1))
        summary = {"mean_dynamic_area_fraction_outside_board": float(np.mean([row["dynamic_area_fraction_outside_board"] for row in measured])), "mean_dynamic_edge_fraction_outside_board": float(np.mean([row["dynamic_edge_fraction_outside_board"] for row in measured])), "present_samples": sum(row["dynamic_operator_proxy_present"] for row in measured)}
        montage = {**_write_png(output_directory / f"{label}_physical_persistent_dynamic_proxy.png", np.concatenate(montages, axis=0)), "layout": "physical_left_persistent_cyan_dynamic_magenta_right"}
        return measured, summary, montage

    development_rows, development_summary, development_montage = measure(development, "development")
    validation = decode(validation_positions)
    validation_rows, validation_summary, validation_montage = measure(validation, "validation")
    acceptance = contract["acceptance"]
    development_gates = {"minimum_mean_dynamic_area_fraction": development_summary["mean_dynamic_area_fraction_outside_board"] >= float(acceptance["development_minimum_mean_dynamic_area_fraction"]), "minimum_mean_dynamic_edge_fraction": development_summary["mean_dynamic_edge_fraction_outside_board"] >= float(acceptance["development_minimum_mean_dynamic_edge_fraction"]), "minimum_present_samples": development_summary["present_samples"] >= int(acceptance["development_minimum_present_samples"])}
    validation_gates = {"minimum_mean_dynamic_area_fraction": validation_summary["mean_dynamic_area_fraction_outside_board"] >= float(acceptance["validation_minimum_mean_dynamic_area_fraction"]), "minimum_mean_dynamic_edge_fraction": validation_summary["mean_dynamic_edge_fraction_outside_board"] >= float(acceptance["validation_minimum_mean_dynamic_edge_fraction"]), "minimum_present_samples": validation_summary["present_samples"] >= int(acceptance["validation_minimum_present_samples"])}
    integrity_gates = {"persistent_support_area_in_bounds": float(acceptance["minimum_persistent_support_area_fraction"]) <= persistent_fraction <= float(acceptance["maximum_persistent_support_area_fraction"]), "exact_development_sample_count": len(development_rows) == int(contract["gates"]["expected_development_sample_count"]), "exact_validation_sample_count": len(validation_rows) == int(contract["gates"]["expected_validation_sample_count"]), "one_development_fitted_support_and_zero_validation_refits": True, "no_identity_or_biometric_inference": True, "no_candidate_decode_render_replay_action_state_mutation_hardware_or_paid_compute": True, "diagnostic_not_geometry_trajectory_fidelity_transfer_or_promotion": True}
    passed = all(development_gates.values()) and all(validation_gates.values()) and all(integrity_gates.values())
    receipt: dict[str, Any] = {"schema_version": "sim2claw.observable_registration_post_final_persistence_subtracted_dynamic_operator_proxy_receipt.v1", "experiment_id": contract["experiment_id"], "status": "PASS_DYNAMIC_OPERATOR_PROXY_VALIDATED" if passed else "TERMINAL_DYNAMIC_OPERATOR_PROXY_INSUFFICIENT", "proof_class": contract["proof_class"], "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)}, "persistent_support": {"area_fraction_outside_board": persistent_fraction, **persistent_binding}, "development_rows": development_rows, "development_summary": development_summary, "development_montage": development_montage, "validation_rows": validation_rows, "validation_summary": validation_summary, "validation_montage": validation_montage, "gates": {"development": development_gates, "validation": validation_gates, "integrity": integrity_gates}, "execution": {"development_physical_episode_decodes": 7, "validation_physical_episode_decodes": 4, "development_physical_frames_read": 21, "validation_physical_frames_read": 12, "persistent_support_fits": 1, "validation_refits": 0, "candidate_video_decodes": 0, "renders": 0, "simulator_replays": 0, "action_or_state_mutations": 0, "hardware_actions": 0, "paid_compute": False}, "claim_limits": contract["claim_limits"], "reviewer_decision": "FREEZE_RENDERER_NATIVE_EXOGENOUS_OPERATOR_PROXY" if passed else "STOP_DYNAMIC_OPERATOR_PROXY_LANE", "next_transition": "freeze_or109_renderer_native_exogenous_operator_proxy" if passed else "stop_dynamic_operator_proxy_lane"}
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

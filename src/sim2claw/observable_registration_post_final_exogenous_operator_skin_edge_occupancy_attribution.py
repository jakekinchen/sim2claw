"""Attribute physical-only operator content with one fixed generic skin-color proxy."""

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
from .observable_registration_post_final_independent_robot_base_full_corpus_diagnostic import _episode_inventory
from .observable_registration_post_final_legacy_photo_background_ablation import _write_png
from .observable_registration_post_final_shared_shoulder_lift_articulation_calibration import _sample_rows


cv2.ocl.setUseOpenCL(False)

SCHEMA = "sim2claw.observable_registration_post_final_exogenous_operator_skin_edge_occupancy_attribution_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_final_exogenous_operator_skin_edge_occupancy_attribution_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_final_exogenous_operator_skin_edge_occupancy_attribution_v1"


def load_post_final_exogenous_operator_skin_edge_occupancy_attribution_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR107 contract")
    for source in contract["sources"].values():
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    split = contract["split"]
    if split["development_positions"] != list(range(1, 8)) or split["validation_positions"] != list(range(8, 12)):
        raise ValueError("OR107 split drifted")
    if split["validation_decode_requires_development_gate"] is not True or split["validation_never_changes_proxy_or_thresholds"] is not True:
        raise ValueError("OR107 validation boundary drifted")
    if contract["sampling"]["within_episode_quantiles"] != [0.25, 0.5, 0.75] or contract["sampling"]["samples_per_episode"] != 3:
        raise ValueError("OR107 sample family drifted")
    proxy = contract["skin_proxy"]
    if proxy["combination"] != "hsv_and_ycrcb" or proxy["board_region_excluded"] is not True or proxy["generic_color_proxy_not_person_identity_or_biometric_inference"] is not True:
        raise ValueError("OR107 proxy boundary drifted")
    expected = {
        "development_physical_episode_decodes_allowed": 7,
        "validation_physical_episode_decodes_allowed_if_development_passes": 4,
        "development_physical_frames_read_allowed": 21,
        "validation_physical_frames_read_allowed_if_development_passes": 12,
        "candidate_video_decodes_allowed": 0,
        "renders_allowed": 0,
        "fits_allowed": 0,
        "parameter_values_allowed": 0,
        "simulator_replays_allowed": 0,
        "action_or_state_mutations_allowed": 0,
        "hardware_actions_allowed": 0,
        "paid_compute_allowed": False,
    }
    if contract["resource_boundary"] != expected or any(contract["authority"].values()):
        raise ValueError("OR107 resource or authority boundary drifted")
    claims = contract["claim_limits"]
    if claims["person_identity_or_biometric_inference"] is not False or claims["operator_geometry_or_trajectory_calibrated"] is not False or claims["same_video_semantic_match"] is not False:
        raise ValueError("OR107 claim boundary drifted")
    return contract


def _skin_mask(frame: np.ndarray, proxy: dict[str, Any]) -> np.ndarray:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
    hsv_spec = proxy["hsv"]
    ycc_spec = proxy["ycrcb"]
    hsv_mask = cv2.inRange(
        hsv,
        np.asarray([hsv_spec["h_min"], hsv_spec["s_min"], hsv_spec["v_min"]], dtype=np.uint8),
        np.asarray([hsv_spec["h_max"], hsv_spec["s_max"], hsv_spec["v_max"]], dtype=np.uint8),
    )
    ycc_mask = cv2.inRange(
        ycrcb,
        np.asarray([0, ycc_spec["cr_min"], ycc_spec["cb_min"]], dtype=np.uint8),
        np.asarray([255, ycc_spec["cr_max"], ycc_spec["cb_max"]], dtype=np.uint8),
    )
    mask = cv2.bitwise_and(hsv_mask, ycc_mask)
    open_size = int(proxy["morphological_open_kernel_px"])
    close_size = int(proxy["morphological_close_kernel_px"])
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((open_size, open_size), dtype=np.uint8))
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((close_size, close_size), dtype=np.uint8))


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR107 one-run receipt already exists")
    contract = load_post_final_exogenous_operator_skin_edge_occupancy_attribution_contract(contract_path)
    or106 = json.loads((REPO_ROOT / contract["sources"]["or106_closeout"]["path"]).read_text())
    if or106["reviewer_decision"] != "REJECT_TWO_CLASS_ROBOT_MATERIAL_PALETTE_AND_ATTRIBUTE_EXOGENOUS_OPERATIONAL_CONTENT":
        raise ValueError("OR106 did not authorize operator-content attribution")
    or95_contract = json.loads((REPO_ROOT / contract["sources"]["or95_contract"]["path"]).read_text())
    episodes = _episode_inventory(or95_contract)
    episode_by_position = {int(row["split_position"]): row for row in episodes}
    frame_rows = json.loads((REPO_ROOT / contract["sources"]["or95_frame_rows"]["path"]).read_text())["rows"]
    board_mask, outside_mask = _region_masks(
        np.asarray([[-3.0, 66.5], [79.0, 52.0], [176.0, 144.5], [71.5, 193.0]], dtype=np.float64),
        width=320,
        height=240,
        dilation_kernel_px=15,
    )
    outside_bool = outside_mask.astype(bool)
    proxy = contract["skin_proxy"]
    edge = contract["metric"]["physical_edge"]
    presence = contract["metric"]["presence"]
    output_directory.mkdir(parents=True, exist_ok=True)

    def evaluate_positions(positions: list[int], label: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        bindings = _sample_rows(frame_rows, positions, [float(value) for value in contract["sampling"]["within_episode_quantiles"]])
        grouped: dict[int, list[dict[str, Any]]] = {}
        for binding in bindings:
            grouped.setdefault(int(binding["split_position"]), []).append(binding)
        rows: list[dict[str, Any]] = []
        montage_rows: list[np.ndarray] = []
        for position, selected in grouped.items():
            episode = episode_by_position[position]
            video = episode["physical_video"]
            if sha256_file(REPO_ROOT / video["path"]) != video["sha256"]:
                raise ValueError("OR107 physical video hash mismatch")
            frames = [
                cv2.flip(frame, -1)
                for frame in _decode_selected_frames(
                    REPO_ROOT / video["path"],
                    selected_indices=np.asarray([int(row["physical_frame_index"]) for row in selected], dtype=np.int64),
                    expected_frame_count=int(video["frame_count"]),
                    expected_width=int(video["width_px"]),
                    expected_height=int(video["height_px"]),
                    output_width=320,
                    output_height=240,
                )
            ]
            for binding, frame in zip(selected, frames, strict=True):
                skin = _skin_mask(frame, proxy)
                skin_bool = skin.astype(bool) & outside_bool
                associated = cv2.dilate(skin, np.ones((int(proxy["edge_association_dilation_kernel_px"]),) * 2, dtype=np.uint8)).astype(bool) & outside_bool
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                physical_edges = cv2.Canny(gray, int(edge["canny_low_threshold"]), int(edge["canny_high_threshold"])).astype(bool) & outside_bool
                area_fraction = float(np.count_nonzero(skin_bool) / max(np.count_nonzero(outside_bool), 1))
                edge_fraction = float(np.count_nonzero(physical_edges & associated) / max(np.count_nonzero(physical_edges), 1))
                components, _, stats, _ = cv2.connectedComponentsWithStats(skin_bool.astype(np.uint8), connectivity=8)
                largest = 0 if components <= 1 else int(np.max(stats[1:, cv2.CC_STAT_AREA]))
                is_present = area_fraction >= float(presence["minimum_skin_area_fraction"]) and edge_fraction >= float(presence["minimum_skin_associated_edge_fraction"])
                rows.append({
                    "split_position": position,
                    "recording_id": binding["recording_id"],
                    "evaluation_index": int(binding["evaluation_index"]),
                    "physical_frame_index": int(binding["physical_frame_index"]),
                    "skin_proxy_pixel_count_outside_board": int(np.count_nonzero(skin_bool)),
                    "skin_area_fraction_outside_board": area_fraction,
                    "physical_edge_pixel_count_outside_board": int(np.count_nonzero(physical_edges)),
                    "skin_associated_edge_fraction_outside_board": edge_fraction,
                    "largest_skin_proxy_component_pixels": largest,
                    "operator_proxy_present": bool(is_present),
                })
                overlay = frame.copy()
                overlay[skin_bool] = np.rint(0.45 * overlay[skin_bool] + 0.55 * np.asarray([255, 0, 255])).astype(np.uint8)
                montage_rows.append(np.concatenate([frame, overlay], axis=1))
        montage = _write_png(output_directory / f"{label}_physical_skin_proxy.png", np.concatenate(montage_rows, axis=0))
        return rows, {**montage, "layout": "physical_left_skin_proxy_overlay_right"}

    development_positions = [int(value) for value in contract["split"]["development_positions"]]
    development_rows, development_montage = evaluate_positions(development_positions, "development")
    development_summary = {
        "mean_skin_area_fraction_outside_board": float(np.mean([row["skin_area_fraction_outside_board"] for row in development_rows])),
        "mean_skin_associated_edge_fraction_outside_board": float(np.mean([row["skin_associated_edge_fraction_outside_board"] for row in development_rows])),
        "present_samples": sum(row["operator_proxy_present"] for row in development_rows),
    }
    acceptance = contract["acceptance"]
    development_gates = {
        "minimum_mean_skin_area_fraction": development_summary["mean_skin_area_fraction_outside_board"] >= float(acceptance["development_minimum_mean_skin_area_fraction"]),
        "minimum_mean_skin_associated_edge_fraction": development_summary["mean_skin_associated_edge_fraction_outside_board"] >= float(acceptance["development_minimum_mean_skin_associated_edge_fraction"]),
        "minimum_present_samples": development_summary["present_samples"] >= int(acceptance["development_minimum_present_samples"]),
    }
    development_passed = all(development_gates.values())
    validation_rows: list[dict[str, Any]] = []
    validation_summary: dict[str, Any] | None = None
    validation_gates: dict[str, bool] | None = None
    validation_montage: dict[str, Any] | None = None
    if development_passed:
        validation_positions = [int(value) for value in contract["split"]["validation_positions"]]
        validation_rows, validation_montage = evaluate_positions(validation_positions, "validation")
        validation_summary = {
            "mean_skin_area_fraction_outside_board": float(np.mean([row["skin_area_fraction_outside_board"] for row in validation_rows])),
            "mean_skin_associated_edge_fraction_outside_board": float(np.mean([row["skin_associated_edge_fraction_outside_board"] for row in validation_rows])),
            "present_samples": sum(row["operator_proxy_present"] for row in validation_rows),
        }
        validation_gates = {
            "minimum_mean_skin_area_fraction": validation_summary["mean_skin_area_fraction_outside_board"] >= float(acceptance["validation_minimum_mean_skin_area_fraction"]),
            "minimum_mean_skin_associated_edge_fraction": validation_summary["mean_skin_associated_edge_fraction_outside_board"] >= float(acceptance["validation_minimum_mean_skin_associated_edge_fraction"]),
            "minimum_present_samples": validation_summary["present_samples"] >= int(acceptance["validation_minimum_present_samples"]),
        }
    validation_passed = validation_gates is not None and all(validation_gates.values())
    integrity_gates = {
        "exact_development_sample_count": len(development_rows) == int(contract["gates"]["expected_development_sample_count"]),
        "validation_condition_and_count_respected": (len(validation_rows) == int(contract["gates"]["expected_validation_sample_count"])) == development_passed,
        "one_fixed_generic_color_proxy": True,
        "board_region_excluded": True,
        "no_person_identity_or_biometric_inference": True,
        "no_candidate_decode_render_fit_parameter_replay_action_state_mutation_hardware_or_paid_compute": True,
        "operator_content_attribution_not_geometry_trajectory_fidelity_transfer_or_promotion": True,
    }
    passed = development_passed and validation_passed and all(integrity_gates.values())
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_post_final_exogenous_operator_skin_edge_occupancy_attribution_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": "PASS_EXOGENOUS_OPERATOR_CONTENT_MATERIALLY_PRESENT" if passed else "TERMINAL_EXOGENOUS_OPERATOR_CONTENT_PROXY_INSUFFICIENT",
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "development_rows": development_rows,
        "development_summary": development_summary,
        "development_montage": development_montage,
        "validation_rows": validation_rows,
        "validation_summary": validation_summary,
        "validation_montage": validation_montage,
        "gates": {"development": development_gates, "validation": validation_gates, "integrity": integrity_gates},
        "execution": {"development_physical_episode_decodes": len(development_positions), "validation_physical_episode_decodes": 4 if development_passed else 0, "development_physical_frames_read": len(development_rows), "validation_physical_frames_read": len(validation_rows), "candidate_video_decodes": 0, "renders": 0, "fits": 0, "parameter_values": 0, "simulator_replays": 0, "action_or_state_mutations": 0, "hardware_actions": 0, "paid_compute": False},
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": "FREEZE_DETERMINISTIC_EXOGENOUS_OPERATOR_PROXY_DIAGNOSTIC" if passed else "STOP_OPERATOR_PROXY_LANE",
        "next_transition": "freeze_or108_deterministic_exogenous_operator_proxy_diagnostic" if passed else "stop_operator_proxy_lane",
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

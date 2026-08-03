"""Attribute OR116's appearance miss between shaft and terminal materials."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, sha256_file
from .observable_registration_post_final_legacy_photo_background_ablation import _write_png


cv2.ocl.setUseOpenCL(False)
SCHEMA = "sim2claw.observable_registration_post_final_finite_linear_object_appearance_failure_attribution_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_final_finite_linear_object_appearance_failure_attribution_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_final_finite_linear_object_appearance_failure_attribution_v1"


def load_post_final_finite_linear_object_appearance_failure_attribution_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR117 contract")
    for source in contract["sources"].values():
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    montage = contract["montage"]
    if montage["row_count"] != 7 or montage["panel_order"] != ["physical", "or95_baseline", "or116_candidate"] or montage["development_only"] is not True:
        raise ValueError("OR117 montage contract drifted")
    support = contract["support"]
    if support["terminal_disk_radius_multiplier"] != 1.5 or support["validation_pixels_allowed"] is not False:
        raise ValueError("OR117 partition drifted")
    resources = contract["resource_boundary"]
    if resources["validation_pixel_reads_allowed"] != 0 or resources["source_video_decodes_allowed"] != 0 or resources["renders_allowed"] != 0 or resources["fits_or_candidate_searches_allowed"] != 0 or resources["geometry_or_material_mutations_allowed"] != 0 or resources["paid_compute_allowed"] is not False or any(contract["authority"].values()):
        raise ValueError("OR117 resource or authority boundary drifted")
    if contract["claim_limits"]["two_material_candidate_validated"] is not False or contract["claim_limits"]["same_video_semantic_match"] is not False:
        raise ValueError("OR117 claim boundary drifted")
    return contract


def _partition_support(baseline: np.ndarray, candidate: np.ndarray, center: np.ndarray, radius: float, spec: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    support = np.max(np.abs(candidate.astype(np.int16) - baseline.astype(np.int16)), axis=2) >= int(spec["candidate_minus_baseline_minimum_max_channel_difference"])
    yy, xx = np.indices(support.shape)
    terminal = support & (np.square(xx - float(center[0])) + np.square(yy - float(center[1])) <= np.square(float(radius) * float(spec["terminal_disk_radius_multiplier"])))
    shaft = support & ~terminal
    return support, shaft, terminal


def _region_metrics(physical: np.ndarray, baseline: np.ndarray, candidate: np.ndarray, mask: np.ndarray) -> dict[str, Any]:
    if not np.any(mask):
        raise ValueError("OR117 empty appearance region")
    physical_pixels = physical[mask].astype(np.float64)
    baseline_pixels = baseline[mask].astype(np.float64)
    candidate_pixels = candidate[mask].astype(np.float64)
    physical_gray = cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY).astype(np.float64)[mask]
    candidate_gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY).astype(np.float64)[mask]
    return {
        "pixel_count": int(np.count_nonzero(mask)),
        "physical_target_median_bgr": np.median(physical_pixels, axis=0).tolist(),
        "physical_target_mean_bgr": np.mean(physical_pixels, axis=0).tolist(),
        "candidate_mean_bgr": np.mean(candidate_pixels, axis=0).tolist(),
        "signed_physical_minus_candidate_grayscale": float(np.mean(physical_gray - candidate_gray)),
        "baseline_mean_absolute_bgr_residual": float(np.mean(np.abs(physical_pixels - baseline_pixels))),
        "candidate_mean_absolute_bgr_residual": float(np.mean(np.abs(physical_pixels - candidate_pixels))),
    }


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR117 one-run receipt already exists")
    contract = load_post_final_finite_linear_object_appearance_failure_attribution_contract(contract_path)
    closeout = json.loads((REPO_ROOT / contract["sources"]["or116_closeout"]["path"]).read_text())
    if closeout["reviewer_decision"] != "REJECT_SINGLE_MATERIAL_FINITE_LINEAR_OBJECT_AND_ATTRIBUTE_APPEARANCE_FAILURE":
        raise ValueError("OR116 did not authorize appearance attribution")
    or116 = json.loads((REPO_ROOT / contract["sources"]["or116_receipt"]["path"]).read_text())
    if or116["artifact_sha256"] != contract["sources"]["or116_receipt"]["artifact_sha256"] or or116["validation_rows"]:
        raise ValueError("OR116 identity drifted or validation was opened")
    montage = cv2.imread(str(REPO_ROOT / contract["sources"]["or116_development_montage"]["path"]), cv2.IMREAD_COLOR)
    spec = contract["montage"]
    width, row_height, row_count = int(spec["panel_width_px"]), int(spec["row_height_px"]), int(spec["row_count"])
    if montage is None or montage.shape != (row_height * row_count, width * 3, 3):
        raise ValueError("OR117 montage dimensions drifted")
    center = np.asarray(or116["shape"]["terminal_center_px"], dtype=np.float64)
    radius = float(or116["shape"]["terminal_radius_px"])
    shaft_physical: list[np.ndarray] = []
    shaft_baseline: list[np.ndarray] = []
    shaft_candidate: list[np.ndarray] = []
    terminal_physical: list[np.ndarray] = []
    terminal_baseline: list[np.ndarray] = []
    terminal_candidate: list[np.ndarray] = []
    diagnostic_rows: list[np.ndarray] = []
    per_row: list[dict[str, Any]] = []
    for row_index in range(row_count):
        row = montage[row_index * row_height : (row_index + 1) * row_height]
        physical, baseline, candidate = row[:, :width], row[:, width : 2 * width], row[:, 2 * width :]
        support, shaft, terminal = _partition_support(baseline, candidate, center, radius, contract["support"])
        shaft_physical.append(physical[shaft]); shaft_baseline.append(baseline[shaft]); shaft_candidate.append(candidate[shaft])
        terminal_physical.append(physical[terminal]); terminal_baseline.append(baseline[terminal]); terminal_candidate.append(candidate[terminal])
        overlay = physical.copy()
        overlay[shaft] = (0, 255, 255)
        overlay[terminal] = (255, 0, 255)
        diagnostic_rows.append(np.concatenate([physical, overlay], axis=1))
        per_row.append({"row_index": row_index, "candidate_support_pixels": int(np.count_nonzero(support)), "shaft_pixels": int(np.count_nonzero(shaft)), "terminal_pixels": int(np.count_nonzero(terminal))})

    def joined_metrics(physical_parts: list[np.ndarray], baseline_parts: list[np.ndarray], candidate_parts: list[np.ndarray]) -> dict[str, Any]:
        physical = np.concatenate(physical_parts, axis=0).reshape((-1, 1, 3)).astype(np.uint8)
        baseline = np.concatenate(baseline_parts, axis=0).reshape((-1, 1, 3)).astype(np.uint8)
        candidate = np.concatenate(candidate_parts, axis=0).reshape((-1, 1, 3)).astype(np.uint8)
        mask = np.ones(physical.shape[:2], dtype=bool)
        return _region_metrics(physical, baseline, candidate, mask)

    shaft_metrics = joined_metrics(shaft_physical, shaft_baseline, shaft_candidate)
    terminal_metrics = joined_metrics(terminal_physical, terminal_baseline, terminal_candidate)
    shaft_target = np.asarray(shaft_metrics["physical_target_median_bgr"], dtype=np.float64)
    terminal_target = np.asarray(terminal_metrics["physical_target_median_bgr"], dtype=np.float64)
    separation = float(np.linalg.norm(shaft_target - terminal_target))
    acceptance = contract["acceptance"]
    signed_shaft = float(shaft_metrics["signed_physical_minus_candidate_grayscale"])
    signed_terminal = float(terminal_metrics["signed_physical_minus_candidate_grayscale"])
    gates = {
        "minimum_aggregate_shaft_pixels": shaft_metrics["pixel_count"] >= int(acceptance["minimum_aggregate_shaft_pixels"]),
        "minimum_aggregate_terminal_pixels": terminal_metrics["pixel_count"] >= int(acceptance["minimum_aggregate_terminal_pixels"]),
        "minimum_target_bgr_euclidean_separation": separation >= float(acceptance["minimum_target_bgr_euclidean_separation"]),
        "minimum_absolute_signed_shaft_residual": abs(signed_shaft) >= float(acceptance["minimum_absolute_signed_grayscale_residual_each_region"]),
        "minimum_absolute_signed_terminal_residual": abs(signed_terminal) >= float(acceptance["minimum_absolute_signed_grayscale_residual_each_region"]),
        "opposite_signed_grayscale_residuals": signed_shaft * signed_terminal < 0.0,
        "or116_local_edge_gain_preserves_geometry": float(or116["development_summary"]["mean_object_roi_edge_f1_delta"]) >= float(acceptance["or116_minimum_local_edge_delta_for_geometry_preservation"]),
    }
    passed = all(gates.values())
    status = "PASS_FINITE_LINEAR_OBJECT_TWO_MATERIAL_APPEARANCE_FACTOR_IDENTIFIED" if passed else "TERMINAL_FINITE_LINEAR_OBJECT_APPEARANCE_FAILURE_UNRESOLVED"
    reviewer_decision = "FREEZE_TWO_MATERIAL_SHAFT_TERMINAL_CALIBRATION" if passed else "FREEZE_PROJECTED_AREA_AND_COVERAGE_ATTRIBUTION"
    next_transition = "freeze_or118_two_material_shaft_terminal_calibration" if passed else "freeze_or118_projected_area_and_coverage_attribution"
    output_directory.mkdir(parents=True, exist_ok=True)
    diagnostic = {**_write_png(output_directory / "shaft_terminal_partition.png", np.concatenate(diagnostic_rows, axis=0)), "layout": "physical_left_shaft_yellow_terminal_magenta_right"}
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_post_final_finite_linear_object_appearance_failure_attribution_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": status,
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "per_row": per_row,
        "shaft": shaft_metrics,
        "terminal": terminal_metrics,
        "shaft_terminal_target_bgr_euclidean_separation": separation,
        "gates": gates,
        "diagnostic": diagnostic,
        "execution": {"or116_receipt_reads": 1, "or116_development_montage_reads": 1, "validation_pixel_reads": 0, "source_video_decodes": 0, "candidate_video_decodes": 0, "renders": 0, "fits_or_candidate_searches": 0, "threshold_changes": 0, "simulator_replays": 0, "geometry_or_material_mutations": 0, "hardware_actions": 0, "paid_compute": False},
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": reviewer_decision,
        "next_transition": next_transition,
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

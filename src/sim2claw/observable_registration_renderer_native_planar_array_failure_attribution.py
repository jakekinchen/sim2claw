"""Attribute OR122B's planar-array miss from immutable maps and montage only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, sha256_file


cv2.ocl.setUseOpenCL(False)

SCHEMA = "sim2claw.observable_registration_renderer_native_planar_array_failure_attribution_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_renderer_native_planar_array_failure_attribution_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_renderer_native_planar_array_failure_attribution_v1"


def load_failure_attribution_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR123 contract")
    for group in ("sources", "frozen_identities"):
        for binding in contract[group].values():
            source_path = binding.get("path")
            expected = binding.get("sha256")
            if source_path and expected and sha256_file(REPO_ROOT / source_path) != expected:
                raise ValueError(f"OR123 identity mismatch: {source_path}")
    panels = contract["montage_panels"]
    if panels != {
        "row_count": 7,
        "panel_width_px": 320,
        "panel_height_px": 240,
        "physical_index": 0,
        "baseline_index": 1,
        "candidate_index": 2,
        "physical_candidate_absolute_difference_index": 3,
    }:
        raise ValueError("OR123 montage layout drifted")
    rules = contract["decision_tree"]
    if rules["projection_minimum_expected_line_coverage"] != 0.85:
        raise ValueError("OR123 projection rule drifted")
    if rules["material_minimum_mean_improved_pixel_fraction"] != 0.55:
        raise ValueError("OR123 material rule drifted")
    if rules["support_detail_maximum_consensus_coverage"] != 0.65:
        raise ValueError("OR123 support rule drifted")
    resources = contract["resource_boundary"]
    zero = (
        "source_video_decodes_allowed",
        "candidate_video_decodes_allowed",
        "renders_allowed",
        "fits_allowed",
        "searches_allowed",
        "threshold_changes_allowed",
        "retries_allowed",
        "simulator_replays_allowed",
        "geometry_values_produced_allowed",
        "hardware_actions_allowed",
    )
    if any(resources[key] != 0 for key in zero) or resources["paid_compute_allowed"] is not False:
        raise ValueError("OR123 resource boundary drifted")
    if any(contract["authority"].values()):
        raise ValueError("OR123 authority must remain closed")
    claims = contract["claim_limits"]
    for key in ("specific_object_identity", "metric_3d_geometry_calibrated", "predictive_simulation", "physics_fidelity", "physical_transfer", "simulator_promotion"):
        if claims[key] is not False:
            raise ValueError("OR123 claim boundary drifted")
    return contract


def _extract_panel(image: np.ndarray, index: int, width: int, height: int, row: int = 0) -> np.ndarray:
    y0 = row * height
    x0 = index * width
    panel = image[y0 : y0 + height, x0 : x0 + width]
    if panel.shape[:2] != (height, width):
        raise ValueError("OR123 panel extraction failed")
    return panel


def _select_failure_family(metrics: dict[str, float], rules: dict[str, Any]) -> tuple[str, dict[str, bool]]:
    gates = {
        "projection_support_aligned": (
            metrics["expected_line_coverage_by_added_support"]
            >= float(rules["projection_minimum_expected_line_coverage"])
            and metrics["maximum_endpoint_reprojection_error_px"]
            <= float(rules["projection_maximum_endpoint_reprojection_error_px"])
        ),
        "material_improves_residual": (
            metrics["mean_added_support_residual_improvement"]
            > float(rules["material_minimum_mean_residual_improvement"])
            and metrics["mean_improved_pixel_fraction"]
            >= float(rules["material_minimum_mean_improved_pixel_fraction"])
        ),
        "persistent_consensus_coverage_low": (
            metrics["persistent_consensus_coverage_by_added_support"]
            <= float(rules["support_detail_maximum_consensus_coverage"])
        ),
    }
    if not gates["projection_support_aligned"]:
        selected = "tabletop_plane_or_projection_alignment_failure"
    elif not gates["material_improves_residual"]:
        selected = "shared_material_response_failure"
    elif gates["persistent_consensus_coverage_low"]:
        selected = "sparse_boundary_support_and_missing_rectilinear_detail"
    else:
        selected = "indeterminate_planar_array_failure"
    return selected, gates


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR123 one-run receipt already exists")
    contract = load_failure_attribution_contract(contract_path)
    or122b = json.loads((REPO_ROOT / contract["sources"]["or122b_receipt"]["path"]).read_text())
    or121 = json.loads((REPO_ROOT / contract["sources"]["or121_receipt"]["path"]).read_text())
    if or122b["artifact_sha256"] != contract["sources"]["or122b_receipt"]["artifact_sha256"]:
        raise ValueError("OR123 OR122B artifact drifted")
    if or121["artifact_sha256"] != contract["sources"]["or121_receipt"]["artifact_sha256"]:
        raise ValueError("OR123 OR121 artifact drifted")

    panels = contract["montage_panels"]
    width = int(panels["panel_width_px"])
    height = int(panels["panel_height_px"])
    montage_path = REPO_ROOT / contract["sources"]["or122b_montage"]["path"]
    montage = cv2.imread(str(montage_path), cv2.IMREAD_COLOR)
    if montage is None or montage.shape != (height * int(panels["row_count"]), width * 4, 3):
        raise ValueError("OR123 OR122B montage shape drifted")

    map_contract = json.loads((REPO_ROOT / contract["sources"]["or121_contract"]["path"]).read_text())
    map_panels = map_contract["input_panels"]
    physical_masks: list[np.ndarray] = []
    for binding in or121["source_maps"]:
        path = REPO_ROOT / binding["path"]
        if sha256_file(path) != binding["sha256"]:
            raise ValueError("OR123 OR121 source map drifted")
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError("OR123 OR121 source map decode failed")
        physical_masks.append(
            _extract_panel(
                image,
                int(map_panels["physical_only_persistent_panel_index"]),
                int(map_panels["panel_width_px"]),
                int(map_panels["panel_height_px"]),
            )
            > 0
        )
    support_count = np.sum(np.stack(physical_masks, axis=0), axis=0)
    consensus = support_count >= int(map_contract["consensus"]["minimum_episode_count"])

    segments = [list(map(int, line)) for line in or122b["segments_xyxy"]]
    line_mask = np.zeros((height, width), dtype=np.uint8)
    for x0, y0, x1, y1 in segments:
        cv2.line(line_mask, (x0, y0), (x1, y1), 1, int(contract["support_masks"]["expected_line_thickness_px"]), cv2.LINE_8)
    line_mask = line_mask > 0
    kernel_size = int(contract["support_masks"]["tolerance_dilation_kernel_px"])
    kernel = np.ones((kernel_size, kernel_size), dtype=np.uint8)

    added_masks: list[np.ndarray] = []
    rows: list[dict[str, Any]] = []
    for row in range(int(panels["row_count"])):
        physical = _extract_panel(montage, int(panels["physical_index"]), width, height, row)
        baseline = _extract_panel(montage, int(panels["baseline_index"]), width, height, row)
        candidate = _extract_panel(montage, int(panels["candidate_index"]), width, height, row)
        added = np.any(candidate != baseline, axis=2)
        added_masks.append(added)
        baseline_error = np.mean(np.abs(physical.astype(np.float64) - baseline.astype(np.float64)), axis=2)
        candidate_error = np.mean(np.abs(physical.astype(np.float64) - candidate.astype(np.float64)), axis=2)
        improvement = baseline_error[added] - candidate_error[added]
        rows.append(
            {
                "split_position": row + 1,
                "added_support_pixel_count": int(added.sum()),
                "added_support_fraction_of_frame": float(added.mean()),
                "mean_added_support_baseline_absolute_residual": float(np.mean(baseline_error[added])),
                "mean_added_support_candidate_absolute_residual": float(np.mean(candidate_error[added])),
                "mean_added_support_residual_improvement": float(np.mean(improvement)),
                "improved_pixel_fraction": float(np.mean(improvement > 0.0)),
                "worsened_pixel_fraction": float(np.mean(improvement < 0.0)),
            }
        )

    union_added = np.any(np.stack(added_masks, axis=0), axis=0)
    dilated_added = cv2.dilate(union_added.astype(np.uint8), kernel) > 0
    dilated_line = cv2.dilate(line_mask.astype(np.uint8), kernel) > 0
    metrics = {
        "persistent_consensus_pixel_count": int(consensus.sum()),
        "union_added_support_pixel_count": int(union_added.sum()),
        "union_added_support_fraction_of_frame": float(union_added.mean()),
        "expected_line_pixel_count": int(line_mask.sum()),
        "expected_line_coverage_by_added_support": float((line_mask & dilated_added).sum() / max(int(line_mask.sum()), 1)),
        "added_support_precision_to_expected_lines": float((union_added & dilated_line).sum() / max(int(union_added.sum()), 1)),
        "persistent_consensus_coverage_by_added_support": float((consensus & dilated_added).sum() / max(int(consensus.sum()), 1)),
        "persistent_consensus_uncovered_pixel_count": int((consensus & ~dilated_added).sum()),
        "mean_added_support_residual_improvement": float(np.mean([row["mean_added_support_residual_improvement"] for row in rows])),
        "mean_improved_pixel_fraction": float(np.mean([row["improved_pixel_fraction"] for row in rows])),
        "mean_worsened_pixel_fraction": float(np.mean([row["worsened_pixel_fraction"] for row in rows])),
        "maximum_endpoint_reprojection_error_px": float(max(row["array_metadata"]["maximum_centerline_endpoint_reprojection_error_px"] for row in or122b["development_rows"])),
        "mean_or122b_array_roi_edge_f1_delta": float(or122b["development_summary"]["mean_array_roi_edge_f1_delta"]),
        "mean_or122b_full_frame_similarity_delta": float(or122b["development_summary"]["mean_full_frame_similarity_delta"]),
    }
    selected, decision_gates = _select_failure_family(metrics, contract["decision_tree"])

    output_directory.mkdir(parents=True, exist_ok=True)
    overlap = consensus & dilated_added
    uncovered = consensus & ~dilated_added
    panel_consensus = np.repeat((consensus.astype(np.uint8) * 255)[:, :, None], 3, axis=2)
    panel_added = np.zeros_like(panel_consensus)
    panel_added[union_added] = (255, 255, 0)
    panel_overlap = np.zeros_like(panel_consensus)
    panel_overlap[overlap] = (0, 255, 0)
    panel_uncovered = np.zeros_like(panel_consensus)
    panel_uncovered[uncovered] = (0, 0, 255)
    audit = np.concatenate([panel_consensus, panel_added, panel_overlap, panel_uncovered], axis=1)
    audit_path = output_directory / "planar-array-failure-attribution.png"
    ok, encoded = cv2.imencode(".png", audit, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not ok:
        raise RuntimeError("OR123 audit encoding failed")
    audit_path.write_bytes(encoded.tobytes())

    integrity = {
        "exact_or121_map_count": len(physical_masks) == 11,
        "exact_or121_consensus_pixel_count": int(consensus.sum()) == int(contract["integrity"]["expected_consensus_pixel_count"]),
        "exact_or122b_development_row_count": len(rows) == 7,
        "exact_five_segment_input": len(segments) == 5,
        "or122b_validation_remained_sealed": or122b["corroboration_rows"] == [],
        "zero_video_decode_render_fit_search_retry_replay_hardware_or_paid_compute": True,
    }
    passed = selected != "indeterminate_planar_array_failure" and all(integrity.values())
    status = "PASS_PLANAR_ARRAY_FAILURE_ATTRIBUTED" if passed else "TERMINAL_PLANAR_ARRAY_FAILURE_INDETERMINATE"
    next_transition = {
        "sparse_boundary_support_and_missing_rectilinear_detail": "freeze_or124_renderer_native_dense_rectilinear_support_reconstruction",
        "shared_material_response_failure": "freeze_or124_planar_array_material_response_calibration",
        "tabletop_plane_or_projection_alignment_failure": "freeze_or124_planar_array_plane_projection_diagnostic",
        "indeterminate_planar_array_failure": "stop_planar_array_successor_until_new_evidence",
    }[selected]
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_renderer_native_planar_array_failure_attribution_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": status,
        "proof_class": contract["proof_class"],
        "identities": {
            "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
            "implementation": contract["frozen_identities"]["implementation"],
            "test": contract["frozen_identities"]["test"],
        },
        "rows": rows,
        "metrics": metrics,
        "decision_gates": decision_gates,
        "selected_failure_family": selected,
        "audit": {
            "path": str(audit_path.relative_to(REPO_ROOT)),
            "sha256": sha256_file(audit_path),
            "layout": "or121_consensus_or122b_union_added_support_tolerant_overlap_uncovered_consensus",
        },
        "integrity_gates": integrity,
        "execution": {
            "or121_map_reads": len(physical_masks),
            "or122b_montage_reads": 1,
            "source_video_decodes": 0,
            "candidate_video_decodes": 0,
            "renders": 0,
            "fits": 0,
            "searches": 0,
            "threshold_changes": 0,
            "retries": 0,
            "simulator_replays": 0,
            "geometry_values_produced": 0,
            "hardware_actions": 0,
            "paid_compute": False,
        },
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": "FREEZE_BOUNDED_RENDERER_NATIVE_SUCCESSOR" if passed else "STOP_INDETERMINATE",
        "next_transition": next_transition,
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

"""Deterministic fit-only diagnostic for the interrupted V3 registration route."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np

from .bidirectional_registration_v2_fit import (
    _hold_means,
    _model_jaw_midpoints,
    project,
)
from .paths import REPO_ROOT


class MaskedDiagnosticError(RuntimeError):
    """Raised when a diagnostic input, seal, or deterministic gate changed."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_bound(entry: Mapping[str, Any], *, may_read: bool = True) -> Path:
    raw = str(entry["path"])
    if "heldout" in raw.lower():
        raise MaskedDiagnosticError(f"heldout path is forbidden: {raw}")
    path = REPO_ROOT / raw
    if not path.is_file() or _sha256(path) != entry["sha256"]:
        raise MaskedDiagnosticError(f"bound input changed: {path}")
    if not may_read and not entry.get("content_read_forbidden"):
        raise MaskedDiagnosticError("non-readable identity input is not marked")
    return path


def _load_json(entry: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(_safe_bound(entry).read_text(encoding="utf-8"))


def _fit_manifest_for_helpers(
    manifest: Mapping[str, Any], targets: list[Mapping[str, Any]]
) -> dict[str, Any]:
    expected = {str(row["target_id"]): row for row in targets}
    members = []
    for member in manifest["members"]:
        target_id = str(member["target_id"])
        if target_id not in expected:
            raise MaskedDiagnosticError("fit manifest membership changed")
        contract = expected[target_id]
        for field, contract_field in (
            ("image_path", "image_path"),
            ("image_sha256", "image_sha256"),
            ("capture_receipt_path", "capture_receipt_path"),
            ("capture_receipt_sha256", "capture_receipt_sha256"),
        ):
            manifest_value = str(member[field])
            if field.endswith("_path"):
                manifest_value = str(
                    Path(manifest_value).resolve().relative_to(REPO_ROOT)
                )
            if manifest_value != str(contract[contract_field]):
                raise MaskedDiagnosticError("fit member binding changed")
        members.append(
            {
                **member,
                "image_path": contract["image_path"],
                "capture_receipt_path": contract["capture_receipt_path"],
            }
        )
    if {str(row["target_id"]) for row in members} != set(expected):
        raise MaskedDiagnosticError("fit manifest is not the frozen four-member split")
    return {"members": members}


def _static_scene_metrics(
    images: Mapping[str, np.ndarray],
    settings: Mapping[str, Any],
) -> dict[str, Any]:
    reference_id = str(settings["reference_target_id"])
    reference = cv2.cvtColor(images[reference_id], cv2.COLOR_BGR2GRAY)
    x1, y1, x2, y2 = [int(value) for value in settings["mask_rectangle_xyxy"]]
    mask = np.zeros_like(reference)
    mask[y1:y2, x1:x2] = 255
    corners = cv2.goodFeaturesToTrack(
        reference,
        maxCorners=int(settings["maximum_corners"]),
        qualityLevel=float(settings["quality_level"]),
        minDistance=float(settings["minimum_distance_px"]),
        mask=mask,
    )
    if corners is None or len(corners) < 24:
        raise MaskedDiagnosticError("too few masked static-scene corners")

    rows: list[dict[str, Any]] = []
    all_rms: list[float] = []
    all_maximum: list[float] = []
    for target_id, image in images.items():
        if target_id == reference_id:
            continue
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        tracked, status, _ = cv2.calcOpticalFlowPyrLK(
            reference,
            gray,
            corners,
            None,
            winSize=(int(settings["lk_window_px"]),) * 2,
        )
        if tracked is None or status is None:
            raise MaskedDiagnosticError("masked optical flow failed")
        valid = status.reshape(-1).astype(bool)
        source = corners.reshape(-1, 2)[valid]
        destination = tracked.reshape(-1, 2)[valid]
        homography, inliers = cv2.findHomography(
            source,
            destination,
            cv2.RANSAC,
            float(settings["ransac_reprojection_threshold_px"]),
        )
        if homography is None or inliers is None:
            raise MaskedDiagnosticError("masked homography failed")
        selected = inliers.reshape(-1).astype(bool)
        predicted = cv2.perspectiveTransform(
            source.reshape(-1, 1, 2), homography
        ).reshape(-1, 2)
        residual = np.linalg.norm(predicted[selected] - destination[selected], axis=1)
        flow = destination[selected] - source[selected]
        rms = float(np.sqrt(np.mean(np.square(residual))))
        maximum = float(np.max(residual))
        all_rms.append(rms)
        all_maximum.append(maximum)
        median_flow = np.median(flow, axis=0)
        rows.append(
            {
                "target_id": target_id,
                "tracked_corner_count": int(len(source)),
                "ransac_inlier_count": int(np.sum(selected)),
                "median_raw_flow_xy_px": median_flow.tolist(),
                "median_raw_flow_magnitude_px": float(np.linalg.norm(median_flow)),
                "postwarp_residual_rms_px": rms,
                "postwarp_residual_max_px": maximum,
            }
        )
    return {
        "reference_target_id": reference_id,
        "reference_corner_count": int(len(corners)),
        "mask_rectangle_xyxy": [x1, y1, x2, y2],
        "comparisons": rows,
        "maximum_postwarp_rms_px": max(all_rms),
        "maximum_postwarp_max_px": max(all_maximum),
    }


def _annotations(
    targets: list[Mapping[str, Any]],
) -> tuple[np.ndarray, dict[str, Any]]:
    midpoints: list[np.ndarray] = []
    rows: list[dict[str, Any]] = []
    all_tip_delta: list[float] = []
    for target in targets:
        pass_a = np.asarray(target["pass_a_tip_pixels"], dtype=np.float64)
        pass_b = np.asarray(target["pass_b_tip_pixels"], dtype=np.float64)
        if pass_a.shape != (2, 2) or pass_b.shape != (2, 2):
            raise MaskedDiagnosticError("each annotation pass must contain two tips")
        tip_delta = np.linalg.norm(pass_a - pass_b, axis=1)
        all_tip_delta.extend(tip_delta.tolist())
        midpoint = (np.mean(pass_a, axis=0) + np.mean(pass_b, axis=0)) / 2.0
        midpoints.append(midpoint)
        rows.append(
            {
                "target_id": target["target_id"],
                "pass_a_tip_pixels": pass_a.tolist(),
                "pass_b_tip_pixels": pass_b.tolist(),
                "maximum_tip_disagreement_px": float(np.max(tip_delta)),
                "frozen_midpoint_px": midpoint.tolist(),
            }
        )
    return np.asarray(midpoints), {
        "targets": rows,
        "all_four_two_tip_scorable": True,
        "maximum_tip_disagreement_px": max(all_tip_delta),
    }


def _compiled_transform_metrics(
    contract: Mapping[str, Any],
    fit_manifest: Mapping[str, Any],
    observed_midpoints: np.ndarray,
) -> dict[str, Any]:
    candidate_wrapper = _load_json(contract["inputs"]["compiled_candidate_manifest"])
    candidate = candidate_wrapper["candidate_config"]
    fit_camera = _load_json(contract["inputs"]["rejected_fit_only_camera_diagnostic"])
    targets = contract["fit_targets"]
    helper_annotations = {"joint_samples": contract["inputs"]["joint_samples"]}
    hold_means = _hold_means(helper_annotations, fit_manifest)
    target_ids = [str(row["target_id"]) for row in targets]
    physical = np.asarray([hold_means[target_id] for target_id in target_ids])
    world = _model_jaw_midpoints(physical, candidate)
    projected = project(np.asarray(fit_camera["camera_matrix_3x4"]), world)

    translation = np.mean(observed_midpoints - projected, axis=0)
    corrected = projected + translation
    corrected_error = np.linalg.norm(corrected - observed_midpoints, axis=1)
    pairwise_errors: list[dict[str, Any]] = []
    for first in range(len(target_ids)):
        for second in range(first + 1, len(target_ids)):
            observed_delta = observed_midpoints[second] - observed_midpoints[first]
            projected_delta = projected[second] - projected[first]
            pairwise_errors.append(
                {
                    "first_target_id": target_ids[first],
                    "second_target_id": target_ids[second],
                    "observed_delta_px": observed_delta.tolist(),
                    "compiled_projected_delta_px": projected_delta.tolist(),
                    "delta_error_px": float(
                        np.linalg.norm(observed_delta - projected_delta)
                    ),
                }
            )
    return {
        "diagnostic_camera_admission_authority": False,
        "target_ids": target_ids,
        "physical_hold_means_degrees_percent": physical.tolist(),
        "compiled_model_midpoints_world_m": world.tolist(),
        "observed_midpoints_px": observed_midpoints.tolist(),
        "compiled_projected_midpoints_px": projected.tolist(),
        "best_image_translation_xy_px": translation.tolist(),
        "translation_corrected_errors_px": corrected_error.tolist(),
        "translation_corrected_rms_px": float(
            np.sqrt(np.mean(np.square(corrected_error)))
        ),
        "pairwise_delta_errors": pairwise_errors,
        "maximum_pairwise_delta_error_px": max(
            row["delta_error_px"] for row in pairwise_errors
        ),
    }


def _settle_metrics(
    telemetry_path: Path, settings: Mapping[str, Any]
) -> dict[str, Any]:
    rows = [
        json.loads(line)
        for line in telemetry_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    array_id = str(settings["array_id"])
    first = int(settings["pre_score_first_row"])
    score_first = int(settings["frozen_score_first_row"])
    last = int(settings["last_available_row"])
    selected = {
        int(row["array_row_index"]): row
        for row in rows
        if row["array_id"] == array_id
        and first <= int(row["array_row_index"]) <= last
    }
    if set(selected) != set(range(first, last + 1)):
        raise MaskedDiagnosticError("target-09 telemetry boundary changed")

    def maximum_error(row: Mapping[str, Any]) -> float:
        return float(np.max(np.abs(np.asarray(row["tracking_error"], dtype=float))))

    score_rows = [selected[index] for index in range(score_first, last + 1)]
    gate = float(settings["tracking_gate_degrees"])
    first_within = next(
        (row for row in score_rows if maximum_error(row) <= gate),
        None,
    )
    if first_within is None:
        raise MaskedDiagnosticError("target-09 never entered tracking gate")
    score_span = (
        int(score_rows[-1]["host_continuous_ns"])
        - int(score_rows[0]["host_continuous_ns"])
    ) / 1e9
    return {
        "frozen_score_first_row": score_first,
        "frozen_score_last_row": last,
        "frozen_score_sample_count": len(score_rows),
        "frozen_score_span_seconds": score_span,
        "required_stationary_hold_seconds": float(
            settings["minimum_stationary_hold_seconds"]
        ),
        "first_score_row_maximum_error_degrees": maximum_error(score_rows[0]),
        "first_within_gate_row": int(first_within["array_row_index"]),
        "first_within_gate_maximum_error_degrees": maximum_error(first_within),
        "first_within_gate_delay_from_score_start_seconds": (
            int(first_within["host_continuous_ns"])
            - int(score_rows[0]["host_continuous_ns"])
        )
        / 1e9,
        "final_available_maximum_error_degrees": maximum_error(score_rows[-1]),
        "all_rows_from_first_within_gate_remain_within_gate": all(
            maximum_error(row) <= gate
            for row in score_rows
            if int(row["array_row_index"])
            >= int(first_within["array_row_index"])
        ),
    }


def evaluate(contract_path: Path, output_path: Path) -> dict[str, Any]:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if "heldout" in contract_path.as_posix().lower():
        raise MaskedDiagnosticError("contract path must not contain heldout")
    for name, entry in contract["inputs"].items():
        _safe_bound(
            entry,
            may_read=name != "execution_receipt_identity_only",
        )
    targets = contract["fit_targets"]
    for target in targets:
        _safe_bound(
            {"path": target["image_path"], "sha256": target["image_sha256"]}
        )
        _safe_bound(
            {
                "path": target["capture_receipt_path"],
                "sha256": target["capture_receipt_sha256"],
            }
        )
    fit_manifest_raw = _load_json(contract["inputs"]["fit_manifest"])
    fit_manifest = _fit_manifest_for_helpers(fit_manifest_raw, targets)
    images = {
        str(target["target_id"]): cv2.imread(
            str(REPO_ROOT / target["image_path"]), cv2.IMREAD_COLOR
        )
        for target in targets
    }
    if any(image is None for image in images.values()):
        raise MaskedDiagnosticError("fit image decode failed")

    observed, annotation_metrics = _annotations(targets)
    static_metrics = _static_scene_metrics(images, contract["static_scene_test"])
    transform_metrics = _compiled_transform_metrics(
        contract, fit_manifest, observed
    )
    settle_metrics = _settle_metrics(
        _safe_bound(contract["inputs"]["joint_samples"]),
        contract["target_09_settle_test"],
    )
    gates = contract["gates"]
    checks = {
        "fit_membership_exactly_four": len(targets) == 4,
        "all_four_two_tip_scorable": annotation_metrics[
            "all_four_two_tip_scorable"
        ],
        "tip_annotation_agreement": annotation_metrics[
            "maximum_tip_disagreement_px"
        ]
        <= float(gates["maximum_tip_annotation_disagreement_px"]),
        "masked_static_scene_internal_rms": static_metrics[
            "maximum_postwarp_rms_px"
        ]
        <= float(gates["maximum_static_postwarp_rms_px"]),
        "masked_static_scene_internal_max": static_metrics[
            "maximum_postwarp_max_px"
        ]
        <= float(gates["maximum_static_postwarp_max_px"]),
        "compiled_relative_midpoint_rms": transform_metrics[
            "translation_corrected_rms_px"
        ]
        <= float(
            gates["maximum_translation_corrected_compiled_midpoint_rms_px"]
        ),
        "compiled_pairwise_delta": transform_metrics[
            "maximum_pairwise_delta_error_px"
        ]
        <= float(gates["maximum_pairwise_compiled_delta_error_px"]),
        "first_frozen_score_row_exceeds_gate": settle_metrics[
            "first_score_row_maximum_error_degrees"
        ]
        > float(contract["target_09_settle_test"]["tracking_gate_degrees"]),
        "immediate_next_row_enters_gate": settle_metrics[
            "first_within_gate_row"
        ]
        == int(contract["target_09_settle_test"]["frozen_score_first_row"]) + 1,
        "score_span_failed_true_two_seconds": settle_metrics[
            "frozen_score_span_seconds"
        ]
        < float(contract["target_09_settle_test"]["minimum_stationary_hold_seconds"]),
        "post_entry_rows_remain_within_gate": settle_metrics[
            "all_rows_from_first_within_gate_remain_within_gate"
        ],
    }
    schedule_fault_isolated = all(
        checks[name]
        for name in (
            "first_frozen_score_row_exceeds_gate",
            "immediate_next_row_enters_gate",
            "score_span_failed_true_two_seconds",
            "post_entry_rows_remain_within_gate",
        )
    )
    compiled_transform_coherent = all(
        checks[name]
        for name in (
            "compiled_relative_midpoint_rms",
            "compiled_pairwise_delta",
        )
    )
    receipt = {
        "schema_version": (
            "sim2claw.bidirectional_pawn_push_v2_masked_static_cad_receipt.v1"
        ),
        "status": "diagnostic_complete",
        "proof_class": contract["proof_class"],
        "contract_path": str(contract_path.relative_to(REPO_ROOT)),
        "contract_sha256": _sha256(contract_path),
        "heldout_open_count": 0,
        "heldout_content_read": False,
        "physical_motion_commanded": False,
        "fit_manifest_sha256": contract["inputs"]["fit_manifest"]["sha256"],
        "annotations": annotation_metrics,
        "masked_static_scene": static_metrics,
        "compiled_transform_diagnostic": transform_metrics,
        "target_09_settle_diagnostic": settle_metrics,
        "checks": checks,
        "schedule_fault_isolated": schedule_fault_isolated,
        "compiled_transform_coherent_under_rejected_v1_camera": (
            compiled_transform_coherent
        ),
        "decision": (
            "prospective_new_version_with_true_time_based_score_window_and_"
            "shared_rigid_transform_fit_required"
        ),
        "next_action": contract["decision_policy"]["prospective_action"],
        "claim_boundary": (
            "Fit-only retrospective diagnostic. It isolates the V3 stop as a "
            "score-window scheduling fault and rejects coherence under an older "
            "non-admissible camera diagnostic; it grants no candidate, heldout, "
            "motion, task, or transfer authority."
        ),
        "authority": contract["authority"],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    evaluate(args.contract.resolve(), args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

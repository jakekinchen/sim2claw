"""Repair OR133B with the exact OR133A union-robot silhouette distance."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from scipy.ndimage import distance_transform_edt

from . import observable_registration_development_boundary_residual_spatiotemporal_falsification as _or133b
from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, sha256_file
from .observable_registration_renderer_native_regional_residual_attribution import _shadow_image_direction


SCHEMA = "sim2claw.observable_registration_union_silhouette_boundary_residual_spatiotemporal_falsification_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_union_silhouette_boundary_residual_spatiotemporal_falsification_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_union_silhouette_boundary_residual_spatiotemporal_falsification_v1"


def load_union_silhouette_falsification_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR133C contract")
    for binding in contract["sources"].values():
        if sha256_file(REPO_ROOT / binding["path"]) != binding["sha256"]:
            raise ValueError(f"OR133C source identity mismatch: {binding['path']}")
    for binding in contract["frozen_identities"].values():
        if sha256_file(REPO_ROOT / binding["path"]) != binding["sha256"]:
            raise ValueError(f"OR133C frozen identity mismatch: {binding['path']}")
    base = _or133b.load_boundary_residual_falsification_contract(
        REPO_ROOT / contract["sources"]["or133b_contract"]["path"]
    )
    failure = json.loads((REPO_ROOT / contract["sources"]["or133b_terminal_failure"]["path"]).read_text())
    if failure["status"] != "TERMINAL_BOUNDARY_RESIDUAL_REPRODUCTION_INFEASIBLE":
        raise ValueError("OR133C OR133B terminal prerequisite drifted")
    if failure["failure"]["same_card_retry_allowed"] is not False:
        raise ValueError("OR133C must remain a new identity")
    if contract["repair"] != {
        "classification_distance_source": "morphological_boundary_of_union_of_left_and_right_robot_id_masks",
        "separate_left_right_distances_are_descriptive_only": True,
        "separate_left_right_distances_may_change_membership": False,
        "all_other_or133b_protocol_fields_inherited_without_change": True,
        "same_card_retry": False,
        "new_experiment_identity": True,
    }:
        raise ValueError("OR133C repair scope drifted")
    inherited = contract["inherited_protocol"]
    if (
        inherited["development_split_positions"] != base["development_partition"]["split_positions"]
        or inherited["total_frame_count"] != base["development_partition"]["total_frame_count"]
        or inherited["expected_triangle_count_per_frame"]
        != base["residual_reproduction"]["expected_triangle_count_per_frame"]
        or inherited["lags_frames"] != base["association_test"]["lags_frames"]
        or inherited["circular_shift_null_count"] != base["association_test"]["circular_shift_null_count"]
        or inherited["minimum_circular_shift_frames"]
        != base["association_test"]["minimum_circular_shift_frames"]
        or inherited["minimum_qualifying_episode_count"]
        != base["association_test"]["minimum_qualifying_episode_count"]
        or inherited["candidate_intervention_renders"]
        != base["resource_boundary"]["candidate_intervention_renders_allowed"]
        or inherited["renderer_or_intervention_dof"]
        != base["resource_boundary"]["renderer_or_intervention_dof_allowed"]
    ):
        raise ValueError("OR133C inherited protocol drifted")
    if any(contract["authority"].values()):
        raise ValueError("OR133C authority must remain closed")
    return contract


def _union_arm_distance(
    idbuffer: np.ndarray, left_group_id: int, right_group_id: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    distances: list[np.ndarray] = []
    for group_id in (left_group_id, right_group_id):
        mask = idbuffer == group_id
        edge = cv2.morphologyEx(
            mask.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)
        ) > 0
        distances.append(
            distance_transform_edt(~edge) if edge.any() else np.full(mask.shape, np.inf)
        )
    union = np.isin(idbuffer, [left_group_id, right_group_id])
    union_edge = cv2.morphologyEx(
        union.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)
    ) > 0
    union_distance = (
        distance_transform_edt(~union_edge) if union_edge.any() else np.full(union.shape, np.inf)
    )
    return distances[0], distances[1], union, union_distance


def _stage_residuals_union(
    physical_frames: list[np.ndarray],
    candidate_frames: list[np.ndarray],
    idbuffers: list[np.ndarray],
    physical_persistent: np.ndarray,
    physical_dynamic: np.ndarray,
    outside_mask: np.ndarray,
    left_id: int,
    right_id: int,
    residual: dict[str, Any],
) -> tuple[list[dict[str, Any]], float, np.ndarray]:
    persistent_values = [
        cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)[physical_persistent]
        for frame in physical_frames
        if physical_persistent.any()
    ]
    baseline_luma = float(np.median(np.concatenate(persistent_values))) if persistent_values else 0.0
    kernel = np.ones(
        (int(residual["candidate_edge_tolerance_kernel_px"]),) * 2, dtype=np.uint8
    )
    shadow_direction = _shadow_image_direction(
        residual["camera"], residual["nominal_light_direction"]
    )
    staged: list[dict[str, Any]] = []
    for physical, candidate, idbuffer in zip(
        physical_frames, candidate_frames, idbuffers, strict=True
    ):
        physical_gray = cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY)
        candidate_gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
        physical_edge = cv2.Canny(
            physical_gray,
            int(residual["canny_low_threshold"]),
            int(residual["canny_high_threshold"]),
        ) > 0
        candidate_edge = cv2.Canny(
            candidate_gray,
            int(residual["canny_low_threshold"]),
            int(residual["canny_high_threshold"]),
        ) > 0
        matched = cv2.dilate(candidate_edge.astype(np.uint8), kernel) > 0
        unmatched = physical_edge & physical_dynamic & outside_mask & ~matched
        left_distance, right_distance, arm_mask, union_distance = _union_arm_distance(
            idbuffer, left_id, right_id
        )
        silhouette = unmatched & (
            union_distance
            < float(residual["arm_silhouette_distance_px_exclusive_max"])
        )
        rest = unmatched & ~silhouette
        potential_shadow = np.zeros_like(rest)
        offset: list[float] | None = None
        if arm_mask.any() and rest.any():
            arm_y, arm_x = np.nonzero(arm_mask)
            arm_centroid = np.asarray([arm_x.mean(), arm_y.mean()])
            yy, xx = np.nonzero(rest)
            relative = np.column_stack([xx, yy]) - arm_centroid
            selected = (
                (relative @ shadow_direction > 0.0)
                & (physical_gray[yy, xx] < baseline_luma)
                & (union_distance[yy, xx] >= float(residual["shadow_distance_px_min"]))
            )
            potential_shadow[yy[selected], xx[selected]] = True
            if potential_shadow.any():
                py, px = np.nonzero(potential_shadow)
                offset = [
                    float(px.mean() - arm_centroid[0]),
                    float(py.mean() - arm_centroid[1]),
                ]
        staged.append(
            {
                "physical_gray": physical_gray,
                "rest": rest,
                "potential_shadow": potential_shadow,
                "offset": offset,
                "left_distance": left_distance,
                "right_distance": right_distance,
                "arm_mask": arm_mask,
            }
        )
    offsets = np.asarray(
        [row["offset"] for row in staged if row["offset"] is not None], dtype=np.float64
    )
    median_offset = (
        np.median(offsets, axis=0) if len(offsets) else np.asarray([np.nan, np.nan])
    )
    for row in staged:
        stable = row["offset"] is not None and float(
            np.linalg.norm(np.asarray(row["offset"]) - median_offset)
        ) <= float(residual["shadow_offset_stability_px_max"])
        shadow = (
            row["potential_shadow"]
            if stable
            else np.zeros_like(row["potential_shadow"])
        )
        row["boundary_source"] = row["rest"] & ~shadow
    return staged, baseline_luma, shadow_direction


def evaluate_once(
    contract_path: Path = DEFAULT_CONTRACT,
    output_directory: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR133C one-run receipt already exists; retry prohibited")
    contract = load_union_silhouette_falsification_contract(contract_path)
    base_path = REPO_ROOT / contract["sources"]["or133b_contract"]["path"]
    base = deepcopy(_or133b.load_boundary_residual_falsification_contract(base_path))
    base["experiment_id"] = contract["experiment_id"]
    base["proof_class"] = contract["proof_class"]
    base["claim_limits"] = contract["claim_limits"]
    base["authority"] = contract["authority"]
    base["stop_conditions"]["instrumentation_failure"] = contract["stop_conditions"][
        "instrumentation_failure"
    ]

    def merged_loader(_path: Path) -> dict[str, Any]:
        return base

    original_loader = _or133b.load_boundary_residual_falsification_contract
    original_stage = _or133b._stage_residuals
    try:
        _or133b.load_boundary_residual_falsification_contract = merged_loader
        _or133b._stage_residuals = _stage_residuals_union
        receipt = _or133b.evaluate_once(contract_path, output_directory)
    finally:
        _or133b.load_boundary_residual_falsification_contract = original_loader
        _or133b._stage_residuals = original_stage
    base_artifact = receipt.pop("artifact_sha256")
    receipt[
        "schema_version"
    ] = "sim2claw.observable_registration_union_silhouette_boundary_residual_spatiotemporal_falsification_receipt.v1"
    receipt["repair"] = contract["repair"]
    receipt["base_evaluator_artifact_sha256_before_repair_identity"] = base_artifact
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

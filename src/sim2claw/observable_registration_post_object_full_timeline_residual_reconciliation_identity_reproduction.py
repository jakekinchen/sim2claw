"""Identity-bound reproduction of the quarantined OR120 residual factorization."""

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
from .observable_registration_post_final_static_dynamic_edge_occupancy_factorization import (
    _binary_tolerant_f1,
    _read_video_frames,
)


cv2.ocl.setUseOpenCL(False)

SCHEMA = "sim2claw.observable_registration_post_object_full_timeline_residual_reconciliation_identity_reproduction_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_object_full_timeline_residual_reconciliation_identity_reproduction_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_object_full_timeline_residual_reconciliation_identity_reproduction_v1"


def load_identity_reproduction_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR120B contract")
    for group in ("sources", "frozen_identities"):
        for binding in contract[group].values():
            if sha256_file(REPO_ROOT / binding["path"]) != binding["sha256"]:
                raise ValueError(f"OR120B identity mismatch: {binding['path']}")
    or97_contract = json.loads((REPO_ROOT / contract["sources"]["or97_contract"]["path"]).read_text())
    if contract["regions"] != or97_contract["regions"] or contract["edge_occupancy"] != or97_contract["edge_occupancy"]:
        raise ValueError("OR120B must preserve the exact OR97 factorization")
    occupancy = contract["edge_occupancy"]
    if (
        occupancy["persistent_minimum_frame_fraction"] != 0.80
        or occupancy["dynamic_minimum_frame_fraction"] != 0.05
        or occupancy["dynamic_maximum_frame_fraction_exclusive"] != 0.80
    ):
        raise ValueError("OR120B occupancy threshold drift")
    rule = contract["decision_rule"]
    if rule["minimum_dominant_deficit_ratio"] != 3.0 or rule["minimum_dominant_episode_count"] != 9:
        raise ValueError("OR120B dominance rule drift")
    resources = contract["resource_boundary"]
    zero_keys = (
        "renders_allowed",
        "fits_allowed",
        "candidate_selections_allowed",
        "threshold_changes_allowed",
        "retries_allowed",
        "simulator_replays_allowed",
        "hardware_actions_allowed",
    )
    if any(resources[key] != 0 for key in zero_keys) or resources["paid_compute_allowed"] is not False:
        raise ValueError("OR120B resource boundary drift")
    if any(contract["authority"].values()):
        raise ValueError("OR120B authority must remain closed")
    if contract["claim_limits"]["same_video_semantic_match"] is not False:
        raise ValueError("OR120B claim boundary drift")
    return contract


def _unmatched_residuals(
    physical: np.ndarray,
    candidate: np.ndarray,
    region: np.ndarray,
    tolerance: int,
) -> tuple[np.ndarray, np.ndarray]:
    physical = physical & region
    candidate = candidate & region
    kernel = np.ones((tolerance, tolerance), dtype=np.uint8)
    physical_dilated = cv2.dilate(physical.astype(np.uint8) * 255, kernel) > 0
    candidate_dilated = cv2.dilate(candidate.astype(np.uint8) * 255, kernel) > 0
    return physical & ~candidate_dilated, candidate & ~physical_dilated


def _write_residual_map(path: Path, maps: list[np.ndarray]) -> dict[str, str]:
    panels = [np.repeat((value.astype(np.uint8) * 255)[:, :, None], 3, axis=2) for value in maps]
    montage = np.concatenate(panels, axis=1)
    ok, encoded = cv2.imencode(".png", montage, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not ok:
        raise RuntimeError("OR120B residual-map encoding failed")
    path.write_bytes(encoded.tobytes())
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "sha256": sha256_file(path),
        "layout": (
            "physical_persistent_candidate_persistent_physical_only_persistent_candidate_only_persistent_"
            "physical_dynamic_candidate_dynamic_physical_only_dynamic_candidate_only_dynamic"
        ),
    }


def _select_successor(
    persistent_values: list[float],
    dynamic_values: list[float],
    rule: dict[str, Any],
) -> dict[str, Any]:
    adequate = float(rule["minimum_adequate_factor_f1"])
    persistent_deficits = [max(0.0, adequate - value) for value in persistent_values]
    dynamic_deficits = [max(0.0, adequate - value) for value in dynamic_values]
    persistent_mean_deficit = float(np.mean(persistent_deficits))
    dynamic_mean_deficit = float(np.mean(dynamic_deficits))
    epsilon = 1.0e-12
    ratio = float(rule["minimum_dominant_deficit_ratio"])
    persistent_dominant = sum(
        persistent >= ratio * max(dynamic, epsilon)
        for persistent, dynamic in zip(persistent_deficits, dynamic_deficits, strict=True)
    )
    dynamic_dominant = sum(
        dynamic >= ratio * max(persistent, epsilon)
        for persistent, dynamic in zip(persistent_deficits, dynamic_deficits, strict=True)
    )
    persistent_below = sum(value < adequate for value in persistent_values)
    dynamic_below = sum(value < adequate for value in dynamic_values)
    minimum_below = int(rule["minimum_inadequate_episode_count"])
    minimum_dominant = int(rule["minimum_dominant_episode_count"])
    persistent_to_dynamic = persistent_mean_deficit / max(dynamic_mean_deficit, epsilon)
    dynamic_to_persistent = dynamic_mean_deficit / max(persistent_mean_deficit, epsilon)
    if persistent_below >= minimum_below and persistent_dominant >= minimum_dominant and persistent_to_dynamic >= ratio:
        selected = rule["persistent_dominant_selects"]
    elif dynamic_below >= minimum_below and dynamic_dominant >= minimum_dominant and dynamic_to_persistent >= ratio:
        selected = rule["dynamic_dominant_selects"]
    else:
        selected = rule["otherwise_selects"]
    return {
        "mean_persistent_outside_board_edge_occupancy_f1": float(np.mean(persistent_values)),
        "mean_dynamic_outside_board_edge_occupancy_f1": float(np.mean(dynamic_values)),
        "mean_persistent_deficit_to_0_60": persistent_mean_deficit,
        "mean_dynamic_deficit_to_0_60": dynamic_mean_deficit,
        "persistent_to_dynamic_mean_deficit_ratio": persistent_to_dynamic,
        "dynamic_to_persistent_mean_deficit_ratio": dynamic_to_persistent,
        "episodes_persistent_below_threshold": persistent_below,
        "episodes_dynamic_below_threshold": dynamic_below,
        "episodes_persistent_deficit_dominant": persistent_dominant,
        "episodes_dynamic_deficit_dominant": dynamic_dominant,
        "selected_residual_family": selected,
    }


def evaluate_once(
    contract_path: Path = DEFAULT_CONTRACT,
    output_directory: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR120B one-run receipt already exists")
    contract = load_identity_reproduction_contract(contract_path)
    or97 = json.loads((REPO_ROOT / contract["sources"]["or97_receipt"]["path"]).read_text())
    or119 = json.loads((REPO_ROOT / contract["sources"]["or119_receipt"]["path"]).read_text())
    or119_rows = json.loads((REPO_ROOT / contract["sources"]["or119_frame_rows"]["path"]).read_text())["rows"]
    reference = json.loads((REPO_ROOT / contract["sources"]["quarantined_or120_receipt"]["path"]).read_text())
    or95_contract = json.loads((REPO_ROOT / contract["sources"]["or95_contract"]["path"]).read_text())
    if or97["status"] != "PASS_STATIC_SCENE_CONTENT_AND_ROBOT_ARTICULATION_SELECTED":
        raise ValueError("OR97 baseline drift")
    if or119["status"] != "TERMINAL_RETROSPECTIVE_TWO_MATERIAL_FINITE_OBJECT_FULL_TIMELINE_GATES_FAILED":
        raise ValueError("OR119 receipt drift")
    episodes = _episode_inventory(or95_contract)
    video_map = {row["recording_id"]: row for row in or119["candidate_videos"]}
    prior_map = {row["recording_id"]: row for row in or97["rows"]}
    reference_map = {row["recording_id"]: row for row in reference["rows"]}
    rows_by_episode = {episode["recording_id"]: [] for episode in episodes}
    for row in or119_rows:
        rows_by_episode[row["recording_id"]].append(row)
    for rows in rows_by_episode.values():
        rows.sort(key=lambda row: int(row["evaluation_index"]))

    occupancy = contract["edge_occupancy"]
    _, outside_mask = _region_masks(
        np.asarray(contract["regions"]["board_plus_margin"]["points_px"], dtype=np.float64),
        width=int(occupancy["width_px"]),
        height=int(occupancy["height_px"]),
        dilation_kernel_px=int(contract["regions"]["board_plus_margin"]["dilation_kernel_px_at_320x240"]),
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    result_rows: list[dict[str, Any]] = []
    physical_identity_matches = True
    reference_numeric_matches = True
    for episode in episodes:
        recording_id = episode["recording_id"]
        bound_rows = rows_by_episode[recording_id]
        if [int(row["evaluation_index"]) for row in bound_rows] != list(range(len(bound_rows))):
            raise ValueError("OR120B evaluation-index drift")
        indices = [int(row["physical_frame_index"]) for row in bound_rows]
        physical_binding = episode["physical_video"]
        physical_frames = [
            cv2.flip(frame, -1)
            for frame in _decode_selected_frames(
                REPO_ROOT / physical_binding["path"],
                selected_indices=np.asarray(indices, dtype=np.int64),
                expected_frame_count=int(physical_binding["frame_count"]),
                expected_width=int(physical_binding["width_px"]),
                expected_height=int(physical_binding["height_px"]),
                output_width=int(occupancy["width_px"]),
                output_height=int(occupancy["height_px"]),
            )
        ]
        candidate_binding = video_map[recording_id]
        if float(candidate_binding["fps"]) != 5.0 or int(candidate_binding["frame_count"]) != len(bound_rows):
            raise ValueError("OR120B candidate metadata drift")
        candidate_path = REPO_ROOT / candidate_binding["path"]
        if sha256_file(candidate_path) != candidate_binding["sha256"]:
            raise ValueError("OR120B candidate-video hash drift")
        candidate_frames = _read_video_frames(candidate_path, len(bound_rows))
        height = int(occupancy["height_px"])
        width = int(occupancy["width_px"])
        physical_edge_sum = np.zeros((height, width), dtype=np.uint32)
        candidate_edge_sum = np.zeros((height, width), dtype=np.uint32)
        for physical, candidate in zip(physical_frames, candidate_frames, strict=True):
            physical_edge_sum += cv2.Canny(
                cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY),
                int(occupancy["canny_low_threshold"]),
                int(occupancy["canny_high_threshold"]),
            ) > 0
            candidate_edge_sum += cv2.Canny(
                cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY),
                int(occupancy["canny_low_threshold"]),
                int(occupancy["canny_high_threshold"]),
            ) > 0
        count = len(bound_rows)
        physical_fraction = physical_edge_sum.astype(np.float64) / count
        candidate_fraction = candidate_edge_sum.astype(np.float64) / count
        persistent_min = float(occupancy["persistent_minimum_frame_fraction"])
        dynamic_min = float(occupancy["dynamic_minimum_frame_fraction"])
        dynamic_max = float(occupancy["dynamic_maximum_frame_fraction_exclusive"])
        physical_persistent = physical_fraction >= persistent_min
        candidate_persistent = candidate_fraction >= persistent_min
        physical_dynamic = (physical_fraction >= dynamic_min) & (physical_fraction < dynamic_max)
        candidate_dynamic = (candidate_fraction >= dynamic_min) & (candidate_fraction < dynamic_max)
        tolerance = int(occupancy["tolerance_dilation_kernel_px"])
        persistent = _binary_tolerant_f1(physical_persistent, candidate_persistent, outside_mask, tolerance)
        dynamic = _binary_tolerant_f1(physical_dynamic, candidate_dynamic, outside_mask, tolerance)
        prior = prior_map[recording_id]
        reference_row = reference_map[recording_id]
        physical_identity_matches = physical_identity_matches and (
            int(persistent["physical_pixels"]) == int(prior["persistent_outside_board"]["physical_pixels"])
            and int(dynamic["physical_pixels"]) == int(prior["dynamic_outside_board"]["physical_pixels"])
        )
        reference_numeric_matches = reference_numeric_matches and (
            abs(float(persistent["f1"]) - float(reference_row["persistent_outside_board"]["f1"])) <= 1.0e-12
            and abs(float(dynamic["f1"]) - float(reference_row["dynamic_outside_board"]["f1"])) <= 1.0e-12
            and int(persistent["candidate_pixels"]) == int(reference_row["persistent_outside_board"]["candidate_pixels"])
            and int(dynamic["candidate_pixels"]) == int(reference_row["dynamic_outside_board"]["candidate_pixels"])
        )
        physical_only_persistent, candidate_only_persistent = _unmatched_residuals(
            physical_persistent, candidate_persistent, outside_mask, tolerance
        )
        physical_only_dynamic, candidate_only_dynamic = _unmatched_residuals(
            physical_dynamic, candidate_dynamic, outside_mask, tolerance
        )
        map_binding = _write_residual_map(
            output_directory / f"{recording_id}-identity-bound-residual.png",
            [
                physical_persistent & outside_mask,
                candidate_persistent & outside_mask,
                physical_only_persistent,
                candidate_only_persistent,
                physical_dynamic & outside_mask,
                candidate_dynamic & outside_mask,
                physical_only_dynamic,
                candidate_only_dynamic,
            ],
        )
        result_rows.append(
            {
                "recording_id": recording_id,
                "split_position": int(episode["split_position"]),
                "frame_count": count,
                "persistent_outside_board": persistent,
                "dynamic_outside_board": dynamic,
                "persistent_f1_delta_vs_or97": float(persistent["f1"]) - float(prior["persistent_outside_board"]["f1"]),
                "dynamic_f1_delta_vs_or97": float(dynamic["f1"]) - float(prior["dynamic_outside_board"]["f1"]),
                "unmatched_pixels": {
                    "physical_only_persistent": int(physical_only_persistent.sum()),
                    "candidate_only_persistent": int(candidate_only_persistent.sum()),
                    "physical_only_dynamic": int(physical_only_dynamic.sum()),
                    "candidate_only_dynamic": int(candidate_only_dynamic.sum()),
                },
                "residual_map": map_binding,
            }
        )

    persistent_values = [float(row["persistent_outside_board"]["f1"]) for row in result_rows]
    dynamic_values = [float(row["dynamic_outside_board"]["f1"]) for row in result_rows]
    summary = _select_successor(persistent_values, dynamic_values, contract["decision_rule"])
    summary["mean_persistent_f1_delta_vs_or97"] = float(np.mean([row["persistent_f1_delta_vs_or97"] for row in result_rows]))
    summary["mean_dynamic_f1_delta_vs_or97"] = float(np.mean([row["dynamic_f1_delta_vs_or97"] for row in result_rows]))
    selected = summary["selected_residual_family"]
    unresolved = contract["decision_rule"]["otherwise_selects"]
    total_frames = sum(row["frame_count"] for row in result_rows)
    gates = {
        "exact_eleven_episode_pairs": len(result_rows) == int(contract["gates"]["expected_episode_count"]),
        "expected_total_physical_and_candidate_frames": total_frames == int(contract["gates"]["expected_total_frame_count"]),
        "physical_occupancy_identity_matches_or97": physical_identity_matches,
        "numeric_rows_match_quarantined_or120_reference": reference_numeric_matches,
        "frozen_contract_implementation_and_test_identities_match": True,
        "single_residual_family_selected": selected != unresolved,
        "zero_render_fit_selection_threshold_change_retry_replay_hardware_or_paid_compute": True,
        "retrospective_diagnostic_not_promotion": True,
    }
    if selected == contract["decision_rule"]["persistent_dominant_selects"] and all(gates.values()):
        status = "PASS_IDENTITY_BOUND_PERSISTENT_STATIC_RESIDUAL_REPRODUCED"
        reviewer_decision = "FREEZE_POST_OBJECT_PERSISTENT_STATIC_SPATIAL_DECOMPOSITION"
        next_transition = "freeze_or121_post_object_persistent_static_spatial_decomposition"
    elif selected == contract["decision_rule"]["dynamic_dominant_selects"] and all(gates.values()):
        status = "PASS_IDENTITY_BOUND_DYNAMIC_RESIDUAL_REPRODUCED"
        reviewer_decision = "FREEZE_POST_OBJECT_DYNAMIC_RESIDUAL_SUCCESSOR"
        next_transition = "freeze_or121_post_object_dynamic_residual_successor"
    else:
        status = "TERMINAL_IDENTITY_BOUND_POST_OBJECT_RESIDUAL_REPRODUCTION_UNRESOLVED"
        reviewer_decision = "CLOSE_RETAINED_POST_OBJECT_SUCCESSOR_LANE"
        next_transition = None
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_post_object_full_timeline_residual_reconciliation_identity_reproduction_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": status,
        "proof_class": contract["proof_class"],
        "identities": {
            "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
            "implementation": contract["frozen_identities"]["implementation"],
            "test": contract["frozen_identities"]["test"],
        },
        "rows": result_rows,
        "summary": summary,
        "gates": gates,
        "execution": {
            "already_open_physical_video_decodes": 11,
            "existing_or119_candidate_video_decodes": 11,
            "physical_frames_read": total_frames,
            "candidate_frames_read": total_frames,
            "residual_map_outputs": len(result_rows),
            "renders": 0,
            "fits": 0,
            "candidate_selections": 0,
            "threshold_changes": 0,
            "retries": 0,
            "simulator_replays": 0,
            "hardware_actions": 0,
            "paid_compute": False,
        },
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": reviewer_decision,
        "next_transition": next_transition,
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

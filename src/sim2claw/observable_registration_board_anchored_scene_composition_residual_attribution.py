"""Evaluator-only board versus outside-board residual attribution for OR81/OR82."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_development_initial_shared_3d_camera_fit import (
    _read_initial_physical_frame,
)
from .observable_registration_host_native_analytic_3d_renderer_capability import (
    REPO_ROOT,
    sha256_file,
)


cv2.ocl.setUseOpenCL(False)

DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_board_anchored_scene_composition_residual_attribution_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_board_anchored_scene_composition_residual_attribution_v1"


def _masked_tolerant_edge_f1(
    physical_gray: np.ndarray,
    candidate_gray: np.ndarray,
    mask: np.ndarray,
    metric: dict[str, Any],
) -> dict[str, float | int]:
    physical_edge = cv2.Canny(
        physical_gray,
        int(metric["canny_low_threshold"]),
        int(metric["canny_high_threshold"]),
    )
    candidate_edge = cv2.Canny(
        candidate_gray,
        int(metric["canny_low_threshold"]),
        int(metric["canny_high_threshold"]),
    )
    kernel_size = int(metric["tolerance_dilation_kernel_px"])
    kernel = np.ones((kernel_size, kernel_size), dtype=np.uint8)
    physical_bool = (physical_edge > 0) & mask
    candidate_bool = (candidate_edge > 0) & mask
    physical_count = int(physical_bool.sum())
    candidate_count = int(candidate_bool.sum())
    if physical_count == 0 or candidate_count == 0:
        return {
            "f1": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "physical_edge_pixels": physical_count,
            "candidate_edge_pixels": candidate_count,
        }
    candidate_dilated = cv2.dilate(candidate_edge, kernel) > 0
    physical_dilated = cv2.dilate(physical_edge, kernel) > 0
    recall = float((physical_bool & candidate_dilated).sum() / physical_count)
    precision = float((candidate_bool & physical_dilated).sum() / candidate_count)
    f1 = 0.0 if precision + recall == 0.0 else 2.0 * precision * recall / (precision + recall)
    return {
        "f1": f1,
        "precision": precision,
        "recall": recall,
        "physical_edge_pixels": physical_count,
        "candidate_edge_pixels": candidate_count,
    }


def evaluate_once(
    contract_path: Path = DEFAULT_CONTRACT,
    output_directory: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR83 one-run receipt already exists")
    contract = json.loads(contract_path.read_text())
    for source in contract["sources"].values():
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    or72 = json.loads(
        (REPO_ROOT / contract["sources"]["or72_contract"]["path"]).read_text()
    )
    or81_contract = json.loads(
        (REPO_ROOT / contract["sources"]["or81_contract"]["path"]).read_text()
    )
    or81_receipt = json.loads(
        (REPO_ROOT / contract["sources"]["or81_receipt"]["path"]).read_text()
    )
    or82_receipt = json.loads(
        (REPO_ROOT / contract["sources"]["or82_receipt"]["path"]).read_text()
    )
    episodes = or72["episodes"]
    annotations = {
        row["recording_id"]: np.asarray(row["points_px"], dtype=np.float64)
        for row in or81_contract["annotations"]["episodes"]
    }
    or81_images = {
        row["recording_id"]: row["candidate_image"]
        for row in or81_receipt["static_metrics_by_episode"]
    }
    or82_images = {
        row["recording_id"]: row["candidate_image"]
        for row in or82_receipt["static_metrics_by_episode"]
    }
    expected_ids = {episode["recording_id"] for episode in episodes}
    if len(episodes) != 4 or set(annotations) != expected_ids or set(or81_images) != expected_ids or set(or82_images) != expected_ids:
        raise ValueError("OR83 episode/image boundary drifted")
    rows: list[dict[str, Any]] = []
    dilation_size = int(contract["regions"]["board_plus_margin"]["dilation_kernel_px"])
    dilation_kernel = np.ones((dilation_size, dilation_size), dtype=np.uint8)
    for episode in episodes:
        recording_id = episode["recording_id"]
        physical_binding = episode["physical_video"]
        if sha256_file(REPO_ROOT / physical_binding["path"]) != physical_binding["sha256"]:
            raise ValueError(f"physical source hash mismatch: {physical_binding['path']}")
        physical = _read_initial_physical_frame(
            REPO_ROOT / physical_binding["path"], width=320, height=240
        )
        candidates: dict[str, np.ndarray] = {}
        for name, binding in (("or81", or81_images[recording_id]), ("or82", or82_images[recording_id])):
            path = REPO_ROOT / binding["path"]
            if sha256_file(path) != binding["sha256"]:
                raise ValueError(f"candidate image hash mismatch: {path}")
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is None or image.shape != (240, 320, 3):
                raise ValueError(f"candidate image unavailable or shape drifted: {path}")
            candidates[name] = image
        board_mask_u8 = np.zeros((240, 320), dtype=np.uint8)
        cv2.fillConvexPoly(
            board_mask_u8,
            np.rint(annotations[recording_id]).astype(np.int32),
            255,
        )
        board_mask = cv2.dilate(board_mask_u8, dilation_kernel) > 0
        outside_mask = ~board_mask
        physical_gray = cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY)
        metrics: dict[str, Any] = {}
        for name, candidate in candidates.items():
            candidate_gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
            metrics[name] = {
                "board_plus_margin": _masked_tolerant_edge_f1(
                    physical_gray, candidate_gray, board_mask, contract["metric"]
                ),
                "outside_board": _masked_tolerant_edge_f1(
                    physical_gray, candidate_gray, outside_mask, contract["metric"]
                ),
            }
        rows.append(
            {
                "recording_id": recording_id,
                "board_mask_pixel_count": int(board_mask.sum()),
                "outside_board_mask_pixel_count": int(outside_mask.sum()),
                "metrics": metrics,
                "or82_minus_or81_board_edge_f1": metrics["or82"]["board_plus_margin"]["f1"] - metrics["or81"]["board_plus_margin"]["f1"],
                "or82_minus_or81_outside_board_edge_f1": metrics["or82"]["outside_board"]["f1"] - metrics["or81"]["outside_board"]["f1"],
            }
        )
    board_deltas = [float(row["or82_minus_or81_board_edge_f1"]) for row in rows]
    outside_deltas = [float(row["or82_minus_or81_outside_board_edge_f1"]) for row in rows]
    gates = {
        "or82_board_edge_f1_improves_every_episode": all(value > 0.0 for value in board_deltas),
        "or82_outside_board_edge_f1_regresses_every_episode": all(value < 0.0 for value in outside_deltas),
        "exact_four_development_episodes": len(rows) == 4,
        "regions_partition_full_frame": all(
            row["board_mask_pixel_count"] + row["outside_board_mask_pixel_count"] == 320 * 240
            for row in rows
        ),
        "no_candidate_render_or_fit": True,
        "validation_and_heldout_closed": True,
    }
    selected = gates["or82_board_edge_f1_improves_every_episode"] and gates[
        "or82_outside_board_edge_f1_regresses_every_episode"
    ]
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_board_anchored_scene_composition_residual_attribution_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": (
            "PASS_BOARD_TO_ROBOT_WORLD_REGISTRATION_SELECTED"
            if selected
            else "TERMINAL_INSUFFICIENT_REGION_SEPARATION"
        ),
        "proof_class": contract["proof_class"],
        "contract": {
            "path": str(contract_path.relative_to(REPO_ROOT)),
            "sha256": sha256_file(contract_path),
        },
        "rows": rows,
        "summary": {
            "mean_or81_board_edge_f1": float(np.mean([row["metrics"]["or81"]["board_plus_margin"]["f1"] for row in rows])),
            "mean_or82_board_edge_f1": float(np.mean([row["metrics"]["or82"]["board_plus_margin"]["f1"] for row in rows])),
            "mean_or81_outside_board_edge_f1": float(np.mean([row["metrics"]["or81"]["outside_board"]["f1"] for row in rows])),
            "mean_or82_outside_board_edge_f1": float(np.mean([row["metrics"]["or82"]["outside_board"]["f1"] for row in rows])),
            "mean_board_edge_f1_delta": float(np.mean(board_deltas)),
            "mean_outside_board_edge_f1_delta": float(np.mean(outside_deltas)),
            "selected_mechanism": "board_to_robot_world_registration" if selected else None,
        },
        "gates": gates,
        "execution": {
            "development_physical_video_decodes": 4,
            "development_physical_frames": 4,
            "existing_candidate_image_reads": 8,
            "new_candidate_images": 0,
            "renders": 0,
            "parameter_fits": 0,
            "simulator_replays": 0,
            "validation_reads": 0,
            "evaluator_heldout_reads": 0,
            "hardware_actions": 0,
            "paid_compute": False,
        },
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": (
            "FREEZE_ONE_BOARD_TO_ROBOT_WORLD_REGISTRATION_FAMILY"
            if selected
            else "DO_NOT_OPEN_NEW_FIT"
        ),
        "next_transition": (
            "freeze_or84_board_to_robot_world_registration_family"
            if selected
            else "stop_camera_scene_lane_insufficient_separation"
        ),
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    output_directory.mkdir(parents=True, exist_ok=True)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

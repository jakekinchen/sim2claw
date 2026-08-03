"""Formalize the post-final board-versus-outside visual sanity residual."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_board_anchored_scene_composition_residual_attribution import _masked_tolerant_edge_f1
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, sha256_file


SCHEMA = "sim2claw.observable_registration_post_final_visual_sanity_residual_attribution_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_final_visual_sanity_residual_attribution_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_final_visual_sanity_residual_attribution_v1"


def load_post_final_visual_sanity_residual_attribution_contract(
    path: Path = DEFAULT_CONTRACT,
) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR92 contract")
    for source in contract["sources"].values():
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    if len(contract["frame_pairs"]) != 6:
        raise ValueError("OR92 frame-pair count drifted")
    if contract["regions"]["board_plus_margin"] != {
        "points_px": [[-3.0, 66.5], [79.0, 52.0], [176.0, 144.5], [71.5, 193.0]],
        "source": "stable_three_of_four_or81_development_annotations",
        "dilation_kernel_px": 15,
    }:
        raise ValueError("OR92 board region drifted")
    resources = contract["resource_boundary"]
    if (
        resources["existing_physical_frame_reads_allowed"] != 6
        or resources["existing_simulator_frame_reads_allowed"] != 6
        or any(
            resources[name] != 0
            for name in (
                "new_physical_video_decodes_allowed",
                "renders_allowed",
                "parameter_fits_allowed",
                "candidate_selections_allowed",
                "simulator_replays_allowed",
                "hardware_actions_allowed",
            )
        )
        or resources["paid_compute_allowed"] is not False
    ):
        raise ValueError("OR92 resource boundary widened")
    if any(contract["authority"].values()):
        raise ValueError("OR92 authority widened")
    return contract


def evaluate_once(
    contract_path: Path = DEFAULT_CONTRACT,
    output_directory: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR92 one-run receipt already exists")
    contract = load_post_final_visual_sanity_residual_attribution_contract(contract_path)
    region = contract["regions"]["board_plus_margin"]
    board_u8 = np.zeros((240, 320), dtype=np.uint8)
    cv2.fillConvexPoly(
        board_u8,
        np.rint(np.asarray(region["points_px"], dtype=np.float64)).astype(np.int32),
        255,
    )
    board = cv2.dilate(
        board_u8,
        np.ones((int(region["dilation_kernel_px"]),) * 2, dtype=np.uint8),
    ) > 0
    outside = ~board
    rows: list[dict[str, Any]] = []
    for pair in contract["frame_pairs"]:
        images: dict[str, np.ndarray] = {}
        for name in ("physical", "simulator"):
            binding = pair[name]
            path = REPO_ROOT / binding["path"]
            if sha256_file(path) != binding["sha256"]:
                raise ValueError(f"frame hash mismatch: {path}")
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is None or image.shape != (240, 320, 3):
                raise ValueError(f"frame shape drifted: {path}")
            images[name] = image
        physical_gray = cv2.cvtColor(images["physical"], cv2.COLOR_BGR2GRAY)
        simulator_gray = cv2.cvtColor(images["simulator"], cv2.COLOR_BGR2GRAY)
        rows.append(
            {
                "recording_id": pair["recording_id"],
                "sample": pair["sample"],
                "board_plus_margin": _masked_tolerant_edge_f1(
                    physical_gray, simulator_gray, board, contract["metric"]
                ),
                "outside_board": _masked_tolerant_edge_f1(
                    physical_gray, simulator_gray, outside, contract["metric"]
                ),
            }
        )
    mean_board = float(np.mean([row["board_plus_margin"]["f1"] for row in rows]))
    mean_outside = float(np.mean([row["outside_board"]["f1"] for row in rows]))
    rule = contract["decision_rule"]["select_robot_workcell_factorization_if"]
    selected = (
        mean_board >= float(rule["minimum_mean_board_plus_margin_edge_f1"])
        and all(
            row["outside_board"]["f1"]
            < float(rule["maximum_every_sample_outside_board_edge_f1"])
            for row in rows
        )
    )
    gates = {
        "exact_six_bound_frame_pairs": len(rows) == 6,
        "regions_partition_full_frame": int(board.sum()) + int(outside.sum()) == 320 * 240,
        "mean_board_plus_margin_edge_f1_at_least_point_five": mean_board >= 0.5,
        "outside_board_edge_f1_below_point_four_every_sample": all(row["outside_board"]["f1"] < 0.4 for row in rows),
        "no_new_physical_decode_render_fit_or_selection": True,
        "post_final_diagnostic_not_promotion": True,
    }
    receipt = {
        "schema_version": "sim2claw.observable_registration_post_final_visual_sanity_residual_attribution_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": "PASS_ROBOT_WORKCELL_FACTORIZATION_SELECTED" if selected else "TERMINAL_INSUFFICIENT_POST_FINAL_REGION_SEPARATION",
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "rows": rows,
        "summary": {"mean_board_plus_margin_edge_f1": mean_board, "mean_outside_board_edge_f1": mean_outside, "minimum_outside_board_edge_f1": min(row["outside_board"]["f1"] for row in rows), "maximum_outside_board_edge_f1": max(row["outside_board"]["f1"] for row in rows), "selected_mechanism": "separate_robot_base_and_static_workcell_registration" if selected else None},
        "gates": gates,
        "execution": {"existing_physical_frame_reads": 6, "existing_simulator_frame_reads": 6, "new_physical_video_decodes": 0, "renders": 0, "parameter_fits": 0, "candidate_selections": 0, "simulator_replays": 0, "hardware_actions": 0, "paid_compute": False},
        "reviewer_decision": "FREEZE_POST_FINAL_SEPARATE_ROBOT_BASE_REGISTRATION_DIAGNOSTIC" if selected else "STOP_POST_FINAL_FACTORIZATION_LANE",
        "next_transition": "freeze_or93_post_final_separate_robot_base_registration_diagnostic" if selected else "stop_or92_insufficient_region_separation",
        "claim_limits": contract["claim_limits"],
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    output_directory.mkdir(parents=True, exist_ok=True)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    evaluate_once()

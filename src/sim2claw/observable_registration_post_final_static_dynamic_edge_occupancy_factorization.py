"""Factor persistent scene edges from dynamic robot edges across OR95 timelines."""

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


cv2.ocl.setUseOpenCL(False)

SCHEMA = "sim2claw.observable_registration_post_final_static_dynamic_edge_occupancy_factorization_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_final_static_dynamic_edge_occupancy_factorization_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_final_static_dynamic_edge_occupancy_factorization_v1"


def load_post_final_static_dynamic_edge_occupancy_factorization_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR97 contract")
    for source in contract["sources"].values():
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    occupancy = contract["edge_occupancy"]
    if occupancy["persistent_minimum_frame_fraction"] != 0.80 or occupancy["dynamic_minimum_frame_fraction"] != 0.05 or occupancy["dynamic_maximum_frame_fraction_exclusive"] != 0.80:
        raise ValueError("OR97 occupancy thresholds drifted")
    resources = contract["resource_boundary"]
    zero_keys = ("renders_allowed", "fits_allowed", "candidate_selections_allowed", "simulator_replays_allowed", "hardware_actions_allowed")
    if any(resources[key] != 0 for key in zero_keys) or resources["paid_compute_allowed"] is not False or any(contract["authority"].values()):
        raise ValueError("OR97 resource or authority boundary drifted")
    if contract["claim_limits"]["same_video_semantic_match"] is not False or contract["claim_limits"]["untouched_cohort_remaining"] is not False:
        raise ValueError("OR97 claim boundary drifted")
    return contract


def _read_video_frames(path: Path, expected_count: int) -> list[np.ndarray]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError(f"cannot open candidate video: {path}")
    frames: list[np.ndarray] = []
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            frames.append(frame)
    finally:
        capture.release()
    if len(frames) != expected_count or any(frame.shape[:2] != (240, 320) for frame in frames):
        raise ValueError("OR97 candidate video frame count or shape drifted")
    return frames


def _binary_tolerant_f1(physical: np.ndarray, candidate: np.ndarray, region: np.ndarray, tolerance: int) -> dict[str, float | int]:
    physical = physical & region
    candidate = candidate & region
    physical_count = int(physical.sum())
    candidate_count = int(candidate.sum())
    if physical_count == 0 or candidate_count == 0:
        return {"f1": 0.0, "precision": 0.0, "recall": 0.0, "physical_pixels": physical_count, "candidate_pixels": candidate_count}
    kernel = np.ones((tolerance, tolerance), dtype=np.uint8)
    physical_dilated = cv2.dilate(physical.astype(np.uint8) * 255, kernel) > 0
    candidate_dilated = cv2.dilate(candidate.astype(np.uint8) * 255, kernel) > 0
    precision = float((candidate & physical_dilated).sum() / candidate_count)
    recall = float((physical & candidate_dilated).sum() / physical_count)
    f1 = 0.0 if precision + recall == 0.0 else 2.0 * precision * recall / (precision + recall)
    return {"f1": f1, "precision": precision, "recall": recall, "physical_pixels": physical_count, "candidate_pixels": candidate_count}


def _write_map(path: Path, maps: list[np.ndarray]) -> dict[str, str]:
    panels = [np.repeat((value.astype(np.uint8) * 255)[:, :, None], 3, axis=2) for value in maps]
    montage = np.concatenate(panels, axis=1)
    ok, encoded = cv2.imencode(".png", montage, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not ok:
        raise RuntimeError("OR97 occupancy map encoding failed")
    path.write_bytes(encoded.tobytes())
    return {"path": str(path.relative_to(REPO_ROOT)), "sha256": sha256_file(path), "layout": "physical_persistent_candidate_persistent_physical_dynamic_candidate_dynamic"}


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR97 one-run receipt already exists")
    contract = load_post_final_static_dynamic_edge_occupancy_factorization_contract(contract_path)
    or96 = json.loads((REPO_ROOT / contract["sources"]["or96_closeout"]["path"]).read_text())
    if or96["selected_mechanism"] != "robot_articulation_and_renderer_native_scene_content_factorization":
        raise ValueError("OR96 did not authorize OR97 factorization")
    or95_contract = json.loads((REPO_ROOT / contract["sources"]["or95_contract"]["path"]).read_text())
    or95 = json.loads((REPO_ROOT / contract["sources"]["or95_receipt"]["path"]).read_text())
    frame_rows = json.loads((REPO_ROOT / contract["sources"]["or95_frame_rows"]["path"]).read_text())["rows"]
    episodes = _episode_inventory(or95_contract)
    video_map = {row["recording_id"]: row for row in or95["candidate_videos"]}
    rows_by_episode = {episode["recording_id"]: [] for episode in episodes}
    for row in frame_rows:
        rows_by_episode[row["recording_id"]].append(row)
    occupancy = contract["edge_occupancy"]
    _, outside_mask = _region_masks(
        np.asarray(contract["regions"]["board_plus_margin"]["points_px"], dtype=np.float64),
        width=int(occupancy["width_px"]),
        height=int(occupancy["height_px"]),
        dilation_kernel_px=int(contract["regions"]["board_plus_margin"]["dilation_kernel_px_at_320x240"]),
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    result_rows: list[dict[str, Any]] = []
    for episode in episodes:
        recording_id = episode["recording_id"]
        bound_rows = rows_by_episode[recording_id]
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
                output_width=320,
                output_height=240,
            )
        ]
        candidate_binding = video_map[recording_id]
        candidate_path = REPO_ROOT / candidate_binding["path"]
        if sha256_file(candidate_path) != candidate_binding["sha256"]:
            raise ValueError("OR97 candidate video hash mismatch")
        candidate_frames = _read_video_frames(candidate_path, len(bound_rows))
        physical_edge_sum = np.zeros((240, 320), dtype=np.uint32)
        candidate_edge_sum = np.zeros((240, 320), dtype=np.uint32)
        for physical, candidate in zip(physical_frames, candidate_frames, strict=True):
            physical_edge_sum += (cv2.Canny(cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY), int(occupancy["canny_low_threshold"]), int(occupancy["canny_high_threshold"])) > 0)
            candidate_edge_sum += (cv2.Canny(cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY), int(occupancy["canny_low_threshold"]), int(occupancy["canny_high_threshold"])) > 0)
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
        persistent = _binary_tolerant_f1(physical_persistent, candidate_persistent, outside_mask, int(occupancy["tolerance_dilation_kernel_px"]))
        dynamic = _binary_tolerant_f1(physical_dynamic, candidate_dynamic, outside_mask, int(occupancy["tolerance_dilation_kernel_px"]))
        map_binding = _write_map(output_directory / f"{recording_id}-occupancy.png", [physical_persistent, candidate_persistent, physical_dynamic, candidate_dynamic])
        result_rows.append({"recording_id": recording_id, "split_position": int(episode["split_position"]), "frame_count": count, "persistent_outside_board": persistent, "dynamic_outside_board": dynamic, "occupancy_map": map_binding})
    rule = contract["decision_rule"]
    persistent_values = [float(row["persistent_outside_board"]["f1"]) for row in result_rows]
    dynamic_values = [float(row["dynamic_outside_board"]["f1"]) for row in result_rows]
    persistent_below = sum(value < float(rule["minimum_adequate_persistent_outside_board_f1"]) for value in persistent_values)
    dynamic_below = sum(value < float(rule["minimum_adequate_dynamic_outside_board_f1"]) for value in dynamic_values)
    minimum_below = int(rule["minimum_episode_count_below_each_inadequate_threshold"])
    persistent_inadequate = persistent_below >= minimum_below
    dynamic_inadequate = dynamic_below >= minimum_below
    if persistent_inadequate and dynamic_inadequate:
        mechanism = rule["both_below_selects"]
    elif persistent_inadequate:
        mechanism = rule["persistent_only_below_selects"]
    elif dynamic_inadequate:
        mechanism = rule["dynamic_only_below_selects"]
    else:
        mechanism = rule["neither_below_selects"]
    gates = {"exact_eleven_episode_pairs": len(result_rows) == 11, "expected_total_physical_and_candidate_frames": sum(row["frame_count"] for row in result_rows) == 1210, "persistent_factor_decidable": persistent_below >= minimum_below or (11 - persistent_below) >= minimum_below, "dynamic_factor_decidable": dynamic_below >= minimum_below or (11 - dynamic_below) >= minimum_below, "zero_render_fit_selection_replay_hardware_or_paid_compute": True, "post_final_diagnostic_not_promotion": True}
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_post_final_static_dynamic_edge_occupancy_factorization_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": "PASS_STATIC_SCENE_CONTENT_AND_ROBOT_ARTICULATION_SELECTED" if mechanism == rule["both_below_selects"] and all(gates.values()) else "PASS_SINGLE_FACTOR_SELECTED" if all(gates.values()) else "TERMINAL_STATIC_DYNAMIC_FACTORIZATION_UNRESOLVED",
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "rows": result_rows,
        "summary": {"mean_persistent_outside_board_edge_occupancy_f1": float(np.mean(persistent_values)), "mean_dynamic_outside_board_edge_occupancy_f1": float(np.mean(dynamic_values)), "episodes_persistent_below_threshold": persistent_below, "episodes_dynamic_below_threshold": dynamic_below, "selected_mechanism": mechanism},
        "gates": gates,
        "execution": {"already_open_physical_video_decodes": 11, "existing_candidate_video_decodes": 11, "physical_frames_read": 1210, "candidate_frames_read": 1210, "occupancy_map_outputs": len(result_rows), "renders": 0, "fits": 0, "candidate_selections": 0, "simulator_replays": 0, "hardware_actions": 0, "paid_compute": False},
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": "FREEZE_STATIC_SCENE_CONTENT_THEN_ROBOT_ARTICULATION_SUCCESSORS" if mechanism == rule["both_below_selects"] else "FREEZE_SELECTED_SINGLE_FACTOR_SUCCESSOR",
        "next_transition": "freeze_or98_renderer_native_static_scene_content_successor" if persistent_inadequate else "freeze_or98_robot_articulation_successor" if dynamic_inadequate else None,
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

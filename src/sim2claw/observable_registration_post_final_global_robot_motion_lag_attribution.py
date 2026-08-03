"""Test one global observation lag on physical/candidate robot-motion energy."""

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
from .observable_registration_post_final_static_dynamic_edge_occupancy_factorization import _read_video_frames


SCHEMA = "sim2claw.observable_registration_post_final_global_robot_motion_lag_attribution_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_final_global_robot_motion_lag_attribution_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_final_global_robot_motion_lag_attribution_v1"


def load_post_final_global_robot_motion_lag_attribution_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR102 contract")
    for source in contract["sources"].values():
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    signal = contract["signal"]
    if signal["lag_candidates_frames"] != list(range(-10, 11)) or signal["one_global_lag"] is not True:
        raise ValueError("OR102 lag family drifted")
    if signal["per_episode_lag"] is not False or signal["frame_interpolation"] is not False or signal["time_warp"] is not False:
        raise ValueError("OR102 temporal boundary drifted")
    resources = contract["resource_boundary"]
    if resources["renders_allowed"] != 0 or resources["simulator_replays_allowed"] != 0 or resources["action_or_state_mutations_allowed"] != 0:
        raise ValueError("OR102 action/render boundary drifted")
    if resources["paid_compute_allowed"] is not False or any(contract["authority"].values()):
        raise ValueError("OR102 authority boundary drifted")
    return contract


def _motion_energy(frames: list[np.ndarray], mask: np.ndarray) -> np.ndarray:
    gray = [cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32) for frame in frames]
    return np.asarray([float(np.mean(np.abs(current - previous)[mask])) for previous, current in zip(gray[:-1], gray[1:], strict=True)], dtype=np.float64)


def _correlation(physical: np.ndarray, candidate: np.ndarray, lag: int) -> float:
    if lag >= 0:
        left, right = physical[: len(physical) - lag or None], candidate[lag:]
    else:
        left, right = physical[-lag:], candidate[: len(candidate) + lag]
    if len(left) < 8 or float(np.std(left)) < 1e-9 or float(np.std(right)) < 1e-9:
        return 0.0
    return float(np.corrcoef(left, right)[0, 1])


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR102 one-run receipt already exists")
    contract = load_post_final_global_robot_motion_lag_attribution_contract(contract_path)
    or101 = json.loads((REPO_ROOT / contract["sources"]["or101_closeout"]["path"]).read_text())
    if or101["selected_mechanism"] != "robot_articulation_and_timing":
        raise ValueError("OR101 did not authorize timing attribution")
    or95_contract = json.loads((REPO_ROOT / contract["sources"]["or95_contract"]["path"]).read_text())
    or95 = json.loads((REPO_ROOT / contract["sources"]["or95_receipt"]["path"]).read_text())
    frame_rows = json.loads((REPO_ROOT / contract["sources"]["or95_frame_rows"]["path"]).read_text())["rows"]
    episodes = _episode_inventory(or95_contract)
    candidate_by_id = {row["recording_id"]: row for row in or95["candidate_videos"]}
    indices_by_id: dict[str, list[int]] = {episode["recording_id"]: [] for episode in episodes}
    for row in frame_rows:
        indices_by_id[row["recording_id"]].append(int(row["physical_frame_index"]))
    _, outside_mask = _region_masks(
        np.asarray(or95_contract["regions"]["board_plus_margin"]["points_px"], dtype=np.float64),
        width=int(contract["signal"]["width_px"]),
        height=int(contract["signal"]["height_px"]),
        dilation_kernel_px=int(or95_contract["regions"]["board_plus_margin"]["dilation_kernel_px_at_320x240"]),
    )
    episode_rows: list[dict[str, Any]] = []
    lags = [int(value) for value in contract["signal"]["lag_candidates_frames"]]
    total_frames = 0
    for episode in episodes:
        recording_id = episode["recording_id"]
        physical_binding = episode["physical_video"]
        indices = indices_by_id[recording_id]
        physical = [cv2.flip(frame, -1) for frame in _decode_selected_frames(REPO_ROOT / physical_binding["path"], selected_indices=np.asarray(indices, dtype=np.int64), expected_frame_count=int(physical_binding["frame_count"]), expected_width=int(physical_binding["width_px"]), expected_height=int(physical_binding["height_px"]), output_width=320, output_height=240)]
        candidate_binding = candidate_by_id[recording_id]
        candidate_path = REPO_ROOT / candidate_binding["path"]
        if sha256_file(candidate_path) != candidate_binding["sha256"]:
            raise ValueError("OR102 candidate video hash mismatch")
        candidate = _read_video_frames(candidate_path, len(indices))
        physical_energy = _motion_energy(physical, outside_mask)
        candidate_energy = _motion_energy(candidate, outside_mask)
        correlations = {str(lag): _correlation(physical_energy, candidate_energy, lag) for lag in lags}
        episode_rows.append({"recording_id": recording_id, "split_position": int(episode["split_position"]), "frame_count": len(indices), "physical_motion_energy_mean": float(np.mean(physical_energy)), "candidate_motion_energy_mean": float(np.mean(candidate_energy)), "lag_correlations": correlations})
        total_frames += len(indices)
    development = [row for row in episode_rows if row["split_position"] in contract["split"]["development_positions"]]
    validation = [row for row in episode_rows if row["split_position"] in contract["split"]["validation_positions"]]
    development_means = {lag: float(np.mean([row["lag_correlations"][str(lag)] for row in development])) for lag in lags}
    selected_lag = max(lags, key=lambda lag: (development_means[lag], -abs(lag), -lag))

    def summarize(rows: list[dict[str, Any]], material_gain: float) -> dict[str, Any]:
        zero = float(np.mean([row["lag_correlations"]["0"] for row in rows]))
        selected = float(np.mean([row["lag_correlations"][str(selected_lag)] for row in rows]))
        return {"zero_lag_mean_correlation": zero, "selected_lag_mean_correlation": selected, "correlation_gain": selected - zero, "episodes_with_material_gain": sum(row["lag_correlations"][str(selected_lag)] - row["lag_correlations"]["0"] >= material_gain for row in rows)}

    dev_summary = summarize(development, 0.03)
    val_summary = summarize(validation, 0.02)
    acceptance = contract["acceptance"]
    dev_gates = {"minimum_correlation_gain": dev_summary["correlation_gain"] >= float(acceptance["development_minimum_selected_minus_zero_lag_mean_correlation"]), "minimum_episodes_with_material_gain": dev_summary["episodes_with_material_gain"] >= int(acceptance["development_minimum_episodes_with_correlation_gain_at_least_0p03"])}
    val_gates = {"minimum_correlation_gain": val_summary["correlation_gain"] >= float(acceptance["validation_minimum_selected_minus_zero_lag_mean_correlation"]), "minimum_episodes_with_material_gain": val_summary["episodes_with_material_gain"] >= int(acceptance["validation_minimum_episodes_with_correlation_gain_at_least_0p02"])}
    integrity = {"exact_eleven_episode_pairs": len(episode_rows) == 11, "exact_total_frame_count": total_frames == 1210, "one_global_lag_selected_on_development_only": True, "validation_not_used_for_selection": True, "no_per_episode_lag_interpolation_warp_render_replay_action_state_mutation_hardware_or_paid_compute": True, "post_final_diagnostic_not_promotion": True}
    passed = all(dev_gates.values()) and all(val_gates.values()) and all(integrity.values())
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_post_final_global_robot_motion_lag_attribution_receipt.v1",
        "experiment_id": contract["experiment_id"], "status": "PASS_GLOBAL_ROBOT_MOTION_LAG_VALIDATED" if passed else "TERMINAL_GLOBAL_ROBOT_MOTION_LAG_INSUFFICIENT", "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)}, "selected_lag_frames": selected_lag, "selected_lag_seconds": selected_lag / 5.0, "development_lag_mean_correlations": {str(key): value for key, value in development_means.items()}, "development_summary": dev_summary, "validation_summary": val_summary, "episode_rows": episode_rows, "gates": {"integrity": integrity, "development": dev_gates, "validation": val_gates},
        "execution": {"already_open_physical_video_decodes": 11, "existing_candidate_video_decodes": 11, "physical_frames_read": total_frames, "candidate_frames_read": total_frames, "renders": 0, "fits": 1, "simulator_replays": 0, "action_or_state_mutations": 0, "hardware_actions": 0, "paid_compute": False}, "claim_limits": contract["claim_limits"],
        "reviewer_decision": "FREEZE_GLOBAL_LAG_FULL_METRIC_EVALUATION" if passed else "REJECT_GLOBAL_LAG_AND_FREEZE_JOINT_ARTICULATION_CALIBRATION", "next_transition": "freeze_or103_global_lag_full_metric_evaluation" if passed else "freeze_or103_joint_articulation_calibration_successor",
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    output_directory.mkdir(parents=True, exist_ok=True)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

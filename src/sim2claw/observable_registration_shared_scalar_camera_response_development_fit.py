"""Fit a shared two-parameter non-spatial camera response on development videos."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_development_shared_camera_baseline import (
    _decode_selected_frames,
    _motion_union_similarity,
    _summary,
    evaluation_times,
    physical_frame_indices,
)
from .observable_registration_host_native_analytic_3d_renderer_capability import (
    REPO_ROOT,
    sha256_file,
)
from .observable_registration_temporal_pixel_similarity import (
    _linear_similarity,
    _tolerant_edge_f1,
)


cv2.ocl.setUseOpenCL(False)

DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_shared_scalar_camera_response_development_fit_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_shared_scalar_camera_response_development_fit_v1"


def apply_response(frame: np.ndarray, *, gain: float, bias: float) -> np.ndarray:
    """Apply one scalar response identically to every BGR sample."""
    return np.clip(
        np.rint(frame.astype(np.float64) * float(gain) + float(bias)), 0.0, 255.0
    ).astype(np.uint8)


def _decode_candidate_video(path: Path, expected_count: int) -> list[np.ndarray]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError(f"renderer candidate video unavailable: {path}")
    frames: list[np.ndarray] = []
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame.shape != (240, 320, 3):
                raise ValueError(f"renderer candidate frame shape drifted: {path}")
            frames.append(frame)
    finally:
        capture.release()
    if len(frames) != expected_count:
        raise ValueError(
            f"renderer candidate frame count drifted: {path} {len(frames)} != {expected_count}"
        )
    return frames


def _metric_gates(
    pooled: dict[str, Any],
    phases: dict[str, dict[str, float | int]],
    episodes: list[dict[str, Any]],
    acceptance: dict[str, Any],
) -> dict[str, bool]:
    return {
        "pooled_mean_full_frame_linear_pixel_similarity": pooled[
            "full_frame_linear_pixel_similarity"
        ]["mean"]
        >= acceptance["minimum_pooled_mean_full_frame_linear_pixel_similarity"],
        "pooled_p10_full_frame_linear_pixel_similarity": pooled[
            "full_frame_linear_pixel_similarity"
        ]["p10"]
        >= acceptance["minimum_pooled_p10_full_frame_linear_pixel_similarity"],
        "pooled_mean_motion_union_linear_pixel_similarity": pooled[
            "motion_union_linear_pixel_similarity"
        ]["mean"]
        >= acceptance["minimum_pooled_mean_motion_union_linear_pixel_similarity"],
        "each_phase_mean_full_frame_linear_pixel_similarity": all(
            value["mean"]
            >= acceptance["minimum_each_phase_mean_full_frame_linear_pixel_similarity"]
            for value in phases.values()
        ),
        "pooled_mean_tolerant_edge_f1": pooled["tolerant_edge_f1"]["mean"]
        >= acceptance["minimum_pooled_mean_tolerant_edge_f1"],
        "each_development_episode_mean_full_frame_linear_pixel_similarity": all(
            row["full_frame_linear_pixel_similarity"]["mean"]
            >= acceptance[
                "minimum_each_development_episode_mean_full_frame_linear_pixel_similarity"
            ]
            for row in episodes
        ),
    }


def fit_once(
    contract_path: Path = DEFAULT_CONTRACT,
    output_directory: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR86 one-run receipt already exists")
    contract = json.loads(contract_path.read_text())
    for source in contract["sources"].values():
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    or85_closeout = json.loads(
        (REPO_ROOT / contract["sources"]["or85_closeout"]["path"]).read_text()
    )
    if or85_closeout["reviewer_decision"] != "FREEZE_ONE_SHARED_SCALAR_CAMERA_RESPONSE_DEVELOPMENT_FIT":
        raise ValueError("OR85 did not authorize the OR86 family")
    or85_receipt = json.loads(
        (REPO_ROOT / contract["sources"]["or85_receipt"]["path"]).read_text()
    )
    or85_contract = json.loads(
        (REPO_ROOT / contract["sources"]["or85_contract"]["path"]).read_text()
    )
    if any(
        contract[key] != or85_contract[key]
        for key in ("timeline", "metric", "acceptance")
    ):
        raise ValueError("OR85 timeline, metric, or acceptance drifted")
    or72 = json.loads(
        (REPO_ROOT / contract["sources"]["or72_contract"]["path"]).read_text()
    )
    episodes = or72["episodes"]
    if len(episodes) != 4 or any(row["split_role"] != "development" for row in episodes):
        raise ValueError("OR86 development split boundary drifted")
    rows_binding = or85_receipt["rows"]
    rows_path = REPO_ROOT / rows_binding["path"]
    if sha256_file(rows_path) != rows_binding["sha256"]:
        raise ValueError("OR85 timeline rows hash mismatch")
    or85_rows = json.loads(rows_path.read_text())["rows"]
    rows_by_episode: dict[str, list[dict[str, Any]]] = {}
    for row in or85_rows:
        rows_by_episode.setdefault(row["recording_id"], []).append(row)
    videos = {row["recording_id"]: row for row in or85_receipt["candidate_videos"]}
    episode_data: list[dict[str, Any]] = []
    for episode in episodes:
        recording_id = episode["recording_id"]
        physical_binding = episode["physical_video"]
        if sha256_file(REPO_ROOT / physical_binding["path"]) != physical_binding["sha256"]:
            raise ValueError(f"physical source hash mismatch: {physical_binding['path']}")
        times = evaluation_times(
            float(episode["state_trace"]["duration_seconds"]),
            float(contract["output"]["fps"]),
        )
        indices = physical_frame_indices(
            times,
            frame_count=int(physical_binding["frame_count"]),
            duration_seconds=float(physical_binding["duration_seconds"]),
        )
        physical_frames = [
            cv2.flip(frame, -1)
            for frame in _decode_selected_frames(
                REPO_ROOT / physical_binding["path"],
                selected_indices=indices,
                expected_frame_count=int(physical_binding["frame_count"]),
                expected_width=int(physical_binding["width_px"]),
                expected_height=int(physical_binding["height_px"]),
                output_width=int(contract["output"]["width_px"]),
                output_height=int(contract["output"]["height_px"]),
            )
        ]
        video = videos[recording_id]
        video_path = REPO_ROOT / video["path"]
        if sha256_file(video_path) != video["sha256"]:
            raise ValueError(f"OR85 candidate video hash mismatch: {video_path}")
        simulator_frames = _decode_candidate_video(video_path, len(physical_frames))
        timeline_rows = rows_by_episode[recording_id]
        if len(timeline_rows) != len(physical_frames):
            raise ValueError("OR85 row and video frame boundary drifted")
        episode_data.append(
            {
                "recording_id": recording_id,
                "physical": physical_frames,
                "simulator": simulator_frames,
                "timeline_rows": timeline_rows,
            }
        )

    family = contract["family"]
    candidates = [
        (float(gain), float(bias))
        for gain in family["gain_values"]
        for bias in family["bias_values"]
    ]
    if len(candidates) != int(family["candidate_count"]):
        raise ValueError("OR86 candidate grid count drifted")
    candidate_rows: list[dict[str, Any]] = []
    selected_frame_rows_by_key: dict[tuple[float, float], list[dict[str, Any]]] = {}
    for gain, bias in candidates:
        all_rows: list[dict[str, Any]] = []
        episode_summaries: list[dict[str, Any]] = []
        for data in episode_data:
            episode_rows: list[dict[str, Any]] = []
            previous_physical: np.ndarray | None = None
            previous_candidate: np.ndarray | None = None
            for slot, (physical, simulator, timeline_row) in enumerate(
                zip(
                    data["physical"],
                    data["simulator"],
                    data["timeline_rows"],
                    strict=True,
                )
            ):
                candidate = apply_response(simulator, gain=gain, bias=bias)
                physical_gray = cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY)
                candidate_gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
                motion, motion_pixels = _motion_union_similarity(
                    physical,
                    candidate,
                    previous_physical,
                    previous_candidate,
                    contract["metric"]["motion_union"],
                )
                row = {
                    "recording_id": data["recording_id"],
                    "evaluation_index": slot,
                    "phase": timeline_row["phase"],
                    "full_frame_linear_pixel_similarity": _linear_similarity(
                        physical, candidate
                    ),
                    "motion_union_linear_pixel_similarity": motion,
                    "motion_union_pixel_count": motion_pixels,
                    "tolerant_edge_f1": _tolerant_edge_f1(
                        physical_gray, candidate_gray, contract["metric"]["edge"]
                    ),
                }
                episode_rows.append(row)
                all_rows.append(row)
                previous_physical = physical
                previous_candidate = candidate
            episode_summaries.append(
                {
                    "recording_id": data["recording_id"],
                    "sample_count": len(episode_rows),
                    "full_frame_linear_pixel_similarity": _summary(
                        [
                            float(row["full_frame_linear_pixel_similarity"])
                            for row in episode_rows
                        ]
                    ),
                }
            )
        phases = {
            phase: _summary(
                [
                    float(row["full_frame_linear_pixel_similarity"])
                    for row in all_rows
                    if row["phase"] == phase
                ]
            )
            for phase in sorted({str(row["phase"]) for row in all_rows})
        }
        pooled = {
            "full_frame_linear_pixel_similarity": _summary(
                [float(row["full_frame_linear_pixel_similarity"]) for row in all_rows]
            ),
            "motion_union_linear_pixel_similarity": _summary(
                [
                    float(row["motion_union_linear_pixel_similarity"])
                    for row in all_rows
                    if row["motion_union_linear_pixel_similarity"] is not None
                ]
            ),
            "tolerant_edge_f1": _summary(
                [float(row["tolerant_edge_f1"]) for row in all_rows]
            ),
            "phase_full_frame_linear_pixel_similarity": phases,
        }
        gates = _metric_gates(
            pooled, phases, episode_summaries, contract["acceptance"]
        )
        candidate_rows.append(
            {
                "gain": gain,
                "bias": bias,
                "eligible": all(gates.values()),
                "pooled": pooled,
                "episode_summaries": episode_summaries,
                "metric_gates": gates,
            }
        )
        selected_frame_rows_by_key[(gain, bias)] = all_rows
    eligible = [row for row in candidate_rows if row["eligible"]]
    selected = (
        max(
            eligible,
            key=lambda row: (
                row["pooled"]["full_frame_linear_pixel_similarity"]["mean"],
                row["pooled"]["tolerant_edge_f1"]["mean"],
                -row["gain"],
                -row["bias"],
            ),
        )
        if eligible
        else None
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    output_videos: list[dict[str, Any]] = []
    selected_rows_path: Path | None = None
    if selected is not None:
        gain = float(selected["gain"])
        bias = float(selected["bias"])
        for data in episode_data:
            path = output_directory / f"{data['recording_id']}.mp4"
            writer = cv2.VideoWriter(
                str(path),
                cv2.VideoWriter_fourcc(*contract["output"]["candidate_video_codec"]),
                float(contract["output"]["fps"]),
                (
                    int(contract["output"]["width_px"]),
                    int(contract["output"]["height_px"]),
                ),
            )
            if not writer.isOpened():
                raise RuntimeError("cannot open OR86 candidate video writer")
            try:
                for simulator in data["simulator"]:
                    writer.write(apply_response(simulator, gain=gain, bias=bias))
            finally:
                writer.release()
            output_videos.append(
                {
                    "recording_id": data["recording_id"],
                    "path": str(path.relative_to(REPO_ROOT)),
                    "sha256": sha256_file(path),
                    "frame_count": len(data["simulator"]),
                    "fps": float(contract["output"]["fps"]),
                }
            )
        selected_rows_artifact: dict[str, Any] = {
            "schema_version": "sim2claw.observable_registration_shared_scalar_camera_response_development_fit_rows.v1",
            "gain": gain,
            "bias": bias,
            "rows": selected_frame_rows_by_key[(gain, bias)],
        }
        selected_rows_artifact["artifact_sha256"] = canonical_digest(
            selected_rows_artifact
        )
        selected_rows_path = output_directory / "selected_rows.json"
        atomic_write_json(selected_rows_path, selected_rows_artifact)
    integrity_gates = {
        "exact_35_candidate_evaluations": len(candidate_rows) == 35,
        "exact_14805_candidate_frame_evaluations": len(candidate_rows) * 423
        == 14805,
        "one_shared_two_parameter_response": selected is not None,
        "no_spatial_regional_channel_or_frame_parameters": all(
            int(family[key]) == 0
            for key in (
                "spatial_parameters",
                "per_channel_parameters",
                "per_region_parameters",
                "per_frame_parameters",
            )
        ),
        "validation_and_heldout_closed": True,
        "no_replay_geometry_timing_state_physics_hardware_or_paid_compute": True,
    }
    passed = selected is not None and all(integrity_gates.values())
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_shared_scalar_camera_response_development_fit_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": (
            "PASS_SHARED_SCALAR_CAMERA_RESPONSE_DEVELOPMENT_PIXEL_TARGET"
            if passed
            else "TERMINAL_NO_SHARED_SCALAR_CAMERA_RESPONSE_CANDIDATE"
        ),
        "proof_class": contract["proof_class"],
        "contract": {
            "path": str(contract_path.relative_to(REPO_ROOT)),
            "sha256": sha256_file(contract_path),
        },
        "candidate_results": candidate_rows,
        "eligible_candidate_count": len(eligible),
        "selected": selected,
        "selected_rows": (
            {
                "path": str(selected_rows_path.relative_to(REPO_ROOT)),
                "sha256": sha256_file(selected_rows_path),
            }
            if selected_rows_path is not None
            else None
        ),
        "candidate_videos": output_videos,
        "integrity_gates": integrity_gates,
        "execution": {
            "development_episode_reads": 4,
            "development_physical_video_decodes": 4,
            "or85_renderer_video_decodes": 4,
            "physical_frames_read": 423,
            "renderer_frames_read": 423,
            "candidate_evaluations": len(candidate_rows),
            "candidate_frame_evaluations": len(candidate_rows) * 423,
            "selected_candidate_videos": len(output_videos),
            "shared_parameter_count": 2,
            "validation_reads": 0,
            "evaluator_heldout_reads": 0,
            "simulator_replays": 0,
            "camera_geometry_time_state_or_physics_fits": 0,
            "hardware_actions": 0,
            "paid_compute": False,
            "prohibited_candidate_inputs_read": [],
        },
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": (
            "OPEN_REJECT_ONLY_VALIDATION_WITH_FROZEN_CAMERA_WORKCELL_RESPONSE"
            if passed
            else "KEEP_VALIDATION_CLOSED_AND_REATTRIBUTE_APPEARANCE_RESIDUAL"
        ),
        "next_transition": (
            "freeze_or87_reject_only_validation_camera_workcell_response"
            if passed
            else "freeze_or87_appearance_residual_attribution"
        ),
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(fit_once(), sort_keys=True))

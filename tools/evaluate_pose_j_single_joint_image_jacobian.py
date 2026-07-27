#!/usr/bin/env python3
"""Compare prospective physical and simulated Pi-tag image Jacobians."""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from tools.fit_current_session_pi_articulated_cad_bundle import (
    Model,
    detect_tags,
    load_contract,
    project,
    tag_local_points,
    tag_world,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SWEEP = (
    ROOT
    / "runs/geometric-hover/"
    "20260727-pose-j-single-joint-image-jacobian-sweep-tricam-v1"
)
DEFAULT_CANDIDATE = (
    ROOT
    / "runs/pi-link-tag-calibration/"
    "20260727-current-session-articulated-cad-bundle-v2/receipt.json"
)
DEFAULT_CONTRACT = (
    ROOT
    / "configs/evaluations/current_session_pi_articulated_cad_bundle_v2.json"
)
DEFAULT_OUTPUT = (
    DEFAULT_SWEEP / "evaluation/single-joint-image-jacobian-v1.json"
)
STAGES = (
    (1, 0, "shoulder_pan", 1),
    (2, 1, "shoulder_lift", 2),
    (3, 2, "elbow_flex", 2),
    (4, 3, "wrist_flex", 2),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def regression(x: np.ndarray, pixels: np.ndarray) -> dict[str, Any]:
    design = np.column_stack((x, np.ones(len(x), dtype=np.float64)))
    coefficients = np.linalg.lstsq(design, pixels, rcond=None)[0]
    predicted = design @ coefficients
    residual_sum = float(np.sum((pixels - predicted) ** 2))
    centered_sum = float(np.sum((pixels - np.mean(pixels, axis=0)) ** 2))
    slope = coefficients[0]
    return {
        "sample_count": int(len(x)),
        "joint_minimum_degrees": float(np.min(x)),
        "joint_maximum_degrees": float(np.max(x)),
        "slope_xy_pixels_per_degree": slope.tolist(),
        "slope_magnitude_pixels_per_degree": float(np.linalg.norm(slope)),
        "combined_r_squared": (
            float(1.0 - residual_sum / centered_sum)
            if centered_sum > 0.0
            else 0.0
        ),
    }


def angle_degrees(first: np.ndarray, second: np.ndarray) -> float:
    denominator = float(np.linalg.norm(first) * np.linalg.norm(second))
    if denominator <= 1e-12:
        return math.inf
    cosine = float(np.clip(np.dot(first, second) / denominator, -1.0, 1.0))
    return float(np.degrees(np.arccos(cosine)))


def load_joint_samples(path: Path) -> tuple[np.ndarray, np.ndarray]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    host = np.asarray(
        [row["host_continuous_ns"] for row in rows], dtype=np.int64
    )
    joints = np.asarray(
        [row["follower_actual_position_degrees"] for row in rows],
        dtype=np.float64,
    )
    require(
        len(rows) >= 1161
        and host.shape == (len(rows),)
        and joints.shape == (len(rows), 6)
        and np.all(np.diff(host) > 0),
        f"invalid joint samples: {path}",
    )
    return host, joints


def observed_tracks(
    stage_path: Path,
    receipt: dict[str, Any],
    joint_index: int,
) -> tuple[dict[int, dict[str, Any]], dict[int, np.ndarray]]:
    video_path = (
        stage_path
        / "final_hold_camera/pi_motion/pi_imx708.browser.mp4"
    )
    pts_path = stage_path / "final_hold_camera/pi_motion/pi_imx708.pts"
    samples_path = stage_path / "joint_samples.jsonl"
    require(
        video_path.is_file() and pts_path.is_file() and samples_path.is_file(),
        f"stage capture is incomplete: {stage_path}",
    )
    pts_seconds = np.loadtxt(pts_path, dtype=np.float64) / 1000.0
    host, joints = load_joint_samples(samples_path)
    start = float(receipt["camera_finished"]["pi"]["host_monotonic_start"])
    tracks: dict[int, list[tuple[float, float, float, int]]] = {}
    matched_q: dict[int, list[np.ndarray]] = {}
    capture = cv2.VideoCapture(str(video_path))
    frame_index = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if frame_index % 3 == 0 and frame_index < len(pts_seconds):
            nominal_ns = int((start + pts_seconds[frame_index]) * 1e9)
            insertion = bisect.bisect_left(host, nominal_ns)
            insertion = min(max(insertion, 1), len(host) - 1)
            nearest = (
                insertion
                if abs(int(host[insertion]) - nominal_ns)
                < abs(int(host[insertion - 1]) - nominal_ns)
                else insertion - 1
            )
            if abs(int(host[nearest]) - nominal_ns) <= 30_000_000:
                for tag_id, corners in detect_tags(frame).items():
                    center = np.mean(corners, axis=0)
                    tracks.setdefault(tag_id, []).append(
                        (
                            float(joints[nearest, joint_index]),
                            float(center[0]),
                            float(center[1]),
                            nearest,
                        )
                    )
                    matched_q.setdefault(tag_id, []).append(
                        joints[nearest].copy()
                    )
        frame_index += 1
    capture.release()
    require(
        frame_index == len(pts_seconds),
        f"Pi frame/PTS count changed for {stage_path}",
    )
    public = {}
    q_by_tag = {}
    for tag_id, values in tracks.items():
        array = np.asarray(values, dtype=np.float64)
        if len(array) < 5:
            continue
        public[tag_id] = regression(array[:, 0], array[:, 1:3])
        q_by_tag[tag_id] = np.asarray(matched_q[tag_id], dtype=np.float64)
    return public, q_by_tag


def simulated_track(
    *,
    robot: Model,
    q_values: np.ndarray,
    joint_index: int,
    tag_id: int,
    body_map: dict[int, str],
    mounts: dict[int, np.ndarray],
    camera: np.ndarray,
    offsets: np.ndarray,
    local_points: np.ndarray,
    focal: float,
    principal: np.ndarray,
) -> dict[str, Any]:
    centers = []
    for joints in q_values:
        robot.set_pose(joints, offsets, np.ones(5, dtype=np.float64))
        points = tag_world(
            robot, body_map[tag_id], mounts[tag_id], local_points
        )
        pixels, valid = project(points, camera, focal, principal)
        require(np.all(valid), f"tag {tag_id} projected behind Pi")
        centers.append(np.mean(pixels, axis=0))
    return regression(q_values[:, joint_index], np.asarray(centers))


def evaluate(
    sweep: Path,
    candidate_path: Path,
    contract_path: Path,
    output: Path,
) -> dict[str, Any]:
    require(not output.exists(), f"refusing to overwrite {output}")
    packet_path = sweep / "packet.json"
    review_path = sweep / "review.json"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    review = json.loads(review_path.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    contract, _ = load_contract(contract_path)
    require(
        packet["schema_version"] == "sim2claw.wrist_view_reposition_packet.v2"
        and review["packet_sha256"] == sha256(packet_path)
        and len(packet["stages"]) == 4,
        "sweep packet/review binding changed",
    )
    candidate_manifest = (
        ROOT / contract["sources"]["candidate_manifest"]["path"]
    )
    manifest = json.loads(candidate_manifest.read_text(encoding="utf-8"))
    robot = Model(manifest["candidate_config"])
    parameters = candidate["parameters"]
    camera = np.concatenate(
        (
            parameters["camera_world_rotation_vector_radians"],
            parameters["camera_world_translation_m"],
        )
    )
    offsets = np.asarray(
        parameters["joint_zero_offsets_degrees"], dtype=np.float64
    )
    mounts = {
        int(tag_id): np.concatenate(
            (
                mount["body_tag_rotation_vector_radians"],
                mount["body_tag_translation_m"],
            )
        )
        for tag_id, mount in parameters["tag_mounts"].items()
    }
    body_map = {
        int(tag_id): body
        for tag_id, body in candidate["model"]["tag_body_map"].items()
    }
    local_points = tag_local_points(
        float(contract["frozen_model"]["tag_black_edge_m"])
    )
    focal = float(candidate["model"]["focal_px"])
    principal = np.asarray(
        candidate["model"]["principal_point_px"], dtype=np.float64
    )
    stage_results = {}
    stage_sources = {}
    joint_results = {}
    for stage_number, joint_index, joint_name, primary_tag in STAGES:
        stage_path = sweep / f"stage-{stage_number}"
        receipt_path = stage_path / "execution_receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        require(
            receipt["status"] == "completed_wrist_view_reposition_stage"
            and receipt["physical_follower_torque_enabled"] is False
            and receipt["error"] is None
            and receipt["completed_motion_samples"] == 1161
            and receipt["completed_capture_hold_samples"] == 80
            and receipt["camera_finished"]["overhead"][
                "action_interval_enclosed_by_callback_frames"
            ]
            and receipt["camera_finished"]["wrist"][
                "action_interval_enclosed_by_callback_frames"
            ]
            and receipt["camera_finished"]["pi"]["action_interval_enclosed"],
            f"stage {stage_number} is not an admitted tricam completion",
        )
        observed, q_by_tag = observed_tracks(
            stage_path, receipt, joint_index
        )
        comparisons = {}
        for tag_id, observed_metrics in sorted(observed.items()):
            simulated = simulated_track(
                robot=robot,
                q_values=q_by_tag[tag_id],
                joint_index=joint_index,
                tag_id=tag_id,
                body_map=body_map,
                mounts=mounts,
                camera=camera,
                offsets=offsets,
                local_points=local_points,
                focal=focal,
                principal=principal,
            )
            observed_slope = np.asarray(
                observed_metrics["slope_xy_pixels_per_degree"]
            )
            simulated_slope = np.asarray(
                simulated["slope_xy_pixels_per_degree"]
            )
            simulated_magnitude = float(
                simulated["slope_magnitude_pixels_per_degree"]
            )
            comparisons[str(tag_id)] = {
                "body": body_map[tag_id],
                "observed": observed_metrics,
                "simulated_identity_joint_map": simulated,
                "magnitude_ratio_observed_over_simulated": (
                    float(
                        observed_metrics[
                            "slope_magnitude_pixels_per_degree"
                        ]
                        / simulated_magnitude
                    )
                    if simulated_magnitude > 1e-9
                    else None
                ),
                "direction_difference_degrees": angle_degrees(
                    observed_slope, simulated_slope
                ),
            }
        primary = comparisons[str(primary_tag)]
        ratio = primary["magnitude_ratio_observed_over_simulated"]
        direction = primary["direction_difference_degrees"]
        passed = bool(
            primary["observed"]["combined_r_squared"] >= 0.75
            and primary["simulated_identity_joint_map"][
                "combined_r_squared"
            ]
            >= 0.95
            and ratio is not None
            and 0.70 <= ratio <= 1.30
            and direction <= 15.0
        )
        stage_results[str(stage_number)] = {
            "joint_index": joint_index,
            "joint_name": joint_name,
            "primary_tag_id": primary_tag,
            "tag_comparisons": comparisons,
        }
        joint_results[joint_name] = {
            "primary_tag_id": primary_tag,
            "observed_slope_xy_pixels_per_degree": primary["observed"][
                "slope_xy_pixels_per_degree"
            ],
            "simulated_slope_xy_pixels_per_degree": primary[
                "simulated_identity_joint_map"
            ]["slope_xy_pixels_per_degree"],
            "magnitude_ratio_observed_over_simulated": ratio,
            "direction_difference_degrees": direction,
            "observed_r_squared": primary["observed"][
                "combined_r_squared"
            ],
            "local_identity_mapping_gate_passed": passed,
        }
        stage_sources[str(stage_number)] = {
            "receipt_path": str(receipt_path.relative_to(ROOT)),
            "receipt_sha256": sha256(receipt_path),
            "action_sha256": receipt["action_sha256"],
            "frame_counts": {
                "C922": receipt["camera_finished"]["overhead"][
                    "callback_frame_count"
                ],
                "D405": receipt["camera_finished"]["wrist"][
                    "callback_frame_count"
                ],
                "Pi": receipt["camera_finished"]["pi"]["observed_video"][
                    "frame_count"
                ],
            },
        }
    receipt = {
        "schema_version": "sim2claw.pose_j_single_joint_image_jacobian.v1",
        "status": "retrospective_joint_image_jacobian_diagnostic_completed",
        "proof_class": "physical_no_contact_tricam_joint_image_jacobian_diagnostic",
        "sources": {
            "packet": {
                "path": str(packet_path.relative_to(ROOT)),
                "sha256": sha256(packet_path),
            },
            "review": {
                "path": str(review_path.relative_to(ROOT)),
                "sha256": sha256(review_path),
            },
            "static_candidate": {
                "path": str(candidate_path.relative_to(ROOT)),
                "sha256": sha256(candidate_path),
                "limitation": "failed retrospective heldout and used only as the local simulated projection comparator",
            },
            "static_contract": {
                "path": str(contract_path.relative_to(ROOT)),
                "sha256": sha256(contract_path),
            },
            "stages": stage_sources,
        },
        "method": {
            "physical_signal": "linear regression of unique AprilTag centers against nearest host-clock-aligned follower encoder samples",
            "frame_stride": 3,
            "maximum_frame_to_joint_delta_ms": 30.0,
            "simulated_signal": "same physical encoder rows through current MuJoCo CAD, historical tag-body map, and static-candidate camera/tag mounts",
            "local_gate": {
                "observed_r_squared_minimum": 0.75,
                "simulated_r_squared_minimum": 0.95,
                "magnitude_ratio_range": [0.70, 1.30],
                "direction_difference_maximum_degrees": 15.0,
            },
        },
        "joint_results": joint_results,
        "stage_results": stage_results,
        "summary": {
            "local_identity_mapping_passed_joints": [
                name
                for name, row in joint_results.items()
                if row["local_identity_mapping_gate_passed"]
            ],
            "local_identity_mapping_failed_joints": [
                name
                for name, row in joint_results.items()
                if not row["local_identity_mapping_gate_passed"]
            ],
        },
        "limitations": {
            "camera_exposure_synchronized": False,
            "host_clock_nearest_neighbor_alignment_only": True,
            "static_projection_candidate_passed_heldout": False,
            "global_joint_transform_promotion": False,
            "simulator_parameter_promotion": False,
            "pawn_contact": False,
            "task_or_policy_evidence": False,
        },
        "authority": {
            "diagnostic_only": True,
            "physical_robot_control": False,
            "simulator_parameter_promotion": False,
            "pawn_contact": False,
            "task_success": False,
            "policy": False,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sweep", type=Path, default=DEFAULT_SWEEP)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    evaluate(
        arguments.sweep.resolve(),
        arguments.candidate.resolve(),
        arguments.contract.resolve(),
        arguments.output.resolve(),
    )


if __name__ == "__main__":
    main()

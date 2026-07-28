#!/usr/bin/env python3
"""Extract wrist-camera background motion from the Pose-J joint sweep."""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SWEEP = (
    ROOT
    / "runs/geometric-hover/"
    "20260727-pose-j-single-joint-image-jacobian-sweep-tricam-v1"
)
DEFAULT_OUTPUT = (
    DEFAULT_SWEEP / "evaluation/d405-background-image-jacobian-v1.json"
)
STAGES = (
    (1, 0, "shoulder_pan"),
    (2, 1, "shoulder_lift"),
    (3, 2, "elbow_flex"),
    (4, 3, "wrist_flex"),
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
        and joints.shape == (len(rows), 6)
        and np.all(np.diff(host) > 0),
        f"invalid joint samples: {path}",
    )
    return host, joints


def nearest_joint_rows(
    callback_host_ns: np.ndarray,
    joint_host_ns: np.ndarray,
    joints: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    frame_indices = []
    matched = []
    deltas_ms = []
    for frame_index, timestamp in enumerate(callback_host_ns):
        insertion = bisect.bisect_left(joint_host_ns, int(timestamp))
        insertion = min(max(insertion, 1), len(joint_host_ns) - 1)
        nearest = (
            insertion
            if abs(int(joint_host_ns[insertion]) - int(timestamp))
            < abs(int(joint_host_ns[insertion - 1]) - int(timestamp))
            else insertion - 1
        )
        delta = abs(int(joint_host_ns[nearest]) - int(timestamp)) / 1e6
        if delta > 30.0:
            continue
        frame_indices.append(frame_index)
        matched.append(joints[nearest])
        deltas_ms.append(delta)
    require(len(matched) >= 100, "too few action-aligned D405 frames")
    return (
        np.asarray(frame_indices, dtype=np.int64),
        np.asarray(matched, dtype=np.float64),
        np.asarray(deltas_ms, dtype=np.float64),
    )


def load_stage(
    stage_path: Path,
    receipt: dict[str, Any],
) -> tuple[list[np.ndarray], np.ndarray, dict[str, Any]]:
    capture = stage_path / "final_hold_camera/native_dual_camera"
    video_path = capture / "wrist_d405.native.mov"
    callback_path = capture / "camera_callback_timestamps.jsonl"
    sample_path = stage_path / "joint_samples.jsonl"
    require(
        video_path.is_file()
        and callback_path.is_file()
        and sample_path.is_file(),
        f"incomplete D405 stage: {stage_path}",
    )
    wrist_receipt = receipt["camera_finished"]["wrist"]
    require(
        wrist_receipt["video_sha256"] == sha256(video_path)
        and wrist_receipt["callback_timestamp_sha256"]
        == sha256(callback_path)
        and wrist_receipt["action_interval_enclosed_by_callback_frames"]
        and wrist_receipt["apple_drop_callback_count"] == 0
        and wrist_receipt["writer_backpressure_count"] == 0,
        f"D405 receipt binding failed: {stage_path}",
    )
    callback_rows = [
        json.loads(line)
        for line in callback_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    timestamps = np.asarray(
        [
            row["host_continuous_ns"]
            for row in callback_rows
            if row["role"] == "d405" and row["appended_to_writer"]
        ],
        dtype=np.int64,
    )
    video = cv2.VideoCapture(str(video_path))
    frames = []
    while True:
        ok, frame = video.read()
        if not ok:
            break
        frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    video.release()
    require(
        len(frames)
        == len(timestamps)
        == wrist_receipt["callback_frame_count"]
        == wrist_receipt["container_frame_count"],
        f"D405 frame/callback count changed: {stage_path}",
    )
    host, joints = load_joint_samples(sample_path)
    aligned_indices, matched, delta_ms = nearest_joint_rows(
        timestamps, host, joints
    )
    aligned_frames = [frames[int(index)] for index in aligned_indices]
    return aligned_frames, matched, {
        "video_path": str(video_path.relative_to(ROOT)),
        "video_sha256": sha256(video_path),
        "callback_path": str(callback_path.relative_to(ROOT)),
        "callback_sha256": sha256(callback_path),
        "joint_samples_path": str(sample_path.relative_to(ROOT)),
        "joint_samples_sha256": sha256(sample_path),
        "frame_count": len(frames),
        "action_aligned_frame_count": len(aligned_frames),
        "excluded_pre_or_post_roll_frame_count": (
            len(frames) - len(aligned_frames)
        ),
        "frame_to_joint_delta_ms": {
            "maximum": float(np.max(delta_ms)),
            "median": float(np.median(delta_ms)),
        },
    }


def evaluate_stage(
    frames: list[np.ndarray],
    joints: np.ndarray,
    joint_index: int,
) -> dict[str, Any]:
    cv2.setRNGSeed(1979)
    detector = cv2.SIFT_create(nfeatures=1000)
    features = [detector.detectAndCompute(frame, None) for frame in frames]
    matcher = cv2.BFMatcher(cv2.NORM_L2)
    rows = []
    for frame_index in range(1, len(frames)):
        delta_joint = float(
            joints[frame_index, joint_index]
            - joints[frame_index - 1, joint_index]
        )
        if abs(delta_joint) < 0.05:
            continue
        prior_points, prior_descriptors = features[frame_index - 1]
        next_points, next_descriptors = features[frame_index]
        if prior_descriptors is None or next_descriptors is None:
            continue
        matches = matcher.knnMatch(
            prior_descriptors, next_descriptors, k=2
        )
        accepted = [
            first
            for first, second in matches
            if first.distance < 0.75 * second.distance
        ]
        if len(accepted) < 10:
            continue
        prior = np.float32(
            [prior_points[row.queryIdx].pt for row in accepted]
        )
        following = np.float32(
            [next_points[row.trainIdx].pt for row in accepted]
        )
        affine, inliers = cv2.estimateAffinePartial2D(
            prior,
            following,
            method=cv2.RANSAC,
            ransacReprojThreshold=1.5,
            maxIters=1000,
        )
        if affine is None or inliers is None:
            continue
        rows.append(
            (
                delta_joint,
                float(affine[0, 2]),
                float(affine[1, 2]),
                float(np.arctan2(affine[1, 0], affine[0, 0])),
                float(
                    np.log(np.hypot(affine[0, 0], affine[1, 0]))
                ),
                len(accepted),
                int(np.sum(inliers)),
            )
        )
    array = np.asarray(rows, dtype=np.float64)
    require(array.shape[0] >= 40, "insufficient adjacent D405 motion pairs")
    delta = array[:, 0]
    signals = array[:, 1:5]
    slope = np.sum(delta[:, None] * signals, axis=0) / np.sum(delta**2)
    predicted = delta[:, None] * slope
    denominator = float(np.sum(signals**2))
    r_squared = float(
        1.0 - np.sum((signals - predicted) ** 2) / denominator
    )
    passed = bool(len(rows) >= 60 and r_squared >= 0.45)
    return {
        "joint_minimum_degrees": float(np.min(joints[:, joint_index])),
        "joint_maximum_degrees": float(np.max(joints[:, joint_index])),
        "motion_pair_count": len(rows),
        "median_feature_match_count": float(np.median(array[:, 5])),
        "median_ransac_inlier_count": float(np.median(array[:, 6])),
        "affine_image_jacobian_per_degree": {
            "translation_x_px": float(slope[0]),
            "translation_y_px": float(slope[1]),
            "rotation_radians": float(slope[2]),
            "log_scale": float(slope[3]),
        },
        "combined_zero_intercept_r_squared": r_squared,
        "physical_background_motion_gate_passed": passed,
    }


def evaluate(sweep: Path, output: Path) -> dict[str, Any]:
    require(not output.exists(), f"refusing to overwrite {output}")
    stage_results = {}
    stage_sources = {}
    for stage_number, joint_index, joint_name in STAGES:
        stage_path = sweep / f"stage-{stage_number}"
        receipt_path = stage_path / "execution_receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        require(
            receipt["status"] == "completed_wrist_view_reposition_stage"
            and receipt["physical_follower_torque_enabled"] is False
            and receipt["error"] is None,
            f"stage {stage_number} is not a torque-off completion",
        )
        frames, joints, source = load_stage(stage_path, receipt)
        result = evaluate_stage(frames, joints, joint_index)
        result.update(
            {
                "joint_index": joint_index,
                "joint_name": joint_name,
            }
        )
        stage_results[str(stage_number)] = result
        stage_sources[str(stage_number)] = {
            "receipt_path": str(receipt_path.relative_to(ROOT)),
            "receipt_sha256": sha256(receipt_path),
            **source,
        }
    passed = [
        row["joint_name"]
        for row in stage_results.values()
        if row["physical_background_motion_gate_passed"]
    ]
    receipt = {
        "schema_version": "sim2claw.pose_j_d405_background_image_jacobian.v1",
        "status": "physical_d405_background_image_jacobian_completed",
        "proof_class": "physical_no_contact_d405_background_motion_diagnostic",
        "sources": stage_sources,
        "method": {
            "features": "SIFT nfeatures=1000 on adjacent native 424x240 D405 frames",
            "matching": "L2 KNN ratio 0.75",
            "motion_model": "RANSAC partial affine, 1.5 px threshold",
            "joint_alignment": "nearest host mach-continuous encoder sample within 30 ms",
            "regression": "zero-intercept adjacent affine parameter delta versus measured joint delta",
            "gate": {
                "minimum_motion_pairs": 60,
                "minimum_combined_r_squared": 0.45,
            },
        },
        "stage_results": stage_results,
        "summary": {
            "joints_with_observed_d405_background_motion": passed,
            "all_four_joint_signals_passed": len(passed) == 4,
            "wrist_flex_signal_is_available": "wrist_flex" in passed,
        },
        "limitations": {
            "camera_exposure_synchronized": False,
            "metric_depth": False,
            "D405_camera_to_wrist_extrinsic_available": False,
            "scene_geometry_used": False,
            "simulated_image_motion_comparison": False,
            "global_motion_is_a_partial_affine_approximation": True,
            "pawn_contact": False,
            "task_or_policy_evidence": False,
        },
        "authority": {
            "diagnostic_only": True,
            "physical_robot_control": False,
            "simulator_parameter_promotion": False,
            "pawn_contact": False,
            "task_success": False,
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
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    evaluate(arguments.sweep.resolve(), arguments.output.resolve())


if __name__ == "__main__":
    main()

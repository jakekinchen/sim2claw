#!/usr/bin/env python3
"""Evaluate gauge-free D405 rotation against model camera-mount rotation."""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from sim2claw.paths import REPO_ROOT
from tools.fit_current_session_pi_articulated_cad_bundle import (
    Model,
    detect_tags,
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


def rotation_trajectory_metrics(
    observed_angle_degrees: np.ndarray,
    simulated_angle_degrees: np.ndarray,
) -> dict[str, float | int]:
    observed = np.asarray(observed_angle_degrees, dtype=np.float64)
    simulated = np.asarray(simulated_angle_degrees, dtype=np.float64)
    require(
        observed.ndim == simulated.ndim == 1
        and observed.shape == simulated.shape
        and len(observed) >= 3
        and np.all(np.isfinite(observed))
        and np.all(np.isfinite(simulated)),
        "rotation trajectories are invalid",
    )
    residual = observed - simulated
    observed_rms = float(np.sqrt(np.mean(observed**2)))
    simulated_rms = float(np.sqrt(np.mean(simulated**2)))
    correlation = (
        float(np.corrcoef(observed, simulated)[0, 1])
        if np.std(observed) > 1e-12 and np.std(simulated) > 1e-12
        else 0.0
    )
    return {
        "sample_count": int(len(observed)),
        "observed_rotation_rms_degrees": observed_rms,
        "simulated_rotation_rms_degrees": simulated_rms,
        "observed_over_simulated_rotation_rms_ratio": (
            float(observed_rms / simulated_rms)
            if simulated_rms > 1e-12
            else float("inf")
        ),
        "rotation_angle_rmse_degrees": float(
            np.sqrt(np.mean(residual**2))
        ),
        "rotation_angle_max_error_degrees": float(
            np.max(np.abs(residual))
        ),
        "rotation_angle_correlation": correlation,
    }


def bound(binding: dict[str, Any]) -> Path:
    path = (REPO_ROOT / str(binding["path"])).resolve()
    require(
        path.is_file() and sha256(path) == binding["sha256"],
        f"bound source changed: {path}",
    )
    return path


def joint_samples(path: Path) -> tuple[np.ndarray, np.ndarray]:
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
        host.shape == (721,)
        and joints.shape == (721, 6)
        and np.all(np.diff(host) > 0),
        "downstream heldout joint samples changed",
    )
    return host, joints


def body_rotation(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    body_name: str,
) -> np.ndarray:
    body_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, body_name
    )
    require(body_id >= 0, f"missing model body {body_name}")
    return np.asarray(data.xmat[body_id], dtype=np.float64).reshape(3, 3)


def stage_rotations(
    *,
    stage_path: Path,
    receipt: dict[str, Any],
    packet_stage: dict[str, Any],
    candidate_config: dict[str, Any],
    intrinsics: dict[str, Any],
    method: dict[str, Any],
) -> dict[str, Any]:
    native = stage_path / "final_hold_camera/native_dual_camera"
    video_path = native / "wrist_d405.native.mov"
    callback_path = native / "camera_callback_timestamps.jsonl"
    samples_path = stage_path / "joint_samples.jsonl"
    wrist = receipt["camera_finished"]["wrist"]
    require(
        sha256(video_path) == wrist["video_sha256"]
        and sha256(callback_path) == wrist["callback_timestamp_sha256"]
        and sha256(samples_path) == receipt["joint_samples_sha256"]
        and wrist["action_interval_enclosed_by_callback_frames"]
        and wrist["apple_drop_callback_count"] == 0
        and wrist["writer_backpressure_count"] == 0,
        "D405 capture binding changed",
    )
    callbacks = [
        json.loads(line)
        for line in callback_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    timestamps = np.asarray(
        [
            row["host_continuous_ns"]
            for row in callbacks
            if row["role"] == "d405" and row["appended_to_writer"]
        ],
        dtype=np.int64,
    )
    host, joints = joint_samples(samples_path)
    focal = np.asarray(intrinsics["focal_length_px"], dtype=np.float64)
    principal = np.asarray(
        intrinsics["principal_point_px"], dtype=np.float64
    )
    source_size = np.asarray(
        [intrinsics["width"], intrinsics["height"]], dtype=np.float64
    )
    output_size = np.asarray(
        [wrist["configured_width"], wrist["configured_height"]],
        dtype=np.float64,
    )
    scale = output_size / source_size
    require(
        np.allclose(scale, scale[0])
        and abs(float(scale[0]) - 0.5) <= 1e-12,
        "D405 native output no longer has the frozen half-resolution scale",
    )
    camera_matrix = np.asarray(
        [
            [focal[0] * scale[0], 0.0, principal[0] * scale[0]],
            [0.0, focal[1] * scale[1], principal[1] * scale[1]],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    half = float(method["nominal_tag_black_edge_m"]) / 2.0
    object_points = np.asarray(
        [
            [-half, half, 0.0],
            [half, half, 0.0],
            [half, -half, 0.0],
            [-half, -half, 0.0],
        ],
        dtype=np.float64,
    )
    video = cv2.VideoCapture(str(video_path))
    observed_rotations = []
    matched_joints = []
    alignment_ms = []
    frame_count = 0
    while True:
        ok, frame = video.read()
        if not ok:
            break
        timestamp = int(timestamps[frame_count])
        insertion = bisect.bisect_left(host, timestamp)
        insertion = min(max(insertion, 1), len(host) - 1)
        nearest = (
            insertion
            if abs(int(host[insertion]) - timestamp)
            < abs(int(host[insertion - 1]) - timestamp)
            else insertion - 1
        )
        delta_ms = abs(int(host[nearest]) - timestamp) / 1e6
        tags = detect_tags(frame)
        if (
            delta_ms
            <= float(method["maximum_frame_to_joint_delta_ms"])
            and int(method["fixed_scene_tag_id"]) in tags
        ):
            solved, rotation_vector, _ = cv2.solvePnP(
                object_points,
                tags[int(method["fixed_scene_tag_id"])],
                camera_matrix,
                np.zeros(5, dtype=np.float64),
                flags=cv2.SOLVEPNP_IPPE_SQUARE,
            )
            if solved:
                observed_rotations.append(
                    Rotation.from_rotvec(
                        rotation_vector.ravel()
                    ).as_matrix().T
                )
                matched_joints.append(joints[nearest].copy())
                alignment_ms.append(delta_ms)
        frame_count += 1
    video.release()
    require(
        frame_count == len(timestamps) == wrist["callback_frame_count"],
        "D405 frame and callback counts changed",
    )
    observed = np.asarray(observed_rotations, dtype=np.float64)
    q_values = np.asarray(matched_joints, dtype=np.float64)
    anchor = np.asarray(
        packet_stage["expected_anchor_degrees"], dtype=np.float64
    )
    active = np.asarray(method["active_joint_indices"], dtype=int)
    reference = np.all(
        np.abs(q_values[:, active] - anchor[None, active])
        <= float(method["anchor_reference_radius_degrees"]),
        axis=1,
    )
    require(
        len(observed) >= int(method["minimum_detected_frame_count"])
        and int(np.count_nonzero(reference))
        >= int(method["minimum_reference_frame_count"]),
        "D405 fixed-tag trajectory is not observable",
    )
    observed_reference = Rotation.from_matrix(
        observed[reference]
    ).mean().as_matrix()
    observed_angles = np.degrees(
        Rotation.from_matrix(
            np.einsum("ij,njk->nik", observed_reference.T, observed)
        ).magnitude()
    )
    robot = Model(candidate_config)
    model = robot.model
    data = robot.data
    simulated = []
    for row in q_values:
        robot.set_pose(
            row,
            np.zeros(5, dtype=np.float64),
            np.ones(5, dtype=np.float64),
        )
        simulated.append(body_rotation(model, data, "left_camera_mount"))
    simulated = np.asarray(simulated, dtype=np.float64)
    robot.set_pose(
        anchor,
        np.zeros(5, dtype=np.float64),
        np.ones(5, dtype=np.float64),
    )
    simulated_reference = body_rotation(
        model, data, "left_camera_mount"
    )
    simulated_angles = np.degrees(
        Rotation.from_matrix(
            np.einsum("ij,njk->nik", simulated_reference.T, simulated)
        ).magnitude()
    )
    metrics = rotation_trajectory_metrics(
        observed_angles, simulated_angles
    )
    return {
        "metrics": metrics,
        "detected_frame_count": int(len(observed)),
        "reference_frame_count": int(np.count_nonzero(reference)),
        "total_d405_frame_count": int(frame_count),
        "tag_detection_fraction": float(len(observed) / frame_count),
        "frame_to_joint_delta_ms": {
            "maximum": float(np.max(alignment_ms)),
            "median": float(np.median(alignment_ms)),
        },
        "final_residual_degrees": receipt["final_residual_degrees"],
        "sources": {
            "video_path": str(video_path.relative_to(REPO_ROOT)),
            "video_sha256": sha256(video_path),
            "callback_path": str(callback_path.relative_to(REPO_ROOT)),
            "callback_sha256": sha256(callback_path),
            "joint_samples_path": str(samples_path.relative_to(REPO_ROOT)),
            "joint_samples_sha256": sha256(samples_path),
        },
    }


def evaluate(contract_path: Path) -> dict[str, Any]:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    require(
        contract.get("schema_version")
        == "sim2claw.calibration_graph_d405_rotation_heldout.v1"
        and contract.get("status")
        == "frozen_after_execution_before_action_interval_trajectory_open"
        and contract["method"]["operational_safety_inspection"]
        == {
            "stage_1_final_hold_frame_opened": True,
            "stage_1_action_interval_trajectory_opened": False,
            "stage_2_any_frame_opened": False,
            "purpose": "between_stage_operational_safety_only",
            "metric_or_outcome_scoring_performed": False,
        }
        and contract["authority"]
        == {
            "read_bound_physical_capture": True,
            "evaluate_downstream_rotation_mapping": True,
            "fit_parameters": False,
            "mapping_approval": False,
            "camera": False,
            "gateway": False,
            "serial": False,
            "physical_motion": False,
            "physical_task_attempt": False,
            "simulator_promotion": False,
            "transfer_claim": False,
        },
        "D405 rotation heldout contract widened",
    )
    packet_path = bound(contract["sources"]["packet"])
    review_path = bound(contract["sources"]["review"])
    manifest_path = bound(contract["sources"]["candidate_manifest"])
    intrinsics_path = bound(contract["sources"]["d405_intrinsics"])
    bound(contract["implementation"])
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    review = json.loads(review_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    intrinsics_receipt = json.loads(
        intrinsics_path.read_text(encoding="utf-8")
    )
    require(
        review["packet_sha256"] == sha256(packet_path)
        and review["status"] == "admitted_for_one_execution_per_stage"
        and len(packet["stages"]) == 2,
        "D405 rotation packet/review binding changed",
    )
    stage_results = {}
    gates = contract["gates"]
    for stage_index, specification in sorted(
        contract["stages"].items(), key=lambda row: int(row[0])
    ):
        index = int(stage_index)
        receipt_path = bound(specification["execution_receipt"])
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        packet_stage = packet["stages"][index - 1]
        require(
            receipt["packet_sha256"] == sha256(packet_path)
            and receipt["review_sha256"] == sha256(review_path)
            and receipt["stage_index"] == index
            and receipt["action_sha256"]
            == packet_stage["action_sha256"]
            == specification["expected_action_sha256"]
            and receipt["status"] == "completed_wrist_view_reposition_stage"
            and receipt["physical_follower_torque_enabled"] is False
            and receipt["error"] is None,
            f"stage {index} is not an exact torque-off completion",
        )
        result = stage_rotations(
            stage_path=receipt_path.parent,
            receipt=receipt,
            packet_stage=packet_stage,
            candidate_config=manifest["candidate_config"],
            intrinsics=intrinsics_receipt["calibration"]["intrinsics"][
                "color"
            ],
            method=contract["method"],
        )
        metrics = result["metrics"]
        joint_index = int(specification["joint_index"])
        checks = {
            "rotation_signal": metrics["simulated_rotation_rms_degrees"]
            >= float(gates["minimum_simulated_rotation_rms_degrees"]),
            "rotation_ratio": float(gates["rotation_rms_ratio_range"][0])
            <= metrics["observed_over_simulated_rotation_rms_ratio"]
            <= float(gates["rotation_rms_ratio_range"][1]),
            "rotation_rmse": metrics["rotation_angle_rmse_degrees"]
            <= float(gates["rotation_angle_rmse_max_degrees"]),
            "rotation_max": metrics["rotation_angle_max_error_degrees"]
            <= float(gates["rotation_angle_max_error_degrees"]),
            "rotation_correlation": metrics["rotation_angle_correlation"]
            >= float(gates["minimum_rotation_angle_correlation"]),
            "return_residual": abs(
                float(result["final_residual_degrees"][joint_index])
            )
            <= float(gates["maximum_active_joint_return_residual_degrees"]),
        }
        stage_results[stage_index] = {
            "joint_name": specification["joint_name"],
            "joint_index": joint_index,
            **result,
            "checks": checks,
            "passed": all(checks.values()),
        }
    passed = all(row["passed"] for row in stage_results.values())
    output = (REPO_ROOT / contract["output_path"]).resolve()
    require(not output.exists(), "immutable D405 rotation heldout exists")
    receipt = {
        "schema_version": "sim2claw.calibration_graph_d405_rotation_heldout_receipt.v1",
        "status": (
            "downstream_rotation_heldout_passed_no_automatic_promotion"
            if passed
            else "downstream_rotation_heldout_rejected_no_automatic_promotion"
        ),
        "proof_class": "prospective_exact_action_physical_d405_fixed_tag_downstream_rotation_mapping_heldout",
        "contract_path": str(contract_path.relative_to(REPO_ROOT)),
        "contract_sha256": sha256(contract_path),
        "stage_results": stage_results,
        "heldout_passed": passed,
        "physical_model_mapping_approved": False,
        "physical_follower_torque_enabled_at_close": False,
        "physical_task_attempts": 0,
        "claim_boundary": contract["claim_boundary"],
        "authority": contract["authority"],
    }
    output.parent.mkdir(parents=True)
    output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    arguments = parser.parse_args()
    result = evaluate(arguments.contract.resolve())
    print(
        json.dumps(
            {
                "status": result["status"],
                "heldout_passed": result["heldout_passed"],
                "stage_results": result["stage_results"],
                "physical_model_mapping_approved": result[
                    "physical_model_mapping_approved"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

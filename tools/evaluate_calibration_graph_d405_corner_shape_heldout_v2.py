#!/usr/bin/env python3
"""Evaluate D405 tag-corner trajectory shape against measured-joint kinematics."""

from __future__ import annotations

import argparse
import bisect
import json
from pathlib import Path
from typing import Any

import cv2
import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from sim2claw.paths import REPO_ROOT
from tools.evaluate_calibration_graph_d405_rotation_heldout_v1 import (
    body_rotation,
    bound,
    joint_samples,
    require,
    sha256,
)
from tools.fit_current_session_pi_articulated_cad_bundle import (
    Model,
    detect_tags,
)


def trajectory_shape_metrics(
    observed_displacement: np.ndarray,
    simulated_rotation_degrees: np.ndarray,
) -> dict[str, float | int]:
    observed = np.asarray(observed_displacement, dtype=np.float64)
    simulated = np.asarray(simulated_rotation_degrees, dtype=np.float64)
    require(
        observed.ndim == simulated.ndim == 1
        and observed.shape == simulated.shape
        and len(observed) >= 3
        and np.all(np.isfinite(observed))
        and np.all(np.isfinite(simulated))
        and np.min(observed) >= 0.0
        and np.min(simulated) >= 0.0,
        "trajectory shapes are invalid",
    )
    observed_peak = float(np.max(observed))
    simulated_peak = float(np.max(simulated))
    require(
        observed_peak > 1e-12 and simulated_peak > 1e-12,
        "trajectory shape has no signal",
    )
    observed_normalized = observed / observed_peak
    simulated_normalized = simulated / simulated_peak
    residual = observed_normalized - simulated_normalized
    correlation = (
        float(np.corrcoef(observed_normalized, simulated_normalized)[0, 1])
        if np.std(observed_normalized) > 1e-12
        and np.std(simulated_normalized) > 1e-12
        else 0.0
    )
    return {
        "sample_count": int(len(observed)),
        "observed_corner_displacement_peak_px": observed_peak,
        "simulated_rotation_peak_degrees": simulated_peak,
        "normalized_shape_rmse": float(np.sqrt(np.mean(residual**2))),
        "normalized_shape_max_error": float(np.max(np.abs(residual))),
        "normalized_shape_correlation": correlation,
    }


def stage_shape(
    *,
    stage_path: Path,
    receipt: dict[str, Any],
    packet_stage: dict[str, Any],
    candidate_config: dict[str, Any],
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
        "D405 corner-shape capture binding changed",
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
    video = cv2.VideoCapture(str(video_path))
    observed_corners = []
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
            delta_ms <= float(method["maximum_frame_to_joint_delta_ms"])
            and int(method["fixed_scene_tag_id"]) in tags
        ):
            observed_corners.append(
                tags[int(method["fixed_scene_tag_id"])].copy()
            )
            matched_joints.append(joints[nearest].copy())
            alignment_ms.append(delta_ms)
        frame_count += 1
    video.release()
    require(
        frame_count == len(timestamps) == wrist["callback_frame_count"],
        "D405 corner-shape frame and callback counts changed",
    )
    corners = np.asarray(observed_corners, dtype=np.float64)
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
        len(corners) >= int(method["minimum_detected_frame_count"])
        and int(np.count_nonzero(reference))
        >= int(method["minimum_reference_frame_count"]),
        "D405 fixed-tag corner trajectory is not observable",
    )
    reference_corners = np.mean(corners[reference], axis=0)
    observed_displacement = np.sqrt(
        np.mean(
            np.sum((corners - reference_corners[None, :, :]) ** 2, axis=2),
            axis=1,
        )
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
    simulated_reference = body_rotation(model, data, "left_camera_mount")
    simulated_angles = np.degrees(
        Rotation.from_matrix(
            np.einsum("ij,njk->nik", simulated_reference.T, simulated)
        ).magnitude()
    )
    return {
        "metrics": trajectory_shape_metrics(
            observed_displacement, simulated_angles
        ),
        "detected_frame_count": int(len(corners)),
        "reference_frame_count": int(np.count_nonzero(reference)),
        "total_d405_frame_count": int(frame_count),
        "tag_detection_fraction": float(len(corners) / frame_count),
        "frame_to_joint_delta_ms": {
            "maximum": float(np.max(alignment_ms)),
            "median": float(np.median(alignment_ms)),
        },
        "measured_active_joint_excursion_degrees": float(
            np.max(np.abs(q_values[:, int(packet_stage["active_joint_index"])] - anchor[int(packet_stage["active_joint_index"])]))
        ),
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
        == "sim2claw.calibration_graph_d405_corner_shape_heldout.v2"
        and contract.get("status")
        == "frozen_after_execution_before_any_new_frame_open"
        and contract["authority"]
        == {
            "read_bound_physical_capture": True,
            "evaluate_downstream_trajectory_shape": True,
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
        "D405 corner-shape heldout contract widened",
    )
    packet_path = bound(contract["sources"]["packet"])
    review_path = bound(contract["sources"]["review"])
    manifest_path = bound(contract["sources"]["candidate_manifest"])
    bound(contract["implementation"])
    bound(contract["implementation_dependency"])
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    review = json.loads(review_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(
        review["packet_sha256"] == sha256(packet_path)
        and review["status"] == "admitted_for_one_execution_per_stage"
        and len(packet["stages"]) == 2,
        "D405 corner-shape packet/review binding changed",
    )
    stage_results = {}
    gates = contract["gates"]
    for stage_index, specification in sorted(
        contract["stages"].items(), key=lambda row: int(row[0])
    ):
        index = int(stage_index)
        receipt_path = bound(specification["execution_receipt"])
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        packet_stage = dict(packet["stages"][index - 1])
        packet_stage["active_joint_index"] = int(
            specification["joint_index"]
        )
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
        result = stage_shape(
            stage_path=receipt_path.parent,
            receipt=receipt,
            packet_stage=packet_stage,
            candidate_config=manifest["candidate_config"],
            method=contract["method"],
        )
        metrics = result["metrics"]
        joint_index = int(specification["joint_index"])
        checks = {
            "measured_joint_signal": (
                result["measured_active_joint_excursion_degrees"]
                >= float(gates["minimum_measured_joint_excursion_degrees"])
            ),
            "observed_image_signal": (
                metrics["observed_corner_displacement_peak_px"]
                >= float(gates["minimum_observed_corner_displacement_peak_px"])
            ),
            "simulated_rotation_signal": (
                metrics["simulated_rotation_peak_degrees"]
                >= float(gates["minimum_simulated_rotation_peak_degrees"])
            ),
            "normalized_shape_rmse": (
                metrics["normalized_shape_rmse"]
                <= float(gates["normalized_shape_rmse_max"])
            ),
            "normalized_shape_max": (
                metrics["normalized_shape_max_error"]
                <= float(gates["normalized_shape_max_error_max"])
            ),
            "normalized_shape_correlation": (
                metrics["normalized_shape_correlation"]
                >= float(gates["minimum_normalized_shape_correlation"])
            ),
            "return_residual": (
                abs(float(result["final_residual_degrees"][joint_index]))
                <= float(gates["maximum_active_joint_return_residual_degrees"])
            ),
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
    require(not output.exists(), "immutable D405 corner-shape heldout exists")
    receipt = {
        "schema_version": "sim2claw.calibration_graph_d405_corner_shape_heldout_receipt.v2",
        "status": (
            "downstream_corner_shape_heldout_passed_no_automatic_promotion"
            if passed
            else "downstream_corner_shape_heldout_rejected_no_automatic_promotion"
        ),
        "proof_class": "prospective_exact_action_physical_d405_fixed_tag_corner_shape_downstream_mapping_heldout",
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

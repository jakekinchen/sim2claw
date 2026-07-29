#!/usr/bin/env python3
"""Evaluate one action-frozen composite calibration heldout."""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def trajectory_metrics(
    observed_centers: np.ndarray,
    simulated_centers: np.ndarray,
    reference_mask: np.ndarray,
) -> dict[str, float | int]:
    observed = np.asarray(observed_centers, dtype=np.float64)
    simulated = np.asarray(simulated_centers, dtype=np.float64)
    reference = np.asarray(reference_mask, dtype=bool)
    require(
        observed.ndim == 2
        and observed.shape[1] == 2
        and simulated.shape == observed.shape
        and reference.shape == (len(observed),)
        and int(np.count_nonzero(reference)) >= 3
        and np.all(np.isfinite(observed))
        and np.all(np.isfinite(simulated)),
        "composite trajectory arrays or reference mask are invalid",
    )
    observed_delta = observed - np.mean(observed[reference], axis=0)
    simulated_delta = simulated - np.mean(simulated[reference], axis=0)
    residual = observed_delta - simulated_delta
    residual_norm = np.linalg.norm(residual, axis=1)
    observed_signal = float(
        np.sqrt(np.mean(np.sum(observed_delta**2, axis=1)))
    )
    simulated_signal = float(
        np.sqrt(np.mean(np.sum(simulated_delta**2, axis=1)))
    )
    flat_observed = observed_delta.reshape(-1)
    flat_simulated = simulated_delta.reshape(-1)
    correlation = (
        float(np.corrcoef(flat_observed, flat_simulated)[0, 1])
        if np.std(flat_observed) > 1e-12
        and np.std(flat_simulated) > 1e-12
        else 0.0
    )
    return {
        "sample_count": int(len(observed)),
        "reference_sample_count": int(np.count_nonzero(reference)),
        "observed_displacement_rms_px": observed_signal,
        "simulated_displacement_rms_px": simulated_signal,
        "observed_over_simulated_signal_ratio": (
            float(observed_signal / simulated_signal)
            if simulated_signal > 1e-12
            else float("inf")
        ),
        "displacement_residual_rmse_px": float(
            np.sqrt(np.mean(residual_norm**2))
        ),
        "displacement_residual_max_px": float(np.max(residual_norm)),
        "flattened_displacement_correlation": correlation,
    }


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
        len(rows) == 1041
        and host.shape == (len(rows),)
        and joints.shape == (len(rows), 6)
        and np.all(np.diff(host) > 0),
        "composite heldout joint samples changed",
    )
    return host, joints


def observed_tracks(
    stage_path: Path,
    receipt: dict[str, Any],
    *,
    frame_stride: int,
    maximum_alignment_ns: int,
) -> dict[int, dict[str, np.ndarray]]:
    video_path = (
        stage_path
        / "final_hold_camera/pi_motion/pi_imx708.browser.mp4"
    )
    pts_path = stage_path / "final_hold_camera/pi_motion/pi_imx708.pts"
    joint_path = stage_path / "joint_samples.jsonl"
    require(
        video_path.is_file() and pts_path.is_file() and joint_path.is_file(),
        "composite heldout capture is incomplete",
    )
    pts_seconds = np.loadtxt(pts_path, dtype=np.float64) / 1000.0
    host, joints = load_joint_samples(joint_path)
    start = float(receipt["camera_finished"]["pi"]["host_monotonic_start"])
    tracks: dict[int, dict[str, list[Any]]] = {}
    capture = cv2.VideoCapture(str(video_path))
    frame_index = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if frame_index % frame_stride == 0 and frame_index < len(pts_seconds):
            nominal_ns = int((start + pts_seconds[frame_index]) * 1e9)
            insertion = bisect.bisect_left(host, nominal_ns)
            if 0 < insertion < len(host):
                nearest = (
                    insertion
                    if abs(int(host[insertion]) - nominal_ns)
                    < abs(int(host[insertion - 1]) - nominal_ns)
                    else insertion - 1
                )
                if abs(int(host[nearest]) - nominal_ns) <= maximum_alignment_ns:
                    for tag_id, corners in detect_tags(frame).items():
                        row = tracks.setdefault(
                            tag_id, {"joints": [], "centers": []}
                        )
                        row["joints"].append(joints[nearest].copy())
                        row["centers"].append(np.mean(corners, axis=0))
        frame_index += 1
    capture.release()
    require(
        frame_index == len(pts_seconds),
        "Pi frame and PTS counts changed",
    )
    return {
        tag_id: {
            "joints": np.asarray(row["joints"], dtype=np.float64),
            "centers": np.asarray(row["centers"], dtype=np.float64),
        }
        for tag_id, row in tracks.items()
    }


def simulated_centers(
    *,
    robot: Model,
    q_values: np.ndarray,
    tag_id: int,
    body_map: dict[int, str],
    mounts: dict[int, np.ndarray],
    camera: np.ndarray,
    offsets: np.ndarray,
    local_points: np.ndarray,
    focal: float,
    principal: np.ndarray,
) -> np.ndarray:
    centers = []
    for joints in q_values:
        robot.set_pose(joints, offsets, np.ones(5, dtype=np.float64))
        points = tag_world(
            robot, body_map[tag_id], mounts[tag_id], local_points
        )
        pixels, valid = project(points, camera, focal, principal)
        require(np.all(valid), f"tag {tag_id} projected behind Pi")
        centers.append(np.mean(pixels, axis=0))
    return np.asarray(centers, dtype=np.float64)


def bound_path(binding: dict[str, Any]) -> Path:
    path = (ROOT / str(binding["path"])).resolve()
    require(
        path.is_file() and sha256(path) == binding["sha256"],
        f"bound source changed: {path}",
    )
    return path


def evaluate(contract_path: Path) -> dict[str, Any]:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    require(
        contract.get("schema_version")
        == "sim2claw.calibration_graph_composite_heldout.v1"
        and contract.get("status")
        == "frozen_after_execution_before_heldout_frame_open"
        and contract["authority"]
        == {
            "read_bound_physical_capture": True,
            "evaluate_composite_factor": True,
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
        "composite heldout contract widened",
    )
    sources = contract["sources"]
    packet_path = bound_path(sources["packet"])
    review_path = bound_path(sources["review"])
    receipt_path = bound_path(sources["execution_receipt"])
    candidate_path = bound_path(sources["static_candidate"])
    cad_contract_path = bound_path(sources["static_contract"])
    bound_path(contract["implementation"])
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    review = json.loads(review_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    require(
        packet["plan_sha256"] == contract["expected"]["plan_sha256"]
        and packet["stages"][0]["action_sha256"]
        == contract["expected"]["action_sha256"]
        and review["packet_sha256"] == sha256(packet_path)
        and review["status"] == "admitted_for_one_execution_per_stage"
        and receipt["packet_sha256"] == sha256(packet_path)
        and receipt["review_sha256"] == sha256(review_path)
        and receipt["action_sha256"] == contract["expected"]["action_sha256"]
        and receipt["status"] == "completed_wrist_view_reposition_stage"
        and receipt["error"] is None
        and receipt["physical_follower_torque_enabled"] is False
        and receipt["completed_motion_samples"] == 961
        and receipt["completed_capture_hold_samples"] == 80
        and receipt["camera_finished"]["pi"]["action_interval_enclosed"],
        "composite heldout execution is not an exact torque-off completion",
    )
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    cad_contract, _ = load_contract(cad_contract_path)
    manifest_path = bound_path(cad_contract["sources"]["candidate_manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
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
        float(cad_contract["frozen_model"]["tag_black_edge_m"])
    )
    tracks = observed_tracks(
        receipt_path.parent,
        receipt,
        frame_stride=int(contract["method"]["frame_stride"]),
        maximum_alignment_ns=int(
            contract["method"]["maximum_frame_to_joint_delta_ms"]
            * 1_000_000
        ),
    )
    anchor = np.asarray(
        packet["command_anchor_degrees"], dtype=np.float64
    )
    active = np.asarray(contract["method"]["active_joint_indices"], dtype=int)
    gates = contract["gates"]
    results: dict[str, Any] = {}
    for tag_id in contract["required_tag_ids"]:
        tag_id = int(tag_id)
        require(
            tag_id in tracks
            and tag_id in mounts
            and tag_id in body_map,
            f"required composite tag {tag_id} is unavailable",
        )
        q_values = tracks[tag_id]["joints"]
        centers = tracks[tag_id]["centers"]
        reference = np.all(
            np.abs(q_values[:, active] - anchor[None, active])
            <= float(contract["method"]["anchor_reference_radius_degrees"]),
            axis=1,
        )
        simulated = simulated_centers(
            robot=robot,
            q_values=q_values,
            tag_id=tag_id,
            body_map=body_map,
            mounts=mounts,
            camera=camera,
            offsets=offsets,
            local_points=local_points,
            focal=float(candidate["model"]["focal_px"]),
            principal=np.asarray(
                candidate["model"]["principal_point_px"],
                dtype=np.float64,
            ),
        )
        metrics = trajectory_metrics(centers, simulated, reference)
        checks = {
            "sample_count": metrics["sample_count"]
            >= int(gates["minimum_sample_count"]),
            "reference_sample_count": metrics["reference_sample_count"]
            >= int(gates["minimum_reference_sample_count"]),
            "simulated_signal": metrics["simulated_displacement_rms_px"]
            >= float(gates["minimum_simulated_displacement_rms_px"]),
            "signal_ratio": float(gates["signal_ratio_range"][0])
            <= metrics["observed_over_simulated_signal_ratio"]
            <= float(gates["signal_ratio_range"][1]),
            "residual_rmse": metrics["displacement_residual_rmse_px"]
            <= float(gates["displacement_residual_rmse_max_px"]),
            "residual_max": metrics["displacement_residual_max_px"]
            <= float(gates["displacement_residual_max_px"]),
            "correlation": metrics["flattened_displacement_correlation"]
            >= float(gates["minimum_displacement_correlation"]),
        }
        results[str(tag_id)] = {
            "body": body_map[tag_id],
            "metrics": metrics,
            "checks": checks,
            "passed": all(checks.values()),
        }
    passed = all(row["passed"] for row in results.values())
    output = (ROOT / contract["output_path"]).resolve()
    require(not output.exists(), "immutable composite heldout output exists")
    result = {
        "schema_version": "sim2claw.calibration_graph_composite_heldout_receipt.v1",
        "status": (
            "composite_heldout_passed_no_automatic_promotion"
            if passed
            else "composite_heldout_rejected_no_automatic_promotion"
        ),
        "proof_class": "prospective_action_frozen_physical_no_contact_composite_mapping_heldout",
        "contract_path": str(contract_path.relative_to(ROOT)),
        "contract_sha256": sha256(contract_path),
        "sources": {
            name: {"path": str(path.relative_to(ROOT)), "sha256": sha256(path)}
            for name, path in {
                "packet": packet_path,
                "review": review_path,
                "execution_receipt": receipt_path,
                "static_candidate": candidate_path,
                "static_contract": cad_contract_path,
                "candidate_manifest": manifest_path,
            }.items()
        },
        "method": contract["method"],
        "gates": gates,
        "tag_results": results,
        "heldout_passed": passed,
        "physical_model_mapping_approved": False,
        "physical_motion_already_completed": True,
        "physical_follower_torque_enabled_at_close": False,
        "physical_task_attempts": 0,
        "claim_boundary": contract["claim_boundary"],
        "authority": contract["authority"],
    }
    output.parent.mkdir(parents=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


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
                "tag_results": result["tag_results"],
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

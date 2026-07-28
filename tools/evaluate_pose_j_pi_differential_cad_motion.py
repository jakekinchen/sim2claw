#!/usr/bin/env python3
"""Compare localized physical Pi motion with frozen full-CAD motion."""

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
    IMAGE_HEIGHT,
    IMAGE_WIDTH,
    MAX_HULL_EDGES_PER_GEOM,
    Model,
    detect_tags,
    load_contract,
    project,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = (
    ROOT
    / "configs/evaluations/pose_j_pi_differential_cad_motion_v1.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "runs/geometric-hover/"
    "20260727-pose-j-single-joint-image-jacobian-sweep-tricam-v1/"
    "evaluation/pi-differential-cad-motion-v1.json"
)
SWEEP = (
    ROOT
    / "runs/geometric-hover/"
    "20260727-pose-j-single-joint-image-jacobian-sweep-tricam-v1"
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


def verify_source(source: dict[str, Any], label: str) -> Path:
    path = ROOT / source["path"]
    require(path.is_file(), f"missing {label}: {path}")
    require(sha256(path) == source["sha256"], f"{label} hash changed")
    return path


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


def freeze_hulls(
    robot: Model,
    joint_degrees: np.ndarray,
    offsets: np.ndarray,
    scales: np.ndarray,
    camera: np.ndarray,
    focal: float,
    principal: np.ndarray,
) -> list[dict[str, Any]]:
    robot.set_pose(joint_degrees, offsets, scales)
    frozen = []
    for geom in robot.visual_geoms:
        world = robot.geom_world_vertices(geom)
        pixels, valid = project(world, camera, focal, principal)
        usable = (
            valid
            & np.isfinite(pixels).all(axis=1)
            & (pixels[:, 0] > -150)
            & (pixels[:, 0] < IMAGE_WIDTH + 150)
            & (pixels[:, 1] > -150)
            & (pixels[:, 1] < IMAGE_HEIGHT + 150)
        )
        indices = np.flatnonzero(usable)
        if len(indices) < 3:
            continue
        hull = cv2.convexHull(
            pixels[indices].astype(np.float32), returnPoints=False
        ).reshape(-1)
        if len(hull) < 3:
            continue
        hull_indices = indices[hull]
        pairs = np.column_stack(
            (hull_indices, np.roll(hull_indices, -1))
        ).astype(np.int64)
        if len(pairs) > MAX_HULL_EDGES_PER_GEOM:
            selected = np.linspace(
                0,
                len(pairs),
                MAX_HULL_EDGES_PER_GEOM,
                endpoint=False,
                dtype=np.int64,
            )
            pairs = pairs[selected]
        frozen.append(
            {
                "geom_id": int(geom["geom_id"]),
                "body": geom["body"],
                "local": geom["local"],
                "pairs": pairs,
            }
        )
    require(frozen, "Pose-J produced no frozen CAD hulls")
    return frozen


def projected_hulls_and_samples(
    robot: Model,
    frozen: list[dict[str, Any]],
    bodies: set[str],
    joint_degrees: np.ndarray,
    offsets: np.ndarray,
    scales: np.ndarray,
    camera: np.ndarray,
    focal: float,
    principal: np.ndarray,
    band_radius: int,
) -> tuple[np.ndarray, np.ndarray, dict[str, int]]:
    robot.set_pose(joint_degrees, offsets, scales)
    mask = np.zeros((IMAGE_HEIGHT, IMAGE_WIDTH), dtype=np.uint8)
    samples = []
    counts: dict[str, int] = {}
    alphas = np.linspace(0.0, 1.0, 4, endpoint=False)
    for geom in frozen:
        if geom["body"] not in bodies:
            continue
        geom_id = int(geom["geom_id"])
        world = (
            geom["local"]
            @ robot.data.geom_xmat[geom_id].reshape(3, 3).T
            + robot.data.geom_xpos[geom_id]
        )
        edge_world = []
        for first_index, second_index in geom["pairs"]:
            first = world[int(first_index)]
            second = world[int(second_index)]
            for alpha in alphas:
                edge_world.append((1.0 - alpha) * first + alpha * second)
        if not edge_world:
            continue
        pixels, valid = project(
            np.asarray(edge_world), camera, focal, principal
        )
        pixels = pixels[valid]
        if not len(pixels):
            continue
        samples.append(pixels)
        counts[geom["body"]] = counts.get(geom["body"], 0) + len(pixels)
        endpoint_world = world[geom["pairs"].reshape(-1)]
        endpoint_pixels, endpoint_valid = project(
            endpoint_world, camera, focal, principal
        )
        endpoint_pixels = endpoint_pixels.reshape(-1, 2, 2)
        endpoint_valid = endpoint_valid.reshape(-1, 2)
        for pair_pixels, pair_valid in zip(
            endpoint_pixels, endpoint_valid, strict=True
        ):
            if not np.all(pair_valid):
                continue
            rounded = np.rint(pair_pixels).astype(np.int32)
            cv2.line(
                mask,
                tuple(rounded[0]),
                tuple(rounded[1]),
                255,
                thickness=2 * band_radius + 1,
                lineType=cv2.LINE_AA,
            )
    require(samples, "selected moving bodies produced no CAD samples")
    return mask, np.concatenate(samples), counts


def tag_mask(tags: dict[int, np.ndarray], dilation: int) -> np.ndarray:
    mask = np.zeros((IMAGE_HEIGHT, IMAGE_WIDTH), dtype=np.uint8)
    for corners in tags.values():
        polygon = np.rint(corners).astype(np.int32)
        cv2.fillConvexPoly(mask, polygon, 255)
    if dilation > 0:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (2 * dilation + 1, 2 * dilation + 1)
        )
        mask = cv2.dilate(mask, kernel)
    return mask


def track_points(
    prior: np.ndarray,
    following: np.ndarray,
    mask: np.ndarray,
    maximum: int,
) -> tuple[np.ndarray, np.ndarray]:
    points = cv2.goodFeaturesToTrack(
        prior,
        maxCorners=maximum,
        qualityLevel=0.005,
        minDistance=4.0,
        mask=mask,
        blockSize=5,
        useHarrisDetector=False,
    )
    if points is None or len(points) < 4:
        return np.empty((0, 2)), np.empty((0, 2))
    next_points, status, errors = cv2.calcOpticalFlowPyrLK(
        prior,
        following,
        points,
        None,
        winSize=(21, 21),
        maxLevel=3,
        criteria=(
            cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
            30,
            0.01,
        ),
    )
    if next_points is None or status is None:
        return np.empty((0, 2)), np.empty((0, 2))
    accepted = (
        status.reshape(-1).astype(bool)
        & np.isfinite(next_points.reshape(-1, 2)).all(axis=1)
        & (errors.reshape(-1) < 30.0)
    )
    return points.reshape(-1, 2)[accepted], next_points.reshape(-1, 2)[
        accepted
    ]


def background_affine(
    prior: np.ndarray,
    following: np.ndarray,
    background_mask: np.ndarray,
) -> tuple[np.ndarray, int, int]:
    first, second = track_points(
        prior, following, background_mask, maximum=1000
    )
    if len(first) < 12:
        return np.asarray([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]), 0, 0
    cv2.setRNGSeed(1979)
    affine, inliers = cv2.estimateAffinePartial2D(
        first,
        second,
        method=cv2.RANSAC,
        ransacReprojThreshold=1.5,
        maxIters=1000,
    )
    if affine is None or inliers is None:
        return np.asarray([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]), len(first), 0
    return affine, len(first), int(np.sum(inliers))


def physical_pair_flow(
    prior: dict[str, Any],
    following: dict[str, Any],
    prior_band: np.ndarray,
    following_band: np.ndarray,
    tag_dilation: int,
    static_threshold: float,
) -> dict[str, Any] | None:
    tags = cv2.bitwise_or(
        tag_mask(prior["tags"], tag_dilation),
        tag_mask(following["tags"], tag_dilation),
    )
    moving_mask = cv2.bitwise_and(prior_band, cv2.bitwise_not(tags))
    excluded_arm = cv2.dilate(
        cv2.bitwise_or(prior_band, following_band),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (49, 49)),
    )
    background_mask = cv2.bitwise_and(
        cv2.bitwise_not(excluded_arm), cv2.bitwise_not(tags)
    )
    affine, background_count, background_inliers = background_affine(
        prior["gray"], following["gray"], background_mask
    )
    first, second = track_points(
        prior["gray"], following["gray"], moving_mask, maximum=600
    )
    if len(first) < 6:
        return None
    rounded = np.rint(second).astype(np.int32)
    inside = (
        (rounded[:, 0] >= 0)
        & (rounded[:, 0] < IMAGE_WIDTH)
        & (rounded[:, 1] >= 0)
        & (rounded[:, 1] < IMAGE_HEIGHT)
    )
    inside[inside] &= (
        following_band[
            rounded[inside, 1], rounded[inside, 0]
        ]
        > 0
    )
    first = first[inside]
    second = second[inside]
    if len(first) < 6:
        return None
    homogeneous = np.column_stack(
        (first, np.ones(len(first), dtype=np.float64))
    )
    background_prediction = (affine @ homogeneous.T).T
    residual = second - background_prediction
    magnitudes = np.linalg.norm(residual, axis=1)
    static_fraction = float(np.mean(magnitudes <= static_threshold))
    accepted = magnitudes > static_threshold
    if int(np.sum(accepted)) < 4:
        return None
    return {
        "flow_xy_px": np.median(residual[accepted], axis=0),
        "feature_count_before_static_rejection": len(first),
        "accepted_feature_count": int(np.sum(accepted)),
        "static_consensus_fraction": static_fraction,
        "background_feature_count": background_count,
        "background_ransac_inlier_count": background_inliers,
    }


def regression(
    joint_delta: np.ndarray, flows: np.ndarray
) -> dict[str, Any]:
    denominator = float(np.sum(joint_delta**2))
    require(denominator > 0.0, "zero joint-delta regression denominator")
    slope = np.sum(joint_delta[:, None] * flows, axis=0) / denominator
    predicted = joint_delta[:, None] * slope
    total = float(np.sum(flows**2))
    return {
        "slope_xy_pixels_per_degree": slope.tolist(),
        "slope_magnitude_pixels_per_degree": float(np.linalg.norm(slope)),
        "combined_zero_intercept_r_squared": (
            float(1.0 - np.sum((flows - predicted) ** 2) / total)
            if total > 0.0
            else 0.0
        ),
    }


def angle_degrees(first: np.ndarray, second: np.ndarray) -> float:
    denominator = float(np.linalg.norm(first) * np.linalg.norm(second))
    if denominator <= 1e-12:
        return math.inf
    cosine = float(np.clip(np.dot(first, second) / denominator, -1.0, 1.0))
    return float(np.degrees(np.arccos(cosine)))


def load_pi_frames(
    stage_path: Path,
    receipt: dict[str, Any],
    stride: int,
    maximum_delta_ms: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    video_path = (
        stage_path / "final_hold_camera/pi_motion/pi_imx708.browser.mp4"
    )
    pts_path = stage_path / "final_hold_camera/pi_motion/pi_imx708.pts"
    samples_path = stage_path / "joint_samples.jsonl"
    require(
        video_path.is_file() and pts_path.is_file() and samples_path.is_file(),
        f"incomplete Pi stage: {stage_path}",
    )
    pts_seconds = np.loadtxt(pts_path, dtype=np.float64) / 1000.0
    host, joints = load_joint_samples(samples_path)
    start = float(receipt["camera_finished"]["pi"]["host_monotonic_start"])
    capture = cv2.VideoCapture(str(video_path))
    rows = []
    frame_index = 0
    alignment_deltas = []
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if frame_index % stride == 0 and frame_index < len(pts_seconds):
            nominal_ns = int((start + pts_seconds[frame_index]) * 1e9)
            insertion = bisect.bisect_left(host, nominal_ns)
            insertion = min(max(insertion, 1), len(host) - 1)
            nearest = (
                insertion
                if abs(int(host[insertion]) - nominal_ns)
                < abs(int(host[insertion - 1]) - nominal_ns)
                else insertion - 1
            )
            delta_ms = abs(int(host[nearest]) - nominal_ns) / 1e6
            if delta_ms <= maximum_delta_ms:
                rows.append(
                    {
                        "frame_index": frame_index,
                        "gray": cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY),
                        "tags": detect_tags(frame),
                        "joints": joints[nearest].copy(),
                    }
                )
                alignment_deltas.append(delta_ms)
        frame_index += 1
    capture.release()
    require(
        frame_index == len(pts_seconds),
        f"Pi frame/PTS count changed: {stage_path}",
    )
    require(len(rows) >= 200, f"too few aligned Pi frames: {stage_path}")
    return rows, {
        "video_path": str(video_path.relative_to(ROOT)),
        "video_sha256": sha256(video_path),
        "pts_path": str(pts_path.relative_to(ROOT)),
        "pts_sha256": sha256(pts_path),
        "joint_samples_path": str(samples_path.relative_to(ROOT)),
        "joint_samples_sha256": sha256(samples_path),
        "decoded_frame_count": frame_index,
        "aligned_sampled_frame_count": len(rows),
        "frame_to_joint_delta_ms": {
            "maximum": float(np.max(alignment_deltas)),
            "median": float(np.median(alignment_deltas)),
        },
    }


def evaluate_stage(
    *,
    robot: Model,
    frozen: list[dict[str, Any]],
    bodies: set[str],
    frames: list[dict[str, Any]],
    joint_index: int,
    offsets: np.ndarray,
    scales: np.ndarray,
    camera: np.ndarray,
    focal: float,
    principal: np.ndarray,
    method: dict[str, Any],
    gates: dict[str, Any],
) -> dict[str, Any]:
    lag = int(method["pair_lag_sampled_frames"])
    minimum_delta = float(method["minimum_pair_joint_delta_degrees"])
    band_radius = int(method["projected_cad_band_radius_px"])
    tag_dilation = int(method["tag_polygon_mask_dilation_px"])
    static_threshold = float(method["static_consensus_residual_max_px"])
    cache = []
    body_counts: dict[str, int] = {}
    for row in frames:
        band, samples, counts = projected_hulls_and_samples(
            robot,
            frozen,
            bodies,
            row["joints"],
            offsets,
            scales,
            camera,
            focal,
            principal,
            band_radius,
        )
        cache.append((band, samples))
        for body, count in counts.items():
            body_counts[body] = body_counts.get(body, 0) + count
    rows = []
    for first_index in range(len(frames) - lag):
        second_index = first_index + lag
        first = frames[first_index]
        second = frames[second_index]
        joint_delta = float(
            second["joints"][joint_index] - first["joints"][joint_index]
        )
        if abs(joint_delta) < minimum_delta:
            continue
        physical = physical_pair_flow(
            first,
            second,
            cache[first_index][0],
            cache[second_index][0],
            tag_dilation,
            static_threshold,
        )
        if physical is None:
            continue
        simulated_flow = np.median(
            cache[second_index][1] - cache[first_index][1], axis=0
        )
        rows.append(
            {
                "joint_delta_degrees": joint_delta,
                "physical_flow_xy_px": physical["flow_xy_px"],
                "simulated_flow_xy_px": simulated_flow,
                **{
                    key: value
                    for key, value in physical.items()
                    if key != "flow_xy_px"
                },
            }
        )
    require(rows, "no accepted localized CAD motion pairs")
    joint_delta = np.asarray(
        [row["joint_delta_degrees"] for row in rows], dtype=np.float64
    )
    physical_flows = np.asarray(
        [row["physical_flow_xy_px"] for row in rows], dtype=np.float64
    )
    simulated_flows = np.asarray(
        [row["simulated_flow_xy_px"] for row in rows], dtype=np.float64
    )
    observed = regression(joint_delta, physical_flows)
    simulated = regression(joint_delta, simulated_flows)
    observed_slope = np.asarray(observed["slope_xy_pixels_per_degree"])
    simulated_slope = np.asarray(simulated["slope_xy_pixels_per_degree"])
    simulated_magnitude = float(
        simulated["slope_magnitude_pixels_per_degree"]
    )
    ratio = (
        float(observed["slope_magnitude_pixels_per_degree"])
        / simulated_magnitude
        if simulated_magnitude > 1e-12
        else None
    )
    direction = angle_degrees(observed_slope, simulated_slope)
    static_fraction = float(
        np.average(
            [row["static_consensus_fraction"] for row in rows],
            weights=[
                row["feature_count_before_static_rejection"] for row in rows
            ],
        )
    )
    passed = bool(
        len(rows)
        >= int(gates["minimum_accepted_motion_pairs_per_joint"])
        and observed["combined_zero_intercept_r_squared"]
        >= float(gates["observed_combined_r_squared_minimum"])
        and simulated["combined_zero_intercept_r_squared"]
        >= float(gates["simulated_combined_r_squared_minimum"])
        and ratio is not None
        and float(gates["observed_over_simulated_magnitude_ratio"][0])
        <= ratio
        <= float(gates["observed_over_simulated_magnitude_ratio"][1])
        and direction
        <= float(gates["direction_difference_maximum_degrees"])
        and static_fraction
        <= float(gates["maximum_static_consensus_feature_fraction"])
    )
    return {
        "accepted_motion_pair_count": len(rows),
        "joint_delta_degrees": {
            "minimum": float(np.min(joint_delta)),
            "maximum": float(np.max(joint_delta)),
        },
        "observed": observed,
        "simulated": simulated,
        "magnitude_ratio_observed_over_simulated": ratio,
        "direction_difference_degrees": direction,
        "static_consensus_feature_fraction_before_rejection": static_fraction,
        "median_accepted_feature_count_per_pair": float(
            np.median([row["accepted_feature_count"] for row in rows])
        ),
        "median_background_ransac_inlier_count_per_pair": float(
            np.median(
                [row["background_ransac_inlier_count"] for row in rows]
            )
        ),
        "projected_sample_counts_by_body": body_counts,
        "local_differential_cad_gate_passed": passed,
    }


def evaluate(contract_path: Path, output: Path) -> dict[str, Any]:
    require(not output.exists(), f"refusing to overwrite {output}")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    require(
        contract.get("schema_version")
        == "sim2claw.pose_j_pi_differential_cad_motion_contract.v1",
        "wrong differential CAD contract schema",
    )
    sources = contract["sources"]
    for name in (
        "sweep_packet",
        "independent_review",
        "pi_tag_center_diagnostic",
        "d405_background_motion_witness",
        "projection_contract",
        "projection_candidate",
    ):
        verify_source(sources[name], name)
    for stage, source in sources["stage_receipts"].items():
        verify_source(source, f"stage {stage} receipt")
    projection_contract_path = ROOT / sources["projection_contract"]["path"]
    projection_candidate_path = ROOT / sources["projection_candidate"]["path"]
    projection_contract, pose_rows = load_contract(
        projection_contract_path
    )
    candidate = json.loads(
        projection_candidate_path.read_text(encoding="utf-8")
    )
    manifest_path = (
        ROOT / projection_contract["sources"]["candidate_manifest"]["path"]
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    robot = Model(manifest["candidate_config"])
    parameters = candidate["parameters"]
    camera = np.asarray(
        parameters["camera_world_rotation_vector_radians"]
        + parameters["camera_world_translation_m"],
        dtype=np.float64,
    )
    offsets = np.asarray(
        parameters["joint_zero_offsets_degrees"], dtype=np.float64
    )
    scales = np.asarray(
        parameters["joint_degree_scales"], dtype=np.float64
    )
    focal = float(candidate["model"]["focal_px"])
    principal = np.asarray(
        candidate["model"]["principal_point_px"], dtype=np.float64
    )
    pose_j = next(row for row in pose_rows if row["name"] == "pose_j")
    frozen = freeze_hulls(
        robot,
        pose_j["joint_degrees"],
        offsets,
        scales,
        camera,
        focal,
        principal,
    )
    d405 = json.loads(
        (ROOT / sources["d405_background_motion_witness"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    stage_results = {}
    stage_sources = {}
    for stage_number, joint_index, joint_name in STAGES:
        stage_path = SWEEP / f"stage-{stage_number}"
        receipt_path = stage_path / "execution_receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        require(
            receipt["status"] == "completed_wrist_view_reposition_stage"
            and receipt["physical_follower_torque_enabled"] is False
            and receipt["error"] is None
            and receipt["camera_finished"]["pi"]["action_interval_enclosed"],
            f"stage {stage_number} is not an admitted Pi completion",
        )
        frames, frame_source = load_pi_frames(
            stage_path,
            receipt,
            int(contract["physical_image_method"]["frame_stride"]),
            float(
                contract["physical_image_method"][
                    "maximum_frame_to_joint_delta_ms"
                ]
            ),
        )
        result = evaluate_stage(
            robot=robot,
            frozen=frozen,
            bodies=set(
                contract["frozen_model"]["moving_bodies_by_joint"][
                    joint_name
                ]
            ),
            frames=frames,
            joint_index=joint_index,
            offsets=offsets,
            scales=scales,
            camera=camera,
            focal=focal,
            principal=principal,
            method=contract["physical_image_method"],
            gates=contract["gates"],
        )
        result.update(
            {
                "joint_index": joint_index,
                "joint_name": joint_name,
                "d405_nonzero_signal_witness_passed": bool(
                    d405["stage_results"][str(stage_number)][
                        "physical_background_motion_gate_passed"
                    ]
                ),
            }
        )
        if not result["d405_nonzero_signal_witness_passed"]:
            result["local_differential_cad_gate_passed"] = False
        stage_results[str(stage_number)] = result
        stage_sources[str(stage_number)] = {
            "receipt_path": str(receipt_path.relative_to(ROOT)),
            "receipt_sha256": sha256(receipt_path),
            **frame_source,
        }
    passed_joints = [
        row["joint_name"]
        for row in stage_results.values()
        if row["local_differential_cad_gate_passed"]
    ]
    aggregate_passed = bool(
        len(passed_joints)
        >= int(contract["gates"]["minimum_passing_joint_count"])
        and (
            not contract["gates"]["wrist_flex_must_pass"]
            or "wrist_flex" in passed_joints
        )
    )
    receipt = {
        "schema_version": "sim2claw.pose_j_pi_differential_cad_motion.v1",
        "status": (
            "diagnostic_gates_passed_no_parameter_promotion"
            if aggregate_passed
            else "diagnostic_gates_failed"
        ),
        "proof_class": contract["proof_class"],
        "contract": {
            "path": str(contract_path.relative_to(ROOT)),
            "sha256": sha256(contract_path),
        },
        "sources": {
            **{
                name: source
                for name, source in sources.items()
                if name != "stage_receipts"
            },
            "stages": stage_sources,
        },
        "method": contract["physical_image_method"],
        "gates": contract["gates"],
        "stage_results": stage_results,
        "summary": {
            "passing_joints": passed_joints,
            "failed_joints": [
                row["joint_name"]
                for row in stage_results.values()
                if not row["local_differential_cad_gate_passed"]
            ],
            "aggregate_diagnostic_gate_passed": aggregate_passed,
            "parameters_fitted": 0,
        },
        "limitations": {
            "projection_candidate_failed_retrospective_static_heldout": True,
            "camera_exposure_synchronized": False,
            "occlusion_reasoning_is_approximate": True,
            "d405_is_nonzero_motion_witness_only": True,
            "simulator_parameter_promotion": False,
            "pawn_contact": False,
            "task_or_policy_evidence": False,
        },
        "authority": contract["authority"],
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
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    evaluate(arguments.contract.resolve(), arguments.output.resolve())


if __name__ == "__main__":
    main()

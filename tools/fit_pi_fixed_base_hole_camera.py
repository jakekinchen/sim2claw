#!/usr/bin/env python3
"""Fit one diagnostic Pi camera from tags and two CAD-native base centers."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import mujoco
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from render_pi_cad_overlay import (
    MANIFEST,
    detect_tags,
    project,
    tag_world_corners,
    transform,
)
from sim2claw.physical_canary import _physical_to_model_position
from sim2claw.recorded_replay import _compile_model


ROOT = Path(__file__).resolve().parents[1]
HELDOUT = (
    ROOT
    / "runs/pi-link-tag-calibration/"
    "20260726-current-three-link-fresh-validation-v1/"
    "heldout-evaluation.json"
)
FEATURES = (
    {
        "feature_id": "base_side_fastener_aperture",
        "mesh_name": "left_base_so101_v2",
        "axis": 2,
        "seed_center_perpendicular_m": [0.007295, -0.036713],
        "seed_radius_m": 0.000762,
        "axis_range_m": [0.0138, 0.0158],
        "hough_roi_xyxy": [550, 460, 610, 515],
        "hough_param2": 9,
        "hough_radius_range_px": [2, 10],
    },
    {
        "feature_id": "servo_output_cylindrical_center",
        "mesh_name": "left_sts3215_03a_v1",
        "axis": 1,
        "seed_center_perpendicular_m": [0.0, 0.011903],
        "seed_radius_m": 0.002678,
        "axis_range_m": [0.0182, 0.0193],
        "hough_roi_xyxy": [688, 410, 712, 442],
        "hough_param2": 8,
        "hough_radius_range_px": [2, 7],
    },
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def frame_sources(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    names = ("pose_h_current", "pose_i_current", "pose_f_current")
    sources = {}
    for item in candidate["training"]:
        if item["name"] in names and item["name"] not in sources:
            sources[item["name"]] = item
    heldout = json.loads(HELDOUT.read_text(encoding="utf-8"))
    sources["pose_n_fresh_heldout"] = heldout["heldout"][0]
    ordered = (*names, "pose_n_fresh_heldout")
    if set(sources) != set(ordered):
        raise RuntimeError("candidate does not bind H, I, F, and fresh N")
    return [sources[name] for name in ordered]


def mesh_arrays(
    model: mujoco.MjModel, mesh_name: str
) -> tuple[np.ndarray, np.ndarray, int]:
    mesh_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_MESH, mesh_name
    )
    vertex_start = int(model.mesh_vertadr[mesh_id])
    face_start = int(model.mesh_faceadr[mesh_id])
    vertices = np.asarray(
        model.mesh_vert[
            vertex_start : vertex_start + int(model.mesh_vertnum[mesh_id])
        ],
        dtype=np.float64,
    )
    faces = np.asarray(
        model.mesh_face[
            face_start : face_start + int(model.mesh_facenum[mesh_id])
        ],
        dtype=np.int32,
    )
    return vertices, faces, mesh_id


def topology_center(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    specification: dict[str, Any],
) -> tuple[np.ndarray, dict[str, Any]]:
    vertices, faces, mesh_id = mesh_arrays(
        model, specification["mesh_name"]
    )
    triangles = vertices[faces]
    cross = np.cross(
        triangles[:, 1] - triangles[:, 0],
        triangles[:, 2] - triangles[:, 0],
    )
    normals = cross / np.maximum(
        np.linalg.norm(cross, axis=1)[:, None], 1e-12
    )
    centroids = np.mean(triangles, axis=1)
    axis = int(specification["axis"])
    perpendicular = [index for index in range(3) if index != axis]
    seed_center = np.asarray(
        specification["seed_center_perpendicular_m"], dtype=np.float64
    )
    seed_radius = float(specification["seed_radius_m"])
    radial = np.linalg.norm(
        centroids[:, perpendicular] - seed_center, axis=1
    )
    axis_min, axis_max = specification["axis_range_m"]
    selected = (
        (np.abs(radial - seed_radius) < seed_radius * 0.15)
        & (np.abs(normals[:, axis]) < 0.2)
        & (centroids[:, axis] >= axis_min)
        & (centroids[:, axis] <= axis_max)
    )
    points = centroids[selected][:, perpendicular]
    if len(points) < 32:
        raise RuntimeError("cylindrical topology support disappeared")
    matrix = np.column_stack(
        [2.0 * points[:, 0], 2.0 * points[:, 1], np.ones(len(points))]
    )
    target = np.sum(points**2, axis=1)
    solution, *_ = np.linalg.lstsq(matrix, target, rcond=None)
    center_2d = solution[:2]
    radii = np.linalg.norm(points - center_2d, axis=1)
    radial_unit = (points - center_2d) / radii[:, None]
    normal_2d = normals[selected][:, perpendicular]
    normal_2d /= np.maximum(
        np.linalg.norm(normal_2d, axis=1)[:, None], 1e-12
    )
    alignment = np.abs(np.sum(radial_unit * normal_2d, axis=1))
    if (
        np.std(radii) / np.mean(radii) >= 0.05
        or np.median(alignment) <= 0.98
    ):
        raise RuntimeError("selected topology is not a precise cylinder")
    center = np.empty(3, dtype=np.float64)
    center[perpendicular] = center_2d
    center[axis] = float(np.mean(centroids[selected, axis]))
    body_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, "left_base"
    )
    geom_id = next(
        geom_id
        for geom_id in range(model.ngeom)
        if int(model.geom_bodyid[geom_id]) == body_id
        and int(model.geom_dataid[geom_id]) == mesh_id
        and int(model.geom_group[geom_id]) == 2
    )
    world = (
        center @ data.geom_xmat[geom_id].reshape(3, 3).T
        + data.geom_xpos[geom_id]
    )
    return world, {
        "mesh_name": specification["mesh_name"],
        "mesh_id": mesh_id,
        "geom_id": geom_id,
        "axis_local_index": axis,
        "center_local_m": center.tolist(),
        "radius_m": float(np.mean(radii)),
        "support_face_count": int(np.count_nonzero(selected)),
        "radial_relative_std": float(np.std(radii) / np.mean(radii)),
        "median_normal_radial_alignment": float(np.median(alignment)),
        "compiled_mesh_sha256": hashlib.sha256(
            vertices.astype("<f4").tobytes()
            + faces.astype("<i4").tobytes()
        ).hexdigest(),
    }


def detect_feature(
    image: np.ndarray, specification: dict[str, Any]
) -> tuple[np.ndarray, float]:
    x0, y0, x1, y1 = specification["hough_roi_xyxy"]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)[y0:y1, x0:x1]
    blurred = cv2.GaussianBlur(gray, (5, 5), 1.0)
    radius_min, radius_max = specification["hough_radius_range_px"]
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.0,
        minDist=8,
        param1=50,
        param2=specification["hough_param2"],
        minRadius=radius_min,
        maxRadius=radius_max,
    )
    if circles is None or len(circles[0]) != 1:
        raise RuntimeError(
            f"{specification['feature_id']} is not uniquely detected"
        )
    x, y, radius = circles[0][0]
    return np.asarray([x + x0, y + y0], dtype=np.float64), float(radius)


def set_pose(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    joint_degrees: list[float],
    offsets: np.ndarray,
    config: dict[str, Any],
) -> None:
    physical = np.asarray(joint_degrees, dtype=np.float64)
    physical[:5] += offsets
    qpos = _physical_to_model_position(physical[None, :], config)[0]
    for index, name in enumerate(config["bindings"]["joint_names"]):
        joint_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_JOINT, name
        )
        data.qpos[int(model.jnt_qposadr[joint_id])] = qpos[index]
    data.qvel[:] = 0
    mujoco.mj_forward(model, data)


def metrics(errors: list[np.ndarray]) -> dict[str, float]:
    norms = np.concatenate(
        [np.linalg.norm(error, axis=1) for error in errors]
    )
    return {
        "rmse_px": float(np.sqrt(np.mean(norms**2))),
        "max_px": float(np.max(norms)),
        "mean_px": float(np.mean(norms)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.output_directory.exists():
        raise RuntimeError("refusing to overwrite base-hole camera diagnostic")
    candidate = json.loads(arguments.candidate.read_text(encoding="utf-8"))
    sources = frame_sources(candidate)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    config = manifest["candidate_config"]
    model, _ = _compile_model(config, base_directory=None)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    topology = [
        topology_center(model, data, specification)
        for specification in FEATURES
    ]
    landmark_world = np.asarray([item[0] for item in topology])
    topology_receipts = [item[1] for item in topology]
    offsets = np.asarray(
        candidate["parameters"]["joint_zero_offsets_degrees"],
        dtype=np.float64,
    )
    frames = []
    for source in sources:
        image_path = Path(source["image_path"])
        receipt_path = Path(source["receipt_path"])
        image = cv2.imread(str(image_path))
        execution = json.loads(receipt_path.read_text(encoding="utf-8"))
        if (
            image is None
            or sha256(image_path) != source["image_sha256"]
            or sha256(receipt_path) != source["receipt_sha256"]
            or (execution.get("pi_hold_still") or {}).get("sha256")
            != source["image_sha256"]
        ):
            raise RuntimeError(f"frame lineage failed for {source['name']}")
        labels = []
        radii = []
        for specification in FEATURES:
            center, radius = detect_feature(image, specification)
            labels.append(center)
            radii.append(radius)
        set_pose(
            model, data, source["joint_degrees"], offsets, config
        )
        detected = detect_tags(image)
        expected_ids = sorted(
            int(tag_id) for tag_id in candidate["tag_model"]["tags"]
        )
        observed_tags = {
            tag_id: detected[tag_id]
            for tag_id in expected_ids
            if tag_id in detected
        }
        world_tags = tag_world_corners(
            model,
            data,
            candidate["tag_model"],
            candidate["parameters"],
        )
        frames.append(
            {
                "name": source["name"],
                "image": image,
                "image_path": image_path,
                "image_sha256": source["image_sha256"],
                "execution_receipt_path": receipt_path,
                "execution_receipt_sha256": source["receipt_sha256"],
                "landmark_labels": np.asarray(labels),
                "landmark_radii": radii,
                "observed_tags": observed_tags,
                "world_tags": world_tags,
            }
        )
    label_stack = np.stack(
        [frame["landmark_labels"] for frame in frames]
    )
    repeatability = np.ptp(label_stack, axis=0)
    if np.any(repeatability > 2.0):
        raise RuntimeError("fixed-base image centers are not repeatable")
    focal = float(candidate["intrinsics"]["focal_pixels"])
    seed = np.asarray(
        [
            *candidate["parameters"][
                "camera_world_rotation_vector_radians"
            ],
            *candidate["parameters"]["camera_world_translation_m"],
        ],
        dtype=np.float64,
    )

    def residual(vector: np.ndarray) -> np.ndarray:
        camera = transform(vector[:3].tolist(), vector[3:6].tolist())
        values = []
        projected_landmarks = project(
            landmark_world, camera, focal
        )
        for frame in frames:
            values.append(
                (projected_landmarks - frame["landmark_labels"]).ravel()
            )
            for tag_id in sorted(frame["observed_tags"]):
                values.append(
                    (
                        project(
                            frame["world_tags"][tag_id], camera, focal
                        )
                        - frame["observed_tags"][tag_id]
                    ).ravel()
                )
        return np.concatenate(values)

    bounds = np.asarray([0.35, 0.35, 0.35, 0.15, 0.15, 0.15])
    result = least_squares(
        residual,
        seed,
        bounds=(seed - bounds, seed + bounds),
        loss="soft_l1",
        f_scale=2.0,
        max_nfev=3000,
    )
    cameras = {
        "before": transform(seed[:3].tolist(), seed[3:6].tolist()),
        "after": transform(
            result.x[:3].tolist(), result.x[3:6].tolist()
        ),
    }
    per_frame = {}
    aggregate = {
        phase: {"landmark": [], "tag": []} for phase in cameras
    }
    visualization_panels = []
    for frame in frames:
        panel = frame["image"].copy()
        frame_result = {}
        for phase, camera in cameras.items():
            projected_landmarks = project(
                landmark_world, camera, focal
            )
            landmark_errors = (
                projected_landmarks - frame["landmark_labels"]
            )
            tag_errors = []
            for tag_id in sorted(frame["observed_tags"]):
                tag_errors.append(
                    project(frame["world_tags"][tag_id], camera, focal)
                    - frame["observed_tags"][tag_id]
                )
            aggregate[phase]["landmark"].append(landmark_errors)
            aggregate[phase]["tag"].extend(tag_errors)
            frame_result[phase] = {
                "landmark": metrics([landmark_errors]),
                "tag": metrics(tag_errors),
            }
            color = (0, 165, 255) if phase == "before" else (255, 255, 255)
            for observed, projected in zip(
                frame["landmark_labels"],
                projected_landmarks,
                strict=True,
            ):
                cv2.line(
                    panel,
                    tuple(np.rint(observed).astype(int)),
                    tuple(np.rint(projected).astype(int)),
                    color,
                    2,
                    cv2.LINE_AA,
                )
                cv2.drawMarker(
                    panel,
                    tuple(np.rint(projected).astype(int)),
                    color,
                    cv2.MARKER_CROSS,
                    15,
                    2,
                )
        for observed in frame["landmark_labels"]:
            cv2.circle(
                panel,
                tuple(np.rint(observed).astype(int)),
                6,
                (70, 255, 70),
                2,
                cv2.LINE_AA,
            )
        cv2.putText(
            panel,
            f"{frame['name']} | green observed | orange before | white after",
            (24, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        visualization_panels.append(cv2.resize(panel, (768, 432)))
        per_frame[frame["name"]] = frame_result
    aggregate_metrics = {
        phase: {
            kind: metrics(errors)
            for kind, errors in values.items()
        }
        for phase, values in aggregate.items()
    }
    no_tag_frame_worsened = all(
        values["after"]["tag"]["rmse_px"]
        <= values["before"]["tag"]["rmse_px"] + 1e-9
        for values in per_frame.values()
    )
    pareto = (
        aggregate_metrics["after"]["landmark"]["rmse_px"]
        < aggregate_metrics["before"]["landmark"]["rmse_px"]
        and aggregate_metrics["after"]["tag"]["rmse_px"]
        < aggregate_metrics["before"]["tag"]["rmse_px"]
        and no_tag_frame_worsened
    )
    visualization = np.vstack(
        [
            np.hstack(visualization_panels[:2]),
            np.hstack(visualization_panels[2:]),
        ]
    )
    arguments.output_directory.mkdir(parents=True)
    visualization_path = arguments.output_directory / "visualization.jpg"
    if not cv2.imwrite(str(visualization_path), visualization):
        raise RuntimeError("failed to write visualization")
    delta_rotation = cameras["after"][:3, :3] @ cameras["before"][:3, :3].T
    receipt = {
        "schema_version": "sim2claw.pi_fixed_base_hole_camera_fit.v1",
        "proof_class": "physical_image_shared_camera_diagnostic_only",
        "status": "completed",
        "candidate": {
            "path": str(arguments.candidate),
            "sha256": sha256(arguments.candidate),
            "joint_tag_geometry_parameters_changed": False,
        },
        "correspondence_gate": {
            "passed": True,
            "topology_features": topology_receipts,
            "image_center_repeatability_peak_to_peak_px": (
                repeatability.tolist()
            ),
            "labels_by_frame": {
                frame["name"]: frame["landmark_labels"].tolist()
                for frame in frames
            },
        },
        "fit": {
            "method": "single_shared_six_dof_camera_soft_l1",
            "per_frame_fit": False,
            "camera_before": {
                "rotation_vector_radians": seed[:3].tolist(),
                "translation_m": seed[3:6].tolist(),
            },
            "camera_after_diagnostic_only": {
                "rotation_vector_radians": result.x[:3].tolist(),
                "translation_m": result.x[3:6].tolist(),
            },
            "rotation_delta_degrees": float(
                np.degrees(
                    Rotation.from_matrix(delta_rotation).magnitude()
                )
            ),
            "translation_delta_m": float(
                np.linalg.norm(result.x[3:6] - seed[3:6])
            ),
            "optimizer_optimality": float(result.optimality),
        },
        "metrics": {
            "aggregate": aggregate_metrics,
            "per_frame": per_frame,
            "pareto_rule": (
                "both aggregate RMSE values strictly improve and no frame tag "
                "RMSE worsens"
            ),
            "no_tag_frame_worsened": no_tag_frame_worsened,
            "genuine_pareto_improvement": pareto,
        },
        "visualization": {
            "path": str(visualization_path),
            "sha256": sha256(visualization_path),
        },
        "authority": {
            "candidate_camera_update": False,
            "simulator_parameter_promotion": False,
            "policy": False,
            "physical_task": False,
        },
    }
    receipt_path = arguments.output_directory / "receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

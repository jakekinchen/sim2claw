#!/usr/bin/env python3
"""Evaluate exact fixed-base CAD rims against physical image arcs without fitting."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import cv2
import mujoco
import numpy as np

from fit_pi_fixed_base_hole_camera import (
    FEATURES,
    frame_sources,
    mesh_arrays,
    set_pose,
)
from render_pi_cad_overlay import MANIFEST, project, transform
from sim2claw.recorded_replay import _compile_model


ROOT = Path(__file__).resolve().parents[1]
PRIOR_CENTER_RECEIPT = (
    ROOT
    / "runs/pi-link-tag-calibration/"
    "20260726-fixed-base-hole-camera-v1/receipt.json"
)
RIM_SAMPLE_COUNT = 720
ORIENTATION_TOLERANCE_DEGREES = 45.0
DISAPPEARANCE_THRESHOLD_PX = 10.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def cylinder_side_faces(
    vertices: np.ndarray,
    faces: np.ndarray,
    specification: dict[str, Any],
) -> np.ndarray:
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
    result = faces[selected]
    if len(result) < 32:
        raise RuntimeError("cylindrical topology support disappeared")
    return result


def ordered_boundary_loops(side_faces: np.ndarray) -> list[np.ndarray]:
    counts: Counter[tuple[int, int]] = Counter()
    for face in side_faces:
        for first, second in (
            (face[0], face[1]),
            (face[1], face[2]),
            (face[2], face[0]),
        ):
            counts[tuple(sorted((int(first), int(second))))] += 1
    boundary = [edge for edge, count in counts.items() if count == 1]
    adjacency: dict[int, set[int]] = defaultdict(set)
    for first, second in boundary:
        adjacency[first].add(second)
        adjacency[second].add(first)
    if not adjacency or any(len(neighbors) != 2 for neighbors in adjacency.values()):
        raise RuntimeError("selected cylinder boundary is not closed degree-two topology")

    loops = []
    remaining = set(adjacency)
    while remaining:
        start = min(remaining)
        ordered = [start]
        previous = None
        current = start
        while True:
            choices = sorted(adjacency[current] - ({previous} if previous is not None else set()))
            following = choices[0]
            if following == start:
                break
            if following in ordered:
                raise RuntimeError("boundary loop self-intersects")
            ordered.append(following)
            previous, current = current, following
        remaining.difference_update(ordered)
        loops.append(np.asarray(ordered, dtype=np.int32))
    if len(loops) != 2:
        raise RuntimeError(f"expected two exact cylinder rims, found {len(loops)}")
    return loops


def sample_closed_polyline(points: np.ndarray, count: int) -> np.ndarray:
    following = np.roll(points, -1, axis=0)
    lengths = np.linalg.norm(following - points, axis=1)
    cumulative = np.concatenate([[0.0], np.cumsum(lengths)])
    if cumulative[-1] <= 0:
        raise RuntimeError("rim perimeter vanished")
    targets = np.linspace(0.0, cumulative[-1], count, endpoint=False)
    segments = np.searchsorted(cumulative[1:], targets, side="right")
    fraction = (targets - cumulative[segments]) / lengths[segments]
    return points[segments] + fraction[:, None] * (
        following[segments] - points[segments]
    )


def camera_depth(points: np.ndarray, camera_world: np.ndarray) -> np.ndarray:
    homogeneous = np.column_stack([points, np.ones(len(points))])
    return (camera_world @ homogeneous.T)[2]


def image_curve_normals(points: np.ndarray) -> np.ndarray:
    tangents = np.roll(points, -1, axis=0) - np.roll(points, 1, axis=0)
    tangents /= np.maximum(np.linalg.norm(tangents, axis=1)[:, None], 1e-12)
    return np.column_stack([-tangents[:, 1], tangents[:, 0]])


def physical_arc_support(
    image: np.ndarray, roi_xyxy: list[int]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x0, y0, x1, y1 = roi_xyxy
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    crop = cv2.GaussianBlur(gray[y0:y1, x0:x1], (5, 5), 1.0)
    edges = cv2.Canny(crop, 30, 90, L2gradient=True)
    gradient_x = cv2.Sobel(crop, cv2.CV_64F, 1, 0, ksize=3)
    gradient_y = cv2.Sobel(crop, cv2.CV_64F, 0, 1, ksize=3)
    rows, columns = np.nonzero(edges)
    if len(rows) < 8:
        raise RuntimeError("physical arc support disappeared")
    points = np.column_stack([columns + x0, rows + y0]).astype(np.float64)
    normals = np.column_stack(
        [gradient_x[rows, columns], gradient_y[rows, columns]]
    )
    norms = np.linalg.norm(normals, axis=1)
    valid = norms > 1e-9
    return points[valid], normals[valid] / norms[valid, None], edges


def oriented_nearest(
    source_points: np.ndarray,
    source_normals: np.ndarray,
    target_points: np.ndarray,
    target_normals: np.ndarray,
) -> np.ndarray:
    compatibility = np.abs(source_normals @ target_normals.T)
    threshold = np.cos(np.radians(ORIENTATION_TOLERANCE_DEGREES))
    distances = np.linalg.norm(
        source_points[:, None, :] - target_points[None, :, :],
        axis=2,
    )
    distances[compatibility < threshold] = np.inf
    result = np.min(distances, axis=1)
    if np.any(~np.isfinite(result)):
        raise RuntimeError("orientation gate removed all counterparts")
    return result


def distribution(values: np.ndarray) -> dict[str, float | int]:
    median = float(np.median(values))
    return {
        "count": int(len(values)),
        "median_px": median,
        "mad_px": float(np.median(np.abs(values - median))),
        "p90_px": float(np.percentile(values, 90)),
        "rmse_px": float(np.sqrt(np.mean(values**2))),
        "max_px": float(np.max(values)),
        "within_5px_fraction": float(np.mean(values <= 5.0)),
        "within_10px_fraction": float(np.mean(values <= 10.0)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.output_directory.exists():
        raise RuntimeError("refusing to overwrite projective-rim evaluation")

    candidate = json.loads(arguments.candidate.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    config = manifest["candidate_config"]
    model, _ = _compile_model(config, base_directory=None)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    camera_world = transform(
        candidate["parameters"]["camera_world_rotation_vector_radians"],
        candidate["parameters"]["camera_world_translation_m"],
    )
    focal = float(candidate["intrinsics"]["focal_pixels"])
    offsets = np.asarray(
        candidate["parameters"]["joint_zero_offsets_degrees"],
        dtype=np.float64,
    )

    topology = {}
    for specification in FEATURES:
        vertices, faces, mesh_id = mesh_arrays(
            model, specification["mesh_name"]
        )
        side_faces = cylinder_side_faces(vertices, faces, specification)
        loops = ordered_boundary_loops(side_faces)
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
        topology[specification["feature_id"]] = {
            "mesh_id": mesh_id,
            "geom_id": geom_id,
            "body_id": body_id,
            "side_face_count": int(len(side_faces)),
            "loops": loops,
            "vertices": vertices,
        }

    prior = json.loads(PRIOR_CENTER_RECEIPT.read_text(encoding="utf-8"))
    prior_candidate = prior["candidate"]
    if (
        Path(prior_candidate["path"]).resolve() != arguments.candidate.resolve()
        or prior_candidate["sha256"] != sha256(arguments.candidate)
    ):
        raise RuntimeError("prior center receipt is not bound to candidate")

    frame_results = {}
    panels = []
    aggregate_visible_cad_to_arc = []
    aggregate_visible_symmetric = []
    aggregate_by_feature_rim = {
        specification["feature_id"]: {"near": [], "far": []}
        for specification in FEATURES
    }
    sources = frame_sources(candidate)
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
        set_pose(model, data, source["joint_degrees"], offsets, config)
        panel = image.copy()
        feature_results = {}
        for specification in FEATURES:
            feature_id = specification["feature_id"]
            item = topology[feature_id]
            geom_id = item["geom_id"]
            rotation = data.geom_xmat[geom_id].reshape(3, 3)
            translation = data.geom_xpos[geom_id]
            rim_records = []
            for loop in item["loops"]:
                local = sample_closed_polyline(
                    item["vertices"][loop], RIM_SAMPLE_COUNT
                )
                world = local @ rotation.T + translation
                pixels = project(world, camera_world, focal)
                rim_records.append(
                    {
                        "pixels": pixels,
                        "normals": image_curve_normals(pixels),
                        "mean_camera_depth_m": float(
                            np.mean(camera_depth(world, camera_world))
                        ),
                        "vertex_count": int(len(loop)),
                    }
                )
            rim_records.sort(key=lambda record: record["mean_camera_depth_m"])
            arc_points, arc_normals, _ = physical_arc_support(
                image, specification["hough_roi_xyxy"]
            )
            rim_results = {}
            for index, (name, rim) in enumerate(
                zip(("near", "far"), rim_records, strict=True)
            ):
                cad_to_arc = oriented_nearest(
                    rim["pixels"], rim["normals"], arc_points, arc_normals
                )
                arc_to_cad = oriented_nearest(
                    arc_points, arc_normals, rim["pixels"], rim["normals"]
                )
                symmetric = np.concatenate([cad_to_arc, arc_to_cad])
                rim_results[name] = {
                    "depth_rank": index,
                    "mean_camera_depth_m": rim["mean_camera_depth_m"],
                    "topology_vertex_count": rim["vertex_count"],
                    "sample_count": RIM_SAMPLE_COUNT,
                    "cad_to_physical_arc": distribution(cad_to_arc),
                    "physical_arc_to_cad": distribution(arc_to_cad),
                    "symmetric_oriented": distribution(symmetric),
                }
                aggregate_by_feature_rim[feature_id][name].append(cad_to_arc)
                color = (255, 220, 40) if name == "near" else (0, 165, 255)
                polyline = np.rint(rim["pixels"]).astype(np.int32)
                cv2.polylines(
                    panel,
                    [polyline],
                    True,
                    color,
                    2,
                    cv2.LINE_AA,
                )
            near_pixels = rim_records[0]["pixels"]
            near_normals = rim_records[0]["normals"]
            visible_cad_to_arc = oriented_nearest(
                near_pixels, near_normals, arc_points, arc_normals
            )
            visible_arc_to_cad = oriented_nearest(
                arc_points, arc_normals, near_pixels, near_normals
            )
            aggregate_visible_cad_to_arc.append(visible_cad_to_arc)
            aggregate_visible_symmetric.append(
                np.concatenate([visible_cad_to_arc, visible_arc_to_cad])
            )
            x0, y0, x1, y1 = specification["hough_roi_xyxy"]
            cv2.rectangle(panel, (x0, y0), (x1, y1), (70, 255, 70), 1)
            for point in np.rint(arc_points).astype(int):
                cv2.circle(panel, tuple(point), 1, (70, 255, 70), -1)
            feature_results[feature_id] = {
                "owning_body": mujoco.mj_id2name(
                    model, mujoco.mjtObj.mjOBJ_BODY, item["body_id"]
                ),
                "owning_geom_id": geom_id,
                "mesh_name": specification["mesh_name"],
                "side_face_count": item["side_face_count"],
                "physical_arc_extraction": {
                    "method": "fixed_roi_gaussian_canny_all_oriented_edges",
                    "roi_xyxy": specification["hough_roi_xyxy"],
                    "canny_thresholds": [30, 90],
                    "admitted_edge_pixel_count": int(len(arc_points)),
                    "uses_fitted_circle_center": False,
                },
                "rims": rim_results,
                "visibility_rule": "near is smaller mean positive camera depth",
            }
        cv2.putText(
            panel,
            (
                f"{source['name']} | green physical arcs | "
                "cyan near CAD rim | orange far CAD rim"
            ),
            (24, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        panels.append(cv2.resize(panel, (768, 432)))
        frame_results[source["name"]] = {
            "image_path": str(image_path),
            "image_sha256": source["image_sha256"],
            "features": feature_results,
        }

    visible_cad_to_arc = np.concatenate(aggregate_visible_cad_to_arc)
    visible_symmetric = np.concatenate(aggregate_visible_symmetric)
    aggregate = {
        "depth_visible_near_rim_cad_to_physical_arc": distribution(
            visible_cad_to_arc
        ),
        "depth_visible_near_rim_symmetric_oriented": distribution(
            visible_symmetric
        ),
        "cad_to_physical_arc_by_feature_and_depth": {
            feature_id: {
                rim_name: distribution(np.concatenate(values))
                for rim_name, values in rims.items()
            }
            for feature_id, rims in aggregate_by_feature_rim.items()
        },
    }
    contradiction_disappears = (
        aggregate["depth_visible_near_rim_cad_to_physical_arc"]["rmse_px"]
        <= DISAPPEARANCE_THRESHOLD_PX
        and aggregate["depth_visible_near_rim_cad_to_physical_arc"]["p90_px"]
        <= DISAPPEARANCE_THRESHOLD_PX
    )

    visualization = np.vstack(
        [np.hstack(panels[:2]), np.hstack(panels[2:])]
    )
    arguments.output_directory.mkdir(parents=True)
    visualization_path = arguments.output_directory / "visualization.jpg"
    if not cv2.imwrite(str(visualization_path), visualization):
        raise RuntimeError("failed to write projective-rim visualization")

    receipt = {
        "schema_version": "sim2claw.pi_fixed_base_projective_rim.v1",
        "proof_class": "physical_image_frozen_projective_rim_diagnostic_only",
        "status": "completed",
        "candidate": {
            "path": str(arguments.candidate),
            "sha256": sha256(arguments.candidate),
        },
        "frozen_inputs": {
            "camera_intrinsics_joints_tag_mounts_feature_centers_meshes": True,
            "optimized_parameter_count": 0,
            "per_frame_fit": False,
            "rim_sample_count": RIM_SAMPLE_COUNT,
            "orientation_tolerance_degrees": ORIENTATION_TOLERANCE_DEGREES,
        },
        "prior_fitted_circle_centers_diagnostic_metadata_only": {
            "receipt_path": str(PRIOR_CENTER_RECEIPT),
            "receipt_sha256": sha256(PRIOR_CENTER_RECEIPT),
            "used_for_arc_extraction_or_scoring": False,
            "labels_by_frame": prior["correspondence_gate"]["labels_by_frame"],
            "aggregate_center_point_rmse_px": prior["metrics"]["aggregate"][
                "before"
            ]["landmark"]["rmse_px"],
        },
        "frames": frame_results,
        "aggregate": aggregate,
        "decision": {
            "rule": (
                "contradiction disappears only if depth-visible near-rim "
                "CAD-to-physical-arc RMSE and p90 are both <= 10 px"
            ),
            "threshold_px": DISAPPEARANCE_THRESHOLD_PX,
            "center_point_contradiction_disappears": contradiction_disappears,
            "model_or_candidate_update_authorized": False,
        },
        "visualization": {
            "path": str(visualization_path),
            "sha256": sha256(visualization_path),
        },
        "authority": {
            "camera_update": False,
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

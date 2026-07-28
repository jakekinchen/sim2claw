#!/usr/bin/env python3
"""Diagnose fixed-base registration under one frozen Pi camera."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from sim2claw.paths import SO101_MODEL_PATH
from sim2claw.recorded_replay import _compile_model


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = (
    ROOT
    / "runs/physical_excitation/20260725-follower-only-v1/"
    "simulation-canary-v1/candidate_manifest.json"
)
HELDOUT = (
    ROOT
    / "runs/pi-link-tag-calibration/"
    "20260726-current-three-link-fresh-validation-v1/"
    "heldout-evaluation.json"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def transform(rotation_vector: list[float], translation: list[float]) -> np.ndarray:
    value = np.eye(4)
    value[:3, :3] = Rotation.from_rotvec(rotation_vector).as_matrix()
    value[:3, 3] = translation
    return value


def project(points: np.ndarray, camera_world: np.ndarray, focal: float) -> np.ndarray:
    homogeneous = np.column_stack([points, np.ones(len(points))])
    camera = (camera_world @ homogeneous.T)[:3]
    if np.any(camera[2] <= 1e-5):
        raise RuntimeError("left_base mesh crosses the camera plane")
    normalized = camera[:2] / camera[2:3]
    return np.column_stack(
        [focal * normalized[0] + 768.0, focal * normalized[1] + 432.0]
    )


def frame_sources(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    wanted = {"pose_h_current", "pose_i_current", "pose_f_current"}
    sources: dict[str, dict[str, Any]] = {}
    for observation in candidate["training"]:
        name = observation["name"]
        if name in wanted and name not in sources:
            sources[name] = observation
    heldout = json.loads(HELDOUT.read_text(encoding="utf-8"))
    sources["pose_n_fresh_heldout"] = heldout["heldout"][0]
    if set(sources) != wanted | {"pose_n_fresh_heldout"}:
        raise RuntimeError("candidate does not bind H, I, F, and fresh N")
    return [sources[name] for name in (
        "pose_h_current",
        "pose_i_current",
        "pose_f_current",
        "pose_n_fresh_heldout",
    )]


def base_mask(
    candidate: dict[str, Any],
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    model, _ = _compile_model(manifest["candidate_config"], base_directory=None)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    body_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, "left_base"
    )
    camera_world = transform(
        candidate["parameters"]["camera_world_rotation_vector_radians"],
        candidate["parameters"]["camera_world_translation_m"],
    )
    focal = float(candidate["intrinsics"]["focal_pixels"])
    mask = np.zeros((864, 1536), dtype=np.uint8)
    meshes = []
    for geom_id in range(model.ngeom):
        if (
            int(model.geom_bodyid[geom_id]) != body_id
            or int(model.geom_group[geom_id]) != 2
            or int(model.geom_type[geom_id])
            != int(mujoco.mjtGeom.mjGEOM_MESH)
        ):
            continue
        mesh_id = int(model.geom_dataid[geom_id])
        vertex_start = int(model.mesh_vertadr[mesh_id])
        vertex_count = int(model.mesh_vertnum[mesh_id])
        face_start = int(model.mesh_faceadr[mesh_id])
        face_count = int(model.mesh_facenum[mesh_id])
        vertices = np.asarray(
            model.mesh_vert[vertex_start : vertex_start + vertex_count],
            dtype=np.float64,
        )
        faces = np.asarray(
            model.mesh_face[face_start : face_start + face_count],
            dtype=np.int32,
        )
        rotation = data.geom_xmat[geom_id].reshape(3, 3)
        world = vertices @ rotation.T + data.geom_xpos[geom_id]
        pixels = project(world, camera_world, focal)
        for face in faces:
            triangle = np.rint(pixels[face]).astype(np.int32)
            cv2.fillConvexPoly(mask, triangle, 255)
        mesh_name = mujoco.mj_id2name(
            model, mujoco.mjtObj.mjOBJ_MESH, mesh_id
        )
        meshes.append(
            {
                "geom_id": geom_id,
                "mesh_id": mesh_id,
                "mesh_name": mesh_name,
                "vertex_count": vertex_count,
                "triangle_count": face_count,
                "compiled_geometry_sha256": hashlib.sha256(
                    vertices.astype("<f4").tobytes()
                    + faces.astype("<i4").tobytes()
                ).hexdigest(),
            }
        )
    if len(meshes) != 4 or cv2.countNonZero(mask) == 0:
        raise RuntimeError("expected all four left_base visual mesh geoms")
    return mask, meshes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.output_directory.exists():
        raise RuntimeError("refusing to overwrite fixed-base diagnostic")
    candidate = json.loads(arguments.candidate.read_text(encoding="utf-8"))
    if candidate.get("schema_version") != (
        "sim2claw.pi_current_three_link_candidate.v1"
    ):
        raise RuntimeError("unexpected Pi calibration candidate")
    sources = frame_sources(candidate)
    mask, meshes = base_mask(candidate)
    contours, _ = cv2.findContours(
        mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
    )
    contour = max(contours, key=cv2.contourArea).reshape(-1, 2)
    edge_maps = []
    images = []
    frame_receipts = []
    for source in sources:
        image_path = Path(source["image_path"])
        receipt_path = Path(source["receipt_path"])
        image = cv2.imread(str(image_path))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if (
            image is None
            or image.shape[:2] != (864, 1536)
            or sha256(image_path) != source["image_sha256"]
            or sha256(receipt_path) != source["receipt_sha256"]
            or (receipt.get("pi_hold_still") or {}).get("sha256")
            != source["image_sha256"]
        ):
            raise RuntimeError(f"frame lineage failed for {source['name']}")
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edge_maps.append(cv2.Canny(gray, 60, 140))
        images.append(image)
        frame_receipts.append(
            {
                "name": source["name"],
                "image_path": str(image_path),
                "image_sha256": source["image_sha256"],
                "execution_receipt_path": str(receipt_path),
                "execution_receipt_sha256": source["receipt_sha256"],
            }
        )
    dilated = [
        cv2.dilate(edges, np.ones((5, 5), np.uint8))
        for edges in edge_maps
    ]
    consensus = (
        np.sum(np.stack(dilated) > 0, axis=0) >= 3
    ).astype(np.uint8) * 255
    distance = cv2.distanceTransform(255 - consensus, cv2.DIST_L2, 5)
    contour_distance = distance[contour[:, 1], contour[:, 0]]
    support = {
        f"within_{radius}_px_fraction": float(
            np.mean(contour_distance <= radius)
        )
        for radius in (2, 4, 8)
    }
    support.update(
        {
            "median_nearest_consensus_edge_px": float(
                np.median(contour_distance)
            ),
            "p90_nearest_consensus_edge_px": float(
                np.percentile(contour_distance, 90)
            ),
            "projected_contour_sample_count": len(contour),
        }
    )
    annotated = []
    for image, edges, source in zip(images, edge_maps, sources, strict=True):
        panel = image.copy()
        panel[consensus > 0] = (
            0.65 * panel[consensus > 0] + 0.35 * np.asarray([255, 0, 255])
        ).astype(np.uint8)
        cv2.drawContours(panel, contours, -1, (0, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(
            panel,
            f"{source['name']} | yellow fixed camera base | magenta 3/4 consensus edges",
            (24, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.72,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        annotated.append(cv2.resize(panel, (768, 432)))
    visualization = np.vstack(
        [np.hstack(annotated[:2]), np.hstack(annotated[2:])]
    )
    reliable = (
        support["within_4_px_fraction"] >= 0.75
        and support["p90_nearest_consensus_edge_px"] <= 8.0
    )
    conclusion = (
        "stationary_base_supplies_reliable_camera_constraint"
        if reliable
        else "stationary_base_contour_not_reliable_from_current_images"
    )
    arguments.output_directory.mkdir(parents=True)
    visualization_path = arguments.output_directory / "visualization.jpg"
    if not cv2.imwrite(str(visualization_path), visualization):
        raise RuntimeError("failed to write fixed-base visualization")
    receipt = {
        "schema_version": "sim2claw.pi_fixed_base_registration_diagnostic.v1",
        "proof_class": "physical_image_fixed_candidate_diagnostic_only",
        "status": "completed",
        "candidate": {
            "path": str(arguments.candidate),
            "sha256": sha256(arguments.candidate),
            "parameters_changed": False,
            "per_frame_camera_adjustment": False,
        },
        "camera": {
            "rotation_vector_radians": candidate["parameters"][
                "camera_world_rotation_vector_radians"
            ],
            "translation_m": candidate["parameters"][
                "camera_world_translation_m"
            ],
            "focal_pixels": candidate["intrinsics"]["focal_pixels"],
            "shared_across_all_frames": True,
        },
        "source_model": {
            "path": str(SO101_MODEL_PATH),
            "sha256": sha256(SO101_MODEL_PATH),
            "compiled_scene_manifest_path": str(MANIFEST),
            "compiled_scene_manifest_sha256": sha256(MANIFEST),
        },
        "left_base_visual_meshes": meshes,
        "frames": frame_receipts,
        "metric": {
            "method": "projected_exact_mesh_union_contour_to_three_of_four_dilated_canny_consensus",
            "canny_thresholds": [60, 140],
            "consensus_dilation_radius_px": 2,
            "required_frame_count": 3,
            **support,
        },
        "decision_rule": {
            "diagnostic_only": True,
            "minimum_within_4_px_fraction": 0.75,
            "maximum_p90_distance_px": 8.0,
        },
        "conclusion": conclusion,
        "reliable_next_camera_constraint": reliable,
        "minimal_alternative": (
            None
            if reliable
            else "Label the same two fixed left_base landmarks in all four images: the upper-left outer housing corner and the upper-right housing-to-column corner; score their shared-camera reprojection without fitting per frame."
        ),
        "limitations": {
            "physical_occlusion_mask_available": False,
            "clamp_separated_from_base": False,
            "moving_shoulder_separated_from_base": False,
            "background_edges_separated_from_base": False,
            "metric_has_camera_update_authority": False,
        },
        "visualization": {
            "path": str(visualization_path),
            "sha256": sha256(visualization_path),
        },
        "authority": {
            "camera_parameter_update": False,
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

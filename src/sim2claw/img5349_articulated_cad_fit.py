"""Evaluate a bounded articulated-CAD hypothesis against the IMG_5349 splat.

This module deliberately does not optimize.  It replays one frozen hypothesis
against the hash-bound board Sim(3), the complete reviewed SO-101 visual meshes,
and a deterministic neutral-surface subset of the private Gaussian cloud.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import mujoco
import numpy as np
from scipy.spatial import cKDTree

from .scene import build_scene_spec, initialize_robot_poses


SCHEMA = "sim2claw.img5349_articulated_cad_fit.v1"
BOARD_SCHEMA = "sim2claw.img5349_3dgs_board_registration.v1"
SH_DC = 0.28209479177387814


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_contract(path: Path) -> dict[str, Any]:
    result = json.loads(path.read_text(encoding="utf-8"))
    if result.get("schema_version") != SCHEMA:
        raise ValueError("unsupported IMG_5349 articulated-CAD schema")
    if result.get("proof_class") != "retrospective_visual_pose_diagnostic":
        raise ValueError("articulated fit must remain a visual diagnostic")
    if any(bool(value) for value in result.get("authority", {}).values()):
        raise ValueError("articulated visual fit cannot grant downstream authority")
    return result


def _load_gaussians(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    properties: list[str] = []
    vertex_count: int | None = None
    with path.open("rb") as handle:
        while True:
            line = handle.readline()
            if not line:
                raise ValueError("PLY header is truncated")
            text = line.decode("ascii").strip()
            if text.startswith("element vertex "):
                vertex_count = int(text.split()[-1])
            elif text.startswith("property float "):
                properties.append(text.split()[-1])
            elif text == "end_header":
                offset = handle.tell()
                break
    if vertex_count is None or len(properties) != 59:
        raise ValueError("expected the bound 59-float Brush Gaussian layout")
    required = ("f_dc_0", "f_dc_1", "f_dc_2", "opacity", "x", "y", "z")
    if any(name not in properties for name in required):
        raise ValueError("PLY is missing required Gaussian properties")
    rows = np.memmap(
        path,
        dtype="<f4",
        mode="r",
        offset=offset,
        shape=(vertex_count, len(properties)),
    )
    positions = np.asarray(
        rows[:, [properties.index(name) for name in ("x", "y", "z")]],
        dtype=np.float64,
    )
    dc = np.asarray(
        rows[:, [properties.index(name) for name in ("f_dc_0", "f_dc_1", "f_dc_2")]],
        dtype=np.float64,
    )
    rgb = np.clip(0.5 + SH_DC * dc, 0.0, 1.0)
    opacity_logit = np.asarray(rows[:, properties.index("opacity")], dtype=np.float64)
    opacity = 1.0 / (1.0 + np.exp(-opacity_logit))
    return positions, rgb, opacity


def _sample_body_vertices(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    *,
    body_name: str,
    maximum_per_geom: int,
) -> np.ndarray:
    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body_name)
    if body_id < 0:
        raise ValueError(f"missing SO-101 body: {body_name}")
    result: list[np.ndarray] = []
    for geom_id in range(model.ngeom):
        if (
            int(model.geom_bodyid[geom_id]) != body_id
            or int(model.geom_group[geom_id]) != 2
            or int(model.geom_type[geom_id]) != int(mujoco.mjtGeom.mjGEOM_MESH)
        ):
            continue
        mesh_id = int(model.geom_dataid[geom_id])
        start = int(model.mesh_vertadr[mesh_id])
        count = int(model.mesh_vertnum[mesh_id])
        vertices = np.asarray(model.mesh_vert[start : start + count], dtype=np.float64)
        if len(vertices) > maximum_per_geom:
            indices = np.linspace(
                0, len(vertices) - 1, maximum_per_geom, dtype=np.int64
            )
            vertices = vertices[indices]
        rotation = np.asarray(data.geom_xmat[geom_id], dtype=np.float64).reshape(3, 3)
        translation = np.asarray(data.geom_xpos[geom_id], dtype=np.float64)
        result.append(vertices @ rotation.T + translation)
    if not result:
        raise ValueError(f"body has no reviewed visual meshes: {body_name}")
    return np.concatenate(result)


def _set_joint_pose(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    names: list[str],
    values: list[float],
) -> None:
    if len(names) != len(values):
        raise ValueError("joint names and values differ in length")
    for name, value in zip(names, values, strict=True):
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        if joint_id < 0:
            raise ValueError(f"missing SO-101 joint: {name}")
        lower, upper = np.asarray(model.jnt_range[joint_id], dtype=np.float64)
        if not math.isfinite(value) or value < lower or value > upper:
            raise ValueError(f"joint hypothesis is outside model limits: {name}")
        data.qpos[int(model.jnt_qposadr[joint_id])] = value
    mujoco.mj_forward(model, data)


def _surface_metrics(tree: cKDTree, points: np.ndarray) -> dict[str, float | int]:
    distances = tree.query(points, k=1)[0]
    return {
        "sample_count": int(len(distances)),
        "median_m": float(np.median(distances)),
        "p75_m": float(np.quantile(distances, 0.75)),
        "p90_m": float(np.quantile(distances, 0.90)),
    }


def evaluate_contract(
    contract: dict[str, Any],
    *,
    repo_root: Path,
) -> dict[str, Any]:
    source = contract["source"]
    ply_path = repo_root / source["ply_path"]
    if sha256_file(ply_path) != source["ply_sha256"]:
        raise ValueError("IMG_5349 PLY binding drifted")

    board_path = repo_root / source["board_registration_path"]
    board = json.loads(board_path.read_text(encoding="utf-8"))
    if board.get("schema_version") != BOARD_SCHEMA:
        raise ValueError("bound board registration schema drifted")
    if sha256_file(board_path) != source["board_registration_sha256"]:
        raise ValueError("bound board registration content drifted")

    positions, rgb, opacity = _load_gaussians(ply_path)
    fit = board["fit"]
    rotation = np.asarray(fit["rotation_source_to_mujoco"], dtype=np.float64)
    translation = np.asarray(fit["translation_mujoco_m"], dtype=np.float64)
    scale = float(fit["scale_m_per_sfm_unit"])
    world = scale * (positions @ rotation.T) + translation

    selection = contract["surface_selection"]
    lower = np.asarray(selection["roi_min_mujoco_m"], dtype=np.float64)
    upper = np.asarray(selection["roi_max_mujoco_m"], dtype=np.float64)
    neutral = np.ptp(rgb, axis=1) < float(selection["maximum_rgb_range"])
    bright = np.mean(rgb, axis=1) > float(selection["minimum_rgb_mean"])
    selected = (
        np.all(world > lower, axis=1)
        & np.all(world < upper, axis=1)
        & neutral
        & bright
        & (opacity > float(selection["minimum_opacity"]))
    )
    cloud = world[selected]
    if len(cloud) != int(selection["expected_selected_splat_count"]):
        raise ValueError("neutral-surface selection no longer reproduces")
    tree = cKDTree(cloud)

    model = build_scene_spec(piece_layout=contract["target"]["piece_layout"]).compile()
    data = mujoco.MjData(model)
    initialize_robot_poses(model, data)
    candidate = contract["right_arm_candidate"]
    joint_names = list(candidate["joint_names"])
    baseline_values = list(candidate["baseline_joint_radians"])
    candidate_values = list(candidate["candidate_joint_radians"])
    body_names = list(candidate["evaluated_body_names"])
    maximum_per_geom = int(contract["surface_selection"]["maximum_vertices_per_geom"])

    by_pose: dict[str, dict[str, Any]] = {}
    for pose_name, values in (
        ("baseline", baseline_values),
        ("candidate", candidate_values),
    ):
        _set_joint_pose(model, data, joint_names, values)
        by_pose[pose_name] = {
            body_name: _surface_metrics(
                tree,
                _sample_body_vertices(
                    model,
                    data,
                    body_name=body_name,
                    maximum_per_geom=maximum_per_geom,
                ),
            )
            for body_name in body_names
        }

    deltas = {
        body_name: {
            "median_delta_m": (
                by_pose["candidate"][body_name]["median_m"]
                - by_pose["baseline"][body_name]["median_m"]
            ),
            "p75_delta_m": (
                by_pose["candidate"][body_name]["p75_m"]
                - by_pose["baseline"][body_name]["p75_m"]
            ),
        }
        for body_name in body_names
    }
    return {
        "schema_version": SCHEMA,
        "status": contract["status"],
        "proof_class": contract["proof_class"],
        "selected_splat_count": int(len(cloud)),
        "surface_metrics": by_pose,
        "surface_deltas": deltas,
        "heldout_silhouette": contract["heldout_silhouette"],
        "visibility": contract["visibility"],
        "verdict": contract["verdict"],
        "authority": contract["authority"],
    }

"""MuJoCo scene manifests and body-state traces for browser inspection.

The browser renderer is a visualization adapter only.  Every pose in a trace
comes from ``MjData`` after MuJoCo has advanced the authoritative simulation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from .paths import DEFAULT_CAPTURE_CONFIG, REPO_ROOT, SO101_MODEL_PATH
from .scene import build_scene_spec, initialize_robot_poses


SCENE_MANIFEST_SCHEMA = "sim2claw.mujoco_scene_manifest.v1"
STATE_TRACE_SCHEMA = "sim2claw.mujoco_body_state_trace.v1"
LIVE_STATE_SCHEMA = "sim2claw.mujoco_live_body_state.v1"
DEFAULT_TRACE_FPS = 30
VISIBLE_GEOM_GROUPS = frozenset({0, 2})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _name(model: mujoco.MjModel, object_type: mujoco.mjtObj, object_id: int) -> str:
    value = mujoco.mj_id2name(model, object_type, object_id)
    if value:
        return value
    return "world" if object_type == mujoco.mjtObj.mjOBJ_BODY and object_id == 0 else f"{object_type.name.lower()}-{object_id}"


def _mesh_path(model: mujoco.MjModel, mesh_id: int) -> str:
    start = int(model.mesh_pathadr[mesh_id])
    end = model.paths.find(b"\0", start)
    if end < 0:
        end = len(model.paths)
    return model.paths[start:end].decode("utf-8")


def _floats(values: Any) -> list[float]:
    return np.asarray(values, dtype=np.float64).astype(float).tolist()


def build_scene_manifest(
    *,
    piece_layout: str = "standard",
    model: mujoco.MjModel | None = None,
) -> dict[str, Any]:
    """Describe the MuJoCo visual scene without making Three.js authoritative."""

    scene_model = model or build_scene_spec(piece_layout=piece_layout).compile()
    initial_data = mujoco.MjData(scene_model)
    initialize_robot_poses(scene_model, initial_data)
    mujoco.mj_forward(scene_model, initial_data)

    mesh_root = SO101_MODEL_PATH.parent / "assets"
    meshes: list[dict[str, Any]] = []
    for mesh_id in range(scene_model.nmesh):
        source_name = Path(_mesh_path(scene_model, mesh_id)).name
        source_path = mesh_root / source_name
        if not source_path.is_file():
            raise FileNotFoundError(f"MuJoCo mesh asset is missing: {source_name}")
        meshes.append(
            {
                "id": mesh_id,
                "name": _name(scene_model, mujoco.mjtObj.mjOBJ_MESH, mesh_id),
                "asset_url": f"/scene-assets/{source_name}",
                "asset_sha256": _sha256(source_path),
                "scale": _floats(scene_model.mesh_scale[mesh_id]),
                # MuJoCo centers/reorients source mesh vertices at compile time.
                # The browser reverses that preprocessing before applying geom poses.
                "compiler_position": _floats(scene_model.mesh_pos[mesh_id]),
                "compiler_quaternion_wxyz": _floats(scene_model.mesh_quat[mesh_id]),
            }
        )

    bodies = [
        {
            "id": body_id,
            "name": _name(scene_model, mujoco.mjtObj.mjOBJ_BODY, body_id),
            "parent_id": int(scene_model.body_parentid[body_id]),
            "initial_position": _floats(initial_data.xpos[body_id]),
            "initial_quaternion_wxyz": _floats(initial_data.xquat[body_id]),
        }
        for body_id in range(scene_model.nbody)
    ]

    geoms: list[dict[str, Any]] = []
    for geom_id in range(scene_model.ngeom):
        group = int(scene_model.geom_group[geom_id])
        if group not in VISIBLE_GEOM_GROUPS:
            continue
        geom_type = mujoco.mjtGeom(int(scene_model.geom_type[geom_id])).name.removeprefix(
            "mjGEOM_"
        ).lower()
        data_id = int(scene_model.geom_dataid[geom_id])
        geoms.append(
            {
                "id": geom_id,
                "name": _name(scene_model, mujoco.mjtObj.mjOBJ_GEOM, geom_id),
                "body_id": int(scene_model.geom_bodyid[geom_id]),
                "group": group,
                "type": geom_type,
                "size": _floats(scene_model.geom_size[geom_id]),
                "position": _floats(scene_model.geom_pos[geom_id]),
                "quaternion_wxyz": _floats(scene_model.geom_quat[geom_id]),
                "rgba": _floats(scene_model.geom_rgba[geom_id]),
                "mesh_id": data_id if geom_type == "mesh" else None,
            }
        )

    piece_positions = [
        np.asarray(initial_data.xpos[body["id"]], dtype=np.float64)
        for body in bodies
        if str(body["name"]).split("_", 1)[0] in {"white", "black", "brown", "tan"}
    ]
    focus = (
        np.mean(np.stack(piece_positions), axis=0)
        if piece_positions
        else np.asarray(scene_model.stat.center, dtype=np.float64)
    )
    overview_camera_id = mujoco.mj_name2id(
        scene_model, mujoco.mjtObj.mjOBJ_CAMERA, "studio_overview"
    )
    suggested_camera = None
    if overview_camera_id >= 0:
        suggested_camera = {
            "name": "studio_overview",
            "position": _floats(initial_data.cam_xpos[overview_camera_id]),
            "target": _floats(focus),
            "fov_degrees": float(scene_model.cam_fovy[overview_camera_id]),
        }

    manifest: dict[str, Any] = {
        "schema_version": SCENE_MANIFEST_SCHEMA,
        "piece_layout": piece_layout,
        "coordinate_system": {
            "up_axis": "Z",
            "distance_unit": "meter",
            "quaternion_order": "wxyz",
        },
        "model": {
            "body_count": scene_model.nbody,
            "visible_geom_count": len(geoms),
            "mesh_count": scene_model.nmesh,
            "center": _floats(scene_model.stat.center),
            "extent": float(scene_model.stat.extent),
            "timestep_seconds": float(scene_model.opt.timestep),
        },
        "bodies": bodies,
        "geoms": geoms,
        "meshes": meshes,
        "suggested_camera": suggested_camera,
        "source": {
            "physics_engine": "MuJoCo",
            "mujoco_version": mujoco.__version__,
            "robot_model": SO101_MODEL_PATH.relative_to(REPO_ROOT).as_posix(),
            "robot_model_sha256": _sha256(SO101_MODEL_PATH),
            "capture_config_sha256": _sha256(DEFAULT_CAPTURE_CONFIG),
        },
        "authority": {
            "physics": "mujoco",
            "browser_renderer": "inspection_only",
            "physical_authority": False,
        },
    }
    revision_source = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    manifest["revision_sha256"] = hashlib.sha256(revision_source).hexdigest()
    return manifest


class EpisodeStateTraceRecorder:
    """Sample world body poses from an already-running MuJoCo episode."""

    def __init__(
        self,
        model: mujoco.MjModel,
        *,
        piece_layout: str = "standard",
        fps: int = DEFAULT_TRACE_FPS,
        proof_class: str = "simulation_episode_state_trace",
        manifest_url: str | None = None,
    ) -> None:
        if fps < 1:
            raise ValueError("trace fps must be positive")
        self.model = model
        self.piece_layout = piece_layout
        self.fps = fps
        self.proof_class = proof_class
        self.manifest_url = manifest_url or f"/api/scene?layout={piece_layout}"
        self.body_names = [
            _name(model, mujoco.mjtObj.mjOBJ_BODY, body_id)
            for body_id in range(model.nbody)
        ]
        self.frames: list[dict[str, Any]] = []
        self._start_time: float | None = None
        self._next_sample_time = 0.0
        self._manifest = build_scene_manifest(piece_layout=piece_layout, model=model)

    def _contacts(self, data: mujoco.MjData) -> list[list[float | int]]:
        contacts: list[list[float | int]] = []
        seen: set[tuple[int, int]] = set()
        for contact_index in range(data.ncon):
            contact = data.contact[contact_index]
            body_1 = int(self.model.geom_bodyid[contact.geom1])
            body_2 = int(self.model.geom_bodyid[contact.geom2])
            if body_1 == body_2:
                continue
            pair = tuple(sorted((body_1, body_2)))
            if pair in seen:
                continue
            seen.add(pair)
            contacts.append([body_1, body_2, *_floats(contact.pos)])
            if len(contacts) >= 24:
                break
        return contacts

    def capture(
        self,
        data: mujoco.MjData,
        *,
        phase: str,
        force: bool = False,
    ) -> bool:
        if self._start_time is None:
            self._start_time = float(data.time)
        elapsed = max(0.0, float(data.time) - self._start_time)
        if not force and elapsed + 1e-9 < self._next_sample_time:
            return False
        if self.frames and abs(elapsed - float(self.frames[-1]["t"])) < 1e-9:
            self.frames[-1]["phase"] = phase
            return False
        self.frames.append(
            {
                "t": round(elapsed, 6),
                "phase": phase,
                "p": np.asarray(data.xpos, dtype=np.float64).reshape(-1).astype(float).tolist(),
                "q": np.asarray(data.xquat, dtype=np.float64).reshape(-1).astype(float).tolist(),
                "c": self._contacts(data),
            }
        )
        interval = 1.0 / self.fps
        if len(self.frames) == 1:
            self._next_sample_time = interval
        else:
            while self._next_sample_time <= elapsed + 1e-9:
                self._next_sample_time += interval
        return True

    def payload(self) -> dict[str, Any]:
        duration = float(self.frames[-1]["t"]) if self.frames else 0.0
        return {
            "schema_version": STATE_TRACE_SCHEMA,
            "proof_class": self.proof_class,
            "scene": {
                "piece_layout": self.piece_layout,
                "manifest_url": self.manifest_url,
                "manifest_revision_sha256": self._manifest["revision_sha256"],
            },
            "fps": self.fps,
            "duration_seconds": duration,
            "frame_count": len(self.frames),
            "body_names": self.body_names,
            "frames": self.frames,
            "authority": {
                "pose_source": "mujoco.MjData.xpos+xquat",
                "browser_interpolation": "visual_only",
                "physical_authority": False,
            },
        }

    def live_snapshot(self) -> dict[str, Any]:
        """Return the latest MuJoCo-owned pose without exporting an episode."""

        return {
            "schema_version": LIVE_STATE_SCHEMA,
            "scene": {
                "piece_layout": self.piece_layout,
                "manifest_url": self.manifest_url,
                "manifest_revision_sha256": self._manifest["revision_sha256"],
            },
            "body_names": self.body_names,
            "frame_index": len(self.frames) - 1 if self.frames else None,
            "frame": self.frames[-1] if self.frames else None,
            "authority": {
                "pose_source": "mujoco.MjData.xpos+xquat",
                "browser_renderer": "inspection_only",
                "physical_authority": False,
            },
        }

    def write(self, path: Path) -> dict[str, Any]:
        payload = self.payload()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n",
            encoding="utf-8",
        )
        payload["path"] = str(path)
        payload["sha256"] = _sha256(path)
        return payload

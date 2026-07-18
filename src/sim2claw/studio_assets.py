"""Generate versioned, inspection-only poster art for the browser studio."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import mujoco

from .paths import (
    DEFAULT_CAPTURE_CONFIG,
    DEFAULT_SO101_MASS_PROFILE,
    SO101_MODEL_PATH,
    STUDIO_ASSET_ROOT,
)
from .render import write_rgb_png
from .scene import (
    CURRENT_TASK_LAYOUT_ID,
    CURRENT_TASK_PIECE_LAYOUT,
    build_scene_spec,
    initialize_robot_poses,
)


POSTER_SPECS = (
    ("studio-overview.png", "studio_overview", 1280, 720),
    ("studio-left.png", "studio_left", 960, 720),
    ("studio-right.png", "studio_right", 960, 720),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _set_geom_color(
    model: mujoco.MjModel,
    name: str,
    rgb: tuple[float, float, float],
) -> None:
    identifier = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, name)
    if identifier >= 0:
        model.geom_rgba[identifier, :3] = rgb


def _apply_inspection_palette(model: mujoco.MjModel) -> None:
    """Increase subject separation for posters without altering task evidence."""

    _set_geom_color(model, "tabletop", (0.56, 0.60, 0.58))
    _set_geom_color(model, "rear_wall", (0.72, 0.75, 0.73))
    _set_geom_color(model, "window_sill", (0.68, 0.71, 0.69))
    _set_geom_color(model, "window_dark", (0.035, 0.055, 0.065))
    for index in range(15):
        _set_geom_color(model, f"blind_{index:02d}", (0.50, 0.53, 0.51))


def render_studio_assets(
    output_directory: Path = STUDIO_ASSET_ROOT,
    *,
    settle_steps: int = 500,
) -> dict[str, Any]:
    """Render current-scene posters that are never used as training observations."""

    if settle_steps < 0:
        raise ValueError("settle_steps cannot be negative")
    output_directory.mkdir(parents=True, exist_ok=True)
    spec = build_scene_spec(piece_layout=CURRENT_TASK_PIECE_LAYOUT)
    model = spec.compile()
    data = mujoco.MjData(model)
    initialize_robot_poses(model, data)
    for _ in range(settle_steps):
        mujoco.mj_step(model, data)
    _apply_inspection_palette(model)
    scene_option = mujoco.MjvOption()
    mujoco.mjv_defaultOption(scene_option)
    scene_option.geomgroup[4] = 0

    artifacts: list[dict[str, Any]] = []
    for filename, camera, width, height in POSTER_SPECS:
        path = output_directory / filename
        renderer = mujoco.Renderer(model, height=height, width=width)
        try:
            renderer.update_scene(data, camera=camera, scene_option=scene_option)
            write_rgb_png(path, renderer.render())
        finally:
            renderer.close()
        artifacts.append(
            {
                "path": filename,
                "camera": camera,
                "width": width,
                "height": height,
                "sha256": _sha256(path),
            }
        )

    scene_source = Path(__file__).with_name("scene.py")
    mass_profile_source = Path(__file__).with_name("mass_profile.py")
    receipt = {
        "schema_version": "sim2claw.studio_assets.v1",
        "proof_class": "simulation_inspection_render",
        "physical_authority": False,
        "training_input": False,
        "piece_layout_id": CURRENT_TASK_LAYOUT_ID,
        "generated_by": "uv run sim2claw studio-assets",
        "settle_steps": settle_steps,
        "sources": {
            "scene_py_sha256": _sha256(scene_source),
            "mass_profile_py_sha256": _sha256(mass_profile_source),
            "capture_config_sha256": _sha256(DEFAULT_CAPTURE_CONFIG),
            "so101_mass_profile_sha256": _sha256(DEFAULT_SO101_MASS_PROFILE),
            "so101_model_sha256": _sha256(SO101_MODEL_PATH),
        },
        "artifacts": artifacts,
    }
    receipt_path = output_directory / "receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt

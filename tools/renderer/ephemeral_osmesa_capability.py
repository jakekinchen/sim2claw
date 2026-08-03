"""Render one tracked SO-101 MJCF frame through a headless OSMesa context."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_ppm(path: Path, frame: object, *, width: int, height: int) -> None:
    path.write_bytes(f"P6\n{width} {height}\n255\n".encode("ascii") + frame.tobytes())


def render_capability(model_path: Path, output_directory: Path) -> dict[str, object]:
    import mujoco
    import numpy as np

    width = 320
    height = 240
    output_directory.mkdir(parents=True, exist_ok=True)
    model = mujoco.MjModel.from_xml_path(str(model_path))
    data = mujoco.MjData(model)
    if model.nkey:
        mujoco.mj_resetDataKeyframe(model, data, 0)
    mujoco.mj_forward(model, data)
    renderer = mujoco.Renderer(model, height=height, width=width)
    try:
        renderer.update_scene(data)
        frame = np.ascontiguousarray(renderer.render(), dtype=np.uint8)
    finally:
        renderer.close()
    if frame.shape != (height, width, 3):
        raise RuntimeError(f"unexpected frame shape: {frame.shape}")
    frame_path = output_directory / "capability_frame.ppm"
    _write_ppm(frame_path, frame, width=width, height=height)
    unique_rgb_count = int(np.unique(frame.reshape(-1, 3), axis=0).shape[0])
    result = {
        "schema_version": "sim2claw.ephemeral_osmesa_renderer_capability_result.v1",
        "status": "PASS_NONEMPTY_OSMESA_RENDER_FRAME",
        "environment": {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "mujoco_version": mujoco.__version__,
            "numpy_version": np.__version__,
            "mujoco_gl": os.environ.get("MUJOCO_GL"),
            "executable": sys.executable,
        },
        "model": {
            "path": str(model_path),
            "sha256": _sha256(model_path),
            "nbody": int(model.nbody),
            "ngeom": int(model.ngeom),
            "nmesh": int(model.nmesh),
        },
        "frame": {
            "path": str(frame_path),
            "sha256": _sha256(frame_path),
            "width_px": width,
            "height_px": height,
            "format": "binary_ppm_rgb",
            "rgb_minimum": int(frame.min()),
            "rgb_maximum": int(frame.max()),
            "rgb_mean": float(frame.mean()),
            "rgb_standard_deviation": float(frame.std()),
            "unique_rgb_triplet_count": unique_rgb_count,
        },
        "execution": {
            "renderer_frames": 1,
            "physical_video_reads": 0,
            "state_trace_reads": 0,
            "candidate_videos": 0,
            "simulator_replays": 0,
            "parameter_fits": 0,
            "hardware_actions": 0,
        },
    }
    if result["frame"]["rgb_standard_deviation"] < 1.0 or unique_rgb_count <= 1:
        raise RuntimeError("rendered frame is visually empty")
    result_path = output_directory / "container_result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(render_capability(args.model, args.output), sort_keys=True))


if __name__ == "__main__":
    main()

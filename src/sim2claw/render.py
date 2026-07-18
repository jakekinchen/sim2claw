from __future__ import annotations

import hashlib
import json
import zlib
from pathlib import Path
from typing import Any

import mujoco

from .paths import DEFAULT_OUTPUT_ROOT
from .scene import build_scene_spec, initialize_robot_poses, scene_summary


PNG_SIGNATURE = bytes.fromhex("89504e470d0a1a0a")


def _png_section(out: bytearray, tag: bytes, body: bytes) -> None:
    out += len(body).to_bytes(4, "big")
    out += tag
    out += body
    out += (zlib.crc32(body, zlib.crc32(tag)) & 0xFFFFFFFF).to_bytes(4, "big")


def write_rgb_png(path: Path, image: Any) -> None:
    if image.ndim != 3 or image.shape[2] != 3 or image.dtype.name != "uint8":
        raise ValueError("expected an HxWx3 uint8 RGB image")
    height, width = image.shape[0], image.shape[1]

    filtered = bytearray()
    for scanline in image:
        filtered.append(0)
        filtered.extend(scanline.tobytes())

    header = bytearray()
    header += width.to_bytes(4, "big")
    header += height.to_bytes(4, "big")
    header += bytes((8, 2, 0, 0, 0))

    encoded = bytearray(PNG_SIGNATURE)
    _png_section(encoded, b"IHDR", bytes(header))
    _png_section(encoded, b"IDAT", zlib.compress(bytes(filtered), 9))
    _png_section(encoded, b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(encoded))


def render_scene(
    *,
    output_path: Path = DEFAULT_OUTPUT_ROOT / "render.png",
    width: int = 768,
    height: int = 1152,
    settle_steps: int = 500,
    camera: str = "photo_reference",
    scan_overlay: bool = False,
) -> dict[str, Any]:
    if width < 64 or height < 64:
        raise ValueError("render dimensions must be at least 64x64")
    if settle_steps < 0:
        raise ValueError("settle_steps cannot be negative")

    spec = build_scene_spec(scan_overlay=scan_overlay)
    model = spec.compile()
    data = mujoco.MjData(model)
    initialize_robot_poses(model, data)
    for _ in range(settle_steps):
        mujoco.mj_step(model, data)

    renderer = mujoco.Renderer(model, height=height, width=width)
    try:
        renderer.update_scene(data, camera=camera)
        image = renderer.render()
    finally:
        renderer.close()
    write_rgb_png(output_path, image)

    model_path = output_path.with_suffix(".xml")
    report_path = output_path.with_suffix(".json")
    model_path.write_text(spec.to_xml(), encoding="utf-8")
    report = {
        **scene_summary(),
        "mujoco_version": mujoco.__version__,
        "model": {
            "nbody": model.nbody,
            "ngeom": model.ngeom,
            "njnt": model.njnt,
            "nq": model.nq,
            "nv": model.nv,
            "nu": model.nu,
        },
        "render": {
            "width": width,
            "height": height,
            "camera": camera,
            "settle_steps": settle_steps,
            "scan_overlay": scan_overlay,
            "image_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        },
        "artifacts": {
            "image": str(output_path),
            "model_xml": str(model_path),
            "report": str(report_path),
        },
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report

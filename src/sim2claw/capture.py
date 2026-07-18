from __future__ import annotations

import hashlib
import json
import os
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image

from .gltf import convert_textured_gltf_to_obj
from .paths import DEFAULT_CAPTURE_CONFIG, DEFAULT_EXTERNAL_ROOT


def load_capture_config(path: Path = DEFAULT_CAPTURE_CONFIG) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema_version") not in {1, 2}:
        raise ValueError("unsupported capture configuration schema")
    if not config.get("capture_id") or not config.get("artifacts"):
        raise ValueError("capture configuration is missing required fields")
    return config


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(65536):
            hasher.update(block)
    return hasher.hexdigest()


def _download_verified(url: str, destination: Path, expected_sha256: str) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and sha256_file(destination) == expected_sha256:
        return "verified-existing"

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "sim2claw-clean-room-fetch/0.1"},
    )
    temporary_name: str | None = None
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            with tempfile.NamedTemporaryFile(
                dir=destination.parent, prefix=destination.name + ".", delete=False
            ) as temporary:
                temporary_name = temporary.name
                while chunk := response.read(1024 * 1024):
                    temporary.write(chunk)
        temporary_path = Path(temporary_name)
        actual_sha256 = sha256_file(temporary_path)
        if actual_sha256 != expected_sha256:
            raise ValueError(
                f"SHA-256 mismatch for {destination.name}: "
                f"expected {expected_sha256}, got {actual_sha256}"
            )
        os.replace(temporary_path, destination)
        return "downloaded"
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)


def capture_directory(
    config: dict[str, Any], external_root: Path = DEFAULT_EXTERNAL_ROOT
) -> Path:
    return external_root / config["capture_id"]


def fetch_capture(
    config_path: Path = DEFAULT_CAPTURE_CONFIG,
    external_root: Path = DEFAULT_EXTERNAL_ROOT,
) -> dict[str, Any]:
    config = load_capture_config(config_path)
    destination_root = capture_directory(config, external_root)
    statuses: list[dict[str, str]] = []
    for artifact in config["artifacts"]:
        relative_path = Path(artifact["path"])
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError(f"unsafe capture artifact path: {relative_path}")
        status = _download_verified(
            artifact["url"],
            destination_root / relative_path,
            artifact["sha256"],
        )
        statuses.append({"path": str(relative_path), "status": status})

    obj_path, mtl_path = convert_textured_gltf_to_obj(destination_root / "raw.gltf")
    jpeg_path = (
        destination_root / "textures" / "cf0b076cb0c70da17b8b9521e1c314f8.jpg"
    )
    png_path = jpeg_path.with_suffix(".png")
    with Image.open(jpeg_path) as image:
        image.convert("RGB").save(png_path, format="PNG", optimize=True)
    return {
        "capture_id": config["capture_id"],
        "directory": str(destination_root),
        "artifacts": statuses,
        "generated": [str(obj_path), str(mtl_path), str(png_path)],
        "proof_class": config["proof_class"],
    }

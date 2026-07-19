#!/usr/bin/env python3
"""Verify private release assets and remux browser-incompatible feeds for Studio."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sim2claw.paths import REPO_ROOT
from sim2claw.studio_private_releases import (
    PHYSICAL_REPLAY_MANIFEST,
    PHYSICAL_REPLAY_RELEASE_ROOT,
    STUDIO_INTEGRATION_RECEIPT,
    STUDIO_BROWSER_DERIVATIVE_KIND,
    verified_release_asset,
)


REMUX_TARGETS = {
    "replay-overhead-c922.mkv": "replay-overhead-c922.browser.mp4",
    "replay-side-logitech.mkv": "replay-side-logitech.browser.mp4",
    "replay-wrist-d405.mkv": "replay-wrist-d405.browser.mp4",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def prepare(ffmpeg: Path, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    executable = ffmpeg.expanduser().resolve(strict=True)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError(f"ffmpeg is not executable: {executable}")

    manifest = _read_json(repo_root / PHYSICAL_REPLAY_MANIFEST)
    specs = {
        str(row.get("name")): row
        for row in manifest.get("assets", [])
        if isinstance(row, dict) and row.get("name")
    }
    derivative_specs = {
        str(row.get("source_name")): row
        for row in manifest.get("assets", [])
        if isinstance(row, dict)
        and row.get("kind") == STUDIO_BROWSER_DERIVATIVE_KIND
        and row.get("source_name")
    }
    release_root = repo_root / PHYSICAL_REPLAY_RELEASE_ROOT
    ffmpeg_sha256 = _sha256(executable)
    version_result = subprocess.run(
        [str(executable), "-version"],
        capture_output=True,
        text=True,
        check=False,
    )
    version_line = version_result.stdout.splitlines()[0] if version_result.stdout else ""
    derived: list[dict[str, Any]] = []
    for source_name, output_name in REMUX_TARGETS.items():
        source = release_root / source_name
        source_spec = specs.get(source_name, {})
        derivative_spec = derivative_specs.get(source_name, {})
        if not verified_release_asset(source, source_spec, release_root=release_root):
            raise ValueError(f"release asset failed checksum verification: {source_name}")
        ffmpeg_identity = derivative_spec.get("ffmpeg_identity", {})
        expected_version = str(ffmpeg_identity.get("version") or "")
        if (
            derivative_spec.get("name") != output_name
            or derivative_spec.get("source_sha256") != source_spec.get("sha256")
            or derivative_spec.get("operation") != "container_remux_h264_copy_to_mp4"
            or ffmpeg_identity.get("executable_sha256") != ffmpeg_sha256
            or not version_line.startswith(f"ffmpeg version {expected_version} ")
        ):
            raise ValueError(
                f"tracked browser-derivative contract does not match producer: {output_name}"
            )
        output = release_root / output_name
        temporary = output.with_suffix(".tmp.mp4")
        temporary.unlink(missing_ok=True)
        command = [
            str(executable),
            "-v",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-c",
            "copy",
            "-map_metadata",
            "-1",
            "-movflags",
            "+faststart",
            str(temporary),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0 or not temporary.is_file():
            temporary.unlink(missing_ok=True)
            raise RuntimeError(
                f"ffmpeg remux failed for {source_name}: {result.stderr.strip()}"
            )
        derived_row = {
            "source_name": source_name,
            "source_sha256": source_spec.get("sha256"),
            "name": output_name,
            "size_bytes": temporary.stat().st_size,
            "sha256": _sha256(temporary),
            "operation": "container_remux_h264_copy_to_mp4",
        }
        if any(
            derived_row.get(field) != derivative_spec.get(field)
            for field in derived_row
        ):
            temporary.unlink(missing_ok=True)
            raise ValueError(
                f"browser derivative differs from tracked contract: {output_name}"
            )
        temporary.replace(output)
        derived.append(derived_row)

    receipt = {
        "schema_version": "sim2claw.studio_private_release_import.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "source_release_tag": manifest.get("release_tag"),
        "source_manifest_sha256": _sha256(repo_root / PHYSICAL_REPLAY_MANIFEST),
        "ffmpeg_sha256": ffmpeg_sha256,
        "derived_assets": derived,
        "authority": {
            "recorded_evidence_only": True,
            "task_success_verified": False,
            "training_admission_granted": False,
            "physical_authority_created": False,
        },
    }
    receipt_path = release_root / STUDIO_INTEGRATION_RECEIPT
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"receipt": str(receipt_path), "derived_assets": derived}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffmpeg", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.ffmpeg), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

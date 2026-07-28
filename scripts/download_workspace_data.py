#!/usr/bin/env python3
"""Download, verify, and hydrate the public sim2claw workspace-data release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPOSITORY = "jakekinchen/sim2claw"
DEFAULT_TAG = "workspace-data-20260728-v1"
MANIFEST_NAME = "WORKSPACE_DATA_MANIFEST.json"


def _request_json(url: str) -> dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "sim2claw-workspace-data-downloader",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub request failed ({exc.code}): {detail}") from exc


def _download(url: str, destination: Path) -> None:
    headers = {
        "Accept": "application/octet-stream",
        "User-Agent": "sim2claw-workspace-data-downloader",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    partial = destination.with_suffix(destination.suffix + ".partial")
    with urllib.request.urlopen(request) as response, partial.open("wb") as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)
    partial.replace(destination)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_tar_zst(archive: Path, destination: Path) -> None:
    if shutil.which("zstd") is None:
        raise RuntimeError(
            "zstd is required to hydrate .tar.zst assets. "
            "Install it with `brew install zstd` or your package manager."
        )
    if shutil.which("tar") is None:
        raise RuntimeError("tar is required to hydrate release assets.")
    destination.mkdir(parents=True, exist_ok=True)
    decompressor = subprocess.Popen(
        ["zstd", "--decompress", "--stdout", str(archive)],
        stdout=subprocess.PIPE,
    )
    assert decompressor.stdout is not None
    extractor = subprocess.run(
        ["tar", "-xf", "-", "-C", str(destination)],
        stdin=decompressor.stdout,
        check=False,
    )
    decompressor.stdout.close()
    decompressor_status = decompressor.wait()
    if decompressor_status != 0 or extractor.returncode != 0:
        raise RuntimeError(
            f"Failed to extract {archive.name}: "
            f"zstd={decompressor_status}, tar={extractor.returncode}"
        )


def _release_assets(tag: str) -> tuple[dict[str, Any], dict[str, str]]:
    release = _request_json(
        f"https://api.github.com/repos/{REPOSITORY}/releases/tags/{tag}"
    )
    urls = {
        asset["name"]: asset["browser_download_url"]
        for asset in release.get("assets", [])
    }
    return release, urls


def _load_manifest(
    tag: str, cache: Path, urls: dict[str, str]
) -> dict[str, Any]:
    if MANIFEST_NAME not in urls:
        raise RuntimeError(f"Release {tag} has no {MANIFEST_NAME} asset")
    manifest_path = cache / MANIFEST_NAME
    if not manifest_path.exists():
        _download(urls[MANIFEST_NAME], manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("release_tag") != tag:
        raise RuntimeError(
            f"Manifest tag {manifest.get('release_tag')!r} does not match {tag!r}"
        )
    return manifest


def _selected_components(
    manifest: dict[str, Any], requested: list[str]
) -> list[dict[str, Any]]:
    components = manifest.get("components", [])
    by_id = {component["id"]: component for component in components}
    unknown = sorted(set(requested) - set(by_id))
    if unknown:
        raise RuntimeError(
            f"Unknown component(s): {', '.join(unknown)}. "
            f"Choose from: {', '.join(sorted(by_id))}"
        )
    if not requested:
        return components
    return [by_id[component_id] for component_id in requested]


def _print_inventory(manifest: dict[str, Any]) -> None:
    print(f"Release: {manifest['release_tag']}")
    print(f"Source commit: {manifest['source_commit']}")
    print(f"Visibility: {manifest['repository_visibility']}")
    for component in manifest.get("components", []):
        total = sum(asset["bytes"] for asset in component.get("assets", []))
        print(
            f"{component['id']:32} "
            f"{len(component.get('assets', [])):3} assets "
            f"{total / (1024**2):9.1f} MiB  "
            f"{component['description']}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=DEFAULT_TAG)
    parser.add_argument(
        "--component",
        action="append",
        default=[],
        help="Component id to fetch; repeatable. Default: all components.",
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path("workspace-data-20260728"),
        help="Hydrated workspace-data destination.",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path(".cache/sim2claw-workspace-data"),
        help="Release-asset download cache.",
    )
    parser.add_argument("--list", action="store_true", help="List components only.")
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Download and verify without extracting archives.",
    )
    parser.add_argument(
        "--keep-archives",
        action="store_true",
        help="Keep verified archives after successful extraction.",
    )
    args = parser.parse_args()

    args.cache.mkdir(parents=True, exist_ok=True)
    _, urls = _release_assets(args.tag)
    manifest = _load_manifest(args.tag, args.cache, urls)
    if args.list:
        _print_inventory(manifest)
        return 0

    components = _selected_components(manifest, args.component)
    for component in components:
        print(f"[{component['id']}] {component['description']}")
        for asset in component.get("assets", []):
            name = asset["name"]
            if name not in urls:
                raise RuntimeError(f"Release is missing declared asset {name}")
            archive = args.cache / name
            if not archive.exists() or archive.stat().st_size != asset["bytes"]:
                print(f"  downloading {name} ({asset['bytes']} bytes)")
                _download(urls[name], archive)
            actual = _sha256(archive)
            if actual != asset["sha256"]:
                raise RuntimeError(
                    f"SHA-256 mismatch for {name}: {actual} != {asset['sha256']}"
                )
            print(f"  verified {name}")
            if not args.download_only and asset["format"] == "tar.zst":
                _extract_tar_zst(archive, args.destination)
                print(f"  hydrated {name} -> {args.destination}")
                if not args.keep_archives:
                    archive.unlink()

    print("Workspace data is checksum-verified.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, urllib.error.URLError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

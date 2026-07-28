#!/usr/bin/env python3
"""Validate and print the tracked IMG_5349 Studio registration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.img5349_registration import (
    REGISTRATION_CONTRACT,
    load_registration_contract,
    validated_studio_registration,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.repo_root.resolve()
    release_manifest = json.loads(
        (
            root / "docs/reference/IPHONE_VIDEO_3DGS_RELEASE_20260719.json"
        ).read_text(encoding="utf-8")
    )
    contract = load_registration_contract(root / REGISTRATION_CONTRACT)
    model_name = str(contract["source_binding"]["splat_name"])
    registration = validated_studio_registration(
        contract,
        release_manifest=release_manifest,
        model_name=model_name,
        model_sha256=str(contract["source_binding"]["splat_sha256"]),
    )
    print(json.dumps(registration, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

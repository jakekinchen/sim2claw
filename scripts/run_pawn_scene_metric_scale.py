#!/usr/bin/env python3
"""Run the IMG_5349 nominal-AprilTag scale-plausibility evaluator."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_scene_metric_scale import run_metric_scale_plausibility


ROBO_SCAN_ROOT_ENV = "SIM2CLAW_ROBO_SCAN_ROOT"


def _default_robo_scan_root() -> Path | None:
    value = os.environ.get(ROBO_SCAN_ROOT_ENV)
    return Path(value).expanduser() if value else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--robo-scan-root",
        type=Path,
        default=_default_robo_scan_root(),
        help=f"robo-scan checkout containing retained IMG_5349 assets (or set {ROBO_SCAN_ROOT_ENV})",
    )
    parser.add_argument(
        "--real-splat",
        type=Path,
        default=(
            REPO_ROOT
            / "artifacts"
            / "private"
            / "releases"
            / "img5349-3dgs-20260719"
            / "IMG_5349-primary-real-splat.ply"
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "outputs" / "pawn_scene_metric_scale_plausibility_v1",
    )
    args = parser.parse_args()
    if args.robo_scan_root is None:
        parser.error(f"--robo-scan-root is required unless {ROBO_SCAN_ROOT_ENV} is set")
    root = args.robo_scan_root.resolve()
    receipt = run_metric_scale_plausibility(
        frame_path=(
            root
            / "artifacts"
            / "private"
            / "IMG_5349-0079c19d-global-sfm-v1"
            / "images"
            / "frame-000001.jpg"
        ),
        source_video_path=root / "artifacts" / "incoming" / "IMG_5349" / "IMG_5349.MOV",
        real_splat_path=args.real_splat,
        output_root=args.output_root,
    )
    print(json.dumps(receipt["decision"], indent=2, sort_keys=True))
    print(args.output_root.resolve() / "metric_scale_plausibility_receipt.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

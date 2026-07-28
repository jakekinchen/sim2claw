#!/usr/bin/env python3
"""Run the action-free MuJoCo wrist-frustum pose grid."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.wrist_camera_pose_grid import search_wrist_camera_pose_grid


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate-manifest", type=Path)
    args = parser.parse_args()
    receipt = search_wrist_camera_pose_grid(
        output_path=args.output,
        candidate_manifest_path=args.candidate_manifest,
    )
    print(
        json.dumps(
            {
                "grid_candidate_count": receipt["grid_candidate_count"],
                "passed_candidate_count": receipt["passed_candidate_count"],
                "verdict": receipt["verdict"],
                "best_candidate": receipt["ranked_candidates"][0],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if receipt["verdict"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

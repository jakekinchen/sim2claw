#!/usr/bin/env python3
"""Build the phone-friendly Studio gallery for the strongest B--G replays."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.pawn_bg_grasp_gallery import (
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_SOURCE_RECEIPT,
    build_ranked_grasp_gallery,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-receipt", type=Path, default=DEFAULT_SOURCE_RECEIPT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--maximum-episodes", type=int, default=7)
    parser.add_argument("--task-id", default="pawn_bg_ranked_grasp_v3")
    parser.add_argument("--title", default="Top action-frozen pawn grasp replays")
    parser.add_argument("--claim-boundary")
    args = parser.parse_args()
    source_receipt = args.source_receipt.resolve()
    output_root = args.output_root.resolve()
    manifest = build_ranked_grasp_gallery(
        source_receipt_path=source_receipt,
        output_root=output_root,
        maximum_episode_count=args.maximum_episodes,
        task_id=args.task_id,
        title=args.title,
        claim_boundary=args.claim_boundary,
    )
    print(
        json.dumps(
            {
                "output": str(output_root / "gallery_manifest.json"),
                "selected": [
                    {
                        "rank": row["rank"],
                        "move": row["move_label"],
                        "outcome": row["relative_success_summary"],
                    }
                    for row in manifest["episodes"]
                ],
                "excluded_episode_count": manifest["ranking"][
                    "excluded_episode_count"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

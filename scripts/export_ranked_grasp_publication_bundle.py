#!/usr/bin/env python3
"""Export the ranked grasp gallery as tracked, phone-sized Studio assets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.pawn_bg_grasp_gallery import (
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_PUBLICATION_ROOT,
    export_ranked_grasp_publication_bundle,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-gallery-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--publication-root", type=Path, default=DEFAULT_PUBLICATION_ROOT)
    parser.add_argument("--publication-fps", type=float, default=10.0)
    parser.add_argument("--expected-episodes", type=int, default=7)
    args = parser.parse_args()
    manifest = export_ranked_grasp_publication_bundle(
        source_gallery_root=args.source_gallery_root,
        publication_root=args.publication_root,
        publication_fps=args.publication_fps,
        expected_episode_count=args.expected_episodes,
    )
    bundle = manifest["publication_bundle"]
    print(
        json.dumps(
            {
                "output": str(
                    (args.publication_root / "gallery_manifest.json").resolve()
                ),
                "episode_count": len(manifest["episodes"]),
                "publication_fps": bundle["publication_fps"],
                "scene_revision": bundle["scene_manifest_revision_sha256"],
                "source_actions_modified": bundle["source_actions_modified"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

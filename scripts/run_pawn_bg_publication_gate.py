#!/usr/bin/env python3
"""Build the retained-data B--G publication gate and summary figure."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_publication_gate import run_publication_gate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "outputs" / "pawn_bg_publication_gate_v1",
    )
    args = parser.parse_args()
    receipt = run_publication_gate(
        repository_root=REPO_ROOT, output_root=args.output_root
    )
    print(
        json.dumps(
            {
                "vector": receipt["frozen_vector"],
                "gates": receipt["gates"],
                "verdict": receipt["verdict"],
                "artifacts": receipt["artifacts"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    print(args.output_root.resolve() / "publication_gate_receipt.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

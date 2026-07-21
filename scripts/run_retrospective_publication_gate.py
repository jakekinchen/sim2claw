#!/usr/bin/env python3
"""Generate the deterministic retrospective publication receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.paths import REPO_ROOT
from sim2claw.retrospective_publication import DEFAULT_GATE_PATH, write_publication_receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", type=Path, default=DEFAULT_GATE_PATH)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "runs" / "publication-gate" / "retrospective_publication_receipt.json",
    )
    args = parser.parse_args()
    receipt = write_publication_receipt(
        args.output,
        gate_path=args.gate,
        repo_root=REPO_ROOT,
    )
    summary = {
        "output": str(args.output),
        "inventory": receipt["inventory"],
        "gates": {name: gate["status"] for name, gate in receipt["gates"].items()},
        "publication_verdict": receipt["publication_verdict"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

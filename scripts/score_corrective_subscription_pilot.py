#!/usr/bin/env python3
"""Score all committed subscription-pilot outputs and matched controls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.paths import REPO_ROOT
from sim2claw.subscription_pilot import score_materialized_subscription_pilot


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "runs" / "publication-gate" / "subscription-pilot",
    )
    args = parser.parse_args()
    summary = score_materialized_subscription_pilot(args.output_root)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

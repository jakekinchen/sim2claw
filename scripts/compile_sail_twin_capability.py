#!/usr/bin/env python3
"""Compile exact-scope TwinWorthiness capability and kill-switch evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.sail.capability_campaign import compile_campaign


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/sail/twin_capability_campaign_v1.json"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("outputs/sail/twin-capability-v1"),
    )
    args = parser.parse_args()
    print(
        json.dumps(
            compile_campaign(args.config, output_root=args.output_root),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

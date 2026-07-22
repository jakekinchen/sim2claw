#!/usr/bin/env python3
"""Run the preregistered action-frozen prospective simulator campaign."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.sail.prospective_simulator import run_campaign


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/sail/prospective_simulator_v1.json"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("outputs/sail/prospective-sim-v1"),
    )
    args = parser.parse_args()
    print(
        json.dumps(
            run_campaign(args.config, output_root=args.output_root),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

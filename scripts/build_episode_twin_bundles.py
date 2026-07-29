#!/usr/bin/env python3
"""Build the frozen EpisodeTwinBundle.v1 cohort artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.episode_twin_bundle import (
    CONTRACT_PATH,
    OUTPUT_DIRECTORY,
    build_episode_twin_bundles,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--output-directory", type=Path, default=OUTPUT_DIRECTORY)
    arguments = parser.parse_args()
    receipt = build_episode_twin_bundles(
        arguments.contract, arguments.output_directory
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

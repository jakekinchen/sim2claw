#!/usr/bin/env python3
"""Build a phase-language relabeling of an admitted GR00T training dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.groot_phase_language import build_phase_language_dataset


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    receipt = build_phase_language_dataset(args.source, args.destination)
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

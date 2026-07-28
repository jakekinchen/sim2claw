#!/usr/bin/env python3
"""Evaluate the frozen v2 registration fit split without opening held-out."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.bidirectional_registration_v2_fit import evaluate_fit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    receipt = evaluate_fit(args.annotations.resolve(), args.output.resolve())
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

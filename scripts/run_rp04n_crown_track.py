#!/usr/bin/env python3
"""Prepare or evaluate the frozen RP04N crown-track diagnostic."""

from __future__ import annotations

import argparse
import json

from sim2claw.rp04n_crown_track import evaluate, prepare_source_frames


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("prepare", "evaluate"))
    arguments = parser.parse_args()
    result = (
        prepare_source_frames()
        if arguments.phase == "prepare"
        else evaluate()
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

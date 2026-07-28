#!/usr/bin/env python3
"""Write the Q06 camera-bound scene safety receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.bidirectional_q06_scene_gate import evaluate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evaluate(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

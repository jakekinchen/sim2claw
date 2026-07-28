#!/usr/bin/env python3
"""Write the Q03 post-Fable held-out label-authority audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.bidirectional_registration_v4_label_audit import evaluate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = evaluate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Compile the receipt-bound post-Phase-1 project application verdict."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.sail.project_application import compile_project_application


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    receipt = compile_project_application(output_root=args.output_root)
    print(
        json.dumps(
            {
                "receipt_digest": receipt["receipt_digest"],
                "counts": receipt["counts"],
                "outcome": receipt["outcome"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

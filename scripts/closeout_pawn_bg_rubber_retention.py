#!/usr/bin/env python3
"""Materialize the action-frozen rubber-tip retention closeout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_rubber_retention import closeout_rubber_retention


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "outputs" / "pawn_bg_rubber_retention_closeout_v1",
    )
    args = parser.parse_args()
    output_root = args.output_root.resolve()
    receipt = closeout_rubber_retention(output_root=output_root)
    print(
        json.dumps(
            {
                "output": str(output_root / "rubber_retention_closeout_receipt.json"),
                "decision": receipt["decision"],
                "full_trace_guard": receipt["frozen_full_set_candidate"]["trace_guard"],
                "e2_to_e1_case": receipt["e2_to_e1_case"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

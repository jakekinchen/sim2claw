#!/usr/bin/env python3
"""Materialize the publication-safe grasp campaign closeout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_grasp_closeout import closeout_campaign


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "outputs" / "pawn_bg_grasp_campaign_closeout_v1",
    )
    args = parser.parse_args()
    receipt = closeout_campaign(output_root=args.output_root.resolve())
    print(
        json.dumps(
            {
                "output": str((args.output_root / "grasp_campaign_closeout_receipt.json").resolve()),
                "verified_wins": receipt["verified_wins"],
                "promotion_gate": receipt["promotion_gate"],
                "family_union": receipt["frozen_family_union"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

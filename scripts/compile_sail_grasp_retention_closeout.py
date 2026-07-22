#!/usr/bin/env python3
"""Compile the grasp-retention closeout receipt."""

from __future__ import annotations

import json

from sim2claw.sail.grasp_retention_closeout import compile_grasp_retention_closeout


def main() -> int:
    receipt = compile_grasp_retention_closeout()
    print(
        json.dumps(
            {
                "decision": receipt["decision"],
                "candidate_runs": receipt["candidate_runs"],
                "anchor_passes": receipt["anchor_passes"],
                "simulator_promotion": receipt["simulator_promotion"],
                "receipt_digest": receipt["receipt_digest"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

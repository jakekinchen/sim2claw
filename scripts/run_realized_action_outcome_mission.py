#!/usr/bin/env python3
"""Execute the frozen C6 mission replay exactly once."""

from __future__ import annotations

import json

from sim2claw.realized_action_outcome_mission import run_once


def main() -> int:
    print(json.dumps(run_once(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

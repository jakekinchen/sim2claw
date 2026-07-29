#!/usr/bin/env python3
"""Run the frozen realized-action first-divergence analysis."""

from __future__ import annotations

import json

from sim2claw.realized_action_first_divergence import analyze


def main() -> int:
    print(json.dumps(analyze(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

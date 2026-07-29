#!/usr/bin/env python3
"""Run the frozen C7 deterministic robustness challengers."""

from __future__ import annotations

import json

from sim2claw.realized_action_robustness import evaluate


def main() -> int:
    print(json.dumps(evaluate(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

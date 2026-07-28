#!/usr/bin/env python3
"""Build the local Q13 terminal-boundary viewer and receipt."""

from __future__ import annotations

import json

from sim2claw.bidirectional_terminal_evidence import build


def main() -> int:
    print(json.dumps(build(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

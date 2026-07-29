#!/usr/bin/env python3
"""Execute the single authorized coordinated-unloading shadow transaction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.coordinated_unloading_shadow_execution import execute


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    receipt = execute(
        packet_path=args.packet,
        authorization_path=args.authorization,
        output_root=args.output,
        operator_acknowledged=args.yes,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["telemetry_acceptance_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

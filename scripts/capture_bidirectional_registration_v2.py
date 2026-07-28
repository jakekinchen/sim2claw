#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.bidirectional_registration_v2_capture import (
    execute_registration_capture,
    review_capture_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review-only", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    if args.review_only:
        result = review_capture_plan(
            packet_path=args.packet,
            review_path=args.review,
        )
    else:
        result = execute_registration_capture(
            packet_path=args.packet,
            review_path=args.review,
            output_root=args.output,
            operator_acknowledged=args.yes,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

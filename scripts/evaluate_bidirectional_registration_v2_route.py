#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.bidirectional_registration_v2_route import evaluate_route


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--route", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate_route(route_path=args.route, output_root=args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["reviewer"]["decision"] == "CONTINUE" else 1


if __name__ == "__main__":
    raise SystemExit(main())

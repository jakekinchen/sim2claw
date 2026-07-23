#!/usr/bin/env python3
"""Run one guarded owner-directed base/inverse/base cycle in five minutes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.owner_directed_base_loop import (
    DEFAULT_DURATION_SECONDS,
    OwnerDirectedLoopError,
    build_loop_plan,
    run_owner_directed_base_loop,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=DEFAULT_DURATION_SECONDS,
        help="maximum wall-clock horizon; defaults to five minutes",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate all 12 source receipts and print the fixed plan without hardware",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="acknowledge that the powered follower workcell is currently clear",
    )
    parser.add_argument(
        "--owner-directed-unqualified-labels",
        action="store_true",
        help="use the fixed recording-folder mapping without promoting it as task evidence",
    )
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    try:
        if args.dry_run:
            result = build_loop_plan(
                repo_root,
                duration_seconds=args.duration_seconds,
            )
        else:
            result = run_owner_directed_base_loop(
                repo_root,
                operator_acknowledged=args.yes,
                owner_directed_unqualified_labels=args.owner_directed_unqualified_labels,
                duration_seconds=args.duration_seconds,
                progress=lambda row: print(
                    json.dumps(row, separators=(",", ":"), sort_keys=True),
                    flush=True,
                ),
            )
    except OwnerDirectedLoopError as error:
        print(
            json.dumps(
                {
                    "error": str(error),
                    "attempt_directory": (
                        str(error.attempt_directory)
                        if error.attempt_directory is not None
                        else None
                    ),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

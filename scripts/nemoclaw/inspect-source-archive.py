#!/usr/bin/env python3
"""Audit a hash-bound Git source archive before deployment extraction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.project_bundle import inspect_source_archive


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("expected_sha256")
    parser.add_argument("expected_revision")
    args = parser.parse_args()
    result = inspect_source_archive(
        args.archive,
        expected_sha256=args.expected_sha256,
        expected_revision=args.expected_revision,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

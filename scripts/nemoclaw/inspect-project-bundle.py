#!/usr/bin/env python3
"""Dependency-free sandbox entrypoint for pre-extraction bundle inspection."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sim2claw.project_bundle import inspect_bundle


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: inspect-project-bundle.py BUNDLE EXPECTED_SHA256 "
            "EXPECTED_SOURCE_REVISION"
        )
    report = inspect_bundle(Path(sys.argv[1]), expected_sha256=sys.argv[2])
    source_revision = report["source_revision"]
    if source_revision["git_head"] != sys.argv[3]:
        raise SystemExit("project bundle source revision does not match source archive")
    if source_revision["working_tree_clean"] is not True:
        raise SystemExit("project bundle source revision is not clean")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

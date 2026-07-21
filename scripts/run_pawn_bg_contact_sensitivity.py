#!/usr/bin/env python3
"""Run the frozen-prior B--G contact sensitivity ensemble."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_contact_sensitivity import run_contact_sensitivity


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root", type=Path,
        default=REPO_ROOT / "outputs" / "pawn_bg_contact_sensitivity_v1",
    )
    args = parser.parse_args()
    receipt = run_contact_sensitivity(
        source_repository_root=REPO_ROOT, output_root=args.output_root
    )
    print(json.dumps({
        "action_invariant": receipt["action_arrays_byte_identical_across_variants"],
        "summaries": receipt["summaries"],
        "decision": receipt["decision"],
    }, indent=2, sort_keys=True))
    print(args.output_root.resolve() / "contact_sensitivity_receipt.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

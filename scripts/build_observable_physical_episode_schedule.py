#!/usr/bin/env python3
"""Build the frozen physical visual-observation timestamp schedule."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.observable_physical_episode import (
    FRAME_OUTPUT_DIRECTORY,
    SCHEDULE_CONTRACT_PATH,
    SCHEDULE_OUTPUT_PATH,
    build_schedule_receipt,
    extract_schedule_frames,
    load_schedule_contract,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=SCHEDULE_CONTRACT_PATH)
    parser.add_argument("--output", type=Path, default=SCHEDULE_OUTPUT_PATH)
    parser.add_argument("--extract-frames", action="store_true")
    parser.add_argument(
        "--frame-output-directory",
        type=Path,
        default=FRAME_OUTPUT_DIRECTORY,
    )
    args = parser.parse_args()
    receipt = build_schedule_receipt(args.contract, args.output)
    result: dict[str, object] = {"schedule_receipt": receipt}
    if args.extract_frames:
        contract = load_schedule_contract(args.contract)
        result["frame_manifest"] = extract_schedule_frames(
            receipt,
            contract,
            args.frame_output_directory,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

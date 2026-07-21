#!/usr/bin/env python3
"""Generate current-dataset physical command-versus-measured comparisons."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.paths import REPO_ROOT
from sim2claw.physical_telemetry import (
    DEFAULT_CONTRACT_PATH,
    materialize_physical_telemetry,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "runs" / "physical-telemetry-trace-v1",
    )
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    result = materialize_physical_telemetry(
        args.output_root,
        contract_path=args.contract,
        repo_root=REPO_ROOT,
        render_plots=not args.no_plots,
    )
    print(
        json.dumps(
            {
                "output_root": str(args.output_root),
                "corpus_comparison": str(
                    args.output_root / "physical_telemetry_corpus_comparison.json"
                ),
                "aggregate_csv": str(
                    args.output_root / "aggregate_joint_comparison.csv"
                ),
                "episode_count": result["episode_count"],
                "sample_count": result["sample_count"],
                "endpoint_frame_count": result["endpoint_frame_count"],
                "episode_outcome_counts": result["episode_outcome_counts"],
                "real_vs_sim": result["comparison_scope"]["real_vs_sim"],
                "provider_calls": 0,
                "physical_actions": 0,
                "corpus_comparison_sha256": result[
                    "corpus_comparison_sha256"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

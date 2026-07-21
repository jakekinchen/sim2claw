#!/usr/bin/env python3
"""Materialize the frozen subscription pilot without calling any model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.paths import REPO_ROOT
from sim2claw.subscription_pilot import (
    DEFAULT_CAMPAIGN_PATH,
    materialize_subscription_pilot,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", type=Path, default=DEFAULT_CAMPAIGN_PATH)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "runs" / "publication-gate" / "subscription-pilot",
    )
    args = parser.parse_args()
    manifest = materialize_subscription_pilot(
        args.output_root,
        campaign_path=args.campaign,
        repo_root=REPO_ROOT,
    )
    readiness = manifest["readiness"]
    print(
        json.dumps(
            {
                "manifest": str(args.output_root / "subscription_pilot_manifest.json"),
                "campaign_id": manifest["campaign_id"],
                "dry_run": manifest["dry_run"],
                "job_count": len(manifest["jobs"]),
                "case_attempt_count": readiness["case_attempt_count"],
                "subscription_case_attempt_count": readiness[
                    "subscription_case_attempt_count"
                ],
                "paid_api_case_attempt_count": readiness["paid_api_case_attempt_count"],
                "estimated_open_model_maximum_cost_usd": readiness[
                    "estimated_open_model_maximum_cost_usd"
                ],
                "campaign_maximum_incremental_cost_usd": readiness[
                    "campaign_maximum_incremental_cost_usd"
                ],
                "execution_ready": readiness["execution_ready"],
                "execution_blockers": readiness["execution_blockers"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

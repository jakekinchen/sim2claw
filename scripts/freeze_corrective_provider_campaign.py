#!/usr/bin/env python3
"""Validate and materialize the no-secrets, dry-run provider campaign."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.learning_factory_artifacts import atomic_write_json
from sim2claw.paths import REPO_ROOT
from sim2claw.retrospective_publication import build_provider_campaign_manifest


DEFAULT_CAMPAIGN = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "sim2claw_corrective_provider_campaign_v1.json"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", type=Path, default=DEFAULT_CAMPAIGN)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "runs" / "publication-gate" / "corrective_provider_campaign_manifest.json",
    )
    args = parser.parse_args()
    manifest = build_provider_campaign_manifest(
        campaign_path=args.campaign,
        repo_root=REPO_ROOT,
    )
    for job in manifest["jobs"]:
        config_path = REPO_ROOT / job["generate_config_path"]
        atomic_write_json(config_path, job["generate_config"])
    atomic_write_json(args.output, manifest)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "campaign_id": manifest["campaign_id"],
                "dry_run": manifest["dry_run"],
                "job_count": manifest["job_count"],
                "case_attempt_count": manifest["case_attempt_count"],
                "execution_ready": manifest["readiness"]["execution_ready"],
                "execution_blockers": manifest["readiness"]["execution_blockers"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

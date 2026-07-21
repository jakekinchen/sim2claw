#!/usr/bin/env python3
"""Materialize fixed-data interaction candidates and evidence artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.interaction_events import (
    DEFAULT_CONTRACT_PATH,
    materialize_interaction_event_pipeline,
)
from sim2claw.paths import REPO_ROOT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "runs" / "fixed-data-event-pipeline-v1" / "train",
    )
    parser.add_argument(
        "--partition", choices=("train", "held_out", "all"), default="train"
    )
    parser.add_argument("--evaluator-owned", action="store_true")
    parser.add_argument("--no-visuals", action="store_true")
    args = parser.parse_args()
    corpus = materialize_interaction_event_pipeline(
        args.output_root,
        partition=args.partition,
        evaluator_owned=args.evaluator_owned,
        render_visuals=not args.no_visuals,
        contract_path=args.contract,
        repo_root=REPO_ROOT,
    )
    print(
        json.dumps(
            {
                "output_root": str(args.output_root.resolve()),
                "partition": corpus["partition"],
                "episode_count": corpus["episode_count"],
                "sample_count": corpus["sample_count"],
                "event_candidate_count": corpus["event_candidate_count"],
                "visual_strip_count": corpus["visual_strip_count"],
                "corpus_sha256": corpus["corpus_sha256"],
                "provider_calls": corpus["provider_calls"],
                "physical_actions": corpus["physical_actions"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

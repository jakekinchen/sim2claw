#!/usr/bin/env python3
"""Run the six-case GapBench lifecycle without a model provider."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from evals.inspect_gapbench.dataset import public_sources, sealed_sources
from sim2claw.gapbench_contracts import CAMPAIGN_SCHEMA, freeze_public_case
from sim2claw.gapbench_evaluator import SCORE_WEIGHTS, SealedEvaluator
from sim2claw.gapbench_tools import GapBenchSession
from sim2claw.learning_factory_artifacts import atomic_write_json, canonical_digest


def _hypotheses(family: str) -> list[dict[str, Any]]:
    return [
        {
            "rank": 1,
            "mechanism": family,
            "evidence": "The public residual direction and active diagnostic agree.",
            "discriminating_prediction": "Correcting this mechanism reduces development and held-out residuals.",
            "uncertainty": 0.1,
            "abstain": False,
        }
    ]


def run_fixture(
    output_root: Path,
    *,
    sealed_source: Path | None = None,
) -> dict[str, Any]:
    public = public_sources()
    sealed = sealed_sources(sealed_source)
    attempts: list[dict[str, Any]] = []
    for case_id in sorted(public):
        for treatment in ("baseline_control", "oracle_repair"):
            attempt_root = output_root / treatment / case_id
            packet_root = attempt_root / "packet"
            freeze_public_case(public[case_id], packet_root)
            session = GapBenchSession(
                packet_root,
                SealedEvaluator(sealed[case_id]),
                attempt_root / "state",
                reset=True,
            )
            family = str(sealed[case_id]["fault_family"])
            session.submit_hypotheses(case_id, _hypotheses(family))
            probe = session.request_probe(case_id, "phase_alignment_probe")
            parameters = (
                public[case_id]["baseline_candidate"]["parameters"]
                if treatment == "baseline_control"
                else sealed[case_id]["target_parameters"]
            )
            candidate_ref = "candidate/proposal.json"
            atomic_write_json(packet_root / candidate_ref, {"parameters": parameters})
            development = session.run_public_evaluation(case_id, candidate_ref)
            receipt = session.submit_candidate(
                case_id,
                candidate_ref,
                {
                    "fault_family": family,
                    "uncertainty": 0.1,
                    "heldout_consequence": "Residuals should fall without changing guarded rows.",
                },
                "synthetic_only",
            )
            attempts.append({
                "case_id": case_id,
                "treatment": treatment,
                "probe_receipt_sha256": probe["receipt_sha256"],
                "public_receipt_sha256": development["receipt_sha256"],
                "score_receipt_sha256": receipt["receipt_sha256"],
                "aggregate_score": receipt["aggregate_score"],
                "scores": receipt["scores"],
            })

    controls = {row["case_id"]: row for row in attempts if row["treatment"] == "baseline_control"}
    repairs = {row["case_id"]: row for row in attempts if row["treatment"] == "oracle_repair"}
    all_improved = all(repairs[case_id]["aggregate_score"] > controls[case_id]["aggregate_score"] for case_id in controls)
    unsigned = {
        "schema_version": CAMPAIGN_SCHEMA,
        "campaign_id": "sim2claw-gapbench-local-fixture-v1",
        "proof_class": "synthetic_benchmark",
        "runner": "deterministic_fixture_not_model_benchmark",
        "case_count": len(public),
        "attempt_count": len(attempts),
        "score_weights_sha256": canonical_digest(SCORE_WEIGHTS),
        "oracle_repairs_outscore_controls": all_improved,
        "provider_calls": 0,
        "physical_actions": 0,
        "promotion_authority": False,
        "attempts": attempts,
    }
    summary = {**unsigned, "campaign_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_root / "campaign_summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("runs/gapbench/local-fixture-v1"))
    parser.add_argument(
        "--sealed-source",
        type=Path,
        help="trusted-host sealed case JSON (otherwise use SIM2CLAW_GAPBENCH_SEALED_SOURCE)",
    )
    args = parser.parse_args()
    summary = run_fixture(
        args.output,
        sealed_source=args.sealed_source,
    )
    print(f"cases={summary['case_count']}")
    print(f"attempts={summary['attempt_count']}")
    print(f"oracle_repairs_outscore_controls={str(summary['oracle_repairs_outscore_controls']).lower()}")
    print(f"campaign_sha256={summary['campaign_sha256']}")
    return 0 if summary["oracle_repairs_outscore_controls"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

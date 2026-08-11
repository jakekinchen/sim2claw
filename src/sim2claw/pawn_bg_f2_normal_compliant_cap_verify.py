"""Independent source-boundary compatibility and strict task verifier for OR137."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT
from .pawn_bg_f2_deformable_cap import TRACE_SCHEMA
from .pawn_bg_f2_deformable_cap_source_boundary_verify import _compatibility_gate
from .pawn_bg_f2_deformable_cap_verify import (
    _load_trace,
    _source_episode,
    verify_trace as verify_strict_trace,
)
from .pawn_bg_f2_normal_compliant_cap import CONTRACT_PATH, SCHEMA, load_contract


VERDICT_SCHEMA = "sim2claw.pawn_bg_f2_normal_compliant_cap_task_verdict.v1"


def verify_trace(
    *, trace_path: Path, metadata_path: Path, contract_path: Path = CONTRACT_PATH
) -> dict:
    contract = load_contract(contract_path)
    arrays, metadata = _load_trace(trace_path, metadata_path, expected_schema=TRACE_SCHEMA)
    source = _source_episode(contract)
    strict = verify_strict_trace(
        trace_path=trace_path,
        metadata_path=metadata_path,
        contract_path=contract_path,
        contract_schema=SCHEMA,
        trace_schema=TRACE_SCHEMA,
        verdict_schema="sim2claw.pawn_bg_f2_normal_compliant_cap_strict_verdict.v1",
        verifier_path=Path(__file__),
        applied_control_excluded_phase_codes=frozenset({0}),
        contract_payload=contract,
    )
    candidate_id = str(strict["candidate_id"])
    is_rigid = candidate_id == "rigid_legacy_shoulder_control"
    compatibility = (
        _compatibility_gate(
            contract=contract,
            arrays=arrays,
            metadata=metadata,
            source_timestamps=source["timestamps"],
            strict_verdict=strict,
        )
        if is_rigid
        else None
    )
    compatibility_passed = None if compatibility is None else bool(compatibility["passed"])
    strict_passed = bool(strict["passed"])
    passed = compatibility_passed if is_rigid else strict_passed
    decision = {
        "candidate_id": candidate_id,
        "compatibility_passed": compatibility_passed,
        "strict_replay_passed": strict_passed,
        "strict_gate_digest": strict["gate_digest"],
        "compatibility": compatibility,
    }
    return {
        "schema_version": VERDICT_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "candidate_id": candidate_id,
        "passed": bool(passed),
        "compatibility_passed": compatibility_passed,
        "strict_replay_passed": strict_passed,
        "compatibility": compatibility,
        "strict_gate_results": strict["gate_results"],
        "strict_metrics": strict["metrics"],
        "strict_gate_digest": strict["gate_digest"],
        "decision_digest": canonical_digest(decision),
        "verifier": {
            "path": str(Path(__file__).resolve().relative_to(REPO_ROOT)),
            "sha256": sha256_file(Path(__file__).resolve()),
            "producer_booleans_read": False,
            "source_action_schedule_and_boundaries_reconstructed": True,
            "strict_full_step_metrics_unchanged": True,
        },
        "inputs": {
            "contract_path": str(contract_path.relative_to(REPO_ROOT)),
            "contract_sha256": sha256_file(contract_path),
            "trace_path": str(trace_path.relative_to(REPO_ROOT)),
            "trace_sha256": sha256_file(trace_path),
            "metadata_path": str(metadata_path.relative_to(REPO_ROOT)),
            "metadata_sha256": sha256_file(metadata_path),
        },
        "authority": contract["authority"],
        "claim_boundary": contract["claim_boundary"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    args = parser.parse_args(argv)
    verdict = verify_trace(
        trace_path=args.trace.resolve(),
        metadata_path=args.metadata.resolve(),
        contract_path=args.contract.resolve(),
    )
    atomic_write_json(args.output.resolve(), verdict)
    print(
        json.dumps(
            {
                "candidate_id": verdict["candidate_id"],
                "compatibility_passed": verdict["compatibility_passed"],
                "strict_replay_passed": verdict["strict_replay_passed"],
                "decision_digest": verdict["decision_digest"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["verify_trace"]

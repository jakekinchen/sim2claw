"""Independent OR135 compatibility and strict replay verifier."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT
from .pawn_bg_f2_deformable_cap import TRACE_SCHEMA
from .pawn_bg_f2_deformable_cap_compatibility import CONTRACT_PATH, SCHEMA
from .pawn_bg_f2_deformable_cap_verify import verify_trace as verify_strict_trace


VERDICT_SCHEMA = "sim2claw.pawn_bg_f2_deformable_cap_compatibility_verdict.v1"


class CompatibilityVerifierError(RuntimeError):
    """The OR135 trace cannot be admitted by the independent evaluator."""


def _compatibility_gate(
    *,
    contract: Mapping[str, Any],
    metadata: Mapping[str, Any],
    strict_verdict: Mapping[str, Any],
) -> dict[str, Any]:
    reference = contract["rigid_compatibility_reference"]
    tolerances = contract["rigid_compatibility_tolerances"]
    metrics = strict_verdict["metrics"]
    original = metrics["original_reward_gate_results_recomputed"]
    observed = {
        "compiled_model_sha256": metadata["compiled_model_sha256"],
        "final_target_distance_m": float(metrics["final_center_distance_m"]),
        "maximum_piece_rise_m": float(metrics["maximum_rise_m"]),
        "piece_lifted": bool(original["piece_lifted"]),
        "qualified_bilateral_contact_observed": bool(
            metrics["maximum_qualified_contact_dwell_seconds"] > 0.0
        ),
        "upright": bool(original["upright"]),
    }
    checks = {
        "compiled_model_identity": observed["compiled_model_sha256"]
        == reference["compiled_model_sha256"],
        "final_target_distance": abs(
            observed["final_target_distance_m"]
            - float(reference["final_target_distance_m"])
        )
        <= float(tolerances["final_target_distance_absolute_m"]),
        "maximum_piece_rise": abs(
            observed["maximum_piece_rise_m"]
            - float(reference["maximum_piece_rise_m"])
        )
        <= float(tolerances["maximum_piece_rise_absolute_m"]),
        "piece_lifted": observed["piece_lifted"] is reference["piece_lifted"],
        "qualified_bilateral_contact": observed[
            "qualified_bilateral_contact_observed"
        ]
        is reference["qualified_bilateral_contact_observed"],
        "upright": observed["upright"] is reference["upright"],
    }
    return {"passed": all(checks.values()), "checks": checks, "observed": observed}


def verify_trace(
    *,
    trace_path: Path,
    metadata_path: Path,
    contract_path: Path = CONTRACT_PATH,
) -> dict[str, Any]:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("schema_version") != SCHEMA:
        raise CompatibilityVerifierError("unexpected OR135 contract schema")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    strict = verify_strict_trace(
        trace_path=trace_path,
        metadata_path=metadata_path,
        contract_path=contract_path,
        contract_schema=SCHEMA,
        trace_schema=TRACE_SCHEMA,
        verdict_schema=(
            "sim2claw.pawn_bg_f2_deformable_cap_compatibility_strict_verdict.v1"
        ),
        verifier_path=Path(__file__),
        applied_control_excluded_phase_codes=frozenset({0}),
    )
    candidate_id = str(strict["candidate_id"])
    is_rigid = candidate_id == "rigid_legacy_shoulder_control"
    compatibility = (
        _compatibility_gate(
            contract=contract,
            metadata=metadata,
            strict_verdict=strict,
        )
        if is_rigid
        else None
    )
    compatibility_passed = None if compatibility is None else compatibility["passed"]
    strict_passed = bool(strict["passed"])
    admitted_pass = bool(compatibility_passed) if is_rigid else strict_passed
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
        "passed": admitted_pass,
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
            "source_action_and_schedule_reconstructed": True,
            "initial_state_phase_excluded_from_applied_action_equality": True,
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


__all__ = ["CompatibilityVerifierError", "verify_trace"]

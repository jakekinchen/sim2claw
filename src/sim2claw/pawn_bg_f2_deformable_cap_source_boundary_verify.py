"""Independent OR136 source-boundary compatibility and strict verifier."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT
from .pawn_bg_f2_deformable_cap import TRACE_SCHEMA, _array_sha256
from .pawn_bg_f2_deformable_cap_source_boundary import (
    CONTRACT_PATH,
    SCHEMA,
    load_contract,
)
from .pawn_bg_f2_deformable_cap_verify import (
    _load_trace,
    _source_episode,
    verify_trace as verify_strict_trace,
)


VERDICT_SCHEMA = "sim2claw.pawn_bg_f2_deformable_cap_source_boundary_verdict.v1"


class SourceBoundaryVerifierError(RuntimeError):
    """The OR136 trace or source-boundary reconstruction is inadmissible."""


def source_boundary_rows(
    *,
    trace_time: np.ndarray,
    source_timestamps: np.ndarray,
    timestep_seconds: float,
    reconstruction: Mapping[str, Any],
) -> dict[str, np.ndarray]:
    if len(source_timestamps) != 440:
        raise SourceBoundaryVerifierError("source timestamp row count drifted")
    if len(trace_time) != int(reconstruction["full_trace_step_count"]):
        raise SourceBoundaryVerifierError("full trace step count drifted")
    counts = np.asarray(
        [
            max(
                1,
                int(
                    round(
                        float(
                            (source_timestamps[index + 1] - source_timestamps[index])
                            / timestep_seconds
                        )
                    )
                ),
            )
            for index in range(len(source_timestamps) - 1)
        ],
        dtype=np.int64,
    )
    boundaries = np.concatenate(
        (np.asarray([0], dtype=np.int64), np.cumsum(counts, dtype=np.int64))
    )
    legacy_rows = np.concatenate(
        (boundaries, np.asarray([len(trace_time) - 1], dtype=np.int64))
    )
    checks = {
        "interval_count": len(counts) == int(reconstruction["interval_count"]),
        "interval_step_count_sum": int(counts.sum())
        == int(reconstruction["interval_step_count_sum"]),
        "terminal_step_count": len(trace_time) - 1 - int(boundaries[-1])
        == int(reconstruction["terminal_step_count"]),
        "action_boundary_row_count": len(boundaries)
        == int(reconstruction["action_boundary_row_count"]),
        "action_boundary_last_index": int(boundaries[-1])
        == int(reconstruction["action_boundary_last_index"]),
        "legacy_row_count": len(legacy_rows)
        == int(reconstruction["legacy_row_count_including_terminal"]),
        "legacy_terminal_index": int(legacy_rows[-1])
        == int(reconstruction["legacy_terminal_index"]),
        "interval_step_counts_sha256": _array_sha256(counts)
        == reconstruction["interval_step_counts_sha256"],
        "action_boundary_indices_sha256": _array_sha256(boundaries)
        == reconstruction["action_boundary_indices_sha256"],
        "legacy_rows_sha256": _array_sha256(legacy_rows)
        == reconstruction["legacy_rows_including_terminal_sha256"],
    }
    if not all(checks.values()):
        failed = sorted(key for key, value in checks.items() if not value)
        raise SourceBoundaryVerifierError(
            f"source-boundary reconstruction drifted: {failed}"
        )
    return {
        "interval_step_counts": counts,
        "action_boundary_indices": boundaries,
        "legacy_rows": legacy_rows,
    }


def _compatibility_gate(
    *,
    contract: Mapping[str, Any],
    arrays: Mapping[str, np.ndarray],
    metadata: Mapping[str, Any],
    source_timestamps: np.ndarray,
    strict_verdict: Mapping[str, Any],
) -> dict[str, Any]:
    rows = source_boundary_rows(
        trace_time=arrays["time"],
        source_timestamps=source_timestamps,
        timestep_seconds=float(metadata["timestep_seconds"]),
        reconstruction=contract["source_boundary_reconstruction"],
    )
    legacy_rows = rows["legacy_rows"]
    rise = (
        arrays["selected_position"][:, 2]
        - float(arrays["selected_position"][0, 2])
    )
    source_boundary_rise = float(np.max(rise[legacy_rows]))
    full_step_rise = float(np.max(rise))
    strict_metrics = strict_verdict["metrics"]
    strict_original = strict_metrics["original_reward_gate_results_recomputed"]
    reference = contract["rigid_compatibility_reference"]
    tolerances = contract["rigid_compatibility_tolerances"]
    observed = {
        "compiled_model_sha256": metadata["compiled_model_sha256"],
        "final_target_distance_m": float(strict_metrics["final_center_distance_m"]),
        "maximum_piece_rise_source_boundary_m": source_boundary_rise,
        "maximum_piece_rise_full_step_m": full_step_rise,
        "piece_lifted_source_boundary": source_boundary_rise >= 0.04,
        "qualified_bilateral_contact_observed": bool(
            strict_metrics["maximum_qualified_contact_dwell_seconds"] > 0.0
        ),
        "upright_terminal": bool(strict_original["upright"]),
    }
    checks = {
        "compiled_model_identity": observed["compiled_model_sha256"]
        == reference["compiled_model_sha256"],
        "final_target_distance": abs(
            observed["final_target_distance_m"]
            - float(reference["final_target_distance_m"])
        )
        <= float(tolerances["final_target_distance_absolute_m"]),
        "maximum_piece_rise_source_boundary": abs(
            observed["maximum_piece_rise_source_boundary_m"]
            - float(reference["maximum_piece_rise_source_boundary_m"])
        )
        <= float(tolerances["maximum_piece_rise_source_boundary_absolute_m"]),
        "piece_lifted_source_boundary": observed["piece_lifted_source_boundary"]
        is reference["piece_lifted_source_boundary"],
        "qualified_bilateral_contact": observed[
            "qualified_bilateral_contact_observed"
        ]
        is reference["qualified_bilateral_contact_observed"],
        "upright_terminal": observed["upright_terminal"]
        is reference["upright_terminal"],
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "observed": observed,
        "row_identities": {
            "interval_step_counts_sha256": _array_sha256(
                rows["interval_step_counts"]
            ),
            "action_boundary_indices_sha256": _array_sha256(
                rows["action_boundary_indices"]
            ),
            "legacy_rows_including_terminal_sha256": _array_sha256(legacy_rows),
        },
    }


def verify_trace(
    *,
    trace_path: Path,
    metadata_path: Path,
    contract_path: Path = CONTRACT_PATH,
) -> dict[str, Any]:
    contract = load_contract(contract_path)
    arrays, metadata = _load_trace(
        trace_path, metadata_path, expected_schema=TRACE_SCHEMA
    )
    source = _source_episode(contract)
    strict = verify_strict_trace(
        trace_path=trace_path,
        metadata_path=metadata_path,
        contract_path=contract_path,
        contract_schema=SCHEMA,
        trace_schema=TRACE_SCHEMA,
        verdict_schema=(
            "sim2claw.pawn_bg_f2_deformable_cap_source_boundary_strict_verdict.v1"
        ),
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


__all__ = [
    "SourceBoundaryVerifierError",
    "source_boundary_rows",
    "verify_trace",
]

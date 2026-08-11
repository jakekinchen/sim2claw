"""Independent strict verifier and contact-height diagnosis for OR146."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT
from .pawn_bg_c2_strict_baseline import CONTRACT_PATH, SCHEMA, load_contract
from .pawn_bg_f2_deformable_cap import TRACE_SCHEMA
from .pawn_bg_f2_deformable_cap_verify import (
    _load_trace,
    _quaternion_tilt_degrees,
    verify_trace as verify_strict_trace,
)


VERDICT_SCHEMA = "sim2claw.pawn_bg_c2_strict_baseline_verdict.v1"


def _contact_diagnosis(
    arrays: Mapping[str, np.ndarray], metadata: Mapping[str, Any]
) -> dict[str, Any]:
    geom_body_ids = np.asarray(metadata["geom_body_ids"], dtype=np.int32)
    selected_body = int(metadata["selected_body_id"])
    fixed = set(int(value) for value in metadata["fixed_jaw_body_ids"])
    moving = set(int(value) for value in metadata["moving_jaw_body_ids"])
    piece_by_body = {
        int(body_id): str(name)
        for body_id, name in zip(metadata["piece_body_ids"], metadata["piece_names"])
    }
    selected_rows: dict[str, list[dict[str, Any]]] = {"fixed": [], "moving": []}
    wrong: dict[str, set[int]] = {}
    for contact_index, step in enumerate(arrays["contact_step"]):
        geom_pair = arrays["contact_geom"][contact_index]
        if np.any(geom_pair < 0):
            continue
        body_pair = [int(geom_body_ids[int(value)]) for value in geom_pair]
        for jaw_side, jaw_bodies in (("fixed", fixed), ("moving", moving)):
            if selected_body in body_pair and any(body in jaw_bodies for body in body_pair):
                selected_rows[jaw_side].append(
                    {
                        "step": int(step),
                        "time_s": float(arrays["time"][int(step)]),
                        "height_relative_selected_center_m": float(
                            arrays["contact_pos"][contact_index, 2]
                            - arrays["selected_position"][int(step), 2]
                        ),
                    }
                )
        robot = any(body in fixed or body in moving for body in body_pair)
        for body in body_pair:
            name = piece_by_body.get(body)
            if robot and name is not None and body != selected_body:
                wrong.setdefault(name, set()).add(int(step))

    def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
        heights = [row["height_relative_selected_center_m"] for row in rows]
        steps = [row["step"] for row in rows]
        return {
            "contact_count": len(rows),
            "first_step": min(steps) if steps else None,
            "last_step": max(steps) if steps else None,
            "minimum_height_relative_selected_center_m": min(heights) if heights else None,
            "maximum_height_relative_selected_center_m": max(heights) if heights else None,
        }

    tilt = _quaternion_tilt_degrees(arrays["selected_quaternion_wxyz"])
    over = np.flatnonzero(tilt > 10.0)
    maximum_step = int(np.argmax(tilt))
    return {
        "selected_contact_height_by_jaw": {
            side: summarize(rows) for side, rows in selected_rows.items()
        },
        "wrong_pawn_contact_steps": {
            name: {
                "step_count": len(steps),
                "first_step": min(steps),
                "last_step": max(steps),
            }
            for name, steps in sorted(wrong.items())
        },
        "continuous_upright": {
            "threshold_degrees": 10.0,
            "first_failure_step": int(over[0]) if len(over) else None,
            "first_failure_time_s": (
                float(arrays["time"][int(over[0])]) if len(over) else None
            ),
            "maximum_tilt_degrees": float(tilt[maximum_step]),
            "maximum_tilt_step": maximum_step,
            "maximum_tilt_time_s": float(arrays["time"][maximum_step]),
        },
    }


def verify_trace(
    *, trace_path: Path, metadata_path: Path, contract_path: Path = CONTRACT_PATH
) -> dict[str, Any]:
    contract = load_contract(contract_path)
    arrays, metadata = _load_trace(
        trace_path, metadata_path, expected_schema=TRACE_SCHEMA
    )
    strict = verify_strict_trace(
        trace_path=trace_path,
        metadata_path=metadata_path,
        contract_path=contract_path,
        contract_schema=SCHEMA,
        trace_schema=TRACE_SCHEMA,
        verdict_schema="sim2claw.pawn_bg_c2_strict_baseline_strict_verdict.v1",
        verifier_path=Path(__file__),
        applied_control_excluded_phase_codes=frozenset({0}),
        contract_payload=contract,
    )
    diagnosis = _contact_diagnosis(arrays, metadata)
    decision = {
        "candidate_id": strict["candidate_id"],
        "strict_replay_passed": bool(strict["passed"]),
        "strict_gate_digest": strict["gate_digest"],
        "contact_diagnosis": diagnosis,
    }
    return {
        "schema_version": VERDICT_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "candidate_id": strict["candidate_id"],
        "passed": bool(strict["passed"]),
        "strict_replay_passed": bool(strict["passed"]),
        "strict_gate_results": strict["gate_results"],
        "strict_metrics": strict["metrics"],
        "strict_gate_digest": strict["gate_digest"],
        "contact_diagnosis": diagnosis,
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
                "strict_replay_passed": verdict["strict_replay_passed"],
                "decision_digest": verdict["decision_digest"],
                "maximum_tilt_degrees": verdict["strict_metrics"][
                    "maximum_tilt_degrees"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["_contact_diagnosis", "verify_trace"]

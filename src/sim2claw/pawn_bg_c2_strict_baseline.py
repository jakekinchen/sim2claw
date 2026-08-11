"""Produce one full-step C2-to-C1 exact-action baseline trace for OR146."""

from __future__ import annotations

import argparse
import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT
from .pawn_bg_f2_deformable_cap import FullStepTraceCollector
from .pawn_bg_f2_deformable_cap_compatibility import legacy_shoulder_spec_mutator
from .pawn_bg_f2_normal_compliant_cap import load_contract as load_or140_contract
from .pawn_bg_grasp_coordinate_descent import run_grasp_episode_probe


CONTRACT_PATH = REPO_ROOT / "configs" / "evaluations" / "pawn_bg_c2_strict_baseline_v1.json"
OUTPUT_ROOT = REPO_ROOT / "outputs" / "pawn_bg_c2_strict_baseline_v1"
SCHEMA = "sim2claw.pawn_bg_c2_strict_baseline.v1"
PRODUCER_SCHEMA = "sim2claw.pawn_bg_c2_strict_baseline_producer.v1"


class C2StrictBaselineError(RuntimeError):
    """The frozen C2 baseline cannot run after provenance drift."""


def _validate_binding(binding: Mapping[str, Any]) -> None:
    path = REPO_ROOT / str(binding["path"])
    if not path.is_file() or sha256_file(path) != str(binding["sha256"]):
        raise C2StrictBaselineError(f"source binding drifted: {binding['path']}")


def load_raw_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != SCHEMA:
        raise C2StrictBaselineError("unexpected OR146 schema")
    _validate_binding(raw["authorization"])
    _validate_binding(raw["base_contract"])
    for binding in raw["source_bindings"].values():
        if isinstance(binding, Mapping) and {"path", "sha256"} <= set(binding):
            _validate_binding(binding)
    for binding in raw["implementation_bindings"].values():
        _validate_binding(binding)
    if any(raw.get("authority", {}).values()):
        raise C2StrictBaselineError("OR146 authority widened")
    if raw["action_invariance"] != {
        "shape": [527, 6],
        "dtype": "float64",
        "c_contiguous": True,
        "joint_order": [
            "shoulder_pan",
            "shoulder_lift",
            "elbow_flex",
            "wrist_flex",
            "wrist_roll",
            "gripper",
        ],
        "per_joint_zoh_delay_seconds": [0.11] * 6,
        "clipped_rows": 0,
        "initial_state_phase_is_not_an_applied_action_step": True,
        "no_ik_offsets_clipping_retiming_smoothing_suffix_or_override": True,
        "no_measured_state_replay_latch_load_hold_or_force_ramp": True,
    }:
        raise C2StrictBaselineError("C2 action invariance drifted")
    if [row["candidate_id"] for row in raw["candidate_order"]] != [
        "c2_rank01_rigid_baseline"
    ]:
        raise C2StrictBaselineError("C2 candidate order drifted")
    return raw


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    raw = load_raw_contract(path)
    base = load_or140_contract(REPO_ROOT / raw["base_contract"]["path"])
    contract = copy.deepcopy(base)
    contract.update(
        {
            "schema_version": SCHEMA,
            "experiment_id": raw["experiment_id"],
            "status": raw["status"],
            "proof_class": raw["proof_class"],
            "authorization": raw["authorization"],
            "base_contract": raw["base_contract"],
            "action_invariance": raw["action_invariance"],
            "candidate_order": raw["candidate_order"],
            "c2_parameters": raw["c2_parameters"],
            "supplemental_gates": raw["supplemental_gates"],
            "implementation_bindings": raw["implementation_bindings"],
            "execution": raw["execution"],
            "authority": raw["authority"],
            "claim_boundary": raw["claim_boundary"],
        }
    )
    contract["source_bindings"].update(raw["source_bindings"])
    return contract


def run_baseline(
    *, output_directory: Path = OUTPUT_ROOT, contract_path: Path = CONTRACT_PATH
) -> dict[str, Any]:
    contract = load_contract(contract_path)
    candidate = contract["candidate_order"][0]
    collector = FullStepTraceCollector(
        candidate_id=str(candidate["candidate_id"]), contract=contract
    )
    probe = run_grasp_episode_probe(
        source_repository_root=REPO_ROOT,
        recording_id=str(contract["source_bindings"]["recording_id"]),
        parameters=copy.deepcopy(contract["c2_parameters"]),
        state_trace_output_directory=output_directory / "inspection_state",
        retention_trace_enabled=True,
        spec_mutator=legacy_shoulder_spec_mutator(contract),
        integration_step_observer=collector,
    )
    episode = probe["episode"]
    if (
        episode["action_array_sha256"]
        != contract["source_bindings"]["action_sha256"]
        or episode["clipped_action_rows"] != 0
        or episode["diagnostic_measured_joint_state_replay"]["enabled"]
    ):
        raise C2StrictBaselineError("exact C2 action identity drifted")
    trace = collector.write(output_directory)
    receipt = {
        "schema_version": PRODUCER_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "candidate": candidate,
        "contract": {
            "path": str(contract_path.relative_to(REPO_ROOT)),
            "sha256": sha256_file(contract_path),
        },
        "implementation": {
            "path": str(Path(__file__).resolve().relative_to(REPO_ROOT)),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "action": {
            "shape": contract["action_invariance"]["shape"],
            "dtype": contract["action_invariance"]["dtype"],
            "sha256": episode["action_array_sha256"],
            "clipped_rows": episode["clipped_action_rows"],
            "byte_identical": episode["action_byte_identical"],
        },
        "parameter_digest": canonical_digest(contract["c2_parameters"]),
        "producer_episode_summary": episode,
        "full_step_trace": trace,
        "producer_pass_fail_is_authoritative": False,
        "authority": contract["authority"],
        "claim_boundary": contract["claim_boundary"],
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    output_directory.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output_directory / "producer_receipt.json", receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    args = parser.parse_args(argv)
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    receipt = run_baseline(
        output_directory=args.output.resolve(), contract_path=args.contract.resolve()
    )
    print(
        json.dumps(
            {
                "candidate_id": receipt["candidate"]["candidate_id"],
                "action_sha256": receipt["action"]["sha256"],
                "trace": receipt["full_step_trace"],
                "receipt_digest": receipt["receipt_digest"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["C2StrictBaselineError", "load_contract", "load_raw_contract", "run_baseline"]

"""OR136 source-boundary compatibility repair and frozen flex replay."""

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
from .pawn_bg_f2_deformable_cap import (
    FullStepTraceCollector,
    compiled_model_sha256,
    flex_semantic_declarations,
)
from .pawn_bg_f2_deformable_cap_compatibility import (
    _candidate,
    candidate_spec_mutator,
    compile_candidate_model,
)
from .pawn_bg_grasp_coordinate_descent import run_grasp_episode_probe


CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "pawn_bg_f2_deformable_cap_source_boundary_v1.json"
)
OUTPUT_ROOT = REPO_ROOT / "outputs" / "pawn_bg_f2_deformable_cap_source_boundary_v1"
SCHEMA = "sim2claw.pawn_bg_f2_deformable_cap_source_boundary.v1"
PRODUCER_SCHEMA = (
    "sim2claw.pawn_bg_f2_deformable_cap_source_boundary_producer_receipt.v1"
)


class SourceBoundaryReplayError(RuntimeError):
    """OR136 cannot execute after any frozen identity or authority drift."""


def _validate_binding(binding: Mapping[str, Any]) -> None:
    path = REPO_ROOT / str(binding["path"])
    if not path.is_file() or sha256_file(path) != str(binding["sha256"]):
        raise SourceBoundaryReplayError(f"source binding drifted: {binding['path']}")


def load_raw_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SourceBoundaryReplayError(f"cannot read OR136 contract: {error}") from error
    if raw.get("schema_version") != SCHEMA:
        raise SourceBoundaryReplayError("unexpected OR136 contract schema")
    _validate_binding(raw["authorization"])
    _validate_binding(raw["base_contract"])
    for binding in raw["additional_source_bindings"].values():
        _validate_binding(binding)
    for binding in raw["implementation_bindings"].values():
        _validate_binding(binding)
    if any(raw.get("authority", {}).values()):
        raise SourceBoundaryReplayError("OR136 authority widened")
    return raw


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    """Materialize the frozen OR135 base plus OR136's narrow evaluator repair."""

    raw = load_raw_contract(path)
    base_path = REPO_ROOT / str(raw["base_contract"]["path"])
    base = json.loads(base_path.read_text(encoding="utf-8"))
    contract = copy.deepcopy(base)
    contract.update(
        {
            "schema_version": SCHEMA,
            "experiment_id": raw["experiment_id"],
            "status": raw["status"],
            "proof_class": raw["proof_class"],
            "authorization": raw["authorization"],
            "base_contract": raw["base_contract"],
            "rigid_compatibility_reference": raw[
                "rigid_compatibility_reference"
            ],
            "rigid_compatibility_tolerances": raw[
                "rigid_compatibility_tolerances"
            ],
            "source_boundary_reconstruction": raw[
                "source_boundary_reconstruction"
            ],
            "execution": raw["execution"],
            "implementation_bindings": raw["implementation_bindings"],
            "authority": raw["authority"],
            "claim_boundary": raw["claim_boundary"],
        }
    )
    contract["source_bindings"].update(raw["additional_source_bindings"])
    if [row["candidate_id"] for row in contract["candidate_order"]] != [
        "rigid_legacy_shoulder_control",
        "flex_10_kpa",
        "flex_25_kpa",
        "flex_63_kpa",
        "flex_158_kpa",
        "flex_400_kpa",
    ]:
        raise SourceBoundaryReplayError("inherited candidate family drifted")
    return contract


def compile_signature(
    *, candidate_id: str, contract_path: Path = CONTRACT_PATH
) -> dict[str, Any]:
    contract = load_contract(contract_path)
    candidate = _candidate(contract, candidate_id)
    model = compile_candidate_model(contract=contract, candidate=candidate)
    return {
        "candidate_id": candidate_id,
        "compiled_model_sha256": compiled_model_sha256(model),
        "nbody": int(model.nbody),
        "ngeom": int(model.ngeom),
        "njnt": int(model.njnt),
        "nq": int(model.nq),
        "nv": int(model.nv),
        "nu": int(model.nu),
        "nflex": int(model.nflex),
        "timestep_seconds": float(model.opt.timestep),
    }


def _require_rigid_gate_for_flex(contract_path: Path) -> None:
    verdict_path = (
        OUTPUT_ROOT
        / "rigid_legacy_shoulder_control"
        / "source_boundary_verdict.json"
    )
    if not verdict_path.is_file():
        raise SourceBoundaryReplayError("flex is closed until OR136 rigid passes")
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    if (
        verdict.get("schema_version")
        != "sim2claw.pawn_bg_f2_deformable_cap_source_boundary_verdict.v1"
        or verdict.get("candidate_id") != "rigid_legacy_shoulder_control"
        or verdict.get("compatibility_passed") is not True
        or verdict.get("inputs", {}).get("contract_sha256")
        != sha256_file(contract_path)
    ):
        raise SourceBoundaryReplayError("OR136 rigid verdict is not admissible")


def run_candidate(
    *, candidate_id: str, output_directory: Path, contract_path: Path = CONTRACT_PATH
) -> dict[str, Any]:
    contract = load_contract(contract_path)
    if contract.get("status") != "frozen_before_dynamic_execution":
        raise SourceBoundaryReplayError("OR136 contract is not frozen")
    candidate = _candidate(contract, candidate_id)
    if candidate["kind"] == "flex":
        _require_rigid_gate_for_flex(contract_path)
    compiled = compile_candidate_model(contract=contract, candidate=candidate)
    compiled_sha = compiled_model_sha256(compiled)
    if candidate["kind"] == "rigid" and compiled_sha != contract[
        "rigid_compatibility_reference"
    ]["compiled_model_sha256"]:
        raise SourceBoundaryReplayError("OR136 rigid compiled model preflight failed")
    collector = FullStepTraceCollector(candidate_id=candidate_id, contract=contract)
    probe = run_grasp_episode_probe(
        source_repository_root=REPO_ROOT,
        recording_id=str(contract["source_bindings"]["recording_id"]),
        parameters=copy.deepcopy(contract["rigid_parameters"]),
        state_trace_output_directory=output_directory / "inspection_state",
        retention_trace_enabled=True,
        spec_mutator=candidate_spec_mutator(contract, candidate),
        flex_semantic_declarations=flex_semantic_declarations(contract, candidate),
        integration_step_observer=collector,
    )
    episode = probe["episode"]
    if (
        episode["action_array_sha256"]
        != contract["source_bindings"]["action_sha256"]
        or episode["clipped_action_rows"] != 0
    ):
        raise SourceBoundaryReplayError("OR136 action identity drifted")
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
        "compiled_model_sha256": compiled_sha,
        "action": {
            "shape": contract["action_invariance"]["shape"],
            "dtype": contract["action_invariance"]["dtype"],
            "sha256": episode["action_array_sha256"],
            "clipped_rows": episode["clipped_action_rows"],
            "byte_identical": episode["action_byte_identical"],
        },
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
    parser.add_argument("--candidate", default="rigid_legacy_shoulder_control")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--compile-signature", action="store_true")
    args = parser.parse_args(argv)
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    if args.compile_signature:
        print(
            json.dumps(
                compile_signature(
                    candidate_id=args.candidate,
                    contract_path=args.contract.resolve(),
                ),
                sort_keys=True,
            )
        )
        return 0
    if args.output is None:
        parser.error("--output is required for dynamic execution")
    receipt = run_candidate(
        candidate_id=args.candidate,
        output_directory=args.output.resolve(),
        contract_path=args.contract.resolve(),
    )
    print(json.dumps(receipt["full_step_trace"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CONTRACT_PATH",
    "OUTPUT_ROOT",
    "SCHEMA",
    "SourceBoundaryReplayError",
    "compile_signature",
    "load_contract",
    "load_raw_contract",
    "run_candidate",
]

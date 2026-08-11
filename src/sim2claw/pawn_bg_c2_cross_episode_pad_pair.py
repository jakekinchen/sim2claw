"""Run OR147's one zero-refit C2 pad-pair plus distal-trim candidate."""

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
from .pawn_bg_c2_strict_baseline import load_contract as load_or146_contract
from .pawn_bg_f2_deformable_cap import FullStepTraceCollector
from .pawn_bg_f2_deformable_cap_compatibility import legacy_shoulder_spec_mutator
from .pawn_bg_grasp_coordinate_descent import run_grasp_episode_probe


CONTRACT_PATH = REPO_ROOT / "configs" / "evaluations" / "pawn_bg_c2_cross_episode_pad_pair_v1.json"
OUTPUT_ROOT = REPO_ROOT / "outputs" / "pawn_bg_c2_cross_episode_pad_pair_v1"
SCHEMA = "sim2claw.pawn_bg_c2_cross_episode_pad_pair.v1"
PRODUCER_SCHEMA = "sim2claw.pawn_bg_c2_cross_episode_pad_pair_producer.v1"


class C2CrossEpisodePadPairError(RuntimeError):
    """The frozen cross-episode pad-pair candidate drifted."""


def _validate_binding(binding: Mapping[str, Any]) -> None:
    path = REPO_ROOT / str(binding["path"])
    if not path.is_file() or sha256_file(path) != str(binding["sha256"]):
        raise C2CrossEpisodePadPairError(f"source binding drifted: {binding['path']}")


def load_raw_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != SCHEMA:
        raise C2CrossEpisodePadPairError("unexpected OR147 schema")
    _validate_binding(raw["authorization"])
    _validate_binding(raw["base_contract"])
    for binding in raw["source_bindings"].values():
        if isinstance(binding, Mapping) and {"path", "sha256"} <= set(binding):
            _validate_binding(binding)
    for binding in raw["implementation_bindings"].values():
        _validate_binding(binding)
    if any(raw.get("authority", {}).values()):
        raise C2CrossEpisodePadPairError("OR147 authority widened")
    expected = {
        "tip_fixed_coverage_offset_m": 0.00752,
        "fixed_jaw_primitive_collision_enabled": False,
        "moving_jaw_primitive_collision_enabled": False,
        "tip_moving_coverage_multiplier": 0.85,
        "tip_moving_coverage_offset_m": 0.0265,
    }
    if raw.get("parameter_overrides") != expected:
        raise C2CrossEpisodePadPairError("cross-episode mechanism drifted")
    if [row["candidate_id"] for row in raw["candidate_order"]] != [
        "c2_or50_fixed_pad_pair_distal_trim_3mm"
    ]:
        raise C2CrossEpisodePadPairError("candidate identity drifted")
    return raw


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    raw = load_raw_contract(path)
    base = load_or146_contract(REPO_ROOT / raw["base_contract"]["path"])
    contract = copy.deepcopy(base)
    parameters = copy.deepcopy(base["c2_parameters"])
    parameters.update(raw["parameter_overrides"])
    contract.update(
        {
            "schema_version": SCHEMA,
            "experiment_id": raw["experiment_id"],
            "status": raw["status"],
            "proof_class": raw["proof_class"],
            "authorization": raw["authorization"],
            "base_contract": raw["base_contract"],
            "candidate_order": raw["candidate_order"],
            "parameter_overrides": raw["parameter_overrides"],
            "c2_parameters": parameters,
            "implementation_bindings": raw["implementation_bindings"],
            "execution": raw["execution"],
            "authority": raw["authority"],
            "claim_boundary": raw["claim_boundary"],
        }
    )
    contract["source_bindings"].update(raw["source_bindings"])
    return contract


def run_candidate(
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
        raise C2CrossEpisodePadPairError("exact C2 action identity drifted")
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
        "parameter_overrides": contract["parameter_overrides"],
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
    receipt = run_candidate(
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


__all__ = ["C2CrossEpisodePadPairError", "load_contract", "run_candidate"]

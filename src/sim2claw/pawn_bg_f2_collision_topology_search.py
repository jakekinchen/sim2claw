"""OR142 verifier-repaired search over existing jaw collision surfaces."""

from __future__ import annotations

import argparse
import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import mujoco

from .contact_prior import read_contact_prior_snapshot
from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT
from .pawn_bg_action_frozen_gap import _load_partition, _reconstruct_stage_d
from .pawn_bg_f2_deformable_cap import FullStepTraceCollector, compiled_model_sha256
from .pawn_bg_f2_deformable_cap_compatibility import legacy_shoulder_spec_mutator
from .pawn_bg_f2_normal_compliant_cap import (
    _candidate,
    _effective_workcell,
    _parameters,
    load_contract as load_or140_contract,
)
from .pawn_bg_grasp_coordinate_descent import (
    _apply_model_coordinates,
    _custom_variant,
    load_grasp_coordinate_contract,
    run_grasp_episode_probe,
)
from .pawn_bg_workcell_fit import build_workcell_model


CONTRACT_PATH = REPO_ROOT / "configs" / "evaluations" / (
    "pawn_bg_f2_collision_topology_search_verifier_repair_v1.json"
)
OUTPUT_ROOT = (
    REPO_ROOT / "outputs" / "pawn_bg_f2_collision_topology_search_verifier_repair_v1"
)
SCHEMA = "sim2claw.pawn_bg_f2_collision_topology_search_verifier_repair.v1"
PRODUCER_SCHEMA = "sim2claw.pawn_bg_f2_collision_topology_search_producer.v1"


class CollisionTopologySearchError(RuntimeError):
    """The bounded OR141 search cannot continue after identity drift."""


def _validate_binding(binding: Mapping[str, Any]) -> None:
    path = REPO_ROOT / str(binding["path"])
    if not path.is_file() or sha256_file(path) != str(binding["sha256"]):
        raise CollisionTopologySearchError(f"source binding drifted: {binding['path']}")


def load_raw_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != SCHEMA:
        raise CollisionTopologySearchError("unexpected OR141 contract schema")
    _validate_binding(raw["authorization"])
    _validate_binding(raw["base_contract"])
    for binding in raw["source_bindings"].values():
        _validate_binding(binding)
    for binding in raw["implementation_bindings"].values():
        _validate_binding(binding)
    if any(raw.get("authority", {}).values()):
        raise CollisionTopologySearchError("OR141 authority widened")
    expected = [
        "rigid_legacy_shoulder_control",
        "rigid_distal_pads_only",
        "rigid_distal_pads_plus_spheres",
        "rigid_distal_pads_plus_boxes",
    ]
    if [row.get("candidate_id") for row in raw["candidate_order"]] != expected:
        raise CollisionTopologySearchError("OR141 candidate order drifted")
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
            "candidate_order": raw["candidate_order"],
            "topology_search": raw["topology_search"],
            "execution": raw["execution"],
            "implementation_bindings": raw["implementation_bindings"],
            "authority": raw["authority"],
            "claim_boundary": raw["claim_boundary"],
        }
    )
    contract["source_bindings"].update(raw["source_bindings"])
    return contract


def topology_spec_mutator(
    contract: Mapping[str, Any], candidate: Mapping[str, Any]
) -> Any:
    restore_legacy = legacy_shoulder_spec_mutator(contract)
    disabled = tuple(candidate.get("disabled_geom_names", []))

    def mutate(spec: mujoco.MjSpec) -> None:
        restore_legacy(spec)
        observed = []
        for name in disabled:
            geom = spec.geom(str(name))
            if geom is None:
                raise CollisionTopologySearchError(f"frozen jaw geom missing: {name}")
            if int(geom.contype) != 1 or int(geom.conaffinity) != 1:
                raise CollisionTopologySearchError(f"jaw geom was not collision-active: {name}")
            geom.contype = 0
            geom.conaffinity = 0
            observed.append(str(name))
        if observed != list(disabled):
            raise CollisionTopologySearchError("disabled-geom order drifted")

    return mutate


def compile_candidate_model(
    *, contract: Mapping[str, Any], candidate: Mapping[str, Any]
) -> mujoco.MjModel:
    grasp_contract = load_grasp_coordinate_contract()
    train_payloads, events = _load_partition(REPO_ROOT, "train")
    _parent, workcell, _stage_d, _details = _reconstruct_stage_d(train_payloads, events)
    parameters = _parameters(contract, candidate)
    snapshot = read_contact_prior_snapshot(
        REPO_ROOT / grasp_contract["source"]["contact_prior_path"]
    )
    if snapshot.sha256 != grasp_contract["source"]["expected_contact_prior_canonical_sha256"]:
        raise CollisionTopologySearchError("contact-prior canonical hash drifted")
    variant = _custom_variant(
        parameters=parameters,
        contract_path=REPO_ROOT
        / "configs"
        / "optimization"
        / "pawn_bg_grasp_coordinate_descent_v1.json",
        contact_snapshot=snapshot,
    )
    binding = build_workcell_model(
        _effective_workcell(workcell, parameters),
        contact_variant=variant,
        spec_mutator=topology_spec_mutator(contract, candidate),
    )
    model, data = binding["model"], binding["data"]
    _apply_model_coordinates(model, data, binding=binding, parameters=parameters)
    return model


def _geom_row(model: mujoco.MjModel, name: str) -> dict[str, Any]:
    geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, name)
    if geom_id < 0:
        raise CollisionTopologySearchError(f"compiled geom missing: {name}")
    return {
        "name": name,
        "contype": int(model.geom_contype[geom_id]),
        "conaffinity": int(model.geom_conaffinity[geom_id]),
        "body_id": int(model.geom_bodyid[geom_id]),
        "type": int(model.geom_type[geom_id]),
        "pos": model.geom_pos[geom_id].tolist(),
        "size": model.geom_size[geom_id].tolist(),
    }


def compile_audit(*, contract_path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = load_contract(contract_path)
    rows = []
    checks: dict[str, bool] = {}
    for candidate in contract["candidate_order"]:
        model = compile_candidate_model(contract=contract, candidate=candidate)
        disabled = list(candidate.get("disabled_geom_names", []))
        disabled_rows = [_geom_row(model, name) for name in disabled]
        pad_ids = [
            index
            for index in range(model.ngeom)
            if "_rubber_tip_" in (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, index) or "")
        ]
        candidate_checks = {
            "no_flex": int(model.nflex) == 0,
            "no_added_compliance_dofs": int(model.njnt) == 28,
            "exactly_two_active_rigid_pads": len(pad_ids) == 2
            and all(int(model.geom_contype[index]) == 1 for index in pad_ids)
            and all(int(model.geom_conaffinity[index]) == 1 for index in pad_ids),
            "frozen_disabled_geoms_inactive": all(
                row["contype"] == 0 and row["conaffinity"] == 0
                for row in disabled_rows
            ),
            "runtime_options_frozen": abs(float(model.opt.timestep) - 0.00225) <= 1e-15,
        }
        checks[candidate["candidate_id"]] = all(candidate_checks.values())
        rows.append(
            {
                "candidate_id": candidate["candidate_id"],
                "compiled_model_sha256": compiled_model_sha256(model),
                "disabled_geom_rows": disabled_rows,
                "checks": candidate_checks,
            }
        )
    rigid_hash = rows[0]["compiled_model_sha256"]
    checks["rigid_compiled_model_identity"] = rigid_hash == contract[
        "rigid_compatibility_reference"
    ]["compiled_model_sha256"]
    return {
        "schema_version": "sim2claw.pawn_bg_f2_collision_topology_compile_audit.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "contract_sha256": sha256_file(contract_path),
        "passed": all(checks.values()),
        "checks": checks,
        "candidates": rows,
        "authority": contract["authority"],
        "claim_boundary": contract["claim_boundary"],
    }


def _require_prior_verdict(candidate_id: str) -> None:
    if candidate_id == "rigid_legacy_shoulder_control":
        return
    rigid_path = OUTPUT_ROOT / "rigid_legacy_shoulder_control" / "task_verdict.json"
    if not rigid_path.is_file():
        raise CollisionTopologySearchError("fresh rigid task verdict is missing")
    rigid = json.loads(rigid_path.read_text(encoding="utf-8"))
    if rigid.get("candidate_id") != "rigid_legacy_shoulder_control" or rigid.get(
        "compatibility_passed"
    ) is not True:
        raise CollisionTopologySearchError("fresh rigid compatibility failed")
    order = [row["candidate_id"] for row in load_contract()["candidate_order"]]
    index = order.index(candidate_id)
    for previous in order[1:index]:
        path = OUTPUT_ROOT / previous / "task_verdict.json"
        if not path.is_file():
            raise CollisionTopologySearchError(f"prior candidate verdict missing: {previous}")
        verdict = json.loads(path.read_text(encoding="utf-8"))
        if verdict.get("strict_replay_passed") is True:
            raise CollisionTopologySearchError("search must stop at first strict pass")


def run_candidate(
    *, candidate_id: str, output_directory: Path, contract_path: Path = CONTRACT_PATH
) -> dict[str, Any]:
    contract = load_contract(contract_path)
    candidate = _candidate(contract, candidate_id)
    _require_prior_verdict(candidate_id)
    model = compile_candidate_model(contract=contract, candidate=candidate)
    model_sha = compiled_model_sha256(model)
    if candidate_id == "rigid_legacy_shoulder_control" and model_sha != contract[
        "rigid_compatibility_reference"
    ]["compiled_model_sha256"]:
        raise CollisionTopologySearchError("rigid compiled model identity failed")
    collector = FullStepTraceCollector(candidate_id=candidate_id, contract=contract)
    probe = run_grasp_episode_probe(
        source_repository_root=REPO_ROOT,
        recording_id=str(contract["source_bindings"]["recording_id"]),
        parameters=_parameters(contract, candidate),
        state_trace_output_directory=output_directory / "inspection_state",
        retention_trace_enabled=True,
        spec_mutator=topology_spec_mutator(contract, candidate),
        integration_step_observer=collector,
    )
    episode = probe["episode"]
    if (
        episode["action_array_sha256"] != contract["source_bindings"]["action_sha256"]
        or episode["clipped_action_rows"] != 0
        or episode["diagnostic_measured_joint_state_replay"]["enabled"]
    ):
        raise CollisionTopologySearchError("exact action identity drifted")
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
        "compiled_model_sha256": model_sha,
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
    parser.add_argument("--mode", choices=("compile-audit", "task"), required=True)
    parser.add_argument("--candidate")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    args = parser.parse_args(argv)
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    if args.mode == "compile-audit":
        payload = compile_audit(contract_path=args.contract.resolve())
        atomic_write_json(args.output.resolve(), payload)
    else:
        if not args.candidate:
            parser.error("--candidate is required")
        payload = run_candidate(
            candidate_id=args.candidate,
            output_directory=args.output.resolve(),
            contract_path=args.contract.resolve(),
        )
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CONTRACT_PATH",
    "OUTPUT_ROOT",
    "SCHEMA",
    "compile_audit",
    "compile_candidate_model",
    "load_contract",
    "load_raw_contract",
    "run_candidate",
    "topology_spec_mutator",
]

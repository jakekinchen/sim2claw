"""OR135 historical-runtime compatibility gate and deformable-cap replay."""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from .contact_prior import read_contact_prior_snapshot
from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT
from .pawn_bg_action_frozen_gap import _load_partition, _reconstruct_stage_d
from .pawn_bg_f2_deformable_cap import (
    FullStepTraceCollector,
    compiled_model_sha256,
    flex_cap_spec_mutator,
    flex_semantic_declarations,
)
from .pawn_bg_grasp_coordinate_descent import (
    _apply_model_coordinates,
    _custom_variant,
    load_grasp_coordinate_contract,
    run_grasp_episode_probe,
)
from .pawn_bg_workcell_fit import build_workcell_model


CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "pawn_bg_f2_deformable_cap_compatibility_v1.json"
)
OUTPUT_ROOT = REPO_ROOT / "outputs" / "pawn_bg_f2_deformable_cap_compatibility_v1"
SCHEMA = "sim2claw.pawn_bg_f2_deformable_cap_compatibility.v1"
PRODUCER_SCHEMA = (
    "sim2claw.pawn_bg_f2_deformable_cap_compatibility_producer_receipt.v1"
)


class CompatibilityReplayError(RuntimeError):
    """OR135 cannot proceed without widening or changing its frozen identity."""


def _validate_binding(binding: Mapping[str, Any]) -> None:
    path = REPO_ROOT / str(binding["path"])
    if not path.is_file() or sha256_file(path) != str(binding["sha256"]):
        raise CompatibilityReplayError(f"source binding drifted: {binding['path']}")


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CompatibilityReplayError(f"cannot read OR135 contract: {error}") from error
    if contract.get("schema_version") != SCHEMA:
        raise CompatibilityReplayError("unexpected OR135 contract schema")
    _validate_binding(contract["authorization"])
    for value in contract["source_bindings"].values():
        if isinstance(value, dict) and {"path", "sha256"} <= set(value):
            _validate_binding(value)
    for value in contract["implementation_bindings"].values():
        _validate_binding(value)
    if any(contract.get("authority", {}).values()):
        raise CompatibilityReplayError("OR135 authority widened")
    expected_candidates = [
        ("rigid_legacy_shoulder_control", None),
        ("flex_10_kpa", 10000.0),
        ("flex_25_kpa", 25000.0),
        ("flex_63_kpa", 63000.0),
        ("flex_158_kpa", 158000.0),
        ("flex_400_kpa", 400000.0),
    ]
    observed = [
        (row.get("candidate_id"), row.get("youngs_modulus_pa"))
        for row in contract.get("candidate_order", [])
    ]
    if observed != expected_candidates:
        raise CompatibilityReplayError("OR135 candidate family drifted")
    runtime = contract["historical_runtime_identity"]
    expected_runtime = {
        "contact_cone": "elliptic",
        "contact_solver": "newton",
        "integrator": "implicitfast",
        "iterations": 10,
        "ls_iterations": 20,
        "noslip_iterations": 0,
        "friction_impratio": 10.0,
        "timestep_seconds_after_multiplier": 0.00225,
        "legacy_shoulder_box_half_extent_xyz_m": [0.023, 0.015, 0.01],
        "current_shoulder_box_half_extent_xyz_m": [0.0124, 0.015, 0.01],
    }
    for key, value in expected_runtime.items():
        if runtime.get(key) != value:
            raise CompatibilityReplayError(f"historical runtime drifted: {key}")
    action = contract["action_invariance"]
    if (
        action.get("shape") != [440, 6]
        or action.get("dtype") != "float64"
        or action.get("per_joint_zoh_delay_seconds") != [0.11] * 6
        or action.get("clipped_rows") != 0
        or action.get("no_ik_offsets_clipping_retiming_smoothing_suffix_or_override")
        is not True
        or action.get("no_measured_state_replay_latch_load_hold_or_force_ramp")
        is not True
    ):
        raise CompatibilityReplayError("OR135 action invariance is not fail closed")
    return contract


def _vector_close(actual: Any, expected: list[float]) -> bool:
    return all(
        math.isclose(float(observed), target, abs_tol=1e-12)
        for observed, target in zip(actual, expected, strict=True)
    )


def legacy_shoulder_spec_mutator(contract: Mapping[str, Any]) -> Any:
    """Restore the named pre-9090042 collider solely as a compatibility fixture."""

    current_size = contract["historical_runtime_identity"][
        "current_shoulder_box_half_extent_xyz_m"
    ]
    legacy_size = contract["historical_runtime_identity"][
        "legacy_shoulder_box_half_extent_xyz_m"
    ]

    def mutate(spec: mujoco.MjSpec) -> None:
        changed: list[str] = []
        for body_name in ("left_shoulder", "right_shoulder"):
            body = spec.body(body_name)
            if body is None:
                raise CompatibilityReplayError(f"missing shoulder body: {body_name}")
            matches = [
                geom
                for geom in body.geoms
                if geom.type == mujoco.mjtGeom.mjGEOM_BOX
                and _vector_close(geom.size, current_size)
            ]
            if len(matches) != 1:
                raise CompatibilityReplayError(
                    f"current shoulder collider identity drifted: {body_name}"
                )
            matches[0].size = list(legacy_size)
            changed.append(body_name)
        if changed != ["left_shoulder", "right_shoulder"]:
            raise CompatibilityReplayError("legacy shoulder mutation was incomplete")

    return mutate


def candidate_spec_mutator(
    contract: Mapping[str, Any], candidate: Mapping[str, Any]
) -> Any:
    restore_legacy = legacy_shoulder_spec_mutator(contract)
    young = candidate["youngs_modulus_pa"]
    add_flex = None if young is None else flex_cap_spec_mutator(contract, float(young))

    def mutate(spec: mujoco.MjSpec) -> None:
        restore_legacy(spec)
        if add_flex is not None:
            add_flex(spec)

    return mutate


def _candidate(contract: Mapping[str, Any], candidate_id: str) -> dict[str, Any]:
    rows = [
        row for row in contract["candidate_order"] if row["candidate_id"] == candidate_id
    ]
    if len(rows) != 1:
        raise CompatibilityReplayError(f"candidate is not preregistered: {candidate_id}")
    return dict(rows[0])


def _effective_workcell(workcell: Any, parameters: Mapping[str, Any]) -> Any:
    return replace(
        workcell,
        board_center_in_table_frame_xy_m=(
            float(workcell.board_center_in_table_frame_xy_m[0])
            + float(parameters.get("board_center_offset_x_m", 0.0)),
            float(workcell.board_center_in_table_frame_xy_m[1])
            + float(parameters.get("board_center_offset_y_m", 0.0)),
        ),
        board_yaw_relative_to_table_degrees=(
            float(workcell.board_yaw_relative_to_table_degrees)
            + float(parameters.get("board_yaw_offset_degrees", 0.0))
        ),
        board_side_m=(
            workcell.board_side_m
            if "board_side_multiplier" not in parameters
            else (
                float(workcell.board_side_m or 0.3556)
                * float(parameters["board_side_multiplier"])
            )
        ),
        base_z_offset_m=float(workcell.base_z_offset_m)
        + float(parameters.get("base_z_offset_m", 0.0)),
        base_roll_offset_degrees=float(workcell.base_roll_offset_degrees)
        + float(parameters.get("base_roll_offset_degrees", 0.0)),
        base_pitch_offset_degrees=float(workcell.base_pitch_offset_degrees)
        + float(parameters.get("base_pitch_offset_degrees", 0.0)),
    )


def compile_candidate_model(
    *, contract: Mapping[str, Any], candidate: Mapping[str, Any]
) -> mujoco.MjModel:
    """Compile the frozen model without advancing simulation state."""

    grasp_contract = load_grasp_coordinate_contract()
    train_payloads, events = _load_partition(REPO_ROOT, "train")
    _parent, workcell, _stage_d, _details = _reconstruct_stage_d(
        train_payloads, events
    )
    parameters = copy.deepcopy(contract["rigid_parameters"])
    contact_snapshot = read_contact_prior_snapshot(
        REPO_ROOT / grasp_contract["source"]["contact_prior_path"]
    )
    if (
        contact_snapshot.sha256
        != grasp_contract["source"]["expected_contact_prior_canonical_sha256"]
    ):
        raise CompatibilityReplayError("contact-prior canonical hash drifted")
    variant = _custom_variant(
        parameters=parameters,
        contract_path=REPO_ROOT
        / "configs"
        / "optimization"
        / "pawn_bg_grasp_coordinate_descent_v1.json",
        contact_snapshot=contact_snapshot,
    )
    binding = build_workcell_model(
        _effective_workcell(workcell, parameters),
        contact_variant=variant,
        spec_mutator=candidate_spec_mutator(contract, candidate),
    )
    model, data = binding["model"], binding["data"]
    _apply_model_coordinates(
        model,
        data,
        binding=binding,
        parameters=parameters,
    )
    return model


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
        "solver": mujoco.mjtSolver(int(model.opt.solver)).name,
        "cone": mujoco.mjtCone(int(model.opt.cone)).name,
        "integrator": mujoco.mjtIntegrator(int(model.opt.integrator)).name,
        "iterations": int(model.opt.iterations),
        "ls_iterations": int(model.opt.ls_iterations),
        "noslip_iterations": int(model.opt.noslip_iterations),
        "impratio": float(model.opt.impratio),
    }


def _rigid_compatibility_gate(
    contract: Mapping[str, Any], episode: Mapping[str, Any], model_sha256: str
) -> dict[str, Any]:
    reference = contract["rigid_compatibility_reference"]
    tolerances = contract["rigid_compatibility_tolerances"]
    observed = {
        "compiled_model_sha256": model_sha256,
        "final_target_distance_m": float(episode["final_target_distance_m"]),
        "maximum_piece_rise_m": float(episode["maximum_piece_rise_m"]),
        "piece_lifted": bool(episode["piece_lifted"]),
        "qualified_bilateral_contact_observed": bool(
            episode["qualified_bilateral_contact_observed"]
        ),
        "upright": bool(episode["original_gate_results"]["upright"]),
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


def _require_rigid_gate_for_flex(contract: Mapping[str, Any]) -> None:
    path = OUTPUT_ROOT / "rigid_legacy_shoulder_control" / "compatibility_verdict.json"
    if not path.is_file():
        raise CompatibilityReplayError("flex is closed until the rigid verdict exists")
    verdict = json.loads(path.read_text(encoding="utf-8"))
    if (
        verdict.get("schema_version")
        != "sim2claw.pawn_bg_f2_deformable_cap_compatibility_verdict.v1"
        or verdict.get("candidate_id") != "rigid_legacy_shoulder_control"
        or verdict.get("compatibility_passed") is not True
        or verdict.get("inputs", {}).get("contract_sha256")
        != sha256_file(CONTRACT_PATH)
    ):
        raise CompatibilityReplayError("rigid compatibility verdict is not admissible")


def run_candidate(
    *, candidate_id: str, output_directory: Path, contract_path: Path = CONTRACT_PATH
) -> dict[str, Any]:
    contract = load_contract(contract_path)
    if contract.get("status") != "frozen_before_dynamic_execution":
        raise CompatibilityReplayError("OR135 contract is not frozen")
    candidate = _candidate(contract, candidate_id)
    if candidate["kind"] == "flex":
        _require_rigid_gate_for_flex(contract)
    compiled = compile_candidate_model(contract=contract, candidate=candidate)
    compiled_sha = compiled_model_sha256(compiled)
    if candidate["kind"] == "rigid" and (
        compiled_sha
        != contract["rigid_compatibility_reference"]["compiled_model_sha256"]
    ):
        raise CompatibilityReplayError("rigid compiled model identity failed preflight")
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
    trace = collector.write(output_directory)
    if trace["model_invariant_digest"] != collector.metadata["model_invariant_digest"]:
        raise CompatibilityReplayError("trace model invariant self-check failed")
    compatibility = (
        _rigid_compatibility_gate(contract, episode, compiled_sha)
        if candidate["kind"] == "rigid"
        else None
    )
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
        "rigid_compatibility": compatibility,
        "full_step_trace": trace,
        "producer_strict_pass_fail_is_authoritative": False,
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
    "CompatibilityReplayError",
    "candidate_spec_mutator",
    "compile_candidate_model",
    "compile_signature",
    "legacy_shoulder_spec_mutator",
    "load_contract",
    "run_candidate",
]

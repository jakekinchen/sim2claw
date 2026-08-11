"""OR140 inherited-default normal-compliant-cap preflight and replay."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
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
from .pawn_bg_f2_deformable_cap import FullStepTraceCollector, compiled_model_sha256
from .pawn_bg_f2_deformable_cap_compatibility import legacy_shoulder_spec_mutator
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
    / "pawn_bg_f2_normal_compliant_cap_inherited_v1.json"
)
BASE_CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "pawn_bg_f2_deformable_cap_source_boundary_v1.json"
)
OR135_BASE_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "pawn_bg_f2_deformable_cap_compatibility_v1.json"
)
PROTOCOL_CONTRACT_PATH = (
    REPO_ROOT / "configs" / "evaluations" / "pawn_bg_f2_normal_compliant_cap_v1.json"
)
OUTPUT_ROOT = REPO_ROOT / "outputs" / "pawn_bg_f2_normal_compliant_cap_inherited_v1"
SCHEMA = "sim2claw.pawn_bg_f2_normal_compliant_cap_inherited.v1"
PREFLIGHT_SCHEMA = "sim2claw.pawn_bg_f2_normal_compliant_cap_preflight_trace.v1"
PRODUCER_SCHEMA = "sim2claw.pawn_bg_f2_normal_compliant_cap_producer_receipt.v1"


class NormalCompliantCapError(RuntimeError):
    """OR137 cannot continue after identity, stability, or authority drift."""


class InitialSettleComplete(RuntimeError):
    """Internal control-flow signal proving no replay action was consumed."""


def _array_digest(arrays: Mapping[str, np.ndarray]) -> str:
    digest = hashlib.sha256()
    for name in sorted(arrays):
        value = np.ascontiguousarray(arrays[name])
        digest.update(name.encode("utf-8"))
        digest.update(value.dtype.str.encode("ascii"))
        digest.update(np.asarray(value.shape, dtype=np.int64).tobytes())
        digest.update(value.tobytes())
    return digest.hexdigest()


def _validate_binding(binding: Mapping[str, Any]) -> None:
    path = REPO_ROOT / str(binding["path"])
    if not path.is_file() or sha256_file(path) != str(binding["sha256"]):
        raise NormalCompliantCapError(f"source binding drifted: {binding['path']}")


def load_raw_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise NormalCompliantCapError(f"cannot read OR137 contract: {error}") from error
    if raw.get("schema_version") != SCHEMA:
        raise NormalCompliantCapError("unexpected OR137 contract schema")
    _validate_binding(raw["authorization"])
    _validate_binding(raw["base_contract"])
    _validate_binding(raw["or135_base_contract"])
    if "protocol_contract" in raw:
        _validate_binding(raw["protocol_contract"])
    for binding in raw["additional_source_bindings"].values():
        _validate_binding(binding)
    for binding in raw["implementation_bindings"].values():
        _validate_binding(binding)
    if any(raw.get("authority", {}).values()):
        raise NormalCompliantCapError("OR137 authority widened")
    expected = [
        ("rigid_legacy_shoulder_control", "rigid"),
        ("normal_compliant_prior_k1000", "normal_compliant"),
    ]
    protocol = (
        json.loads(PROTOCOL_CONTRACT_PATH.read_text(encoding="utf-8"))
        if "protocol_contract" in raw
        else raw
    )
    observed = [
        (row.get("candidate_id"), row.get("kind"))
        for row in protocol["candidate_order"]
    ]
    if observed != expected:
        raise NormalCompliantCapError("OR137 candidate identity drifted")
    return raw


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    """Materialize OR137 over the immutable historical runtime/action contract."""

    raw = load_raw_contract(path)
    base = json.loads(OR135_BASE_PATH.read_text(encoding="utf-8"))
    protocol = (
        json.loads(PROTOCOL_CONTRACT_PATH.read_text(encoding="utf-8"))
        if "protocol_contract" in raw
        else raw
    )
    contract = copy.deepcopy(base)
    contract.update(
        {
            "schema_version": SCHEMA,
            "experiment_id": raw["experiment_id"],
            "status": raw["status"],
            "proof_class": raw["proof_class"],
            "authorization": raw["authorization"],
            "base_contract": raw["base_contract"],
            "or135_base_contract": raw["or135_base_contract"],
            "candidate_order": protocol["candidate_order"],
            "normal_compliance": protocol["normal_compliance"],
            "preflight": protocol["preflight"],
            "rigid_compatibility_reference": protocol[
                "rigid_compatibility_reference"
            ],
            "rigid_compatibility_tolerances": protocol[
                "rigid_compatibility_tolerances"
            ],
            "source_boundary_reconstruction": protocol[
                "source_boundary_reconstruction"
            ],
            "execution": protocol["execution"],
            "construction_repair": raw.get("construction_repair", {}),
            "preflight_repair": raw.get("preflight_repair", {}),
            "implementation_bindings": raw["implementation_bindings"],
            "authority": raw["authority"],
            "claim_boundary": raw["claim_boundary"],
        }
    )
    contract["source_bindings"].update(raw["additional_source_bindings"])
    return contract


def _candidate(contract: Mapping[str, Any], candidate_id: str) -> dict[str, Any]:
    matches = [row for row in contract["candidate_order"] if row["candidate_id"] == candidate_id]
    if len(matches) != 1:
        raise NormalCompliantCapError(f"candidate is not frozen: {candidate_id}")
    return dict(matches[0])


def _parameters(contract: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    parameters = copy.deepcopy(contract["rigid_parameters"])
    parameters.update(copy.deepcopy(candidate.get("parameter_overrides", {})))
    return parameters


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
            else float(workcell.board_side_m or 0.3556)
            * float(parameters["board_side_multiplier"])
        ),
        base_z_offset_m=float(workcell.base_z_offset_m)
        + float(parameters.get("base_z_offset_m", 0.0)),
        base_roll_offset_degrees=float(workcell.base_roll_offset_degrees)
        + float(parameters.get("base_roll_offset_degrees", 0.0)),
        base_pitch_offset_degrees=float(workcell.base_pitch_offset_degrees)
        + float(parameters.get("base_pitch_offset_degrees", 0.0)),
    )


def candidate_spec_mutator(
    contract: Mapping[str, Any], candidate: Mapping[str, Any]
) -> Any:
    """Restore the legacy shoulder fixture and retain disclosed child defaults."""

    restore_legacy = legacy_shoulder_spec_mutator(contract)
    expected = 2 if candidate["kind"] == "normal_compliant" else 0

    def mutate(spec: mujoco.MjSpec) -> None:
        restore_legacy(spec)
        matches = [
            joint for joint in spec.joints if str(joint.name).endswith("_normal_joint")
        ]
        if len(matches) != expected:
            raise NormalCompliantCapError(
                f"normal-compliant joint inventory drifted: {len(matches)} != {expected}"
            )

    return mutate


def compile_candidate_model(
    *, contract: Mapping[str, Any], candidate: Mapping[str, Any]
) -> mujoco.MjModel:
    grasp_contract = load_grasp_coordinate_contract()
    train_payloads, events = _load_partition(REPO_ROOT, "train")
    _parent, workcell, _stage_d, _details = _reconstruct_stage_d(train_payloads, events)
    parameters = _parameters(contract, candidate)
    contact_snapshot = read_contact_prior_snapshot(
        REPO_ROOT / grasp_contract["source"]["contact_prior_path"]
    )
    if contact_snapshot.sha256 != grasp_contract["source"][
        "expected_contact_prior_canonical_sha256"
    ]:
        raise NormalCompliantCapError("contact-prior canonical hash drifted")
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
    _apply_model_coordinates(model, data, binding=binding, parameters=parameters)
    return model


def _names(model: mujoco.MjModel, obj: mujoco.mjtObj, count: int) -> list[str]:
    return [mujoco.mj_id2name(model, obj, index) or f"unnamed_{index}" for index in range(count)]


def compile_audit(*, contract_path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = load_contract(contract_path)
    rigid = compile_candidate_model(
        contract=contract, candidate=_candidate(contract, "rigid_legacy_shoulder_control")
    )
    compliant = compile_candidate_model(
        contract=contract, candidate=_candidate(contract, "normal_compliant_prior_k1000")
    )
    rigid_hash = compiled_model_sha256(rigid)
    body_names = _names(compliant, mujoco.mjtObj.mjOBJ_BODY, compliant.nbody)
    joint_names = _names(compliant, mujoco.mjtObj.mjOBJ_JOINT, compliant.njnt)
    geom_names = _names(compliant, mujoco.mjtObj.mjOBJ_GEOM, compliant.ngeom)
    cap_joint_ids = [index for index, name in enumerate(joint_names) if name.endswith("_normal_joint")]
    cap_body_names = [name for name in body_names if "_rubber_tip_" in name and name.endswith("_body")]
    cap_geom_ids = [index for index, name in enumerate(geom_names) if "_rubber_tip_" in name]
    cap_rows = []
    for joint_id in cap_joint_ids:
        dof = int(compliant.jnt_dofadr[joint_id])
        body_id = int(compliant.jnt_bodyid[joint_id])
        geom_ids = [gid for gid in cap_geom_ids if int(compliant.geom_bodyid[gid]) == body_id]
        cap_rows.append(
            {
                "joint_name": joint_names[joint_id],
                "body_name": body_names[body_id],
                "geom_names": [geom_names[gid] for gid in geom_ids],
                "axis": np.asarray(compliant.jnt_axis[joint_id], dtype=float).tolist(),
                "range_m": np.asarray(compliant.jnt_range[joint_id], dtype=float).tolist(),
                "stiffness_n_per_m": float(compliant.jnt_stiffness[joint_id]),
                "damping_n_s_per_m": float(compliant.dof_damping[dof]),
                "armature": float(compliant.dof_armature[dof]),
                "frictionloss": float(compliant.dof_frictionloss[dof]),
                "springref": float(compliant.qpos_spring[int(compliant.jnt_qposadr[joint_id])]),
                "solref_limit": np.asarray(compliant.jnt_solref[joint_id], dtype=float).tolist(),
                "body_mass_kg": float(compliant.body_mass[body_id]),
                "geom_size_m": [
                    np.asarray(compliant.geom_size[gid], dtype=float).tolist() for gid in geom_ids
                ],
                "geom_friction": [
                    np.asarray(compliant.geom_friction[gid], dtype=float).tolist() for gid in geom_ids
                ],
                "geom_solref": [
                    np.asarray(compliant.geom_solref[gid], dtype=float).tolist() for gid in geom_ids
                ],
                "geom_solimp": [
                    np.asarray(compliant.geom_solimp[gid], dtype=float).tolist() for gid in geom_ids
                ],
            }
        )
    checks = {
        "rigid_compiled_model_identity": rigid_hash
        == contract["rigid_compatibility_reference"]["compiled_model_sha256"],
        "no_flex": int(compliant.nflex) == 0,
        "exactly_two_added_bodies": int(compliant.nbody - rigid.nbody) == 2
        and len(cap_body_names) == 2,
        "exactly_two_added_slide_joints": int(compliant.njnt - rigid.njnt) == 2
        and len(cap_joint_ids) == 2
        and all(int(compliant.jnt_type[jid]) == int(mujoco.mjtJoint.mjJNT_SLIDE) for jid in cap_joint_ids),
        "options_unchanged": (
            float(compliant.opt.timestep) == float(rigid.opt.timestep)
            and abs(float(compliant.opt.timestep) - 0.00225) <= 1e-15
            and int(compliant.opt.solver) == int(rigid.opt.solver)
            and int(compliant.opt.integrator) == int(rigid.opt.integrator)
            and int(compliant.opt.cone) == int(rigid.opt.cone)
            and int(compliant.opt.iterations) == int(rigid.opt.iterations)
            and int(compliant.opt.ls_iterations) == int(rigid.opt.ls_iterations)
        ),
        "cap_armature_inherited_default": all(
            row["armature"] == 0.005 for row in cap_rows
        ),
        "cap_frictionloss_inherited_default": all(
            row["frictionloss"] == 0.1 for row in cap_rows
        ),
    }
    return {
        "schema_version": "sim2claw.pawn_bg_f2_normal_compliant_cap_compile_audit.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "contract_sha256": sha256_file(contract_path),
        "passed": all(checks.values()),
        "checks": checks,
        "rigid_compiled_model_sha256": rigid_hash,
        "candidate_compiled_model_sha256": compiled_model_sha256(compliant),
        "rigid_counts": {"nbody": rigid.nbody, "njnt": rigid.njnt, "nq": rigid.nq, "nv": rigid.nv, "nflex": rigid.nflex},
        "candidate_counts": {"nbody": compliant.nbody, "njnt": compliant.njnt, "nq": compliant.nq, "nv": compliant.nv, "nflex": compliant.nflex},
        "cap_rows": cap_rows,
        "authority": contract["authority"],
        "claim_boundary": contract["claim_boundary"],
    }


class InitialSettleObserver:
    """Capture the canonical 100-step initial hold, then abort before replay."""

    def __init__(
        self,
        *,
        candidate_id: str,
        output_directory: Path,
        contract: Mapping[str, Any],
        contract_path: Path,
    ) -> None:
        self.candidate_id = candidate_id
        self.output_directory = output_directory
        self.contract = contract
        self.contract_path = contract_path
        self.started = False
        self.rows: dict[str, list[Any]] = {
            "time": [],
            "qpos": [],
            "qvel": [],
            "qacc": [],
            "ctrl": [],
            "robot_qpos": [],
            "robot_qvel": [],
            "cap_qpos": [],
            "cap_qvel": [],
            "cap_qacc": [],
            "pawn_positions": [],
            "pawn_quaternions_wxyz": [],
            "static_positions": [],
            "static_quaternions_wxyz": [],
            "warning_counts": [],
        }
        self.contact_offsets = [0]
        self.contact_geom: list[list[int]] = []
        self.contact_dist: list[float] = []
        self.contact_pos: list[list[float]] = []

    def start(self, *, model: mujoco.MjModel, data: mujoco.MjData) -> None:
        if self.started:
            raise NormalCompliantCapError("initial-settle observer started twice")
        self.started = True
        self.model = model
        body_names = _names(model, mujoco.mjtObj.mjOBJ_BODY, model.nbody)
        joint_names = _names(model, mujoco.mjtObj.mjOBJ_JOINT, model.njnt)
        geom_names = _names(model, mujoco.mjtObj.mjOBJ_GEOM, model.ngeom)
        self.pawn_body_ids = np.asarray(
            [index for index, name in enumerate(body_names) if name.startswith(("brown_pawn_", "tan_pawn_"))],
            dtype=np.int32,
        )
        self.pawn_names = [body_names[index] for index in self.pawn_body_ids]
        self.static_body_ids = np.asarray(
            [
                index
                for index, name in enumerate(body_names)
                if name == "chess_board"
                or "table" in name.lower()
                or "apriltag" in name.lower()
            ],
            dtype=np.int32,
        )
        self.static_names = [body_names[index] for index in self.static_body_ids]
        self.cap_joint_ids = np.asarray(
            [index for index, name in enumerate(joint_names) if name.endswith("_normal_joint")],
            dtype=np.int32,
        )
        self.cap_joint_names = [joint_names[index] for index in self.cap_joint_ids]
        self.cap_qpos_addresses = np.asarray(
            [int(model.jnt_qposadr[index]) for index in self.cap_joint_ids], dtype=np.int32
        )
        self.cap_dof_addresses = np.asarray(
            [int(model.jnt_dofadr[index]) for index in self.cap_joint_ids], dtype=np.int32
        )
        robot_joint_ids = []
        for actuator_id in range(model.nu):
            joint_id = int(model.actuator_trnid[actuator_id, 0])
            if joint_id >= 0 and joint_id not in robot_joint_ids:
                robot_joint_ids.append(joint_id)
        self.robot_joint_names = [joint_names[index] for index in robot_joint_ids]
        self.robot_qpos_addresses = np.asarray(
            [int(model.jnt_qposadr[index]) for index in robot_joint_ids], dtype=np.int32
        )
        self.robot_dof_addresses = np.asarray(
            [int(model.jnt_dofadr[index]) for index in robot_joint_ids], dtype=np.int32
        )
        self.cap_geom_ids = np.asarray(
            [index for index, name in enumerate(geom_names) if "_rubber_tip_" in name],
            dtype=np.int32,
        )
        self.cap_geom_names = [geom_names[index] for index in self.cap_geom_ids]
        self.warning_names = [
            mujoco.mjtWarning(index).name for index in range(int(mujoco.mjtWarning.mjNWARNING))
        ]
        self.preforward = {
            "time": float(data.time),
            "qpos": np.asarray(data.qpos, dtype=float).tolist(),
            "qvel": np.asarray(data.qvel, dtype=float).tolist(),
            "qacc": np.asarray(data.qacc, dtype=float).tolist(),
            "ctrl": np.asarray(data.ctrl, dtype=float).tolist(),
        }

    def _capture(self, *, model: mujoco.MjModel, data: mujoco.MjData) -> None:
        self.rows["time"].append(float(data.time))
        self.rows["qpos"].append(np.asarray(data.qpos, dtype=float).copy())
        self.rows["qvel"].append(np.asarray(data.qvel, dtype=float).copy())
        self.rows["qacc"].append(np.asarray(data.qacc, dtype=float).copy())
        self.rows["ctrl"].append(np.asarray(data.ctrl, dtype=float).copy())
        self.rows["robot_qpos"].append(np.asarray(data.qpos[self.robot_qpos_addresses], dtype=float).copy())
        self.rows["robot_qvel"].append(np.asarray(data.qvel[self.robot_dof_addresses], dtype=float).copy())
        self.rows["cap_qpos"].append(np.asarray(data.qpos[self.cap_qpos_addresses], dtype=float).copy())
        self.rows["cap_qvel"].append(np.asarray(data.qvel[self.cap_dof_addresses], dtype=float).copy())
        self.rows["cap_qacc"].append(np.asarray(data.qacc[self.cap_dof_addresses], dtype=float).copy())
        self.rows["pawn_positions"].append(np.asarray(data.xpos[self.pawn_body_ids], dtype=float).copy())
        self.rows["pawn_quaternions_wxyz"].append(np.asarray(data.xquat[self.pawn_body_ids], dtype=float).copy())
        self.rows["static_positions"].append(np.asarray(data.xpos[self.static_body_ids], dtype=float).copy())
        self.rows["static_quaternions_wxyz"].append(np.asarray(data.xquat[self.static_body_ids], dtype=float).copy())
        self.rows["warning_counts"].append(
            np.asarray([int(data.warning[index].number) for index in range(len(self.warning_names))], dtype=np.int32)
        )
        for contact_index in range(data.ncon):
            contact = data.contact[contact_index]
            self.contact_geom.append(np.asarray(contact.geom, dtype=int).tolist())
            self.contact_dist.append(float(contact.dist))
            self.contact_pos.append(np.asarray(contact.pos, dtype=float).tolist())
        self.contact_offsets.append(len(self.contact_geom))

    def after_forward(self, *, model: mujoco.MjModel, data: mujoco.MjData) -> None:
        self._capture(model=model, data=data)

    def capture(
        self, *, model: mujoco.MjModel, data: mujoco.MjData, settle_step: int
    ) -> None:
        if settle_step != len(self.rows["time"]):
            raise NormalCompliantCapError("initial-settle step order drifted")
        self._capture(model=model, data=data)

    def finish(self, *, model: mujoco.MjModel, data: mujoco.MjData) -> None:
        arrays = {name: np.asarray(values) for name, values in self.rows.items()}
        arrays.update(
            {
                "contact_offsets": np.asarray(self.contact_offsets, dtype=np.int64),
                "contact_geom": np.asarray(self.contact_geom, dtype=np.int32).reshape(-1, 2),
                "contact_dist": np.asarray(self.contact_dist, dtype=np.float64),
                "contact_pos": np.asarray(self.contact_pos, dtype=np.float64).reshape(-1, 3),
            }
        )
        self.output_directory.mkdir(parents=True, exist_ok=True)
        trace_path = self.output_directory / "initial_settle_trace.npz"
        np.savez_compressed(trace_path, **arrays)
        metadata = {
            "schema_version": PREFLIGHT_SCHEMA,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "candidate_id": self.candidate_id,
            "contract_path": str(self.contract_path.relative_to(REPO_ROOT)),
            "contract_sha256": sha256_file(self.contract_path),
            "implementation_path": str(Path(__file__).resolve().relative_to(REPO_ROOT)),
            "implementation_sha256": sha256_file(Path(__file__).resolve()),
            "compiled_model_sha256": compiled_model_sha256(model),
            "timestep_seconds": float(model.opt.timestep),
            "settle_steps": 100,
            "recorded_rows_after_forward_including_initial": len(arrays["time"]),
            "source_action_rows_consumed": 0,
            "state_discarded_after_preflight": True,
            "preforward": self.preforward,
            "robot_joint_names": self.robot_joint_names,
            "cap_joint_names": self.cap_joint_names,
            "cap_joint_ranges_m": np.asarray(model.jnt_range[self.cap_joint_ids], dtype=float).tolist(),
            "cap_geom_ids": self.cap_geom_ids.astype(int).tolist(),
            "cap_geom_names": self.cap_geom_names,
            "geom_names": _names(model, mujoco.mjtObj.mjOBJ_GEOM, model.ngeom),
            "pawn_names": self.pawn_names,
            "static_body_names": self.static_names,
            "warning_names": self.warning_names,
            "array_digest": _array_digest(arrays),
            "trace_path": str(trace_path.relative_to(REPO_ROOT)),
            "trace_sha256": sha256_file(trace_path),
            "producer_pass_fail_is_authoritative": False,
            "authority": self.contract["authority"],
            "claim_boundary": self.contract["claim_boundary"],
        }
        atomic_write_json(self.output_directory / "initial_settle_metadata.json", metadata)
        raise InitialSettleComplete(self.candidate_id)


def run_preflight(
    *, candidate_id: str, output_directory: Path, contract_path: Path = CONTRACT_PATH
) -> dict[str, Any]:
    contract = load_contract(contract_path)
    candidate = _candidate(contract, candidate_id)
    observer = InitialSettleObserver(
        candidate_id=candidate_id,
        output_directory=output_directory,
        contract=contract,
        contract_path=contract_path,
    )
    try:
        run_grasp_episode_probe(
            source_repository_root=REPO_ROOT,
            recording_id=str(contract["source_bindings"]["recording_id"]),
            parameters=_parameters(contract, candidate),
            retention_trace_enabled=False,
            spec_mutator=candidate_spec_mutator(contract, candidate),
            initial_settle_observer=observer,
        )
    except InitialSettleComplete:
        pass
    else:
        raise NormalCompliantCapError("preflight consumed task actions")
    return json.loads(
        (output_directory / "initial_settle_metadata.json").read_text(encoding="utf-8")
    )


def _require_verdict(path: Path, *, candidate_id: str, field: str) -> None:
    if not path.is_file():
        raise NormalCompliantCapError(f"required independent verdict is missing: {path}")
    verdict = json.loads(path.read_text(encoding="utf-8"))
    if verdict.get("candidate_id") != candidate_id or verdict.get(field) is not True:
        raise NormalCompliantCapError(f"required independent gate failed: {path}")


def run_candidate(
    *, candidate_id: str, output_directory: Path, contract_path: Path = CONTRACT_PATH
) -> dict[str, Any]:
    contract = load_contract(contract_path)
    candidate = _candidate(contract, candidate_id)
    if candidate_id == "rigid_legacy_shoulder_control":
        _require_verdict(
            OUTPUT_ROOT / "preflight_normal_compliant_prior_k1000" / "preflight_verdict.json",
            candidate_id="normal_compliant_prior_k1000",
            field="passed",
        )
    else:
        _require_verdict(
            OUTPUT_ROOT / "rigid_legacy_shoulder_control" / "task_verdict.json",
            candidate_id="rigid_legacy_shoulder_control",
            field="compatibility_passed",
        )
        _require_verdict(
            OUTPUT_ROOT / "preflight_normal_compliant_prior_k1000" / "preflight_verdict.json",
            candidate_id="normal_compliant_prior_k1000",
            field="passed",
        )
    model = compile_candidate_model(contract=contract, candidate=candidate)
    model_sha = compiled_model_sha256(model)
    if candidate_id == "rigid_legacy_shoulder_control" and model_sha != contract[
        "rigid_compatibility_reference"
    ]["compiled_model_sha256"]:
        raise NormalCompliantCapError("OR137 rigid compiled model identity failed")
    collector = FullStepTraceCollector(candidate_id=candidate_id, contract=contract)
    probe = run_grasp_episode_probe(
        source_repository_root=REPO_ROOT,
        recording_id=str(contract["source_bindings"]["recording_id"]),
        parameters=_parameters(contract, candidate),
        state_trace_output_directory=output_directory / "inspection_state",
        retention_trace_enabled=True,
        spec_mutator=candidate_spec_mutator(contract, candidate),
        integration_step_observer=collector,
    )
    episode = probe["episode"]
    if (
        episode["action_array_sha256"] != contract["source_bindings"]["action_sha256"]
        or episode["clipped_action_rows"] != 0
        or episode["diagnostic_measured_joint_state_replay"]["enabled"]
    ):
        raise NormalCompliantCapError("OR137 exact action identity drifted")
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
    parser.add_argument("--mode", choices=("compile-audit", "preflight", "task"), required=True)
    parser.add_argument("--candidate")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    args = parser.parse_args(argv)
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    output = args.output.resolve()
    if args.mode == "compile-audit":
        payload = compile_audit(contract_path=args.contract.resolve())
        atomic_write_json(output, payload)
    else:
        if not args.candidate:
            parser.error("--candidate is required")
        if args.mode == "preflight":
            payload = run_preflight(
                candidate_id=args.candidate,
                output_directory=output,
                contract_path=args.contract.resolve(),
            )
        else:
            payload = run_candidate(
                candidate_id=args.candidate,
                output_directory=output,
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
    "NormalCompliantCapError",
    "compile_audit",
    "compile_candidate_model",
    "load_contract",
    "load_raw_contract",
    "run_candidate",
    "run_preflight",
]

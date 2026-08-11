"""OR134 action-frozen F2-to-F1 deformable fingertip-cap replay.

This is a permanently quarantined same-episode simulator diagnostic.  It
changes only the preregistered fingertip contact mechanism, records every
integration step, and leaves pass/fail ownership to the separate verifier.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .mujoco_contact_endpoints import FlexContactSemantic
from .paths import REPO_ROOT
from .pawn_bg_grasp_coordinate_descent import run_grasp_episode_probe


CONTRACT_PATH = (
    REPO_ROOT / "configs" / "evaluations" / "pawn_bg_f2_deformable_cap_v1.json"
)
OUTPUT_ROOT = REPO_ROOT / "outputs" / "pawn_bg_f2_deformable_cap_v1"
SCHEMA = "sim2claw.pawn_bg_f2_deformable_cap.v1"
TRACE_SCHEMA = "sim2claw.pawn_bg_f2_deformable_cap_full_step_trace.v1"
PRODUCER_SCHEMA = "sim2claw.pawn_bg_f2_deformable_cap_producer_receipt.v1"
PHASE_CODE = {"initial": 0, "action_replay": 1, "terminal_settle": 2}


class DeformableCapError(RuntimeError):
    """The frozen OR134 diagnostic cannot run without widening scope."""


def _array_sha256(value: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def _validate_binding(binding: Mapping[str, Any]) -> None:
    path = REPO_ROOT / str(binding["path"])
    if not path.is_file() or sha256_file(path) != str(binding["sha256"]):
        raise DeformableCapError(f"source binding drifted: {binding['path']}")


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DeformableCapError(f"cannot read OR134 contract: {error}") from error
    if contract.get("schema_version") != SCHEMA:
        raise DeformableCapError("unexpected OR134 contract schema")
    _validate_binding(contract["authorization"])
    for value in contract["source_bindings"].values():
        if isinstance(value, dict) and {"path", "sha256"} <= set(value):
            _validate_binding(value)
    if any(contract.get("authority", {}).values()):
        raise DeformableCapError("OR134 external authority widened")
    candidates = contract.get("candidate_order")
    expected = [
        ("rigid_0p91_control", None),
        ("flex_10_kpa", 10000.0),
        ("flex_25_kpa", 25000.0),
        ("flex_63_kpa", 63000.0),
        ("flex_158_kpa", 158000.0),
        ("flex_400_kpa", 400000.0),
    ]
    observed = [
        (row.get("candidate_id"), row.get("youngs_modulus_pa"))
        for row in candidates or []
    ]
    if observed != expected:
        raise DeformableCapError("OR134 candidate order or values drifted")
    invariance = contract.get("action_invariance", {})
    if (
        invariance.get("shape") != [440, 6]
        or invariance.get("dtype") != "float64"
        or invariance.get("per_joint_zoh_delay_seconds") != [0.11] * 6
        or invariance.get("clipped_rows") != 0
        or invariance.get(
            "no_ik_offsets_clipping_retiming_smoothing_suffix_or_override"
        )
        is not True
        or invariance.get("no_measured_state_replay_latch_load_hold_or_force_ramp")
        is not True
    ):
        raise DeformableCapError("OR134 action invariance is not fail closed")
    return contract


def _template_xml(
    *,
    name: str,
    center: list[float],
    count: list[int],
    spacing: list[float],
    pinned: list[int],
    young: float,
    caps: Mapping[str, Any],
) -> str:
    values = {
        "center": " ".join(f"{value:.17g}" for value in center),
        "count": " ".join(str(int(value)) for value in count),
        "spacing": " ".join(f"{value:.17g}" for value in spacing),
        "pinned": " ".join(str(int(value)) for value in pinned),
        "friction": " ".join(f"{float(value):.17g}" for value in caps["friction"]),
        "solref": " ".join(f"{float(value):.17g}" for value in caps["solref"]),
    }
    return f"""
    <mujoco>
      <worldbody>
        <body name="template_parent">
          <flexcomp name="{name}" type="grid" dim="3"
                    pos="{values['center']}" count="{values['count']}"
                    spacing="{values['spacing']}" radius="0"
                    mass="{float(caps['mass_kg_per_cap']):.17g}"
                    dof="trilinear">
            <contact contype="{int(caps['contact_bit'])}" conaffinity="0"
                     condim="{int(caps['condim'])}"
                     friction="{values['friction']}" solref="{values['solref']}"
                     selfcollide="none" internal="false"/>
            <edge equality="false"/>
            <elasticity young="{young:.17g}"
                        poisson="{float(caps['poisson_ratio']):.17g}"
                        damping="{float(caps['damping_seconds']):.17g}"/>
            <pin id="{values['pinned']}"/>
          </flexcomp>
        </body>
      </worldbody>
    </mujoco>
    """


def _add_cap(
    spec: mujoco.MjSpec,
    *,
    cap: Mapping[str, Any],
    caps: Mapping[str, Any],
    young: float,
    rgba: list[float],
) -> None:
    name = str(cap["flex_name"])
    parent_name = str(cap["parent_body"])
    template = mujoco.MjSpec.from_string(
        _template_xml(
            name=name,
            center=[float(value) for value in cap["center_parent_xyz_m"]],
            count=[int(value) for value in cap["count"]],
            spacing=[float(value) for value in cap["spacing_m"]],
            pinned=[int(value) for value in cap["pinned_node_ids"]],
            young=young,
            caps=caps,
        )
    )
    parent = spec.body(parent_name)
    template_flex = template.flexes[0]
    body_names: dict[str, str] = {"template_parent": parent_name}
    for template_body in list(template.bodies)[2:]:
        body_name = str(template_body.name).replace(name, f"{name}_node", 1)
        body_names[str(template_body.name)] = body_name
        body = parent.add_body(
            name=body_name,
            pos=np.asarray(template_body.pos, dtype=np.float64).tolist(),
            quat=np.asarray(template_body.quat, dtype=np.float64).tolist(),
            mass=float(template_body.mass),
            ipos=np.asarray(template_body.ipos, dtype=np.float64).tolist(),
            iquat=np.asarray(template_body.iquat, dtype=np.float64).tolist(),
            inertia=np.asarray(template_body.inertia, dtype=np.float64).tolist(),
            explicitinertial=1,
        )
        for joint_index, template_joint in enumerate(template_body.joints):
            body.add_joint(
                name=f"{body_name}_slide_{joint_index}",
                type=template_joint.type,
                axis=np.asarray(template_joint.axis, dtype=np.float64).tolist(),
            )
    def remap(values: Any) -> list[str]:
        return [body_names[str(value)] for value in values]
    spec.add_flex(
        name=name,
        dim=int(template_flex.dim),
        radius=float(caps["radius_m"]),
        internal=0,
        selfcollide=0,
        contype=int(caps["contact_bit"]),
        conaffinity=0,
        condim=int(caps["condim"]),
        friction=[float(value) for value in caps["friction"]],
        solref=[float(value) for value in caps["solref"]],
        solimp=[float(value) for value in caps["solimp"]],
        young=float(young),
        poisson=float(caps["poisson_ratio"]),
        damping=float(caps["damping_seconds"]),
        cellcount=np.asarray(template_flex.cellcount, dtype=np.int32).tolist(),
        order=int(template_flex.order),
        nodebody=remap(template_flex.nodebody),
        node=np.asarray(template_flex.node, dtype=np.float64).tolist(),
        vertbody=remap(template_flex.vertbody),
        vert=np.asarray(template_flex.vert, dtype=np.float64).tolist(),
        elem=np.asarray(template_flex.elem, dtype=np.int32).tolist(),
        rgba=rgba,
        group=2,
    )


def flex_cap_spec_mutator(
    contract: Mapping[str, Any], young: float
) -> Any:
    """Return the preregistered, result-independent MjSpec mutation."""

    caps = contract["flex_caps"]

    def mutate(spec: mujoco.MjSpec) -> None:
        wrapper_counts = {"fixed": 0, "moving": 0}
        for geom in spec.geoms:
            name = str(geom.name)
            for side in ("fixed", "moving"):
                if str(caps[side]["rigid_wrapper_name_contains"]) in name:
                    geom.contype = 0
                    geom.conaffinity = 0
                    rgba = np.asarray(geom.rgba, dtype=np.float64)
                    rgba[3] = 0.0
                    geom.rgba = rgba.tolist()
                    geom.group = 5
                    wrapper_counts[side] += 1
            parent_name = str(geom.parent.name)
            if parent_name.startswith(("brown_pawn_", "tan_pawn_")) and (
                int(geom.contype) or int(geom.conaffinity)
            ):
                geom.conaffinity = int(geom.conaffinity) | int(caps["contact_bit"])
        if wrapper_counts != {"fixed": 1, "moving": 1}:
            raise DeformableCapError(
                f"rigid wrapper identity drifted: {wrapper_counts}"
            )
        _add_cap(
            spec,
            cap=caps["fixed"],
            caps=caps,
            young=young,
            rgba=[0.1, 0.25, 0.8, 0.85],
        )
        _add_cap(
            spec,
            cap=caps["moving"],
            caps=caps,
            young=young,
            rgba=[0.1, 0.75, 0.35, 0.85],
        )

    return mutate


def flex_semantic_declarations(
    contract: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, tuple[str, str]]:
    if candidate["kind"] != "flex":
        return {}
    caps = contract["flex_caps"]
    return {
        str(caps["fixed"]["flex_name"]): (
            str(caps["fixed"]["parent_body"]),
            "fixed",
        ),
        str(caps["moving"]["flex_name"]): (
            str(caps["moving"]["parent_body"]),
            "moving",
        ),
    }


def _names(model: mujoco.MjModel, kind: mujoco.mjtObj, count: int) -> list[str]:
    return [
        mujoco.mj_id2name(model, kind, index) or f"{kind.name.lower()}_{index}"
        for index in range(count)
    ]


def _model_invariant_payload(
    model: mujoco.MjModel, contact_bit: int
) -> dict[str, Any]:
    """Describe named preexisting scene data with authorized deltas normalized."""

    body_names = _names(model, mujoco.mjtObj.mjOBJ_BODY, model.nbody)
    joint_names = _names(model, mujoco.mjtObj.mjOBJ_JOINT, model.njnt)
    rows: dict[str, Any] = {"bodies": [], "geoms": [], "joints": [], "actuators": []}
    for body_id, name in enumerate(body_names):
        if name.startswith("or134_"):
            continue
        parent_id = int(model.body_parentid[body_id])
        rows["bodies"].append(
            [
                name,
                body_names[parent_id],
                np.asarray(model.body_pos[body_id], dtype=float).tolist(),
                np.asarray(model.body_quat[body_id], dtype=float).tolist(),
                float(model.body_mass[body_id]),
                np.asarray(model.body_inertia[body_id], dtype=float).tolist(),
            ]
        )
    for geom_id, name in enumerate(_names(model, mujoco.mjtObj.mjOBJ_GEOM, model.ngeom)):
        body_name = body_names[int(model.geom_bodyid[geom_id])]
        conaffinity = int(model.geom_conaffinity[geom_id])
        contype = int(model.geom_contype[geom_id])
        rgba = np.asarray(model.geom_rgba[geom_id], dtype=float).tolist()
        group = int(model.geom_group[geom_id])
        if "left_rubber_tip_fixed_" in name or "left_rubber_tip_moving_" in name:
            contype = 1
            conaffinity = 1
            rgba[3] = 1.0
            group = 3
        if body_name.startswith(("brown_pawn_", "tan_pawn_")):
            conaffinity &= ~contact_bit
        rows["geoms"].append(
            [
                name,
                body_name,
                int(model.geom_type[geom_id]),
                np.asarray(model.geom_pos[geom_id], dtype=float).tolist(),
                np.asarray(model.geom_quat[geom_id], dtype=float).tolist(),
                np.asarray(model.geom_size[geom_id], dtype=float).tolist(),
                np.asarray(model.geom_friction[geom_id], dtype=float).tolist(),
                np.asarray(model.geom_solref[geom_id], dtype=float).tolist(),
                np.asarray(model.geom_solimp[geom_id], dtype=float).tolist(),
                contype,
                conaffinity,
                group,
                rgba,
            ]
        )
    for joint_id, name in enumerate(joint_names):
        if name.startswith("or134_"):
            continue
        rows["joints"].append(
            [
                name,
                body_names[int(model.jnt_bodyid[joint_id])],
                int(model.jnt_type[joint_id]),
                np.asarray(model.jnt_pos[joint_id], dtype=float).tolist(),
                np.asarray(model.jnt_axis[joint_id], dtype=float).tolist(),
                np.asarray(model.jnt_range[joint_id], dtype=float).tolist(),
            ]
        )
    for actuator_id, name in enumerate(
        _names(model, mujoco.mjtObj.mjOBJ_ACTUATOR, model.nu)
    ):
        target_id = int(model.actuator_trnid[actuator_id, 0])
        target_name = (
            joint_names[target_id]
            if 0 <= target_id < len(joint_names)
            else f"non_joint_target_{target_id}"
        )
        rows["actuators"].append(
            [
                name,
                target_name,
                int(model.actuator_trnid[actuator_id, 1]),
                np.asarray(model.actuator_ctrlrange[actuator_id], dtype=float).tolist(),
                np.asarray(model.actuator_forcerange[actuator_id], dtype=float).tolist(),
                np.asarray(model.actuator_gainprm[actuator_id], dtype=float).tolist(),
                np.asarray(model.actuator_biasprm[actuator_id], dtype=float).tolist(),
            ]
        )
    return rows


def _model_invariant_digest(model: mujoco.MjModel, contact_bit: int) -> str:
    """Digest the normalized named model payload."""

    return canonical_digest(_model_invariant_payload(model, contact_bit))


def compiled_model_sha256(model: mujoco.MjModel) -> str:
    """Hash MuJoCo's complete compiled binary model representation."""

    with tempfile.TemporaryDirectory(prefix="sim2claw-model-signature-") as directory:
        path = Path(directory) / "model.mjb"
        mujoco.mj_saveModel(model, str(path))
        return sha256_file(path)


class FullStepTraceCollector:
    """Preallocated full-integration-step trace with complete contact identity."""

    def __init__(self, *, candidate_id: str, contract: Mapping[str, Any]) -> None:
        self.candidate_id = candidate_id
        self.contract = contract
        self.started = False
        self.finished = False
        self.index = 0
        self.arrays: dict[str, np.ndarray] = {}
        self.contact_offsets = [0]
        self.contact_step: list[int] = []
        self.contact_geom: list[list[int]] = []
        self.contact_flex: list[list[int]] = []
        self.contact_elem: list[list[int]] = []
        self.contact_vert: list[list[int]] = []
        self.contact_pos: list[list[float]] = []
        self.contact_frame: list[list[float]] = []
        self.contact_force: list[list[float]] = []
        self.contact_dim: list[int] = []
        self.contact_dist: list[float] = []
        self.metadata: dict[str, Any] = {}

    def start(
        self,
        *,
        model: mujoco.MjModel,
        data: mujoco.MjData,
        expected_step_count: int,
        selected_body: int,
        selected_dof: int,
        piece_bodies: Mapping[str, int],
        initial_piece_positions: Mapping[str, np.ndarray],
        target_position_xyz_m: np.ndarray,
        robot_body_ids: set[int],
        fixed_jaw_body_ids: set[int],
        moving_jaw_body_ids: set[int],
        flex_semantics: Mapping[int, FlexContactSemantic],
        actuator_ids: list[int],
        qpos_addresses: list[int],
        timestep: float,
    ) -> None:
        if self.started:
            raise DeformableCapError("full-step trace collector started twice")
        self.started = True
        self.expected_step_count = int(expected_step_count)
        self.selected_body = int(selected_body)
        self.selected_dof = int(selected_dof)
        self.piece_names = sorted(piece_bodies)
        self.piece_body_ids = np.asarray(
            [piece_bodies[name] for name in self.piece_names], dtype=np.int32
        )
        self.actuator_ids = np.asarray(actuator_ids, dtype=np.int32)
        self.qpos_addresses = np.asarray(qpos_addresses, dtype=np.int32)
        count = self.expected_step_count
        self.arrays = {
            "time": np.empty(count, dtype=np.float64),
            "phase": np.empty(count, dtype=np.int8),
            "source_indices": np.empty((count, 6), dtype=np.int32),
            "requested_action": np.empty((count, 6), dtype=np.float64),
            "applied_ctrl": np.empty((count, 6), dtype=np.float64),
            "qpos": np.empty((count, model.nq), dtype=np.float64),
            "qvel": np.empty((count, model.nv), dtype=np.float64),
            "selected_position": np.empty((count, 3), dtype=np.float64),
            "selected_quaternion_wxyz": np.empty((count, 4), dtype=np.float64),
            "selected_linear_velocity": np.empty((count, 3), dtype=np.float64),
            "selected_angular_velocity": np.empty((count, 3), dtype=np.float64),
            "piece_positions": np.empty(
                (count, len(self.piece_names), 3), dtype=np.float64
            ),
            "piece_quaternions_wxyz": np.empty(
                (count, len(self.piece_names), 4), dtype=np.float64
            ),
        }
        body_names = _names(model, mujoco.mjtObj.mjOBJ_BODY, model.nbody)
        geom_names = _names(model, mujoco.mjtObj.mjOBJ_GEOM, model.ngeom)
        flex_names = _names(model, mujoco.mjtObj.mjOBJ_FLEX, model.nflex)
        initial_piece_quaternions = {
            name: np.asarray(data.xquat[piece_bodies[name]], dtype=float).tolist()
            for name in self.piece_names
        }
        model_invariant_payload = _model_invariant_payload(
            model, int(self.contract["flex_caps"]["contact_bit"])
        )
        self.metadata = {
            "schema_version": TRACE_SCHEMA,
            "candidate_id": self.candidate_id,
            "recording_id": self.contract["source_bindings"]["recording_id"],
            "timestep_seconds": float(timestep),
            "expected_step_count": count,
            "selected_body_id": self.selected_body,
            "selected_body_name": body_names[self.selected_body],
            "piece_names": self.piece_names,
            "piece_body_ids": self.piece_body_ids.astype(int).tolist(),
            "initial_piece_positions": {
                name: np.asarray(initial_piece_positions[name], dtype=float).tolist()
                for name in self.piece_names
            },
            "initial_piece_quaternions_wxyz": initial_piece_quaternions,
            "target_position_xyz_m": np.asarray(
                target_position_xyz_m, dtype=float
            ).tolist(),
            "body_names": body_names,
            "geom_names": geom_names,
            "geom_body_ids": np.asarray(model.geom_bodyid, dtype=int).tolist(),
            "flex_names": flex_names,
            "flex_semantics": [
                {
                    "flex_id": int(flex_id),
                    "flex_name": semantic.flex_name,
                    "body_id": int(semantic.body_id),
                    "body_name": semantic.body_name,
                    "role": semantic.role,
                }
                for flex_id, semantic in sorted(flex_semantics.items())
            ],
            "robot_body_ids": sorted(int(value) for value in robot_body_ids),
            "fixed_jaw_body_ids": sorted(int(value) for value in fixed_jaw_body_ids),
            "moving_jaw_body_ids": sorted(int(value) for value in moving_jaw_body_ids),
            "board_support_body_names": ["chess_board"],
            "actuator_ids": self.actuator_ids.astype(int).tolist(),
            "robot_qpos_addresses": self.qpos_addresses.astype(int).tolist(),
            "model_invariant_payload": model_invariant_payload,
            "model_invariant_digest": canonical_digest(model_invariant_payload),
            "compiled_model_sha256": compiled_model_sha256(model),
            "runtime_initial_original_body_pose_digest": canonical_digest(
                [
                    [
                        body_names[body_id],
                        np.asarray(data.xpos[body_id], dtype=float).tolist(),
                        np.asarray(data.xquat[body_id], dtype=float).tolist(),
                    ]
                    for body_id in range(model.nbody)
                    if not body_names[body_id].startswith("or134_")
                ]
            ),
            "authority": self.contract["authority"],
        }

    def capture(
        self,
        *,
        model: mujoco.MjModel,
        data: mujoco.MjData,
        episode_time_s: float,
        source_indices: np.ndarray,
        requested_action: np.ndarray,
        phase: str,
    ) -> None:
        if not self.started or self.finished:
            raise DeformableCapError("full-step trace collector is not active")
        if self.index >= self.expected_step_count:
            raise DeformableCapError("full-step trace exceeded preregistered length")
        row = self.index
        self.arrays["time"][row] = float(episode_time_s)
        self.arrays["phase"][row] = PHASE_CODE[phase]
        self.arrays["source_indices"][row] = source_indices
        self.arrays["requested_action"][row] = requested_action
        self.arrays["applied_ctrl"][row] = data.ctrl[self.actuator_ids]
        self.arrays["qpos"][row] = data.qpos
        self.arrays["qvel"][row] = data.qvel
        self.arrays["selected_position"][row] = data.xpos[self.selected_body]
        self.arrays["selected_quaternion_wxyz"][row] = data.xquat[
            self.selected_body
        ]
        self.arrays["selected_linear_velocity"][row] = data.qvel[
            self.selected_dof : self.selected_dof + 3
        ]
        self.arrays["selected_angular_velocity"][row] = data.qvel[
            self.selected_dof + 3 : self.selected_dof + 6
        ]
        self.arrays["piece_positions"][row] = data.xpos[self.piece_body_ids]
        self.arrays["piece_quaternions_wxyz"][row] = data.xquat[
            self.piece_body_ids
        ]
        for contact_index in range(data.ncon):
            contact = data.contact[contact_index]
            force = np.zeros(6, dtype=np.float64)
            if int(contact.efc_address) >= 0:
                mujoco.mj_contactForce(model, data, contact_index, force)
            self.contact_step.append(row)
            self.contact_geom.append(np.asarray(contact.geom, dtype=int).tolist())
            self.contact_flex.append(np.asarray(contact.flex, dtype=int).tolist())
            self.contact_elem.append(np.asarray(contact.elem, dtype=int).tolist())
            self.contact_vert.append(np.asarray(contact.vert, dtype=int).tolist())
            self.contact_pos.append(np.asarray(contact.pos, dtype=float).tolist())
            self.contact_frame.append(np.asarray(contact.frame, dtype=float).tolist())
            self.contact_force.append(force.astype(float).tolist())
            self.contact_dim.append(int(contact.dim))
            self.contact_dist.append(float(contact.dist))
        self.contact_offsets.append(len(self.contact_step))
        self.index += 1

    def finish(self, *, model: mujoco.MjModel, data: mujoco.MjData) -> None:
        if self.index != self.expected_step_count:
            raise DeformableCapError(
                f"full-step trace length mismatch: {self.index} != "
                f"{self.expected_step_count}"
            )
        warning_rows = []
        for warning_id in range(int(mujoco.mjtWarning.mjNWARNING)):
            count = int(data.warning[warning_id].number)
            if count:
                warning_rows.append(
                    {
                        "name": mujoco.mjtWarning(warning_id).name,
                        "count": count,
                        "last_info": int(data.warning[warning_id].lastinfo),
                    }
                )
        self.metadata["warning_rows"] = warning_rows
        self.metadata["observed_step_count"] = self.index
        self.metadata["contact_count"] = len(self.contact_step)
        self.finished = True

    def write(self, output_directory: Path) -> dict[str, Any]:
        if not self.finished:
            raise DeformableCapError("full-step trace is not finished")
        output_directory.mkdir(parents=True, exist_ok=True)
        trace_path = output_directory / "full_step_trace.npz"
        arrays = {
            **self.arrays,
            "contact_offsets": np.asarray(self.contact_offsets, dtype=np.int64),
            "contact_step": np.asarray(self.contact_step, dtype=np.int32),
            "contact_geom": np.asarray(self.contact_geom, dtype=np.int32).reshape(-1, 2),
            "contact_flex": np.asarray(self.contact_flex, dtype=np.int32).reshape(-1, 2),
            "contact_elem": np.asarray(self.contact_elem, dtype=np.int32).reshape(-1, 2),
            "contact_vert": np.asarray(self.contact_vert, dtype=np.int32).reshape(-1, 2),
            "contact_pos": np.asarray(self.contact_pos, dtype=np.float64).reshape(-1, 3),
            "contact_frame": np.asarray(self.contact_frame, dtype=np.float64).reshape(-1, 9),
            "contact_force": np.asarray(self.contact_force, dtype=np.float64).reshape(-1, 6),
            "contact_dim": np.asarray(self.contact_dim, dtype=np.int8),
            "contact_dist": np.asarray(self.contact_dist, dtype=np.float64),
        }
        np.savez_compressed(trace_path, **arrays)
        digest = hashlib.sha256()
        for name in sorted(arrays):
            value = np.ascontiguousarray(arrays[name])
            digest.update(name.encode("utf-8"))
            digest.update(value.dtype.str.encode("ascii"))
            digest.update(np.asarray(value.shape, dtype=np.int64).tobytes())
            digest.update(value.tobytes())
        self.metadata["array_digest"] = digest.hexdigest()
        self.metadata["array_file"] = trace_path.name
        self.metadata["array_file_sha256"] = sha256_file(trace_path)
        metadata_path = output_directory / "full_step_trace_metadata.json"
        atomic_write_json(metadata_path, self.metadata)
        return {
            "trace_path": str(trace_path.relative_to(REPO_ROOT)),
            "trace_file_sha256": sha256_file(trace_path),
            "metadata_path": str(metadata_path.relative_to(REPO_ROOT)),
            "metadata_sha256": sha256_file(metadata_path),
            "array_digest": self.metadata["array_digest"],
            "step_count": self.index,
            "contact_count": len(self.contact_step),
            "model_invariant_digest": self.metadata["model_invariant_digest"],
            "runtime_initial_original_body_pose_digest": self.metadata[
                "runtime_initial_original_body_pose_digest"
            ],
        }


def _candidate(contract: Mapping[str, Any], candidate_id: str) -> dict[str, Any]:
    matches = [
        row for row in contract["candidate_order"] if row["candidate_id"] == candidate_id
    ]
    if len(matches) != 1:
        raise DeformableCapError(f"candidate is not preregistered: {candidate_id}")
    return dict(matches[0])


def run_candidate(
    *,
    candidate_id: str,
    output_directory: Path,
    contract_path: Path = CONTRACT_PATH,
) -> dict[str, Any]:
    contract = load_contract(contract_path)
    candidate = _candidate(contract, candidate_id)
    collector = FullStepTraceCollector(candidate_id=candidate_id, contract=contract)
    young = candidate["youngs_modulus_pa"]
    spec_mutator = (
        None if young is None else flex_cap_spec_mutator(contract, float(young))
    )
    declarations = flex_semantic_declarations(contract, candidate)
    state_directory = output_directory / "inspection_state"
    probe = run_grasp_episode_probe(
        source_repository_root=REPO_ROOT,
        recording_id=str(contract["source_bindings"]["recording_id"]),
        parameters=dict(contract["rigid_parameters"]),
        state_trace_output_directory=state_directory,
        retention_trace_enabled=True,
        spec_mutator=spec_mutator,
        flex_semantic_declarations=declarations,
        integration_step_observer=collector,
    )
    episode = probe["episode"]
    expected_action = str(contract["source_bindings"]["action_sha256"])
    if (
        episode["action_array_sha256"] != expected_action
        or episode["action_sha256"] != expected_action
        or episode["clipped_action_rows"] != 0
    ):
        raise DeformableCapError("action provenance drifted during candidate replay")
    if episode["diagnostic_measured_joint_state_replay"]["enabled"]:
        raise DeformableCapError("measured-state forcing is forbidden")
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
            "application_delay_seconds_by_joint": episode[
                "application_delay_seconds_by_joint"
            ],
        },
        "producer_episode_summary": episode,
        "full_step_trace": trace,
        "producer_pass_fail_is_authoritative": False,
        "authority": contract["authority"],
        "claim_boundary": contract["claim_boundary"],
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    output_directory.mkdir(parents=True, exist_ok=True)
    receipt_path = output_directory / "producer_receipt.json"
    atomic_write_json(receipt_path, receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    args = parser.parse_args(argv)
    os.environ.setdefault("OMP_NUM_THREADS", "1")
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
    "DeformableCapError",
    "FullStepTraceCollector",
    "compiled_model_sha256",
    "flex_cap_spec_mutator",
    "flex_semantic_declarations",
    "load_contract",
    "run_candidate",
]

"""Read-only internal-step introspection of the exact OR19 replay."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
)
from .observable_registration_belief_recalculation import (
    REPO_ROOT,
    _bound_json,
    _bound_path,
)
from .observable_registration_unilateral_push_dynamic_replay import (
    load_unilateral_push_dynamic_replay_contract,
    run_unilateral_push_dynamic_replay_once,
)
from .realized_action_outcome_mission import _rotation, _tensor, _tilt

SCHEMA = (
    "sim2claw.observable_registration_exact_replay_contact_introspection_contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_exact_replay_contact_introspection_receipt.v1"
)
TRACE_SCHEMA = (
    "sim2claw.observable_registration_exact_replay_contact_introspection_trace.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "observable_registration_exact_replay_contact_introspection_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs/observable_registration_exact_replay_contact_introspection_v1"
)
JAW_BODY_NAMES = {"left_gripper", "left_moving_jaw_so101_v1"}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _name(
    model: mujoco.MjModel, object_type: mujoco.mjtObj, object_id: int
) -> str:
    return (
        mujoco.mj_id2name(model, object_type, object_id)
        or f"{object_type.name.lower()}-{object_id}"
    )


def load_exact_replay_contact_introspection_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR21 contact introspection")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
    policy = contract["introspection"]
    _require(
        policy["one_run_only"] is True
        and policy["internal_step_seconds"] == 0.005
        and policy["capture_all_task_and_terminal_settle_steps"] is True,
        "introspection identity widened",
    )
    forbidden = (
        "model_change_allowed",
        "configuration_change_allowed",
        "action_change_allowed",
        "parameter_selection_allowed",
        "camera_fit_allowed",
    )
    _require(
        all(policy[name] is False for name in forbidden),
        "introspection mutation enabled",
    )
    _require(
        contract["reporting"]["require_exact_or19_receipt_reproduction"]
        is True
        and contract["reporting"]["global_mapping_approval_allowed"] is False
        and contract["reporting"]["transfer_claim_allowed"] is False,
        "reporting boundary widened",
    )
    authority = contract["authority"]
    _require(
        authority["simulator_replay"] is True
        and not any(
            value
            for name, value in authority.items()
            if name != "simulator_replay"
        ),
        "authority widened",
    )
    return contract


def _object_velocity(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    object_type: mujoco.mjtObj,
    object_id: int,
) -> np.ndarray:
    velocity = np.zeros(6, dtype=np.float64)
    mujoco.mj_objectVelocity(
        model, data, object_type, object_id, velocity, 0
    )
    return velocity


def _contact_observations(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    *,
    selected_body: int,
    jaw_body_names: set[str] | None = None,
) -> tuple[list[dict[str, Any]], set[str], bool]:
    if jaw_body_names is None:
        jaw_body_names = JAW_BODY_NAMES
    observations: list[dict[str, Any]] = []
    jaw_bodies: set[str] = set()
    support = False
    pawn_position = np.asarray(data.xpos[selected_body], dtype=np.float64)
    for index in range(data.ncon):
        contact = data.contact[index]
        geom1 = int(contact.geom1)
        geom2 = int(contact.geom2)
        body1 = int(model.geom_bodyid[geom1])
        body2 = int(model.geom_bodyid[geom2])
        if selected_body not in (body1, body2):
            continue
        other_body = body2 if body1 == selected_body else body1
        other_name = _name(
            model, mujoco.mjtObj.mjOBJ_BODY, other_body
        )
        if other_name == "chess_board":
            support = True
        if other_name in jaw_body_names:
            jaw_bodies.add(other_name)

        force = np.zeros(6, dtype=np.float64)
        mujoco.mj_contactForce(model, data, index, force)
        frame = np.asarray(contact.frame, dtype=np.float64).reshape(3, 3)
        normal = frame[0].copy()
        selected_geom = geom1 if body1 == selected_body else geom2
        other_geom = geom2 if selected_geom == geom1 else geom1
        selected_velocity = _object_velocity(
            model,
            data,
            mujoco.mjtObj.mjOBJ_GEOM,
            selected_geom,
        )
        other_velocity = _object_velocity(
            model,
            data,
            mujoco.mjtObj.mjOBJ_GEOM,
            other_geom,
        )
        position = np.asarray(contact.pos, dtype=np.float64)
        selected_linear = selected_velocity[3:] + np.cross(
            selected_velocity[:3],
            position - np.asarray(data.geom_xpos[selected_geom]),
        )
        other_linear = other_velocity[3:] + np.cross(
            other_velocity[:3],
            position - np.asarray(data.geom_xpos[other_geom]),
        )
        relative = other_linear - selected_linear
        tangent = relative - normal * float(relative @ normal)
        observations.append(
            {
                "contact_index": index,
                "selected_geom": _name(
                    model, mujoco.mjtObj.mjOBJ_GEOM, selected_geom
                ),
                "other_geom": _name(
                    model, mujoco.mjtObj.mjOBJ_GEOM, other_geom
                ),
                "other_body": other_name,
                "selected_is_geom1": body1 == selected_body,
                "distance_m": float(contact.dist),
                "position_world_m": position.tolist(),
                "frame_rows_world": frame.tolist(),
                "mujoco_contact_frame_force_torque_raw": force.tolist(),
                "relative_contact_velocity_world_m_s": relative.tolist(),
                "tangential_slip_speed_m_s": float(
                    np.linalg.norm(tangent)
                ),
                "contact_offset_from_pawn_root_world_m": (
                    position - pawn_position
                ).tolist(),
            }
        )
    return observations, jaw_bodies, support


def _first_row(
    rows: list[dict[str, Any]], predicate: Any
) -> dict[str, Any] | None:
    return next((row for row in rows if predicate(row)), None)


def run_exact_replay_contact_introspection_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR21 one-run receipt already exists")
    contract = load_exact_replay_contact_introspection_contract(
        contract_path, root=root
    )
    sources = contract["sources"]
    expected_or19 = _bound_json(
        sources["or19_receipt"], root=root, label="OR19 receipt"
    )
    or19_contract_path = _bound_path(
        sources["or19_contract"], root=root, label="OR19 contract"
    )
    _, c6 = load_unilateral_push_dynamic_replay_contract(
        or19_contract_path, root=root
    )
    timestamps = _tensor(
        _bound_path(
            c6["source"]["timestamps"], root=root, label="timestamps"
        ),
        c6["source"]["timestamps"],
    )
    selected_name = c6["initialization"]["selected_piece"]
    reporting = contract["reporting"]
    rows: list[dict[str, Any]] = []
    state: dict[str, Any] = {
        "setup_seen": False,
        "task_step": 0,
        "total_task_steps": None,
        "boundaries": None,
        "selected_body": None,
        "selected_dof": None,
    }
    original_step = mujoco.mj_step

    def instrumented_step(
        model: mujoco.MjModel,
        data: mujoco.MjData,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        original_step(model, data, *args, **kwargs)
        requested_nstep = int(
            kwargs.get("nstep", args[0] if args else 1)
        )
        if not state["setup_seen"]:
            _require(
                requested_nstep == 100,
                "OR19 setup settle identity changed",
            )
            _require(
                abs(float(model.opt.timestep) - 0.005) < 1e-12,
                "OR19 internal timestep changed",
            )
            state["setup_seen"] = True
            interval_steps = np.asarray(
                [
                    max(
                        1,
                        round(
                            float(timestamps[index] - timestamps[index - 1])
                            / float(model.opt.timestep)
                        ),
                    )
                    for index in range(1, len(timestamps))
                ],
                dtype=np.int64,
            )
            state["boundaries"] = np.cumsum(interval_steps)
            state["total_task_steps"] = int(
                state["boundaries"][-1]
            )
            selected_body = mujoco.mj_name2id(
                model, mujoco.mjtObj.mjOBJ_BODY, selected_name
            )
            selected_joint = mujoco.mj_name2id(
                model,
                mujoco.mjtObj.mjOBJ_JOINT,
                f"{selected_name}_free",
            )
            _require(
                selected_body >= 0 and selected_joint >= 0,
                "selected pawn introspection binding missing",
            )
            state["selected_body"] = selected_body
            state["selected_dof"] = int(
                model.jnt_dofadr[selected_joint]
            )
            return

        _require(
            requested_nstep == 1,
            "OR19 task step width changed",
        )
        state["task_step"] += 1
        internal_index = int(state["task_step"])
        total_task_steps = int(state["total_task_steps"])
        phase = (
            "task" if internal_index <= total_task_steps else "terminal_settle"
        )
        if phase == "task":
            source_index = int(
                np.searchsorted(
                    state["boundaries"], internal_index, side="left"
                )
                + 1
            )
        else:
            source_index = len(timestamps) - 1
        selected_body = int(state["selected_body"])
        selected_dof = int(state["selected_dof"])
        contacts, jaw_bodies, support = _contact_observations(
            model, data, selected_body=selected_body
        )
        velocity = np.asarray(
            data.qvel[selected_dof : selected_dof + 6],
            dtype=np.float64,
        )
        rows.append(
            {
                "internal_step_index": internal_index,
                "phase": phase,
                "source_sample_index": source_index,
                "source_timestamp_seconds": float(
                    timestamps[source_index]
                ),
                "simulator_time_seconds": float(data.time),
                "selected_pawn_position_m": np.asarray(
                    data.xpos[selected_body], dtype=np.float64
                ).tolist(),
                "selected_pawn_quaternion_wxyz": np.asarray(
                    data.xquat[selected_body], dtype=np.float64
                ).tolist(),
                "selected_pawn_tilt_degrees": _tilt(
                    _rotation(data, selected_body)
                ),
                "selected_pawn_linear_velocity_m_s": velocity[
                    :3
                ].tolist(),
                "selected_pawn_angular_velocity_rad_s": velocity[
                    3:
                ].tolist(),
                "board_support_contact": support,
                "named_jaw_contact_bodies": sorted(jaw_bodies),
                "named_jaw_contact_state": (
                    "bilateral"
                    if len(jaw_bodies) >= 2
                    else ("unilateral" if jaw_bodies else "none")
                ),
                "contacts": contacts,
            }
        )

    reproduction_directory = output_directory / "or19_reproduction"
    mujoco.mj_step = instrumented_step
    try:
        reproduced_or19 = run_unilateral_push_dynamic_replay_once(
            contract_path=or19_contract_path,
            output_directory=reproduction_directory,
            root=root,
        )
    finally:
        mujoco.mj_step = original_step

    exact_receipt_match = reproduced_or19 == expected_or19
    _require(
        exact_receipt_match,
        "OR19 receipt did not reproduce exactly; introspection rejected",
    )
    _require(rows, "OR21 internal trace is empty")
    analysis_rows = [
        row
        for row in rows
        if row["phase"] == "task"
        and int(reporting["analysis_source_sample_start"])
        <= row["source_sample_index"]
        <= int(reporting["analysis_source_sample_end"])
    ]
    first_jaw = _first_row(
        analysis_rows,
        lambda row: row["named_jaw_contact_state"] != "none",
    )
    first_bilateral = _first_row(
        analysis_rows,
        lambda row: row["named_jaw_contact_state"] == "bilateral",
    )
    first_orientation = _first_row(
        analysis_rows,
        lambda row: row["selected_pawn_tilt_degrees"]
        >= float(reporting["orientation_event_threshold_degrees"]),
    )
    first_slip = _first_row(
        analysis_rows,
        lambda row: any(
            contact["other_body"] in JAW_BODY_NAMES
            and contact["tangential_slip_speed_m_s"]
            >= float(reporting["slip_event_threshold_m_s"])
            for contact in row["contacts"]
        ),
    )
    support_loss_minimum = int(
        reporting["support_loss_minimum_consecutive_steps"]
    )
    first_support_loss: dict[str, Any] | None = None
    for index in range(len(analysis_rows) - support_loss_minimum + 1):
        window = analysis_rows[index : index + support_loss_minimum]
        if all(not row["board_support_contact"] for row in window):
            first_support_loss = window[0]
            break

    maximum_jaw_force = 0.0
    maximum_jaw_slip = 0.0
    for row in analysis_rows:
        for contact in row["contacts"]:
            if contact["other_body"] not in JAW_BODY_NAMES:
                continue
            maximum_jaw_force = max(
                maximum_jaw_force,
                abs(
                    float(
                        contact[
                            "mujoco_contact_frame_force_torque_raw"
                        ][0]
                    )
                ),
            )
            maximum_jaw_slip = max(
                maximum_jaw_slip,
                float(contact["tangential_slip_speed_m_s"]),
            )

    def event(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "internal_step_index": row["internal_step_index"],
            "source_sample_index": row["source_sample_index"],
            "source_timestamp_seconds": row["source_timestamp_seconds"],
            "simulator_time_seconds": row["simulator_time_seconds"],
        }

    trace_payload = {
        "schema_version": TRACE_SCHEMA,
        "proof_class": contract["proof_class"],
        "contact_force_semantics": (
            "raw_mujoco_contact_frame_force_torque_no_physical_force_claim"
        ),
        "rows": rows,
    }
    trace_path = output_directory / "internal_trace.json"
    atomic_write_json(trace_path, trace_payload)
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": "PASS_EXACT_REPRODUCTION_CONTACT_TRACE",
        "source_identity": {
            "row_count": expected_or19["source_identity"]["row_count"],
            "requested_sha256": expected_or19["source_identity"][
                "requested_sha256"
            ],
            "gateway_sent_sha256": expected_or19["source_identity"][
                "gateway_sent_sha256"
            ],
            "timestamps_sha256": expected_or19["source_identity"][
                "timestamps_sha256"
            ],
            "identified_applied_sha256": expected_or19[
                "source_identity"
            ]["identified_applied_sha256"],
            "actions_changed": False,
        },
        "or19_reproduction": {
            "exact_receipt_match": exact_receipt_match,
            "expected_artifact_sha256": expected_or19["artifact_sha256"],
            "reproduced_artifact_sha256": reproduced_or19[
                "artifact_sha256"
            ],
            "selected_contact_sample": reproduced_or19["dynamics"][
                "first_selected_jaw_contact_sample"
            ],
            "first_motion_sample": reproduced_or19["dynamics"][
                "first_motion_over_1mm_sample"
            ],
            "signed_progress_m": reproduced_or19["dynamics"][
                "signed_progress_toward_d2_m"
            ],
            "final_tilt_degrees": reproduced_or19["outcome"][
                "final_upright_tilt_degrees"
            ],
            "final_height_error_m": reproduced_or19["outcome"][
                "final_height_error_m"
            ],
            "maximum_other_piece_displacement_m": reproduced_or19[
                "outcome"
            ]["maximum_other_piece_displacement_m"],
        },
        "trace_summary": {
            "internal_step_seconds": contract["introspection"][
                "internal_step_seconds"
            ],
            "internal_step_count": len(rows),
            "task_internal_step_count": sum(
                row["phase"] == "task" for row in rows
            ),
            "terminal_settle_internal_step_count": sum(
                row["phase"] == "terminal_settle" for row in rows
            ),
            "analysis_source_sample_window": [
                reporting["analysis_source_sample_start"],
                reporting["analysis_source_sample_end"],
            ],
            "analysis_internal_step_count": len(analysis_rows),
            "first_named_jaw_contact": event(first_jaw),
            "first_named_jaw_contact_source_sample": (
                first_jaw["source_sample_index"]
                if first_jaw is not None
                else None
            ),
            "first_bilateral_jaw_contact": event(first_bilateral),
            "first_orientation_over_threshold": event(first_orientation),
            "first_support_loss": event(first_support_loss),
            "first_jaw_slip_over_threshold": event(first_slip),
            "maximum_named_jaw_normal_force_raw": maximum_jaw_force,
            "maximum_named_jaw_tangential_slip_speed_m_s": (
                maximum_jaw_slip
            ),
            "internal_trace_sha256": _sha256(trace_path),
        },
        "parameter_selection_performed": False,
        "simulator_mutated": False,
        "global_mapping_approved": False,
        "transfer_claim": False,
        "authority": contract["authority"],
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


def main() -> int:
    run_exact_replay_contact_introspection_once()
    return 0

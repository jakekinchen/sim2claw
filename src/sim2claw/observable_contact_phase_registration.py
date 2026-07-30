"""Proof-safe named-geometry contact-phase gate for the retained C6 episode."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from .exact_applied_state_schedule import build_exact_applied_state_schedule
from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .named_jaw_contact import (
    measure_named_jaw_contact,
    resolve_named_contact_geometry,
)
from .observable_jaw_aperture_replay import _bound_json, _bound_path
from .paths import REPO_ROOT
from .realized_action_outcome_mission import (
    _tensor,
    load_contract as load_c6_contract,
    physical_to_model,
)
from .recorded_replay import _compile_model


SCHEMA = "sim2claw.observable_contact_phase_registration_contract.v1"
RECEIPT_SCHEMA = "sim2claw.observable_contact_phase_registration_receipt.v1"
TRACE_SCHEMA = "sim2claw.observable_contact_phase_registration_trace.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "observable_contact_phase_registration_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT / "outputs" / "observable_contact_phase_registration_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_contact_phase_contract(
    path: Path = CONTRACT_PATH,
    *,
    root: Path = REPO_ROOT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = load_json_object(path, label="contact phase registration")
    _require(
        contract.get("schema_version") == SCHEMA,
        "unsupported contact phase schema",
    )
    sources = contract.get("sources")
    _require(isinstance(sources, dict) and sources, "contact sources are missing")
    for source_id, binding in sources.items():
        _require(isinstance(binding, dict), f"invalid source: {source_id}")
        _bound_path(binding, root=root, label=source_id)
    c6 = load_c6_contract(
        _bound_path(sources["c6_contract"], root=root, label="C6 contract"),
        root=root,
    )
    identity = contract.get("identity")
    _require(
        isinstance(identity, dict)
        and identity.get("recording_id") == c6["source"]["recording_id"]
        and int(identity.get("row_count", 0)) == 531
        and int(identity.get("joint_count", 0)) == 6,
        "contact identity changed",
    )
    for field, source_field in (
        ("requested_sha256", "requested"),
        ("gateway_sent_sha256", "gateway_sent"),
        ("timestamps_sha256", "timestamps"),
        ("identified_applied_sha256", "identified_applied"),
    ):
        _require(
            identity.get(field) == c6["source"][source_field]["sha256"],
            f"{field} changed",
        )
    fit_policy = contract.get("fit_policy")
    _require(
        isinstance(fit_policy, dict)
        and fit_policy.get("task_rows_allowed_in_fit") is False
        and fit_policy.get("task_outcome_allowed_in_fit") is False
        and fit_policy.get("contact_timing_allowed_in_fit") is False
        and fit_policy.get("one_mechanism_family_only") is True
        and fit_policy.get("heldout_refit_allowed") is False,
        "contact fit policy widened",
    )
    schedule = contract.get("schedule")
    _require(
        isinstance(schedule, dict)
        and schedule.get("physics_integration_allowed") is False
        and schedule.get("forward_kinematics_only") is True
        and schedule.get("preserve_source_row_order") is True
        and schedule.get("preserve_source_timestamps") is True,
        "contact schedule widened",
    )
    phase_gate = contract.get("phase_gate")
    _require(
        isinstance(phase_gate, dict)
        and int(phase_gate.get("last_definitely_separate_sample", -1)) == 224
        and phase_gate.get("candidate_contact_samples") == [228, 232]
        and phase_gate.get("unrelated_contact_allowed") is False,
        "contact phase gate changed",
    )
    boundaries = contract.get("proof_boundaries")
    authority = contract.get("authority")
    _require(
        isinstance(boundaries, dict)
        and boundaries
        and not any(boundaries.values()),
        "contact proof boundary widened",
    )
    _require(
        isinstance(authority, dict)
        and authority
        and not any(authority.values()),
        "contact authority widened",
    )
    or3 = _bound_json(sources["or3_closeout"], root=root, label="OR3")
    _require(
        or3["physical_events"]["candidate_contact_interval_samples"]
        == phase_gate["candidate_contact_samples"],
        "physical contact interval changed",
    )
    return contract, c6


def _initialize_kinematic_state(
    model: mujoco.MjModel,
    candidate: dict[str, Any],
    initial_model: np.ndarray,
    *,
    selected_piece: str,
    initial_xy: np.ndarray,
    support_z: float,
) -> tuple[mujoco.MjData, np.ndarray, np.ndarray, int]:
    data = mujoco.MjData(model)
    joint_ids = np.asarray(
        [
            mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            for name in candidate["bindings"]["joint_names"]
        ],
        dtype=np.int64,
    )
    _require(bool(np.all(joint_ids >= 0)), "robot joint binding is incomplete")
    qpos_addresses = np.asarray(
        [int(model.jnt_qposadr[joint_id]) for joint_id in joint_ids],
        dtype=np.int64,
    )
    dof_addresses = np.asarray(
        [int(model.jnt_dofadr[joint_id]) for joint_id in joint_ids],
        dtype=np.int64,
    )
    selected_body = int(
        mujoco.mj_name2id(
            model,
            mujoco.mjtObj.mjOBJ_BODY,
            selected_piece,
        )
    )
    selected_joint = int(
        mujoco.mj_name2id(
            model,
            mujoco.mjtObj.mjOBJ_JOINT,
            f"{selected_piece}_free",
        )
    )
    _require(
        selected_body >= 0 and selected_joint >= 0,
        "selected pawn binding is incomplete",
    )
    selected_qpos = int(model.jnt_qposadr[selected_joint])
    data.qpos[qpos_addresses] = initial_model
    data.qpos[selected_qpos : selected_qpos + 2] = initial_xy
    data.qpos[selected_qpos + 2] = support_z
    data.qvel[:] = 0.0
    mujoco.mj_forward(model, data)
    return data, qpos_addresses, dof_addresses, selected_body


def _source_hashes_unchanged(
    contract: dict[str, Any],
    c6: dict[str, Any],
) -> bool:
    identity = contract["identity"]
    return all(
        identity[field] == c6["source"][source]["sha256"]
        for field, source in (
            ("requested_sha256", "requested"),
            ("gateway_sent_sha256", "gateway_sent"),
            ("timestamps_sha256", "timestamps"),
            ("identified_applied_sha256", "identified_applied"),
        )
    )


def build_contact_phase_receipt(
    contract_path: Path = CONTRACT_PATH,
    output_path: Path = OUTPUT_DIRECTORY / "receipt.json",
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract, c6 = load_contact_phase_contract(contract_path, root=root)
    source = c6["source"]
    applied_physical = _tensor(
        _bound_path(source["identified_applied"], root=root, label="applied"),
        source["identified_applied"],
    )
    timestamps = _tensor(
        _bound_path(source["timestamps"], root=root, label="timestamps"),
        source["timestamps"],
    )
    initial_measured = _tensor(
        _bound_path(
            source["initial_measured"],
            root=root,
            label="initial measured",
        ),
        source["initial_measured"],
    )
    candidate_manifest = _bound_json(
        contract["sources"]["or6_candidate"],
        root=root,
        label="OR6 candidate",
    )
    candidate = candidate_manifest["candidate_config"]
    _require(
        candidate_manifest.get("candidate_config_sha256")
        == contract["sources"]["or6_candidate"]["candidate_config_sha256"]
        == canonical_digest(candidate),
        "OR6 candidate identity changed",
    )
    factor_receipt = _bound_json(
        contract["sources"]["factor_isolation_receipt"],
        root=root,
        label="factor isolation",
    )
    _require(
        factor_receipt.get("artifact_sha256")
        == contract["sources"]["factor_isolation_receipt"]["artifact_sha256"],
        "factor isolation artifact changed",
    )
    or7_receipt = _bound_json(
        contract["sources"]["or7_receipt"],
        root=root,
        label="OR7 receipt",
    )
    _require(
        or7_receipt.get("artifact_sha256")
        == contract["sources"]["or7_receipt"]["artifact_sha256"],
        "OR7 receipt artifact changed",
    )
    endpoint = _bound_json(
        contract["sources"]["initial_endpoint_receipt"],
        root=root,
        label="initial endpoint",
    )
    initial_xy = np.asarray(
        endpoint["observations"]["initial"]["world_position_m"][:2],
        dtype=np.float64,
    )
    applied_model = physical_to_model(
        applied_physical,
        {"candidate_config": candidate},
    )
    initial_model = physical_to_model(
        initial_measured[:1],
        {"candidate_config": candidate},
    )[0]
    schedule = build_exact_applied_state_schedule(
        applied_model,
        timestamps,
        timestep_seconds=float(contract["schedule"]["timestep_seconds"]),
    )
    model, _ = _compile_model(candidate, base_directory=None)
    data, qpos_addresses, dof_addresses, selected_body = (
        _initialize_kinematic_state(
            model,
            candidate,
            initial_model,
            selected_piece=str(contract["identity"]["selected_piece"]),
            initial_xy=initial_xy,
            support_z=float(or7_receipt["initialization"]["pawn_support_z_m"]),
        )
    )
    geometry_contract = contract["geometry"]
    geometry = resolve_named_contact_geometry(
        model,
        selected_body_name=str(contract["identity"]["selected_piece"]),
        fixed_jaw_prefix=str(geometry_contract["fixed_jaw_prefix"]),
        moving_jaw_prefix=str(geometry_contract["moving_jaw_prefix"]),
        fixed_tip_names=geometry_contract["fixed_tip_geoms"],
        moving_tip_names=geometry_contract["moving_tip_geoms"],
    )
    _require(
        geometry.selected_body_id == selected_body,
        "named pawn body identity changed",
    )
    last_phase_sample = int(contract["phase_gate"]["candidate_contact_samples"][1])
    trace_rows: list[dict[str, Any]] = []
    for step in schedule.rows:
        if step.source_sample_index > last_phase_sample:
            break
        data.qpos[qpos_addresses] = np.asarray(step.qpos, dtype=np.float64)
        data.qvel[dof_addresses] = np.asarray(step.qvel, dtype=np.float64)
        mujoco.mj_forward(model, data)
        measured = measure_named_jaw_contact(
            model,
            data,
            geometry,
            distance_maximum_m=float(geometry_contract["distance_maximum_m"]),
            other_pad_tolerance_m=float(
                contract["phase_gate"]["other_pad_maximum_distance_m"]
            ),
        )
        trace_rows.append({**step.to_dict(), **measured})

    separate_sample = int(
        contract["phase_gate"]["last_definitely_separate_sample"]
    )
    contact_first, contact_last = [
        int(value) for value in contract["phase_gate"]["candidate_contact_samples"]
    ]
    precontact_rows = [
        row
        for row in trace_rows
        if int(row["source_sample_index"]) <= separate_sample
    ]
    contact_rows = [
        row
        for row in trace_rows
        if contact_first <= int(row["source_sample_index"]) <= contact_last
    ]
    first_contact = next(
        (
            row
            for row in contact_rows
            if row["phase_contact_geometry_pass"]
            and not row["unrelated_pawn_contact_pairs"]
        ),
        None,
    )
    minimum_precontact_clearance = min(
        min(
            float(row["fixed"]["signed_distance_m"]),
            float(row["moving"]["signed_distance_m"]),
        )
        for row in precontact_rows
    )
    precontact_clear = bool(
        minimum_precontact_clearance
        >= float(contract["phase_gate"]["minimum_precontact_clearance_m"])
        and all(not row["exact_named_contact_pairs"] for row in precontact_rows)
        and all(
            not row["unrelated_pawn_contact_pairs"] for row in precontact_rows
        )
    )
    sample_232 = next(
        row
        for row in reversed(contact_rows)
        if int(row["source_sample_index"]) == contact_last
    )
    promotable_spatial_candidate = bool(
        factor_receipt.get("result")
        == contract["fit_policy"]["factor_isolation_required_result"]
        and factor_receipt.get("canonical_parameter_update_authorized") is True
    )
    phase_pass = bool(precontact_clear and first_contact is not None)
    dynamics_authorized = bool(promotable_spatial_candidate and phase_pass)
    result = (
        "STATIC_AND_PHASE_ADMITTED_DYNAMICS_SUCCESSOR_REQUIRED"
        if dynamics_authorized
        else (
            "FROZEN_RETAINED_CANDIDATE_MISSES_NAMED_CONTACT_PHASE_NO_DYNAMICS"
            if not phase_pass
            else "PHASE_DIAGNOSTIC_ONLY_NO_PROMOTABLE_SPATIAL_CANDIDATE"
        )
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path = output_path.with_name("trace.json")
    trace = {
        "schema_version": TRACE_SCHEMA,
        "rows": trace_rows,
    }
    atomic_write_json(trace_path, trace)
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "contract_sha256": sha256_file(contract_path),
        "identity": {
            "recording_id": contract["identity"]["recording_id"],
            "row_count": len(applied_physical),
            "joint_count": int(applied_physical.shape[1]),
            "source_hashes_unchanged": _source_hashes_unchanged(contract, c6),
            "requested_sha256": source["requested"]["sha256"],
            "gateway_sent_sha256": source["gateway_sent"]["sha256"],
            "timestamps_sha256": source["timestamps"]["sha256"],
            "identified_applied_sha256": source["identified_applied"]["sha256"],
            "candidate_config_sha256": canonical_digest(candidate),
        },
        "schedule": {
            "source_row_count": len(schedule.interval_step_counts),
            "internal_row_count": len(schedule.rows),
            "timestep_seconds": schedule.timestep_seconds,
            "maximum_timestamp_quantization_error_seconds": (
                schedule.maximum_timestamp_quantization_error_seconds
            ),
            "physics_integration_steps": 0,
        },
        "static_admission": {
            "factor_isolation_result": factor_receipt["result"],
            "factor_isolation_artifact_sha256": factor_receipt["artifact_sha256"],
            "promotable_spatial_candidate": promotable_spatial_candidate,
            "task_rows_used_for_fit": 0,
            "task_outcome_used_for_fit": False,
            "heldout_refit_performed": False,
        },
        "phase": {
            "last_definitely_separate_sample": separate_sample,
            "candidate_contact_samples": [contact_first, contact_last],
            "minimum_precontact_clearance_m": minimum_precontact_clearance,
            "precontact_clear": precontact_clear,
            "first_named_contact_source_sample": (
                int(first_contact["source_sample_index"])
                if first_contact is not None
                else None
            ),
            "first_named_contact_source_timestamp_seconds": (
                float(first_contact["source_timestamp_seconds"])
                if first_contact is not None
                else None
            ),
            "contact_at_expected_phase": first_contact is not None,
            "sample_232": {
                "fixed_signed_distance_m": float(
                    sample_232["fixed"]["signed_distance_m"]
                ),
                "moving_signed_distance_m": float(
                    sample_232["moving"]["signed_distance_m"]
                ),
                "pawn_center_bracketed": bool(
                    sample_232["pawn_center_bracketed"]
                ),
                "phase_contact_geometry_pass": bool(
                    sample_232["phase_contact_geometry_pass"]
                ),
                "fixed_jaw_geom": sample_232["fixed"]["jaw_geom"],
                "moving_jaw_geom": sample_232["moving"]["jaw_geom"],
                "pawn_geom": sample_232["fixed"]["pawn_geom"],
            },
        },
        "dynamics": {
            "authorized": dynamics_authorized,
            "run_count": 0,
            "reason": (
                "all_static_and_kinematic_gates_pass"
                if dynamics_authorized
                else "static_or_phase_prerequisite_failed"
            ),
        },
        "proof_boundaries": dict(contract["proof_boundaries"]),
        "authority": dict(contract["authority"]),
        "trace": {
            "path": trace_path.relative_to(root).as_posix()
            if root.resolve() in trace_path.resolve().parents
            else trace_path.resolve().as_posix(),
            "sha256": sha256_file(trace_path),
            "row_count": len(trace_rows),
        },
        "result": result,
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_path, receipt)
    return receipt


def main() -> int:
    receipt = build_contact_phase_receipt()
    print(receipt["result"])
    return 0


__all__ = [
    "CONTRACT_PATH",
    "OUTPUT_DIRECTORY",
    "build_contact_phase_receipt",
    "load_contact_phase_contract",
    "main",
]

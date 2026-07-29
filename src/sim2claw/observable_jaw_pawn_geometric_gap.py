"""Measure the signed jaw-to-pawn gap at exact applied states."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .observable_jaw_aperture_replay import _bound_json, _bound_path
from .realized_action_outcome_mission import (
    _tensor,
    load_contract as load_c6_contract,
    physical_to_model,
)
from .recorded_replay import _compile_model
from .paths import REPO_ROOT


SCHEMA = "sim2claw.observable_jaw_pawn_geometric_gap_contract.v1"
RECEIPT_SCHEMA = "sim2claw.observable_jaw_pawn_geometric_gap_receipt.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "observable_jaw_pawn_geometric_gap_v1.json"
)
OUTPUT_PATH = (
    REPO_ROOT
    / "outputs"
    / "observable_jaw_pawn_geometric_gap_v1"
    / "receipt.json"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_gap_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = load_json_object(path, label="observable jaw pawn gap")
    _require(contract.get("schema_version") == SCHEMA, "unsupported gap schema")
    sources = contract.get("sources")
    _require(isinstance(sources, dict) and sources, "gap sources are missing")
    for source_id, binding in sources.items():
        _require(isinstance(binding, dict), f"invalid gap source: {source_id}")
        _bound_path(binding, root=root, label=source_id)
    c6 = load_c6_contract(
        _bound_path(sources["c6_contract"], root=root, label="C6 contract"),
        root=root,
    )
    or3 = _bound_json(
        sources["or3_closeout"], root=root, label="OR3 closeout"
    )
    identity = contract.get("identity")
    _require(
        isinstance(identity, dict)
        and identity.get("recording_id") == c6["source"]["recording_id"]
        and int(identity.get("row_count", 0)) == 531
        and identity.get("candidate_contact_interval_samples")
        == or3["physical_events"]["candidate_contact_interval_samples"]
        and int(identity.get("first_definite_enclosure_sample", -1))
        == int(or3["physical_events"]["first_definite_enclosure_sample"])
        and int(identity.get("first_definite_carried_motion_sample", -1))
        == int(or3["physical_events"]["definite_carried_motion_interval_samples"][0]),
        "gap event identity changed",
    )
    evaluation = contract.get("evaluation")
    _require(
        isinstance(evaluation, dict)
        and evaluation.get("mappings")
        == ["immutable_c6_baseline", "or6_gripper_zero_offset"]
        and evaluation.get("physics_integration_allowed") is False
        and evaluation.get("forward_kinematics_allowed") is True
        and all(
            evaluation.get(field) is False
            for field in (
                "parameter_fit_allowed",
                "task_outcome_read_for_parameter_selection",
                "contact_material_change_allowed",
                "object_change_allowed",
                "camera_change_allowed",
                "joint_mapping_change_allowed",
                "global_transform_change_allowed",
            )
        ),
        "gap diagnostic widened",
    )
    boundaries = contract.get("proof_boundaries")
    authority = contract.get("authority")
    _require(
        isinstance(boundaries, dict) and boundaries and not any(boundaries.values()),
        "gap proof boundary widened",
    )
    _require(
        isinstance(authority, dict) and authority and not any(authority.values()),
        "gap authority widened",
    )
    return contract, c6


def _ids_by_name(
    model: mujoco.MjModel, names: list[str], object_type: mujoco.mjtObj
) -> list[int]:
    ids = [
        mujoco.mj_name2id(model, object_type, name)
        for name in names
    ]
    _require(min(ids) >= 0, f"named MuJoCo objects are missing: {names}")
    return ids


def _initialize(
    model: mujoco.MjModel,
    candidate: dict[str, Any],
    initial_model: np.ndarray,
    observed_initial_xy: np.ndarray,
    selected_name: str,
) -> tuple[mujoco.MjData, np.ndarray, int, int, np.ndarray]:
    data = mujoco.MjData(model)
    joint_names = candidate["bindings"]["joint_names"]
    joint_ids = _ids_by_name(model, joint_names, mujoco.mjtObj.mjOBJ_JOINT)
    qpos_addresses = np.asarray(
        [int(model.jnt_qposadr[item]) for item in joint_ids], dtype=np.int64
    )
    selected_body = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, selected_name
    )
    selected_joint = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, f"{selected_name}_free"
    )
    _require(selected_body >= 0 and selected_joint >= 0, "selected pawn is missing")
    selected_qpos = int(model.jnt_qposadr[selected_joint])
    data.qpos[qpos_addresses] = initial_model
    mujoco.mj_forward(model, data)
    mujoco.mj_step(model, data, nstep=100)
    support_z = float(data.qpos[selected_qpos + 2])
    upright = np.asarray(
        data.qpos[selected_qpos + 3 : selected_qpos + 7],
        dtype=np.float64,
    ).copy()
    data.qpos[selected_qpos : selected_qpos + 2] = observed_initial_xy
    data.qpos[selected_qpos + 2] = support_z
    data.qpos[selected_qpos + 3 : selected_qpos + 7] = upright
    data.qpos[qpos_addresses] = initial_model
    data.qvel[:] = 0.0
    mujoco.mj_forward(model, data)
    return data, qpos_addresses, selected_body, selected_qpos, upright


def _jaw_geom_ids(
    model: mujoco.MjModel,
    prefixes: list[str],
) -> list[int]:
    result = []
    for geom_id in range(model.ngeom):
        name = (
            mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_id)
            or ""
        )
        if any(name.startswith(prefix) for prefix in prefixes):
            result.append(geom_id)
    _require(result, "named jaw collision geoms are missing")
    return result


def _pawn_geom_ids(model: mujoco.MjModel, selected_body: int) -> list[int]:
    result = [
        geom_id
        for geom_id in range(model.ngeom)
        if int(model.geom_bodyid[geom_id]) == selected_body
        and int(model.geom_contype[geom_id]) != 0
    ]
    _require(result, "selected pawn collision geoms are missing")
    return result


def _geom_name(model: mujoco.MjModel, geom_id: int) -> str:
    return (
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_id)
        or f"unnamed_geom_{geom_id}"
    )


def _sample_gap(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    *,
    jaw_geoms: list[int],
    pawn_geoms: list[int],
    fixed_tips: list[int],
    moving_tips: list[int],
    selected_body: int,
    distance_maximum: float,
) -> dict[str, Any]:
    nearest: dict[str, Any] | None = None
    for jaw_geom in jaw_geoms:
        for pawn_geom in pawn_geoms:
            fromto = np.zeros(6, dtype=np.float64)
            distance = float(
                mujoco.mj_geomDistance(
                    model,
                    data,
                    jaw_geom,
                    pawn_geom,
                    distance_maximum,
                    fromto,
                )
            )
            if nearest is None or distance < nearest["signed_distance_m"]:
                nearest = {
                    "signed_distance_m": distance,
                    "jaw_geom": _geom_name(model, jaw_geom),
                    "pawn_geom": _geom_name(model, pawn_geom),
                    "nearest_point_on_jaw_m": fromto[:3].tolist(),
                    "nearest_point_on_pawn_m": fromto[3:].tolist(),
                }
    _require(nearest is not None, "no jaw pawn geom pair was evaluated")
    fixed = np.mean(data.geom_xpos[fixed_tips], axis=0)
    moving = np.mean(data.geom_xpos[moving_tips], axis=0)
    midpoint = (fixed + moving) / 2.0
    pawn_center = np.asarray(data.xpos[selected_body], dtype=np.float64)
    return {
        **nearest,
        "fixed_tip_center_m": fixed.tolist(),
        "moving_tip_center_m": moving.tolist(),
        "jaw_tip_midpoint_m": midpoint.tolist(),
        "pawn_center_m": pawn_center.tolist(),
        "midpoint_to_pawn_vector_m": (pawn_center - midpoint).tolist(),
        "midpoint_to_pawn_distance_m": float(
            np.linalg.norm(pawn_center - midpoint)
        ),
        "jaw_tip_center_separation_m": float(np.linalg.norm(moving - fixed)),
    }


def _evaluate_mapping(
    candidate: dict[str, Any],
    applied_physical: np.ndarray,
    initial_measured: np.ndarray,
    observed_initial_xy: np.ndarray,
    *,
    selected_name: str,
    first_sample: int,
    last_sample: int,
    geometry: dict[str, Any],
) -> dict[str, Any]:
    wrapper = {"candidate_config": candidate}
    applied_model = physical_to_model(applied_physical, wrapper)
    initial_model = physical_to_model(initial_measured[:1], wrapper)[0]
    model, _ = _compile_model(candidate, base_directory=None)
    data, qpos_addresses, selected_body, _, _ = _initialize(
        model,
        candidate,
        initial_model,
        observed_initial_xy,
        selected_name,
    )
    jaw_geoms = _jaw_geom_ids(
        model, [str(value) for value in geometry["named_jaw_geom_prefixes"]]
    )
    pawn_geoms = _pawn_geom_ids(model, selected_body)
    fixed_tips = _ids_by_name(
        model,
        [str(value) for value in geometry["fixed_tip_geoms"]],
        mujoco.mjtObj.mjOBJ_GEOM,
    )
    moving_tips = _ids_by_name(
        model,
        [str(value) for value in geometry["moving_tip_geoms"]],
        mujoco.mjtObj.mjOBJ_GEOM,
    )
    rows = []
    for sample_index in range(first_sample, last_sample + 1):
        data.qpos[qpos_addresses] = applied_model[sample_index]
        data.qvel[:] = 0.0
        mujoco.mj_forward(model, data)
        rows.append(
            {
                "sample_index": sample_index,
                **_sample_gap(
                    model,
                    data,
                    jaw_geoms=jaw_geoms,
                    pawn_geoms=pawn_geoms,
                    fixed_tips=fixed_tips,
                    moving_tips=moving_tips,
                    selected_body=selected_body,
                    distance_maximum=float(geometry["distance_maximum_m"]),
                ),
            }
        )
    minimum = min(rows, key=lambda row: row["signed_distance_m"])
    return {
        "rows": rows,
        "minimum_signed_distance_m": minimum["signed_distance_m"],
        "minimum_distance_sample": minimum["sample_index"],
        "minimum_distance_jaw_geom": minimum["jaw_geom"],
        "minimum_distance_pawn_geom": minimum["pawn_geom"],
    }


def evaluate_geometric_gap(
    contract: dict[str, Any],
    c6: dict[str, Any],
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    source = c6["source"]
    applied_physical = _tensor(
        _bound_path(source["identified_applied"], root=root, label="applied"),
        source["identified_applied"],
    )
    initial_measured = _tensor(
        _bound_path(source["initial_measured"], root=root, label="measured"),
        source["initial_measured"],
    )
    base_manifest = load_json_object(
        root / c6["lineage"]["joint_mapping_manifest"]["path"],
        label="C6 mapping manifest",
    )
    or6_manifest = _bound_json(
        contract["sources"]["or6_candidate"],
        root=root,
        label="OR6 candidate",
    )
    _require(
        or6_manifest.get("candidate_config_sha256")
        == contract["sources"]["or6_candidate"]["candidate_config_sha256"],
        "OR6 candidate config changed",
    )
    endpoint = load_json_object(
        root / c6["lineage"]["initial_endpoint_receipt"]["path"],
        label="initial endpoint",
    )
    initial_xy = np.asarray(
        endpoint["observations"]["initial"]["world_position_m"][:2],
        dtype=np.float64,
    )
    identity = contract["identity"]
    first_sample, last_sample = [
        int(value) for value in identity["evaluation_interval_samples"]
    ]
    geometry = contract["geometry"]
    baseline = _evaluate_mapping(
        base_manifest["candidate_config"],
        applied_physical,
        initial_measured,
        initial_xy,
        selected_name=identity["selected_piece"],
        first_sample=first_sample,
        last_sample=last_sample,
        geometry=geometry,
    )
    candidate = _evaluate_mapping(
        or6_manifest["candidate_config"],
        applied_physical,
        initial_measured,
        initial_xy,
        selected_name=identity["selected_piece"],
        first_sample=first_sample,
        last_sample=last_sample,
        geometry=geometry,
    )
    baseline_by_sample = {
        int(row["sample_index"]): row for row in baseline["rows"]
    }
    candidate_by_sample = {
        int(row["sample_index"]): row for row in candidate["rows"]
    }
    report_rows = []
    for sample_index in identity["report_samples"]:
        baseline_row = baseline_by_sample[int(sample_index)]
        candidate_row = candidate_by_sample[int(sample_index)]
        report_rows.append(
            {
                "sample_index": int(sample_index),
                "baseline": baseline_row,
                "candidate": candidate_row,
                "candidate_minus_baseline_signed_distance_m": float(
                    candidate_row["signed_distance_m"]
                    - baseline_row["signed_distance_m"]
                ),
                "candidate_minus_baseline_midpoint_to_pawn_vector_m": (
                    np.asarray(
                        candidate_row["midpoint_to_pawn_vector_m"],
                        dtype=np.float64,
                    )
                    - np.asarray(
                        baseline_row["midpoint_to_pawn_vector_m"],
                        dtype=np.float64,
                    )
                ).tolist(),
            }
        )
    candidate_reduction = float(
        baseline["minimum_signed_distance_m"]
        - candidate["minimum_signed_distance_m"]
    )
    candidate_contact = bool(
        candidate["minimum_signed_distance_m"]
        <= float(geometry["geometric_contact_tolerance_m"])
    )
    materially_closed = bool(
        candidate_reduction >= float(geometry["material_gap_reduction_m"])
        and candidate_contact
    )
    large_residual = bool(
        candidate["minimum_signed_distance_m"]
        > float(geometry["large_residual_gap_m"])
    )
    classification = (
        "APERTURE_MAPPING_CLOSES_KINEMATIC_CONTACT_GAP"
        if materially_closed
        else (
            "LARGE_JAW_CENTER_OR_GLOBAL_WRIST_SPATIAL_GAP_REMAINS"
            if large_residual
            else "SUB_5MM_PAD_OR_CONTACT_BOUNDARY_REMAINS"
        )
    )
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "contract_sha256": (
            sha256_file(CONTRACT_PATH)
            if root == REPO_ROOT and CONTRACT_PATH.is_file()
            else canonical_digest(contract)
        ),
        "identity": {
            "recording_id": source["recording_id"],
            "applied_sha256": source["identified_applied"]["sha256"],
            "row_count": len(applied_physical),
            "evaluation_interval_samples": [first_sample, last_sample],
            "physics_steps": 0,
            "parameters_fit": 0,
        },
        "baseline": {
            key: value for key, value in baseline.items() if key != "rows"
        },
        "candidate": {
            key: value for key, value in candidate.items() if key != "rows"
        },
        "report_rows": report_rows,
        "comparison": {
            "minimum_gap_reduction_m": candidate_reduction,
            "candidate_reaches_geometric_contact_tolerance": candidate_contact,
            "aperture_mapping_materially_closes_spatial_gap": materially_closed,
            "large_residual_gap_remains": large_residual,
        },
        "classification": classification,
        "proof_boundaries": contract["proof_boundaries"],
        "authority": contract["authority"],
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def build_geometric_gap_receipt(
    contract_path: Path = CONTRACT_PATH,
    output_path: Path = OUTPUT_PATH,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract, c6 = load_gap_contract(contract_path, root=root)
    receipt = evaluate_geometric_gap(contract, c6, root=root)
    atomic_write_json(output_path, receipt)
    return receipt


__all__ = [
    "CONTRACT_PATH",
    "OUTPUT_PATH",
    "build_geometric_gap_receipt",
    "evaluate_geometric_gap",
    "load_gap_contract",
]

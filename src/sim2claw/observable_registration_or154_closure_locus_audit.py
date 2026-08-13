"""Reproduce OR154's closure-locus discrepancy without stepping dynamics."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from .current_workcell import current_square_center
from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .observable_registration_belief_recalculation import REPO_ROOT, _bound_path
from .observable_registration_or153_exact_d1_center_replay import (
    load_exact_d1_center_replay_contract,
)
from .observable_registration_unilateral_push_dynamic_replay import (
    load_unilateral_push_dynamic_replay_contract,
)
from .observable_registration_visible_divergence_video import _candidate_config
from .post_hackathon_home_workspace_geometry_camera import _candidate_spec


SCHEMA = "sim2claw.observable_registration_or154_closure_locus_audit_contract.v1"
RECEIPT_SCHEMA = "sim2claw.observable_registration_or154_closure_locus_audit_receipt.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "observable_registration_or154_closure_locus_audit_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT / "outputs" / "observable_registration_or154_closure_locus_audit_v1"
)
AUDIT_SAMPLES = (224, 228, 232, 236, 241)
CONTACT_SAMPLE = 271
MOTION_SAMPLE = 292
JAW_BODY_NAMES = ("left_gripper", "left_moving_jaw_so101_v1")
FIXED_TIP_NAMES = tuple(f"left_fixed_jaw_sph_tip{index}" for index in (1, 2, 3))
MOVING_TIP_NAMES = tuple(
    f"left_moving_jaw_sph_tip{index}" for index in (1, 2, 3)
)
EXECUTION_BOUNDARY = {
    "mujoco_forward_calls": len(AUDIT_SAMPLES) + 1,
    "mujoco_step_calls": 0,
    "simulator_replays": 0,
    "fits": 0,
    "searches": 0,
    "renders": 0,
    "task_evaluations": 0,
    "action_or_timestamp_mutations": 0,
    "hardware_actions": 0,
    "paid_compute": False,
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _load_array(binding: dict[str, Any], *, root: Path, label: str) -> np.ndarray:
    path = _bound_path(binding, root=root, label=label)
    values = np.fromfile(path, dtype=np.dtype(binding["dtype"]))
    result = values.reshape(binding["shape"])
    _require(sha256_file(path) == binding["sha256"], f"{label} hash changed")
    return result


def _object_id(
    model: mujoco.MjModel,
    object_type: mujoco.mjtObj,
    name: str,
) -> int:
    value = mujoco.mj_name2id(model, object_type, name)
    _require(value >= 0, f"missing MuJoCo object: {name}")
    return value


def _object_name(
    model: mujoco.MjModel,
    object_type: mujoco.mjtObj,
    object_id: int,
) -> str:
    return mujoco.mj_id2name(model, object_type, object_id) or ""


def _first_closed_hold(
    values: np.ndarray, *, after_sample: int, minimum_run: int = 10
) -> int:
    closed_value = float(np.min(values))
    closed = np.flatnonzero(np.isclose(values, closed_value, atol=1e-6, rtol=0.0))
    _require(closed.size >= minimum_run, "closed-command hold is absent")
    for start in closed:
        if int(start) <= after_sample:
            continue
        stop = int(start) + minimum_run
        if stop <= values.shape[0] and bool(
            np.all(np.isclose(values[int(start):stop], closed_value, atol=1e-6, rtol=0.0))
        ):
            return int(start)
    raise FactoryArtifactError("closed-command hold is shorter than required")


def _collision_geoms_for_bodies(
    model: mujoco.MjModel, body_names: tuple[str, ...]
) -> list[int]:
    body_ids = {
        _object_id(model, mujoco.mjtObj.mjOBJ_BODY, name) for name in body_names
    }
    result = [
        geom_id
        for geom_id in range(model.ngeom)
        if int(model.geom_bodyid[geom_id]) in body_ids
        and int(model.geom_contype[geom_id]) != 0
    ]
    _require(result, "gripper collision geometry is absent")
    return result


def _pawn_collision_geoms(model: mujoco.MjModel, body_id: int) -> list[int]:
    result = [
        geom_id
        for geom_id in range(model.ngeom)
        if int(model.geom_bodyid[geom_id]) == body_id
        and int(model.geom_contype[geom_id]) != 0
    ]
    _require(result, "selected-pawn collision geometry is absent")
    return result


def _collision_rows(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    *,
    gripper_geoms: list[int],
    pawn_geoms: list[int],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for gripper_geom in gripper_geoms:
        for pawn_geom in pawn_geoms:
            points = np.zeros(6, dtype=np.float64)
            distance = float(
                mujoco.mj_geomDistance(
                    model,
                    data,
                    gripper_geom,
                    pawn_geom,
                    0.2,
                    points,
                )
            )
            geom_name = _object_name(
                model, mujoco.mjtObj.mjOBJ_GEOM, gripper_geom
            )
            data_id = int(model.geom_dataid[gripper_geom])
            mesh_name = (
                _object_name(model, mujoco.mjtObj.mjOBJ_MESH, data_id)
                if int(model.geom_type[gripper_geom])
                == int(mujoco.mjtGeom.mjGEOM_MESH)
                and data_id >= 0
                else None
            )
            rows.append(
                {
                    "signed_distance_m": distance,
                    "gripper_geom_id": gripper_geom,
                    "gripper_geom_name": geom_name,
                    "gripper_body_name": _object_name(
                        model,
                        mujoco.mjtObj.mjOBJ_BODY,
                        int(model.geom_bodyid[gripper_geom]),
                    ),
                    "gripper_mesh_name": mesh_name,
                    "pawn_geom_id": pawn_geom,
                    "pawn_geom_name": _object_name(
                        model, mujoco.mjtObj.mjOBJ_GEOM, pawn_geom
                    ),
                    "named_jaw_geom": geom_name.startswith(
                        ("left_fixed_jaw_", "left_moving_jaw_")
                    ),
                    "nearest_points_m": points.tolist(),
                }
            )
    rows.sort(key=lambda row: float(row["signed_distance_m"]))
    return rows


def load_closure_locus_audit_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR155 closure-locus audit")
    _require(contract.get("schema_version") == SCHEMA, "unsupported OR155 contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
    audit = contract["audit"]
    _require(
        audit["samples"] == list(AUDIT_SAMPLES)
        and audit["or154_first_broad_contact_sample"] == CONTACT_SAMPLE
        and audit["or154_first_motion_over_1mm_sample"] == MOTION_SAMPLE
        and audit["known_result_reproduction"] is True,
        "OR155 audit identity changed",
    )
    _require(contract["execution"] == EXECUTION_BOUNDARY, "OR155 execution widened")
    _require(not any(contract["claim_limits"].values()), "OR155 claim widened")
    return contract


def run_closure_locus_audit(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    _require(not output_directory.exists(), "OR155 write-once output already exists")
    contract = load_closure_locus_audit_contract(contract_path, root=root)
    source_hashes_before = {
        name: sha256_file(root / binding["path"])
        for name, binding in contract["sources"].items()
    }

    or154_contract = load_exact_d1_center_replay_contract(
        _bound_path(
            contract["sources"]["or154_contract"], root=root, label="OR154 contract"
        ),
        root=root,
    )
    or154_receipt = load_json_object(
        _bound_path(
            contract["sources"]["or154_receipt"], root=root, label="OR154 receipt"
        ),
        label="OR154 receipt",
    )
    or154_trace = load_json_object(
        _bound_path(
            contract["sources"]["or154_trace"], root=root, label="OR154 trace"
        ),
        label="OR154 trace",
    )
    _require(
        len(or154_trace["rows"]) == 531
        and [row["sample_index"] for row in or154_trace["rows"]] == list(range(531)),
        "OR154 trace identity changed",
    )
    _require(
        or154_receipt["natural_dynamics"]["first_selected_jaw_contact_sample"]
        == CONTACT_SAMPLE
        and or154_receipt["natural_dynamics"]["first_motion_over_1mm_sample"]
        == MOTION_SAMPLE,
        "OR154 event samples changed",
    )

    or19, c6 = load_unilateral_push_dynamic_replay_contract(
        _bound_path(
            or154_contract["sources"]["or19_contract"], root=root, label="OR19 contract"
        ),
        root=root,
    )
    c6_loaded, candidate, measured_model, _ = _candidate_config(or19, root=root)
    _require(c6_loaded == c6, "C6 identity changed")
    source = c6["source"]
    requested = _load_array(source["requested"], root=root, label="requested rows")
    sent = _load_array(source["gateway_sent"], root=root, label="gateway-sent rows")
    raw_measured = _load_array(
        source["initial_measured"], root=root, label="raw measured rows"
    )
    timestamps = _load_array(source["timestamps"], root=root, label="timestamps")
    _require(
        requested.shape == sent.shape == raw_measured.shape == measured_model.shape == (531, 6)
        and timestamps.shape == (531,),
        "OR155 source array shape changed",
    )
    _require(
        source["initial_measured"]["sha256"]
        == or154_contract["preserved_state"]["raw_measured_sha256"],
        "OR154 raw measured identity changed",
    )

    scene_path = _bound_path(
        or154_contract["sources"]["or13_scene"], root=root, label="OR13 scene"
    )
    model = _candidate_spec(
        scene_path, pawn_height_m=0.034, canonical_piece_reset=True
    ).compile()
    data = mujoco.MjData(model)
    joint_ids = [
        _object_id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        for name in candidate["bindings"]["joint_names"]
    ]
    qpos_addresses = np.asarray(
        [int(model.jnt_qposadr[joint_id]) for joint_id in joint_ids],
        dtype=np.int64,
    )
    fixed_tips = [
        _object_id(model, mujoco.mjtObj.mjOBJ_GEOM, name)
        for name in FIXED_TIP_NAMES
    ]
    moving_tips = [
        _object_id(model, mujoco.mjtObj.mjOBJ_GEOM, name)
        for name in MOVING_TIP_NAMES
    ]
    d1_center = np.asarray(
        current_square_center("d1", config_path=scene_path), dtype=np.float64
    )

    locus_rows: list[dict[str, Any]] = []
    for sample in AUDIT_SAMPLES:
        data.qpos[qpos_addresses] = measured_model[sample]
        mujoco.mj_forward(model, data)
        fixed = np.mean(data.geom_xpos[fixed_tips], axis=0)
        moving = np.mean(data.geom_xpos[moving_tips], axis=0)
        midpoint = (fixed + moving) / 2.0
        planar_delta = midpoint[:2] - d1_center[:2]
        locus_rows.append(
            {
                "sample_index": sample,
                "source_timestamp_seconds": float(timestamps[sample]),
                "requested_gripper_degrees": float(requested[sample, -1]),
                "gateway_sent_gripper_degrees": float(sent[sample, -1]),
                "raw_measured_gripper_degrees": float(raw_measured[sample, -1]),
                "measured_minus_sent_gripper_degrees": float(
                    raw_measured[sample, -1] - sent[sample, -1]
                ),
                "fixed_tip_center_m": fixed.tolist(),
                "moving_tip_center_m": moving.tolist(),
                "jaw_tip_midpoint_m": midpoint.tolist(),
                "midpoint_minus_exact_d1_xy_m": planar_delta.tolist(),
                "midpoint_planar_distance_to_exact_d1_m": float(
                    np.linalg.norm(planar_delta)
                ),
                "jaw_tip_center_separation_m": float(np.linalg.norm(moving - fixed)),
            }
        )

    selected_name = c6["initialization"]["selected_piece"]
    selected_body = _object_id(
        model, mujoco.mjtObj.mjOBJ_BODY, selected_name
    )
    selected_joint = _object_id(
        model, mujoco.mjtObj.mjOBJ_JOINT, f"{selected_name}_free"
    )
    selected_qpos = int(model.jnt_qposadr[selected_joint])
    contact_trace_row = or154_trace["rows"][CONTACT_SAMPLE]
    data.qpos[qpos_addresses] = measured_model[CONTACT_SAMPLE]
    data.qpos[selected_qpos:selected_qpos + 3] = contact_trace_row[
        "selected_pawn_position_m"
    ]
    data.qpos[selected_qpos + 3:selected_qpos + 7] = contact_trace_row[
        "selected_pawn_quaternion_wxyz"
    ]
    mujoco.mj_forward(model, data)
    collision_rows = _collision_rows(
        model,
        data,
        gripper_geoms=_collision_geoms_for_bodies(model, JAW_BODY_NAMES),
        pawn_geoms=_pawn_collision_geoms(model, selected_body),
    )
    nearest = collision_rows[0]
    named_rows = [row for row in collision_rows if row["named_jaw_geom"]]
    _require(named_rows, "named jaw collision rows are absent")
    nearest_named = named_rows[0]

    physical = load_json_object(
        _bound_path(
            contract["sources"]["physical_event_closeout"],
            root=root,
            label="physical event closeout",
        ),
        label="physical event closeout",
    )
    presentation = load_json_object(
        _bound_path(
            contract["sources"]["or149_publication_receipt"],
            root=root,
            label="OR149 publication receipt",
        ),
        label="OR149 publication receipt",
    )
    or2 = load_json_object(
        _bound_path(
            contract["sources"]["or2_mapping_closeout"], root=root, label="OR2 closeout"
        ),
        label="OR2 closeout",
    )
    or12 = load_json_object(
        _bound_path(
            contract["sources"]["or12_metrology_closeout"],
            root=root,
            label="OR12 closeout",
        ),
        label="OR12 closeout",
    )
    proxies = load_json_object(
        _bound_path(
            contract["sources"]["retained_proxy_closeout"],
            root=root,
            label="retained proxy closeout",
        ),
        label="retained proxy closeout",
    )
    second_episode = load_json_object(
        _bound_path(
            contract["sources"]["second_episode_contract"],
            root=root,
            label="second episode contract",
        ),
        label="second episode contract",
    )
    static_closeouts = [
        load_json_object(
            _bound_path(contract["sources"][name], root=root, label=name),
            label=name,
        )
        for name in ("or31_closeout", "or32_closeout", "or33_closeout")
    ]

    enclosure_sample = int(physical["physical_events"]["first_definite_enclosure_sample"])
    closed_hold_sample = _first_closed_hold(
        requested[:, -1], after_sample=enclosure_sample
    )
    association = presentation["d405_timeline_association"]
    closure_row = next(row for row in locus_rows if row["sample_index"] == closed_hold_sample)
    raw_more_open_than_sent = all(
        float(row["measured_minus_sent_gripper_degrees"]) > 0.0
        for row in locus_rows
        if row["sample_index"] in (224, 232, 241)
    )
    fit_rows = 0
    untouched_validation_cohorts = 0
    source_hashes_after = {
        name: sha256_file(root / binding["path"])
        for name, binding in contract["sources"].items()
    }
    source_immutability = source_hashes_before == source_hashes_after
    _require(source_immutability, "OR155 source changed during audit")

    reproduced = (
        closed_hold_sample == 241
        and float(closure_row["midpoint_planar_distance_to_exact_d1_m"]) > 0.03
        and raw_more_open_than_sent
        and float(nearest["signed_distance_m"]) < 0.0
        and nearest["named_jaw_geom"] is False
        and float(nearest_named["signed_distance_m"]) > 0.0
        and fit_rows == 0
        and untouched_validation_cohorts == 0
    )
    _require(reproduced, "OR155 known closure-locus result did not reproduce")
    status = "PASS_SPATIAL_CLOSURE_LOCUS_AND_NON_NAMED_MESH_CONTACT_ATTRIBUTED_NO_SUCCESSOR"
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": status,
        "source_identity": {
            "recording_id": source["recording_id"],
            "row_count": 531,
            "raw_measured_sha256": source["initial_measured"]["sha256"],
            "timestamps_sha256": source["timestamps"]["sha256"],
            "or154_receipt_artifact_sha256": or154_receipt["artifact_sha256"],
            "source_hashes_unchanged": source_immutability,
        },
        "timing": {
            "physical_first_definite_enclosure_sample": enclosure_sample,
            "requested_closed_hold_start_sample": closed_hold_sample,
            "or154_first_broad_contact_sample": CONTACT_SAMPLE,
            "or154_first_motion_over_1mm_sample": MOTION_SAMPLE,
            "physical_enclosure_to_or154_contact_seconds": float(
                timestamps[CONTACT_SAMPLE] - timestamps[enclosure_sample]
            ),
            "closed_command_to_or154_contact_seconds": float(
                timestamps[CONTACT_SAMPLE] - timestamps[closed_hold_sample]
            ),
            "maximum_d405_association_error_ms": float(
                association["maximum_d405_association_error_ms"]
            ),
            "camera_exposure_synchronized": bool(
                association["camera_exposure_synchronized"]
            ),
            "device_clock_synchronized": bool(association["device_clock_synchronized"]),
            "actuator_application_timestamps_available": bool(
                association["actuator_application_timestamps_available"]
            ),
            "raw_measured_more_open_than_sent_at_samples_224_232_241": raw_more_open_than_sent,
        },
        "closure_locus": {
            "exact_d1_center_m": d1_center.tolist(),
            "rows": locus_rows,
            "closed_hold_midpoint_planar_distance_to_exact_d1_m": float(
                closure_row["midpoint_planar_distance_to_exact_d1_m"]
            ),
            "closed_hold_midpoint_minus_exact_d1_xy_m": closure_row[
                "midpoint_minus_exact_d1_xy_m"
            ],
        },
        "contact_provenance": {
            "sample_index": CONTACT_SAMPLE,
            "recorded_body_pairs": contact_trace_row["selected_jaw_contact_pairs"],
            "nearest_compiled_collision": nearest,
            "nearest_named_jaw_collision": nearest_named,
            "broad_body_contact_is_named_jaw_contact": bool(
                nearest["named_jaw_geom"]
            ),
            "named_jaw_pair_enclosure_proved": False,
        },
        "exposure_ledger": {
            "or2_rigid_fit_accepted": bool(or2["fit"]["accepted"]),
            "or2_fit_tip_rms_px": float(or2["fit"]["tip_reprojection_rms_px"]),
            "or2_fit_failed_gates": or2["fit"]["failed_gates"],
            "or12_planar_translation_already_adopted_m": or12[
                "translation_candidate"
            ]["translation_delta_table_xy_m"],
            "or12_global_mapping_approved": bool(
                or12["translation_candidate"]["global_mapping_approved"]
            ),
            "retained_proxy_parameter_fit_allowed": bool(
                proxies["result"]["parameter_fit_allowed"]
            ),
            "retained_proxy_first_accepted_crown_sample": proxies["result"][
                "first_accepted_crown_source_sample"
            ],
            "retained_proxy_pawn_base_rows": proxies["result"][
                "pawn_base_proxy_rows"
            ],
            "second_episode_cross_episode_parameter_fit_allowed": bool(
                second_episode["recording_policy"]["cross_episode_parameter_fit_allowed"]
            ),
            "static_refinement_statuses": [item["status"] for item in static_closeouts],
            "admissible_fit_rows": fit_rows,
            "untouched_validation_cohorts": untouched_validation_cohorts,
        },
        "diagnosis": {
            "early_actuator_closure_supported": False,
            "or149_visible_lead_is_identifying": False,
            "spatial_closure_locus_mismatch_reproduced": True,
            "or154_broad_contact_witness_proves_bilateral_grasp": False,
            "task_level_success_advanced_by_this_audit": False,
            "admissible_task_successor": False,
            "interpretation": "The measured gripper does not lead its command. At the closed-command hold, the named jaw midpoint remains displaced from exact D1; OR154's later broad contact is first supported by a non-named fixed-gripper CAD mesh while named jaw geometry remains separated. The retained corpus cannot identify a promotable timing, registration, aperture, or contact correction.",
        },
        "known_result_reproduction": True,
        "execution": EXECUTION_BOUNDARY,
        "claim_limits": contract["claim_limits"],
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    output_directory.mkdir(parents=True, exist_ok=False)
    atomic_write_json(output_directory / "receipt.json", receipt)
    return receipt


def verify_closure_locus_audit(
    output_directory: Path = OUTPUT_DIRECTORY,
    contract_path: Path = CONTRACT_PATH,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_closure_locus_audit_contract(contract_path, root=root)
    receipt_path = output_directory / "receipt.json"
    receipt = load_json_object(receipt_path, label="OR155 receipt")
    _require(receipt.get("schema_version") == RECEIPT_SCHEMA, "OR155 receipt schema changed")
    unsigned = {key: value for key, value in receipt.items() if key != "artifact_sha256"}
    _require(
        receipt["artifact_sha256"] == canonical_digest(unsigned),
        "OR155 receipt digest changed",
    )
    _require(
        receipt["status"]
        == "PASS_SPATIAL_CLOSURE_LOCUS_AND_NON_NAMED_MESH_CONTACT_ATTRIBUTED_NO_SUCCESSOR",
        "OR155 status changed",
    )
    _require(receipt["execution"] == EXECUTION_BOUNDARY, "OR155 execution changed")
    _require(receipt["claim_limits"] == contract["claim_limits"], "OR155 claims changed")
    _require(not any(receipt["claim_limits"].values()), "OR155 claim widened")
    _require(receipt["diagnosis"]["admissible_task_successor"] is False, "OR155 opened a successor")
    return receipt

"""Frozen direct-target and 0.11 s ZOH replay for canonical seeded actions."""

from __future__ import annotations

import hashlib
import json
import copy
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from . import canonical_seeded_action_static as _static
from . import canonical_seeded_action_static_v2 as _static_v2
from .bidirectional_registration_v2_fit import project
from .current_workcell import current_square_center
from .observable_episode import (
    build_simulator_episode,
    first_divergence,
    write_episode,
)
from .paths import REPO_ROOT


class CanonicalSeededActionTemporalError(RuntimeError):
    """A frozen temporal input or consequence invariant changed."""


KEY_LINK_BODIES = (
    "left_shoulder",
    "left_upper_arm",
    "left_lower_arm",
    "left_wrist",
    "left_gripper",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(entry: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(entry["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise CanonicalSeededActionTemporalError(
            "canonical temporal input escapes repository"
        ) from error
    if not path.is_file() or _sha(path) != entry["sha256"]:
        raise CanonicalSeededActionTemporalError(
            f"bound canonical temporal input changed: {path}"
        )
    return path


def _json(entry: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(_bound(entry).read_text(encoding="utf-8"))


def _write_tensor(
    directory: Path,
    name: str,
    values: np.ndarray,
) -> dict[str, Any]:
    path = directory / f"{name}.f64le"
    array = np.asarray(values, dtype="<f8", order="C")
    path.write_bytes(array.tobytes(order="C"))
    return {
        "path": _display_path(path),
        "sha256": _sha(path),
        "shape": list(array.shape),
        "dtype": "little_endian_float64",
    }


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def _board_frame() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    origin = np.asarray(current_square_center("a1"), dtype=np.float64)
    file_axis = (
        np.asarray(current_square_center("b1"), dtype=np.float64) - origin
    )
    rank_axis = (
        np.asarray(current_square_center("a2"), dtype=np.float64) - origin
    )
    file_axis /= np.linalg.norm(file_axis)
    rank_axis /= np.linalg.norm(rank_axis)
    return origin, file_axis, rank_axis


def _board_se2(
    data: mujoco.MjData,
    body_id: int,
    board_frame: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> np.ndarray:
    origin, file_axis, rank_axis = board_frame
    delta = data.xpos[body_id] - origin
    body_x_world = data.xmat[body_id].reshape(3, 3)[:, 0]
    return np.asarray(
        [
            np.dot(delta, file_axis),
            np.dot(delta, rank_axis),
            np.arctan2(
                np.dot(body_x_world, rank_axis),
                np.dot(body_x_world, file_axis),
            ),
        ],
        dtype=np.float64,
    )


def _link_pose(
    data: mujoco.MjData,
    body_id: int,
) -> list[float]:
    return [
        *np.asarray(data.xpos[body_id], dtype=np.float64).tolist(),
        *np.asarray(data.xquat[body_id], dtype=np.float64).tolist(),
    ]


def _zoh_delay(
    requested: np.ndarray,
    *,
    sample_hz: float,
    delay_seconds: float,
) -> tuple[np.ndarray, np.ndarray]:
    timestamps = np.arange(len(requested), dtype="<f8") / sample_hz
    source_times = np.maximum(0.0, timestamps - delay_seconds)
    indices = np.floor(source_times * sample_hz + 1e-12).astype(np.int64)
    indices = np.clip(indices, 0, len(requested) - 1)
    return np.asarray(requested[indices], dtype="<f8", order="C"), indices


def _load_action(case: Mapping[str, Any]) -> np.ndarray:
    path = _bound(
        {
            "path": case["action_path"],
            "sha256": case["action_sha256"],
        }
    )
    shape = tuple(int(value) for value in case["action_shape"])
    action = np.fromfile(path, dtype="<f8")
    if action.size != int(np.prod(shape)):
        raise CanonicalSeededActionTemporalError(
            "canonical action shape changed"
        )
    return np.asarray(action.reshape(shape), dtype="<f8", order="C")


def _body_name(model: mujoco.MjModel, body_id: int) -> str:
    return (
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id)
        or f"body-{body_id}"
    )


def _jaw_contact_pairs(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    jaw_bodies: set[int],
) -> set[tuple[str, str]]:
    result = set()
    for index in range(data.ncon):
        contact = data.contact[index]
        bodies = (
            int(model.geom_bodyid[int(contact.geom1)]),
            int(model.geom_bodyid[int(contact.geom2)]),
        )
        if set(bodies) & jaw_bodies:
            result.add(tuple(sorted(_body_name(model, item) for item in bodies)))
    return result


def _replay(
    *,
    model: mujoco.MjModel,
    addresses: list[int],
    actuators: list[int],
    jaw_bodies: set[int],
    action: np.ndarray,
    selected_name: str,
    source_delta_m: np.ndarray,
    direction: np.ndarray,
    substeps: int,
    sample_hz: float,
    first_object_motion_threshold_m: float,
    camera: np.ndarray,
    image_size: tuple[int, int],
    reset_layout: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    data = mujoco.MjData(model)
    selected_id = _static._named_id(
        model, mujoco.mjtObj.mjOBJ_BODY, selected_name
    )
    selected_joint = int(model.body_jntadr[selected_id])
    selected_qpos = int(model.jnt_qposadr[selected_joint])
    data.qpos[selected_qpos : selected_qpos + 2] += source_delta_m
    data.qpos[addresses] = action[0]
    data.ctrl[actuators] = action[0]
    pawn_ids = {
        body_id
        for body_id in range(model.nbody)
        if "_pawn_" in _body_name(model, body_id)
    }
    excluded_ids = pawn_ids - {selected_id}
    if reset_layout is not None:
        if reset_layout != {
            "mode": "isolated_selected_pawn_offboard_parking",
            "parking_origin_xyz_m": [0.8, 0.1, 0.800883941],
            "parking_spacing_m": 0.05,
            "selected_pawn_pose_unchanged": True,
            "nonselected_pawn_dynamics_unchanged": True,
        }:
            raise CanonicalSeededActionTemporalError(
                "canonical reset layout changed"
            )
        origin = np.asarray(
            reset_layout["parking_origin_xyz_m"], dtype=np.float64
        )
        for parking_index, body_id in enumerate(
            sorted(excluded_ids, key=lambda item: _body_name(model, item))
        ):
            joint_id = int(model.body_jntadr[body_id])
            qpos_address = int(model.jnt_qposadr[joint_id])
            data.qpos[qpos_address : qpos_address + 3] = origin + np.asarray(
                [
                    parking_index
                    * float(reset_layout["parking_spacing_m"]),
                    0.0,
                    0.0,
                ],
                dtype=np.float64,
            )
    mujoco.mj_forward(model, data)
    initial_selected = data.xpos[selected_id].copy()
    initial_excluded = {
        body_id: data.xpos[body_id].copy() for body_id in excluded_ids
    }
    link_ids = {
        name: _static._named_id(model, mujoco.mjtObj.mjOBJ_BODY, name)
        for name in KEY_LINK_BODIES
    }
    board_frame = _board_frame()
    baseline = _jaw_contact_pairs(model, data, jaw_bodies)
    selected_contact_steps = 0
    excluded_contact_steps = 0
    maximum_vertical_rise = 0.0
    maximum_excluded = 0.0
    new_pairs: set[tuple[str, str]] = set()
    joint_states: list[list[float]] = []
    link_poses: list[dict[str, list[float]]] = []
    object_states: list[list[float]] = []
    object_covariances: list[list[list[float]]] = []
    contact_states: list[bool] = []
    first_object_motion_sample: int | None = None
    object_world_positions: list[list[float]] = []
    for row_index, row in enumerate(action):
        data.ctrl[actuators] = row
        row_selected_contact = False
        for _ in range(substeps):
            mujoco.mj_step(model, data)
            maximum_vertical_rise = max(
                maximum_vertical_rise,
                float(data.xpos[selected_id][2] - initial_selected[2]),
            )
            for contact_index in range(data.ncon):
                contact = data.contact[contact_index]
                bodies = {
                    int(model.geom_bodyid[int(contact.geom1)]),
                    int(model.geom_bodyid[int(contact.geom2)]),
                }
                if bodies & jaw_bodies and selected_id in bodies:
                    selected_contact_steps += 1
                    row_selected_contact = True
                if bodies & jaw_bodies and bodies & excluded_ids:
                    excluded_contact_steps += 1
            new_pairs |= (
                _jaw_contact_pairs(model, data, jaw_bodies) - baseline
            )
            maximum_excluded = max(
                maximum_excluded,
                max(
                    float(
                        np.linalg.norm(
                            data.xpos[body][:2] - initial[:2]
                        )
                    )
                    for body, initial in initial_excluded.items()
                ),
            )
        selected_position = data.xpos[selected_id].copy()
        object_world_positions.append(selected_position.tolist())
        if (
            first_object_motion_sample is None
            and float(
                np.linalg.norm(
                    (selected_position - initial_selected)[:2]
                )
            )
            >= first_object_motion_threshold_m
        ):
            first_object_motion_sample = row_index
        joint_states.append(
            np.asarray(data.qpos[addresses], dtype=np.float64).tolist()
        )
        link_poses.append(
            {
                name: _link_pose(data, body_id)
                for name, body_id in link_ids.items()
            }
        )
        object_states.append(
            _board_se2(data, selected_id, board_frame).tolist()
        )
        object_covariances.append(np.zeros((3, 3)).tolist())
        contact_states.append(row_selected_contact)
    mujoco.mj_forward(model, data)
    final_selected = data.xpos[selected_id].copy()
    progress = float(
        np.dot((final_selected - initial_selected)[:2], direction[:2])
    )
    allowed = {
        tuple(sorted((_body_name(model, jaw), selected_name)))
        for jaw in jaw_bodies
    }
    collision_pairs = sorted(new_pairs - allowed)
    projected = project(camera, np.asarray(object_world_positions))
    width, height = image_size
    camera_margin = float(
        np.min(
            np.column_stack(
                (
                    projected[:, 0],
                    width - projected[:, 0],
                    projected[:, 1],
                    height - projected[:, 1],
                )
            )
        )
    )
    return {
        "selected_initial_xyz_m": initial_selected.tolist(),
        "selected_final_xyz_m": final_selected.tolist(),
        "signed_progress_mm": progress * 1000.0,
        "maximum_selected_vertical_rise_mm": maximum_vertical_rise * 1000.0,
        "selected_contact_steps": selected_contact_steps,
        "excluded_contact_steps": excluded_contact_steps,
        "maximum_excluded_displacement_mm": maximum_excluded * 1000.0,
        "new_nonselected_jaw_collision_pairs": [
            list(item) for item in collision_pairs
        ],
        "camera_margin_px": camera_margin,
        "reset_layout": reset_layout,
        "observable_inputs": {
            "joint_states": np.asarray(joint_states, dtype="<f8"),
            "link_poses": link_poses,
            "object_states_board_se2": np.asarray(
                object_states, dtype=np.float64
            ),
            "object_covariances": np.asarray(
                object_covariances, dtype=np.float64
            ),
            "contact_states": contact_states,
            "first_object_motion_sample": first_object_motion_sample,
            "sample_hz": sample_hz,
        },
    }


def replay(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Run the frozen baseline and diagnostic temporal challenger once."""

    if output_directory.exists():
        raise CanonicalSeededActionTemporalError(
            "immutable temporal output directory already exists"
        )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    raw_contract = contract
    if contract.get("schema_version") == (
        "sim2claw.canonical_seeded_action_temporal_successor.v2"
    ):
        expected_fields = {
            "schema_version",
            "contract_id",
            "status",
            "proof_class",
            "frozen_v1_contract",
            "v1_dry_validation_closeout",
            "temporal_implementation",
            "output_directory",
            "unchanged_from_v1",
            "claim_boundary",
        }
        if (
            set(contract) != expected_fields
            or not all(contract["unchanged_from_v1"].values())
        ):
            raise CanonicalSeededActionTemporalError(
                "canonical V2 successor widened its override surface"
            )
        base = _json(contract["frozen_v1_contract"])
        _bound(contract["v1_dry_validation_closeout"])
        _bound(contract["temporal_implementation"])
        contract = copy.deepcopy(base)
        contract["contract_id"] = raw_contract["contract_id"]
        contract["status"] = raw_contract["status"]
        contract["proof_class"] = raw_contract["proof_class"]
        contract["inputs"]["temporal_implementation"] = raw_contract[
            "temporal_implementation"
        ]
        contract["inputs"]["v1_dry_validation_closeout"] = raw_contract[
            "v1_dry_validation_closeout"
        ]
        contract["output_directory"] = raw_contract["output_directory"]
        contract["claim_boundary"] = raw_contract["claim_boundary"]
    elif contract.get("schema_version") == (
        "sim2claw.canonical_wrist_path_temporal.v1"
    ):
        expected_fields = {
            "schema_version",
            "contract_id",
            "status",
            "proof_class",
            "base_temporal_contract",
            "static_receipt",
            "static_closeout",
            "temporal_implementation",
            "cases",
            "live_seed",
            "output_directory",
            "unchanged_from_base",
            "claim_boundary",
        }
        if (
            set(contract) != expected_fields
            or not all(contract["unchanged_from_base"].values())
            or len(contract["cases"]) != 4
        ):
            raise CanonicalSeededActionTemporalError(
                "canonical wrist/path temporal contract widened its surface"
            )
        base = _json(contract["base_temporal_contract"])
        for binding_name in (
            "static_receipt",
            "static_closeout",
            "temporal_implementation",
        ):
            _bound(contract[binding_name])
        contract = copy.deepcopy(base)
        contract["contract_id"] = raw_contract["contract_id"]
        contract["status"] = raw_contract["status"]
        contract["proof_class"] = raw_contract["proof_class"]
        contract["inputs"]["static_receipt"] = raw_contract[
            "static_receipt"
        ]
        contract["inputs"]["static_closeout"] = raw_contract[
            "static_closeout"
        ]
        contract["inputs"]["temporal_implementation"] = raw_contract[
            "temporal_implementation"
        ]
        contract["cases"] = raw_contract["cases"]
        contract["live_seed"] = raw_contract["live_seed"]
        contract["output_directory"] = raw_contract["output_directory"]
        contract["claim_boundary"] = raw_contract["claim_boundary"]
    elif contract.get("schema_version") in {
        "sim2claw.canonical_wrist_path_reset_temporal.v2",
        "sim2claw.canonical_wrist_path_low_contact_temporal.v3",
    }:
        reset_schema = contract["schema_version"]
        expected_case_count = (
            6
            if reset_schema
            == "sim2claw.canonical_wrist_path_reset_temporal.v2"
            else 4
        )
        expected_fields = {
            "schema_version",
            "contract_id",
            "status",
            "proof_class",
            "base_temporal_contract",
            "static_receipt",
            "static_closeout",
            "action_completion_receipt",
            "temporal_closeout",
            "temporal_implementation",
            "cases",
            "live_seed",
            "reset_layout",
            "output_directory",
            "unchanged_from_base",
            "claim_boundary",
        }
        if (
            set(contract) != expected_fields
            or not all(contract["unchanged_from_base"].values())
            or len(contract["cases"]) != expected_case_count
        ):
            raise CanonicalSeededActionTemporalError(
                "canonical reset-layout temporal contract widened"
            )
        base = _json(contract["base_temporal_contract"])
        for binding_name in (
            "static_receipt",
            "static_closeout",
            "action_completion_receipt",
            "temporal_closeout",
            "temporal_implementation",
        ):
            _bound(contract[binding_name])
        contract = copy.deepcopy(base)
        contract["contract_id"] = raw_contract["contract_id"]
        contract["status"] = raw_contract["status"]
        contract["proof_class"] = raw_contract["proof_class"]
        contract["inputs"]["static_receipt"] = raw_contract[
            "static_receipt"
        ]
        contract["inputs"]["static_closeout"] = raw_contract[
            "static_closeout"
        ]
        contract["inputs"]["action_completion_receipt"] = raw_contract[
            "action_completion_receipt"
        ]
        contract["inputs"]["temporal_closeout"] = raw_contract[
            "temporal_closeout"
        ]
        contract["inputs"]["temporal_implementation"] = raw_contract[
            "temporal_implementation"
        ]
        contract["cases"] = raw_contract["cases"]
        contract["live_seed"] = raw_contract["live_seed"]
        contract["reset_layout"] = raw_contract["reset_layout"]
        contract["observable_episode"]["expected_episode_count"] = (
            expected_case_count * 10
        )
        contract["action_completion_expected_status"] = (
            "two_unopened_v4_family_actions_frozen"
            if expected_case_count == 6
            else "four_low_contact_v4_family_actions_frozen"
        )
        contract["output_directory"] = raw_contract["output_directory"]
        contract["claim_boundary"] = raw_contract["claim_boundary"]
    elif contract.get("schema_version") != (
        "sim2claw.canonical_seeded_action_temporal.v1"
    ):
        raise CanonicalSeededActionTemporalError(
            "unexpected canonical temporal contract"
        )
    static_receipt = _json(contract["inputs"]["static_receipt"])
    completion_receipt = (
        _json(contract["inputs"]["action_completion_receipt"])
        if "action_completion_receipt" in contract["inputs"]
        else None
    )
    manifest = _json(contract["inputs"]["candidate_manifest"])
    rigid = _json(contract["inputs"]["registration_candidate"])
    for name in (
        "static_closeout",
        "observable_episode_contract",
        "observable_episode_closeout",
        "observable_episode_implementation",
        "temporal_implementation",
    ):
        _bound(contract["inputs"][name])
    if "v1_dry_validation_closeout" in contract["inputs"]:
        _bound(contract["inputs"]["v1_dry_validation_closeout"])
    if contract["plant_paths"] != [
        {
            "path_id": "canonical_direct_target",
            "kind": "direct_target_mujoco",
            "delay_seconds": 0.0,
            "diagnostic_only": False,
            "calibrated_physical_latency": False,
        },
        {
            "path_id": "diagnostic_zoh_0p11s",
            "kind": "zero_order_hold_command_delay",
            "delay_seconds": 0.11,
            "diagnostic_only": True,
            "calibrated_physical_latency": False,
        },
    ]:
        raise CanonicalSeededActionTemporalError(
            "canonical plant paths changed"
        )
    if (
        contract["action_identity"][
            "no_clipping_smoothing_retiming_offset_repair_or_rate_limit"
        ]
        is not True
        or contract["observable_episode"]["schema_version"]
        != "sim2claw.observable_episode.v2-min"
        or contract["authority"]["dynamic_simulation"] is not True
        or any(
            value
            for name, value in contract["authority"].items()
            if name != "dynamic_simulation"
        )
    ):
        raise CanonicalSeededActionTemporalError(
            "canonical temporal authority or identity changed"
        )
    sample_hz = float(contract["action_identity"]["sample_hz"])
    if not np.isclose(
        float(contract["simulation"]["timestep_s"])
        * int(contract["simulation"]["substeps_per_row"]),
        1.0 / sample_hz,
        rtol=0.0,
        atol=1e-12,
    ):
        raise CanonicalSeededActionTemporalError(
            "simulator substeps do not preserve frozen 40 Hz timing"
        )
    seeded_static_admitted = (
        static_receipt.get("status")
        == "canonical_seeded_action_static_v2_pass"
        and static_receipt.get("model_joint_margin_gate_passed") is True
        and static_receipt.get("dynamic_simulation_executed") is False
        and static_receipt.get("physical_motion") is False
    )
    wrist_path_static_admitted = (
        static_receipt.get("status")
        == "canonical_wrist_path_static_pass"
        and static_receipt.get("passed") is True
        and static_receipt.get("statically_eligible_family_count", 0) >= 4
        and static_receipt.get("direction_counts")
        == {"REAL_TO_SIM": 2, "SIM_TO_REAL": 2}
        and static_receipt.get("dynamic_replay_executed") is False
        and static_receipt.get("physical_motion") is False
    )
    if not (seeded_static_admitted or wrist_path_static_admitted):
        raise CanonicalSeededActionTemporalError(
            "canonical static admission changed"
        )
    static_rows = list(static_receipt["selected"])
    if completion_receipt is not None:
        if (
            completion_receipt["status"]
            != contract.get(
                "action_completion_expected_status",
                "two_unopened_v4_family_actions_frozen",
            )
            or completion_receipt["dynamic_simulation"]
            or completion_receipt["physical_motion"]
        ):
            raise CanonicalSeededActionTemporalError(
                "canonical action completion admission changed"
            )
        static_rows.extend(completion_receipt["frozen_actions"])
    static_by_id = {row["case_id"]: row for row in static_rows}
    contract_case_ids = [case["case_id"] for case in contract["cases"]]
    if (
        len(set(contract_case_ids)) != len(contract_case_ids)
        or not set(contract_case_ids).issubset(static_by_id)
    ):
        raise CanonicalSeededActionTemporalError(
            "canonical temporal case count changed"
        )

    original = _static._registered_current_model
    model_builder = _static_v2._calibrated_registered_model(
        original, manifest["candidate_config"]
    )
    model, addresses, _, jaw_bodies = model_builder(
        rigid, float(contract["simulation"]["timestep_s"])
    )
    actuators = [
        _static._named_id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
        for name in _static.ALL_JOINTS
    ]
    camera = np.asarray(rigid["camera_matrix_3x4"], dtype=np.float64)
    image_size = tuple(contract["camera_gate"]["image_size_px"])
    output_directory.mkdir(parents=True)
    results = []
    for case in contract["cases"]:
        static = static_by_id.get(case["case_id"])
        if (
            static is None
            or static["action_sha256"] != case["action_sha256"]
            or static.get("direction", case["direction"])
            != case["direction"]
        ):
            raise CanonicalSeededActionTemporalError(
                "temporal case differs from static freeze"
            )
        requested = _load_action(case)
        sent = requested.copy(order="C")
        timestamps = np.arange(len(requested), dtype="<f8") / sample_hz
        source = np.asarray(
            current_square_center(case["source_square"]),
            dtype=np.float64,
        )
        destination = np.asarray(
            current_square_center(case["destination_square"]),
            dtype=np.float64,
        )
        direction = destination - source
        direction /= np.linalg.norm(direction)
        path_results = []
        episodes_by_path_variant: dict[
            tuple[str, str], dict[str, Any]
        ] = {}
        for path_spec in contract["plant_paths"]:
            if path_spec["kind"] == "direct_target_mujoco":
                applied = requested.copy(order="C")
                source_indices = np.arange(len(requested), dtype=np.int64)
            elif path_spec["kind"] == "zero_order_hold_command_delay":
                applied, source_indices = _zoh_delay(
                    requested,
                    sample_hz=sample_hz,
                    delay_seconds=float(path_spec["delay_seconds"]),
                )
            else:
                raise CanonicalSeededActionTemporalError(
                    "unknown canonical plant path"
                )
            trace_directory = (
                output_directory
                / "traces"
                / case["case_id"]
                / path_spec["path_id"]
            )
            trace_directory.mkdir(parents=True)
            traces = {
                "requested": _write_tensor(
                    trace_directory, "requested", requested
                ),
                "mapped": _write_tensor(
                    trace_directory, "mapped", requested
                ),
                "sent": _write_tensor(trace_directory, "sent", sent),
                "applied": _write_tensor(
                    trace_directory, "applied", applied
                ),
                "requested_timestamps": _write_tensor(
                    trace_directory, "requested_timestamps", timestamps
                ),
                "sent_timestamps": _write_tensor(
                    trace_directory, "sent_timestamps", timestamps
                ),
                "applied_timestamps": _write_tensor(
                    trace_directory, "applied_timestamps", timestamps
                ),
            }
            index_path = trace_directory / "applied_source_indices.i64le"
            index_path.write_bytes(
                np.asarray(source_indices, dtype="<i8").tobytes(order="C")
            )
            traces["applied_source_indices"] = {
                "path": _display_path(index_path),
                "sha256": _sha(index_path),
                "shape": list(source_indices.shape),
                "dtype": "little_endian_int64",
            }
            robustness = []
            for variant in contract["robustness_variants"]:
                longitudinal, lateral = variant["delta_m"]
                delta = (
                    direction[:2] * longitudinal
                    + np.asarray([-direction[1], direction[0]]) * lateral
                )
                consequence = _replay(
                    model=model,
                    addresses=addresses,
                    actuators=actuators,
                    jaw_bodies=jaw_bodies,
                    action=applied,
                    selected_name=case["selected_piece_id"],
                    source_delta_m=delta,
                    direction=direction,
                    substeps=int(
                        contract["simulation"]["substeps_per_row"]
                    ),
                    sample_hz=sample_hz,
                    first_object_motion_threshold_m=float(
                        contract["observable_episode"][
                            "first_object_motion_threshold_m"
                        ]
                    ),
                    camera=camera,
                    image_size=image_size,
                    reset_layout=contract.get("reset_layout"),
                )
                observable_inputs = consequence.pop("observable_inputs")
                checks = {
                    "progress": consequence["signed_progress_mm"]
                    >= contract["gates"]["minimum_signed_progress_mm"],
                    "selected_contact": consequence[
                        "selected_contact_steps"
                    ]
                    > 0,
                    "excluded_contact": consequence[
                        "excluded_contact_steps"
                    ]
                    == 0,
                    "excluded_displacement": consequence[
                        "maximum_excluded_displacement_mm"
                    ]
                    <= contract["gates"][
                        "maximum_excluded_displacement_mm"
                    ],
                    "no_lift": consequence[
                        "maximum_selected_vertical_rise_mm"
                    ]
                    <= contract["gates"][
                        "maximum_selected_vertical_rise_mm"
                    ],
                    "collision": not consequence[
                        "new_nonselected_jaw_collision_pairs"
                    ],
                    "camera_margin": consequence["camera_margin_px"]
                    >= contract["camera_gate"]["minimum_margin_px"],
                }
                task_outcome = (
                    "pass"
                    if all(checks.values())
                    else "fail:" + ",".join(
                        sorted(
                            name
                            for name, value in checks.items()
                            if not value
                        )
                    )
                )
                episode = build_simulator_episode(
                    episode_id=(
                        f"{case['case_id']}__{path_spec['path_id']}"
                        f"__{variant['variant_id']}"
                    ),
                    requested=requested,
                    applied=applied,
                    sample_hz=observable_inputs["sample_hz"],
                    joint_states=observable_inputs["joint_states"],
                    link_poses=observable_inputs["link_poses"],
                    object_states_board_se2=observable_inputs[
                        "object_states_board_se2"
                    ],
                    object_covariances=observable_inputs[
                        "object_covariances"
                    ],
                    contact_states=observable_inputs["contact_states"],
                    task_outcome=task_outcome,
                    first_object_motion_sample=observable_inputs[
                        "first_object_motion_sample"
                    ],
                    provenance={
                        "contract_path": _display_path(contract_path),
                        "contract_sha256": _sha(contract_path),
                        "static_receipt_sha256": contract["inputs"][
                            "static_receipt"
                        ]["sha256"],
                        "case_id": case["case_id"],
                        "direction": case["direction"],
                        "plant_path_id": path_spec["path_id"],
                        "plant_kind": path_spec["kind"],
                        "diagnostic_only": bool(
                            path_spec.get("diagnostic_only", False)
                        ),
                        "calibrated_physical_latency": bool(
                            path_spec.get(
                                "calibrated_physical_latency", False
                            )
                        ),
                        "variant_id": variant["variant_id"],
                        "source_delta_m": delta.tolist(),
                        "object_covariance_semantics": (
                            "zero_deterministic_simulator_state"
                        ),
                    },
                )
                episode_path = (
                    output_directory
                    / "episodes"
                    / case["case_id"]
                    / path_spec["path_id"]
                    / f"{variant['variant_id']}.json"
                )
                episode_receipt = write_episode(episode, episode_path)
                episode_receipt["path"] = _display_path(episode_path)
                episodes_by_path_variant[
                    (path_spec["path_id"], variant["variant_id"])
                ] = episode
                robustness.append(
                    {
                        "variant_id": variant["variant_id"],
                        **consequence,
                        "checks": checks,
                        "passed": all(checks.values()),
                        "observable_episode": episode_receipt,
                    }
                )
            physical_applied = _static._physical_actions(
                applied, manifest["candidate_config"]
            )
            maximum_applied_rates = np.max(
                np.abs(np.diff(physical_applied, axis=0)) * sample_hz,
                axis=0,
            )
            gateway_rate_limits = np.asarray(
                contract["action_identity"][
                    "gateway_rate_limits_per_joint"
                ],
                dtype=np.float64,
            )
            identity_checks = {
                "requested_sent_byte_identical": (
                    requested.tobytes(order="C")
                    == sent.tobytes(order="C")
                ),
                "requested_mapped_byte_identical": (
                    traces["requested"]["sha256"]
                    == traces["mapped"]["sha256"]
                ),
                "requested_hash_matches_freeze": hashlib.sha256(
                    requested.tobytes(order="C")
                ).hexdigest()
                == case["action_sha256"],
                "applied_trace_hash_matches_observable_episodes": all(
                    item["observable_episode"]["sha256"]
                    and episodes_by_path_variant[
                        (path_spec["path_id"], item["variant_id"])
                    ]["action"]["applied_sha256_or_missing"]
                    == traces["applied"]["sha256"]
                    for item in robustness
                ),
                "timestamps_strictly_monotonic": bool(
                    np.all(np.diff(timestamps) > 0.0)
                ),
                "row_zero_exact_live_seed": np.array_equal(
                    _static._physical_actions(
                        requested[:1], manifest["candidate_config"]
                    )[0],
                    np.asarray(
                        contract["live_seed"][
                            "follower_position_degrees"
                        ],
                        dtype=np.float64,
                    ),
                ),
                "applied_gateway_rate_compatible_without_modification": bool(
                    np.all(maximum_applied_rates <= gateway_rate_limits)
                ),
            }
            path_results.append(
                {
                    "path_id": path_spec["path_id"],
                    "kind": path_spec["kind"],
                    "delay_seconds": path_spec.get("delay_seconds", 0.0),
                    "diagnostic_only": bool(
                        path_spec.get("diagnostic_only", False)
                    ),
                    "traces": traces,
                    "maximum_applied_physical_rate_per_second": (
                        maximum_applied_rates.tolist()
                    ),
                    "gateway_rate_limits_per_joint": (
                        gateway_rate_limits.tolist()
                    ),
                    "identity_checks": identity_checks,
                    "robustness": robustness,
                    "passed": all(identity_checks.values())
                    and all(item["passed"] for item in robustness),
                }
            )
        direct_path_id = contract["plant_paths"][0]["path_id"]
        challenger_path_id = contract["plant_paths"][1]["path_id"]
        divergence_rows = []
        for variant in contract["robustness_variants"]:
            variant_id = variant["variant_id"]
            divergence_rows.append(
                {
                    "variant_id": variant_id,
                    **first_divergence(
                        episodes_by_path_variant[
                            (direct_path_id, variant_id)
                        ],
                        episodes_by_path_variant[
                            (challenger_path_id, variant_id)
                        ],
                        joint_threshold=float(
                            contract["first_divergence"][
                                "joint_threshold_rad"
                            ]
                        ),
                        link_position_threshold_m=float(
                            contract["first_divergence"][
                                "link_position_threshold_m"
                            ]
                        ),
                        object_position_threshold_m=float(
                            contract["first_divergence"][
                                "object_position_threshold_m"
                            ]
                        ),
                        object_yaw_threshold_rad=float(
                            contract["first_divergence"][
                                "object_yaw_threshold_rad"
                            ]
                        ),
                    ),
                }
            )
        results.append(
            {
                "case_id": case["case_id"],
                "direction": case["direction"],
                "source_square": case["source_square"],
                "destination_square": case["destination_square"],
                "selected_piece_id": case["selected_piece_id"],
                "action_sha256": case["action_sha256"],
                "plant_paths": path_results,
                "direct_vs_zoh_first_divergence": divergence_rows,
                "passed_both_paths": all(
                    item["passed"] for item in path_results
                ),
            }
        )
    passing = [item for item in results if item["passed_both_paths"]]
    counts = {
        direction: sum(item["direction"] == direction for item in passing)
        for direction in ("REAL_TO_SIM", "SIM_TO_REAL")
    }
    required = int(contract["acceptance"]["minimum_cases_per_direction"])
    direction_checks = {
        direction: count >= required for direction, count in counts.items()
    }
    passed = all(direction_checks.values())
    receipt = {
        "schema_version": "sim2claw.canonical_seeded_action_temporal_receipt.v1",
        "status": (
            "canonical_seeded_action_temporal_pass"
            if passed
            else "canonical_seeded_action_temporal_reject"
        ),
        "proof_class": (
            "cpu_fp64_canonical_action_frozen_direct_target_and_"
            "diagnostic_zoh_consequence_replay"
        ),
        "contract_path": _display_path(contract_path),
        "contract_sha256": _sha(contract_path),
        "resolved_contract_id": contract["contract_id"],
        "source_contract_schema_version": raw_contract["schema_version"],
        "static_receipt_sha256": contract["inputs"]["static_receipt"][
            "sha256"
        ],
        "results": results,
        "passing_case_ids": [item["case_id"] for item in passing],
        "direction_counts": counts,
        "direction_checks": direction_checks,
        "minimum_cases_per_direction": required,
        "candidate_refit": False,
        "task_outcomes_used_for_action_selection": False,
        "physical_motion": False,
        "physical_task_attempts": 0,
        "passed": passed,
        "authority": contract["authority"],
        "claim_boundary": contract["claim_boundary"],
    }
    (output_directory / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = [
    "CanonicalSeededActionTemporalError",
    "replay",
]

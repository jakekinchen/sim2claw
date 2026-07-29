"""Finite current-workcell wrist/path static successor after CC02 negatives."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from . import canonical_seeded_action_static as _static
from . import canonical_seeded_action_static_v2 as _static_v2
from .current_workcell import current_square_center
from .paths import REPO_ROOT


class CanonicalWristPathStaticError(RuntimeError):
    """The frozen canonical wrist/path static successor failed closed."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(binding: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(binding["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise CanonicalWristPathStaticError(
            "canonical wrist/path input escapes repository"
        ) from error
    if not path.is_file() or _sha(path) != binding["sha256"]:
        raise CanonicalWristPathStaticError(
            f"bound canonical wrist/path input changed: {path}"
        )
    return path


def _json(binding: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(_bound(binding).read_text(encoding="utf-8"))


def _geom_name(model: mujoco.MjModel, geom_id: int) -> str:
    return (
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_id)
        or f"geom-{geom_id}"
    )


def _first_contact_witness(
    *,
    model: mujoco.MjModel,
    addresses: list[int],
    seed: np.ndarray,
    action: np.ndarray,
    selected_name: str,
    jaw_bodies: set[int],
) -> dict[str, Any]:
    data = mujoco.MjData(model)
    selected_id = _static._named_id(
        model, mujoco.mjtObj.mjOBJ_BODY, selected_name
    )
    data.qpos[addresses] = seed
    mujoco.mj_forward(model, data)
    initial_z = float(data.xpos[selected_id][2])
    for row_index, row in enumerate(action):
        data.qpos[addresses] = row
        data.qvel[:] = 0.0
        mujoco.mj_forward(model, data)
        for contact_index in range(data.ncon):
            contact = data.contact[contact_index]
            geom1, geom2 = int(contact.geom1), int(contact.geom2)
            body1 = int(model.geom_bodyid[geom1])
            body2 = int(model.geom_bodyid[geom2])
            bodies = {body1, body2}
            if selected_id not in bodies or not (bodies & jaw_bodies):
                continue
            jaw_geom = geom1 if body1 in jaw_bodies else geom2
            pawn_geom = geom2 if jaw_geom == geom1 else geom1
            normal = np.asarray(contact.frame[:3], dtype=np.float64)
            if jaw_geom == geom2:
                normal = -normal
            return {
                "observed": True,
                "row_index": row_index,
                "jaw_geom": _geom_name(model, jaw_geom),
                "pawn_geom": _geom_name(model, pawn_geom),
                "contact_height_relative_initial_pawn_root_m": float(
                    contact.pos[2] - initial_z
                ),
                "absolute_vertical_normal_component": float(abs(normal[2])),
            }
    return {
        "observed": False,
        "row_index": None,
        "jaw_geom": None,
        "pawn_geom": None,
        "contact_height_relative_initial_pawn_root_m": None,
        "absolute_vertical_normal_component": None,
    }


def _compile(
    *,
    model: mujoco.MjModel,
    addresses: list[int],
    live_seed: np.ndarray,
    candidate_config: Mapping[str, Any],
    source_xyz: np.ndarray,
    direction: np.ndarray,
    wrist_roll_rad: float,
    contact_offset_m: float,
    contact_height_m: float,
    clearance_height_m: float,
    stroke_m: float,
    closed_jaw_rad: float,
    sample_hz: float,
    target_rates: np.ndarray,
    maximum_ik_residual_m: float,
    precontact_backoff_m: float = 0.0,
) -> tuple[np.ndarray, dict[str, Any]]:
    closed_seed = live_seed.copy()
    closed_seed[-1] = closed_jaw_rad
    data = mujoco.MjData(model)
    data.qpos[addresses] = closed_seed
    mujoco.mj_forward(model, data)
    pinch_local = _static._pinch_offset(model, data, "left")
    current_pinch = _static._pinch_point(
        model, data, "left", pinch_local
    )
    contact = source_xyz.copy()
    contact[:2] -= direction[:2] * contact_offset_m
    contact[2] += contact_height_m
    live_lift = current_pinch.copy()
    live_lift[2] = max(
        current_pinch[2] + 0.03,
        source_xyz[2] + clearance_height_m,
    )
    clearance = contact.copy()
    clearance[2] = source_xyz[2] + clearance_height_m
    low_precontact = contact - direction * precontact_backoff_m
    precontact_clearance = low_precontact.copy()
    precontact_clearance[2] = clearance[2]
    pushed = contact + direction * stroke_m
    retreat = pushed.copy()
    retreat[2] = clearance[2]
    if precontact_backoff_m > 0.0:
        cartesian_targets = [
            live_lift,
            live_lift,
            precontact_clearance,
            low_precontact,
            contact,
            pushed,
            retreat,
        ]
    else:
        cartesian_targets = [
            live_lift,
            live_lift,
            clearance,
            contact,
            pushed,
            retreat,
        ]
    targets = [live_seed.copy(), closed_seed.copy()]
    active = closed_seed.copy()
    residuals: list[float] = []
    for index, target in enumerate(cartesian_targets):
        if index == 1:
            active[4] = wrist_roll_rad
        active, residual = _static._solve_fixed_roll(
            model,
            active,
            target,
            pinch_local,
            iterations=260,
            damping=0.015,
            step_limit=0.08,
        )
        residuals.append(float(residual))
        if residual > maximum_ik_residual_m:
            raise CanonicalWristPathStaticError(
                "canonical lifted-wrist IK residual exceeded gate"
            )
        active[-1] = closed_jaw_rad
        targets.append(active.copy())
    action = _static._interpolate_targets(
        targets,
        candidate_config,
        sample_hz=sample_hz,
        target_rates=target_rates,
    )
    if not np.array_equal(action[0], live_seed):
        raise CanonicalWristPathStaticError(
            "canonical wrist/path row zero changed"
        )
    margins = []
    for index, name in enumerate(_static.ALL_JOINTS):
        joint_id = _static._named_id(
            model, mujoco.mjtObj.mjOBJ_JOINT, name
        )
        low, high = model.jnt_range[joint_id]
        margins.append(
            float(
                min(
                    np.min(action[:, index] - low),
                    np.min(high - action[:, index]),
                )
            )
        )
    return action, {
        "maximum_ik_residual_m": max(residuals),
        "minimum_model_joint_margin_rad": min(margins),
        "cartesian_targets_xyz_m": [
            item.tolist() for item in cartesian_targets
        ],
        "wrist_roll_target_rad": wrist_roll_rad,
        "wrist_rotation_after_live_lift": True,
        "precontact_backoff_m": precontact_backoff_m,
        "low_horizontal_precontact_approach": precontact_backoff_m > 0.0,
        "action_rows": len(action),
        "action_raw_float64le_sha256": hashlib.sha256(
            action.tobytes(order="C")
        ).hexdigest(),
    }


def enumerate_and_freeze(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Run the prospective finite static successor once."""

    if output_directory.exists():
        raise CanonicalWristPathStaticError(
            "immutable canonical wrist/path output already exists"
        )
    raw_contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract = raw_contract
    if raw_contract.get("schema_version") == (
        "sim2claw.canonical_wrist_path_static_successor.v2"
    ):
        expected = {
            "schema_version",
            "contract_id",
            "status",
            "proof_class",
            "predecessor_contract",
            "preexecution_closeout",
            "implementation",
            "output_directory",
            "unchanged_from_v1",
            "claim_boundary",
        }
        if (
            set(raw_contract) != expected
            or not all(raw_contract["unchanged_from_v1"].values())
        ):
            raise CanonicalWristPathStaticError(
                "canonical wrist/path V2 widened its change surface"
            )
        contract = copy.deepcopy(
            _json(raw_contract["predecessor_contract"])
        )
        _bound(raw_contract["preexecution_closeout"])
        _bound(raw_contract["implementation"])
        contract["inputs"]["implementation"] = raw_contract[
            "implementation"
        ]
        contract["output_directory"] = raw_contract["output_directory"]
        contract["claim_boundary"] = raw_contract["claim_boundary"]
    elif raw_contract.get("schema_version") == (
        "sim2claw.canonical_wrist_path_static_successor.v3"
    ):
        expected = {
            "schema_version",
            "contract_id",
            "status",
            "proof_class",
            "base_contract",
            "predecessor_closeout",
            "implementation",
            "path_shape_override",
            "output_directory",
            "unchanged_from_v2",
            "claim_boundary",
        }
        if (
            set(raw_contract) != expected
            or not all(raw_contract["unchanged_from_v2"].values())
            or raw_contract["path_shape_override"]
            != {
                "from": "rotate wrist at low live pose before lift",
                "to": "lift with live wrist then rotate at clearance",
                "only_outcome_relevant_change": True,
            }
        ):
            raise CanonicalWristPathStaticError(
                "canonical wrist/path V3 widened its change surface"
            )
        contract = copy.deepcopy(_json(raw_contract["base_contract"]))
        _bound(raw_contract["predecessor_closeout"])
        _bound(raw_contract["implementation"])
        contract["inputs"]["implementation"] = raw_contract[
            "implementation"
        ]
        contract["action"]["path_shape"] = raw_contract[
            "path_shape_override"
        ]["to"]
        contract["output_directory"] = raw_contract["output_directory"]
        contract["claim_boundary"] = raw_contract["claim_boundary"]
    elif raw_contract.get("schema_version") == (
        "sim2claw.canonical_wrist_path_static_successor.v4"
    ):
        expected = {
            "schema_version",
            "contract_id",
            "status",
            "proof_class",
            "base_contract",
            "predecessor_closeout",
            "implementation",
            "path_shape_override",
            "output_directory",
            "unchanged_from_v3",
            "claim_boundary",
        }
        override = raw_contract.get("path_shape_override")
        if (
            set(raw_contract) != expected
            or not all(raw_contract["unchanged_from_v3"].values())
            or override
            != {
                "from": "vertical descent at contact offset",
                "to": (
                    "descend at a 0.035 m rear standoff then approach "
                    "contact horizontally"
                ),
                "precontact_backoff_m": 0.035,
                "derivation": (
                    "0.015 m modeled jaw collision half width plus "
                    "0.010 m modeled pawn radius plus 0.010 m margin"
                ),
                "only_outcome_relevant_change": True,
            }
        ):
            raise CanonicalWristPathStaticError(
                "canonical wrist/path V4 widened its change surface"
            )
        contract = copy.deepcopy(_json(raw_contract["base_contract"]))
        _bound(raw_contract["predecessor_closeout"])
        _bound(raw_contract["implementation"])
        contract["inputs"]["implementation"] = raw_contract[
            "implementation"
        ]
        contract["action"]["path_shape"] = override["to"]
        contract["action"]["precontact_backoff_m"] = override[
            "precontact_backoff_m"
        ]
        contract["output_directory"] = raw_contract["output_directory"]
        contract["claim_boundary"] = raw_contract["claim_boundary"]
    elif raw_contract.get("schema_version") != (
        "sim2claw.canonical_wrist_path_static.v1"
    ):
        raise CanonicalWristPathStaticError(
            "unexpected canonical wrist/path contract"
        )
    for binding in contract["inputs"].values():
        _bound(binding)
    proxy_closeout = _json(contract["inputs"]["proxy_closeout"])
    static_receipt = _json(contract["inputs"]["static_receipt"])
    manifest = _json(contract["inputs"]["candidate_manifest"])
    rigid = _json(contract["inputs"]["registration_candidate"])
    if (
        proxy_closeout["status"]
        != "proxy_only_collision_challenger_rejected"
        or static_receipt["status"]
        != "canonical_seeded_action_static_v2_pass"
        or contract["authority"]["static_simulation"] is not True
        or any(
            value
            for name, value in contract["authority"].items()
            if name not in {"model_loading", "static_simulation"}
        )
    ):
        raise CanonicalWristPathStaticError(
            "canonical wrist/path admission or authority changed"
        )
    model_builder = _static_v2._calibrated_registered_model(
        _static._registered_current_model,
        manifest["candidate_config"],
    )
    model, addresses, robot_bodies, jaw_bodies = model_builder(
        rigid, float(contract["simulation"]["timestep_s"])
    )
    live_seed = np.asarray(
        contract["live_seed"]["model_radians"], dtype=np.float64
    )
    initial = mujoco.MjData(model)
    initial.qpos[addresses] = live_seed
    mujoco.mj_forward(model, initial)
    quarantine = set(contract["quarantine"]["case_ids"])
    families = [
        row
        for row in _static._families(model)
        if row["case_id"] not in quarantine
    ]
    if (
        len(quarantine) != contract["quarantine"]["exact_count"]
        or len(families)
        != contract["family_universe"]["expected_postquarantine_count"]
    ):
        raise CanonicalWristPathStaticError(
            "canonical wrist/path family universe changed"
        )
    camera = np.asarray(rigid["camera_matrix_3x4"], dtype=np.float64)
    image_width, image_height = contract["camera_gate"]["image_size_px"]
    target_rates = np.asarray(
        contract["action"]["target_rates_per_joint"], dtype=np.float64
    )
    grid_results: list[dict[str, Any]] = []
    winners: list[tuple[dict[str, Any], np.ndarray]] = []
    for family_index, family in enumerate(families):
        selected_id = _static._named_id(
            model,
            mujoco.mjtObj.mjOBJ_BODY,
            family["selected_piece_id"],
        )
        source_xyz = initial.xpos[selected_id].copy()
        source = np.asarray(
            current_square_center(family["source_square"]),
            dtype=np.float64,
        )
        destination = np.asarray(
            current_square_center(family["destination_square"]),
            dtype=np.float64,
        )
        direction = destination - source
        direction /= np.linalg.norm(direction)
        eligible: list[tuple[dict[str, Any], np.ndarray]] = []
        for wrist_index, wrist_roll in enumerate(
            contract["grid"]["wrist_roll_targets_rad"]
        ):
            for height_index, contact_height in enumerate(
                contract["grid"]["contact_heights_m"]
            ):
                base = {
                    **family,
                    "family_index": family_index,
                    "wrist_orientation_index": wrist_index,
                    "wrist_roll_target_rad": wrist_roll,
                    "contact_height_index": height_index,
                    "contact_height_m": contact_height,
                    "contact_offset_m": contract["grid"][
                        "contact_offset_m"
                    ],
                    "stroke_m": contract["grid"]["stroke_m"],
                }
                try:
                    action, compile_metrics = _compile(
                        model=model,
                        addresses=addresses,
                        live_seed=live_seed,
                        candidate_config=manifest["candidate_config"],
                        source_xyz=source_xyz,
                        direction=direction,
                        wrist_roll_rad=float(wrist_roll),
                        contact_offset_m=float(
                            contract["grid"]["contact_offset_m"]
                        ),
                        contact_height_m=float(contact_height),
                        clearance_height_m=float(
                            contract["grid"]["clearance_height_m"]
                        ),
                        stroke_m=float(contract["grid"]["stroke_m"]),
                        closed_jaw_rad=float(
                            contract["action"]["closed_jaw_rad"]
                        ),
                        sample_hz=float(contract["action"]["sample_hz"]),
                        target_rates=target_rates,
                        maximum_ik_residual_m=float(
                            contract["gates"]["maximum_ik_residual_m"]
                        ),
                        precontact_backoff_m=float(
                            contract["action"].get(
                                "precontact_backoff_m", 0.0
                            )
                        ),
                    )
                except (RuntimeError, ValueError) as error:
                    grid_results.append(
                        {
                            **base,
                            "status": "compile_reject",
                            "error": str(error),
                            "static_eligible": False,
                        }
                    )
                    continue
                collision = _static._static_audit(
                    model,
                    addresses,
                    live_seed,
                    action,
                    family["selected_piece_id"],
                    robot_bodies,
                    jaw_bodies,
                )
                gateway = _static._gateway_audit(
                    action, manifest["candidate_config"], contract
                )
                terminal = source_xyz + direction * float(
                    contract["grid"]["stroke_m"]
                )
                pixels = _static.project(
                    camera, np.asarray([source_xyz, terminal])
                )
                camera_margin = float(
                    np.min(
                        np.column_stack(
                            (
                                pixels[:, 0],
                                image_width - pixels[:, 0],
                                pixels[:, 1],
                                image_height - pixels[:, 1],
                            )
                        )
                    )
                )
                witness = _first_contact_witness(
                    model=model,
                    addresses=addresses,
                    seed=live_seed,
                    action=action,
                    selected_name=family["selected_piece_id"],
                    jaw_bodies=jaw_bodies,
                )
                checks = {
                    "collision": collision["passed"],
                    "gateway_limits": gateway[
                        "all_rows_inside_calibrated_limits"
                    ],
                    "gateway_rates": gateway[
                        "all_rates_within_gateway_limits"
                    ],
                    "camera": camera_margin
                    >= contract["camera_gate"]["minimum_margin_px"],
                    "contact_witness": witness["observed"],
                    "contact_height": witness["observed"]
                    and witness[
                        "contact_height_relative_initial_pawn_root_m"
                    ]
                    <= contract["gates"][
                        "maximum_first_contact_height_m"
                    ],
                    "contact_normal": witness["observed"]
                    and witness["absolute_vertical_normal_component"]
                    <= contract["gates"][
                        "maximum_first_contact_abs_vertical_normal"
                    ],
                }
                row = {
                    **base,
                    "compile": compile_metrics,
                    "collision": collision,
                    "gateway": gateway,
                    "camera": {
                        "minimum_margin_px": camera_margin,
                        "passed": checks["camera"],
                    },
                    "first_contact_witness": witness,
                    "checks": checks,
                    "static_eligible": all(checks.values()),
                }
                row["status"] = (
                    "static_eligible"
                    if row["static_eligible"]
                    else "static_reject"
                )
                grid_results.append(row)
                if row["static_eligible"]:
                    eligible.append((row, action))
        if eligible:
            eligible.sort(
                key=lambda item: (
                    item[0]["first_contact_witness"][
                        "absolute_vertical_normal_component"
                    ],
                    item[0]["first_contact_witness"][
                        "contact_height_relative_initial_pawn_root_m"
                    ],
                    -item[0]["compile"]["minimum_model_joint_margin_rad"],
                    -item[0]["camera"]["minimum_margin_px"],
                    item[0]["compile"]["maximum_ik_residual_m"],
                    item[0]["wrist_orientation_index"],
                    item[0]["contact_height_index"],
                    item[0]["case_id"],
                )
            )
            winners.append(eligible[0])
    winners.sort(
        key=lambda item: (
            item[0]["first_contact_witness"][
                "absolute_vertical_normal_component"
            ],
            item[0]["first_contact_witness"][
                "contact_height_relative_initial_pawn_root_m"
            ],
            -item[0]["compile"]["minimum_model_joint_margin_rad"],
            item[0]["case_id"],
        )
    )
    selected = winners[: int(contract["selection"]["selected_count"])]
    output_directory.mkdir(parents=True)
    action_directory = output_directory / "actions"
    action_directory.mkdir()
    selected_rows = []
    for index, (row, action) in enumerate(selected):
        path = action_directory / f"{index:02d}.f64le"
        path.write_bytes(action.tobytes(order="C"))
        selected_rows.append(
            {
                **row,
                "direction": (
                    "REAL_TO_SIM" if index % 2 == 0 else "SIM_TO_REAL"
                ),
                "action_path": str(path.relative_to(REPO_ROOT)),
                "action_sha256": _sha(path),
                "action_shape": list(action.shape),
            }
        )
    counts = {
        direction: sum(row["direction"] == direction for row in selected_rows)
        for direction in ("REAL_TO_SIM", "SIM_TO_REAL")
    }
    required = int(contract["selection"]["minimum_per_direction"])
    passed = (
        len(selected_rows) == int(contract["selection"]["selected_count"])
        and all(count >= required for count in counts.values())
    )
    receipt = {
        "schema_version": "sim2claw.canonical_wrist_path_static_receipt.v1",
        "status": (
            "canonical_wrist_path_static_pass"
            if passed
            else "canonical_wrist_path_static_reject"
        ),
        "proof_class": "cpu_fp64_current_workcell_wrist_path_contact_normal_static_action_freeze",
        "contract_path": str(contract_path.relative_to(REPO_ROOT)),
        "contract_sha256": _sha(contract_path),
        "family_count": len(families),
        "grid_result_count": len(grid_results),
        "statically_eligible_family_count": len(winners),
        "selected": selected_rows,
        "direction_counts": counts,
        "minimum_per_direction": required,
        "passed": passed,
        "grid_results": grid_results,
        "dynamic_replay_executed": False,
        "physical_motion": False,
        "physical_task_attempts": 0,
        "authority": contract["authority"],
        "claim_boundary": contract["claim_boundary"],
    }
    (output_directory / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = ["CanonicalWristPathStaticError", "enumerate_and_freeze"]

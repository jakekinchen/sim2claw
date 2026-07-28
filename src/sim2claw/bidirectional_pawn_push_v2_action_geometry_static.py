"""Prospective V05-TK static-only action-geometry successor freezer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from . import bidirectional_pawn_push_v2_sim_rehearsal as _rehearsal
from . import bidirectional_pawn_push_v2_sim_rehearsal_v2 as _rehearsal_v2
from . import bidirectional_pawn_push_v2_temporal_static as _static
from .paths import REPO_ROOT
from .physical_canary import _physical_to_model_position
from .scene import board_square_center


class ActionGeometryStaticError(RuntimeError):
    """The prospectively frozen V05-TK static search failed closed."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(path: Path) -> Path:
    resolved = path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise ActionGeometryStaticError(
            "V05-TK path escapes repository"
        ) from error
    return resolved


def _bound(entry: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
    path = _resolve(Path(str(entry["path"])))
    if not path.is_file() or _sha(path) != entry["sha256"]:
        raise ActionGeometryStaticError(f"bound V05-TK input changed: {path}")
    return path, json.loads(path.read_text(encoding="utf-8"))


def _case_id(case: Mapping[str, str]) -> str:
    return (
        f"{case['selected_piece_id']}__"
        f"{case['source_square']}_{case['destination_square']}"
    )


def _fractional_gateway_margins(
    action: np.ndarray,
    wrapper: Mapping[str, Any],
    gateway: Mapping[str, Any],
) -> tuple[float, float]:
    physical = _static._physical_actions(action, wrapper)
    lower = np.asarray(gateway["calibrated_physical_lower"], dtype=np.float64)
    upper = np.asarray(gateway["calibrated_physical_upper"], dtype=np.float64)
    span = upper - lower
    if np.any(span <= 0.0):
        raise ActionGeometryStaticError("gateway bound span is invalid")
    lower_margin = (physical - lower[None, :]) / span[None, :]
    upper_margin = (upper[None, :] - physical) / span[None, :]
    bound_margin = float(np.min(np.minimum(lower_margin, upper_margin)))

    rates = np.asarray(
        gateway["maximum_absolute_rate_per_second"], dtype=np.float64
    )
    limits = np.asarray(
        gateway["reviewed_gateway_rate_limit_per_second"], dtype=np.float64
    )
    if np.any(limits <= 0.0):
        raise ActionGeometryStaticError("gateway rate limit is invalid")
    rate_margin = float(np.min((limits - rates) / limits))
    return bound_margin, rate_margin


def _selection_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    """Prefer static safety headroom only, then frozen grid order."""

    return (
        -float(row["compile"]["minimum_arm_joint_limit_margin_rad"]),
        -float(row["gateway_bound_fractional_margin"]),
        -float(row["gateway_rate_fractional_margin"]),
        -float(row["camera"]["minimum_margin_px"]),
        float(row["compile"]["maximum_ik_residual_m"]),
        int(row["contact_offset_index"]),
        int(row["contact_height_index"]),
        int(row["stroke_index"]),
        str(row["case_id"]),
    )


def enumerate_and_freeze(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    public_contract = _resolve(contract_path)
    public_output = _resolve(output_directory)
    contract = json.loads(public_contract.read_text(encoding="utf-8"))
    if (
        contract.get("schema_version")
        != "sim2claw.bidirectional_pawn_push_v2_action_geometry_static.v1"
    ):
        raise ActionGeometryStaticError("unexpected V05-TK static contract")

    _, authorization = _bound(contract["authorization"])
    _bound(contract["rehearsal_contract"])
    _bound(contract["temporal_plan"])
    _bound(contract["geometry_source"])
    _bound(contract["scene_implementation"])
    _, wrapper = _bound(contract["candidate_manifest"])
    _, rigid = _bound(contract["registration_candidate"])
    if authorization["quarantine"]["case_ids"] != contract["quarantine"][
        "case_ids"
    ]:
        raise ActionGeometryStaticError("V05-TK quarantine changed")
    quarantine = set(contract["quarantine"]["case_ids"])
    if len(quarantine) != 4:
        raise ActionGeometryStaticError("V05-TK quarantine is not exact")

    model, qpos, _, jaw_bodies = _rehearsal._registered_model(
        wrapper,
        rigid,
        float(contract["simulation"]["timestep_s"]),
    )
    seed_physical = np.asarray(
        [contract["action_identity"]["seed_physical"]], dtype=np.float64
    )
    seed_model = _physical_to_model_position(
        seed_physical, wrapper["candidate_config"]
    )[0]
    initial = mujoco.MjData(model)
    initial.qpos[qpos] = seed_model
    mujoco.mj_forward(model, initial)
    pieces = _static._pawn_layout(model)
    complete_universe = _static.enumerate_empty_orthogonal_neighbors(
        pieces,
        excluded_squares=contract["family_grid"]["excluded_source_squares"],
    )
    if len(complete_universe) != int(
        contract["family_grid"]["expected_prequarantine_family_count"]
    ):
        raise ActionGeometryStaticError(
            "V05-TK reset-layout family universe changed"
        )
    universe = [
        case for case in complete_universe if _case_id(case) not in quarantine
    ]
    if len(universe) != int(
        contract["family_grid"]["expected_postquarantine_family_count"]
    ):
        raise ActionGeometryStaticError(
            "V05-TK post-quarantine family universe changed"
        )
    if any(_case_id(case) in quarantine for case in universe):
        raise ActionGeometryStaticError(
            "V05-TK quarantine leaked into candidate universe"
        )

    camera = np.asarray(rigid["camera_matrix_3x4"], dtype=np.float64)
    image_size = tuple(contract["camera_gate"]["image_size_px"])
    minimum_camera_margin = float(contract["camera_gate"]["minimum_margin_px"])
    robot_bodies = _static._descendants(model, "left_base")
    sample_hz = float(contract["action_identity"]["sample_hz"])
    closed_jaw = float(contract["action_identity"]["closed_jaw_rad"])
    if closed_jaw != -0.1727003294848389:
        raise ActionGeometryStaticError("V05-TK jaw scalar changed")

    public_output.mkdir(parents=True, exist_ok=True)
    actions_directory = public_output / "actions"
    actions_directory.mkdir(parents=True, exist_ok=True)
    grid_results: list[dict[str, Any]] = []
    family_winners: list[tuple[dict[str, Any], np.ndarray]] = []

    for family_index, case in enumerate(universe):
        selected_id = mujoco.mj_name2id(
            model,
            mujoco.mjtObj.mjOBJ_BODY,
            case["selected_piece_id"],
        )
        if selected_id < 0:
            raise ActionGeometryStaticError("V05-TK selected pawn is missing")
        source_xyz = initial.xpos[selected_id].copy()
        source_center = np.asarray(
            board_square_center(case["source_square"]), dtype=np.float64
        )
        destination_center = np.asarray(
            board_square_center(case["destination_square"]), dtype=np.float64
        )
        direction = destination_center - source_center
        direction /= np.linalg.norm(direction)
        case_id = _case_id(case)
        passing_cells: list[tuple[dict[str, Any], np.ndarray]] = []

        for offset_index, contact_offset in enumerate(
            contract["parameter_grid"]["contact_center_offsets_m"]
        ):
            for height_index, contact_height in enumerate(
                contract["parameter_grid"]["contact_heights_m"]
            ):
                for stroke_index, stroke in enumerate(
                    contract["parameter_grid"]["stroke_lengths_m"]
                ):
                    start = source_xyz.copy()
                    start[:2] -= direction[:2] * float(contact_offset)
                    start[2] += float(contact_height)
                    base = {
                        "case_id": case_id,
                        "family_id": case_id,
                        "family_index": family_index,
                        **case,
                        "contact_center_offset_m": contact_offset,
                        "contact_offset_index": offset_index,
                        "contact_height_m": contact_height,
                        "contact_height_index": height_index,
                        "stroke_m": stroke,
                        "stroke_index": stroke_index,
                    }
                    try:
                        action, compile_metrics = (
                            _rehearsal_v2._compile_action_v2(
                                model=model,
                                qpos_addresses=qpos,
                                seed_model=seed_model,
                                start_xyz=start,
                                direction=direction,
                                stroke_m=float(stroke),
                                sample_hz=sample_hz,
                                speed_m_s=float(
                                    contract["action_identity"][
                                        "cartesian_speed_m_s"
                                    ]
                                ),
                                closed_jaw_rad=closed_jaw,
                                maximum_ik_residual_m=float(
                                    contract["static_gates"][
                                        "maximum_ik_residual_m"
                                    ]
                                ),
                            )
                        )
                    except _rehearsal.PushRehearsalError as error:
                        grid_results.append(
                            {
                                **base,
                                "status": "compile_reject",
                                "error": str(error),
                                "static_eligible": False,
                            }
                        )
                        continue
                    if not np.all(action[:, 5] == closed_jaw):
                        raise ActionGeometryStaticError(
                            "V05-TK action lost exact jaw scalar"
                        )
                    collision = _static._collision_audit(
                        model=model,
                        qpos_addresses=qpos,
                        seed_model=seed_model,
                        action=action,
                        selected_piece_id=case["selected_piece_id"],
                        robot_bodies=robot_bodies,
                        jaw_bodies=jaw_bodies,
                    )
                    camera_audit = _static._camera_audit(
                        camera,
                        source_xyz,
                        direction,
                        float(stroke),
                        image_size,
                        minimum_camera_margin,
                    )
                    gateway = _static._gateway_audit(
                        action,
                        wrapper,
                        sample_hz=sample_hz,
                    )
                    bound_margin, rate_margin = _fractional_gateway_margins(
                        action, wrapper, gateway
                    )
                    checks = {
                        "ik": compile_metrics["maximum_ik_residual_m"]
                        <= contract["static_gates"][
                            "maximum_ik_residual_m"
                        ],
                        "arm_joint_margin": compile_metrics[
                            "minimum_arm_joint_limit_margin_rad"
                        ]
                        >= contract["static_gates"][
                            "minimum_arm_joint_limit_margin_rad"
                        ],
                        "jaw_target": compile_metrics[
                            "maximum_closed_jaw_target_error_rad"
                        ]
                        <= contract["static_gates"][
                            "jaw_target_tolerance_rad"
                        ],
                        "selected_contact": collision[
                            "static_selected_contact_observed"
                        ],
                        "collision": collision["collision_free"],
                        "camera": camera_audit["camera_gate_passed"],
                        "gateway_limits": gateway[
                            "all_rows_inside_calibrated_limits"
                        ],
                        "gateway_rates": gateway[
                            "all_rates_within_reviewed_gateway_limits"
                        ],
                        "requested_sent_identity": gateway[
                            "requested_sent_byte_identical"
                        ],
                    }
                    row = {
                        **base,
                        "compile": compile_metrics,
                        "collision": collision,
                        "camera": camera_audit,
                        "gateway": gateway,
                        "gateway_bound_fractional_margin": bound_margin,
                        "gateway_rate_fractional_margin": rate_margin,
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
                        passing_cells.append((row, action))
        if passing_cells:
            family_winners.append(min(passing_cells, key=lambda item: _selection_key(item[0])))

    selected_family_count = int(
        contract["selection"]["selected_family_count"]
    )
    family_winners.sort(key=lambda item: _selection_key(item[0]))
    selected = family_winners[:selected_family_count]
    eligible_cases: list[dict[str, Any]] = []
    for selected_index, (row, action) in enumerate(selected):
        lane = (
            "REAL_TO_SIM"
            if selected_index % 2 == 0
            else "SIM_TO_REAL"
        )
        action_bytes = np.asarray(action, dtype="<f8", order="C").tobytes(
            order="C"
        )
        action_path = actions_directory / f"{selected_index:02d}.f64le"
        action_path.write_bytes(action_bytes)
        eligible_cases.append(
            {
                "case_id": row["case_id"],
                "family_id": row["family_id"],
                "direction_lane": lane,
                "source_square": row["source_square"],
                "destination_square": row["destination_square"],
                "selected_piece_id": row["selected_piece_id"],
                "contact_center_offset_m": row[
                    "contact_center_offset_m"
                ],
                "contact_height_m": row["contact_height_m"],
                "stroke_m": row["stroke_m"],
                "action_path": str(action_path.relative_to(REPO_ROOT)),
                "action_sha256": hashlib.sha256(action_bytes).hexdigest(),
                "action_shape": list(action.shape),
                "action_dtype": "little_endian_float64",
                "sample_hz": sample_hz,
                "compile": row["compile"],
                "camera": row["camera"],
                "collision": row["collision"],
                "gateway": row["gateway"],
                "gateway_bound_fractional_margin": row[
                    "gateway_bound_fractional_margin"
                ],
                "gateway_rate_fractional_margin": row[
                    "gateway_rate_fractional_margin"
                ],
            }
        )

    lane_counts = {
        lane: sum(row["direction_lane"] == lane for row in eligible_cases)
        for lane in ("REAL_TO_SIM", "SIM_TO_REAL")
    }
    minimum = int(
        contract["selection"]["minimum_distinct_families_per_direction"]
    )
    passed = (
        len(family_winners) >= selected_family_count
        and len({row["family_id"] for row in eligible_cases})
        == selected_family_count
        and min(lane_counts.values(), default=0) >= minimum
    )
    receipt = {
        "schema_version": (
            "sim2claw."
            "bidirectional_pawn_push_v2_action_geometry_static_receipt.v1"
        ),
        "status": (
            "static_action_geometry_freeze_pass"
            if passed
            else "static_action_geometry_freeze_reject"
        ),
        "proof_class": (
            "cpu_fp64_static_action_geometry_ik_collision_camera_gateway_"
            "action_freeze_only"
        ),
        "contract_path": str(public_contract.relative_to(REPO_ROOT)),
        "contract_sha256": _sha(public_contract),
        "authorization_sha256": contract["authorization"]["sha256"],
        "quarantined_case_ids": list(contract["quarantine"]["case_ids"]),
        "quarantined_case_count": len(quarantine),
        "quarantine_leaked_into_candidates": False,
        "selection_used_dynamic_outcomes": False,
        "prequarantine_family_count": len(complete_universe),
        "postquarantine_family_count": len(universe),
        "parameter_cell_count_per_family": (
            len(contract["parameter_grid"]["contact_center_offsets_m"])
            * len(contract["parameter_grid"]["contact_heights_m"])
            * len(contract["parameter_grid"]["stroke_lengths_m"])
        ),
        "grid_result_count": len(grid_results),
        "grid_results": grid_results,
        "statically_eligible_family_count": len(family_winners),
        "selected_family_count": len(eligible_cases),
        "eligible_cases": eligible_cases,
        "lane_counts": lane_counts,
        "minimum_distinct_families_per_direction": minimum,
        "dynamic_replay_executed": False,
        "physical_motion": False,
        "physical_task_attempts": 0,
        "authority": contract["authority"],
        "claim_boundary": (
            "Static-only deterministic action-geometry search and exact "
            "action freeze over nonquarantined reset-layout families. No "
            "dynamic task outcome, calibrated plant, physical packet, "
            "promotion, or transfer claim."
        ),
    }
    receipt_path = public_output / "receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = ["ActionGeometryStaticError", "enumerate_and_freeze"]

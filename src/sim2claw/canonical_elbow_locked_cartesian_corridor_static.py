"""Exact-lock static successor with a chord-constrained Cartesian corridor."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from . import achieved_lock_task_freeze as _achieved
from . import canonical_elbow_locked_low_path_static as _low
from . import canonical_seeded_action_static as _static
from . import canonical_wrist_path_static as _wrist
from .paths import REPO_ROOT


class CartesianCorridorStaticError(RuntimeError):
    """The frozen corridor contract or its Cartesian audit failed closed."""


MAXIMUM_CARTESIAN_CHORD_ERROR_M = 0.0005
MAXIMUM_REFINEMENT_DEPTH = 6
MAXIMUM_POST_CONTACT_BACKTRACK_M = 0.00025


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(binding: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(binding["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise CartesianCorridorStaticError(
            "Cartesian-corridor input escaped repository"
        ) from error
    if not path.is_file() or _sha(path) != binding["sha256"]:
        raise CartesianCorridorStaticError(
            f"Cartesian-corridor input changed: {path}"
        )
    return path


def _pinch_fk(
    model: mujoco.MjModel,
    addresses: list[int],
    qpos: np.ndarray,
    pinch_local: np.ndarray,
) -> np.ndarray:
    data = mujoco.MjData(model)
    data.qpos[addresses] = qpos
    mujoco.mj_forward(model, data)
    return _static._pinch_point(model, data, "left", pinch_local).copy()


def _point_to_segment_error(
    point: np.ndarray,
    first: np.ndarray,
    second: np.ndarray,
) -> tuple[float, np.ndarray]:
    delta = second - first
    length_squared = float(delta @ delta)
    if length_squared <= np.finfo(np.float64).eps:
        return float(np.linalg.norm(point - first)), first.copy()
    blend = float(np.clip(((point - first) @ delta) / length_squared, 0, 1))
    closest = first + blend * delta
    return float(np.linalg.norm(point - closest)), closest


def _refine_segment(
    *,
    model: mujoco.MjModel,
    addresses: list[int],
    pinch_local: np.ndarray,
    desired_first: np.ndarray,
    qpos_first: np.ndarray,
    desired_second: np.ndarray,
    qpos_second: np.ndarray,
    maximum_ik_residual_m: float,
    depth: int = 0,
) -> tuple[list[tuple[np.ndarray, np.ndarray]], list[float]]:
    qpos_midpoint_linear = 0.5 * (qpos_first + qpos_second)
    actual_first = _pinch_fk(
        model, addresses, qpos_first, pinch_local
    )
    actual_second = _pinch_fk(
        model, addresses, qpos_second, pinch_local
    )
    actual_midpoint_linear = _pinch_fk(
        model, addresses, qpos_midpoint_linear, pinch_local
    )
    chord_error, _ = _point_to_segment_error(
        actual_midpoint_linear, actual_first, actual_second
    )
    if chord_error <= MAXIMUM_CARTESIAN_CHORD_ERROR_M:
        return [
            (desired_first.copy(), qpos_first.copy()),
            (desired_second.copy(), qpos_second.copy()),
        ], []
    if depth >= MAXIMUM_REFINEMENT_DEPTH:
        raise CartesianCorridorStaticError(
            "Cartesian chord refinement exhausted"
        )
    desired_midpoint = 0.5 * (desired_first + desired_second)
    qpos_midpoint, residual = _static._solve_fixed_roll(
        model,
        qpos_midpoint_linear,
        desired_midpoint,
        pinch_local,
        iterations=260,
        damping=0.015,
        step_limit=0.08,
    )
    if residual > maximum_ik_residual_m:
        raise CartesianCorridorStaticError(
            "Cartesian midpoint IK residual exceeded gate"
        )
    qpos_midpoint[-1] = qpos_first[-1]
    left, left_residuals = _refine_segment(
        model=model,
        addresses=addresses,
        pinch_local=pinch_local,
        desired_first=desired_first,
        qpos_first=qpos_first,
        desired_second=desired_midpoint,
        qpos_second=qpos_midpoint,
        maximum_ik_residual_m=maximum_ik_residual_m,
        depth=depth + 1,
    )
    right, right_residuals = _refine_segment(
        model=model,
        addresses=addresses,
        pinch_local=pinch_local,
        desired_first=desired_midpoint,
        qpos_first=qpos_midpoint,
        desired_second=desired_second,
        qpos_second=qpos_second,
        maximum_ik_residual_m=maximum_ik_residual_m,
        depth=depth + 1,
    )
    return (
        left[:-1] + right,
        [float(residual), *left_residuals, *right_residuals],
    )


def _interpolate_pairs(
    targets: list[np.ndarray],
    candidate_config: Mapping[str, Any],
    *,
    sample_hz: float,
    target_rates: np.ndarray,
) -> tuple[np.ndarray, list[tuple[int, int]]]:
    rows = [targets[0].copy()]
    spans: list[tuple[int, int]] = []
    for first, second in zip(targets[:-1], targets[1:], strict=True):
        segment = _static._interpolate_targets(
            [first, second],
            candidate_config,
            sample_hz=sample_hz,
            target_rates=target_rates,
        )
        start = len(rows) - 1
        rows.extend(segment[1:])
        spans.append((start, len(rows) - 1))
    return np.asarray(rows, dtype="<f8", order="C"), spans


def _audit_segment(
    *,
    model: mujoco.MjModel,
    addresses: list[int],
    pinch_local: np.ndarray,
    rows: np.ndarray,
    direction: np.ndarray,
) -> dict[str, float]:
    points = np.asarray(
        [
            _pinch_fk(model, addresses, row, pinch_local)
            for row in rows
        ],
        dtype=np.float64,
    )
    first, second = points[0], points[-1]
    lateral = np.asarray(
        [-direction[1], direction[0], 0.0], dtype=np.float64
    )
    errors: list[float] = []
    normal_deviations: list[float] = []
    lateral_deviations: list[float] = []
    progress = (points - first) @ direction
    for point in points:
        error, closest = _point_to_segment_error(point, first, second)
        residual = point - closest
        errors.append(error)
        normal_deviations.append(abs(float(residual[2])))
        lateral_deviations.append(abs(float(residual @ lateral)))
    return {
        "maximum_cartesian_chord_error_m": max(errors, default=0.0),
        "maximum_board_normal_deviation_m": max(
            normal_deviations, default=0.0
        ),
        "maximum_lateral_deviation_m": max(
            lateral_deviations, default=0.0
        ),
        "maximum_task_axis_backtrack_m": max(
            0.0,
            float(-np.min(np.diff(progress))) if len(progress) > 1 else 0.0,
        ),
    }


def _compile_cartesian_corridor(
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
    del clearance_height_m
    if (
        stroke_m != 0.04
        or precontact_backoff_m != 0.035
        or sample_hz != 40.0
    ):
        raise CartesianCorridorStaticError(
            "Cartesian corridor changed frozen endpoint or timing geometry"
        )
    closed_seed = live_seed.copy()
    closed_seed[-1] = closed_jaw_rad
    data = mujoco.MjData(model)
    data.qpos[addresses] = closed_seed
    mujoco.mj_forward(model, data)
    pinch_local = _static._pinch_offset(model, data, "left")
    contact = source_xyz.copy()
    contact[:2] -= direction[:2] * contact_offset_m
    contact[2] += contact_height_m
    low_precontact = contact - direction * precontact_backoff_m
    pushed = contact + direction * stroke_m
    desired_targets = [low_precontact, contact, pushed]

    endpoint_qpos: list[np.ndarray] = []
    residuals: list[float] = []
    active = closed_seed.copy()
    active[4] = wrist_roll_rad
    for target in desired_targets:
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
            raise CartesianCorridorStaticError(
                "Cartesian corridor endpoint IK residual exceeded gate"
            )
        active[-1] = closed_jaw_rad
        endpoint_qpos.append(active.copy())

    refined_targets: list[np.ndarray] = []
    midpoint_residuals: list[float] = []
    corridor_segment_counts: list[int] = []
    for index in range(2):
        refined, new_residuals = _refine_segment(
            model=model,
            addresses=addresses,
            pinch_local=pinch_local,
            desired_first=desired_targets[index],
            qpos_first=endpoint_qpos[index],
            desired_second=desired_targets[index + 1],
            qpos_second=endpoint_qpos[index + 1],
            maximum_ik_residual_m=maximum_ik_residual_m,
        )
        if index:
            refined = refined[1:]
        refined_targets.extend([qpos for _, qpos in refined])
        midpoint_residuals.extend(new_residuals)
        corridor_segment_counts.append(len(refined) - 1 + int(index > 0))

    targets = [live_seed.copy(), closed_seed.copy(), *refined_targets]
    action, spans = _interpolate_pairs(
        targets,
        candidate_config,
        sample_hz=sample_hz,
        target_rates=target_rates,
    )
    if not np.array_equal(action[0], live_seed):
        raise CartesianCorridorStaticError(
            "Cartesian corridor row zero changed"
        )

    corridor_spans = spans[2:]
    segment_audits = [
        _audit_segment(
            model=model,
            addresses=addresses,
            pinch_local=pinch_local,
            rows=action[start : stop + 1],
            direction=direction,
        )
        for start, stop in corridor_spans
    ]
    maximum_chord_error = max(
        (
            audit["maximum_cartesian_chord_error_m"]
            for audit in segment_audits
        ),
        default=0.0,
    )
    maximum_normal_deviation = max(
        (
            audit["maximum_board_normal_deviation_m"]
            for audit in segment_audits
        ),
        default=0.0,
    )
    maximum_lateral_deviation = max(
        (
            audit["maximum_lateral_deviation_m"]
            for audit in segment_audits
        ),
        default=0.0,
    )
    contact_refined_index = corridor_segment_counts[0]
    push_audits = segment_audits[contact_refined_index:]
    maximum_backtrack = max(
        (
            audit["maximum_task_axis_backtrack_m"]
            for audit in push_audits
        ),
        default=0.0,
    )
    if (
        maximum_chord_error > MAXIMUM_CARTESIAN_CHORD_ERROR_M
        or maximum_backtrack > MAXIMUM_POST_CONTACT_BACKTRACK_M
    ):
        raise CartesianCorridorStaticError(
            "emitted Cartesian corridor rows exceeded frozen audit"
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
        "maximum_ik_residual_m": max(
            [*residuals, *midpoint_residuals], default=0.0
        ),
        "minimum_model_joint_margin_rad": min(margins),
        "cartesian_targets_xyz_m": [
            item.tolist() for item in desired_targets
        ],
        "wrist_roll_target_rad": wrist_roll_rad,
        "precontact_backoff_m": precontact_backoff_m,
        "stroke_m": stroke_m,
        "maximum_cartesian_chord_error_m": maximum_chord_error,
        "maximum_board_normal_deviation_m": maximum_normal_deviation,
        "maximum_lateral_deviation_m": maximum_lateral_deviation,
        "maximum_post_contact_task_axis_backtrack_m": maximum_backtrack,
        "maximum_cartesian_chord_error_gate_m": (
            MAXIMUM_CARTESIAN_CHORD_ERROR_M
        ),
        "maximum_post_contact_backtrack_gate_m": (
            MAXIMUM_POST_CONTACT_BACKTRACK_M
        ),
        "maximum_refinement_depth": MAXIMUM_REFINEMENT_DEPTH,
        "refined_corridor_segment_count": len(corridor_spans),
        "midpoint_ik_solve_count": len(midpoint_residuals),
        "exact_elbow_range_rad": float(np.ptp(action[:, 2])),
        "ends_at_pushed_target": True,
        "action_rows": len(action),
        "action_raw_float64le_sha256": hashlib.sha256(
            action.tobytes(order="C")
        ).hexdigest(),
    }


def enumerate_and_freeze(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Run the frozen RP03C static universe exactly once."""

    if output_directory.exists():
        raise CartesianCorridorStaticError(
            "immutable Cartesian-corridor output already exists"
        )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    expected = {
        "schema_version",
        "contract_id",
        "status",
        "proof_class",
        "base_contract",
        "predecessor_closeout",
        "predecessor_temporal_closeout",
        "implementation",
        "intervention",
        "output_directory",
        "unchanged",
        "authority",
        "claim_boundary",
    }
    if (
        set(contract) != expected
        or contract.get("schema_version")
        != "sim2claw.parking_recovery_rp03c_cartesian_corridor_static.v1"
        or contract.get("status")
        != "frozen_before_one_bounded_static_cartesian_corridor_run"
        or not all(contract["unchanged"].values())
        or contract["intervention"]
        != {
            "maximum_cartesian_chord_error_m": (
                MAXIMUM_CARTESIAN_CHORD_ERROR_M
            ),
            "maximum_refinement_depth": MAXIMUM_REFINEMENT_DEPTH,
            "maximum_post_contact_backtrack_m": (
                MAXIMUM_POST_CONTACT_BACKTRACK_M
            ),
            "only_outcome_relevant_change": (
                "joint_interpolation_between_existing_cartesian_endpoints"
            ),
        }
        or any(
            value
            for name, value in contract["authority"].items()
            if name not in {"model_loading", "static_simulation"}
        )
    ):
        raise CartesianCorridorStaticError(
            "RP03C Cartesian-corridor contract widened"
        )
    base_path = _bound(contract["base_contract"])
    _bound(contract["predecessor_closeout"])
    _bound(contract["predecessor_temporal_closeout"])
    _bound(contract["implementation"])
    base = copy.deepcopy(
        json.loads(base_path.read_text(encoding="utf-8"))
    )
    base["contract_id"] = (
        "rp03c-cartesian-corridor-materialized-20260729-v1"
    )
    base["output_directory"] = contract["output_directory"]
    base["claim_boundary"] = contract["claim_boundary"]

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    original_compile = _low._compile_low_direct
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            prefix="rp03c-cartesian-corridor-",
            dir=contract_path.parent,
            delete=False,
            encoding="utf-8",
        ) as handle:
            json.dump(base, handle, indent=2, sort_keys=True)
            handle.write("\n")
            temporary_path = Path(handle.name)
        _low._compile_low_direct = _compile_cartesian_corridor
        receipt = _achieved.enumerate_and_freeze(
            temporary_path.resolve(), output_directory.resolve()
        )
    finally:
        _low._compile_low_direct = original_compile
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    selected_audits_pass = bool(
        receipt["selected"]
        and all(
            row["compile"]["maximum_cartesian_chord_error_m"]
            <= MAXIMUM_CARTESIAN_CHORD_ERROR_M
            and row["compile"][
                "maximum_post_contact_task_axis_backtrack_m"
            ]
            <= MAXIMUM_POST_CONTACT_BACKTRACK_M
            and row["compile"]["exact_elbow_range_rad"] == 0.0
            for row in receipt["selected"]
        )
    )
    passed = bool(receipt["passed"] and selected_audits_pass)
    receipt.update(
        {
            "schema_version": (
                "sim2claw.parking_recovery_rp03c_"
                "cartesian_corridor_static_receipt.v1"
            ),
            "status": (
                "parking_recovery_rp03c_cartesian_corridor_static_pass"
                if passed
                else "parking_recovery_rp03c_cartesian_corridor_static_reject"
            ),
            "proof_class": contract["proof_class"],
            "contract_path": str(contract_path.relative_to(REPO_ROOT)),
            "contract_sha256": _sha(contract_path),
            "selected_cartesian_audits_pass": selected_audits_pass,
            "passed": passed,
            "physical_motion": False,
            "physical_task_attempts": 0,
            "authority": contract["authority"],
            "claim_boundary": contract["claim_boundary"],
        }
    )
    (output_directory / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = [
    "CartesianCorridorStaticError",
    "MAXIMUM_CARTESIAN_CHORD_ERROR_M",
    "MAXIMUM_POST_CONTACT_BACKTRACK_M",
    "MAXIMUM_REFINEMENT_DEPTH",
    "_compile_cartesian_corridor",
    "enumerate_and_freeze",
]

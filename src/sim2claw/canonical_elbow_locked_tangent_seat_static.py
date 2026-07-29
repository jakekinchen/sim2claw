"""Exact-lock static successor with one frozen tangent-seat waypoint."""

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
from . import canonical_elbow_locked_cartesian_corridor_static as _corridor
from . import canonical_elbow_locked_low_path_static as _low
from . import canonical_seeded_action_static as _static
from .paths import REPO_ROOT


class TangentSeatStaticError(RuntimeError):
    """The frozen tangent-seat contract or static audit failed closed."""


TANGENT_SEAT_DEPTH_M = 0.0015


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(binding: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(binding["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise TangentSeatStaticError(
            "tangent-seat input escaped repository"
        ) from error
    if not path.is_file() or _sha(path) != binding["sha256"]:
        raise TangentSeatStaticError(
            f"tangent-seat input changed: {path}"
        )
    return path


def _compile_tangent_seat(
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
        raise TangentSeatStaticError(
            "tangent seat changed frozen endpoint or timing geometry"
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
    desired_targets = [
        contact - direction * precontact_backoff_m,
        contact,
        contact + direction * TANGENT_SEAT_DEPTH_M,
        contact + direction * stroke_m,
    ]

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
            raise TangentSeatStaticError(
                "tangent-seat endpoint IK residual exceeded gate"
            )
        active[-1] = closed_jaw_rad
        endpoint_qpos.append(active.copy())

    refined_qpos: list[np.ndarray] = []
    midpoint_residuals: list[float] = []
    segment_counts: list[int] = []
    for index in range(3):
        refined, new_residuals = _corridor._refine_segment(
            model=model,
            addresses=addresses,
            pinch_local=pinch_local,
            desired_first=desired_targets[index],
            qpos_first=endpoint_qpos[index],
            desired_second=desired_targets[index + 1],
            qpos_second=endpoint_qpos[index + 1],
            maximum_ik_residual_m=maximum_ik_residual_m,
        )
        raw_count = len(refined) - 1
        if index:
            refined = refined[1:]
        refined_qpos.extend([qpos for _, qpos in refined])
        midpoint_residuals.extend(new_residuals)
        segment_counts.append(raw_count)

    targets = [live_seed.copy(), closed_seed.copy(), *refined_qpos]
    action, spans = _corridor._interpolate_pairs(
        targets,
        candidate_config,
        sample_hz=sample_hz,
        target_rates=target_rates,
    )
    if not np.array_equal(action[0], live_seed):
        raise TangentSeatStaticError("tangent-seat row zero changed")
    corridor_spans = spans[2:]
    audits = [
        _corridor._audit_segment(
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
            for audit in audits
        ),
        default=0.0,
    )
    maximum_normal_deviation = max(
        (
            audit["maximum_board_normal_deviation_m"]
            for audit in audits
        ),
        default=0.0,
    )
    maximum_lateral_deviation = max(
        (
            audit["maximum_lateral_deviation_m"]
            for audit in audits
        ),
        default=0.0,
    )
    post_contact_audits = audits[segment_counts[0] :]
    maximum_backtrack = max(
        (
            audit["maximum_task_axis_backtrack_m"]
            for audit in post_contact_audits
        ),
        default=0.0,
    )
    if (
        maximum_chord_error
        > _corridor.MAXIMUM_CARTESIAN_CHORD_ERROR_M
        or maximum_backtrack
        > _corridor.MAXIMUM_POST_CONTACT_BACKTRACK_M
    ):
        raise TangentSeatStaticError(
            "emitted tangent-seat rows exceeded frozen corridor audit"
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
        "tangent_seat_depth_m": TANGENT_SEAT_DEPTH_M,
        "stroke_m": stroke_m,
        "maximum_cartesian_chord_error_m": maximum_chord_error,
        "maximum_board_normal_deviation_m": maximum_normal_deviation,
        "maximum_lateral_deviation_m": maximum_lateral_deviation,
        "maximum_post_contact_task_axis_backtrack_m": maximum_backtrack,
        "maximum_cartesian_chord_error_gate_m": (
            _corridor.MAXIMUM_CARTESIAN_CHORD_ERROR_M
        ),
        "maximum_post_contact_backtrack_gate_m": (
            _corridor.MAXIMUM_POST_CONTACT_BACKTRACK_M
        ),
        "refined_corridor_segment_count": len(corridor_spans),
        "midpoint_ik_solve_count": len(midpoint_residuals),
        "exact_elbow_range_rad": float(np.ptp(action[:, 2])),
        "ends_at_original_40mm_pushed_target": True,
        "action_rows": len(action),
        "action_raw_float64le_sha256": hashlib.sha256(
            action.tobytes(order="C")
        ).hexdigest(),
    }


def enumerate_and_freeze(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Run the frozen RP03D tangent-seat static universe once."""

    if output_directory.exists():
        raise TangentSeatStaticError(
            "immutable tangent-seat output already exists"
        )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    expected = {
        "schema_version",
        "contract_id",
        "status",
        "proof_class",
        "base_contract",
        "predecessor_closeout",
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
        != "sim2claw.parking_recovery_rp03d_tangent_seat_static.v1"
        or contract.get("status")
        != "frozen_before_one_bounded_static_tangent_seat_run"
        or not all(contract["unchanged"].values())
        or contract["intervention"]
        != {
            "tangent_seat_depth_m": TANGENT_SEAT_DEPTH_M,
            "derivation": (
                "midpoint_of_prospectively_advised_1_to_2mm_range"
            ),
            "only_outcome_relevant_change": (
                "one_task_horizontal_seat_waypoint_after_contact"
            ),
        }
        or any(
            value
            for name, value in contract["authority"].items()
            if name not in {"model_loading", "static_simulation"}
        )
    ):
        raise TangentSeatStaticError("RP03D tangent-seat contract widened")
    base_path = _bound(contract["base_contract"])
    _bound(contract["predecessor_closeout"])
    _bound(contract["implementation"])
    base = copy.deepcopy(
        json.loads(base_path.read_text(encoding="utf-8"))
    )
    base["contract_id"] = "rp03d-tangent-seat-materialized-20260729-v1"
    base["output_directory"] = contract["output_directory"]
    base["claim_boundary"] = contract["claim_boundary"]

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    original_compile = _low._compile_low_direct
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            prefix="rp03d-tangent-seat-",
            dir=contract_path.parent,
            delete=False,
            encoding="utf-8",
        ) as handle:
            json.dump(base, handle, indent=2, sort_keys=True)
            handle.write("\n")
            temporary_path = Path(handle.name)
        _low._compile_low_direct = _compile_tangent_seat
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
            row["compile"]["tangent_seat_depth_m"]
            == TANGENT_SEAT_DEPTH_M
            and row["compile"]["maximum_cartesian_chord_error_m"]
            <= _corridor.MAXIMUM_CARTESIAN_CHORD_ERROR_M
            and row["compile"][
                "maximum_post_contact_task_axis_backtrack_m"
            ]
            <= _corridor.MAXIMUM_POST_CONTACT_BACKTRACK_M
            and row["compile"]["exact_elbow_range_rad"] == 0.0
            for row in receipt["selected"]
        )
    )
    passed = bool(receipt["passed"] and selected_audits_pass)
    receipt.update(
        {
            "schema_version": (
                "sim2claw.parking_recovery_rp03d_"
                "tangent_seat_static_receipt.v1"
            ),
            "status": (
                "parking_recovery_rp03d_tangent_seat_static_pass"
                if passed
                else "parking_recovery_rp03d_tangent_seat_static_reject"
            ),
            "proof_class": contract["proof_class"],
            "contract_path": str(contract_path.relative_to(REPO_ROOT)),
            "contract_sha256": _sha(contract_path),
            "selected_tangent_seat_audits_pass": selected_audits_pass,
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
    "TANGENT_SEAT_DEPTH_M",
    "TangentSeatStaticError",
    "_compile_tangent_seat",
    "enumerate_and_freeze",
]

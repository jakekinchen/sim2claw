"""Postfreeze feasibility audit for the immutable Q05 evaluator."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import mujoco
import numpy as np

from .bidirectional_off_source_evaluator import (
    CONTRACT_PATH as EVALUATOR_PATH,
    load_contract,
)
from .bidirectional_scene_registration_v4 import (
    build_registered_scene,
    load_candidate,
    physical_square_center,
)
from .paths import REPO_ROOT
from .scene import TELEOP_PAWN_SOURCE_SQUARES, TELEOP_TAN_PAWN_SQUARES

EXPECTED_EVALUATOR_SHA256 = (
    "8450682fac61ac064198b90858f58e6753b0d701ed55f067f91d88ed04604479"
)


class OffSourceFeasibilityAuditError(RuntimeError):
    pass


def _sha256() -> str:
    return hashlib.sha256(EVALUATOR_PATH.read_bytes()).hexdigest()


def _point(square: str, square_side_mm: float) -> np.ndarray:
    return np.asarray(
        [
            (ord(square[0]) - ord("a")) * square_side_mm,
            (int(square[1]) - 1) * square_side_mm,
        ],
        dtype=np.float64,
    )


def evaluate() -> dict[str, Any]:
    evaluator_sha256 = _sha256()
    if evaluator_sha256 != EXPECTED_EVALUATOR_SHA256:
        raise OffSourceFeasibilityAuditError("frozen Q05 evaluator changed")
    evaluator = load_contract(EVALUATOR_PATH)
    square_side = float(evaluator["geometry"]["board_square_side_mm"])
    required = float(
        evaluator["task_local_exclusions"]["minimum_route_clearance_mm"]
    )
    occupied = sorted(
        set(TELEOP_PAWN_SOURCE_SQUARES) | set(TELEOP_TAN_PAWN_SQUARES)
    )
    source_bounds = []
    for source in occupied:
        nearest_distance, nearest_square = min(
            (
                float(np.linalg.norm(_point(source, square_side) - _point(other, square_side))),
                other,
            )
            for other in occupied
            if other != source
        )
        source_bounds.append(
            {
                "source_square": source,
                "nearest_other_occupied_square": nearest_square,
                "source_to_nearest_exclusion_mm": nearest_distance,
                "route_clearance_upper_bound_mm": nearest_distance,
            }
        )
    global_upper_bound = max(
        row["route_clearance_upper_bound_mm"] for row in source_bounds
    )
    analytic_upper_bound = math.sqrt(2.0) * square_side
    if not math.isclose(global_upper_bound, analytic_upper_bound, abs_tol=1e-12):
        raise OffSourceFeasibilityAuditError("unexpected sparse-layout bound")

    model, data = build_registered_scene()
    mujoco.mj_forward(model, data)
    base_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, "left_base"
    )
    base_xyz = np.asarray(data.xpos[base_id], dtype=np.float64)
    candidate = load_candidate()
    far_side_base_distances = []
    for case in evaluator["case_family"]:
        if case["case_id"] not in {"S03_B7_B8", "S04_D7_D8", "S05_F7_F8"}:
            continue
        center = physical_square_center(case["source_square"], candidate)
        far_side_base_distances.append(
            {
                "case_id": case["case_id"],
                "source_square": case["source_square"],
                "source_center_xyz_m": center.tolist(),
                "left_base_xyz_m": base_xyz.tolist(),
                "planar_base_distance_m": float(
                    np.linalg.norm((center - base_xyz)[:2])
                ),
                "reachability_authority": False,
            }
        )

    feasible = global_upper_bound >= required
    return {
        "schema_version": "sim2claw.bidirectional_off_source_feasibility_audit.v1",
        "evaluation_id": "bidirectional_off_source_push_q05_feasibility_audit_20260727_v1",
        "status": (
            "feasible"
            if feasible
            else "preregistered_contract_structurally_infeasible"
        ),
        "proof_class": "postfreeze_zero_motion_contract_feasibility_audit",
        "evaluator": {
            "path": str(EVALUATOR_PATH.relative_to(REPO_ROOT)),
            "sha256": evaluator_sha256,
            "id": evaluator["evaluator_id"],
            "mutated": False,
        },
        "geometry": {
            "square_side_mm": square_side,
            "required_route_clearance_mm": required,
            "analytic_source_clearance_upper_bound": "sqrt(2) * square_side_mm",
            "analytic_source_clearance_upper_bound_mm": analytic_upper_bound,
            "global_route_clearance_upper_bound_mm": global_upper_bound,
            "contract_feasible": feasible,
            "proof": (
                "Every route contains its source point. In the frozen sparse "
                "layout, every occupied source has another occupied square "
                "one file and one rank away. Therefore route clearance is at "
                "most sqrt(2) board squares, below the frozen two-square gate."
            ),
            "source_bounds": source_bounds,
        },
        "far_side_planar_base_distance_diagnostic": far_side_base_distances,
        "far_side_reachability_conclusion": (
            "not_adjudicated_by_this_distance_only_audit"
        ),
        "detected_before_q06_possible": True,
        "new_data_opened": False,
        "new_action_compiled": False,
        "robot_motion_commands": 0,
        "counted_physical_attempts": 0,
        "authority": {
            "physical_motion": False,
            "action_compilation": False,
            "training": False,
            "promotion": False,
            "task_success": False,
        },
        "claim_boundary": (
            "The immutable Q05 case family could never satisfy its own "
            "88.9 mm exclusion gate in the frozen reset layout. This is a "
            "preregistered-contract infeasibility, not a physical safety "
            "event, mechanical failure, task attempt, or transfer result."
        ),
    }

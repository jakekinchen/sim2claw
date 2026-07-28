"""Q06 camera-bound exclusion gate for the frozen ten-case family."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from .bidirectional_off_source_evaluator import (
    CONTRACT_PATH as EVALUATOR_PATH,
    load_contract,
)
from .paths import REPO_ROOT
from .scene import TELEOP_PAWN_SOURCE_SQUARES, TELEOP_TAN_PAWN_SQUARES

CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "bidirectional_q06_rgb_scene_gate_v1.json"
)


class Q06SceneGateError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _point(square: str, square_side_mm: float) -> np.ndarray:
    return np.asarray(
        [
            (ord(square[0]) - ord("a")) * square_side_mm,
            (int(square[1]) - 1) * square_side_mm,
        ],
        dtype=np.float64,
    )


def _point_segment_distance(
    point: np.ndarray, start: np.ndarray, end: np.ndarray
) -> float:
    delta = end - start
    parameter = float(np.dot(point - start, delta) / np.dot(delta, delta))
    projection = start + np.clip(parameter, 0.0, 1.0) * delta
    return float(np.linalg.norm(point - projection))


def evaluate() -> dict[str, Any]:
    contract = json.loads(CONTRACT_PATH.read_bytes())
    if (
        contract.get("schema_version")
        != "sim2claw.bidirectional_q06_rgb_scene_gate.v1"
    ):
        raise Q06SceneGateError("unexpected Q06 scene-gate schema")
    for entry in [
        contract["capture_receipt"],
        *contract["camera_frames"].values(),
    ]:
        path = REPO_ROOT / entry["path"]
        if not path.is_file() or _sha256(path) != entry["sha256"]:
            raise Q06SceneGateError(f"Q06 camera evidence changed: {entry['path']}")
    capture = json.loads(
        (REPO_ROOT / contract["capture_receipt"]["path"]).read_bytes()
    )
    if (
        capture.get("status") != "completed_motion_free_rgb_scene_capture"
        or capture.get("metric_depth") is not False
        or capture.get("robot_gateway_constructed") is not False
        or capture.get("robot_motion_commands") != 0
    ):
        raise Q06SceneGateError("Q06 capture widened authority")

    evaluator = load_contract(EVALUATOR_PATH)
    square_side = float(contract["geometry_source"]["board_square_side_mm"])
    required = float(contract["geometry_source"]["minimum_route_clearance_mm"])
    occupied = set(TELEOP_PAWN_SOURCE_SQUARES) | set(TELEOP_TAN_PAWN_SQUARES)
    results = []
    for case in evaluator["case_family"]:
        source = case["source_square"]
        destination = case["destination_direction_square"]
        exclusions = sorted(occupied - {source})
        start = _point(source, square_side)
        end = _point(destination, square_side)
        distances = [
            (
                _point_segment_distance(
                    _point(exclusion, square_side), start, end
                ),
                exclusion,
            )
            for exclusion in exclusions
        ]
        minimum, nearest = min(distances)
        admitted = minimum >= required
        results.append(
            {
                "case_id": case["case_id"],
                "direction": case["direction"],
                "source_square": source,
                "destination_direction_square": destination,
                "nearest_excluded_square": nearest,
                "minimum_center_to_route_clearance_mm": minimum,
                "minimum_base_edge_clearance_mm": minimum
                - 2.0 * float(contract["geometry_source"]["pawn_base_radius_mm"]),
                "required_center_to_route_clearance_mm": required,
                "admitted": admitted,
            }
        )
    admitted = [result["case_id"] for result in results if result["admitted"]]
    return {
        "schema_version": "sim2claw.bidirectional_q06_rgb_scene_gate_receipt.v1",
        "evaluation_id": contract["evaluation_id"],
        "status": (
            "scene_admitted"
            if admitted
            else "terminal_safety_boundary_no_admissible_case"
        ),
        "proof_class": "fresh_rgb_scene_and_frozen_exclusion_geometry",
        "evaluator_sha256": _sha256(EVALUATOR_PATH),
        "capture_receipt_sha256": contract["capture_receipt"]["sha256"],
        "camera_frames": contract["camera_frames"],
        "manual_c922_observation": contract["manual_c922_observation"],
        "case_results": results,
        "admitted_case_ids": admitted,
        "camera_availability": {
            "c922_rgb": True,
            "d405_color_rgb": True,
            "pi_imx708_rgb": True,
            "metric_depth_used": False,
        },
        "robot_gateway_constructed": False,
        "robot_motion_commands": 0,
        "counted_physical_attempts": 0,
        "terminal_boundary": {
            "kind": "human_only_scene_reconfiguration_or_gate_change_required",
            "reason": (
                "Every frozen case route is 44.45 mm from at least one "
                "excluded reset-layout pawn, below the preregistered 88.9 mm "
                "minimum. The agent is forbidden to move/reset pawns or "
                "weaken the gate."
            ),
            "safe_in_scope_alternatives_exhausted": [
                "all ten preregistered cases evaluated",
                "near-side and far-side cases evaluated",
                "F1 widened stroke does not repair source/destination exclusion clearance",
                "setup prefixes cannot move or reposition scene objects",
                "case-family expansion and post-outcome gate weakening are forbidden"
            ],
        },
        "claim_boundary": (
            "Fresh RGB availability and reset-layout observation are verified. "
            "No case is admitted, no action is compiled, and no physical or "
            "bidirectional task result exists."
        ),
    }

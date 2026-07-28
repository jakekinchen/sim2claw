"""Frozen evaluator for the F1 off-source pawn-push primitive."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .paths import REPO_ROOT

CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "bidirectional_off_source_push_evaluator_v1.json"
)


class OffSourceEvaluatorError(RuntimeError):
    pass


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = json.loads(path.read_bytes())
    if (
        contract.get("schema_version")
        != "sim2claw.bidirectional_off_source_push_evaluator.v1"
    ):
        raise OffSourceEvaluatorError("unexpected off-source evaluator schema")
    if contract.get("status") != "frozen_before_counted_action_compilation":
        raise OffSourceEvaluatorError("off-source evaluator is not frozen")
    return contract


def raw_action_sha256(action: np.ndarray) -> str:
    array = np.asarray(action)
    if (
        array.ndim != 2
        or array.shape[1] != 6
        or array.dtype.kind != "f"
        or array.dtype.itemsize != 8
        or not array.flags.c_contiguous
        or not np.all(np.isfinite(array))
    ):
        raise OffSourceEvaluatorError(
            "canonical action must be finite C-contiguous float64 Nx6"
        )
    little_endian = np.asarray(array, dtype="<f8", order="C")
    return hashlib.sha256(little_endian.tobytes(order="C")).hexdigest()


def case_by_id(contract: Mapping[str, Any], case_id: str) -> dict[str, Any]:
    matches = [
        case for case in contract["case_family"] if case["case_id"] == case_id
    ]
    if len(matches) != 1:
        raise OffSourceEvaluatorError(f"unknown or duplicate case: {case_id}")
    return dict(matches[0])


def evaluate_consequence(
    *,
    contract: Mapping[str, Any],
    case_id: str,
    initial_selected_center_xy_mm: list[float],
    final_selected_center_xy_mm: list[float],
    initial_upright_cosine: float,
    selected_contact_count: int,
    excluded_contact_count: int,
    maximum_excluded_displacement: float,
    excluded_displacement_unit: str,
) -> dict[str, Any]:
    case = case_by_id(contract, case_id)
    initial = np.asarray(initial_selected_center_xy_mm, dtype=np.float64)
    final = np.asarray(final_selected_center_xy_mm, dtype=np.float64)
    if initial.shape != (2,) or final.shape != (2,):
        raise OffSourceEvaluatorError("selected-pawn centers must be XY pairs")
    source_file = ord(case["source_square"][0]) - ord("a")
    source_rank = int(case["source_square"][1]) - 1
    destination_file = ord(case["destination_direction_square"][0]) - ord("a")
    destination_rank = int(case["destination_direction_square"][1]) - 1
    direction = np.asarray(
        [destination_file - source_file, destination_rank - source_rank],
        dtype=np.float64,
    )
    norm = float(np.linalg.norm(direction))
    if not np.isclose(norm, 1.0):
        raise OffSourceEvaluatorError("case direction must be one adjacent axis")
    progress_mm = float(np.dot(final - initial, direction / norm))
    geometry = contract["geometry"]
    upright_passed = (
        float(initial_upright_cosine)
        >= geometry["initial_upright_minimum_cosine"]
    )
    progress_passed = (
        progress_mm >= geometry["complete_off_source_signed_progress_mm"]
    )
    selected_contact_passed = int(selected_contact_count) > 0
    exclusions = contract["task_local_exclusions"]
    if excluded_displacement_unit == "px":
        exclusion_limit = exclusions["c922_maximum_centroid_displacement_px"]
    elif excluded_displacement_unit == "mm":
        exclusion_limit = exclusions["simulator_maximum_base_displacement_mm"]
    else:
        raise OffSourceEvaluatorError("excluded displacement unit must be px or mm")
    exclusions_passed = (
        int(excluded_contact_count)
        == exclusions["simulator_excluded_contact_count"]
        and float(maximum_excluded_displacement) <= exclusion_limit
    )
    passed = (
        upright_passed
        and progress_passed
        and selected_contact_passed
        and exclusions_passed
    )
    return {
        "case_id": case_id,
        "direction": case["direction"],
        "signed_progress_mm": progress_mm,
        "required_progress_mm": geometry[
            "complete_off_source_signed_progress_mm"
        ],
        "initial_upright_passed": upright_passed,
        "complete_off_source_passed": progress_passed,
        "selected_contact_passed": selected_contact_passed,
        "exclusions_passed": exclusions_passed,
        "passed": passed,
        "claim": (
            "selected pawn completely displaced off source square"
            if passed
            else "off-source consequence not proven"
        ),
    }


def validate_attempt_ledger(
    contract: Mapping[str, Any], attempts: list[Mapping[str, Any]]
) -> dict[str, Any]:
    seen: set[str] = set()
    per_direction = {
        "REAL_TO_SIM": {"successes": 0, "physical_attempts": 0},
        "SIM_TO_REAL": {"successes": 0, "physical_attempts": 0},
    }
    for attempt in attempts:
        case = case_by_id(contract, str(attempt["case_id"]))
        case_id = case["case_id"]
        if case_id in seen:
            raise OffSourceEvaluatorError("a case has more than one physical attempt")
        seen.add(case_id)
        direction = case["direction"]
        per_direction[direction]["physical_attempts"] += 1
        per_direction[direction]["successes"] += int(bool(attempt["passed"]))
    total = sum(item["physical_attempts"] for item in per_direction.values())
    maximum = contract["case_rules"]["maximum_physical_attempts_total"]
    if total > maximum:
        raise OffSourceEvaluatorError("physical attempt budget exceeded")
    return {
        **per_direction,
        "total_physical_attempts": total,
        "maximum_total_physical_attempts": maximum,
    }

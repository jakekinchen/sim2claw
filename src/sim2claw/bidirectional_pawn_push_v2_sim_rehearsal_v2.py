"""Versioned V05 rehearsal with separate arm-margin and jaw-stop gates."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from . import bidirectional_pawn_push_v2_sim_rehearsal as _v1
from .paths import REPO_ROOT


PushRehearsalError = _v1.PushRehearsalError
_BASE_COMPILE_ACTION = _v1._compile_action
_ARM_JOINT_NAMES = (
    "left_shoulder_pan",
    "left_shoulder_lift",
    "left_elbow_flex",
    "left_wrist_flex",
    "left_wrist_roll",
)
_JAW_JOINT_NAME = "left_gripper"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_implementation_bindings(contract: dict[str, Any]) -> None:
    for key in ("implementation", "base_implementation"):
        binding = contract[key]
        path = REPO_ROOT / str(binding["path"])
        if not path.is_file() or _sha(path) != binding["sha256"]:
            raise PushRehearsalError(
                f"bound rehearsal implementation changed: {path}"
            )


def _jaw_hardware_bounds(
    wrapper: dict[str, Any],
    contract: dict[str, Any],
) -> tuple[float, float]:
    transforms = wrapper["candidate_config"]["physical_adapter"][
        "joint_transform"
    ]["joints"]
    transform = next(
        row for row in transforms if row["simulator_joint"] == _JAW_JOINT_NAME
    )
    if (
        transform["input_unit"] != "percent"
        or transform["output_unit"] != "radian"
        or float(transform["sign"]) != 1.0
    ):
        raise PushRehearsalError("unexpected frozen jaw hardware transform")
    low_percent, high_percent = contract["closed_jaw_gate"][
        "hardware_input_bounds_percent"
    ]
    scale = float(transform["scale"])
    offset = float(transform["zero_offset"])
    return (
        float(low_percent) * scale + offset,
        float(high_percent) * scale + offset,
    )


def _compile_action_v2(**kwargs: Any) -> tuple[np.ndarray, dict[str, Any]]:
    action, metrics = _BASE_COMPILE_ACTION(**kwargs)
    model = kwargs["model"]
    closed_jaw = float(kwargs["closed_jaw_rad"])

    arm_margins = []
    for action_index, name in enumerate(_ARM_JOINT_NAMES):
        joint_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_JOINT, name
        )
        low, high = model.jnt_range[joint_id]
        arm_margins.append(
            float(
                min(
                    np.min(action[:, action_index] - low),
                    np.min(high - action[:, action_index]),
                )
            )
        )

    jaw_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, _JAW_JOINT_NAME
    )
    jaw_low, jaw_high = model.jnt_range[jaw_id]
    jaw_error = float(np.max(np.abs(action[:, -1] - closed_jaw)))
    metrics.update(
        {
            # Kept for the v1 evaluator call below; its meaning is versioned
            # by the v2 receipt and is arm-only.
            "minimum_joint_limit_margin_rad": min(arm_margins),
            "minimum_arm_joint_limit_margin_rad": min(arm_margins),
            "per_arm_joint_limit_margin_rad": {
                name: margin
                for name, margin in zip(
                    _ARM_JOINT_NAMES, arm_margins, strict=True
                )
            },
            "closed_jaw_target_rad": closed_jaw,
            "maximum_closed_jaw_target_error_rad": jaw_error,
            "simulator_jaw_bounds_rad": [
                float(jaw_low),
                float(jaw_high),
            ],
        }
    )
    return action, metrics


def _recompute_receipt(
    receipt: dict[str, Any],
    contract: dict[str, Any],
    wrapper: dict[str, Any],
) -> dict[str, Any]:
    jaw_gate = contract["closed_jaw_gate"]
    target = float(contract["action_synthesis"]["closed_jaw_rad"])
    tolerance = float(jaw_gate["target_tolerance_rad"])
    bounds_tolerance = float(jaw_gate["bounds_roundoff_tolerance_rad"])
    hardware_low, hardware_high = _jaw_hardware_bounds(wrapper, contract)

    for row in receipt["grid_results"]:
        if row["status"] == "compile_reject":
            continue
        compile_metrics = row["compile"]
        simulator_low, simulator_high = compile_metrics[
            "simulator_jaw_bounds_rad"
        ]
        compile_metrics["hardware_mapped_jaw_bounds_rad"] = [
            hardware_low,
            hardware_high,
        ]
        compile_metrics["jaw_bounds_roundoff_tolerance_rad"] = (
            bounds_tolerance
        )
        static_checks = {
            "ik": compile_metrics["maximum_ik_residual_m"]
            <= contract["gates"]["maximum_ik_residual_m"],
            "arm_joint_margin": compile_metrics[
                "minimum_arm_joint_limit_margin_rad"
            ]
            >= contract["gates"]["minimum_arm_joint_limit_margin_rad"],
            "closed_jaw_target": compile_metrics[
                "maximum_closed_jaw_target_error_rad"
            ]
            <= tolerance,
            "closed_jaw_simulator_bounds": (
                simulator_low - bounds_tolerance
                <= target
                <= simulator_high + bounds_tolerance
            ),
            "closed_jaw_hardware_bounds": (
                hardware_low - bounds_tolerance
                <= target
                <= hardware_high + bounds_tolerance
            ),
            "action_identity": row["static_checks"]["action_identity"],
        }
        row["static_checks"] = static_checks
        row["passed"] = all(static_checks.values()) and all(
            replay["passed"] for replay in row["robustness"]
        )
        row["status"] = "pass" if row["passed"] else "sim_reject"

    passing = [row for row in receipt["grid_results"] if row["passed"]]
    per_case: dict[str, dict[str, Any]] = {}
    eligible_by_direction: dict[str, int] = {
        "REAL_TO_SIM": 0,
        "SIM_TO_REAL": 0,
    }
    for case in contract["cases"]:
        rows = [
            row for row in passing if row["case_id"] == case["case_id"]
        ]
        feasible = bool(rows)
        per_case[case["case_id"]] = {
            "feasible": feasible,
            "passing_grid_count": len(rows),
            "recommended": (
                min(
                    rows,
                    key=lambda row: (
                        row["stroke_m"],
                        abs(row["contact_height_m"] - 0.024),
                    ),
                )
                if rows
                else None
            ),
        }
        if feasible and case["eligible_for_v06_recommendation"]:
            eligible_by_direction[case["direction_lane"]] += 1

    minimum = int(
        contract["gates"][
            "minimum_feasible_recommendable_cases_per_direction"
        ]
    )
    direction_checks = {
        direction: count >= minimum
        for direction, count in eligible_by_direction.items()
    }
    receipt.update(
        {
            "schema_version": (
                "sim2claw."
                "bidirectional_pawn_push_v2_sim_rehearsal_receipt.v2"
            ),
            "status": (
                "sim_rehearsal_pass"
                if all(direction_checks.values())
                else "sim_rehearsal_reject"
            ),
            "proof_class": (
                "cpu_fp64_sim_only_straight_closed_jaw_push_"
                "rehearsal_arm_margin_jaw_stop_v2"
            ),
            "per_case": per_case,
            "passing_case_ids": [
                case_id
                for case_id, row in per_case.items()
                if row["feasible"]
            ],
            "direction_gate": {
                "minimum_recommendable_cases_per_direction": minimum,
                "eligible_feasible_case_count": eligible_by_direction,
                "checks": direction_checks,
            },
            "jaw_gate": {
                "target_rad": target,
                "target_tolerance_rad": tolerance,
                "bounds_roundoff_tolerance_rad": bounds_tolerance,
                "hardware_mapped_bounds_rad": [
                    hardware_low,
                    hardware_high,
                ],
            },
            "claim_boundary": (
                "Versioned simulation-only rehearsal correcting only "
                "arm-margin versus declared closed-jaw lower-stop semantics; "
                "no physical task, transfer, promotion, or success claim."
            ),
        }
    )
    return receipt


def evaluate(contract_path: Path, output_path: Path) -> dict[str, Any]:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if (
        contract.get("schema_version")
        != "sim2claw.bidirectional_pawn_push_v2_sim_rehearsal.v2"
    ):
        raise PushRehearsalError("unexpected rehearsal-v2 contract schema")
    _verify_implementation_bindings(contract)
    _, wrapper = _v1._bound(contract["candidate_manifest"])

    previous = _v1._compile_action
    _v1._compile_action = _compile_action_v2
    try:
        receipt = _v1.evaluate(contract_path, output_path)
    finally:
        _v1._compile_action = previous

    receipt = _recompute_receipt(receipt, contract, wrapper)
    output_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = ["PushRehearsalError", "evaluate"]

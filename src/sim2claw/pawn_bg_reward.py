"""Strict manipulation reward and hard gates for the frozen B-G pawn eval."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .paths import REPO_ROOT


CONTRACT_PATH = REPO_ROOT / "configs/evaluations/pawn_bg_sim_reward_v1.json"
SCHEMA_VERSION = "sim2claw.pawn_bg_sim_reward.v1"
EXPECTED_PRODUCT_SHA256 = "8e5a351421dc222688e3ad0cfc7e0c14023352e3ee7132e02c26290d0a7f96f3"
EXPECTED_LANGUAGE_SHA256 = "8e1b1a863b02ce6f8ff2d446bfceda4202d35eb5e6346eb1988cf759b61eed8c"
EXPECTED_SKILLS = tuple(
    (f"pawn_{file_}{source}_to_{file_}{destination}", f"{file_}{source}", f"{file_}{destination}")
    for file_ in "bcdefg"
    for source, destination in (("1", "2"), ("2", "1"))
)
ROOT_KEYS = {
    "schema_version", "reward_id", "frozen_at", "proof_class",
    "product_binding", "language_binding", "contact_sensitivity_binding", "scene_binding", "ordered_skills",
    "hard_gates", "diagnostic_reward", "evaluation_modes", "fixed_evaluation",
    "provenance", "authority", "claim_boundary",
}
TRACE_KEYS = {
    "piece_position_xyz_m", "piece_upright_cosine", "piece_linear_speed_m_s",
    "selected_piece_jaw_contact", "wrong_piece_robot_contact",
    "maximum_other_piece_displacement_m", "finite_state",
}


class PawnBGRewardError(ValueError):
    """Raised when the frozen reward contract or trace has drifted."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _strict_equal(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            _strict_equal(actual[key], expected[key]) for key in expected
        )
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _strict_equal(a, b) for a, b in zip(actual, expected, strict=True)
        )
    return bool(actual == expected)


def _object(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise PawnBGRewardError(f"{label} schema changed")
    return value


def _number(value: Any, label: str, *, minimum: float | None = None) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise PawnBGRewardError(f"{label} must be a finite number, not bool")
    result = float(value)
    if minimum is not None and result < minimum:
        raise PawnBGRewardError(f"{label} is below its allowed minimum")
    return result


def _boolean(value: Any, expected: bool, label: str) -> None:
    if type(value) is not bool or value is not expected:
        raise PawnBGRewardError(f"{label} must be exactly {expected}")


def load_reward_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PawnBGRewardError(f"cannot load reward contract: {path}") from error
    contract = _object(value, ROOT_KEYS, "reward contract")
    if contract["schema_version"] != SCHEMA_VERSION:
        raise PawnBGRewardError("unsupported reward contract schema")

    product = _object(contract["product_binding"], {"path", "sha256", "evaluation_set_id"}, "product binding")
    language = _object(contract["language_binding"], {"path", "sha256", "contract_id"}, "language binding")
    if product != {
        "path": "configs/evaluations/pawn_rank12_bidirectional_v2.json",
        "sha256": EXPECTED_PRODUCT_SHA256,
        "evaluation_set_id": "pawn_rank12_bidirectional_b_to_g_v2",
    }:
        raise PawnBGRewardError("product binding drifted")
    if language != {
        "path": "configs/tasks/pawn_b_g_language_semantics_v1.json",
        "sha256": EXPECTED_LANGUAGE_SHA256,
        "contract_id": "pawn_b_g_language_semantics_v1",
    }:
        raise PawnBGRewardError("language binding drifted")
    for binding, label in ((product, "product"), (language, "language")):
        bound = REPO_ROOT / binding["path"]
        if not bound.is_file() or sha256_file(bound) != binding["sha256"]:
            raise PawnBGRewardError(f"{label} contract bytes do not match the frozen digest")

    contact = _object(contract["contact_sensitivity_binding"], {"path", "canonical_sha256", "analysis_id", "parameter_use_mode", "ordered_variants"}, "contact sensitivity binding")
    if not _strict_equal(contact, {
        "path": "configs/simulation/rubber_tip_contact_sensitivity_v1.json",
        "canonical_sha256": "e89eb1084e7e1dee64aaebfbc18b816b5bf58aefa98b18d38ef2e9a81b6ee499",
        "analysis_id": "rubber_tip_contact_sensitivity_v1",
        "parameter_use_mode": "reuse_same_unmeasured_prior_ensemble_for_b_g_diagnostic_not_source_task_evaluator",
        "ordered_variants": ["nominal_uncalibrated", "rubber_tip_low", "rubber_tip_nominal_prior", "rubber_tip_high"],
    }):
        raise PawnBGRewardError("contact sensitivity binding drifted")
    from .contact_prior import read_contact_prior_snapshot
    snapshot = read_contact_prior_snapshot(REPO_ROOT / contact["path"])
    if snapshot.sha256 != contact["canonical_sha256"]:
        raise PawnBGRewardError("contact prior canonical digest drifted")

    scene = _object(contract["scene_binding"], {
        "scene_id", "workspace_pose_id", "board_pose_id", "piece_layout",
        "piece_family", "piece_color", "task_arm", "square_side_m", "pawn_base_radius_m",
    }, "scene binding")
    expected_scene_strings = {
        "scene_id": "operator_updated_chess_workcell_v3",
        "workspace_pose_id": "workspace_board_fiducial_robotward_100mm_20260718_v3",
        "board_pose_id": "board_robotward_100mm_20260718_v3",
        "piece_layout": "sparse_two_sided_pawns", "piece_family": "pawn",
        "piece_color": "brown", "task_arm": "left",
    }
    if any(type(scene.get(key)) is not str or scene[key] != expected for key, expected in expected_scene_strings.items()):
        raise PawnBGRewardError("scene identity drifted")
    if _number(scene["square_side_m"], "square side", minimum=0.0) != 0.04445 or _number(scene["pawn_base_radius_m"], "pawn radius", minimum=0.0) != 0.0138:
        raise PawnBGRewardError("scene dimensions drifted")

    skills = contract["ordered_skills"]
    if type(skills) is not list or len(skills) != 12:
        raise PawnBGRewardError("reward contract requires exactly 12 ordered skills")
    actual_skills = []
    for index, skill in enumerate(skills):
        row = _object(skill, {"skill_id", "source_square", "destination_square"}, f"skill {index}")
        if any(type(row[key]) is not str for key in row):
            raise PawnBGRewardError("skill values must be strings")
        actual_skills.append((row["skill_id"], row["source_square"], row["destination_square"]))
    if tuple(actual_skills) != EXPECTED_SKILLS or len(set(actual_skills)) != 12:
        raise PawnBGRewardError("skill order, identity, or uniqueness drifted")

    gates = _object(contract["hard_gates"], {
        "minimum_piece_rise_m", "maximum_final_center_distance_for_whole_base_inside_m",
        "maximum_final_center_distance_composable_m", "maximum_final_center_distance_precision_m",
        "minimum_final_upright_cosine", "maximum_final_linear_speed_m_s",
        "maximum_other_piece_displacement_m", "require_selected_piece_jaw_contact",
        "require_release_before_terminal", "forbid_wrong_piece_robot_contact", "require_finite_state",
    }, "hard gates")
    expected_numbers = {
        "minimum_piece_rise_m": 0.04,
        "maximum_final_center_distance_for_whole_base_inside_m": 0.008425,
        "maximum_final_center_distance_composable_m": 0.006,
        "maximum_final_center_distance_precision_m": 0.003,
        "minimum_final_upright_cosine": 0.95,
        "maximum_final_linear_speed_m_s": 0.02,
        "maximum_other_piece_displacement_m": 0.006,
    }
    for key, expected in expected_numbers.items():
        if _number(gates[key], f"hard gate {key}", minimum=0.0) != expected:
            raise PawnBGRewardError(f"hard gate {key} drifted")
    for key in ("require_selected_piece_jaw_contact", "require_release_before_terminal", "forbid_wrong_piece_robot_contact", "require_finite_state"):
        _boolean(gates[key], True, f"hard gate {key}")

    reward = _object(contract["diagnostic_reward"], {"promotion_authority", "range", "weights", "penalties"}, "diagnostic reward")
    _boolean(reward["promotion_authority"], False, "diagnostic reward promotion authority")
    if not _strict_equal(reward["range"], [-1.0, 1.0]):
        raise PawnBGRewardError("reward range drifted")
    weights = _object(reward["weights"], {"destination_progress", "lift_progress", "destination_centering", "upright", "settled", "released"}, "reward weights")
    if not math.isclose(sum(_number(v, f"reward weight {k}", minimum=0.0) for k, v in weights.items()), 1.0, abs_tol=1e-12):
        raise PawnBGRewardError("positive reward weights must sum to one")
    penalties = _object(reward["penalties"], {"no_selected_piece_contact", "wrong_piece_contact", "collateral_displacement", "nonfinite_state"}, "reward penalties")
    for key, value_ in penalties.items():
        _number(value_, f"reward penalty {key}", minimum=0.0)

    modes = _object(contract["evaluation_modes"], {"learned_policy", "source_demonstration_replay"}, "evaluation modes")
    expected_modes = {
        "learned_policy": {"require_model_owned_actions": True, "require_zero_assistance": True, "can_report_policy_success": True},
        "source_demonstration_replay": {"require_model_owned_actions": False, "require_zero_assistance": True, "can_report_policy_success": False},
    }
    if not _strict_equal(modes, expected_modes):
        raise PawnBGRewardError("evaluation modes drifted")
    fixed = _object(contract["fixed_evaluation"], {"seeds", "skill_order_is_frozen", "thresholds_are_frozen", "no_held_out_search", "no_action_clipping_for_admissible_policy_evaluation"}, "fixed evaluation")
    if not _strict_equal(fixed, {"seeds": [190719], "skill_order_is_frozen": True, "thresholds_are_frozen": True, "no_held_out_search": True, "no_action_clipping_for_admissible_policy_evaluation": True}):
        raise PawnBGRewardError("fixed evaluation settings drifted")
    provenance = _object(contract["provenance"], {"method", "measured_physical_trajectory_used_to_set_reward_weights", "held_out_data_used", "network_used", "physical_calibration_claimed"}, "provenance")
    if provenance["method"] != "clean_room_engineering_reward_derived_from_frozen_product_thresholds":
        raise PawnBGRewardError("reward provenance method drifted")
    for key in ("measured_physical_trajectory_used_to_set_reward_weights", "held_out_data_used", "network_used", "physical_calibration_claimed"):
        _boolean(provenance[key], False, f"provenance {key}")
    authority = _object(contract["authority"], {"hard_gates_own_pass_fail", "diagnostic_reward_can_promote", "source_demonstration_replay_can_promote", "training_can_promote", "physical_authority", "sim_to_real_error_measured"}, "authority")
    if not _strict_equal(authority, {"hard_gates_own_pass_fail": True, "diagnostic_reward_can_promote": False, "source_demonstration_replay_can_promote": False, "training_can_promote": False, "physical_authority": False, "sim_to_real_error_measured": False}):
        raise PawnBGRewardError("authority boundary drifted")
    if type(contract["claim_boundary"]) is not str or not contract["claim_boundary"]:
        raise PawnBGRewardError("claim boundary is required")
    return contract


def _trace_row(row: Any, index: int) -> dict[str, Any]:
    value = _object(row, TRACE_KEYS, f"trace row {index}")
    xyz = value["piece_position_xyz_m"]
    if type(xyz) is not list or len(xyz) != 3:
        raise PawnBGRewardError(f"trace row {index} position must be XYZ")
    for axis, coordinate in enumerate(xyz):
        _number(coordinate, f"trace row {index} position {axis}")
    for key in ("piece_upright_cosine", "piece_linear_speed_m_s", "maximum_other_piece_displacement_m"):
        _number(value[key], f"trace row {index} {key}", minimum=0.0 if key != "piece_upright_cosine" else None)
    for key in ("selected_piece_jaw_contact", "wrong_piece_robot_contact", "finite_state"):
        if type(value[key]) is not bool:
            raise PawnBGRewardError(f"trace row {index} {key} must be boolean")
    return value


def score_episode(
    contract: dict[str, Any], *, skill_id: str, trace: Iterable[dict[str, Any]],
    target_position_xyz_m: Iterable[float], initial_piece_height_m: float,
    evaluation_mode: str, action_owner: str, assistance_used: bool,
) -> dict[str, Any]:
    skills = {row["skill_id"]: row for row in contract["ordered_skills"]}
    if skill_id not in skills:
        raise PawnBGRewardError(f"unknown frozen skill: {skill_id}")
    if evaluation_mode not in contract["evaluation_modes"]:
        raise PawnBGRewardError(f"unknown evaluation mode: {evaluation_mode}")
    if type(action_owner) is not str or not action_owner:
        raise PawnBGRewardError("action_owner must be a non-empty string")
    if type(assistance_used) is not bool:
        raise PawnBGRewardError("assistance_used must be boolean")
    target = np.asarray(list(target_position_xyz_m), dtype=np.float64)
    if target.shape != (3,) or not np.isfinite(target).all():
        raise PawnBGRewardError("target position must be finite XYZ")
    initial_height = _number(initial_piece_height_m, "initial piece height")
    rows = [_trace_row(row, index) for index, row in enumerate(trace)]
    if not rows:
        raise PawnBGRewardError("episode trace cannot be empty")

    gates = contract["hard_gates"]
    weights = contract["diagnostic_reward"]["weights"]
    penalties = contract["diagnostic_reward"]["penalties"]
    source_distance = float(contract["scene_binding"]["square_side_m"])
    max_rise = max(float(row["piece_position_xyz_m"][2]) - initial_height for row in rows)
    final = rows[-1]
    final_xyz = np.asarray(final["piece_position_xyz_m"], dtype=np.float64)
    final_distance = float(np.linalg.norm(final_xyz[:2] - target[:2]))
    contact_ever = any(row["selected_piece_jaw_contact"] for row in rows)
    wrong_contact = any(row["wrong_piece_robot_contact"] for row in rows)
    max_collateral = max(float(row["maximum_other_piece_displacement_m"]) for row in rows)
    finite = all(row["finite_state"] for row in rows) and bool(np.isfinite(final_xyz).all())
    final_contact = bool(final["selected_piece_jaw_contact"])

    gate_results = {
        "piece_lifted": max_rise >= gates["minimum_piece_rise_m"],
        "whole_base_inside_destination": final_distance <= gates["maximum_final_center_distance_for_whole_base_inside_m"],
        "composable_center": final_distance <= gates["maximum_final_center_distance_composable_m"],
        "precision_center": final_distance <= gates["maximum_final_center_distance_precision_m"],
        "upright": float(final["piece_upright_cosine"]) >= gates["minimum_final_upright_cosine"],
        "settled": float(final["piece_linear_speed_m_s"]) <= gates["maximum_final_linear_speed_m_s"],
        "selected_piece_contact_observed": contact_ever,
        "released": not final_contact,
        "no_wrong_piece_contact": not wrong_contact,
        "collateral_within_limit": max_collateral <= gates["maximum_other_piece_displacement_m"],
        "finite_state": finite,
    }
    task_required = (
        "piece_lifted", "whole_base_inside_destination", "composable_center",
        "upright", "settled", "selected_piece_contact_observed", "released",
        "no_wrong_piece_contact", "collateral_within_limit", "finite_state",
    )
    task_success = all(gate_results[key] for key in task_required)
    mode = contract["evaluation_modes"][evaluation_mode]
    ownership_pass = not mode["require_model_owned_actions"] or action_owner == "model"
    assistance_pass = not mode["require_zero_assistance"] or not assistance_used
    policy_success = bool(mode["can_report_policy_success"] and task_success and ownership_pass and assistance_pass)

    positive = (
        weights["destination_progress"] * float(np.clip(1.0 - final_distance / source_distance, 0.0, 1.0))
        + weights["lift_progress"] * float(np.clip(max_rise / gates["minimum_piece_rise_m"], 0.0, 1.0))
        + weights["destination_centering"] * float(np.clip(1.0 - final_distance / gates["maximum_final_center_distance_composable_m"], 0.0, 1.0))
        + weights["upright"] * float(np.clip(final["piece_upright_cosine"], 0.0, 1.0))
        + weights["settled"] * float(final["piece_linear_speed_m_s"] <= gates["maximum_final_linear_speed_m_s"])
        + weights["released"] * float(not final_contact)
    )
    penalty = (
        penalties["no_selected_piece_contact"] * float(not contact_ever)
        + penalties["wrong_piece_contact"] * float(wrong_contact)
        + penalties["collateral_displacement"] * float(max_collateral > gates["maximum_other_piece_displacement_m"])
        + penalties["nonfinite_state"] * float(not finite)
    )
    reward = float(np.clip(positive - penalty, -1.0, 1.0))
    return {
        "schema_version": "sim2claw.pawn_bg_sim_episode_score.v1",
        "reward_id": contract["reward_id"],
        "skill_id": skill_id,
        "source_square": skills[skill_id]["source_square"],
        "destination_square": skills[skill_id]["destination_square"],
        "evaluation_mode": evaluation_mode,
        "diagnostic_reward": reward,
        "diagnostic_reward_has_promotion_authority": False,
        "maximum_piece_rise_m": max_rise,
        "final_center_distance_m": final_distance,
        "final_piece_upright_cosine": float(final["piece_upright_cosine"]),
        "final_piece_linear_speed_m_s": float(final["piece_linear_speed_m_s"]),
        "maximum_other_piece_displacement_m": max_collateral,
        "gate_results": gate_results,
        "task_consequence_success": task_success,
        "action_owner": action_owner,
        "model_owned_action_gate": ownership_pass,
        "assistance_used": assistance_used,
        "zero_assistance_gate": assistance_pass,
        "policy_success": policy_success,
        "policy_success_reportable": bool(mode["can_report_policy_success"]),
    }


def aggregate_scores(contract: dict[str, Any], scores: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(scores)
    expected = [row["skill_id"] for row in contract["ordered_skills"]]
    if [row.get("skill_id") for row in rows] != expected:
        raise PawnBGRewardError("aggregate requires one result in frozen 12-skill order")
    directions = {
        "rank1_to_rank2": [row for row in rows if row["source_square"].endswith("1")],
        "rank2_to_rank1": [row for row in rows if row["source_square"].endswith("2")],
    }
    rate = lambda subset, key: sum(bool(row[key]) for row in subset) / len(subset)
    forward = rate(directions["rank1_to_rank2"], "task_consequence_success")
    reverse = rate(directions["rank2_to_rank1"], "task_consequence_success")
    return {
        "schema_version": "sim2claw.pawn_bg_sim_aggregate.v1",
        "reward_id": contract["reward_id"],
        "episode_count": 12,
        "macro_task_consequence_success_rate": rate(rows, "task_consequence_success"),
        "macro_policy_success_rate": rate(rows, "policy_success"),
        "mean_diagnostic_reward": float(np.mean([row["diagnostic_reward"] for row in rows])),
        "rank1_to_rank2_task_success_rate": forward,
        "rank2_to_rank1_task_success_rate": reverse,
        "direction_parity_gap": abs(forward - reverse),
        "per_column_forward_reverse": {
            file_: {
                "forward": bool(rows[index * 2]["task_consequence_success"]),
                "reverse": bool(rows[index * 2 + 1]["task_consequence_success"]),
            }
            for index, file_ in enumerate("bcdefg")
        },
        "failed_skills": [row["skill_id"] for row in rows if not row["task_consequence_success"]],
        "policy_result_available": any(row["policy_success_reportable"] for row in rows),
    }


__all__ = ["CONTRACT_PATH", "PawnBGRewardError", "aggregate_scores", "load_reward_contract", "score_episode", "sha256_file"]

"""Frozen contract helpers for goal-conditioned ACT pick-and-place."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .paths import REPO_ROOT
from .scene import ROBOT_JOINTS, board_square_center


TASK_CONTRACT_PATH = REPO_ROOT / "configs" / "tasks" / "chess_pick_place_act_state_v1.json"
ALLOWED_FRAMES = {
    "so101_joint",
    "world",
    "gripper",
    "selected_piece",
    "continuous_target",
    "state_machine",
    "contact_sensor",
}
REQUIRED_LINEAGE_FIELDS = {
    "source_episode_id",
    "source_segment_ids",
    "source_proof_class",
    "object_relative_transform_sha256",
    "target_relative_transform_sha256",
    "planner_id",
    "ik_solver_id",
    "scene_id",
    "initial_state_sha256",
    "candidate_seed",
    "repair_parent_id",
    "evaluator_contract_sha256",
}


def task_contract_sha256(path: Path = TASK_CONTRACT_PATH) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ranges_overlap(left: Iterable[float], right: Iterable[float]) -> bool:
    left_min, left_max = (float(value) for value in left)
    right_min, right_max = (float(value) for value in right)
    return max(left_min, right_min) <= min(left_max, right_max)


def _validate_pose_cells(contract: dict[str, Any]) -> None:
    splits = contract["splits"]
    if set(splits["training_seeds"]) & set(splits["held_out_seeds"]):
        raise ValueError("training and held-out seeds overlap")
    if int(splits["held_out_training_rows"]) != 0:
        raise ValueError("held-out split must contain zero training rows")
    for family in ("source_pose_cells", "target_pose_cells"):
        values = splits[family]
        training_ids = {row["id"] for row in values["training"]}
        held_out_ids = {row["id"] for row in values["held_out"]}
        if training_ids & held_out_ids:
            raise ValueError(f"{family} ids overlap")
    training_pairs = set(splits["object_destination_pairs"]["training"])
    held_out_pairs = set(splits["object_destination_pairs"]["held_out"])
    if training_pairs & held_out_pairs:
        raise ValueError("object/destination pair holdouts overlap training")
    training_layouts = set(splits["distractor_layouts"]["training"])
    held_out_layouts = set(splits["distractor_layouts"]["held_out"])
    if training_layouts & held_out_layouts:
        raise ValueError("distractor layout holdouts overlap training")


def validate_task_contract(contract: dict[str, Any]) -> dict[str, Any]:
    if contract.get("schema_version") != "sim2claw.chess_pick_place_act_state_task.v1":
        raise ValueError("unsupported goal-conditioned ACT contract schema")
    if contract.get("task_id") != "chess_pick_place_act_state_v1":
        raise ValueError("unexpected task identity")
    if not contract.get("frozen_before_training"):
        raise ValueError("task contract must be frozen before training")

    observation = contract["observation"]
    features = observation["features"]
    names = [str(feature["name"]) for feature in features]
    if len(names) != len(set(names)):
        raise ValueError("observation feature names must be unique")
    dimension = sum(int(feature["dimension"]) for feature in features)
    if dimension != int(observation["dimension"]):
        raise ValueError("observation dimension does not match feature dimensions")
    if any(feature["frame"] not in ALLOWED_FRAMES for feature in features):
        raise ValueError("observation uses an undeclared coordinate frame")
    prohibited = set(observation["prohibited_features"])
    if prohibited & set(names):
        raise ValueError("prohibited leakage feature is present")
    if not observation.get("feature_order_is_frozen"):
        raise ValueError("observation feature order is not frozen")

    action = contract["action"]
    if action["representation"] != "absolute_joint_position_target":
        raise ValueError("ACT actions must be absolute joint-position targets")
    if int(action["dimension"]) != len(ROBOT_JOINTS) or len(action["bounds"]) != len(ROBOT_JOINTS):
        raise ValueError("ACT action dimension must match the six SO-101 joints")
    for lower, upper in action["bounds"]:
        if not math.isfinite(float(lower)) or not math.isfinite(float(upper)) or lower >= upper:
            raise ValueError("invalid ACT action bound")

    skills = contract["execution"]["skills"]
    if skills != ["pregrasp", "grasp_lift", "transport", "place_release", "retreat"]:
        raise ValueError("unexpected skill ordering")
    feature_names = set(names)
    for transition in contract["execution"]["transitions"]:
        if not set(transition["observable_inputs"]).issubset(feature_names):
            raise ValueError("transition depends on an unavailable observation")

    lineage = set(contract["generator"]["required_lineage_fields"])
    if lineage != REQUIRED_LINEAGE_FIELDS:
        raise ValueError("candidate lineage fields are incomplete or changed")
    if contract["generator"]["admission"] != "strict_evaluator_success_only":
        raise ValueError("generated candidate admission must fail closed")
    _validate_pose_cells(contract)

    evaluator = contract["evaluator"]
    if evaluator["owner"] != "separate_cpu_fp32_consequence_evaluator":
        raise ValueError("evaluator ownership changed")
    if evaluator["device"] != "cpu" or evaluator["dtype"] != "float32":
        raise ValueError("selection evaluator must remain CPU/fp32")
    for requirement in (
        "require_no_final_jaw_contact",
        "require_model_owned_actions",
        "require_no_assistance",
        "training_cannot_promote",
    ):
        if not evaluator[requirement]:
            raise ValueError(f"evaluator requirement disabled: {requirement}")
    runtime_scope = contract.get("runtime_scope")
    if not isinstance(runtime_scope, dict):
        raise ValueError("goal-conditioned ACT runtime scope is missing")
    expected_skills = {
        f"pawn_{file_name}{source}_to_{file_name}{destination}"
        for file_name in "bcdefg"
        for source, destination in ((1, 2), (2, 1))
    }
    if set(runtime_scope.get("eligible_skill_ids", [])) != expected_skills:
        raise ValueError("goal-conditioned ACT runtime scope is not the frozen B-G set")
    if int(runtime_scope.get("minimum_held_out_cases_per_skill", 0)) < 1:
        raise ValueError("every runtime skill requires a held-out evaluation case")
    if runtime_scope.get("all_skills_must_pass_before_registry_publication") is not True:
        raise ValueError("partial runtime-skill publication is forbidden")
    if any(contract["authority"][key] for key in ("physical_authority", "camera_hardware_access", "serial_access", "gateway_access")):
        raise ValueError("M6 contract cannot grant hardware authority")
    return contract


def load_act_pick_place_task_contract(path: Path = TASK_CONTRACT_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("task contract must be a JSON object")
    return validate_task_contract(payload)


def resolve_structured_goal(piece_id: str, target_square: str) -> dict[str, Any]:
    if not piece_id or target_square.lower() not in {
        f"{file_name}{rank}" for file_name in "abcdefgh" for rank in "12345678"
    }:
        raise ValueError("piece and target square are required")
    target_position = board_square_center(target_square.lower())
    return {
        "piece_id": piece_id,
        "target_pose": [*target_position, 1.0, 0.0, 0.0, 0.0],
        "target_pose_frame": "world",
        "target_square_is_planner_metadata_only": target_square.lower(),
    }


def encode_observation(
    contract: dict[str, Any],
    feature_values: dict[str, Iterable[float]],
) -> np.ndarray:
    validate_task_contract(contract)
    prohibited = set(contract["observation"]["prohibited_features"])
    if prohibited & set(feature_values):
        raise ValueError("observation contains a prohibited leakage feature")
    encoded: list[float] = []
    expected_names = {feature["name"] for feature in contract["observation"]["features"]}
    unknown = set(feature_values) - expected_names
    if unknown:
        raise ValueError(f"unknown observation features: {sorted(unknown)}")
    for feature in contract["observation"]["features"]:
        name = feature["name"]
        if name not in feature_values:
            raise ValueError(f"missing observable feature: {name}")
        values = [float(value) for value in feature_values[name]]
        if len(values) != int(feature["dimension"]):
            raise ValueError(f"wrong dimension for {name}")
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"non-finite observation for {name}")
        encoded.extend(values)
    return np.asarray(encoded, dtype=np.float32)


def validate_candidate_lineage(contract: dict[str, Any], lineage: dict[str, Any]) -> None:
    validate_task_contract(contract)
    missing = REQUIRED_LINEAGE_FIELDS - set(lineage)
    if missing:
        raise ValueError(f"candidate lineage missing fields: {sorted(missing)}")


def validate_candidate_outcome(
    contract: dict[str, Any],
    outcome: dict[str, Any],
) -> None:
    validate_task_contract(contract)
    rejection = outcome.get("rejection_reason")
    if rejection:
        if rejection not in contract["negative_fixture_rejections"]:
            raise ValueError("candidate used an undeclared rejection reason")
        raise ValueError(f"candidate rejected: {rejection}")
    if not outcome.get("strict_success"):
        raise ValueError("candidate did not pass the strict evaluator")
    if outcome.get("assistance"):
        raise ValueError("assisted candidate cannot enter training")
    if outcome.get("action_owner") != "model_or_declared_source_expert":
        raise ValueError("candidate action ownership is invalid")

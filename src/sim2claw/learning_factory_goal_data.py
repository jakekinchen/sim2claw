"""Goal-conditioned curriculum and immutable source-to-policy dataset assembly.

This module is deliberately split at the evaluator boundary.  LF-08 may plan
bounded candidates, but only LF-09 invokes a source evaluator and converts its
strict admissions into training rows.  Candidate plans and caller booleans
never authorize data.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .act_pick_place import (
    REQUIRED_LINEAGE_FIELDS,
    encode_observation,
    load_act_pick_place_task_contract,
    task_contract_sha256,
    validate_candidate_lineage,
)
from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .pawn_source_evaluator import evaluate_source_episode
from .scene import board_square_center
from .source_episode import adapt_source_episode, load_source_episode, tree_manifest


CURRICULUM_SCHEMA = "sim2claw.goal_act_curriculum.v1"
DATASET_SCHEMA = "sim2claw.goal_act_dataset.v1"
ROW_SCHEMA = "sim2claw.goal_act_dataset_row.v1"
REJECTION_SCHEMA = "sim2claw.goal_act_candidate_rejection.v1"
EXECUTION_BATCH_SCHEMA = "sim2claw.goal_act_candidate_execution_batch.v1"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(_canonical_bytes(row).decode("utf-8") + "\n" for row in materialized),
        encoding="utf-8",
    )
    return {"path": path.name, "sha256": sha256_file(path), "row_count": len(materialized)}


def _sample_range(bounds: Iterable[float], fraction: float) -> float:
    lower, upper = (float(item) for item in bounds)
    if not math.isfinite(lower) or not math.isfinite(upper) or lower > upper:
        raise ValueError("curriculum cell has invalid bounds")
    return lower + fraction * (upper - lower)


def _fraction(seed: int, label: str) -> float:
    digest = hashlib.sha256(f"{seed}:{label}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64 - 1)


def _split_manifest(task: dict[str, Any]) -> dict[str, Any]:
    splits = task["splits"]
    training = {
        "seeds": splits["training_seeds"],
        "source_pose_cells": splits["source_pose_cells"]["training"],
        "target_pose_cells": splits["target_pose_cells"]["training"],
        "object_destination_pairs": splits["object_destination_pairs"]["training"],
        "distractor_layouts": splits["distractor_layouts"]["training"],
    }
    held_out = {
        "seeds": splits["held_out_seeds"],
        "source_pose_cells": splits["source_pose_cells"]["held_out"],
        "target_pose_cells": splits["target_pose_cells"]["held_out"],
        "object_destination_pairs": splits["object_destination_pairs"]["held_out"],
        "distractor_layouts": splits["distractor_layouts"]["held_out"],
    }
    return {
        "training_sha256": canonical_digest(training),
        "held_out_sha256": canonical_digest(held_out),
        "held_out_training_rows": 0,
        "held_out_opened_for_curriculum_selection": False,
    }


def compile_goal_act_curriculum(
    *,
    parent_twin_id: str,
    source_episodes: list[dict[str, Any]],
    maximum_candidates: int,
    generation: int = 0,
    task_contract_path: Path | None = None,
) -> dict[str, Any]:
    """Select the smallest deterministic training-only pose/layout batch.

    The output is a plan, not an admission.  Fields that can only be known
    after scene reset are explicitly marked pending and must be replaced by
    LF-09 before candidate lineage can validate.
    """

    if maximum_candidates <= 0:
        raise ValueError("curriculum must contain at least one bounded candidate")
    if not parent_twin_id:
        raise ValueError("curriculum requires a parent twin identity")
    task = load_act_pick_place_task_contract(
        task_contract_path
        if task_contract_path is not None
        else Path(__file__).parents[2]
        / "configs/tasks/chess_pick_place_act_state_v1.json"
    )
    if not source_episodes:
        raise ValueError("curriculum requires at least one admitted source declaration")
    normalized_sources: list[dict[str, Any]] = []
    for source in source_episodes:
        source_id = str(source.get("source_episode_id") or "")
        proof_class = str(source.get("source_proof_class") or "")
        segments = list(source.get("source_segment_ids") or [])
        if not source_id or not proof_class or not segments:
            raise ValueError("source declarations require identity, proof class, and segments")
        normalized_sources.append(
            {
                "source_episode_id": source_id,
                "source_proof_class": proof_class,
                "source_segment_ids": segments,
            }
        )

    splits = task["splits"]
    source_cells = splits["source_pose_cells"]["training"]
    target_cells = {
        str(cell["id"]): cell for cell in splits["target_pose_cells"]["training"]
    }
    pairs = list(splits["object_destination_pairs"]["training"])
    seeds = [int(seed) for seed in splits["training_seeds"]]
    layouts = list(splits["distractor_layouts"]["training"])
    count = min(maximum_candidates, len(pairs) * len(seeds))
    candidates: list[dict[str, Any]] = []
    for index in range(count):
        pair = str(pairs[index % len(pairs)])
        piece_id, target_cell_id = pair.split(":", 1)
        target_cell = target_cells[target_cell_id]
        source_cell = source_cells[index % len(source_cells)]
        seed = seeds[index % len(seeds)]
        source = normalized_sources[index % len(normalized_sources)]
        source_offset = [
            _sample_range(source_cell["x_offset_m"], _fraction(seed, "source-x")),
            _sample_range(source_cell["y_offset_m"], _fraction(seed, "source-y")),
        ]
        source_yaw = _sample_range(source_cell["yaw_rad"], _fraction(seed, "source-yaw"))
        target_xy = [
            _sample_range(target_cell["x_m"], _fraction(seed, "target-x")),
            _sample_range(target_cell["y_m"], _fraction(seed, "target-y")),
        ]
        identity = {
            "task_id": task["task_id"],
            "parent_twin_id": parent_twin_id,
            "generation": int(generation),
            "piece_id": piece_id,
            "target_cell_id": target_cell_id,
            "source_cell_id": source_cell["id"],
            "candidate_seed": seed,
            "distractor_layout": layouts[index % len(layouts)],
            "source_offset_xy_m": source_offset,
            "source_yaw_rad": source_yaw,
            "continuous_target_xy_m": target_xy,
        }
        candidate_id = f"goal-cousin-{canonical_digest(identity)[:20]}"
        candidates.append(
            {
                "candidate_id": candidate_id,
                "role": "train",
                **identity,
                "source": source,
                "planner_id": "repo_native_free_space_planner_v1",
                "ik_solver_id": "mujoco_damped_least_squares_v1",
                "lineage_state": "planned_pending_scene_execution",
                "execution_bound_lineage_fields": [
                    "object_relative_transform_sha256",
                    "target_relative_transform_sha256",
                    "initial_state_sha256",
                    "evaluator_contract_sha256",
                ],
            }
        )

    split_manifest = _split_manifest(task)
    unsigned = {
        "schema_version": CURRICULUM_SCHEMA,
        "task_id": task["task_id"],
        "task_contract_sha256": task_contract_sha256(
            task_contract_path
            if task_contract_path is not None
            else Path(__file__).parents[2]
            / "configs/tasks/chess_pick_place_act_state_v1.json"
        ),
        "parent_twin_id": parent_twin_id,
        "generation": int(generation),
        "candidate_count": len(candidates),
        "maximum_candidates": int(maximum_candidates),
        "coverage": {
            "pieces": sorted({row["piece_id"] for row in candidates}),
            "source_cells": sorted({row["source_cell_id"] for row in candidates}),
            "target_cells": sorted({row["target_cell_id"] for row in candidates}),
            "distractor_layouts": sorted({row["distractor_layout"] for row in candidates}),
            "seeds": sorted({row["candidate_seed"] for row in candidates}),
        },
        "split_manifest": split_manifest,
        "candidates": candidates,
        "admission_authority": "none_plan_only",
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def generate_goal_act_candidate_executions(
    curriculum: dict[str, Any],
    *,
    output_directory: Path,
    task_contract_path: Path | None = None,
    maximum_executions: int = 1,
    object_dimensions_m: Iterable[float],
    gripper_aperture_mapping: dict[str, Any],
) -> dict[str, Any]:
    """Execute bounded curriculum candidates with the repo-native source expert.

    This generator owns actions and scene creation only. The returned episodes
    remain pending until ``build_goal_act_dataset`` reruns the independent
    strict evaluator. Unsupported planned poses fail closed instead of being
    relabelled to match the expert.
    """

    from .pawn_source_expert import (
        DESTINATION_SQUARE,
        SOURCE_PIECE_ID,
        collect_pawn_source_expert_candidate,
    )

    if curriculum.get("schema_version") != CURRICULUM_SCHEMA:
        raise ValueError("unsupported goal ACT curriculum")
    unsigned_curriculum = {
        key: value for key, value in curriculum.items() if key != "artifact_sha256"
    }
    if curriculum.get("artifact_sha256") != canonical_digest(unsigned_curriculum):
        raise ValueError("curriculum digest does not match its content")
    task_path = (
        task_contract_path
        if task_contract_path is not None
        else Path(__file__).parents[2]
        / "configs/tasks/chess_pick_place_act_state_v1.json"
    )
    if curriculum.get("task_contract_sha256") != task_contract_sha256(task_path):
        raise ValueError("curriculum uses another task contract")
    dimensions = [float(value) for value in object_dimensions_m]
    if len(dimensions) != 3 or not all(value > 0 and math.isfinite(value) for value in dimensions):
        raise ValueError("candidate generator requires three positive object dimensions")
    if gripper_aperture_mapping.get("mapping_id") != "so101_parallel_jaw_affine_v1":
        raise ValueError("candidate generator requires a reviewed aperture mapping")
    if maximum_executions < 1:
        raise ValueError("candidate generator maximum_executions must be positive")
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=False)
    executions: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    expert_target_xy = np.asarray(board_square_center(DESTINATION_SQUARE)[:2], dtype=np.float64)
    for candidate in curriculum["candidates"][:maximum_executions]:
        planned_xy = np.asarray(candidate["continuous_target_xy_m"], dtype=np.float64)
        if candidate.get("piece_id") != SOURCE_PIECE_ID or not np.allclose(
            planned_xy, expert_target_xy, atol=1e-12
        ):
            unsupported.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "reason": "repo_native_expert_does_not_cover_planned_piece_or_target",
                    "training_rows_authorized": 0,
                }
            )
            continue
        episode_directory = output_directory / str(candidate["candidate_id"])
        generated = collect_pawn_source_expert_candidate(
            episode_directory,
            render_size=64,
        )
        receipt = json.loads(
            (episode_directory / "recording_receipt.json").read_text(encoding="utf-8")
        )
        executions.append(
            {
                "candidate_id": candidate["candidate_id"],
                "episode_directory": str(episode_directory),
                "generated_recording_id": receipt["recording_id"],
                "object_dimensions_m": dimensions,
                "gripper_aperture_mapping": dict(gripper_aperture_mapping),
                "generator_id": "repo_native_pawn_source_expert_v1",
                "generator_receipt_sha256": generated["receipt_sha256"],
                "planner_id": candidate["planner_id"],
                "ik_solver_id": candidate["ik_solver_id"],
            }
        )
    unsigned = {
        "schema_version": EXECUTION_BATCH_SCHEMA,
        "curriculum_sha256": curriculum["artifact_sha256"],
        "task_contract_sha256": task_contract_sha256(task_path),
        "execution_count": len(executions),
        "unsupported_count": len(unsupported),
        "executions": executions,
        "unsupported": unsupported,
        "admission_authority": "none_pending_strict_lf09_evaluator",
        "physical_authority": False,
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def _quaternion_conjugate(quaternion: np.ndarray) -> np.ndarray:
    return quaternion * np.asarray([1.0, -1.0, -1.0, -1.0])


def _quaternion_multiply(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    lw, lx, ly, lz = left
    rw, rx, ry, rz = right
    return np.asarray(
        [
            lw * rw - lx * rx - ly * ry - lz * rz,
            lw * rx + lx * rw + ly * rz - lz * ry,
            lw * ry - lx * rz + ly * rw + lz * rx,
            lw * rz + lx * ry - ly * rx + lz * rw,
        ],
        dtype=np.float64,
    )


def _rotation_matrix(quaternion: np.ndarray) -> np.ndarray:
    quaternion = quaternion / max(float(np.linalg.norm(quaternion)), 1e-12)
    w, x, y, z = quaternion
    return np.asarray(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def _relative_pose(reference: np.ndarray, pose: np.ndarray) -> list[float]:
    if reference.shape != (7,) or pose.shape != (7,):
        raise ValueError("relative pose inputs must contain xyz and quaternion")
    reference_quaternion = reference[3:] / max(float(np.linalg.norm(reference[3:])), 1e-12)
    pose_quaternion = pose[3:] / max(float(np.linalg.norm(pose[3:])), 1e-12)
    inverse = _quaternion_conjugate(reference_quaternion)
    translation = _rotation_matrix(inverse) @ (pose[:3] - reference[:3])
    quaternion = _quaternion_multiply(inverse, pose_quaternion)
    return [*translation.astype(float).tolist(), *quaternion.astype(float).tolist()]


def _skill_id(row: dict[str, Any]) -> list[float]:
    phase = ""
    for event in row["events"]["simulator_events"]:
        if event.get("type") == "expert_phase":
            phase = str(event.get("phase") or "")
    groups = [
        {"stand_off", "advance", "pregrasp"},
        {"close", "lift", "grasp_lift"},
        {"transit", "air_recenter", "transport"},
        {"lower", "partial_release", "place_release"},
        {"vertical_extract", "open_clear", "settle", "retreat"},
    ]
    vector = [float(phase in group) for group in groups]
    if sum(vector) != 1.0:
        raise ValueError(f"source row has no consequence-derived skill phase: {phase!r}")
    return vector


def _selected_piece_contact(row: dict[str, Any], piece_id: str) -> float:
    for contact in row["events"]["contacts"]:
        bodies = {str(contact.get("body_a") or ""), str(contact.get("body_b") or "")}
        if piece_id in bodies and any("jaw" in body or "gripper" in body for body in bodies):
            return 1.0
    return 0.0


def encode_goal_act_rows(
    source_rows: list[dict[str, Any]],
    *,
    piece_id: str,
    object_dimensions_m: Iterable[float],
    gripper_aperture_mapping: dict[str, Any],
    task_contract_path: Path | None = None,
) -> list[np.ndarray]:
    """Encode canonical observable source rows into the frozen 61-D state."""

    task = load_act_pick_place_task_contract(
        task_contract_path
        if task_contract_path is not None
        else Path(__file__).parents[2]
        / "configs/tasks/chess_pick_place_act_state_v1.json"
    )
    dimensions = [float(value) for value in object_dimensions_m]
    if len(dimensions) != 3 or not all(value > 0 and math.isfinite(value) for value in dimensions):
        raise ValueError("pawn object dimensions must be three positive finite values")
    if gripper_aperture_mapping.get("mapping_id") != "so101_parallel_jaw_affine_v1":
        raise ValueError("a reviewed gripper-aperture mapping is required")
    scale = float(gripper_aperture_mapping.get("scale_m_per_rad"))
    offset = float(gripper_aperture_mapping.get("offset_m"))
    if not math.isfinite(scale) or not math.isfinite(offset):
        raise ValueError("gripper-aperture mapping is non-finite")
    encoded: list[np.ndarray] = []
    for row in source_rows:
        robot = row["robot"]
        goal = row["goal"]
        end_effector = np.asarray(robot["end_effector_pose_world"], dtype=np.float64)
        piece = np.asarray(goal["selected_piece_pose_world"], dtype=np.float64)
        target = np.asarray(goal["continuous_target_pose_world"], dtype=np.float64)
        aperture = max(0.0, scale * float(robot["gripper_joint_position_rad"]) + offset)
        features = {
            "robot_joint_position": robot["joint_position_rad"],
            "robot_joint_velocity": robot["joint_velocity_rad_s"],
            "end_effector_pose": end_effector,
            "gripper_aperture": [aperture],
            "selected_piece_pose": piece,
            "continuous_target_pose": target,
            "end_effector_in_piece_frame": _relative_pose(piece, end_effector),
            "piece_in_target_frame": _relative_pose(target, piece),
            "object_descriptor": [0.0, 1.0, 0.0, 0.0, *dimensions],
            "observable_skill_id": _skill_id(row),
            "selected_piece_contact": [_selected_piece_contact(row, piece_id)],
        }
        encoded.append(encode_observation(task, features))
    return encoded


def _validate_execution_lineage(
    task: dict[str, Any], candidate: dict[str, Any], execution: dict[str, Any]
) -> dict[str, Any]:
    source = candidate["source"]
    lineage = {
        "source_episode_id": source["source_episode_id"],
        "source_segment_ids": source["source_segment_ids"],
        "source_proof_class": source["source_proof_class"],
        "object_relative_transform_sha256": str(execution.get("object_relative_transform_sha256") or ""),
        "target_relative_transform_sha256": str(execution.get("target_relative_transform_sha256") or ""),
        "planner_id": candidate["planner_id"],
        "ik_solver_id": candidate["ik_solver_id"],
        "scene_id": str(execution.get("scene_id") or ""),
        "initial_state_sha256": str(execution.get("initial_state_sha256") or ""),
        "candidate_seed": candidate["candidate_seed"],
        "repair_parent_id": execution.get("repair_parent_id"),
        "evaluator_contract_sha256": str(execution.get("evaluator_contract_sha256") or ""),
    }
    validate_candidate_lineage(task, lineage)
    for field in REQUIRED_LINEAGE_FIELDS - {"repair_parent_id", "candidate_seed", "source_segment_ids"}:
        if not lineage[field]:
            raise ValueError(f"candidate lineage field is empty: {field}")
    return lineage


def _verified_execution_identity(
    *,
    candidate: dict[str, Any],
    execution: dict[str, Any],
    episode_directory: Path,
    receipt: dict[str, Any],
    source_rows: list[dict[str, Any]],
    verdict: dict[str, Any],
) -> dict[str, Any]:
    if candidate.get("role") != "train":
        raise ValueError("only training-role cousins may enter the training dataset")
    if receipt.get("piece_id") != candidate.get("piece_id"):
        raise ValueError("executed source piece differs from the curriculum candidate")
    target_poses = [row["goal"]["continuous_target_pose_world"] for row in source_rows]
    if not target_poses or any(pose != target_poses[0] for pose in target_poses[1:]):
        raise ValueError("generated candidate target pose is missing or changes by row")
    planned_xy = np.asarray(candidate["continuous_target_xy_m"], dtype=np.float64)
    executed_xy = np.asarray(target_poses[0][:2], dtype=np.float64)
    if planned_xy.shape != (2,) or not np.allclose(planned_xy, executed_xy, atol=1e-12):
        raise ValueError("executed target pose differs from the curriculum candidate")
    initial_path = episode_directory / str(
        receipt["initial_evaluator_privileged_state_path"]
    )
    verified = {
        **execution,
        "scene_id": receipt["scene_id"],
        "initial_state_sha256": sha256_file(initial_path),
        "object_relative_transform_sha256": canonical_digest(
            [row["goal"]["selected_piece_pose_world"] for row in source_rows]
        ),
        "target_relative_transform_sha256": canonical_digest(target_poses),
        "evaluator_contract_sha256": verdict["evaluator_contract_sha256"],
    }
    for field in (
        "scene_id",
        "initial_state_sha256",
        "object_relative_transform_sha256",
        "target_relative_transform_sha256",
        "evaluator_contract_sha256",
    ):
        declared = execution.get(field)
        if declared is not None and declared != verified[field]:
            raise ValueError(f"candidate execution {field} differs from verified bytes")
    return verified


def build_goal_act_dataset(
    curriculum: dict[str, Any],
    *,
    executions: list[dict[str, Any]],
    output_directory: Path,
    task_contract_path: Path | None = None,
) -> dict[str, Any]:
    """Evaluate candidate episodes and write an immutable ACT/GR00T dataset.

    Each execution supplies only paths and generation identities.  This
    function reruns the separate source evaluator itself; it does not consume
    a caller-reported replay or success boolean.
    """

    if curriculum.get("schema_version") != CURRICULUM_SCHEMA:
        raise ValueError("unsupported goal ACT curriculum")
    unsigned_curriculum = {key: value for key, value in curriculum.items() if key != "artifact_sha256"}
    if curriculum.get("artifact_sha256") != canonical_digest(unsigned_curriculum):
        raise ValueError("curriculum digest does not match its content")
    task_path = (
        task_contract_path
        if task_contract_path is not None
        else Path(__file__).parents[2] / "configs/tasks/chess_pick_place_act_state_v1.json"
    )
    task = load_act_pick_place_task_contract(task_path)
    if curriculum.get("task_contract_sha256") != task_contract_sha256(task_path):
        raise ValueError("curriculum uses another task contract")
    candidates = {str(row["candidate_id"]): row for row in curriculum["candidates"]}
    if len(candidates) != len(curriculum["candidates"]):
        raise ValueError("curriculum candidate identities are not unique")
    output_directory = output_directory.resolve()
    if output_directory.exists():
        raise FileExistsError(f"dataset output already exists: {output_directory}")
    output_directory.mkdir(parents=True)

    training_rows: list[dict[str, Any]] = []
    groot_rows: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for execution in executions:
        candidate_id = str(execution.get("candidate_id") or "")
        if candidate_id not in candidates or candidate_id in seen:
            raise ValueError("execution references an unknown or duplicate candidate")
        seen.add(candidate_id)
        candidate = candidates[candidate_id]
        episode_directory = Path(str(execution.get("episode_directory") or "")).resolve()
        rejection_reasons: list[str] = []
        verdict: dict[str, Any] | None = None
        try:
            receipt, source_rows = load_source_episode(episode_directory)
            expected_recording_id = str(
                execution.get("generated_recording_id")
                or candidate["source"]["source_episode_id"]
            )
            if receipt.get("recording_id") != expected_recording_id:
                raise ValueError("executed source recording identity differs from the plan")
            verdict = evaluate_source_episode(
                episode_directory,
                output_path=output_directory / f"{candidate_id}.evaluator.json",
            )
            if verdict.get("strict_success") is not True:
                failed = sorted(name for name, gate in verdict["gates"].items() if not gate["passed"])
                raise ValueError("strict evaluator rejected: " + ",".join(failed))
            if verdict.get("exact_float32_sample_hold_replay_passed") is not True:
                raise ValueError("exact float32 sample-hold replay failed")
            verified_execution = _verified_execution_identity(
                candidate=candidate,
                execution=execution,
                episode_directory=episode_directory,
                receipt=receipt,
                source_rows=source_rows,
                verdict=verdict,
            )
            lineage = _validate_execution_lineage(
                task, candidate, verified_execution
            )
            act_adapted = adapt_source_episode(
                episode_directory, adapter="act", admission_verdict=verdict
            )
            groot_adapted = adapt_source_episode(
                episode_directory, adapter="groot", admission_verdict=verdict
            )
            observations = encode_goal_act_rows(
                source_rows,
                piece_id=str(receipt["piece_id"]),
                object_dimensions_m=execution["object_dimensions_m"],
                gripper_aperture_mapping=execution["gripper_aperture_mapping"],
                task_contract_path=task_path,
            )
            if len(observations) != len(act_adapted):
                raise ValueError("ACT encoding changed source row count")
            start_row = len(training_rows)
            for source_row, adapted, observation in zip(
                source_rows, act_adapted, observations, strict=True
            ):
                action = [float(value) for value in adapted["action_joint_target_rad"]]
                training_rows.append(
                    {
                        "schema_version": ROW_SCHEMA,
                        "candidate_id": candidate_id,
                        "source_sample_index": int(source_row["sample_index"]),
                        "observation": observation.astype(float).tolist(),
                        "action_joint_target_rad": action,
                        "lineage": {**adapted["lineage"], "candidate": lineage},
                    }
                )
            for adapted in groot_adapted:
                groot_rows.append(
                    {
                        **adapted,
                        "candidate_id": candidate_id,
                        "source_root": str(episode_directory),
                    }
                )
            accepted.append(
                {
                    "candidate_id": candidate_id,
                    "recording_id": receipt["recording_id"],
                    "source_receipt_sha256": sha256_file(episode_directory / "recording_receipt.json"),
                    "source_tree_manifest_sha256": canonical_digest(tree_manifest(episode_directory)),
                    "evaluator_verdict_sha256": verdict["canonical_payload_sha256"],
                    "training_row_start": start_row,
                    "training_row_end_exclusive": len(training_rows),
                    "lineage": lineage,
                }
            )
        except (KeyError, TypeError, ValueError, FileNotFoundError) as error:
            rejection_reasons.append(str(error))
        if rejection_reasons:
            rejection = {
                "schema_version": REJECTION_SCHEMA,
                "candidate_id": candidate_id,
                "role": candidate.get("role"),
                "episode_directory": str(episode_directory),
                "reasons": rejection_reasons,
                "evaluator_verdict_sha256": (
                    verdict.get("canonical_payload_sha256") if verdict else None
                ),
                "training_rows_authorized": 0,
            }
            rejection_path = output_directory / "rejections" / f"{candidate_id}.json"
            atomic_write_json(rejection_path, rejection)
            rejected.append(
                {
                    **rejection,
                    "rejection_artifact": rejection_path.relative_to(output_directory).as_posix(),
                    "rejection_artifact_sha256": sha256_file(rejection_path),
                }
            )

    act_payload = _write_jsonl(output_directory / "act_train.jsonl", training_rows)
    groot_payload = _write_jsonl(output_directory / "groot_train.jsonl", groot_rows)
    source_ids = [row["recording_id"] for row in accepted]
    unsigned = {
        "schema_version": DATASET_SCHEMA,
        "task_id": task["task_id"],
        "task_contract_sha256": task_contract_sha256(task_path),
        "curriculum_sha256": curriculum["artifact_sha256"],
        "parent_twin_id": curriculum["parent_twin_id"],
        "generation": curriculum["generation"],
        "accepted": accepted,
        "rejected": rejected,
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "training_episode_ids": source_ids,
        "training_row_count": len(training_rows),
        "held_out_training_rows": 0,
        "rejected_training_rows": 0,
        "act_payload": act_payload,
        "groot_payload": groot_payload,
        "preflight": {
            "observation_dimension": 61,
            "action_dimension": 6,
            "all_rows_have_lineage": all(bool(row["lineage"]) for row in training_rows),
            "all_groot_sources_hash_bound": len(groot_rows) == len(training_rows),
            "privileged_state_in_policy_payload": False,
        },
        "admission_owner": "separate_cpu_fp32_consequence_evaluator",
        "dataset_receipt_path": str(output_directory / "dataset_receipt.json"),
    }
    dataset_sha256 = canonical_digest(unsigned)
    receipt = {**unsigned, "dataset_sha256": dataset_sha256}
    atomic_write_json(output_directory / "dataset_receipt.json", receipt)
    return receipt

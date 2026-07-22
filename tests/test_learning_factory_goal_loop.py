from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import torch

from sim2claw.act_pick_place import load_act_pick_place_task_contract, task_contract_sha256
from sim2claw.goal_act_evaluator import freeze_goal_act_evaluation_cohort
from sim2claw.goal_act_training import load_goal_act_dataset, train_goal_act
from sim2claw.learning_factory_artifacts import canonical_digest, sha256_file
from sim2claw.learning_factory_goal_data import (
    DATASET_SCHEMA,
    ROW_SCHEMA,
    compile_goal_act_curriculum,
    encode_goal_act_rows,
)
from sim2claw.learning_factory_promotion import _publish_skill_package
from sim2claw.learning_factory_recursion import persist_counterexample_registry
from sim2claw.orchestrator_skills import SkillRegistry
from sim2claw.project_bundle import EXPECTED_BG_SKILL_IDS
from sim2claw.paths import REPO_ROOT
from sim2claw.sail.contracts import seal_contract
from sim2claw.sail.twin_worthiness import (
    TwinCapabilityDenied,
    issue_capability_certificate,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _data_capability_context() -> dict:
    identities = {
        "evidence": ["a" * 64],
        "graph": "b" * 64,
        "posterior": "c" * 64,
        "simulator": "d" * 64,
        "evaluator": "e" * 64,
        "policy_candidates": [],
    }
    base = seal_contract(
        {
            "schema_version": "sim2claw.twin_worthiness_certificate.v1",
            "certificate_id": "goal-loop-data-fixture",
            "campaign_id": "goal-loop-fixture",
            "identities": identities,
            "gates": {
                f"TW-G{index}": {
                    "status": "pass" if index <= 2 else "not_evaluable",
                    "reason": "synthetic fixture",
                    "evidence_ids": ["fixture"] if index <= 2 else [],
                }
                for index in range(5)
            },
            "level": "TW-DATA",
            "authority": {
                "data_generation": True,
                "policy_selection": False,
                "physical_canary": False,
                "robot_motion": False,
            },
            "issued_at": "2026-07-22T00:00:00Z",
        }
    )
    scope = {
        "twin_id": "calibrated-twin",
        "workcell_id": "goal-loop-fixture",
        "task_id": "chess_pick_place_act_state_v1",
        "distribution_id": "goal-loop-training-fixture",
        "task_contract_sha256": task_contract_sha256(),
        "distribution_sha256": "1" * 64,
    }
    certificate = issue_capability_certificate(
        base_certificate=base,
        scope=scope,
        not_before="2026-07-22T00:00:00Z",
        expires_at="2027-07-22T00:00:00Z",
        issuance_request={
            "issuer_owner": "deterministic_sail_evaluator",
            "request_id": "goal-loop-data-fixture",
        },
    )
    return {
        "certificate": certificate,
        "request": {
            "capability": "data_generation",
            "stage_id": "LF-08",
            "scope": scope,
            "expected_identities": identities,
            "external_authority": {},
        },
        "at_time": "2026-07-22T12:00:00Z",
    }


def _dataset_fixture(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    payload_path = root / "act_train.jsonl"
    rows = []
    for episode_index, source_id in enumerate(("source-a", "source-b")):
        for sample_index in range(8):
            observation = np.linspace(0.0, 1.0, 61, dtype=np.float32)
            observation += episode_index * 0.1 + sample_index * 0.01
            action = np.linspace(-0.2, 0.2, 6, dtype=np.float32)
            action += sample_index * 0.005
            rows.append(
                {
                    "schema_version": ROW_SCHEMA,
                    "candidate_id": f"candidate-{episode_index}",
                    "source_sample_index": sample_index,
                    "observation": observation.astype(float).tolist(),
                    "action_joint_target_rad": action.astype(float).tolist(),
                    "lineage": {
                        "source_recording_id": source_id,
                        "source_sample_index": sample_index,
                        "candidate": {"candidate_seed": 2101 + episode_index},
                    },
                }
            )
    payload_path.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )
    unsigned = {
        "schema_version": DATASET_SCHEMA,
        "task_id": "chess_pick_place_act_state_v1",
        "task_contract_sha256": task_contract_sha256(),
        "accepted_count": 2,
        "rejected_count": 1,
        "training_episode_ids": ["source-a", "source-b"],
        "training_row_count": len(rows),
        "held_out_training_rows": 0,
        "rejected_training_rows": 0,
        "act_payload": {
            "path": payload_path.name,
            "sha256": sha256_file(payload_path),
            "row_count": len(rows),
        },
    }
    receipt = {**unsigned, "dataset_sha256": canonical_digest(unsigned)}
    receipt_path = root / "dataset_receipt.json"
    _write_json(receipt_path, receipt)
    return receipt_path


def test_curriculum_covers_training_axes_without_opening_heldout() -> None:
    result = compile_goal_act_curriculum(
        parent_twin_id="calibrated-twin",
        source_episodes=[
            {
                "source_episode_id": "admitted-source",
                "source_proof_class": "simulation_strict_success",
                "source_segment_ids": ["all"],
            }
        ],
        maximum_candidates=8,
        twin_capability_context=_data_capability_context(),
    )
    task = load_act_pick_place_task_contract()
    held_seeds = set(task["splits"]["held_out_seeds"])
    held_pairs = set(task["splits"]["object_destination_pairs"]["held_out"])
    assert result["candidate_count"] == 8
    assert set(result["coverage"]["pieces"]) == {
        "brown_pawn_a2",
        "brown_pawn_b1",
        "brown_pawn_c2",
        "brown_pawn_d1",
        "brown_pawn_e2",
        "brown_pawn_f1",
    }
    assert not ({row["candidate_seed"] for row in result["candidates"]} & held_seeds)
    assert not (
        {
            f"{row['piece_id']}:{row['target_cell_id']}"
            for row in result["candidates"]
        }
        & held_pairs
    )
    assert result["split_manifest"]["held_out_training_rows"] == 0
    assert result["admission_authority"] == "none_plan_only"


def test_curriculum_helper_fails_closed_without_recomputed_capability() -> None:
    with pytest.raises(TwinCapabilityDenied):
        compile_goal_act_curriculum(
            parent_twin_id="calibrated-twin",
            source_episodes=[
                {
                    "source_episode_id": "admitted-source",
                    "source_proof_class": "simulation_strict_success",
                    "source_segment_ids": ["all"],
                }
            ],
            maximum_candidates=1,
            twin_capability_context={},
        )


def test_source_observable_encoder_is_exactly_61d_and_rejects_timing_phase() -> None:
    row = {
        "robot": {
            "joint_position_rad": [0.0] * 6,
            "joint_velocity_rad_s": [0.0] * 6,
            "end_effector_pose_world": [0.0, 0.0, 0.2, 1.0, 0.0, 0.0, 0.0],
            "gripper_joint_position_rad": 0.4,
        },
        "goal": {
            "selected_piece_pose_world": [0.02, 0.01, 0.03, 1.0, 0.0, 0.0, 0.0],
            "continuous_target_pose_world": [0.1, -0.1, 0.03, 1.0, 0.0, 0.0, 0.0],
        },
        "events": {
            "contacts": [],
            "simulator_events": [{"type": "expert_phase", "phase": "grasp_lift"}],
        },
    }
    encoded = encode_goal_act_rows(
        [row],
        piece_id="brown_pawn_b1",
        object_dimensions_m=[0.02, 0.02, 0.04],
        gripper_aperture_mapping={
            "mapping_id": "so101_parallel_jaw_affine_v1",
            "scale_m_per_rad": 0.02,
            "offset_m": 0.01,
        },
    )
    assert encoded[0].shape == (61,)
    assert encoded[0].dtype == np.float32
    row["events"]["simulator_events"][0]["phase"] = "elapsed_time_bucket"
    with pytest.raises(ValueError, match="no consequence-derived skill phase"):
        encode_goal_act_rows(
            [row],
            piece_id="brown_pawn_b1",
            object_dimensions_m=[0.02, 0.02, 0.04],
            gripper_aperture_mapping={
                "mapping_id": "so101_parallel_jaw_affine_v1",
                "scale_m_per_rad": 0.02,
                "offset_m": 0.01,
            },
        )


def test_trainer_consumes_exact_dataset_and_tampering_invalidates_lineage(tmp_path: Path) -> None:
    receipt_path = _dataset_fixture(tmp_path / "dataset")
    recipe = json.loads(
        (REPO_ROOT / "configs/training/goal_act_recipe_v1.json").read_text(encoding="utf-8")
    )
    recipe.update(
        {
            "recipe_id": "goal-act-test",
            "chunk_size": 4,
            "n_action_steps": 2,
            "model_dimension": 16,
            "attention_heads": 4,
            "encoder_layers": 1,
            "decoder_layers": 1,
            "feedforward_dimension": 32,
            "latent_dimension": 4,
            "batch_size": 4,
            "optimizer_updates": 2,
            "checkpoint_interval_updates": 1,
            "maximum_wall_seconds": 60,
        }
    )
    recipe_path = tmp_path / "recipe.json"
    _write_json(recipe_path, recipe)
    result = train_goal_act(
        dataset_receipt_path=receipt_path,
        output_directory=tmp_path / "training",
        recipe_path=recipe_path,
    )
    checkpoint_path = Path(result["checkpoint_path"])
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    dataset, _ = load_goal_act_dataset(receipt_path)
    assert checkpoint["training"]["dataset_sha256"] == dataset["dataset_sha256"]
    assert result["dataset_receipt_sha256"] == sha256_file(receipt_path)
    assert result["training_can_promote"] is False
    assert result["resource_closeout"]["cleanup_complete"] is True
    payload_path = receipt_path.parent / "act_train.jsonl"
    payload_path.write_text(payload_path.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing or changed"):
        load_goal_act_dataset(receipt_path)


def test_evaluation_cohort_rejects_training_seed_before_opening_episode(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="frozen held-out split"):
        freeze_goal_act_evaluation_cohort(
            cases=[
                {
                    "case_id": "leak",
                    "candidate_seed": 2101,
                    "runtime_skill_id": "pawn_b1_to_b2",
                    "object_destination_pair": "brown_pawn_b1:target_left_train",
                    "distractor_layout": "one_nearby_distractor",
                    "episode_directory": str(tmp_path / "missing"),
                }
            ],
            output_path=tmp_path / "cohort.json",
        )


def test_counterexample_registry_is_trace_native_deduplicated_and_routed(tmp_path: Path) -> None:
    unsigned = {
        "schema_version": "sim2claw.goal_act_evaluation_receipt.v1",
        "checkpoint_sha256": "1" * 64,
        "cohort_sha256": "2" * 64,
        "evaluator_owner": "separate_cpu_fp32_consequence_evaluator",
        "case_results": [
            {
                "case_id": "case-b1",
                "strict_success": False,
                "failure_codes": ["final_xy_error", "wrong_piece_contact"],
                "action_trace_sha256": "3" * 64,
                "candidate_seed": 9201,
                "object_destination_pair": "brown_pawn_b1:target_left_train",
                "distractor_layout": "one_nearby_distractor",
                "measurements": {"final_xy_error_m": 0.2},
            }
        ],
    }
    evaluation = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    first_path = tmp_path / "registry-1.json"
    first = persist_counterexample_registry(evaluation, output_path=first_path)
    second = persist_counterexample_registry(
        evaluation,
        output_path=tmp_path / "registry-2.json",
        previous_registry_path=first_path,
    )
    assert first["counterexample_count"] == 1
    assert first["route_targets"] == ["LF-06", "LF-08"]
    assert first["counterexamples"][0]["training_rows_authorized"] == 0
    assert second["counterexample_count"] == 1
    assert second["new_counterexample_count"] == 0


def test_publisher_builds_hash_guarded_runtime_package(tmp_path: Path) -> None:
    checkpoint = tmp_path / "source-checkpoint.pt"
    evaluation_path = tmp_path / "source-evaluation.json"
    promotion_path = tmp_path / "source-promotion.json"
    checkpoint.write_bytes(b"checkpoint")
    _write_json(evaluation_path, {"schema_version": "fixture-evaluation"})
    _write_json(promotion_path, {"schema_version": "fixture-promotion"})
    package = _publish_skill_package(
        output_directory=tmp_path / "published",
        project={
            "project_id": "publisher-mechanism-fixture",
            "scope": {"directed_skill_ids": list(EXPECTED_BG_SKILL_IDS)},
        },
        training={
            "checkpoint_path": str(checkpoint),
            "checkpoint_sha256": sha256_file(checkpoint),
        },
        evaluation={"artifact_sha256": "1" * 64},
        evaluation_path=evaluation_path,
        promotion_path=promotion_path,
    )
    registry_path = Path(package["registry_path"])
    registry = SkillRegistry.load(registry_path)
    assert registry.capability_summary()["callable"] == 12
    contract = json.loads(
        (registry_path.parent / "counterexample_return_contract.json").read_text(
            encoding="utf-8"
        )
    )
    assert contract["training_rows_authorized"] == 0
    (registry_path.parent / "evaluation_receipt.json").unlink()
    assert SkillRegistry.load(registry_path).capability_summary()["callable"] == 0

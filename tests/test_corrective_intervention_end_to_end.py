from __future__ import annotations

import json
from pathlib import Path

import mujoco
import numpy as np
import pytest
import torch

from sim2claw.corrective_intervention import (
    FAILURE_PACKET_SCHEMA,
    PROPOSAL_SCHEMA,
    compile_task_space_intervention,
)
from sim2claw.corrective_intervention_lf import (
    admit_llm_proposed_correction,
    build_correction_submission,
    materialize_correction_evidence,
)
from sim2claw.corrective_intervention_runtime import capture_branch_state
from sim2claw.corrective_intervention_training import (
    build_goal_act_correction_mixture,
    evaluate_correction_checkpoint_runtime,
)
from sim2claw.goal_act_training import train_goal_act
from sim2claw.learning_factory_artifacts import canonical_digest, sha256_file
from sim2claw.learning_factory_goal_data import (
    DATASET_SCHEMA,
    ROW_SCHEMA,
    encode_goal_act_rows,
)
from sim2claw.learning_factory_recursion import (
    CORRECTION_SCHEMA,
    REGISTRY_SCHEMA,
    _independent_replay_digest,
)
from sim2claw.pawn_source_evaluator import evaluate_source_episode
from sim2claw.pawn_source_expert import collect_pawn_source_expert_candidate
from sim2claw.paths import REPO_ROOT
from sim2claw.act_pick_place import task_contract_sha256
from sim2claw.scene import CURRENT_TASK_PIECE_LAYOUT, build_scene_spec, registered_board_center
from sim2claw.source_episode import (
    admission_payload_sha256,
    adapt_source_episode,
    load_source_episode,
)


DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_full_corrective_episode_replays_and_admits_suffix_only(tmp_path: Path) -> None:
    nominal_directory = tmp_path / "nominal"
    nominal_result = collect_pawn_source_expert_candidate(
        nominal_directory,
        render_size=64,
    )
    nominal_receipt, nominal_rows = load_source_episode(nominal_directory)
    assert nominal_result["sample_count"] == len(nominal_rows)
    privileged_rows = _load_jsonl(
        nominal_directory / nominal_receipt["evaluator_privileged_state_path"]
    )
    branch_index = 1
    branch_state_values = np.asarray(
        privileged_rows[branch_index - 1]["state"]["integration_state_float64"],
        dtype=np.float64,
    )
    model = build_scene_spec(
        piece_layout=CURRENT_TASK_PIECE_LAYOUT,
        board_center_in_table_frame_xy_m=registered_board_center(
            nominal_receipt["scene_id"]
        ),
    ).compile()
    branch_data = mujoco.MjData(model)
    mujoco.mj_setState(
        model,
        branch_data,
        branch_state_values,
        mujoco.mjtState.mjSTATE_INTEGRATION,
    )
    mujoco.mj_forward(model, branch_data)
    initial_action = nominal_rows[branch_index - 1]["action"]["joint_target_rad"]
    state = capture_branch_state(
        model,
        branch_data,
        scene_id=nominal_receipt["scene_id"],
        initial_action_rad=initial_action,
    )
    packet = {
        "schema_version": FAILURE_PACKET_SCHEMA,
        "counterexample_id": "counterexample-synthetic-canonical-repair-v1",
        "source_role": "development",
        "proof_class": "simulation",
        "identities": {
            "dataset_sha256": DIGEST_A,
            "policy_id": "synthetic-fixture-policy",
            "scene_id": nominal_receipt["scene_id"],
            "evaluator_id": "chess_pick_place_pawn_evaluator_v3",
            "action_trace_sha256": DIGEST_B,
        },
        "branch": {
            "step": branch_index,
            "integration_state_sha256": state["artifact_sha256"],
        },
        "observations": [
            {
                "kind": "robot_joint_state",
                "artifact_sha256": DIGEST_C,
                "description": "synthetic fixture branch joints",
            }
        ],
        "failure": {
            "code": "pregrasp_lateral_offset",
            "phase": "pregrasp",
            "first_divergence_step": branch_index,
            "consequences": {"synthetic_fixture_failure": True},
        },
        "budgets": {"candidate_proposals": 8, "simulator_calls": 136},
        "authority": {
            "held_out": False,
            "policy_adapter_privileged_state": False,
            "physical_authority": False,
            "promotion_authority": False,
        },
    }
    proposal = {
        "schema_version": PROPOSAL_SCHEMA,
        "proposal_id": "proposal-synthetic-canonical-repair-v1",
        "counterexample_id": packet["counterexample_id"],
        "branch_state_sha256": state["artifact_sha256"],
        "bindings": packet["identities"],
        "proposer": {
            "model_id": "deterministic-fixture-proposer",
            "harness_id": "hardware-free-test",
            "prompt_sha256": DIGEST_A,
            "skill_bundle_sha256": DIGEST_B,
            "tool_contract_sha256": DIGEST_C,
        },
        "waypoints": [
            {
                "reference_frame": "selected_object",
                "translation_delta_m": [0.0, 0.0, 0.001],
                "rotation_delta_axis_angle_rad": [0.0, 0.0, 0.0],
                "gripper_delta_rad": 0.0,
                "duration_s": 0.25,
                "expected_effect": "bounded early pregrasp perturbation",
            }
        ],
        "expected_consequences": {"canonical_episode_remains_successful": True},
        "confidence": 1.0,
        "abstain": False,
    }
    compiled = compile_task_space_intervention(
        proposal,
        failure_packet=packet,
        model=model,
        branch_data=branch_data,
        selected_piece_body_name=nominal_receipt["piece_id"],
        target_rotation_world=np.eye(3),
        initial_action_rad=initial_action,
    )
    intervention_end = branch_index + len(compiled["actions_rad"])
    corrected_directory = tmp_path / "corrected"
    collect_pawn_source_expert_candidate(
        corrected_directory,
        render_size=64,
        corrective_action_overrides={
            branch_index + offset: action
            for offset, action in enumerate(compiled["actions_rad"])
        },
        correction_lineage={
            "parent_counterexample_id": packet["counterexample_id"],
            "parent_source_episode_id": nominal_receipt["recording_id"],
            "branch_state_sha256": state["artifact_sha256"],
            "proposal_sha256": canonical_digest(proposal),
            "compiled_trajectory_sha256": canonical_digest(compiled),
            "intervention_start_sample_index": branch_index,
            "intervention_end_sample_index_exclusive": intervention_end,
        },
    )
    corrected_receipt, corrected_rows = load_source_episode(corrected_directory)
    assert [
        row["action"]["joint_target_rad"]
        for row in corrected_rows[:branch_index]
    ] == [
        row["action"]["joint_target_rad"]
        for row in nominal_rows[:branch_index]
    ]
    corrected_privileged_rows = _load_jsonl(
        corrected_directory / corrected_receipt["evaluator_privileged_state_path"]
    )
    assert (
        corrected_privileged_rows[branch_index - 1]["state"][
            "integration_state_float64"
        ]
        == privileged_rows[branch_index - 1]["state"][
            "integration_state_float64"
        ]
    )
    assert [row["action"]["joint_target_rad"] for row in corrected_rows[branch_index:intervention_end]] == compiled["actions_rad"]
    assert all(
        row["action"]["intervention"] == 1
        for row in corrected_rows[branch_index:intervention_end]
    )
    ordinary_verdict = evaluate_source_episode(corrected_directory)
    assert ordinary_verdict["strict_success"] is True
    assert ordinary_verdict["exact_float32_sample_hold_replay_passed"] is True

    parent = {
        "counterexample_id": packet["counterexample_id"],
        "action_trace_sha256": packet["identities"]["action_trace_sha256"],
        "route_targets": ["LF-09"],
        "training_rows_authorized": 0,
    }
    evidence = materialize_correction_evidence(
        tmp_path / "correction-evidence",
        parent_counterexample=parent,
        start_sample_index=branch_index,
        branch_state=state,
        proposal=proposal,
        compiled_trajectory=compiled,
    )
    suffix = {
        "start_sample_index": branch_index,
        "end_sample_index_exclusive": len(corrected_rows),
        "exact_pre_failure_integration_state_matched": True,
        "failed_prefix_excluded_from_imitation_rows": True,
        "independent_full_episode_replay_passed": True,
        "corrective_actions_owned_by_declared_expert_or_teleoperator": True,
        "parent_counterexample_id": packet["counterexample_id"],
        "failed_prefix_sha256": evidence["failed_prefix"]["sha256"],
        "pre_failure_integration_state_sha256": evidence[
            "pre_failure_integration_state"
        ]["sha256"],
        "intervention_sha256": evidence["intervention"]["sha256"],
        "independent_full_episode_evidence_sha256": _independent_replay_digest(
            ordinary_verdict
        ),
    }
    corrective_verdict = {
        **ordinary_verdict,
        "admission_class": "corrective_suffix",
        "all_source_actions_admitted": False,
        "corrective_suffix": suffix,
    }
    corrective_verdict["canonical_payload_sha256"] = admission_payload_sha256(
        corrective_verdict
    )
    verdict_path = tmp_path / "corrective-verdict.json"
    verdict_path.write_text(
        json.dumps(corrective_verdict, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    registry_unsigned = {
        "schema_version": REGISTRY_SCHEMA,
        "source_evaluation_sha256": DIGEST_A,
        "parent_registry_sha256": None,
        "counterexample_count": 1,
        "new_counterexample_count": 1,
        "counterexamples": [parent],
        "route_targets": ["LF-09"],
        "correction_candidates": [],
        "raw_failures_are_training_data": False,
    }
    registry = {
        **registry_unsigned,
        "artifact_sha256": canonical_digest(registry_unsigned),
    }
    submission = build_correction_submission(
        correction_candidate_id="correction-synthetic-canonical-v1",
        evidence=evidence,
        corrective_episode_directory=corrected_directory,
        admission_verdict_path=verdict_path,
    )
    assert submission["schema_version"] == CORRECTION_SCHEMA
    admitted = admit_llm_proposed_correction(submission, registry=registry)
    adapted = adapt_source_episode(
        corrected_directory,
        adapter="act",
        admission_verdict=corrective_verdict,
    )
    assert admitted["independent_evaluator_admitted"] is True
    assert admitted["failed_prefix_training_rows"] == 0
    assert admitted["admitted_suffix_row_count"] == len(corrected_rows) - branch_index
    assert len(adapted) == len(corrected_rows) - branch_index
    assert adapted[0]["lineage"]["source_sample_index"] == branch_index

    nominal_verdict = evaluate_source_episode(nominal_directory)
    assert nominal_verdict["strict_success"] is True
    nominal_adapted = adapt_source_episode(
        nominal_directory,
        adapter="act",
        admission_verdict=nominal_verdict,
    )
    dimensions = [0.02, 0.02, 0.04]
    aperture_mapping = {
        "mapping_id": "so101_parallel_jaw_affine_v1",
        "scale_m_per_rad": 0.02,
        "offset_m": 0.01,
    }
    nominal_observations = encode_goal_act_rows(
        nominal_rows,
        piece_id=nominal_receipt["piece_id"],
        object_dimensions_m=dimensions,
        gripper_aperture_mapping=aperture_mapping,
    )
    base_rows = [
        {
            "schema_version": ROW_SCHEMA,
            "candidate_id": "nominal-canonical-source",
            "source_sample_index": int(source_row["sample_index"]),
            "observation": observation.astype(float).tolist(),
            "action_joint_target_rad": adapted_row["action_joint_target_rad"],
            "lineage": adapted_row["lineage"],
        }
        for source_row, adapted_row, observation in zip(
            nominal_rows,
            nominal_adapted,
            nominal_observations,
            strict=True,
        )
    ]
    base_directory = tmp_path / "base-dataset"
    base_directory.mkdir()
    base_payload_path = base_directory / "act_train.jsonl"
    base_payload_path.write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in base_rows
        ),
        encoding="utf-8",
    )
    base_unsigned = {
        "schema_version": DATASET_SCHEMA,
        "task_id": "chess_pick_place_act_state_v1",
        "task_contract_sha256": task_contract_sha256(),
        "accepted_count": 1,
        "rejected_count": 0,
        "training_episode_ids": [nominal_receipt["recording_id"]],
        "training_row_count": len(base_rows),
        "held_out_training_rows": 0,
        "rejected_training_rows": 0,
        "act_payload": {
            "path": base_payload_path.name,
            "sha256": sha256_file(base_payload_path),
            "row_count": len(base_rows),
        },
    }
    base_receipt = {**base_unsigned, "dataset_sha256": canonical_digest(base_unsigned)}
    base_receipt_path = base_directory / "dataset_receipt.json"
    _write_json(base_receipt_path, base_receipt)
    mixture_directory = tmp_path / "correction-mixture"
    mixture = build_goal_act_correction_mixture(
        base_dataset_receipt_path=base_receipt_path,
        corrections=[{"admitted_correction": admitted}],
        output_directory=mixture_directory,
        object_dimensions_m=dimensions,
        gripper_aperture_mapping=aperture_mapping,
    )
    assert mixture["base_training_row_count"] == len(nominal_rows)
    assert mixture["correction_training_row_count"] == len(corrected_rows) - 1
    assert mixture["held_out_training_rows"] == 0
    assert mixture["preflight"]["failed_prefix_training_rows"] == 0

    recipe = json.loads(
        (REPO_ROOT / "configs/training/goal_act_recipe_v1.json").read_text(
            encoding="utf-8"
        )
    )
    recipe.update(
        {
            "recipe_id": "corrective-mixture-fixture-v1",
            "device": "cpu",
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
    recipe_path = tmp_path / "correction-recipe.json"
    _write_json(recipe_path, recipe)
    training_directory = tmp_path / "correction-training"
    training = train_goal_act(
        dataset_receipt_path=mixture_directory / "dataset_receipt.json",
        output_directory=training_directory,
        recipe_path=recipe_path,
    )
    checkpoint = torch.load(
        training["checkpoint_path"],
        map_location="cpu",
        weights_only=False,
    )
    assert checkpoint["training"]["dataset_sha256"] == mixture["dataset_sha256"]
    smoke = evaluate_correction_checkpoint_runtime(
        checkpoint_path=Path(training["checkpoint_path"]),
        training_receipt_path=training_directory / "training_receipt.json",
        dataset_receipt_path=mixture_directory / "dataset_receipt.json",
        output_path=tmp_path / "checkpoint-smoke.json",
    )
    assert smoke["finite_actions"] is True
    assert smoke["behavioral_evaluation"] is False
    assert smoke["held_out_policy_success"] is None


def test_generator_rejects_noncontiguous_or_unbound_overrides(tmp_path: Path) -> None:
    action = [0.0] * 6
    with pytest.raises(ValueError, match="contiguous"):
        collect_pawn_source_expert_candidate(
            tmp_path / "noncontiguous",
            corrective_action_overrides={1: action, 3: action},
            correction_lineage={
                "parent_counterexample_id": "counterexample",
                "parent_source_episode_id": "episode",
                "branch_state_sha256": DIGEST_A,
                "proposal_sha256": DIGEST_B,
                "compiled_trajectory_sha256": DIGEST_C,
                "intervention_start_sample_index": 1,
                "intervention_end_sample_index_exclusive": 4,
            },
        )
    with pytest.raises(ValueError, match="require immutable correction lineage"):
        collect_pawn_source_expert_candidate(
            tmp_path / "unbound",
            corrective_action_overrides={1: action},
        )

from __future__ import annotations

import copy

import mujoco
import numpy as np
import pytest

from sim2claw.corrective_intervention import (
    FAILURE_PACKET_SCHEMA,
    POSTERIOR_SCHEMA,
    PROPOSAL_SCHEMA,
    CorrectiveInterventionError,
    compile_task_space_intervention,
)
from sim2claw.corrective_intervention_runtime import (
    capture_branch_state,
    restore_branch_state,
    run_compiled_branch,
    run_posterior_robustness,
    sample_robustness_posterior,
    score_intervention_proposal,
)
from sim2claw.grasp import _actuator_map
from sim2claw.scene import CURRENT_TASK_PIECE_LAYOUT, ROBOT_JOINTS, build_scene_spec, initialize_robot_poses


DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64
DIGEST_D = "d" * 64
DIGEST_E = "e" * 64


def failure_packet() -> dict:
    return {
        "schema_version": FAILURE_PACKET_SCHEMA,
        "counterexample_id": "counterexample-centering-001",
        "source_role": "development",
        "proof_class": "simulation",
        "identities": {
            "dataset_sha256": DIGEST_A,
            "policy_id": "policy-dev-001",
            "scene_id": "scene-100mm-v1",
            "evaluator_id": "pawn-consequence-cpu-fp32-v1",
            "action_trace_sha256": DIGEST_B,
        },
        "branch": {"step": 80, "integration_state_sha256": DIGEST_C},
        "observations": [
            {"kind": "wrist_rgb", "artifact_sha256": DIGEST_D, "description": "branch frame"}
        ],
        "failure": {
            "code": "pregrasp_lateral_offset",
            "phase": "pregrasp",
            "first_divergence_step": 84,
            "consequences": {"lateral_error_m": 0.006},
        },
        "budgets": {"candidate_proposals": 8, "simulator_calls": 136},
        "authority": {
            "held_out": False,
            "policy_adapter_privileged_state": False,
            "physical_authority": False,
            "promotion_authority": False,
        },
    }


def proposal() -> dict:
    packet = failure_packet()
    return {
        "schema_version": PROPOSAL_SCHEMA,
        "proposal_id": "proposal-centering-001",
        "counterexample_id": packet["counterexample_id"],
        "branch_state_sha256": packet["branch"]["integration_state_sha256"],
        "bindings": copy.deepcopy(packet["identities"]),
        "proposer": {
            "model_id": "fixture-model",
            "harness_id": "inspect-codex-cli",
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
                "expected_effect": "move the pregrasp pinch point upward",
            }
        ],
        "expected_consequences": {"lateral_error_m": 0.002},
        "confidence": 0.7,
        "abstain": False,
    }


def posterior() -> dict:
    return {
        "schema_version": POSTERIOR_SCHEMA,
        "posterior_id": "posterior-centering-dev-v1",
        "scene_id": "scene-100mm-v1",
        "evaluator_id": "pawn-consequence-cpu-fp32-v1",
        "source_evidence_sha256": [DIGEST_A, DIGEST_B],
        "parameters": [
            {
                "name": "object_pose_x_m",
                "distribution": "truncated_normal",
                "nominal": 0.0,
                "lower": -0.01,
                "upper": 0.01,
                "stddev": 0.003,
                "evidence_sha256": DIGEST_A,
            },
            {
                "name": "control_latency_s",
                "distribution": "uniform",
                "nominal": 0.03,
                "lower": 0.01,
                "upper": 0.06,
                "stddev": None,
                "evidence_sha256": DIGEST_B,
            },
        ],
        "development_seeds": list(range(4101, 4117)),
        "sealed_seeds": list(range(9101, 9117)),
        "authority": {
            "calibration_proof": False,
            "physical_transfer_proof": False,
            "visible_to_proposer": False,
            "promotion_authority": False,
        },
    }


def _model_data_action() -> tuple[mujoco.MjModel, mujoco.MjData, list[float]]:
    model = build_scene_spec(piece_layout=CURRENT_TASK_PIECE_LAYOUT).compile()
    data = mujoco.MjData(model)
    initialize_robot_poses(model, data)
    actuators = _actuator_map(model, "left")
    action = [float(data.ctrl[actuators[joint]]) for joint in ROBOT_JOINTS]
    return model, data, action


def test_capture_restore_is_exact_and_tamper_evident() -> None:
    model, data, action = _model_data_action()
    state = capture_branch_state(model, data, scene_id="scene-100mm-v1", initial_action_rad=action)
    restored = restore_branch_state(model, state)
    assert restored.time == data.time
    assert np.array_equal(restored.qpos, data.qpos)
    tampered = copy.deepcopy(state)
    tampered["integration_state_float64"][0] += 1.0
    with pytest.raises(CorrectiveInterventionError, match="digest mismatch"):
        restore_branch_state(model, tampered)


def test_compiled_branch_binds_state_and_stops_short_of_admission() -> None:
    model, data, action = _model_data_action()
    state = capture_branch_state(model, data, scene_id="scene-100mm-v1", initial_action_rad=action)
    packet = failure_packet()
    packet["branch"]["integration_state_sha256"] = state["artifact_sha256"]
    value = proposal()
    value["branch_state_sha256"] = state["artifact_sha256"]
    value["waypoints"][0].update(
        {
            "translation_delta_m": [0.0, 0.0, 0.001],
            "rotation_delta_axis_angle_rad": [0.0, 0.0, 0.0],
            "gripper_delta_rad": 0.0,
        }
    )
    compiled = compile_task_space_intervention(
        value,
        failure_packet=packet,
        model=model,
        branch_data=data,
        selected_piece_body_name="tan_pawn_c8",
        target_rotation_world=np.eye(3),
        initial_action_rad=action,
    )
    result = run_compiled_branch(
        model,
        branch_state=state,
        compiled_trajectory=compiled,
        scene_id="scene-100mm-v1",
        consequence_observer=lambda _model, branch_data, index: {
            "sample_index": float(index),
            "simulation_time_s": float(branch_data.time),
        },
    )
    receipt = result["receipt"]
    assert receipt["exact_branch_state_restored"] is True
    assert receipt["action_count"] == 5
    assert receipt["authority"]["branch_only_diagnostic"] is True
    assert receipt["authority"]["full_prefix_plus_suffix_replay_passed"] is False
    assert receipt["authority"]["training_admitted"] is False


def test_branch_rejects_another_state_or_initial_action() -> None:
    model, data, action = _model_data_action()
    state = capture_branch_state(model, data, scene_id="scene-100mm-v1", initial_action_rad=action)
    packet = failure_packet()
    packet["branch"]["integration_state_sha256"] = state["artifact_sha256"]
    value = proposal()
    value["branch_state_sha256"] = state["artifact_sha256"]
    value["waypoints"][0].update(
        {
            "translation_delta_m": [0.0, 0.0, 0.001],
            "rotation_delta_axis_angle_rad": [0.0, 0.0, 0.0],
            "gripper_delta_rad": 0.0,
        }
    )
    compiled = compile_task_space_intervention(
        value,
        failure_packet=packet,
        model=model,
        branch_data=data,
        selected_piece_body_name="tan_pawn_c8",
        target_rotation_world=np.eye(3),
        initial_action_rad=action,
    )
    wrong = copy.deepcopy(compiled)
    wrong["branch_state_sha256"] = DIGEST_A
    with pytest.raises(CorrectiveInterventionError, match="another branch state"):
        run_compiled_branch(
            model,
            branch_state=state,
            compiled_trajectory=wrong,
            scene_id="scene-100mm-v1",
        )


def test_posterior_sampling_is_deterministic_bounded_and_split() -> None:
    value = posterior()
    first = sample_robustness_posterior(value)
    second = sample_robustness_posterior(value)
    sealed = sample_robustness_posterior(value, split="sealed")
    assert first == second
    assert {row["seed"] for row in first}.isdisjoint({row["seed"] for row in sealed})
    for row in first:
        assert -0.01 <= row["parameters"]["object_pose_x_m"] <= 0.01
        assert 0.01 <= row["parameters"]["control_latency_s"] <= 0.06


def test_score_requires_nominal_robust_nonregressing_repair() -> None:
    results = [
        {"split": "development", "strict_success": index < 12, "safety_violations": 0}
        for index in range(16)
    ]
    score = score_intervention_proposal(
        proposal_sha256=DIGEST_A,
        counterexample_id="counterexample-centering-001",
        evaluator_id="evaluator-v1",
        nominal_strict_success=True,
        nominal_safety_violations=0,
        policy_consequence_reward=1.0,
        baseline_strict_success=False,
        robustness_results=results,
        development_seed_set_sha256=DIGEST_B,
        intervention_cost=0.1,
        ik_failure_count=0,
        non_regression=True,
    )
    assert score["decision"]["suffix_candidate"] is True
    assert score["decision"]["training_admitted"] is False

    results[0]["safety_violations"] = 1
    rejected = score_intervention_proposal(
        proposal_sha256=DIGEST_A,
        counterexample_id="counterexample-centering-001",
        evaluator_id="evaluator-v1",
        nominal_strict_success=True,
        nominal_safety_violations=0,
        policy_consequence_reward=1.0,
        baseline_strict_success=False,
        robustness_results=results,
        development_seed_set_sha256=DIGEST_B,
        intervention_cost=0.1,
        ik_failure_count=0,
        non_regression=True,
    )
    assert rejected["decision"]["suffix_candidate"] is False


def test_posterior_runner_preserves_trials_and_sealed_selection_boundary() -> None:
    value = posterior()

    def trial(sample: dict) -> dict:
        success = sample["parameters"]["object_pose_x_m"] <= 0.005
        return {
            "strict_success": success,
            "safety_violations": 0,
            "policy_consequence_reward": 1.0 if success else 0.0,
            "consequence_sha256": DIGEST_C,
        }

    development = run_posterior_robustness(value, trial_runner=trial)
    repeated = run_posterior_robustness(value, trial_runner=trial)
    sealed = run_posterior_robustness(value, trial_runner=trial, split="sealed")
    assert development == repeated
    assert development["receipt"]["selection_eligible"] is True
    assert sealed["receipt"]["selection_eligible"] is False
    assert development["receipt"]["authority"]["training_admitted"] is False


def test_score_rejects_sealed_selection_results() -> None:
    with pytest.raises(CorrectiveInterventionError, match="sealed results"):
        score_intervention_proposal(
            proposal_sha256=DIGEST_A,
            counterexample_id="counterexample-centering-001",
            evaluator_id="evaluator-v1",
            nominal_strict_success=True,
            nominal_safety_violations=0,
            policy_consequence_reward=1.0,
            baseline_strict_success=False,
            robustness_results=[{"split": "sealed", "strict_success": True, "safety_violations": 0}],
            development_seed_set_sha256=DIGEST_B,
            intervention_cost=0.1,
            ik_failure_count=0,
            non_regression=True,
        )

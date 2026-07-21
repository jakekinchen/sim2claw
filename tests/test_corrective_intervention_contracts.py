from __future__ import annotations

import copy

import mujoco
import numpy as np
import pytest

from sim2claw.corrective_intervention import (
    COMPILED_TRAJECTORY_SCHEMA,
    FAILURE_PACKET_SCHEMA,
    POSTERIOR_SCHEMA,
    PROPOSAL_SCHEMA,
    PROPOSAL_SCORE_SCHEMA,
    CorrectiveInterventionError,
    build_failure_packet,
    compile_task_space_intervention,
    load_corrective_loop_contract,
    seal_artifact,
    validate_compiled_trajectory,
    validate_failure_packet,
    validate_intervention_proposal,
    validate_proposal_score,
    validate_robustness_posterior,
    verify_sealed_artifact,
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
            {"kind": "wrist_rgb", "artifact_sha256": DIGEST_D, "description": "wrist frame at branch"},
            {"kind": "robot_joint_state", "artifact_sha256": DIGEST_E, "description": "requested and observed joints"},
        ],
        "failure": {
            "code": "pregrasp_lateral_offset",
            "phase": "pregrasp",
            "first_divergence_step": 84,
            "consequences": {"selected_piece_contact": False, "lateral_error_m": 0.006},
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
                "translation_delta_m": [-0.003, 0.002, 0.004],
                "rotation_delta_axis_angle_rad": [0.0, 0.0, 0.02],
                "gripper_delta_rad": -0.04,
                "duration_s": 0.25,
                "expected_effect": "recenter before closure",
            }
        ],
        "expected_consequences": {"selected_piece_contact": True, "lateral_error_m": 0.002},
        "confidence": 0.7,
        "abstain": False,
    }


def compiled_trajectory() -> dict:
    actions = [
        [0.01, 0.0, 0.0, 0.0, 0.0, -0.01],
        [0.02, 0.0, 0.0, 0.0, 0.0, -0.02],
    ]
    return {
        "schema_version": COMPILED_TRAJECTORY_SCHEMA,
        "proposal_sha256": DIGEST_A,
        "counterexample_id": "counterexample-centering-001",
        "branch_state_sha256": DIGEST_C,
        "compiler": {"compiler_id": "bounded-cartesian-v1", "ik_solver_id": "so101-dls-v1"},
        "execution": {
            "sample_hold_hz": 20,
            "action_representation": "absolute_joint_position_target",
            "action_dimension": 6,
            "maximum_action_count": 20,
            "no_clipping": True,
        },
        "initial_action_rad": [0.0] * 6,
        "maximum_delta_per_sample_rad": [0.05] * 6,
        "actions_rad": actions,
        "diagnostics": {
            "maximum_ik_residual_m": 0.002,
            "collision_free": True,
            "joint_limits_passed": True,
            "rate_limits_passed": True,
            "duration_s": len(actions) / 20,
        },
        "authority": {
            "compiled_action_owner": "geometric_expert",
            "llm_direct_control": False,
            "physical_authority": False,
        },
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


def proposal_score() -> dict:
    return {
        "schema_version": PROPOSAL_SCORE_SCHEMA,
        "proposal_sha256": DIGEST_A,
        "counterexample_id": "counterexample-centering-001",
        "evaluator_id": "pawn-consequence-cpu-fp32-v1",
        "nominal": {"strict_success": True, "safety_violations": 0, "policy_consequence_reward": 1.0},
        "robustness": {
            "sample_count": 16,
            "success_count": 12,
            "safety_violations": 0,
            "threshold_met": True,
            "development_seed_set_sha256": DIGEST_B,
        },
        "components": {
            "success_uplift": 1.0,
            "robustness_rate": 0.75,
            "intervention_cost": 0.1,
            "ik_failure_penalty": 0.0,
            "safety_penalty": 0.0,
            "non_regression": True,
        },
        "decision": {
            "suffix_candidate": True,
            "requires_independent_full_replay": True,
            "training_admitted": False,
            "promoted": False,
        },
        "authority": {
            "policy_reward_is_proposal_score": False,
            "evaluator_owns_admission": True,
            "promotion_authority": False,
            "physical_transfer_proof": False,
        },
    }


def counterexample() -> dict:
    return {
        "counterexample_id": "counterexample-centering-001",
        "checkpoint_sha256": DIGEST_A,
        "cohort_sha256": DIGEST_B,
        "action_trace_sha256": DIGEST_C,
        "failure_codes": ["pregrasp_lateral_offset"],
        "route_targets": ["LF-09"],
        "training_rows_authorized": 0,
    }


def test_valid_contracts_are_normalized_without_mutation() -> None:
    assert load_corrective_loop_contract()["contract_id"] == "llm_corrective_intervention_pregrasp_v1"
    packet = failure_packet()
    proposal_value = proposal()
    assert validate_failure_packet(packet) == packet
    assert validate_intervention_proposal(proposal_value, failure_packet=packet) == proposal_value
    assert validate_compiled_trajectory(compiled_trajectory())["actions_rad"][-1][-1] == -0.02
    assert validate_robustness_posterior(posterior())["development_seeds"][0] == 4101
    assert validate_proposal_score(proposal_score())["decision"]["suffix_candidate"] is True


def test_sealed_artifacts_detect_mutation() -> None:
    sealed = seal_artifact(proposal())
    assert verify_sealed_artifact(sealed) == sealed
    sealed["confidence"] = 0.4
    with pytest.raises(CorrectiveInterventionError, match="digest mismatch"):
        verify_sealed_artifact(sealed)


def test_failure_packet_builder_uses_lf12_identity_without_privileged_bytes() -> None:
    packet = build_failure_packet(
        counterexample=counterexample(),
        source_role="development",
        scene_id="scene-100mm-v1",
        evaluator_id="pawn-consequence-cpu-fp32-v1",
        branch_step=80,
        branch_state_sha256=DIGEST_D,
        first_divergence_step=84,
        failure_code="pregrasp_lateral_offset",
        failure_phase="pregrasp",
        consequences={"lateral_error_m": 0.006},
        observations=[
            {"kind": "wrist_rgb", "artifact_sha256": DIGEST_E, "description": "branch frame"}
        ],
    )
    assert packet["identities"]["dataset_sha256"] == DIGEST_B
    assert packet["identities"]["policy_id"] == f"checkpoint-sha256:{DIGEST_A}"
    assert "integration_state" not in str(packet["observations"])


def test_failure_packet_builder_rejects_non_lf09_and_unowned_failure() -> None:
    row = counterexample()
    row["route_targets"] = ["LF-06"]
    with pytest.raises(CorrectiveInterventionError, match="not routed"):
        build_failure_packet(
            counterexample=row,
            source_role="development",
            scene_id="scene",
            evaluator_id="evaluator",
            branch_step=1,
            branch_state_sha256=DIGEST_D,
            first_divergence_step=1,
            failure_code="pregrasp_lateral_offset",
            failure_phase="pregrasp",
            consequences={"error": 1.0},
            observations=[{"kind": "wrist_rgb", "artifact_sha256": DIGEST_E, "description": "frame"}],
        )

    row = counterexample()
    with pytest.raises(CorrectiveInterventionError, match="not evaluator-owned"):
        build_failure_packet(
            counterexample=row,
            source_role="development",
            scene_id="scene",
            evaluator_id="evaluator",
            branch_step=1,
            branch_state_sha256=DIGEST_D,
            first_divergence_step=1,
            failure_code="invented_failure",
            failure_phase="pregrasp",
            consequences={"error": 1.0},
            observations=[{"kind": "wrist_rgb", "artifact_sha256": DIGEST_E, "description": "frame"}],
        )


@pytest.mark.parametrize("source_role", ["held_out", "physical", "physical_read_only"])
def test_failure_packet_rejects_non_training_roles(source_role: str) -> None:
    value = failure_packet()
    value["source_role"] = source_role
    with pytest.raises(CorrectiveInterventionError, match="held-out or physical"):
        validate_failure_packet(value)


@pytest.mark.parametrize("kind", ["evaluator_privileged_state", "integration_state", "hidden_seed"])
def test_failure_packet_rejects_privileged_observations(kind: str) -> None:
    value = failure_packet()
    value["observations"][0]["kind"] = kind
    with pytest.raises(CorrectiveInterventionError, match="privileged"):
        validate_failure_packet(value)


def test_failure_packet_rejects_unknown_identity() -> None:
    value = failure_packet()
    value["identities"]["checkpoint_path"] = "/secret/checkpoint"
    with pytest.raises(CorrectiveInterventionError, match="keys differ"):
        validate_failure_packet(value)


def test_proposal_rejects_raw_joint_delta_surface() -> None:
    value = proposal()
    value["waypoints"][0]["joint_delta_rad"] = [0.0] * 6
    with pytest.raises(CorrectiveInterventionError, match="keys differ"):
        validate_intervention_proposal(value)


@pytest.mark.parametrize(
    ("field", "invalid", "message"),
    [
        ("translation_delta_m", [0.011, 0.0, 0.0], "10 mm"),
        ("rotation_delta_axis_angle_rad", [0.16, 0.0, 0.0], "rotation"),
        ("gripper_delta_rad", 0.13, "gripper"),
        ("duration_s", 0.23, "align to 20 Hz"),
    ],
)
def test_proposal_rejects_unbounded_waypoints(field: str, invalid: object, message: str) -> None:
    value = proposal()
    value["waypoints"][0][field] = invalid
    with pytest.raises(CorrectiveInterventionError, match=message):
        validate_intervention_proposal(value)


def test_proposal_rejects_scientific_identity_mismatch() -> None:
    value = proposal()
    value["bindings"]["policy_id"] = "another-policy"
    with pytest.raises(CorrectiveInterventionError, match="scientific bindings mismatch"):
        validate_intervention_proposal(value, failure_packet=failure_packet())


def test_compiled_trajectory_rejects_joint_limit_rate_and_clipping() -> None:
    value = compiled_trajectory()
    value["actions_rad"][0][0] = 2.0
    with pytest.raises(CorrectiveInterventionError, match="exceeds bounds"):
        validate_compiled_trajectory(value)

    value = compiled_trajectory()
    value["actions_rad"][0][0] = 0.06
    with pytest.raises(CorrectiveInterventionError, match="rate limit"):
        validate_compiled_trajectory(value)

    value = compiled_trajectory()
    value["execution"]["no_clipping"] = False
    with pytest.raises(CorrectiveInterventionError, match="clipping"):
        validate_compiled_trajectory(value)


def test_compiled_trajectory_rejects_ik_and_llm_action_ownership() -> None:
    value = compiled_trajectory()
    value["diagnostics"]["maximum_ik_residual_m"] = 0.0031
    with pytest.raises(CorrectiveInterventionError, match="3 mm"):
        validate_compiled_trajectory(value)


def test_real_mujoco_compiler_produces_bounded_pregrasp_actions() -> None:
    model = build_scene_spec(piece_layout=CURRENT_TASK_PIECE_LAYOUT).compile()
    data = mujoco.MjData(model)
    initialize_robot_poses(model, data)
    actuators = _actuator_map(model, "left")
    initial = [float(data.ctrl[actuators[joint]]) for joint in ROBOT_JOINTS]
    packet = failure_packet()
    value = proposal()
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
        initial_action_rad=initial,
    )
    assert len(compiled["actions_rad"]) == 5
    assert compiled["diagnostics"]["maximum_ik_residual_m"] <= 0.003
    assert compiled["authority"]["compiled_action_owner"] == "geometric_expert"


def test_compiler_rejects_contact_phase_and_orientation_change() -> None:
    model = build_scene_spec(piece_layout=CURRENT_TASK_PIECE_LAYOUT).compile()
    data = mujoco.MjData(model)
    initialize_robot_poses(model, data)
    actuators = _actuator_map(model, "left")
    initial = [float(data.ctrl[actuators[joint]]) for joint in ROBOT_JOINTS]

    packet = failure_packet()
    packet["failure"]["phase"] = "grasp_lift"
    packet["failure"]["code"] = "partial_contact"
    with pytest.raises(CorrectiveInterventionError, match="pregrasp"):
        compile_task_space_intervention(
            proposal(),
            failure_packet=packet,
            model=model,
            branch_data=data,
            selected_piece_body_name="tan_pawn_c8",
            target_rotation_world=np.eye(3),
            initial_action_rad=initial,
        )

    value = proposal()
    with pytest.raises(CorrectiveInterventionError, match="orientation-changing"):
        compile_task_space_intervention(
            value,
            failure_packet=failure_packet(),
            model=model,
            branch_data=data,
            selected_piece_body_name="tan_pawn_c8",
            target_rotation_world=np.eye(3),
            initial_action_rad=initial,
        )

    value = compiled_trajectory()
    value["authority"]["compiled_action_owner"] = "language_model"
    with pytest.raises(CorrectiveInterventionError, match="geometric_expert"):
        validate_compiled_trajectory(value)


def test_posterior_rejects_unsupported_unmeasured_and_broad_parameters() -> None:
    value = posterior()
    value["parameters"][0]["name"] = "magic_contact_quality"
    with pytest.raises(CorrectiveInterventionError, match="unsupported"):
        validate_robustness_posterior(value)

    value = posterior()
    value["parameters"][0]["evidence_sha256"] = DIGEST_C
    with pytest.raises(CorrectiveInterventionError, match="lacks declared source evidence"):
        validate_robustness_posterior(value)

    value = posterior()
    value["parameters"][0].update({"lower": -0.02, "upper": 0.02, "nominal": 0.0})
    with pytest.raises(CorrectiveInterventionError, match="too broad"):
        validate_robustness_posterior(value)


def test_posterior_rejects_seed_leakage_and_authority() -> None:
    value = posterior()
    value["sealed_seeds"][0] = value["development_seeds"][0]
    with pytest.raises(CorrectiveInterventionError, match="overlap"):
        validate_robustness_posterior(value)

    value = posterior()
    value["authority"]["visible_to_proposer"] = True
    with pytest.raises(CorrectiveInterventionError, match="visible_to_proposer"):
        validate_robustness_posterior(value)


def test_proposal_score_cannot_relabel_reward_as_admission_or_promotion() -> None:
    value = proposal_score()
    value["authority"]["policy_reward_is_proposal_score"] = True
    with pytest.raises(CorrectiveInterventionError, match="must remain separate"):
        validate_proposal_score(value)

    value = proposal_score()
    value["decision"]["training_admitted"] = True
    with pytest.raises(CorrectiveInterventionError, match="cannot admit"):
        validate_proposal_score(value)

    value = proposal_score()
    value["decision"]["promoted"] = True
    with pytest.raises(CorrectiveInterventionError, match="cannot promote"):
        validate_proposal_score(value)


def test_proposal_score_recomputes_robustness_and_candidate_decision() -> None:
    value = proposal_score()
    value["robustness"]["success_count"] = 11
    with pytest.raises(CorrectiveInterventionError, match="threshold flag"):
        validate_proposal_score(value)

    value = proposal_score()
    value["nominal"]["strict_success"] = False
    with pytest.raises(CorrectiveInterventionError, match="candidate decision"):
        validate_proposal_score(value)

from __future__ import annotations

import json
from pathlib import Path

import mujoco
import numpy as np
import pytest

from sim2claw.corrective_intervention import CorrectiveInterventionError, compile_task_space_intervention
from sim2claw.corrective_intervention_lf import build_correction_submission, materialize_correction_evidence
from sim2claw.corrective_intervention_runtime import capture_branch_state
from sim2claw.grasp import _actuator_map
from sim2claw.scene import CURRENT_TASK_PIECE_LAYOUT, ROBOT_JOINTS, build_scene_spec, initialize_robot_poses
from sim2claw.source_episode import sha256_file
from sim2claw.learning_factory_recursion import _validate_llm_compiled_intervention_rows


DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64


def _fixture() -> tuple[dict, dict, dict]:
    model = build_scene_spec(piece_layout=CURRENT_TASK_PIECE_LAYOUT).compile()
    data = mujoco.MjData(model)
    initialize_robot_poses(model, data)
    actuators = _actuator_map(model, "left")
    action = [float(data.ctrl[actuators[joint]]) for joint in ROBOT_JOINTS]
    state = capture_branch_state(model, data, scene_id="scene-100mm-v1", initial_action_rad=action)
    packet = {
        "schema_version": "sim2claw.corrective_failure_packet.v1",
        "counterexample_id": "counterexample-centering-001",
        "source_role": "development",
        "proof_class": "simulation",
        "identities": {
            "dataset_sha256": DIGEST_A,
            "policy_id": "policy-dev-001",
            "scene_id": "scene-100mm-v1",
            "evaluator_id": "evaluator-v1",
            "action_trace_sha256": DIGEST_B,
        },
        "branch": {"step": 10, "integration_state_sha256": state["artifact_sha256"]},
        "observations": [{"kind": "wrist_rgb", "artifact_sha256": DIGEST_C, "description": "branch frame"}],
        "failure": {
            "code": "pregrasp_lateral_offset",
            "phase": "pregrasp",
            "first_divergence_step": 10,
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
    proposal = {
        "schema_version": "sim2claw.corrective_intervention_proposal.v1",
        "proposal_id": "proposal-centering-001",
        "counterexample_id": packet["counterexample_id"],
        "branch_state_sha256": state["artifact_sha256"],
        "bindings": packet["identities"],
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
                "expected_effect": "raise pregrasp by one millimeter",
            }
        ],
        "expected_consequences": {"lateral_error_m": 0.002},
        "confidence": 0.7,
        "abstain": False,
    }
    compiled = compile_task_space_intervention(
        proposal,
        failure_packet=packet,
        model=model,
        branch_data=data,
        selected_piece_body_name="tan_pawn_c8",
        target_rotation_world=np.eye(3),
        initial_action_rad=action,
    )
    parent = {
        "counterexample_id": packet["counterexample_id"],
        "action_trace_sha256": DIGEST_B,
        "route_targets": ["LF-09"],
        "training_rows_authorized": 0,
    }
    return parent, state, {"proposal": proposal, "compiled": compiled}


def test_materialized_evidence_preserves_llm_proposal_but_geometric_action_owner(tmp_path: Path) -> None:
    parent, state, values = _fixture()
    evidence = materialize_correction_evidence(
        tmp_path / "evidence",
        parent_counterexample=parent,
        start_sample_index=10,
        branch_state=state,
        proposal=values["proposal"],
        compiled_trajectory=values["compiled"],
    )
    intervention = json.loads(Path(evidence["intervention"]["path"]).read_text(encoding="utf-8"))
    failed_prefix = json.loads(Path(evidence["failed_prefix"]["path"]).read_text(encoding="utf-8"))
    assert intervention["owner"] == "geometric_expert"
    assert intervention["llm_direct_control"] is False
    assert intervention["compiled_action_count"] == 5
    assert failed_prefix["training_rows_authorized"] == 0
    for name in ("failed_prefix", "pre_failure_integration_state", "intervention", "proposal", "compiled_trajectory"):
        assert sha256_file(Path(evidence[name]["path"])) == evidence[name]["sha256"]


def test_submission_waits_for_real_episode_and_independent_verdict(tmp_path: Path) -> None:
    parent, state, values = _fixture()
    evidence = materialize_correction_evidence(
        tmp_path / "evidence",
        parent_counterexample=parent,
        start_sample_index=10,
        branch_state=state,
        proposal=values["proposal"],
        compiled_trajectory=values["compiled"],
    )
    with pytest.raises(CorrectiveInterventionError, match="episode directory"):
        build_correction_submission(
            correction_candidate_id="correction-001",
            evidence=evidence,
            corrective_episode_directory=tmp_path / "missing-episode",
            admission_verdict_path=tmp_path / "missing-verdict.json",
        )

    episode = tmp_path / "episode"
    episode.mkdir()
    verdict = tmp_path / "verdict.json"
    verdict.write_text("{}", encoding="utf-8")
    submission = build_correction_submission(
        correction_candidate_id="correction-001",
        evidence=evidence,
        corrective_episode_directory=episode,
        admission_verdict_path=verdict,
    )
    assert submission["schema_version"] == "sim2claw.factory_correction_candidate.v1"
    assert "proposal" not in submission
    assert submission["intervention"]["sha256"] == evidence["intervention"]["sha256"]


def test_lf_row_binding_rejects_compiled_action_or_marker_mismatch(tmp_path: Path) -> None:
    parent, state, values = _fixture()
    evidence = materialize_correction_evidence(
        tmp_path / "evidence",
        parent_counterexample=parent,
        start_sample_index=2,
        branch_state=state,
        proposal=values["proposal"],
        compiled_trajectory=values["compiled"],
    )
    intervention = json.loads(
        Path(evidence["intervention"]["path"]).read_text(encoding="utf-8")
    )
    prefix = [
        {"action": {"joint_target_rad": [0.0] * 6, "owner": "learned_policy", "intervention": 0}}
        for _ in range(2)
    ]
    intervention_rows = [
        {
            "action": {
                "joint_target_rad": action,
                "owner": "geometric_expert",
                "intervention": 1,
            }
        }
        for action in values["compiled"]["actions_rad"]
    ]
    source_rows = prefix + intervention_rows
    _validate_llm_compiled_intervention_rows(
        intervention,
        source_rows=source_rows,
        suffix_start=2,
        suffix_end=len(source_rows),
    )

    changed = json.loads(json.dumps(source_rows))
    changed[2]["action"]["joint_target_rad"][0] += 0.001
    with pytest.raises(ValueError, match="differ from corrective episode"):
        _validate_llm_compiled_intervention_rows(
            intervention,
            source_rows=changed,
            suffix_start=2,
            suffix_end=len(changed),
        )

    changed = json.loads(json.dumps(source_rows))
    changed[2]["action"]["intervention"] = 0
    with pytest.raises(ValueError, match="ownership or marker"):
        _validate_llm_compiled_intervention_rows(
            intervention,
            source_rows=changed,
            suffix_start=2,
            suffix_end=len(changed),
        )

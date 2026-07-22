from __future__ import annotations

import copy

import pytest

from sim2claw.policy_flywheel import (
    compile_groot_challenger_disposition,
    validate_generation_lineage,
)
from sim2claw.sail.contracts import seal_contract
from sim2claw.sail.twin_worthiness import issue_capability_certificate


def _context_and_lineage() -> tuple[dict, dict]:
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
            "certificate_id": "flywheel-data-fixture",
            "campaign_id": "flywheel-fixture",
            "identities": identities,
            "gates": {
                f"TW-G{index}": {
                    "status": "pass" if index <= 2 else "not_evaluable",
                    "reason": "synthetic flywheel fixture",
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
        "twin_id": "synthetic-flywheel-twin-v1",
        "workcell_id": "synthetic-flywheel-workcell-v1",
        "task_id": "chess_pick_place_act_state_v1",
        "distribution_id": "synthetic-flywheel-distribution-v1",
        "task_contract_sha256": "1" * 64,
        "distribution_sha256": "2" * 64,
    }
    certificate = issue_capability_certificate(
        base_certificate=base,
        scope=scope,
        not_before="2026-07-22T00:00:00Z",
        expires_at="2027-07-22T00:00:00Z",
        issuance_request={
            "issuer_owner": "deterministic_sail_evaluator",
            "request_id": "flywheel-data-fixture",
        },
    )
    context = {
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
    lineage = {
        "schema_version": "sim2claw.policy_flywheel_generation_lineage.v1",
        "source_segment_representation": "object_and_target_relative",
        "posterior": {
            "artifact_sha256": identities["posterior"],
            "posterior_digest": "3" * 64,
            "eligible_particle_ids": ["particle-a", "particle-b"],
            "sampling_policy": "identified_posterior_only",
            "arbitrary_domain_randomization": False,
            "physical_parameter_claim": False,
        },
        "teacher": {
            "teacher_id": "fixture-geometric-expert-v1",
            "action_owner": "geometric_expert",
            "admission_authority": False,
        },
        "simulator": {
            "simulator_id": "fixture-mujoco-v1",
            "implementation_sha256": identities["simulator"],
        },
        "task_distribution": {
            "task_id": scope["task_id"],
            "task_contract_sha256": scope["task_contract_sha256"],
            "distribution_id": scope["distribution_id"],
            "distribution_sha256": scope["distribution_sha256"],
        },
        "policy_modalities": {
            "act_policy_inputs": ["state_goal"],
            "groot_policy_camera_ids": ["overhead"],
            "evaluator_only_camera_ids": ["wrist"],
            "wrist_is_main_policy_input": False,
        },
        "physical_authority": False,
    }
    return context, lineage


def test_generation_lineage_binds_exact_posterior_teacher_simulator_and_scope() -> None:
    context, lineage = _context_and_lineage()
    validated = validate_generation_lineage(
        lineage,
        twin_capability_context=context,
        parent_twin_id="synthetic-flywheel-twin-v1",
        task_id="chess_pick_place_act_state_v1",
        task_contract_sha256="1" * 64,
    )
    assert len(validated["lineage_digest"]) == 64
    assert validated["posterior"]["eligible_particle_ids"] == [
        "particle-a",
        "particle-b",
    ]
    assert validated["teacher"]["admission_authority"] is False
    assert validated["physical_authority"] is False


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda row: row["posterior"].update(
                {"arbitrary_domain_randomization": True}
            ),
            "domain randomization",
        ),
        (
            lambda row: row["posterior"].update({"artifact_sha256": "0" * 64}),
            "certified posterior",
        ),
        (
            lambda row: row["teacher"].update({"admission_authority": True}),
            "cannot admit",
        ),
        (
            lambda row: row["policy_modalities"].update(
                {"groot_policy_camera_ids": ["overhead", "wrist"]}
            ),
            "overhead-only",
        ),
    ],
)
def test_generation_lineage_fails_closed_on_widening(mutation, message: str) -> None:
    context, lineage = _context_and_lineage()
    mutation(lineage)
    with pytest.raises(ValueError, match=message):
        validate_generation_lineage(
            lineage,
            twin_capability_context=context,
            parent_twin_id="synthetic-flywheel-twin-v1",
            task_id="chess_pick_place_act_state_v1",
            task_contract_sha256="1" * 64,
        )


def test_groot_challenger_skip_is_explicit_overhead_only_and_non_authoritative() -> None:
    receipt = {
        "dataset_sha256": "4" * 64,
        "groot_payload": {"sha256": "5" * 64, "row_count": 12},
    }
    declaration = {
        "mode": "deterministic_skip",
        "compute_available": False,
        "reason": "no_compatible_local_groot_runtime_or_authorized_bounded_compute",
        "policy_camera_ids": ["overhead"],
        "evaluator_only_camera_ids": ["wrist"],
    }
    result = compile_groot_challenger_disposition(receipt, declaration)
    assert result["status"] == "skipped_compute_unavailable"
    assert result["policy_camera_ids"] == ["overhead"]
    assert result["wrist_main_policy_input"] is False
    assert result["training_invoked"] is False
    assert result["policy_comparison_published"] is False
    assert result["physical_authority"] is False

    changed = copy.deepcopy(declaration)
    changed["policy_camera_ids"].append("wrist")
    with pytest.raises(ValueError, match="overhead-only"):
        compile_groot_challenger_disposition(receipt, changed)

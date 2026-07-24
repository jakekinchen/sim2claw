from __future__ import annotations

import copy
from pathlib import Path

import pytest

from sim2claw.actuator_external_validation import (
    ActuatorExternalValidationError,
    _load_hash_bound_json,
    evaluate_external_replays,
    load_external_episode_payloads,
    load_external_validation_contract,
    validate_external_validation_contract,
)
from sim2claw.cli import build_parser
from sim2claw.learning_factory_artifacts import sha256_file
from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_timing_ablation import BODY_JOINT_NAMES


EXTERNAL_ROOT = REPO_ROOT / "datasets" / "act_source_recordings"


def _metrics(*, sample_count: int, joint_rms: float, ee_rms: float) -> dict:
    joint_sse = sample_count * joint_rms**2
    return {
        "sample_count": sample_count,
        "joint_squared_error_degrees": [joint_sse] * 5,
        "per_joint_rms_degrees": {
            name: joint_rms for name in BODY_JOINT_NAMES
        },
        "overall_joint_rms_degrees": joint_rms,
        "ee_squared_error_m2": sample_count * ee_rms**2,
        "ee_rms_m": ee_rms,
        "ee_max_m": ee_rms,
        "stall_rows": {name: 0 for name in BODY_JOINT_NAMES},
        "stall_reproduced": {name: 0 for name in BODY_JOINT_NAMES},
    }


def _raw_result(
    contract: dict,
    *,
    contract_sha256: str,
    candidate_joint_rms: float = 0.9,
    candidate_ee_rms: float = 0.9,
) -> dict:
    episodes = []
    for index, manifest in enumerate(
        contract["external_evaluation"]["expected_episode_manifest"]
    ):
        sample_count = int(manifest["sample_count"])
        action_sha256 = f"{index + 1:064x}"
        variants = {}
        for variant_index, name in enumerate(("baseline", "candidate")):
            joint_rms = 1.0 if name == "baseline" else candidate_joint_rms
            ee_rms = 1.0 if name == "baseline" else candidate_ee_rms
            variants[name] = {
                "variant_id": contract["variants"][name]["variant_id"],
                "parameters": {
                    "shoulder_lift_deadband_degrees": float(
                        contract["variants"][name][
                            "shoulder_lift_deadband_degrees"
                        ]
                    ),
                    "elbow_flex_deadband_degrees": float(
                        contract["variants"][name]["elbow_flex_deadband_degrees"]
                    ),
                    "elbow_load_bias_coefficient": float(
                        contract["variants"][name]["elbow_load_bias_coefficient"]
                    ),
                },
                "action_sha256": action_sha256,
                "action_shape": [sample_count, 6],
                "action_dtype": "float64",
                "clipped_action_rows": 0,
                "schedule_sha256": f"{index * 2 + variant_index + 11:064x}",
                "load_response": {},
                "metrics": _metrics(
                    sample_count=sample_count,
                    joint_rms=joint_rms,
                    ee_rms=ee_rms,
                ),
            }
        episodes.append(
            {
                "recording_id": manifest["recording_id"],
                "metadata_status": "historical_unknown",
                "samples_sha256": manifest["samples_sha256"],
                "historical_replay_receipt_sha256": manifest[
                    "historical_replay_receipt_sha256"
                ],
                "historical_state_trace_sha256": manifest[
                    "historical_state_trace_sha256"
                ],
                "variants": variants,
            }
        )
    return {
        "schema_version": "sim2claw.pawn_actuator_external_validation_raw.v1",
        "validation_id": contract["validation_id"],
        "contract_sha256": contract_sha256,
        "proof_class": contract["proof_boundary"]["external_proof_class"],
        "candidate_runner_score_authority": False,
        "candidate_runner_promotion_authority": False,
        "inventory": {
            "episode_count": 5,
            "sample_count": 2186,
            "ledger_sha256": contract["external_evaluation"]["intake_ledger"][
                "sha256"
            ],
        },
        "budget": {
            "simulator_replays_used": 10,
            "retries_used": 0,
            "provider_calls_used": 0,
        },
        "episodes": episodes,
    }


def _task_receipt(contract: dict) -> dict:
    return {
        "proof_class": contract["proof_boundary"]["selection_proof_class"],
        "target_piece_consequence_comparison": {
            "current_baseline": {
                "episode_count": 11,
                "task_consequence_successes": 0,
            },
            "selected_load_bias": {
                "episode_count": 11,
                "task_consequence_successes": 0,
            },
            "verified_grasp_or_task_advancement": False,
        },
    }


def test_contract_freezes_external_cohort_budget_thresholds_and_authority() -> None:
    contract = load_external_validation_contract()

    assert len(contract["external_evaluation"]["expected_episode_manifest"]) == 5
    assert sum(
        row["sample_count"]
        for row in contract["external_evaluation"]["expected_episode_manifest"]
    ) == 2186
    assert contract["budget"]["maximum_simulator_replays"] == 10
    assert contract["budget"]["maximum_retries"] == 0
    assert contract["variants"]["post_result_family_expansion_allowed"] is False
    assert not any(contract["authority"].values())


def test_cli_exposes_bounded_external_validation_command() -> None:
    args = build_parser().parse_args(
        ["actuator-external-validate", "--output", "outputs/example"]
    )
    assert args.command == "actuator-external-validate"
    assert args.output == Path("outputs/example")


def test_evaluator_accepts_material_effect_and_is_byte_deterministic() -> None:
    contract = load_external_validation_contract()
    contract_sha256 = sha256_file(
        REPO_ROOT
        / "configs"
        / "evaluations"
        / "pawn_actuator_external_validation_v1.json"
    )
    raw = _raw_result(contract, contract_sha256=contract_sha256)
    task = _task_receipt(contract)

    first = evaluate_external_replays(
        raw,
        contract,
        contract_sha256=contract_sha256,
        task_receipt=task,
    )
    second = evaluate_external_replays(
        raw,
        contract,
        contract_sha256=contract_sha256,
        task_receipt=task,
    )

    assert first == second
    assert first["external_trace_validation_passed"] is True
    assert first["pooled"]["improved_episode_count"] == 5
    assert first["task_completion_score_changed"] is False
    assert first["parameters_promoted"] is False


def test_evaluator_reports_honest_negative_without_changing_task_score() -> None:
    contract = load_external_validation_contract()
    contract_sha256 = "a" * 64
    raw = _raw_result(
        contract,
        contract_sha256=contract_sha256,
        candidate_joint_rms=0.995,
        candidate_ee_rms=1.001,
    )

    result = evaluate_external_replays(
        raw,
        contract,
        contract_sha256=contract_sha256,
        task_receipt=_task_receipt(contract),
    )

    assert result["external_trace_validation_passed"] is False
    assert result["verdict"] == (
        "external_trace_validation_reject_task_completion_unchanged"
    )
    assert result["task_completion_score_changed"] is False


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda raw: raw["episodes"][0]["variants"]["candidate"].__setitem__(
                "action_sha256", "f" * 64
            ),
            "action substitution",
        ),
        (
            lambda raw: raw["episodes"].__setitem__(
                1, copy.deepcopy(raw["episodes"][0])
            ),
            "replays an episode twice",
        ),
        (
            lambda raw: raw.__setitem__("contract_sha256", "b" * 64),
            "not bound",
        ),
        (
            lambda raw: raw["episodes"][0]["variants"]["candidate"].__setitem__(
                "verdict", "pass"
            ),
            "self-score",
        ),
        (
            lambda raw: raw["episodes"][0].__setitem__(
                "samples_sha256", "c" * 64
            ),
            "source manifest drifted",
        ),
        (
            lambda raw: raw["episodes"][0]["variants"]["candidate"]["metrics"].__setitem__(
                "overall_joint_rms_degrees", 0.01
            ),
            "joint RMS is inconsistent",
        ),
    ],
)
def test_evaluator_rejects_action_replay_contract_scoring_and_metric_tampering(
    mutation,
    message: str,
) -> None:
    contract = load_external_validation_contract()
    contract_sha256 = "a" * 64
    raw = _raw_result(contract, contract_sha256=contract_sha256)
    mutation(raw)

    with pytest.raises(ActuatorExternalValidationError, match=message):
        evaluate_external_replays(
            raw,
            contract,
            contract_sha256=contract_sha256,
            task_receipt=_task_receipt(contract),
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda contract: contract["budget"].__setitem__(
            "maximum_simulator_replays", 11
        ),
        lambda contract: contract["evaluator"].__setitem__(
            "minimum_pooled_joint_rms_relative_improvement", 0.0
        ),
        lambda contract: contract["variants"]["candidate"].__setitem__(
            "elbow_load_bias_coefficient", -2.0
        ),
        lambda contract: contract["authority"].__setitem__("promotion", True),
    ],
)
def test_contract_rejects_posthoc_budget_threshold_candidate_or_authority_change(
    mutation,
) -> None:
    contract = load_external_validation_contract()
    mutation(contract)

    with pytest.raises(ActuatorExternalValidationError):
        validate_external_validation_contract(contract)


def test_task_receipt_cannot_self_upgrade_task_evidence() -> None:
    contract = load_external_validation_contract()
    contract_sha256 = "a" * 64
    task = _task_receipt(contract)
    task["target_piece_consequence_comparison"][
        "verified_grasp_or_task_advancement"
    ] = True

    with pytest.raises(ActuatorExternalValidationError, match="claims"):
        evaluate_external_replays(
            _raw_result(contract, contract_sha256=contract_sha256),
            contract,
            contract_sha256=contract_sha256,
            task_receipt=task,
        )


@pytest.mark.skipif(
    not EXTERNAL_ROOT.is_dir(),
    reason="hash-bound external recordings are unavailable",
)
def test_live_external_sources_hash_bind_and_map_without_replay() -> None:
    contract = load_external_validation_contract()
    _, selection_receipt = _load_hash_bound_json(
        contract["selection_evidence"]["servo_load_bias_receipt"],
        repo_root=REPO_ROOT,
        require_digest=True,
    )

    payloads, _, inventory = load_external_episode_payloads(
        contract,
        selection_receipt,
    )

    assert inventory["episode_count"] == 5
    assert inventory["sample_count"] == 2186
    assert sum(len(row["mapped"]["actions"]) for row in payloads) == 2186
    assert all(row["mapped"]["action_receipt"]["clipped_rows"] == 0 for row in payloads)

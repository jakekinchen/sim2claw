from __future__ import annotations

import copy
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

import sim2claw.sail.live_adapters as live_adapters
from sim2claw.learning_factory_artifacts import (
    canonical_digest,
    sha256_file,
)
from sim2claw.sail.c2_trusted_adapter import (
    ADAPTER_ID,
    REQUEST_SCHEMA,
    build_c2_adapter_request,
    compile_c2_adapter_request,
    execute_c2_adapter_request,
    verify_c2_adapter_receipt,
)
from sim2claw.sail.live_contracts import load_live_campaign_contract
from sim2claw.sail.live_decision import rank_live_acquisition
from sim2claw.sail.live_operator import run_live_operator
from sim2claw.sail.live_receipts import (
    build_live_evaluator_identity,
    verify_live_operator_receipt,
)
from sim2claw.sail.live_types import LiveOperatorError


REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_CONFIG = REPO_ROOT / "configs/sail/live_operator_c2_adapter_v1.json"
ADAPTER_CONTRACT = REPO_ROOT / "configs/sail/c2_trusted_adapter_v1.json"
C2_TRACE = (
    REPO_ROOT / "outputs/sail/project-application-v1/c2-v3-retention-trace.json"
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _contract_and_selected() -> tuple[Any, dict[str, Any]]:
    contract = load_live_campaign_contract(LIVE_CONFIG)
    ranking = rank_live_acquisition(
        hypotheses=contract.hypothesis_priors,
        candidates=[row.payload for row in contract.interventions],
        weights=contract.payload["acquisition"]["weights"],
    )
    selected = next(
        row.payload
        for row in contract.interventions
        if row.intervention_id == ranking["selected_intervention"]
    )
    return contract, selected


def _request() -> tuple[Any, dict[str, Any], dict[str, Any]]:
    contract, selected = _contract_and_selected()
    request = build_c2_adapter_request(
        contract=contract,
        selected_intervention=selected,
        adapter_contract_path=ADAPTER_CONTRACT,
        evaluator_identity=build_live_evaluator_identity(contract),
        authority=contract.payload["authority"],
    )
    return contract, selected, request


def _fake_runner(**kwargs: Any) -> dict[str, Any]:
    episode = copy.deepcopy(_load(C2_TRACE)["episode"])
    parameters = copy.deepcopy(kwargs["parameters"])
    unsigned = {
        "schema_version": "sim2claw.pawn_bg_grasp_episode_probe.v1",
        "created_at": "2026-07-23T11:15:00-05:00",
        "proof_class": "action_frozen_simulator_mechanism_diagnostic",
        "recording_id": kwargs["recording_id"],
        "parameters": parameters,
        "parameter_digest": canonical_digest(parameters),
        "contract": {"path": "test-bound-runner", "sha256": "a" * 64},
        "implementation": {"path": "test-bound-runner", "sha256": "b" * 64},
        "stage_d_parameters": {},
        "episode": episode,
        "authority": {
            "physical_capture": False,
            "robot_motion": False,
            "training": False,
            "self_promotion": False,
        },
        "claim_boundary": "synthetic test double for the action-frozen runner",
    }
    return {**unsigned, "receipt_digest": canonical_digest(unsigned)}


def _execute(
    tmp_path: Path,
    *,
    runner: Any = _fake_runner,
    remaining_anchor_replays: int = 4,
) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    contract, selected, request = _request()
    admission = execute_c2_adapter_request(
        request,
        contract=contract,
        selected_intervention=selected,
        affected_factor_ids=[
            "factor:actuator_load_path",
            "factor:rubber_contact_patch",
        ],
        expected_evaluator_identity=build_live_evaluator_identity(contract),
        remaining_anchor_replays=remaining_anchor_replays,
        output_root=tmp_path / "operator" / "trusted_adapter",
        prior_execution_ids=[],
        prior_anchor_replay_ids=[],
        episode_runner=runner,
    )
    return contract, selected, admission


def test_live_contract_selects_the_single_preregistered_simulator_family() -> None:
    contract, selected = _contract_and_selected()
    assert contract.action_sha256 == (
        "402a29e4cdc0c4cb90d41a83327ad8df5685544851b4e4d659129b3239744fd6"
    )
    assert selected["intervention_id"] == "simulator_preregistered_c2_factorial"
    assert selected["maximum_trials"] == 4
    assert selected["trusted_adapter"]["adapter_id"] == ADAPTER_ID
    assert len(live_adapters._NON_FIXTURE_TRUSTED_ADAPTERS) == 1
    assert set(live_adapters._NON_FIXTURE_TRUSTED_ADAPTERS) == {ADAPTER_ID}


def test_result_free_request_has_no_fixture_or_caller_result_values(
    tmp_path: Path,
) -> None:
    output = tmp_path / "request.json"
    compiled = compile_c2_adapter_request(
        LIVE_CONFIG,
        adapter_contract_path=ADAPTER_CONTRACT,
        output_path=output,
    )
    request = _load(output)
    assert request["schema_version"] == REQUEST_SCHEMA
    assert "fixture" not in request
    assert "result" not in request
    assert "consequence" not in request
    assert request["action_sha256"] == (
        "402a29e4cdc0c4cb90d41a83327ad8df5685544851b4e4d659129b3239744fd6"
    )
    assert compiled["status"] == "preregistered_not_executed"
    assert compiled["candidate_count"] == 4
    assert compiled["anchor_replays_used"] == 0


def test_adapter_owns_four_mutations_and_preserves_prior_on_rejection(
    tmp_path: Path,
) -> None:
    _contract, _selected, admission = _execute(tmp_path)
    assert len(admission["anchor_replay_ids"]) == 4
    assert len(admission["raw_artifacts"]) == 4
    assert admission["consequence"]["evaluator_passed"] is False
    assert admission["consequence"]["posterior_movement_permitted"] is False
    assert admission["result"]["hypothesis_likelihoods"] == {
        "actuator_load_path_v1": 1.0,
        "flexural_rubber_contact_v1": 1.0,
    }
    assert admission["result"]["factor_updates"] == {}
    assert admission["receipt"]["budget"] == {
        "interventions": 1,
        "anchor_replays": 4,
        "measurement_trials": 0,
        "provider_calls": 0,
    }
    assert all(
        row["anchor_evaluation"]["action_sha256"]
        == "402a29e4cdc0c4cb90d41a83327ad8df5685544851b4e4d659129b3239744fd6"
        for row in _load(
            tmp_path / "operator" / "trusted_adapter" / "evaluation.json"
        )["candidate_results"]
    )


def test_budget_rejects_before_any_runner_call(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    def runner(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return _fake_runner(**kwargs)

    with pytest.raises(LiveOperatorError, match="remaining anchor replay budget"):
        _execute(tmp_path, runner=runner, remaining_anchor_replays=3)
    assert calls == []
    assert not (tmp_path / "operator" / "trusted_adapter").exists()


def test_action_mutation_is_rejected(tmp_path: Path) -> None:
    def runner(**kwargs: Any) -> dict[str, Any]:
        raw = _fake_runner(**kwargs)
        raw["episode"]["action_array_sha256"] = "f" * 64
        raw.pop("receipt_digest")
        raw["receipt_digest"] = canonical_digest(raw)
        return raw

    with pytest.raises(LiveOperatorError, match="raw simulator identity changed"):
        _execute(tmp_path, runner=runner)


def test_request_with_result_or_source_substitution_is_rejected(
    tmp_path: Path,
) -> None:
    contract, selected, request = _request()
    request["result"] = {"evaluator_passed": True}
    request.pop("request_digest")
    request["request_digest"] = canonical_digest(request)
    with pytest.raises(LiveOperatorError, match="field set changed"):
        execute_c2_adapter_request(
            request,
            contract=contract,
            selected_intervention=selected,
            affected_factor_ids=[
                "factor:actuator_load_path",
                "factor:rubber_contact_patch",
            ],
            expected_evaluator_identity=build_live_evaluator_identity(contract),
            remaining_anchor_replays=4,
            output_root=tmp_path,
            prior_execution_ids=[],
            prior_anchor_replay_ids=[],
            episode_runner=_fake_runner,
        )


def test_receipt_is_independently_rederived_and_rejects_tampering(
    tmp_path: Path,
) -> None:
    contract, selected, admission = _execute(tmp_path)
    summary = {
        "adapter_id": admission["adapter_id"],
        "adapter_identity": admission["adapter_identity"],
        "adapter_receipt": admission["receipt"],
        "receipt_sha256": admission["receipt_sha256"],
        "raw_artifacts": admission["raw_artifacts"],
        "result_artifact": admission["result_artifact"],
    }
    verify_c2_adapter_receipt(
        summary,
        contract=contract,
        selected_intervention=selected,
        expected_evaluator_identity=build_live_evaluator_identity(contract),
        expected_consequence=admission["consequence"],
        expected_affected_factor_ids=[
            "factor:actuator_load_path",
            "factor:rubber_contact_patch",
        ],
        receipt_root=tmp_path / "operator",
        repo_root=REPO_ROOT,
    )
    evaluation_path = (
        tmp_path / "operator" / "trusted_adapter" / "evaluation.json"
    )
    evaluation = _load(evaluation_path)
    evaluation["consequence"]["evaluator_passed"] = True
    evaluation_path.write_text(
        json.dumps(evaluation, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(LiveOperatorError, match="evaluation was not rederived"):
        verify_c2_adapter_receipt(
            summary,
            contract=contract,
            selected_intervention=selected,
            expected_evaluator_identity=build_live_evaluator_identity(contract),
            expected_consequence=admission["consequence"],
            expected_affected_factor_ids=[
                "factor:actuator_load_path",
                "factor:rubber_contact_patch",
            ],
            receipt_root=tmp_path / "operator",
            repo_root=REPO_ROOT,
        )


def test_live_operator_consumes_non_fixture_adapter_receipt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _load(LIVE_CONFIG)
    config["campaign_id"] = (
        f"test-c2-adapter-{canonical_digest(str(tmp_path))[:12]}"
    )
    config_root = (
        REPO_ROOT
        / "outputs"
        / "sail"
        / "test-live-campaigns"
        / canonical_digest(str(tmp_path))
    )
    config_root.mkdir(parents=True, exist_ok=True)
    config_path = config_root / "campaign.json"
    config_path.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    contract = load_live_campaign_contract(config_path)
    selected = next(
        row.payload
        for row in contract.interventions
        if row.intervention_id == "simulator_preregistered_c2_factorial"
    )
    request = build_c2_adapter_request(
        contract=contract,
        selected_intervention=selected,
        adapter_contract_path=ADAPTER_CONTRACT,
        evaluator_identity=build_live_evaluator_identity(contract),
        authority=contract.payload["authority"],
    )
    request_path = config_root / "request.json"
    request_path.write_text(
        json.dumps(request, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    def handler(request: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return execute_c2_adapter_request(
            request, **kwargs, episode_runner=_fake_runner
        )

    monkeypatch.setattr(
        live_adapters,
        "_NON_FIXTURE_TRUSTED_ADAPTERS",
        MappingProxyType({ADAPTER_ID: handler}),
    )
    output = tmp_path / "live-operator"
    result = run_live_operator(
        config_path,
        output_root=output,
        trusted_adapter_request_path=request_path,
    )
    assert result["selected_intervention"] == (
        "simulator_preregistered_c2_factorial"
    )
    assert result["verdict"] == "evaluator_reject"
    assert result["budget"]["used_interventions"] == 1
    assert result["budget"]["used_anchor_replays"] == 4
    receipt = _load(output / "receipt.json")
    assert receipt["intervention_executor_implemented"] is True
    assert (
        _load(output / "operator_trace.json")[
            "intervention_executor_implemented"
        ]
        is True
    )
    verify_live_operator_receipt(output / "receipt.json")
    assert sha256_file(output / "trusted_adapter" / "receipt.json") == (
        _load(output / "admitted_evaluator_receipt.json")["receipt_sha256"]
    )

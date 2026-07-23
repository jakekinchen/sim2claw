"""Fail-closed trusted adapters that derive simulator evidence from raw fixtures."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence

import numpy as np

from ..learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    sha256_file,
)
from .contracts import REPO_ROOT
from .c2_trusted_adapter import (
    ADAPTER_ID as C2_ADAPTER_ID,
    REQUEST_SCHEMA as C2_REQUEST_SCHEMA,
    build_c2_adapter_request,
    execute_c2_adapter_request,
    verify_c2_adapter_receipt,
)
from .importers import load_json_object
from .live_evidence import json_artifact_sha256
from .live_types import LiveCampaignContract, LiveOperatorError


REQUEST_SCHEMA = "sim2claw.sail_trusted_adapter_request.v1"
FIXTURE_SCHEMA = "sim2claw.sail_trusted_adapter_fixture.v1"
ADAPTER_CONTRACT_SCHEMA = "sim2claw.sail_fixture_adapter_contract.v1"
RESULT_SCHEMA = "sim2claw.sail_trusted_adapter_result.v1"
RECEIPT_SCHEMA = "sim2claw.sail_trusted_adapter_receipt.v1"
FIXTURE_ADAPTER_ID = "fixture_deterministic_v1"
ADAPTER_IMPLEMENTATION_PATH = "src/sim2claw/sail/live_adapters.py"


class TrustedSimulatorAdapter(Protocol):
    adapter_id: str

    def execute(
        self,
        *,
        request: Mapping[str, Any],
        fixture: Mapping[str, Any],
        contract: LiveCampaignContract,
        selected_intervention: Mapping[str, Any],
        affected_factor_ids: Sequence[str],
        expected_evaluator_identity: Mapping[str, Any],
        output_root: Path,
        repo_root: Path,
    ) -> dict[str, Any]: ...


def _verify_digest(
    payload: Mapping[str, Any], *, field: str, label: str
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(payload))
    observed = normalized.pop(field, None)
    if observed != canonical_digest(normalized):
        raise LiveOperatorError(f"{label} digest mismatch")
    return {**normalized, field: str(observed)}


def _require_all_false(value: object, *, label: str) -> dict[str, bool]:
    if not isinstance(value, Mapping) or not value:
        raise LiveOperatorError(f"{label} authority is missing")
    if any(not isinstance(name, str) or not name for name in value):
        raise LiveOperatorError(f"{label} authority key is invalid")
    normalized = dict(value)
    if any(flag is not False for flag in normalized.values()):
        raise LiveOperatorError(f"{label} widened authority")
    return normalized


def _repo_file(
    binding: Mapping[str, Any], *, repo_root: Path, label: str
) -> Path:
    if set(binding) != {"path", "sha256"}:
        raise LiveOperatorError(f"{label} binding field set changed")
    if (
        not isinstance(binding["path"], str)
        or not binding["path"]
        or not isinstance(binding["sha256"], str)
        or len(binding["sha256"]) != 64
    ):
        raise LiveOperatorError(f"{label} binding value is invalid")
    raw = Path(binding["path"])
    root = repo_root.resolve()
    path = raw.resolve() if raw.is_absolute() else (root / raw).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise LiveOperatorError(f"{label} escaped the repository") from error
    if not path.is_file() or sha256_file(path) != str(binding["sha256"]):
        raise LiveOperatorError(f"{label} source identity changed")
    return path


def _finite_number(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LiveOperatorError(f"{label} is not a JSON number")
    normalized = float(value)
    if not np.isfinite(normalized):
        raise LiveOperatorError(f"{label} is non-finite")
    return normalized


def _adapter_contract(
    selected_intervention: Mapping[str, Any], *, adapter_id: str
) -> dict[str, Any]:
    payload = selected_intervention.get("trusted_adapter")
    if not isinstance(payload, Mapping):
        raise LiveOperatorError("selected intervention has no trusted adapter contract")
    normalized = copy.deepcopy(dict(payload))
    if set(normalized) != {
        "schema_version",
        "adapter_id",
        "mutation",
        "response",
        "evaluation",
    }:
        raise LiveOperatorError("trusted adapter contract field set changed")
    if (
        normalized["schema_version"] != ADAPTER_CONTRACT_SCHEMA
        or normalized["adapter_id"] != adapter_id
    ):
        raise LiveOperatorError("trusted adapter substitution rejected")
    mutation = normalized["mutation"]
    response = normalized["response"]
    evaluation = normalized["evaluation"]
    if not isinstance(mutation, Mapping) or set(mutation) != {
        "field",
        "operation",
        "value",
    }:
        raise LiveOperatorError("trusted adapter mutation contract changed")
    if mutation["operation"] not in {"add", "scale", "set"}:
        raise LiveOperatorError("trusted adapter mutation operation is invalid")
    if not isinstance(mutation["field"], str) or not mutation["field"]:
        raise LiveOperatorError("trusted adapter mutation field is invalid")
    if not isinstance(response, Mapping) or set(response) != {"operation", "fields"}:
        raise LiveOperatorError("trusted adapter response contract changed")
    response_fields = response["fields"]
    if (
        response["operation"] != "product"
        or not isinstance(response_fields, list)
        or len(response_fields) != 2
        or len(set(response_fields)) != 2
        or any(not isinstance(value, str) or not value for value in response_fields)
    ):
        raise LiveOperatorError("trusted adapter response operation is invalid")
    if not isinstance(evaluation, Mapping) or set(evaluation) != {
        "target",
        "pass_tolerance",
    }:
        raise LiveOperatorError("trusted adapter evaluation contract changed")
    _finite_number(mutation["value"], label="trusted adapter mutation value")
    target = _finite_number(
        evaluation["target"], label="trusted adapter evaluation target"
    )
    tolerance = _finite_number(
        evaluation["pass_tolerance"], label="trusted adapter pass tolerance"
    )
    if tolerance < 0.0:
        raise LiveOperatorError("trusted adapter tolerance is invalid")
    if not 0.0 <= target <= 1.0:
        raise LiveOperatorError("trusted adapter target is outside the response domain")
    return normalized


def _derive_fixture_evidence(
    *,
    fixture: Mapping[str, Any],
    adapter_contract: Mapping[str, Any],
    selected_intervention: Mapping[str, Any],
    affected_factor_ids: Sequence[str],
) -> dict[str, Any]:
    inputs = fixture.get("inputs")
    if not isinstance(inputs, Mapping) or not inputs:
        raise LiveOperatorError("trusted adapter fixture inputs are missing")
    values = {
        str(name): _finite_number(
            value, label=f"trusted adapter fixture input {name}"
        )
        for name, value in inputs.items()
    }

    mutation = adapter_contract["mutation"]
    field = str(mutation["field"])
    if field not in values:
        raise LiveOperatorError("trusted adapter mutation field is absent from fixture")
    before = values[field]
    operand = _finite_number(
        mutation["value"], label="trusted adapter mutation value"
    )
    if mutation["operation"] == "add":
        after = before + operand
    elif mutation["operation"] == "scale":
        after = before * operand
    else:
        after = operand
    if not np.isfinite(after):
        raise LiveOperatorError("trusted adapter mutation produced a non-finite value")
    values[field] = after

    response_fields = [str(value) for value in adapter_contract["response"]["fields"]]
    if any(name not in values for name in response_fields):
        raise LiveOperatorError("trusted adapter response field is absent from fixture")
    response = float(
        np.clip(np.prod([values[name] for name in response_fields]), 0.0, 1.0)
    )
    if not np.isfinite(response):
        raise LiveOperatorError("trusted adapter response is non-finite")
    evaluation = adapter_contract["evaluation"]
    target = _finite_number(
        evaluation["target"], label="trusted adapter evaluation target"
    )
    tolerance = _finite_number(
        evaluation["pass_tolerance"], label="trusted adapter pass tolerance"
    )
    passed = abs(response - target) <= tolerance

    likelihoods: dict[str, float] = {}
    for mechanism_id, signatures in selected_intervention[
        "predicted_signatures"
    ].items():
        predictions = [
            float(payload["normalized_response"])
            for payload in signatures.values()
        ]
        predicted = float(np.mean(predictions))
        likelihoods[str(mechanism_id)] = max(
            1e-6, 1.0 - abs(predicted - response)
        )
    consequence = {
        "status": "fixture_evaluator_pass" if passed else "fixture_evaluator_reject",
        "evaluator_passed": passed,
        "derived_response": response,
        "target": target,
        "pass_tolerance": tolerance,
        "promotion": False,
        "simulator_promotion": False,
        "training_admitted": False,
        "physical_authority": False,
        "robot_motion": False,
    }
    return {
        "actual_mutations": [
            {
                "field": field,
                "operation": mutation["operation"],
                "operand": operand,
                "before": before,
                "after": after,
            }
        ],
        "derived_response": response,
        "hypothesis_likelihoods": likelihoods,
        "factor_updates": {
            str(factor_id): response for factor_id in affected_factor_ids
        },
        "consequence": consequence,
    }


def _adapter_execution_id(
    *, adapter_id: str, request_digest: str, fixture_id: str
) -> str:
    return canonical_digest(
        {
            "adapter_id": adapter_id,
            "request_digest": request_digest,
            "fixture_id": fixture_id,
        }
    )
def build_trusted_adapter_request(
    *,
    adapter_id: str,
    contract: LiveCampaignContract,
    selected_intervention: Mapping[str, Any],
    fixture_path: Path,
    evaluator_identity: Mapping[str, Any],
    authority: Mapping[str, bool],
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Build a result-free request; mutation and evaluation stay config-owned."""

    normalized_authority = _require_all_false(
        authority, label="trusted adapter request"
    )
    if normalized_authority != contract.payload["authority"]:
        raise LiveOperatorError("trusted adapter request authority changed")
    try:
        fixture_relative = fixture_path.resolve().relative_to(repo_root.resolve())
    except ValueError as error:
        raise LiveOperatorError(
            "trusted adapter request fixture escaped the repository"
        ) from error
    fixture_binding = {
        "path": fixture_relative.as_posix(),
        "sha256": sha256_file(fixture_path),
    }
    _repo_file(
        fixture_binding,
        repo_root=repo_root,
        label="trusted adapter request fixture",
    )
    unsigned = {
        "schema_version": REQUEST_SCHEMA,
        "adapter_id": adapter_id,
        "campaign_id": contract.campaign_id,
        "config_digest": contract.config_digest,
        "selected_intervention": str(selected_intervention["intervention_id"]),
        "intervention_set_digest": contract.intervention_set_digest,
        "action_sha256": contract.action_sha256,
        "evaluator_identity": copy.deepcopy(dict(evaluator_identity)),
        "fixture": fixture_binding,
        "authority": copy.deepcopy(normalized_authority),
    }
    return {**unsigned, "request_digest": canonical_digest(unsigned)}


@dataclass(frozen=True)
class FixtureDeterministicAdapter:
    adapter_id: str = FIXTURE_ADAPTER_ID

    def execute(
        self,
        *,
        request: Mapping[str, Any],
        fixture: Mapping[str, Any],
        contract: LiveCampaignContract,
        selected_intervention: Mapping[str, Any],
        affected_factor_ids: Sequence[str],
        expected_evaluator_identity: Mapping[str, Any],
        output_root: Path,
        repo_root: Path,
    ) -> dict[str, Any]:
        adapter_contract = _adapter_contract(
            selected_intervention, adapter_id=self.adapter_id
        )
        derived = _derive_fixture_evidence(
            fixture=fixture,
            adapter_contract=adapter_contract,
            selected_intervention=selected_intervention,
            affected_factor_ids=affected_factor_ids,
        )
        execution_id = _adapter_execution_id(
            adapter_id=self.adapter_id,
            request_digest=str(request["request_digest"]),
            fixture_id=str(fixture["fixture_id"]),
        )
        result = {
            "schema_version": RESULT_SCHEMA,
            "campaign_id": contract.campaign_id,
            "selected_intervention": selected_intervention["intervention_id"],
            "execution_id": execution_id,
            "anchor_replay_ids": [str(fixture["fixture_id"])],
            "measurement_trial_ids": [],
            **derived,
            "authority": copy.deepcopy(dict(request["authority"])),
        }
        output_root.mkdir(parents=True, exist_ok=True)
        result_path = output_root / "result.json"
        atomic_write_json(result_path, result)
        adapter_identity = {
            "adapter_id": self.adapter_id,
            "implementation": {
                "path": ADAPTER_IMPLEMENTATION_PATH,
                "sha256": sha256_file(repo_root / ADAPTER_IMPLEMENTATION_PATH),
            },
            "contract_digest": canonical_digest(adapter_contract),
        }
        receipt_unsigned = {
            "schema_version": RECEIPT_SCHEMA,
            "adapter_identity": adapter_identity,
            "request_digest": request["request_digest"],
            "fixture": copy.deepcopy(dict(request["fixture"])),
            "campaign_id": contract.campaign_id,
            "config_digest": contract.config_digest,
            "selected_intervention": selected_intervention["intervention_id"],
            "selected_intervention_digest": canonical_digest(selected_intervention),
            "intervention_set_digest": contract.intervention_set_digest,
            "action_sha256": contract.action_sha256,
            "evaluator_identity": copy.deepcopy(dict(expected_evaluator_identity)),
            "execution_id": execution_id,
            "actual_mutations": copy.deepcopy(result["actual_mutations"]),
            "result_artifact": {
                "path": str(result_path),
                "sha256": sha256_file(result_path),
            },
            "consequence": derived["consequence"],
            "authority": copy.deepcopy(dict(request["authority"])),
        }
        receipt = {
            **receipt_unsigned,
            "receipt_digest": canonical_digest(receipt_unsigned),
        }
        receipt_path = output_root / "receipt.json"
        atomic_write_json(receipt_path, receipt)
        return {
            "lane": "trusted_simulator_adapter",
            "adapter_id": self.adapter_id,
            "adapter_identity": adapter_identity,
            "receipt": receipt,
            "receipt_sha256": sha256_file(receipt_path),
            "execution_id": execution_id,
            "anchor_replay_ids": result["anchor_replay_ids"],
            "measurement_trial_ids": [],
            "actual_mutations": result["actual_mutations"],
            "raw_artifacts": [copy.deepcopy(dict(request["fixture"]))],
            "result_artifact": receipt["result_artifact"],
            "result": result,
            "consequence": derived["consequence"],
        }


_TRUSTED_ADAPTERS: Mapping[str, TrustedSimulatorAdapter] = MappingProxyType(
    {FIXTURE_ADAPTER_ID: FixtureDeterministicAdapter()}
)
_NON_FIXTURE_TRUSTED_ADAPTERS = MappingProxyType(
    {C2_ADAPTER_ID: execute_c2_adapter_request}
)


def execute_trusted_adapter_request(
    request_path: Path,
    *,
    contract: LiveCampaignContract,
    selected_intervention: Mapping[str, Any],
    affected_factor_ids: Sequence[str],
    expected_evaluator_identity: Mapping[str, Any],
    remaining_anchor_replays: int,
    output_root: Path,
    prior_execution_ids: Sequence[str] = (),
    prior_anchor_replay_ids: Sequence[str] = (),
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    request_raw = load_json_object(request_path, label="trusted adapter request")
    if request_raw.get("schema_version") == C2_REQUEST_SCHEMA:
        adapter_id = str(request_raw.get("adapter_id", ""))
        handler = _NON_FIXTURE_TRUSTED_ADAPTERS.get(adapter_id)
        if handler is None:
            raise LiveOperatorError("non-fixture trusted adapter is not registered")
        return handler(
            request_raw,
            contract=contract,
            selected_intervention=selected_intervention,
            affected_factor_ids=affected_factor_ids,
            expected_evaluator_identity=expected_evaluator_identity,
            remaining_anchor_replays=remaining_anchor_replays,
            output_root=output_root,
            prior_execution_ids=prior_execution_ids,
            prior_anchor_replay_ids=prior_anchor_replay_ids,
            repo_root=repo_root,
        )
    if set(request_raw) != {
        "schema_version",
        "adapter_id",
        "campaign_id",
        "config_digest",
        "selected_intervention",
        "intervention_set_digest",
        "action_sha256",
        "evaluator_identity",
        "fixture",
        "authority",
        "request_digest",
    }:
        raise LiveOperatorError("trusted adapter request field set changed")
    request = _verify_digest(
        request_raw, field="request_digest", label="trusted adapter request"
    )
    for field in (
        "schema_version",
        "adapter_id",
        "campaign_id",
        "config_digest",
        "selected_intervention",
        "intervention_set_digest",
        "action_sha256",
        "request_digest",
    ):
        if not isinstance(request[field], str) or not request[field]:
            raise LiveOperatorError("trusted adapter request string field is invalid")
    if not isinstance(request["evaluator_identity"], Mapping) or not request[
        "evaluator_identity"
    ]:
        raise LiveOperatorError("trusted adapter evaluator identity is invalid")
    if request["schema_version"] != REQUEST_SCHEMA:
        raise LiveOperatorError("unexpected trusted adapter request schema")
    request_authority = _require_all_false(
        request["authority"], label="trusted adapter request"
    )
    if (
        request["campaign_id"] != contract.campaign_id
        or request["config_digest"] != contract.config_digest
        or request["selected_intervention"]
        != selected_intervention["intervention_id"]
        or request["intervention_set_digest"] != contract.intervention_set_digest
        or request["action_sha256"] != contract.action_sha256
        or request["evaluator_identity"] != expected_evaluator_identity
        or request_authority != contract.payload["authority"]
    ):
        raise LiveOperatorError("trusted adapter request identity is stale or changed")
    if remaining_anchor_replays < 1:
        raise LiveOperatorError("trusted adapter request exceeds remaining anchor budget")
    adapter_id = str(request["adapter_id"])
    adapter = _TRUSTED_ADAPTERS.get(adapter_id)
    if adapter is None:
        raise LiveOperatorError("trusted adapter is not registered")
    _adapter_contract(selected_intervention, adapter_id=adapter_id)
    fixture_path = _repo_file(
        request["fixture"], repo_root=repo_root, label="trusted adapter fixture"
    )
    fixture = load_json_object(fixture_path, label="trusted adapter fixture")
    if set(fixture) != {"schema_version", "fixture_id", "inputs", "authority"}:
        raise LiveOperatorError("trusted adapter fixture field set changed")
    if (
        fixture["schema_version"] != FIXTURE_SCHEMA
        or not isinstance(fixture["fixture_id"], str)
        or not fixture["fixture_id"]
    ):
        raise LiveOperatorError("trusted adapter fixture identity is invalid")
    fixture_authority = _require_all_false(
        fixture["authority"], label="trusted adapter fixture"
    )
    if fixture_authority != request_authority:
        raise LiveOperatorError("trusted adapter fixture authority changed")
    execution_id = _adapter_execution_id(
        adapter_id=adapter_id,
        request_digest=str(request["request_digest"]),
        fixture_id=str(fixture["fixture_id"]),
    )
    if execution_id in {str(value) for value in prior_execution_ids} or str(
        fixture["fixture_id"]
    ) in {str(value) for value in prior_anchor_replay_ids}:
        raise LiveOperatorError("trusted adapter request replay rejected before execution")
    return adapter.execute(
        request=request,
        fixture=fixture,
        contract=contract,
        selected_intervention=selected_intervention,
        affected_factor_ids=affected_factor_ids,
        expected_evaluator_identity=expected_evaluator_identity,
        output_root=output_root,
        repo_root=repo_root,
    )


def verify_embedded_trusted_adapter_receipt(
    summary: Mapping[str, Any],
    *,
    contract: LiveCampaignContract,
    expected_evaluator_identity: Mapping[str, Any],
    expected_consequence: Mapping[str, Any],
    expected_affected_factor_ids: Sequence[str],
    receipt_root: Path,
    repo_root: Path,
) -> dict[str, Any]:
    embedded = summary.get("adapter_receipt")
    if not isinstance(embedded, Mapping):
        raise LiveOperatorError("trusted adapter receipt is missing from summary")
    identity = embedded.get("adapter_identity")
    if (
        isinstance(identity, Mapping)
        and identity.get("adapter_id") == C2_ADAPTER_ID
    ):
        selected = next(
            (
                row.payload
                for row in contract.interventions
                if row.intervention_id
                == embedded.get("selected_intervention")
            ),
            None,
        )
        if selected is None:
            raise LiveOperatorError(
                "C2 trusted adapter selected intervention changed"
            )
        return verify_c2_adapter_receipt(
            summary,
            contract=contract,
            selected_intervention=selected,
            expected_evaluator_identity=expected_evaluator_identity,
            expected_consequence=expected_consequence,
            expected_affected_factor_ids=expected_affected_factor_ids,
            receipt_root=receipt_root,
            repo_root=repo_root,
        )
    if set(embedded) != {
        "schema_version",
        "adapter_identity",
        "request_digest",
        "fixture",
        "campaign_id",
        "config_digest",
        "selected_intervention",
        "selected_intervention_digest",
        "intervention_set_digest",
        "action_sha256",
        "evaluator_identity",
        "execution_id",
        "actual_mutations",
        "result_artifact",
        "consequence",
        "authority",
        "receipt_digest",
    }:
        raise LiveOperatorError("trusted adapter receipt field set changed")
    receipt = _verify_digest(
        embedded, field="receipt_digest", label="trusted adapter receipt"
    )
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise LiveOperatorError("unexpected trusted adapter receipt schema")
    receipt_authority = _require_all_false(
        receipt.get("authority"), label="trusted adapter receipt"
    )
    if receipt_authority != contract.payload["authority"]:
        raise LiveOperatorError("trusted adapter receipt authority changed")
    identity = receipt.get("adapter_identity")
    if not isinstance(identity, Mapping) or set(identity) != {
        "adapter_id",
        "implementation",
        "contract_digest",
    }:
        raise LiveOperatorError("trusted adapter identity is missing")
    adapter_id = str(identity.get("adapter_id", ""))
    if adapter_id not in _TRUSTED_ADAPTERS:
        raise LiveOperatorError("trusted adapter substitution rejected")
    if summary.get("adapter_id") != adapter_id or summary.get(
        "adapter_identity"
    ) != identity:
        raise LiveOperatorError("trusted adapter summary identity changed")
    implementation = identity.get("implementation")
    if (
        not isinstance(implementation, Mapping)
        or implementation.get("path") != ADAPTER_IMPLEMENTATION_PATH
        or implementation.get("sha256")
        != sha256_file(repo_root / ADAPTER_IMPLEMENTATION_PATH)
    ):
        raise LiveOperatorError("trusted adapter implementation identity changed")
    selected = next(
        (
            row.payload
            for row in contract.interventions
            if row.intervention_id == receipt.get("selected_intervention")
        ),
        None,
    )
    if selected is not None and identity.get("contract_digest") != canonical_digest(
        _adapter_contract(selected, adapter_id=adapter_id)
    ):
        raise LiveOperatorError("trusted adapter contract identity changed")
    fixture_path = _repo_file(
        receipt.get("fixture") or {},
        repo_root=repo_root,
        label="trusted adapter receipt fixture",
    )
    fixture = load_json_object(fixture_path, label="trusted adapter receipt fixture")
    if (
        set(fixture) != {"schema_version", "fixture_id", "inputs", "authority"}
        or fixture.get("schema_version") != FIXTURE_SCHEMA
        or not str(fixture.get("fixture_id", ""))
    ):
        raise LiveOperatorError("trusted adapter receipt fixture changed")
    if summary.get("raw_artifacts") != [receipt.get("fixture")]:
        raise LiveOperatorError("trusted adapter raw artifact binding changed")
    adapter_receipt_path = receipt_root / "trusted_adapter" / "receipt.json"
    if (
        not adapter_receipt_path.is_file()
        or sha256_file(adapter_receipt_path) != summary.get("receipt_sha256")
    ):
        raise LiveOperatorError("trusted adapter receipt artifact binding changed")
    result_artifact = receipt.get("result_artifact") or {}
    expected_result_path = (receipt_root / "trusted_adapter" / "result.json").resolve()
    if (
        set(result_artifact) != {"path", "sha256"}
        or Path(str(result_artifact["path"])).resolve() != expected_result_path
        or not expected_result_path.is_file()
        or sha256_file(expected_result_path) != result_artifact["sha256"]
    ):
        raise LiveOperatorError("trusted adapter result artifact binding changed")
    result = load_json_object(
        expected_result_path, label="trusted adapter result artifact"
    )
    expected_result_fields = {
        "schema_version",
        "campaign_id",
        "selected_intervention",
        "execution_id",
        "anchor_replay_ids",
        "measurement_trial_ids",
        "actual_mutations",
        "derived_response",
        "hypothesis_likelihoods",
        "factor_updates",
        "consequence",
        "authority",
    }
    adapter_contract = _adapter_contract(selected or {}, adapter_id=adapter_id)
    derived = _derive_fixture_evidence(
        fixture=fixture,
        adapter_contract=adapter_contract,
        selected_intervention=selected or {},
        affected_factor_ids=expected_affected_factor_ids,
    )
    expected_result = {
        "schema_version": RESULT_SCHEMA,
        "campaign_id": contract.campaign_id,
        "selected_intervention": receipt.get("selected_intervention"),
        "execution_id": receipt.get("execution_id"),
        "anchor_replay_ids": [str(fixture["fixture_id"])],
        "measurement_trial_ids": [],
        **derived,
        "authority": copy.deepcopy(dict(receipt["authority"])),
    }
    if set(result) != expected_result_fields or result != expected_result:
        raise LiveOperatorError("trusted adapter result was not independently derived")
    if receipt.get("actual_mutations") != derived["actual_mutations"]:
        raise LiveOperatorError("trusted adapter mutation evidence changed")
    if receipt.get("consequence") != derived["consequence"]:
        raise LiveOperatorError("trusted adapter consequence was not independently derived")
    expected_request = {
        "schema_version": REQUEST_SCHEMA,
        "adapter_id": adapter_id,
        "campaign_id": contract.campaign_id,
        "config_digest": contract.config_digest,
        "selected_intervention": receipt.get("selected_intervention"),
        "intervention_set_digest": contract.intervention_set_digest,
        "action_sha256": contract.action_sha256,
        "evaluator_identity": copy.deepcopy(dict(expected_evaluator_identity)),
        "fixture": copy.deepcopy(dict(receipt["fixture"])),
        "authority": copy.deepcopy(receipt_authority),
    }
    expected_request_digest = canonical_digest(expected_request)
    expected_execution_id = _adapter_execution_id(
        adapter_id=adapter_id,
        request_digest=expected_request_digest,
        fixture_id=str(fixture["fixture_id"]),
    )
    if (
        selected is None
        or receipt.get("request_digest") != expected_request_digest
        or receipt.get("execution_id") != expected_execution_id
        or receipt.get("selected_intervention_digest") != canonical_digest(selected)
        or receipt.get("campaign_id") != contract.campaign_id
        or receipt.get("config_digest") != contract.config_digest
        or receipt.get("intervention_set_digest") != contract.intervention_set_digest
        or receipt.get("action_sha256") != contract.action_sha256
        or receipt.get("evaluator_identity") != expected_evaluator_identity
        or receipt.get("consequence") != expected_consequence
        or receipt.get("execution_id") != summary.get("execution_id")
        or receipt.get("result_artifact") != summary.get("result_artifact")
        or json_artifact_sha256(embedded) != summary.get("receipt_sha256")
    ):
        raise LiveOperatorError("trusted adapter receipt identity changed")
    fixture_authority = _require_all_false(
        fixture.get("authority"), label="trusted adapter receipt fixture"
    )
    if fixture_authority != receipt_authority:
        raise LiveOperatorError("trusted adapter receipt fixture authority changed")
    return receipt


__all__ = [
    "ADAPTER_CONTRACT_SCHEMA",
    "FIXTURE_ADAPTER_ID",
    "FIXTURE_SCHEMA",
    "REQUEST_SCHEMA",
    "C2_ADAPTER_ID",
    "build_c2_adapter_request",
    "build_trusted_adapter_request",
    "execute_trusted_adapter_request",
    "verify_embedded_trusted_adapter_receipt",
]

"""Non-fixture trusted adapter for one preregistered retained-C2 family."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ..learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    sha256_file,
)
from ..pawn_bg_grasp_coordinate_descent import run_grasp_episode_probe
from .c2_consequence_evaluator import evaluate_c2_family
from .contracts import REPO_ROOT, SailContractError, verify_source_binding
from .importers import load_json_object
from .live_types import LiveCampaignContract, LiveOperatorError


ADAPTER_ID = "retained_action_frozen_c2_v1"
CONTRACT_SCHEMA = "sim2claw.sail_c2_trusted_adapter_contract.v1"
REQUEST_SCHEMA = "sim2claw.sail_c2_trusted_adapter_request.v1"
RESULT_SCHEMA = "sim2claw.sail_c2_trusted_adapter_result.v1"
RECEIPT_SCHEMA = "sim2claw.sail_c2_trusted_adapter_receipt.v1"
REFERENCE_SCHEMA = "sim2claw.sail_c2_trusted_adapter_reference.v1"
ADAPTER_IMPLEMENTATION_PATH = "src/sim2claw/sail/c2_trusted_adapter.py"
EVALUATOR_IMPLEMENTATION_PATH = (
    "src/sim2claw/sail/c2_consequence_evaluator.py"
)
SIMULATOR_IMPLEMENTATION_PATH = (
    "src/sim2claw/pawn_bg_grasp_coordinate_descent.py"
)

EpisodeRunner = Callable[..., dict[str, Any]]


def _all_false(value: object, *, label: str) -> dict[str, bool]:
    if not isinstance(value, Mapping) or not value:
        raise LiveOperatorError(f"{label} authority is missing")
    normalized = dict(value)
    if any(flag is not False for flag in normalized.values()):
        raise LiveOperatorError(f"{label} widened authority")
    return normalized


def _verify_digest(
    payload: Mapping[str, Any], *, field: str, label: str
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(payload))
    observed = normalized.pop(field, None)
    if observed != canonical_digest(normalized):
        raise LiveOperatorError(f"{label} digest mismatch")
    return {**normalized, field: str(observed)}


def _repo_relative(path: Path, *, repo_root: Path, label: str) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as error:
        raise LiveOperatorError(f"{label} escaped the repository") from error


def _load_contract(
    binding: Mapping[str, Any], *, repo_root: Path
) -> tuple[Path, dict[str, Any]]:
    try:
        path = verify_source_binding(binding, repo_root=repo_root)
    except SailContractError as error:
        raise LiveOperatorError(
            f"C2 adapter contract source identity changed: {error}"
        ) from error
    contract = load_json_object(path, label="C2 trusted adapter contract")
    if contract.get("schema_version") != CONTRACT_SCHEMA:
        raise LiveOperatorError("unexpected C2 trusted adapter contract schema")
    if contract.get("adapter_id") != ADAPTER_ID:
        raise LiveOperatorError("C2 trusted adapter substitution rejected")
    _all_false(contract.get("authority"), label="C2 trusted adapter contract")
    budget = contract.get("budget")
    candidates = contract.get("frozen_candidate_family")
    if (
        not isinstance(budget, Mapping)
        or set(budget)
        != {
            "maximum_interventions",
            "maximum_anchor_replays",
            "maximum_provider_calls",
        }
        or int(budget["maximum_interventions"]) != 1
        or not 1 <= int(budget["maximum_anchor_replays"]) <= 18
        or int(budget["maximum_provider_calls"]) != 0
        or not isinstance(candidates, list)
        or len(candidates) != int(budget["maximum_anchor_replays"])
    ):
        raise LiveOperatorError("C2 trusted adapter budget changed")
    candidate_ids = [str(row.get("candidate_id", "")) for row in candidates]
    if (
        any(not value for value in candidate_ids)
        or len(candidate_ids) != len(set(candidate_ids))
        or any(
            not isinstance(row.get("overrides"), Mapping)
            or not isinstance(row.get("axis_levels"), Mapping)
            for row in candidates
        )
    ):
        raise LiveOperatorError("C2 trusted adapter candidate family changed")
    axes = [str(value) for value in contract["factorial_design"]["axes"]]
    allowed_by_axis = contract["factorial_design"].get(
        "allowed_mutation_fields_by_axis"
    )
    if (
        not isinstance(allowed_by_axis, Mapping)
        or set(allowed_by_axis) != set(axes)
        or any(
            not isinstance(fields, list)
            or not fields
            or len(fields) != len(set(fields))
            or any(not isinstance(field, str) or not field for field in fields)
            for fields in allowed_by_axis.values()
        )
    ):
        raise LiveOperatorError("C2 trusted adapter mutation scope changed")
    combinations = {
        tuple(bool(row["axis_levels"][axis]) for axis in axes)
        for row in candidates
    }
    if (
        len(axes) != 2
        or len(combinations) != 4
        or len(candidates) != 4
        or any(set(row["axis_levels"]) != set(axes) for row in candidates)
    ):
        raise LiveOperatorError("C2 trusted adapter factorial design changed")
    for candidate in candidates:
        expected_fields = {
            str(field)
            for axis in axes
            if bool(candidate["axis_levels"][axis])
            for field in allowed_by_axis[axis]
        }
        if set(candidate["overrides"]) != expected_fields:
            raise LiveOperatorError(
                "C2 trusted adapter candidate escaped its declared axis"
            )
    verified = {}
    for name, source in contract["source_bindings"].items():
        try:
            source_path = verify_source_binding(source, repo_root=repo_root)
        except SailContractError as error:
            raise LiveOperatorError(
                f"C2 trusted adapter source identity changed: {name}: {error}"
            ) from error
        verified[str(name)] = source_path
    if (
        verified.get("simulator_implementation")
        != (repo_root / SIMULATOR_IMPLEMENTATION_PATH).resolve()
        or verified.get("independent_consequence_evaluator")
        != (repo_root / EVALUATOR_IMPLEMENTATION_PATH).resolve()
    ):
        raise LiveOperatorError("C2 trusted adapter implementation binding changed")
    posterior_rule = contract.get("posterior_update_rule") or {}
    if (
        set(posterior_rule.get("hypothesis_axis") or {})
        != set(contract.get("hypotheses") or {})
        or set((posterior_rule.get("hypothesis_axis") or {}).values())
        != set(axes)
        or posterior_rule.get("movement_requires_admitted_evaluator_owned_evidence")
        is not True
        or posterior_rule.get("preserve_prior_on_rejection_or_abstention")
        is not True
        or posterior_rule.get("no_post_hoc_threshold_change") is not True
    ):
        raise LiveOperatorError("C2 trusted adapter posterior rule changed")
    thresholds = contract.get("consequence_thresholds") or {}
    weights = thresholds.get("mechanism_score_weights") or {}
    if (
        set(weights)
        != {
            "retention",
            "loaded_aperture",
            "slip_reduction",
            "task_consequence",
            "ee_consequence",
        }
        or abs(sum(float(value) for value in weights.values()) - 1.0) > 1e-9
        or any(float(value) < 0.0 for value in weights.values())
        or float(thresholds.get("maximum_ee_rms_m", 0.0)) <= 0.0
        or float(thresholds.get("maximum_joint_rms_degrees", 0.0)) <= 0.0
        or thresholds.get(
            "lower_rms_without_strict_task_success_is_diagnostic_only"
        )
        is not True
    ):
        raise LiveOperatorError("C2 trusted adapter consequence thresholds changed")
    application = load_json_object(
        verified["project_application_contract"],
        label="C2 trusted adapter project application",
    )
    recording_id = str(contract["diagnosis_anchor"]["recording_id"])
    action_sha = str(contract["diagnosis_anchor"]["action_array_sha256"])
    if (
        application["episode_roles"]["diagnosis_anchor"] != recording_id
        or application["action_sha256_by_recording_id"][recording_id]
        != action_sha
    ):
        raise LiveOperatorError("C2 trusted adapter retained input identity changed")
    return path, contract


def build_c2_adapter_request(
    *,
    contract: LiveCampaignContract,
    selected_intervention: Mapping[str, Any],
    adapter_contract_path: Path,
    evaluator_identity: Mapping[str, Any],
    authority: Mapping[str, bool],
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Build a result-free source-bound request for the retained C2 adapter."""

    normalized_authority = _all_false(
        authority, label="C2 trusted adapter request"
    )
    if normalized_authority != contract.payload["authority"]:
        raise LiveOperatorError("C2 trusted adapter request authority changed")
    binding = {
        "path": _repo_relative(
            adapter_contract_path,
            repo_root=repo_root,
            label="C2 adapter contract",
        ),
        "sha256": sha256_file(adapter_contract_path),
    }
    _load_contract(binding, repo_root=repo_root)
    reference = selected_intervention.get("trusted_adapter")
    if reference != {
        "schema_version": REFERENCE_SCHEMA,
        "adapter_id": ADAPTER_ID,
        "contract_source_binding": "c2_trusted_adapter_contract",
    }:
        raise LiveOperatorError("C2 trusted adapter reference changed")
    unsigned = {
        "schema_version": REQUEST_SCHEMA,
        "adapter_id": ADAPTER_ID,
        "campaign_id": contract.campaign_id,
        "config_digest": contract.config_digest,
        "selected_intervention": str(selected_intervention["intervention_id"]),
        "intervention_set_digest": contract.intervention_set_digest,
        "action_sha256": contract.action_sha256,
        "evaluator_identity": copy.deepcopy(dict(evaluator_identity)),
        "adapter_contract": binding,
        "authority": copy.deepcopy(normalized_authority),
    }
    return {**unsigned, "request_digest": canonical_digest(unsigned)}


def compile_c2_adapter_request(
    config_path: Path,
    *,
    adapter_contract_path: Path,
    output_path: Path,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Materialize a result-free request for the SAIL-selected intervention."""

    from .live_contracts import load_live_campaign_contract
    from .live_decision import rank_live_acquisition
    from .live_receipts import build_live_evaluator_identity

    contract = load_live_campaign_contract(config_path, repo_root=repo_root)
    ranking = rank_live_acquisition(
        hypotheses=contract.hypothesis_priors,
        candidates=[row.payload for row in contract.interventions],
        weights=contract.payload["acquisition"]["weights"],
    )
    selected_id = str(ranking["selected_intervention"])
    selected = next(
        row.payload
        for row in contract.interventions
        if row.intervention_id == selected_id
    )
    if (
        selected.get("kind") != "simulator_family"
        or selected.get("availability") != "available_simulator"
    ):
        raise LiveOperatorError(
            "SAIL did not select an available simulator intervention"
        )
    request = build_c2_adapter_request(
        contract=contract,
        selected_intervention=selected,
        adapter_contract_path=adapter_contract_path,
        evaluator_identity=build_live_evaluator_identity(
            contract, repo_root=repo_root
        ),
        authority=contract.payload["authority"],
        repo_root=repo_root,
    )
    atomic_write_json(output_path, request)
    adapter_contract = load_json_object(
        adapter_contract_path, label="C2 trusted adapter contract"
    )
    return {
        "schema_version": "sim2claw.sail_c2_adapter_request_compile_result.v1",
        "status": "preregistered_not_executed",
        "selected_intervention": selected_id,
        "action_sha256": contract.action_sha256,
        "candidate_count": len(
            adapter_contract["frozen_candidate_family"]
        ),
        "interventions_used": 0,
        "anchor_replays_used": 0,
        "provider_calls": 0,
        "request_sha256": sha256_file(output_path),
        "request_digest": request["request_digest"],
        "output_path": str(output_path),
        "training_admitted": False,
        "physical_authority": False,
    }


def _expected_request(
    *,
    adapter_contract: Mapping[str, Any],
    contract: LiveCampaignContract,
    selected_intervention: Mapping[str, Any],
    evaluator_identity: Mapping[str, Any],
    authority: Mapping[str, bool],
) -> dict[str, Any]:
    return {
        "schema_version": REQUEST_SCHEMA,
        "adapter_id": ADAPTER_ID,
        "campaign_id": contract.campaign_id,
        "config_digest": contract.config_digest,
        "selected_intervention": selected_intervention["intervention_id"],
        "intervention_set_digest": contract.intervention_set_digest,
        "action_sha256": contract.action_sha256,
        "evaluator_identity": copy.deepcopy(dict(evaluator_identity)),
        "adapter_contract": copy.deepcopy(dict(adapter_contract)),
        "authority": copy.deepcopy(dict(authority)),
    }


def _validate_request(
    request: Mapping[str, Any],
    *,
    contract: LiveCampaignContract,
    selected_intervention: Mapping[str, Any],
    evaluator_identity: Mapping[str, Any],
    repo_root: Path,
) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    expected_fields = {
        "schema_version",
        "adapter_id",
        "campaign_id",
        "config_digest",
        "selected_intervention",
        "intervention_set_digest",
        "action_sha256",
        "evaluator_identity",
        "adapter_contract",
        "authority",
        "request_digest",
    }
    if set(request) != expected_fields:
        raise LiveOperatorError("C2 trusted adapter request field set changed")
    normalized = _verify_digest(
        request, field="request_digest", label="C2 trusted adapter request"
    )
    authority = _all_false(
        normalized["authority"], label="C2 trusted adapter request"
    )
    expected = _expected_request(
        adapter_contract=normalized["adapter_contract"],
        contract=contract,
        selected_intervention=selected_intervention,
        evaluator_identity=evaluator_identity,
        authority=authority,
    )
    if (
        normalized["schema_version"] != REQUEST_SCHEMA
        or normalized["adapter_id"] != ADAPTER_ID
        or normalized["request_digest"] != canonical_digest(expected)
        or authority != contract.payload["authority"]
    ):
        raise LiveOperatorError("C2 trusted adapter request identity changed")
    reference = selected_intervention.get("trusted_adapter")
    if (
        not isinstance(reference, Mapping)
        or reference.get("schema_version") != REFERENCE_SCHEMA
        or reference.get("adapter_id") != ADAPTER_ID
        or normalized["adapter_contract"]
        != contract.payload["source_bindings"].get(
            str(reference.get("contract_source_binding", ""))
        )
    ):
        raise LiveOperatorError("C2 trusted adapter source reference changed")
    path, adapter_contract = _load_contract(
        normalized["adapter_contract"], repo_root=repo_root
    )
    if adapter_contract["diagnosis_anchor"]["action_array_sha256"] != (
        contract.action_sha256
    ) or set(
        adapter_contract["posterior_update_rule"]["hypothesis_axis"]
    ) != set(contract.hypothesis_priors):
        raise LiveOperatorError("C2 trusted adapter action binding changed")
    return normalized, path, adapter_contract


def execute_c2_adapter_request(
    request: Mapping[str, Any],
    *,
    contract: LiveCampaignContract,
    selected_intervention: Mapping[str, Any],
    affected_factor_ids: Sequence[str],
    expected_evaluator_identity: Mapping[str, Any],
    remaining_anchor_replays: int,
    output_root: Path,
    prior_execution_ids: Sequence[str],
    prior_anchor_replay_ids: Sequence[str],
    repo_root: Path = REPO_ROOT,
    episode_runner: EpisodeRunner = run_grasp_episode_probe,
) -> dict[str, Any]:
    """Own mutation, replay execution, evaluation, and receipt issuance."""

    normalized, _contract_path, adapter_contract = _validate_request(
        request,
        contract=contract,
        selected_intervention=selected_intervention,
        evaluator_identity=expected_evaluator_identity,
        repo_root=repo_root,
    )
    candidates = adapter_contract["frozen_candidate_family"]
    if len(candidates) > remaining_anchor_replays:
        raise LiveOperatorError(
            "C2 trusted adapter family exceeds remaining anchor replay budget"
        )
    family_digest = canonical_digest(
        {
            "base_parameters": adapter_contract["base_parameters"],
            "candidates": candidates,
            "posterior_update_rule": adapter_contract["posterior_update_rule"],
            "consequence_thresholds": adapter_contract[
                "consequence_thresholds"
            ],
        }
    )
    execution_id = canonical_digest(
        {
            "adapter_id": ADAPTER_ID,
            "request_digest": normalized["request_digest"],
            "family_digest": family_digest,
        }
    )
    if execution_id in {str(value) for value in prior_execution_ids}:
        raise LiveOperatorError("C2 trusted adapter request replay rejected")

    raw_root = output_root / "raw"
    raw_receipts: dict[str, dict[str, Any]] = {}
    raw_artifacts: list[dict[str, str]] = []
    anchor_replay_ids: list[str] = []
    actual_mutations: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_id = str(candidate["candidate_id"])
        parameters = copy.deepcopy(dict(adapter_contract["base_parameters"]))
        parameters.update(candidate["overrides"])
        raw = episode_runner(
            source_repository_root=repo_root,
            recording_id=str(
                adapter_contract["diagnosis_anchor"]["recording_id"]
            ),
            parameters=parameters,
            retention_trace_enabled=True,
        )
        raw_path = raw_root / f"{candidate_id}.json"
        atomic_write_json(raw_path, raw)
        raw_sha = sha256_file(raw_path)
        replay_id = canonical_digest(
            {
                "adapter_id": ADAPTER_ID,
                "candidate_id": candidate_id,
                "raw_sha256": raw_sha,
            }
        )
        if replay_id in {
            str(value) for value in prior_anchor_replay_ids
        } or replay_id in anchor_replay_ids:
            raise LiveOperatorError("C2 trusted adapter raw replay duplicated")
        raw_receipts[candidate_id] = raw
        raw_artifacts.append(
            {
                "candidate_id": candidate_id,
                "path": raw_path.relative_to(output_root).as_posix(),
                "sha256": raw_sha,
            }
        )
        anchor_replay_ids.append(replay_id)
        actual_mutations.append(
            {
                "candidate_id": candidate_id,
                "axis_levels": copy.deepcopy(candidate["axis_levels"]),
                "overrides": copy.deepcopy(candidate["overrides"]),
                "parameter_digest": canonical_digest(parameters),
            }
        )

    evaluation = evaluate_c2_family(
        contract=adapter_contract,
        raw_receipts=raw_receipts,
        affected_factor_ids=affected_factor_ids,
    )
    evaluation_path = output_root / "evaluation.json"
    atomic_write_json(evaluation_path, evaluation)
    selected_id = evaluation["consequence"]["selected_candidate_id"]
    selected_score = next(
        (
            float(row["mechanism_score"])
            for row in evaluation["candidate_results"]
            if row["candidate_id"] == selected_id
        ),
        0.0,
    )
    result = {
        "schema_version": RESULT_SCHEMA,
        "campaign_id": contract.campaign_id,
        "selected_intervention": selected_intervention["intervention_id"],
        "execution_id": execution_id,
        "anchor_replay_ids": anchor_replay_ids,
        "measurement_trial_ids": [],
        "actual_mutations": actual_mutations,
        "derived_response": selected_score,
        "hypothesis_likelihoods": evaluation["hypothesis_likelihoods"],
        "factor_updates": evaluation["factor_updates"],
        "consequence": evaluation["consequence"],
        "authority": copy.deepcopy(dict(normalized["authority"])),
    }
    output_root.mkdir(parents=True, exist_ok=True)
    result_path = output_root / "result.json"
    atomic_write_json(result_path, result)
    adapter_identity = {
        "adapter_id": ADAPTER_ID,
        "implementation": {
            "path": ADAPTER_IMPLEMENTATION_PATH,
            "sha256": sha256_file(repo_root / ADAPTER_IMPLEMENTATION_PATH),
        },
        "evaluator": {
            "path": EVALUATOR_IMPLEMENTATION_PATH,
            "sha256": sha256_file(
                repo_root / EVALUATOR_IMPLEMENTATION_PATH
            ),
        },
        "contract_digest": canonical_digest(adapter_contract),
        "family_digest": family_digest,
    }
    receipt_unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "adapter_identity": adapter_identity,
        "request_digest": normalized["request_digest"],
        "adapter_contract": copy.deepcopy(normalized["adapter_contract"]),
        "campaign_id": contract.campaign_id,
        "config_digest": contract.config_digest,
        "selected_intervention": selected_intervention["intervention_id"],
        "selected_intervention_digest": canonical_digest(
            selected_intervention
        ),
        "intervention_set_digest": contract.intervention_set_digest,
        "action_sha256": contract.action_sha256,
        "evaluator_identity": copy.deepcopy(
            dict(expected_evaluator_identity)
        ),
        "execution_id": execution_id,
        "anchor_replay_ids": anchor_replay_ids,
        "actual_mutations": actual_mutations,
        "raw_artifacts": raw_artifacts,
        "evaluation_artifact": {
            "path": evaluation_path.relative_to(output_root).as_posix(),
            "sha256": sha256_file(evaluation_path),
        },
        "result_artifact": {
            "path": str(result_path.resolve()),
            "sha256": sha256_file(result_path),
        },
        "consequence": evaluation["consequence"],
        "budget": {
            "interventions": 1,
            "anchor_replays": len(anchor_replay_ids),
            "measurement_trials": 0,
            "provider_calls": 0,
        },
        "authority": copy.deepcopy(dict(normalized["authority"])),
    }
    receipt = {
        **receipt_unsigned,
        "receipt_digest": canonical_digest(receipt_unsigned),
    }
    receipt_path = output_root / "receipt.json"
    atomic_write_json(receipt_path, receipt)
    return {
        "lane": "trusted_simulator_adapter",
        "adapter_id": ADAPTER_ID,
        "adapter_identity": adapter_identity,
        "receipt": receipt,
        "receipt_sha256": sha256_file(receipt_path),
        "execution_id": execution_id,
        "anchor_replay_ids": anchor_replay_ids,
        "measurement_trial_ids": [],
        "actual_mutations": actual_mutations,
        "raw_artifacts": raw_artifacts,
        "result_artifact": receipt["result_artifact"],
        "result": result,
        "consequence": evaluation["consequence"],
    }


def verify_c2_adapter_receipt(
    summary: Mapping[str, Any],
    *,
    contract: LiveCampaignContract,
    selected_intervention: Mapping[str, Any],
    expected_evaluator_identity: Mapping[str, Any],
    expected_consequence: Mapping[str, Any],
    expected_affected_factor_ids: Sequence[str],
    receipt_root: Path,
    repo_root: Path,
) -> dict[str, Any]:
    """Independently rederive a C2 result from content-addressed raw receipts."""

    embedded = summary.get("adapter_receipt")
    if not isinstance(embedded, Mapping):
        raise LiveOperatorError("C2 trusted adapter receipt is missing")
    expected_fields = {
        "schema_version",
        "adapter_identity",
        "request_digest",
        "adapter_contract",
        "campaign_id",
        "config_digest",
        "selected_intervention",
        "selected_intervention_digest",
        "intervention_set_digest",
        "action_sha256",
        "evaluator_identity",
        "execution_id",
        "anchor_replay_ids",
        "actual_mutations",
        "raw_artifacts",
        "evaluation_artifact",
        "result_artifact",
        "consequence",
        "budget",
        "authority",
        "receipt_digest",
    }
    if set(embedded) != expected_fields:
        raise LiveOperatorError("C2 trusted adapter receipt field set changed")
    receipt = _verify_digest(
        embedded, field="receipt_digest", label="C2 trusted adapter receipt"
    )
    authority = _all_false(
        receipt["authority"], label="C2 trusted adapter receipt"
    )
    if (
        receipt["schema_version"] != RECEIPT_SCHEMA
        or authority != contract.payload["authority"]
    ):
        raise LiveOperatorError("C2 trusted adapter receipt identity changed")
    _contract_path, adapter_contract = _load_contract(
        receipt["adapter_contract"], repo_root=repo_root
    )
    identity = receipt["adapter_identity"]
    expected_identity = {
        "adapter_id": ADAPTER_ID,
        "implementation": {
            "path": ADAPTER_IMPLEMENTATION_PATH,
            "sha256": sha256_file(repo_root / ADAPTER_IMPLEMENTATION_PATH),
        },
        "evaluator": {
            "path": EVALUATOR_IMPLEMENTATION_PATH,
            "sha256": sha256_file(
                repo_root / EVALUATOR_IMPLEMENTATION_PATH
            ),
        },
        "contract_digest": canonical_digest(adapter_contract),
        "family_digest": canonical_digest(
            {
                "base_parameters": adapter_contract["base_parameters"],
                "candidates": adapter_contract["frozen_candidate_family"],
                "posterior_update_rule": adapter_contract[
                    "posterior_update_rule"
                ],
                "consequence_thresholds": adapter_contract[
                    "consequence_thresholds"
                ],
            }
        ),
    }
    if (
        identity != expected_identity
        or summary.get("adapter_id") != ADAPTER_ID
        or summary.get("adapter_identity") != identity
    ):
        raise LiveOperatorError("C2 trusted adapter implementation identity changed")

    adapter_root = receipt_root / "trusted_adapter"
    raw_receipts: dict[str, dict[str, Any]] = {}
    for binding in receipt["raw_artifacts"]:
        candidate_id = str(binding["candidate_id"])
        path = adapter_root / str(binding["path"])
        expected_path = adapter_root / "raw" / f"{candidate_id}.json"
        if (
            path.resolve() != expected_path.resolve()
            or not path.is_file()
            or sha256_file(path) != binding["sha256"]
        ):
            raise LiveOperatorError("C2 trusted adapter raw artifact changed")
        raw_receipts[candidate_id] = load_json_object(
            path, label=f"C2 trusted adapter raw result {candidate_id}"
        )
    evaluation = evaluate_c2_family(
        contract=adapter_contract,
        raw_receipts=raw_receipts,
        affected_factor_ids=expected_affected_factor_ids,
    )
    evaluation_binding = receipt["evaluation_artifact"]
    evaluation_path = adapter_root / str(evaluation_binding["path"])
    if (
        evaluation_path.resolve()
        != (adapter_root / "evaluation.json").resolve()
        or not evaluation_path.is_file()
        or sha256_file(evaluation_path) != evaluation_binding["sha256"]
        or load_json_object(
            evaluation_path, label="C2 trusted adapter evaluation"
        )
        != evaluation
    ):
        raise LiveOperatorError("C2 trusted adapter evaluation was not rederived")
    result_path = adapter_root / "result.json"
    result_binding = receipt["result_artifact"]
    if (
        Path(str(result_binding["path"])).resolve() != result_path.resolve()
        or not result_path.is_file()
        or sha256_file(result_path) != result_binding["sha256"]
    ):
        raise LiveOperatorError("C2 trusted adapter result artifact changed")
    result = load_json_object(result_path, label="C2 trusted adapter result")
    expected_result = {
        "schema_version": RESULT_SCHEMA,
        "campaign_id": contract.campaign_id,
        "selected_intervention": selected_intervention["intervention_id"],
        "execution_id": receipt["execution_id"],
        "anchor_replay_ids": receipt["anchor_replay_ids"],
        "measurement_trial_ids": [],
        "actual_mutations": receipt["actual_mutations"],
        "derived_response": next(
            (
                float(row["mechanism_score"])
                for row in evaluation["candidate_results"]
                if row["candidate_id"]
                == evaluation["consequence"]["selected_candidate_id"]
            ),
            0.0,
        ),
        "hypothesis_likelihoods": evaluation["hypothesis_likelihoods"],
        "factor_updates": evaluation["factor_updates"],
        "consequence": evaluation["consequence"],
        "authority": copy.deepcopy(authority),
    }
    expected_request = _expected_request(
        adapter_contract=receipt["adapter_contract"],
        contract=contract,
        selected_intervention=selected_intervention,
        evaluator_identity=expected_evaluator_identity,
        authority=authority,
    )
    expected_request_digest = canonical_digest(expected_request)
    expected_execution_id = canonical_digest(
        {
            "adapter_id": ADAPTER_ID,
            "request_digest": expected_request_digest,
            "family_digest": identity["family_digest"],
        }
    )
    adapter_receipt_path = adapter_root / "receipt.json"
    if (
        result != expected_result
        or receipt["request_digest"] != expected_request_digest
        or receipt["execution_id"] != expected_execution_id
        or receipt["selected_intervention_digest"]
        != canonical_digest(selected_intervention)
        or receipt["campaign_id"] != contract.campaign_id
        or receipt["config_digest"] != contract.config_digest
        or receipt["intervention_set_digest"]
        != contract.intervention_set_digest
        or receipt["action_sha256"] != contract.action_sha256
        or receipt["evaluator_identity"] != expected_evaluator_identity
        or receipt["consequence"] != evaluation["consequence"]
        or receipt["consequence"] != expected_consequence
        or receipt["budget"]
        != {
            "interventions": 1,
            "anchor_replays": len(adapter_contract["frozen_candidate_family"]),
            "measurement_trials": 0,
            "provider_calls": 0,
        }
        or not adapter_receipt_path.is_file()
        or sha256_file(adapter_receipt_path)
        != summary.get("receipt_sha256")
        or summary.get("result_artifact") != result_binding
        or summary.get("raw_artifacts") != receipt["raw_artifacts"]
    ):
        raise LiveOperatorError("C2 trusted adapter receipt identity changed")
    return receipt


__all__ = [
    "ADAPTER_ID",
    "CONTRACT_SCHEMA",
    "REFERENCE_SCHEMA",
    "REQUEST_SCHEMA",
    "build_c2_adapter_request",
    "compile_c2_adapter_request",
    "execute_c2_adapter_request",
    "verify_c2_adapter_receipt",
]

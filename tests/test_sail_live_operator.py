from __future__ import annotations

import copy
import builtins
import inspect
import json
import multiprocessing
import shutil
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import sim2claw.sail.live_runtime as live_runtime_module
from sim2claw.learning_factory_artifacts import canonical_digest, sha256_file
from sim2claw.sail.live_adapters import (
    ADAPTER_CONTRACT_SCHEMA,
    FIXTURE_ADAPTER_ID,
    FIXTURE_SCHEMA,
    build_trusted_adapter_request,
    verify_embedded_trusted_adapter_receipt,
)
from sim2claw.sail.live_operator import (
    LiveOperatorError,
    apply_live_sparse_closure,
    build_live_evaluator_identity,
    load_live_campaign_contract,
    resolve_live_campaign_state_path,
    run_live_operator,
    update_discrete_structure_posterior,
    verify_live_operator_migration_receipt,
    verify_live_operator_receipt,
)
from sim2claw.sail.live_evidence import (
    EvidenceAdmissionError,
    MEASUREMENT_RECEIPT_SCHEMA,
    MEASUREMENT_RESULT_SCHEMA,
    MEASUREMENT_TRIALS_SCHEMA,
    SIMULATOR_RECEIPT_SCHEMA,
    SIMULATOR_RESULT_SCHEMA,
    evaluate_offline_measurement_trials,
    verify_measurement_evaluator_receipt,
    verify_simulator_evaluator_receipt,
)
from sim2claw.sail.live_state import (
    commit_prepared_state,
    locked_campaign_state,
    prepare_admitted_result,
)
from sim2claw.sail.loop_closure import LoopClosureError
from sim2claw.sail.posterior import PosteriorError


ACTION_SHA = "a" * 64
_LOCK_BUDGET = {
    "maximum_interventions": 1,
    "maximum_anchor_replays": 1,
    "maximum_measurement_trials": 1,
    "used_interventions": 0,
    "used_anchor_replays": 0,
    "used_measurement_trials": 0,
}


def _hold_campaign_lock(
    state_root: str,
    entered: object,
    release: object,
) -> None:
    with locked_campaign_state(
        Path(state_root),
        campaign_id="lock-test",
        config_digest="c" * 64,
        initial_budget=_LOCK_BUDGET,
    ):
        entered.set()  # type: ignore[attr-defined]
        release.wait(5)  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def cleanup_test_generated_live_campaign_state() -> object:
    repo_root = Path(__file__).resolve().parents[1]
    roots = (
        repo_root / "outputs/sail/test-live-campaigns",
        repo_root / "outputs/sail/live-campaign-state-v1",
    )
    before = {
        root: {path.resolve() for path in root.iterdir()} if root.is_dir() else set()
        for root in roots
    }
    yield
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.iterdir():
            if path.resolve() in before[root]:
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()


def test_public_operator_api_has_no_disabled_simulator_receipt_parameter() -> None:
    parameters = inspect.signature(run_live_operator).parameters
    assert "simulator_evaluator_receipt_path" not in parameters
    assert "trusted_adapter_request_path" in parameters


def test_modularization_migration_receipt_binds_byte_identical_outputs(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    path = (
        repo_root
        / "configs/sail/migrations/live_operator_modularization_v3.json"
    )
    verified = verify_live_operator_migration_receipt(path)
    assert verified["retained_outputs_byte_identical"] is True
    payload = json.loads(path.read_text())
    payload["output_sha256"]["after"]["ablation.json"] = "f" * 64
    unsigned = {key: value for key, value in payload.items() if key != "migration_digest"}
    payload["migration_digest"] = canonical_digest(unsigned)
    changed = _write(tmp_path / "changed-migration.json", payload)
    with pytest.raises(LiveOperatorError, match="changed retained outputs"):
        verify_live_operator_migration_receipt(changed)


def test_trusted_adapter_contract_request_and_fixture_match_frozen_schemas(
    tmp_path: Path,
) -> None:
    path, config, fixture_path, request_path = _trusted_adapter_campaign(tmp_path)
    repo_root = Path(__file__).resolve().parents[1]
    cases = (
        (
            "trusted_adapter_fixture_v1.json",
            json.loads(fixture_path.read_text()),
        ),
        (
            "trusted_adapter_request_v1.json",
            json.loads(request_path.read_text()),
        ),
        (
            "trusted_fixture_adapter_contract_v1.json",
            next(
                row["trusted_adapter"]
                for row in config["interventions"]
                if row["kind"] == "simulator_family"
            ),
        ),
    )
    assert path.is_file()
    assert json.loads(fixture_path.read_text())["schema_version"] == FIXTURE_SCHEMA
    for schema_name, instance in cases:
        schema = json.loads(
            (repo_root / "configs/sail/schemas" / schema_name).read_text()
        )
        Draft202012Validator(schema).validate(instance)


def test_trusted_adapter_request_builder_rejects_fixture_outside_repository(
    tmp_path: Path,
) -> None:
    path, config, _, _ = _trusted_adapter_campaign(tmp_path)
    contract = load_live_campaign_contract(path)
    selected = next(
        row.payload
        for row in contract.interventions
        if row.kind == "simulator_family"
    )
    outside_fixture = _write(
        tmp_path / "outside-fixture.json",
        {
            "schema_version": FIXTURE_SCHEMA,
            "fixture_id": "outside-repository",
            "inputs": {"gain": 0.4, "signal": 1.0},
            "authority": config["authority"],
        },
    )
    with pytest.raises(LiveOperatorError, match="escaped the repository"):
        build_trusted_adapter_request(
            adapter_id=FIXTURE_ADAPTER_ID,
            contract=contract,
            selected_intervention=selected,
            fixture_path=outside_fixture,
            evaluator_identity=build_live_evaluator_identity(contract),
            authority=config["authority"],
        )


def test_runtime_adapter_validation_matches_numeric_json_schemas(
    tmp_path: Path,
) -> None:
    path, config, _, _ = _trusted_adapter_campaign(tmp_path)
    changed = copy.deepcopy(config)
    simulator = next(
        row for row in changed["interventions"] if row["kind"] == "simulator_family"
    )
    simulator["trusted_adapter"]["mutation"]["value"] = "2.0"
    changed_path = _write(path.parent / "string-mutation.json", changed)
    string_request = _trusted_request_for_campaign(
        changed_path,
        changed,
        fixture_path=Path(__file__).resolve().parent
        / "fixtures/sail/trusted_adapter_fixture_v1.json",
        name="string-mutation-request.json",
    )
    with pytest.raises(LiveOperatorError, match="not a JSON number"):
        run_live_operator(
            changed_path,
            output_root=tmp_path / "string-mutation-output",
            trusted_adapter_request_path=string_request,
        )

    fixture = _write(
        path.parent / "boolean-input-fixture.json",
        {
            "schema_version": FIXTURE_SCHEMA,
            "fixture_id": "boolean-input",
            "inputs": {"gain": True, "signal": 1.0},
            "authority": config["authority"],
        },
    )
    boolean_request = _trusted_request_for_campaign(
        path,
        config,
        fixture_path=fixture,
        name="boolean-input-request.json",
    )
    with pytest.raises(LiveOperatorError, match="not a JSON number"):
        run_live_operator(
            path,
            output_root=tmp_path / "boolean-input-output",
            trusted_adapter_request_path=boolean_request,
        )


def test_campaign_state_lock_serializes_two_processes(tmp_path: Path) -> None:
    context = multiprocessing.get_context("fork")
    entered_first = context.Event()
    entered_second = context.Event()
    release_first = context.Event()
    release_second = context.Event()
    state_root = str(tmp_path / "shared-state")
    first = context.Process(
        target=_hold_campaign_lock,
        args=(state_root, entered_first, release_first),
    )
    second = context.Process(
        target=_hold_campaign_lock,
        args=(state_root, entered_second, release_second),
    )
    first.start()
    assert entered_first.wait(5)
    second.start()
    assert not entered_second.wait(0.25)
    release_first.set()
    assert entered_second.wait(5)
    release_second.set()
    first.join(5)
    second.join(5)
    assert first.exitcode == 0
    assert second.exitcode == 0


def test_interrupted_state_replace_leaves_canonical_bytes_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = tmp_path / "interrupted-state"
    with locked_campaign_state(
        state_root,
        campaign_id="interrupt-test",
        config_digest="d" * 64,
        initial_budget=_LOCK_BUDGET,
    ) as (state_path, state):
        admission = {
            "lane": "offline_measurement",
            "execution_id": "interrupt-execution",
            "anchor_replay_ids": [],
            "measurement_trial_ids": ["interrupt-trial"],
            "receipt_sha256": "a" * 64,
            "receipt": {"receipt_digest": "b" * 64},
            "result_artifact": {"sha256": "c" * 64},
        }
        prepared = prepare_admitted_result(state, admission)
        before = state_path.read_bytes()
        original_replace = Path.replace

        def interrupted_replace(path: Path, target: Path) -> Path:
            if Path(target) == state_path:
                raise OSError("simulated interruption before atomic replace")
            return original_replace(path, target)

        monkeypatch.setattr(Path, "replace", interrupted_replace)
        with pytest.raises(OSError, match="simulated interruption"):
            commit_prepared_state(state_path, state, prepared)
        assert state_path.read_bytes() == before
        for temporary in state_path.parent.glob("campaign_state.json.*.tmp"):
            temporary.unlink()


def test_live_metric_rename_does_not_mutate_frozen_phase_one_acquisition_contracts() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    expected = {
        "src/sim2claw/sail/acquisition.py": "bbd987fa2ffa6eafd9aa9c883b97f5c8e3ad9af2b8b838facc80541d59982f1b",
        "configs/sail/acquisition_v1.json": "02bc19d8d8851fdc0199f8cb70025fea589260a36aac6cf480625b1f592e3411",
        "configs/sail/schemas/intervention_v1.json": "b2c8251b99d1ecdf48d5541338c5c549c3f001c81b7d1aec620540c3710d6d40",
        "tests/fixtures/sail/intervention_valid_v1.json": "97e989bd3d8b41bc6a192c4ba0480ee5a8b36a410333acc7ac3db8540e709e77",
    }
    assert {path: sha256_file(repo_root / path) for path in expected} == expected


def _write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def _binding(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": sha256_file(path)}


def _mechanism(
    mechanism_id: str,
    family: str,
    required: list[str],
    intervention_ids: list[str],
    factor_ids: list[str],
) -> dict:
    return {
        "mechanism_id": mechanism_id,
        "family": family,
        "physical_interpretation": f"bounded hypothesis {mechanism_id}",
        "affected_components": ["retained_subject"],
        "parameters": [
            {
                "name": "gain",
                "unit": "normalized",
                "prior": {"mean": 0.5},
                "minimum": 0.0,
                "maximum": 1.0,
            }
        ],
        "predicted_residual_signatures": [{"id": "declared_before_result"}],
        "required_observables": required,
        "non_identifiabilities": ["requires discriminating observation"],
        "candidate_interventions": intervention_ids,
        "simulator_mutation": "config_bound_mutation_only",
        "graph_factors": factor_ids,
        "influence_edges": [],
        "invalidation_rules": ["opposite preregistered signature observed"],
        "invariance_scope": {
            "invariant_parameters": ["gain"],
            "allowed_context_covariates": ["episode_context"],
        },
        "action_immutability_tests": ["source_action_sha256_equal"],
        "prediction_model": {"kind": "linear", "features": ["feature"]},
    }


def _campaign(tmp_path: Path) -> tuple[Path, dict]:
    action = _write(
        tmp_path / "action.json",
        {"action": {"sha256": ACTION_SHA, "byte_identical": True}},
    )
    evaluator = _write(tmp_path / "evaluator.json", {"id": "eval:any-id", "sealed": True})
    residual = _write(tmp_path / "residual.json", {"id": "residual:any-id"})

    receipts = tmp_path / "manual"
    _write(
        receipts / "one" / "anchor-screen-receipt.json",
        {
            "campaign_id": "manual-one",
            "candidate_count": 2,
            "anchor_pass_count": 0,
            "action_array_sha256": ACTION_SHA,
            "all_actions_byte_identical": True,
        },
    )
    _write(
        receipts / "two" / "anchor-screen-receipt.json",
        {
            "campaign_id": "manual-two",
            "candidate_count": 1,
            "anchor_pass_count": 0,
            "action_array_sha256": ACTION_SHA,
            "all_actions_byte_identical": True,
        },
    )
    incomplete = _write(tmp_path / "incomplete" / "candidate.json", {"status": "wip"})

    flex = "flexural-mechanism-arbitrary"
    actuator = "actuator-path-mechanism-arbitrary"
    simulator_probe = "probe-simulator-arbitrary"
    measurement_probe = "probe-measurement-arbitrary"
    factors = ["residual:contact", "residual:aperture"]
    components = [
        {"id": "persistent_structured_residual", "weight": 0.5, "uncertainty_class": "structural_uncertainty"},
        {"id": "ensemble_without_single_winner", "weight": 0.5, "uncertainty_class": "structural_uncertainty"},
    ]
    config = {
        "schema_version": "sim2claw.sail_live_campaign.v2",
        "campaign_id": "campaign-with-no-python-registration",
        "created_at": "2026-07-22T12:00:00-05:00",
        "subject": {
            "workcell_id": "workcell:any",
            "session_id": "session:any",
            "context_id": "context:any",
            "label": "generic retained subject",
        },
        "source_bindings": {
            "action": _binding(action),
            "evaluator": _binding(evaluator),
            "residual": _binding(residual),
        },
        "action_identity": {
            "source_binding": "action",
            "sha256_pointer": "/action/sha256",
            "byte_identical_pointer": "/action/byte_identical",
            "sha256": ACTION_SHA,
        },
        "evaluator": {
            "evaluator_id": "independent-evaluator-any",
            "owner": "independent_cpu_fp32_evaluator",
            "source_bindings": ["evaluator"],
            "release_index": 401,
        },
        "proof_boundary": {
            "proof_class": "retained_simulator_fixture",
            "physical_authority": False,
            "training_admitted": False,
            "agent_can_promote": False,
            "simulator_can_promote": False,
            "operator_can_promote": False,
        },
        "budget": {
            "maximum_interventions": 1,
            "maximum_anchor_replays": 18,
            "maximum_measurement_trials": 6,
            "used_interventions": 0,
            "used_anchor_replays": 0,
            "used_measurement_trials": 0,
        },
        "persistent_state": {
            "repo_relative_root": "outputs/sail/live-campaign-state-v1",
            "key_algorithm": "sha256_campaign_config_v1",
        },
        "residual_evidence": [
            {
                "residual_id": "residual:contact",
                "label": "contact retention",
                "value": 1.0,
                "available": True,
                "source_binding": "residual",
                "provenance": "sealed retained trace",
            },
            {
                "residual_id": "residual:aperture",
                "label": "loaded aperture",
                "value": 0.9,
                "available": True,
                "source_binding": "residual",
                "provenance": "sealed retained trace",
            },
        ],
        "structural_surprise": {
            "components": components,
            "signals": {
                "persistent_structured_residual": {
                    "value": 1.0,
                    "available": True,
                    "provenance": "manual families remain terminal negative",
                    "reason": "persistent residual",
                },
                "ensemble_without_single_winner": {
                    "value": 1.0,
                    "available": True,
                    "provenance": "two retained structures",
                    "reason": "non-identifying evidence",
                },
            },
            "trigger": {
                "score_threshold": 0.6,
                "component_threshold": 0.6,
                "minimum_triggered_components": 2,
                "minimum_available_weight": 0.5,
                "require_structural_component": True,
                "missing_components_are_zero": False,
            },
        },
        "observables": [
            {"observable_id": "joint_angle", "unit": "rad", "available": True},
            {"observable_id": "joint_current", "unit": "ampere", "available": True},
            {"observable_id": "jaw_force", "unit": "newton", "available": False},
            {"observable_id": "rubber_profile", "unit": "millimeter", "available": False},
        ],
        "mechanisms": [
            {"prior_probability": 0.5, **_mechanism(flex, "fingertip_contact", ["jaw_force", "rubber_profile"], [simulator_probe, measurement_probe], factors)},
            {"prior_probability": 0.5, **_mechanism(actuator, "load_compliance", ["joint_angle", "joint_current", "jaw_force"], [simulator_probe, measurement_probe], factors)},
        ],
        "interventions": [
            {
                "intervention_id": simulator_probe,
                "kind": "simulator_family",
                "availability": "available_simulator",
                "allowed_mutations": ["declared simulator factor"],
                "required_observables": ["joint_angle", "joint_current"],
                "declared_scopes": ["fingertip_contact", "load_compliance"],
                "residual_node_ids": factors,
                "maximum_trials": 18,
                "cost": 0.5,
                "risk": 0.3,
                "gate_relevance": 0.5,
                "compensation_debt_reduction": 0.3,
                "parameter_diagnostic_score": 0.2,
                "predicted_signatures": {
                    flex: {"contact_response": {"normalized_response": 0.55}},
                    actuator: {"contact_response": {"normalized_response": 0.45}},
                },
            },
            {
                "intervention_id": measurement_probe,
                "kind": "measurement_acquisition",
                "availability": "unavailable_measurement",
                "allowed_mutations": [],
                "required_observables": ["jaw_force", "rubber_profile", "joint_angle", "joint_current"],
                "declared_scopes": ["fingertip_contact", "load_compliance"],
                "residual_node_ids": factors,
                "maximum_trials": 6,
                "cost": 0.1,
                "risk": 0.0,
                "gate_relevance": 1.0,
                "compensation_debt_reduction": 1.0,
                "parameter_diagnostic_score": 1.0,
                "predicted_signatures": {
                    flex: {"force_deformation_coupling": {"normalized_response": 0.95}},
                    actuator: {"force_deformation_coupling": {"normalized_response": 0.05}},
                },
            },
        ],
        "acquisition": {
            "weights": {
                "predicted_signature_separation": 0.6,
                "compensation_debt_reduction": 0.2,
                "gate_relevance": 0.2,
                "cost": -0.05,
                "risk": -0.05,
            },
            "minimum_predicted_signature_separation": 0.5,
        },
        "factor_beliefs": [
            {"factor_id": "factor:contact_patch", "value": 0.5, "status": "retained", "affected_by_mechanisms": [flex]},
            {"factor_id": "factor:actuator_path", "value": 0.5, "status": "retained", "affected_by_mechanisms": [actuator]},
            {"factor_id": "factor:arm_tracking", "value": 0.0, "status": "unaffected_frozen", "affected_by_mechanisms": []},
        ],
        "influence_thresholds": {
            "require_declared_scope": True,
            "require_predicts_path": True,
            "minimum_residual_overlap": 1,
            "minimum_local_sensitivity": 0.5,
            "minimum_precision": 0.0,
            "minimum_recall": 0.0,
        },
        "invariance": {
            "mechanism_id": flex,
            "invariant_parameter": "gain",
            "context_covariate": "episode_context",
            "episode_contexts": [
                {
                    "episode_id": "retained:any",
                    "level": "single",
                    "feature": None,
                    "observation": None,
                    "actions": None,
                }
            ],
            "thresholds": {
                "minimum_context_levels": 2,
                "minimum_episodes_per_level": 1,
                "maximum_invariant_parameter_range": 0.1,
                "minimum_residual_signature_consistency": 0.9,
            },
        },
        "ablation": {
            "manual_receipt_glob": str(receipts / "*" / "anchor-screen-receipt.json"),
            "incomplete_artifact_glob": str(incomplete.parent / "*.json"),
            "expected_completed_campaigns": 2,
            "expected_candidate_replays": 3,
            "expected_anchor_passes": 0,
            "manual_hypotheses_rejected_or_narrowed": ["scalar friction alone"],
            "manual_hypotheses_retained": [flex, actuator],
        },
        "measurement_acquisition_packet": {
            "measurements": ["jaw_force", "rubber_profile", "joint_angle", "joint_current"],
            "minimum_sampling_hz": 100,
            "maximum_alignment_skew_samples": 1,
            "calibration": ["zero force before each trial", "known-gap blocked closures"],
            "synchronization": "one monotonic timestamp domain",
            "required_phases": [
                "unloaded close",
                "first contact",
                "loaded hold",
                "transport-equivalent dwell",
                "release",
            ],
            "robot_motion_authority": False,
        },
        "measurement_result_evaluation": {
            "allowed_proof_classes": ["synthetic_measurement_fixture"],
            "flexural_mechanism_id": flex,
            "actuator_mechanism_id": actuator,
            "feature_algorithms": {
                "force_deformation_coupling": "nonnegative Pearson correlation",
                "current_force_hysteresis": "absolute normalized loop area",
                "loaded_patch_change": "normalized unloaded-to-loaded mean change",
            },
            "thresholds": {
                "flexural_min_force_deformation_coupling": 0.8,
                "flexural_max_current_force_hysteresis": 0.1,
                "flexural_min_loaded_patch_change": 0.25,
                "actuator_max_force_deformation_coupling": 0.4,
                "actuator_min_current_force_hysteresis": 0.2,
                "actuator_max_loaded_patch_change": 0.15,
            },
        },
        "authority": {
            "physical_capture": False,
            "robot_motion": False,
            "training": False,
            "self_promotion": False,
        },
    }
    repo_root = Path(__file__).resolve().parents[1]
    config_path = _write(
        repo_root
        / "outputs"
        / "sail"
        / "test-live-campaigns"
        / canonical_digest(str(tmp_path))
        / "campaign.json",
        config,
    )
    return config_path, config


def _trusted_adapter_campaign(
    tmp_path: Path,
) -> tuple[Path, dict, Path, Path]:
    path, original = _campaign(tmp_path)
    config = copy.deepcopy(original)
    simulator = next(
        row for row in config["interventions"] if row["kind"] == "simulator_family"
    )
    measurement = next(
        row
        for row in config["interventions"]
        if row["kind"] == "measurement_acquisition"
    )
    mechanism_ids = [row["mechanism_id"] for row in config["mechanisms"]]
    simulator["cost"] = 0.0
    simulator["risk"] = 0.0
    simulator["gate_relevance"] = 1.0
    simulator["compensation_debt_reduction"] = 1.0
    simulator["predicted_signatures"] = {
        mechanism_ids[0]: {"contact_response": {"normalized_response": 0.8}},
        mechanism_ids[1]: {"contact_response": {"normalized_response": 0.1}},
    }
    simulator["trusted_adapter"] = {
        "schema_version": ADAPTER_CONTRACT_SCHEMA,
        "adapter_id": FIXTURE_ADAPTER_ID,
        "mutation": {"field": "gain", "operation": "scale", "value": 2.0},
        "response": {"operation": "product", "fields": ["gain", "signal"]},
        "evaluation": {"target": 0.8, "pass_tolerance": 0.01},
    }
    measurement["cost"] = 1.0
    measurement["risk"] = 1.0
    measurement["gate_relevance"] = 0.0
    measurement["compensation_debt_reduction"] = 0.0
    measurement["predicted_signatures"] = {
        mechanism_ids[0]: {"force_deformation_coupling": {"normalized_response": 0.55}},
        mechanism_ids[1]: {"force_deformation_coupling": {"normalized_response": 0.45}},
    }
    path = _write(path.parent / "trusted-adapter-campaign.json", config)
    repo_root = Path(__file__).resolve().parents[1]
    fixture_path = (
        repo_root / "tests/fixtures/sail/trusted_adapter_fixture_v1.json"
    )
    request_path = _trusted_request_for_campaign(
        path, config, fixture_path=fixture_path
    )
    return path, config, fixture_path, request_path


def _trusted_request_for_campaign(
    path: Path,
    config: dict,
    *,
    fixture_path: Path,
    name: str = "trusted-adapter-request.json",
) -> Path:
    contract = load_live_campaign_contract(path)
    selected = next(
        row.payload
        for row in contract.interventions
        if row.intervention_id == "probe-simulator-arbitrary"
    )
    request = build_trusted_adapter_request(
        adapter_id=FIXTURE_ADAPTER_ID,
        contract=contract,
        selected_intervention=selected,
        fixture_path=fixture_path,
        evaluator_identity=build_live_evaluator_identity(contract),
        authority=config["authority"],
    )
    return _write(path.parent / name, request)


def _measurement_raw(
    path: Path,
    *,
    config: dict,
    trial_id: str = "measurement-trial-arbitrary-1",
    force: list[float] | None = None,
    deformation: list[float] | None = None,
    current: list[float] | None = None,
    patch: list[float] | None = None,
) -> Path:
    packet = config["measurement_acquisition_packet"]
    return _write(
        path,
        {
            "schema_version": MEASUREMENT_TRIALS_SCHEMA,
            "campaign_id": config["campaign_id"],
            "selected_intervention": "probe-measurement-arbitrary",
            "proof_class": "synthetic_measurement_fixture",
            "authority": copy.deepcopy(config["authority"]),
            "trials": [
                {
                    "trial_id": trial_id,
                    "clock_id": "synthetic-common-clock-arbitrary",
                    "sampling_hz": 100.0,
                    "maximum_alignment_skew_samples": 1,
                    "calibration_completed": packet["calibration"],
                    "phases_completed": packet.get(
                        "required_phases",
                        [
                            "unloaded close",
                            "first contact",
                            "loaded hold",
                            "transport-equivalent dwell",
                            "release",
                        ],
                    ),
                    "phase_labels": [
                        "unloaded close",
                        "unloaded close",
                        "first contact",
                        "loaded hold",
                        "loaded hold",
                        "release",
                        "release",
                    ],
                    "jaw_force_n": force or [0.0, 0.0, 1.0, 2.0, 3.0, 2.0, 0.0],
                    "deformation_mm": deformation
                    or [0.0, 0.0, 0.4, 0.8, 1.2, 0.8, 0.0],
                    "motor_current_a": current
                    or [0.0, 0.0, 0.2, 0.4, 0.6, 0.4, 0.0],
                    "patch_area_mm2": patch
                    or [1.0, 1.0, 1.1, 2.0, 2.0, 1.4, 1.0],
                }
            ],
        },
    )


def _measurement_receipt(
    tmp_path: Path,
    *,
    config_path: Path,
    config: dict,
    packet_path: Path,
    raw_path: Path,
    execution_id: str = "measurement-execution-arbitrary-1",
    result_name: str = "measurement-result.json",
    receipt_name: str = "measurement-receipt.json",
) -> Path:
    contract = load_live_campaign_contract(config_path)
    packet = json.loads(packet_path.read_text())
    raw = json.loads(raw_path.read_text())
    evaluated = evaluate_offline_measurement_trials(
        [raw],
        campaign_id=contract.campaign_id,
        selected_intervention="probe-measurement-arbitrary",
        packet=packet,
        evaluation_contract=config["measurement_result_evaluation"],
    )
    result_path = _write(
        tmp_path / result_name,
        {
            "schema_version": MEASUREMENT_RESULT_SCHEMA,
            "campaign_id": contract.campaign_id,
            "selected_intervention": "probe-measurement-arbitrary",
            "execution_id": execution_id,
            "actual_mutations": [],
            "acquisition_packet_digest": packet["packet_digest"],
            **evaluated,
            "authority": copy.deepcopy(config["authority"]),
        },
    )
    unsigned = {
        "schema_version": MEASUREMENT_RECEIPT_SCHEMA,
        "campaign_id": contract.campaign_id,
        "selected_intervention": "probe-measurement-arbitrary",
        "frozen_intervention_set_digest": contract.intervention_set_digest,
        "action_sha256": ACTION_SHA,
        "evaluator_identity": build_live_evaluator_identity(contract),
        "execution_id": execution_id,
        "actual_mutations": [],
        "measurement_trial_ids": evaluated["measurement_trial_ids"],
        "acquisition_packet": _binding(packet_path),
        "raw_artifacts": [_binding(raw_path)],
        "result_artifact": _binding(result_path),
        "consequence": evaluated["consequence"],
        "authority": copy.deepcopy(config["authority"]),
    }
    return _write(
        tmp_path / receipt_name,
        {**unsigned, "receipt_digest": canonical_digest(unsigned)},
    )


def _simulator_receipt(tmp_path: Path, *, config_path: Path, config: dict) -> tuple[Path, dict]:
    contract = load_live_campaign_contract(config_path)
    raw_path = _write(tmp_path / "simulator-raw.json", {"sealed": True, "score": 0.0})
    consequence = {"evaluator_passed": False, "status": "frozen_evaluator_reject"}
    result_path = _write(
        tmp_path / "simulator-result.json",
        {
            "schema_version": SIMULATOR_RESULT_SCHEMA,
            "campaign_id": contract.campaign_id,
            "selected_intervention": "probe-simulator-arbitrary",
            "execution_id": "simulator-execution-arbitrary-1",
            "anchor_replay_ids": ["anchor-replay-arbitrary-1"],
            "actual_mutations": ["declared simulator factor"],
            "hypothesis_likelihoods": {
                "flexural-mechanism-arbitrary": 0.8,
                "actuator-path-mechanism-arbitrary": 0.2,
            },
            "factor_updates": {"factor:contact_patch": 0.8},
            "consequence": consequence,
            "authority": copy.deepcopy(config["authority"]),
        },
    )
    unsigned = {
        "schema_version": SIMULATOR_RECEIPT_SCHEMA,
        "campaign_id": contract.campaign_id,
        "selected_intervention": "probe-simulator-arbitrary",
        "frozen_intervention_set_digest": contract.intervention_set_digest,
        "action_sha256": ACTION_SHA,
        "evaluator_identity": build_live_evaluator_identity(contract),
        "execution_id": "simulator-execution-arbitrary-1",
        "anchor_replay_ids": ["anchor-replay-arbitrary-1"],
        "actual_mutations": ["declared simulator factor"],
        "raw_artifacts": [_binding(raw_path)],
        "result_artifact": _binding(result_path),
        "consequence": consequence,
        "authority": copy.deepcopy(config["authority"]),
    }
    receipt = {**unsigned, "receipt_digest": canonical_digest(unsigned)}
    return _write(tmp_path / "simulator-receipt.json", receipt), receipt


def test_generic_campaign_ids_need_no_python_registration(tmp_path: Path) -> None:
    path, config = _campaign(tmp_path)
    contract = load_live_campaign_contract(path)
    assert contract.campaign_id == config["campaign_id"]
    assert {row.mechanism_id for row in contract.mechanisms} == {
        "flexural-mechanism-arbitrary",
        "actuator-path-mechanism-arbitrary",
    }


def test_action_and_source_drift_fail_closed(tmp_path: Path) -> None:
    path, config = _campaign(tmp_path)
    changed = copy.deepcopy(config)
    changed["action_identity"]["sha256"] = "b" * 64
    changed_path = _write(path.parent / "changed-action.json", changed)
    with pytest.raises(LiveOperatorError, match="action identity"):
        load_live_campaign_contract(changed_path)

    evaluator_path = Path(config["source_bindings"]["evaluator"]["path"])
    evaluator_path.write_text("drift\n")
    with pytest.raises(LiveOperatorError, match="source"):
        load_live_campaign_contract(path)


def test_invalid_posterior_updates_fail_closed() -> None:
    prior = {
        "one": 0.5,
        "two": 0.5,
    }
    with pytest.raises(PosteriorError, match="hypothesis set"):
        update_discrete_structure_posterior(prior, likelihoods={"one": 1.0})
    with pytest.raises(PosteriorError, match="likelihood"):
        update_discrete_structure_posterior(
            prior, likelihoods={"one": -1.0, "two": 1.0}
        )


def test_valid_bayesian_update_may_increase_entropy() -> None:
    result = update_discrete_structure_posterior(
        {"concentrated": 0.99, "unlikely": 0.01},
        likelihoods={"concentrated": 0.01, "unlikely": 0.99},
        observation_id="surprising-observation",
    )
    assert result["entropy_delta_bits"] > 0.0
    assert result["observed_information_gain_bits"] < 0.0
    assert result["entropy_after_bits"] > result["entropy_before_bits"]


def test_sparse_closure_rejects_unaffected_factor_mutation() -> None:
    before = [
        {"factor_id": "affected", "value": 0.5, "status": "retained"},
        {"factor_id": "frozen", "value": 0.0, "status": "unaffected_frozen"},
    ]
    with pytest.raises(LoopClosureError, match="unaffected"):
        apply_live_sparse_closure(
            before_factors=before,
            affected_factor_ids=["affected"],
            updates={"affected": 0.7, "frozen": 0.2},
            observation_opened=True,
            action_identity={"sha256": ACTION_SHA},
            evidence_identity={"sha256": "b" * 64},
        )


def test_self_consistent_forged_simulator_bundle_is_never_evaluator_authority(
    tmp_path: Path,
) -> None:
    path, config = _campaign(tmp_path)
    contract = load_live_campaign_contract(path)
    receipt_path, _ = _simulator_receipt(tmp_path, config_path=path, config=config)
    simulator_intervention = next(
        row.payload for row in contract.interventions if row.kind == "simulator_family"
    )
    # This is the exact previously accepted forgery shape: raw, result, receipt,
    # hashes, evaluator identity, and digest are mutually consistent, but no
    # trusted code recomputes its consequence from the raw artifact.
    with pytest.raises(EvidenceAdmissionError, match="admission is disabled"):
        verify_simulator_evaluator_receipt(
            receipt_path,
            campaign_id=contract.campaign_id,
            selected_intervention=simulator_intervention,
            intervention_set_digest=contract.intervention_set_digest,
            action_sha256=ACTION_SHA,
            expected_evaluator_identity=build_live_evaluator_identity(contract),
            remaining_anchor_replays=18,
        )


def test_end_to_end_operator_abstains_for_missing_discriminating_measurement(
    tmp_path: Path,
) -> None:
    path, _ = _campaign(tmp_path)
    output_root = tmp_path / "output"
    result = run_live_operator(path, output_root=output_root)
    assert result["verdict"] == "abstain_measurement_acquisition_required"
    assert result["selected_intervention"] == "probe-measurement-arbitrary"
    assert result["budget"]["used_interventions"] == 0
    assert result["budget"]["used_anchor_replays"] == 0
    trace = json.loads((output_root / "operator_trace.json").read_text())
    assert trace["stages"][0]["stage"] == "residual_evidence"
    assert trace["stages"][-1]["stage"] == "terminal_verdict"
    ablation = json.loads((output_root / "ablation.json").read_text())
    assert ablation["manual"]["completed_campaigns"] == 2
    assert ablation["manual"]["simulator_evaluations"] == 3
    assert ablation["manual"]["incomplete_work_in_progress"]["artifact_count"] == 1
    assert not ablation["manual"]["incomplete_work_in_progress"]["included_in_completed_counts"]
    assert ablation["sail"]["simulator_evaluations"] == 0
    comparison = ablation["comparison"]
    assert comparison["historical_simulator_evaluations_informed_frozen_retrospective_decision"] == 3
    assert comparison["sail_additional_simulator_evaluations_after_pause"] == 0
    assert comparison["historical_evaluations_remain_retrospective_context"]
    assert "avoided" not in json.dumps(comparison).lower()
    assert comparison["claim"] == (
        "3 historical evaluations informed the frozen retrospective decision; "
        "SAIL used 0 additional evaluations after the pause."
    )
    invariance = json.loads((output_root / "invariance.json").read_text())
    assert invariance["verdict"] == "not_evaluable"
    assert invariance["reason"] == "missing_source_bound_feature_observation_or_action_vectors"
    assert not invariance["missing_vectors_imputed"]
    receipt = json.loads((output_root / "receipt.json").read_text())
    unsigned = {key: value for key, value in receipt.items() if key != "receipt_digest"}
    assert receipt["receipt_digest"] == canonical_digest(unsigned)


def test_selected_simulator_abstains_without_a_bound_trusted_request(
    tmp_path: Path,
) -> None:
    path, _, _, _ = _trusted_adapter_campaign(tmp_path)
    result = run_live_operator(path, output_root=tmp_path / "no-adapter-request")
    assert result["selected_intervention"] == "probe-simulator-arbitrary"
    assert result["verdict"] == "abstain_no_bound_intervention_result"
    assert result["budget"]["used_interventions"] == 0
    assert result["budget"]["used_anchor_replays"] == 0


@pytest.mark.parametrize(
    ("gate", "verdict"),
    [
        ("intervention_budget", "abstain_global_budget_exhausted"),
        ("anchor_budget", "abstain_global_budget_exhausted"),
        ("signature_separation", "abstain_non_identifying_simulator_intervention"),
    ],
)
def test_trusted_adapter_abstains_before_execution_when_a_global_gate_is_closed(
    tmp_path: Path, gate: str, verdict: str
) -> None:
    path, config, fixture_path, _ = _trusted_adapter_campaign(tmp_path)
    changed = copy.deepcopy(config)
    if gate == "intervention_budget":
        changed["budget"]["used_interventions"] = changed["budget"][
            "maximum_interventions"
        ]
    elif gate == "anchor_budget":
        changed["budget"]["used_anchor_replays"] = changed["budget"][
            "maximum_anchor_replays"
        ]
    else:
        changed["acquisition"]["minimum_predicted_signature_separation"] = 0.8
    changed_path = _write(path.parent / f"closed-{gate}.json", changed)
    request_path = _trusted_request_for_campaign(
        changed_path,
        changed,
        fixture_path=fixture_path,
        name=f"closed-{gate}-request.json",
    )
    output = tmp_path / f"closed-{gate}-output"
    result = run_live_operator(
        changed_path,
        output_root=output,
        trusted_adapter_request_path=request_path,
    )
    assert result["verdict"] == verdict
    assert not (output / "trusted_adapter").exists()
    assert result["budget"] == changed["budget"]


def test_trusted_adapter_derives_and_admits_one_simulator_result(
    tmp_path: Path,
) -> None:
    path, _, _, request_path = _trusted_adapter_campaign(tmp_path)
    output = tmp_path / "trusted-adapter-output"
    result = run_live_operator(
        path,
        output_root=output,
        trusted_adapter_request_path=request_path,
    )
    assert result["selected_intervention"] == "probe-simulator-arbitrary"
    assert result["verdict"] == "evaluator_pass"
    assert result["budget"]["used_interventions"] == 1
    assert result["budget"]["used_anchor_replays"] == 1
    assert result["budget"]["used_measurement_trials"] == 0
    assert result["promotion"] is False
    assert result["training_admitted"] is False
    assert result["physical_authority"] is False
    summary = json.loads((output / "admitted_evaluator_receipt.json").read_text())
    assert summary["lane"] == "trusted_simulator_adapter"
    assert summary["adapter_id"] == FIXTURE_ADAPTER_ID
    assert summary["adapter_receipt"]["actual_mutations"] == [
        {
            "after": 0.8,
            "before": 0.4,
            "field": "gain",
            "operand": 2.0,
            "operation": "scale",
        }
    ]
    assert summary["adapter_receipt"]["consequence"]["derived_response"] == 0.8
    verify_live_operator_receipt(output / "receipt.json")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda request: request.__setitem__("result", {"evaluator_passed": True}), "field set"),
        (lambda request: request.__setitem__("config_digest", "f" * 64), "identity"),
        (
            lambda request: request["evaluator_identity"].__setitem__(
                "evaluator_id", "forged-evaluator"
            ),
            "identity",
        ),
        (lambda request: request["fixture"].__setitem__("sha256", "f" * 64), "source identity"),
        (lambda request: request.__setitem__("adapter_id", "unregistered-adapter"), "registered"),
        (lambda request: request["authority"].__setitem__("training", True), "widened authority"),
    ],
)
def test_trusted_adapter_request_rejects_substitution_result_and_authority_tamper(
    tmp_path: Path, mutation: object, message: str
) -> None:
    path, _, _, request_path = _trusted_adapter_campaign(tmp_path)
    request = json.loads(request_path.read_text())
    mutation(request)  # type: ignore[operator]
    request.pop("request_digest")
    request["request_digest"] = canonical_digest(request)
    changed_request = _write(path.parent / "changed-adapter-request.json", request)
    with pytest.raises(LiveOperatorError, match=message):
        run_live_operator(
            path,
            output_root=tmp_path / "rejected-adapter-output",
            trusted_adapter_request_path=changed_request,
        )


def test_trusted_adapter_request_is_single_use_across_output_roots(
    tmp_path: Path,
) -> None:
    path, config, fixture_path, _ = _trusted_adapter_campaign(tmp_path)
    changed = copy.deepcopy(config)
    changed["budget"]["maximum_interventions"] = 2
    path = _write(path.parent / "two-intervention-budget.json", changed)
    request_path = _trusted_request_for_campaign(
        path,
        changed,
        fixture_path=fixture_path,
        name="two-intervention-request.json",
    )
    run_live_operator(
        path,
        output_root=tmp_path / "trusted-first",
        trusted_adapter_request_path=request_path,
    )
    with pytest.raises(LiveOperatorError, match="replay"):
        run_live_operator(
            path,
            output_root=tmp_path / "trusted-second",
            trusted_adapter_request_path=request_path,
        )
    assert not (tmp_path / "trusted-second" / "trusted_adapter").exists()


def test_trusted_adapter_request_rejects_a_changed_frozen_mutation(
    tmp_path: Path,
) -> None:
    path, config, _, request_path = _trusted_adapter_campaign(tmp_path)
    changed = copy.deepcopy(config)
    simulator = next(
        row for row in changed["interventions"] if row["kind"] == "simulator_family"
    )
    simulator["trusted_adapter"]["mutation"]["value"] = 3.0
    changed_path = _write(path.parent / "changed-mutation-campaign.json", changed)
    with pytest.raises(LiveOperatorError, match="identity"):
        run_live_operator(
            changed_path,
            output_root=tmp_path / "changed-mutation-output",
            trusted_adapter_request_path=request_path,
        )


def test_live_receipt_rejects_resealed_stale_adapter_implementation_identity(
    tmp_path: Path,
) -> None:
    path, _, _, request_path = _trusted_adapter_campaign(tmp_path)
    output = tmp_path / "stale-adapter-output"
    run_live_operator(
        path,
        output_root=output,
        trusted_adapter_request_path=request_path,
    )
    adapter_receipt_path = output / "trusted_adapter" / "receipt.json"
    adapter_receipt = json.loads(adapter_receipt_path.read_text())
    adapter_receipt["adapter_identity"]["implementation"]["sha256"] = "f" * 64
    adapter_unsigned = {
        key: value
        for key, value in adapter_receipt.items()
        if key != "receipt_digest"
    }
    adapter_receipt["receipt_digest"] = canonical_digest(adapter_unsigned)
    _write(adapter_receipt_path, adapter_receipt)

    summary_path = output / "admitted_evaluator_receipt.json"
    summary = json.loads(summary_path.read_text())
    summary["adapter_identity"] = adapter_receipt["adapter_identity"]
    summary["adapter_receipt"] = adapter_receipt
    summary["receipt_sha256"] = sha256_file(adapter_receipt_path)
    summary["receipt_digest"] = adapter_receipt["receipt_digest"]
    _write(summary_path, summary)

    receipt_path = output / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["outputs"]["admitted_evaluator_receipt"]["sha256"] = sha256_file(
        summary_path
    )
    receipt["admitted_evaluator_receipt"]["receipt_sha256"] = summary[
        "receipt_sha256"
    ]
    receipt["admitted_evaluator_receipt"]["receipt_digest"] = summary[
        "receipt_digest"
    ]
    receipt_unsigned = {
        key: value for key, value in receipt.items() if key != "receipt_digest"
    }
    receipt["receipt_digest"] = canonical_digest(receipt_unsigned)
    _write(receipt_path, receipt)
    with pytest.raises(LiveOperatorError, match="implementation identity"):
        verify_live_operator_receipt(receipt_path)


def test_adapter_verifier_rejects_a_resealed_non_derived_consequence(
    tmp_path: Path,
) -> None:
    path, _, _, request_path = _trusted_adapter_campaign(tmp_path)
    output = tmp_path / "changed-consequence-output"
    run_live_operator(
        path,
        output_root=output,
        trusted_adapter_request_path=request_path,
    )
    adapter_receipt_path = output / "trusted_adapter" / "receipt.json"
    adapter_receipt = json.loads(adapter_receipt_path.read_text())
    changed_consequence = copy.deepcopy(adapter_receipt["consequence"])
    changed_consequence["status"] = "caller_changed_status"
    adapter_receipt["consequence"] = changed_consequence
    adapter_unsigned = {
        key: value
        for key, value in adapter_receipt.items()
        if key != "receipt_digest"
    }
    adapter_receipt["receipt_digest"] = canonical_digest(adapter_unsigned)
    _write(adapter_receipt_path, adapter_receipt)
    summary = json.loads((output / "admitted_evaluator_receipt.json").read_text())
    summary["adapter_receipt"] = adapter_receipt
    summary["receipt_sha256"] = sha256_file(adapter_receipt_path)
    summary["receipt_digest"] = adapter_receipt["receipt_digest"]
    contract = load_live_campaign_contract(path)
    with pytest.raises(LiveOperatorError, match="not independently derived"):
        verify_embedded_trusted_adapter_receipt(
            summary,
            contract=contract,
            expected_evaluator_identity=build_live_evaluator_identity(contract),
            expected_consequence=changed_consequence,
            expected_affected_factor_ids=[
                "factor:actuator_path",
                "factor:contact_patch",
            ],
            receipt_root=output,
            repo_root=Path(__file__).resolve().parents[1],
        )


def test_trusted_adapter_and_measurement_receipts_are_mutually_exclusive(
    tmp_path: Path,
) -> None:
    path, _, _, request_path = _trusted_adapter_campaign(tmp_path)
    with pytest.raises(LiveOperatorError, match="only one"):
        run_live_operator(
            path,
            output_root=tmp_path / "mutually-exclusive",
            measurement_evaluator_receipt_path=tmp_path / "measurement.json",
            trusted_adapter_request_path=request_path,
        )


def test_two_context_missing_invariance_vectors_are_not_imputed(tmp_path: Path) -> None:
    path, config = _campaign(tmp_path)
    changed = copy.deepcopy(config)
    changed["invariance"]["episode_contexts"] = [
        {"episode_id": "context-a", "level": "a", "feature": None, "observation": None, "actions": None},
        {"episode_id": "context-b", "level": "b", "feature": None, "observation": None, "actions": None},
    ]
    changed_path = _write(path.parent / "two-context-missing.json", changed)
    output = tmp_path / "two-context-output"
    run_live_operator(changed_path, output_root=output)
    invariance = json.loads((output / "invariance.json").read_text())
    assert invariance["verdict"] == "not_evaluable"
    assert invariance["missing_vector_episode_ids"] == ["context-a", "context-b"]
    assert not invariance["missing_vectors_imputed"]


def test_offline_measurement_features_return_all_preregistered_outcomes(
    tmp_path: Path,
) -> None:
    path, config = _campaign(tmp_path)
    contract = load_live_campaign_contract(path)
    output = tmp_path / "packet-output"
    run_live_operator(path, output_root=output)
    packet = json.loads((output / "acquisition_packet.json").read_text())

    flex_raw = json.loads(
        _measurement_raw(tmp_path / "flex-raw.json", config=config).read_text()
    )
    flex = evaluate_offline_measurement_trials(
        [flex_raw],
        campaign_id=contract.campaign_id,
        selected_intervention="probe-measurement-arbitrary",
        packet=packet,
        evaluation_contract=config["measurement_result_evaluation"],
    )
    assert flex["classification"] == "flexural_dominant"

    actuator_raw = json.loads(
        _measurement_raw(
            tmp_path / "actuator-raw.json",
            config=config,
            trial_id="measurement-trial-actuator",
            deformation=[1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0],
            current=[0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0],
            patch=[1.0, 1.0, 1.0, 1.05, 1.05, 1.0, 1.0],
        ).read_text()
    )
    actuator = evaluate_offline_measurement_trials(
        [actuator_raw],
        campaign_id=contract.campaign_id,
        selected_intervention="probe-measurement-arbitrary",
        packet=packet,
        evaluation_contract=config["measurement_result_evaluation"],
    )
    assert actuator["classification"] == "actuator_dominant"

    ambiguous_raw = copy.deepcopy(actuator_raw)
    ambiguous_raw["trials"][0]["trial_id"] = "measurement-trial-ambiguous"
    ambiguous_raw["trials"][0]["patch_area_mm2"] = [1.0, 1.0, 1.0, 2.0, 2.0, 1.0, 1.0]
    ambiguous = evaluate_offline_measurement_trials(
        [ambiguous_raw],
        campaign_id=contract.campaign_id,
        selected_intervention="probe-measurement-arbitrary",
        packet=packet,
        evaluation_contract=config["measurement_result_evaluation"],
    )
    assert ambiguous["classification"] == "ambiguous_abstention"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda trial, artifact: trial.__setitem__("sampling_hz", 99.0), "sampling rate"),
        (
            lambda trial, artifact: trial.__setitem__(
                "maximum_alignment_skew_samples", 2
            ),
            "alignment skew",
        ),
        (
            lambda trial, artifact: trial.__setitem__("calibration_completed", []),
            "calibration",
        ),
        (
            lambda trial, artifact: trial.__setitem__("phases_completed", []),
            "phases",
        ),
        (
            lambda trial, artifact: artifact["authority"].__setitem__(
                "physical_capture", True
            ),
            "authority",
        ),
    ],
)
def test_offline_measurement_preflight_fails_closed(
    tmp_path: Path, mutation: object, message: str
) -> None:
    path, config = _campaign(tmp_path)
    contract = load_live_campaign_contract(path)
    output = tmp_path / "preflight-output"
    run_live_operator(path, output_root=output)
    packet = json.loads((output / "acquisition_packet.json").read_text())
    raw = json.loads(_measurement_raw(tmp_path / "preflight-raw.json", config=config).read_text())
    mutation(raw["trials"][0], raw)  # type: ignore[operator]
    with pytest.raises(EvidenceAdmissionError, match=message):
        evaluate_offline_measurement_trials(
            [raw],
            campaign_id=contract.campaign_id,
            selected_intervention="probe-measurement-arbitrary",
            packet=packet,
            evaluation_contract=config["measurement_result_evaluation"],
        )


def test_measurement_receipt_rejects_a_resealed_but_changed_packet(tmp_path: Path) -> None:
    path, config = _campaign(tmp_path)
    output = tmp_path / "packet-tamper-output"
    run_live_operator(path, output_root=output)
    raw_path = _measurement_raw(tmp_path / "packet-tamper-raw.json", config=config)
    receipt_path = _measurement_receipt(
        tmp_path,
        config_path=path,
        config=config,
        packet_path=output / "acquisition_packet.json",
        raw_path=raw_path,
    )
    packet = json.loads((output / "acquisition_packet.json").read_text())
    packet["minimum_sampling_hz"] = 101
    unsigned_packet = {key: value for key, value in packet.items() if key != "packet_digest"}
    packet["packet_digest"] = canonical_digest(unsigned_packet)
    changed_packet = _write(tmp_path / "changed-packet.json", packet)
    receipt = json.loads(receipt_path.read_text())
    receipt["acquisition_packet"] = _binding(changed_packet)
    receipt.pop("receipt_digest")
    receipt["receipt_digest"] = canonical_digest(receipt)
    changed_receipt = _write(tmp_path / "changed-packet-receipt.json", receipt)
    with pytest.raises(LiveOperatorError, match="sealed packet"):
        run_live_operator(
            path,
            output_root=output,
            measurement_evaluator_receipt_path=changed_receipt,
        )


def test_offline_measurement_trials_require_one_common_clock(tmp_path: Path) -> None:
    path, config = _campaign(tmp_path)
    contract = load_live_campaign_contract(path)
    output = tmp_path / "clock-output"
    run_live_operator(path, output_root=output)
    packet = json.loads((output / "acquisition_packet.json").read_text())
    raw = json.loads(_measurement_raw(tmp_path / "clock-raw.json", config=config).read_text())
    second = copy.deepcopy(raw["trials"][0])
    second["trial_id"] = "measurement-trial-other-clock"
    second["clock_id"] = "synthetic-other-clock"
    raw["trials"].append(second)
    with pytest.raises(EvidenceAdmissionError, match="one clock"):
        evaluate_offline_measurement_trials(
            [raw],
            campaign_id=contract.campaign_id,
            selected_intervention="probe-measurement-arbitrary",
            packet=packet,
            evaluation_contract=config["measurement_result_evaluation"],
        )


def test_packet_bound_measurement_result_is_admitted_once_and_chain_is_validated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, config = _campaign(tmp_path)
    output = tmp_path / "measurement-output"
    first = run_live_operator(path, output_root=output)
    assert first["verdict"] == "abstain_measurement_acquisition_required"
    raw_path = _measurement_raw(tmp_path / "measurement-raw.json", config=config)
    receipt_path = _measurement_receipt(
        tmp_path,
        config_path=path,
        config=config,
        packet_path=output / "acquisition_packet.json",
        raw_path=raw_path,
    )

    banned = ("physical_gateway", "teleop_recording", "serial", "camera", "force_hardware")
    real_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object) -> object:
        if any(token in name for token in banned):
            raise AssertionError(f"device opener imported: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    admitted = run_live_operator(
        path,
        output_root=output,
        measurement_evaluator_receipt_path=receipt_path,
    )
    assert admitted["verdict"] == "measurement_evidence_flexural_dominant"
    assert admitted["budget"]["used_anchor_replays"] == 0
    assert admitted["budget"]["used_measurement_trials"] == 1
    assert not admitted["promotion"]
    repo_root = Path(__file__).resolve().parents[1]
    state_path = repo_root / admitted["campaign_state_path"]
    state = json.loads(state_path.read_text())
    assert len(state["events"]) == 1
    assert state["events"][0]["anchor_replay_ids"] == []
    assert state["events"][0]["measurement_trial_ids"] == [
        "measurement-trial-arbitrary-1"
    ]
    assert state["state_digest"] == canonical_digest(
        {key: value for key, value in state.items() if key != "state_digest"}
    )

    with pytest.raises(LiveOperatorError, match="replay"):
        run_live_operator(
            path,
            output_root=output,
            measurement_evaluator_receipt_path=receipt_path,
        )

    state["budget"]["used_measurement_trials"] = 0
    _write(state_path, state)
    with pytest.raises(EvidenceAdmissionError, match="state digest"):
        run_live_operator(path, output_root=output)


def test_canonical_state_is_config_bound_and_rejects_alternate_roots(
    tmp_path: Path,
) -> None:
    path, config = _campaign(tmp_path)
    contract = load_live_campaign_contract(path)
    repo_root = Path(__file__).resolve().parents[1]
    state_path = resolve_live_campaign_state_path(contract)
    assert state_path.is_relative_to(repo_root / "outputs" / "sail" / "live-campaign-state-v1")
    assert state_path.name == "campaign_state.json"
    assert len(state_path.parent.name) == 64

    for name, root in (
        ("absolute", str(tmp_path / "alternate-state")),
        ("escape", "outputs/sail/../alternate-state"),
        ("alternate", "outputs/sail/another-state-root"),
    ):
        changed = copy.deepcopy(config)
        changed["persistent_state"]["repo_relative_root"] = root
        changed_path = _write(path.parent / f"{name}-state-root.json", changed)
        with pytest.raises(LiveOperatorError, match="persistent state root"):
            load_live_campaign_contract(changed_path)


def test_identical_receipt_is_rejected_across_two_output_roots_by_shared_state(
    tmp_path: Path,
) -> None:
    path, config = _campaign(tmp_path)
    output_a = tmp_path / "output-a"
    output_b = tmp_path / "output-b"
    initial = run_live_operator(path, output_root=output_a)
    raw_path = _measurement_raw(tmp_path / "shared-state-raw.json", config=config)
    receipt_path = _measurement_receipt(
        tmp_path,
        config_path=path,
        config=config,
        packet_path=output_a / "acquisition_packet.json",
        raw_path=raw_path,
    )
    admitted = run_live_operator(
        path,
        output_root=output_a,
        measurement_evaluator_receipt_path=receipt_path,
    )
    assert admitted["campaign_state_path"] == initial["campaign_state_path"]
    repo_root = Path(__file__).resolve().parents[1]
    state_path = repo_root / admitted["campaign_state_path"]
    before = state_path.read_bytes()
    with pytest.raises(LiveOperatorError, match="replay"):
        run_live_operator(
            path,
            output_root=output_b,
            measurement_evaluator_receipt_path=receipt_path,
        )
    assert state_path.read_bytes() == before
    assert not (output_a / "campaign_state.json").exists()
    assert not (output_b / "campaign_state.json").exists()


def test_rejected_factor_poison_leaves_state_and_budget_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, config = _campaign(tmp_path)
    contract = load_live_campaign_contract(path)
    output = tmp_path / "poison-output"
    initial = run_live_operator(path, output_root=output)
    packet = json.loads((output / "acquisition_packet.json").read_text())
    raw_path = _measurement_raw(tmp_path / "poison-raw.json", config=config)
    receipt_path = _measurement_receipt(
        tmp_path,
        config_path=path,
        config=config,
        packet_path=output / "acquisition_packet.json",
        raw_path=raw_path,
    )
    measurement_intervention = next(
        row.payload for row in contract.interventions if row.kind == "measurement_acquisition"
    )
    admission = verify_measurement_evaluator_receipt(
        receipt_path,
        campaign_id=contract.campaign_id,
        selected_intervention=measurement_intervention,
        intervention_set_digest=contract.intervention_set_digest,
        action_sha256=ACTION_SHA,
        expected_evaluator_identity=build_live_evaluator_identity(contract),
        expected_packet=packet,
        evaluation_contract=config["measurement_result_evaluation"],
        remaining_measurement_trials=6,
    )
    poisoned = copy.deepcopy(admission)
    poisoned["result"]["factor_updates"] = {"factor:arm_tracking": 0.9}
    monkeypatch.setattr(
        live_runtime_module,
        "verify_measurement_evaluator_receipt",
        lambda *args, **kwargs: poisoned,
    )
    repo_root = Path(__file__).resolve().parents[1]
    state_path = repo_root / initial["campaign_state_path"]
    before = state_path.read_bytes()
    with pytest.raises(LiveOperatorError, match="unaffected factor update"):
        run_live_operator(
            path,
            output_root=tmp_path / "poison-rejected-output",
            measurement_evaluator_receipt_path=receipt_path,
        )
    assert state_path.read_bytes() == before
    state = json.loads(state_path.read_text())
    assert state["events"] == []
    assert state["budget"]["used_interventions"] == 0
    assert state["budget"]["used_measurement_trials"] == 0


def test_live_operator_receipt_verifier_rejects_artifact_and_authority_tamper(
    tmp_path: Path,
) -> None:
    path, _ = _campaign(tmp_path)
    output = tmp_path / "verify-output"
    result = run_live_operator(path, output_root=output)
    receipt_path = output / "receipt.json"
    verified = verify_live_operator_receipt(receipt_path)
    assert verified["receipt_sha256"] == result["receipt_sha256"]
    assert not verified["promotion"]

    trace_path = output / "operator_trace.json"
    trace_bytes = trace_path.read_bytes()
    trace = json.loads(trace_bytes)
    trace["agent_promoted"] = True
    _write(trace_path, trace)
    with pytest.raises(LiveOperatorError, match="output hash"):
        verify_live_operator_receipt(receipt_path)
    trace_path.write_bytes(trace_bytes)

    receipt_bytes = receipt_path.read_bytes()
    receipt = json.loads(receipt_bytes)
    receipt["promotion"] = True
    unsigned = {key: value for key, value in receipt.items() if key != "receipt_digest"}
    receipt["receipt_digest"] = canonical_digest(unsigned)
    _write(receipt_path, receipt)
    with pytest.raises(LiveOperatorError, match="promotion widened authority"):
        verify_live_operator_receipt(receipt_path)
    receipt_path.write_bytes(receipt_bytes)
    verify_live_operator_receipt(receipt_path)


def test_live_operator_receipt_verifier_rejects_stale_canonical_state(
    tmp_path: Path,
) -> None:
    path, config = _campaign(tmp_path)
    changed = copy.deepcopy(config)
    changed["budget"]["maximum_interventions"] = 2
    changed_path = _write(path.parent / "two-admission-campaign.json", changed)
    output_a = tmp_path / "stale-output-a"
    output_b = tmp_path / "stale-output-b"
    run_live_operator(changed_path, output_root=output_a)

    raw_a = _measurement_raw(tmp_path / "stale-raw-a.json", config=changed)
    receipt_a = _measurement_receipt(
        tmp_path,
        config_path=changed_path,
        config=changed,
        packet_path=output_a / "acquisition_packet.json",
        raw_path=raw_a,
        execution_id="measurement-execution-stale-a",
        result_name="measurement-result-stale-a.json",
        receipt_name="measurement-receipt-stale-a.json",
    )
    run_live_operator(
        changed_path,
        output_root=output_a,
        measurement_evaluator_receipt_path=receipt_a,
    )
    verify_live_operator_receipt(output_a / "receipt.json")

    raw_b = _measurement_raw(
        tmp_path / "stale-raw-b.json",
        config=changed,
        trial_id="measurement-trial-stale-b",
    )
    receipt_b = _measurement_receipt(
        tmp_path,
        config_path=changed_path,
        config=changed,
        packet_path=output_a / "acquisition_packet.json",
        raw_path=raw_b,
        execution_id="measurement-execution-stale-b",
        result_name="measurement-result-stale-b.json",
        receipt_name="measurement-receipt-stale-b.json",
    )
    run_live_operator(
        changed_path,
        output_root=output_b,
        measurement_evaluator_receipt_path=receipt_b,
    )
    verify_live_operator_receipt(output_b / "receipt.json")
    with pytest.raises(LiveOperatorError, match="stale against canonical campaign state"):
        verify_live_operator_receipt(output_a / "receipt.json")


def test_static_publication_is_read_only_and_matches_terminal_receipt() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    web_root = repo_root / "src" / "sim2claw" / "studio_web"
    manifest = json.loads(
        (web_root / "publication" / "sail_live_operator_v1" / "manifest.json").read_text()
    )
    assert manifest["verdict"] == "abstain_measurement_acquisition_required"
    assert manifest["action_sha256"] == "402a29e4cdc0c4cb90d41a83327ad8df5685544851b4e4d659129b3239744fd6"
    assert manifest["ablation"]["manual"] == {
        "completed_campaigns": 32,
        "simulator_evaluations": 514,
        "anchor_passes": 0,
        "abstention_quality": "no_global_abstention_incomplete_family_interrupted",
    }
    assert not any(
        value for key, value in manifest["authority"].items() if key != "read_only"
    )
    assert manifest["authority"]["read_only"]
    html = (web_root / "live-operator.html").read_text()
    script = (web_root / "live-operator.js").read_text()
    assert "read-only · no authority" in html
    assert "<button" not in html
    assert 'method: "POST"' not in script
    publication_receipt = json.loads(
        (web_root / "publication" / "sail_live_operator_v1" / "receipt.json").read_text()
    )
    assert publication_receipt["route"] == "/live-operator.html"
    assert publication_receipt["authority"]["read_only"]
    assert not publication_receipt["authority"]["physical_authority"]
    for relative, expected in publication_receipt["files"].items():
        assert sha256_file(repo_root / relative) == expected

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sim2claw.learning_factory_artifacts import canonical_digest, sha256_file
from sim2claw.sail.prospective_simulator import (
    ProspectiveSimulatorError,
    _compensating_fit,
    _signature_evaluation,
    build_experiment,
    load_config,
    run_campaign,
    verify_receipt,
)

REPO_ROOT = Path(__file__).parents[1]
CONFIG_PATH = REPO_ROOT / "configs/sail/prospective_simulator_v1.json"
OUTPUT_ROOT = REPO_ROOT / "outputs/sail/prospective-sim-v1"


def _raw_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _loaded() -> tuple[dict, dict[str, dict]]:
    raw = _raw_config()
    missing = [
        binding["path"]
        for binding in raw["source_bindings"].values()
        if not (REPO_ROOT / binding["path"]).is_file()
    ]
    if missing:
        pytest.skip("owner-local prospective sources unavailable: " + ", ".join(missing))
    config = load_config(CONFIG_PATH)
    sources = {
        name: json.loads((REPO_ROOT / binding["path"]).read_text(encoding="utf-8"))
        for name, binding in config["source_bindings"].items()
    }
    return config, sources


def test_preregistered_signature_rules_are_directional_and_fixed() -> None:
    config = _raw_config()
    rows = {
        "stride1_load0": {
            "dynamic_elbow_flex_rms_degrees": 10.0,
            "dynamic_overall_joint_rms_degrees": 10.0,
            "stationary_elbow_flex_rms_degrees": 10.0,
            "stationary_elbow_flex_absolute_signed_mean_error_degrees": 10.0,
        },
        "stride2_load0": {
            "dynamic_elbow_flex_rms_degrees": 11.0,
            "dynamic_overall_joint_rms_degrees": 12.0,
        },
        "stride1_loadm1500": {
            "dynamic_elbow_flex_rms_degrees": 9.0,
            "stationary_elbow_flex_rms_degrees": 8.0,
            "stationary_elbow_flex_absolute_signed_mean_error_degrees": 8.0,
        },
    }
    evaluated = _signature_evaluation(config, rows)
    assert evaluated["timing_delay"]["score"] == 1.0
    assert evaluated["load_compliance"]["score"] == 1.0
    assert all(
        row["matched"] is True
        for row in evaluated["load_compliance"]["signatures"]
    )


def test_compensating_fit_rule_uses_full_vector_guards() -> None:
    config = _raw_config()
    per_joint = {name: 10.0 for name in ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll")}
    rows = {
        "stride1_loadm1500": {
            "overall_joint_rms_degrees": 10.0,
            "ee_rms_m": 10.0,
            "per_joint_rms_degrees": per_joint,
            "dynamic_elbow_flex_rms_degrees": 10.0,
        },
        "stride2_loadm1500": {
            "overall_joint_rms_degrees": 9.0,
            "ee_rms_m": 10.3,
            "per_joint_rms_degrees": {**per_joint, "wrist_flex": 10.3},
            "dynamic_elbow_flex_rms_degrees": 10.3,
        },
    }
    result = _compensating_fit(config, rows)
    assert result["aggregate_joint_rms_improved"] is True
    assert result["rejected_as_compensating_fit"] is True
    assert set(result["guard_failures"]) == {
        "ee_rms_relative_regression",
        "per_joint_rms_relative_regression",
        "dynamic_elbow_rms_relative_regression",
    }


def test_config_fails_closed_if_authority_is_widened(tmp_path: Path) -> None:
    changed = _raw_config()
    changed["authority"]["training_admission"] = True
    path = tmp_path / "prospective.json"
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ProspectiveSimulatorError, match="authority widened"):
        load_config(path)


def test_action_tensor_and_declared_factorial_are_exact() -> None:
    config, sources = _loaded()
    experiment, trials, _states = build_experiment(config, sources)
    assert [row["trial_id"] for row in trials] == config["acceptance"]["required_trial_ids"]
    assert experiment["action_invariance"]["all_trial_shape_dtype_order_values_hash_identical"] is True
    assert {
        row["action_identity"]["sha256"] for row in trials
    } == {config["action_contract"]["sha256"]}
    assert experiment["execution_accounting"] == {
        "episode_count": 1,
        "declared_trial_count": 4,
        "executed_trial_count": 4,
        "retry_count": 0,
        "undeclared_trial_count": 0,
        "post_hoc_grid_expansion": False,
        "stopped_trial_count": 0,
        "all_results_retained": True,
    }


def test_observed_campaign_selects_timing_probe_without_physical_claim() -> None:
    _loaded()
    experiment = json.loads((OUTPUT_ROOT / "prospective_experiment.json").read_text(encoding="utf-8"))
    assert experiment["predicted_versus_observed_signatures"]["timing_delay"]["score"] == 1.0
    assert experiment["predicted_versus_observed_signatures"]["load_compliance"]["score"] == pytest.approx(2.0 / 3.0)
    assert experiment["loop_closure_next_probe"]["selected_next_probe_id"] == "sim_timing_rate_probe"
    assert experiment["frozen_simulator_family"]["selected_trial_id_for_simulator_diagnostic"] == "stride1_loadm1500"
    assert experiment["frozen_posterior_family"]["physical_parameter_posterior"] is False
    assert experiment["authority"]["twin_worthiness_data"] is False


def test_every_trial_retains_full_vector_and_missing_consequence_boundary() -> None:
    _loaded()
    experiment = json.loads((OUTPUT_ROOT / "prospective_experiment.json").read_text(encoding="utf-8"))
    expected_metrics = set(_raw_config()["evaluator"]["full_vector_metrics"])
    expected_missing = set(_raw_config()["evaluator"]["missing_consequence_channels"])
    for row in experiment["trial_results"]:
        assert expected_metrics <= set(row["metrics"])
        assert set(row["missing_consequence_channels"]) == expected_missing
        assert row["consequence_status"] == "not_evaluable_no_imputation"
        assert row["retention_status"].endswith("retained")


def test_graph_delta_and_phase2_freeze_are_source_bound() -> None:
    _loaded()
    graph = json.loads((OUTPUT_ROOT / "prospective_graph_delta.json").read_text(encoding="utf-8"))
    freeze = json.loads((OUTPUT_ROOT / "phase2_prediction_freeze.json").read_text(encoding="utf-8"))
    assert graph["graph_native"] is True
    assert graph["historical_graph_mutated"] is False
    assert len([node for node in graph["nodes"] if node["type"] == "candidate"]) == 4
    assert len([edge for edge in graph["edges"] if edge["type"] == "evaluated-on"]) == 4
    assert freeze["frozen_before_any_phase2_physical_observation"] is True
    assert freeze["physical_observations_consumed"] == 0
    assert len(freeze["predictions"]) == 3
    assert not any(freeze["authority"].values())


def test_run_is_deterministic_and_receipt_verifies(tmp_path: Path) -> None:
    _loaded()
    first = run_campaign(CONFIG_PATH, output_root=tmp_path / "campaign")
    receipt_sha = sha256_file(tmp_path / "campaign/receipt.json")
    second = run_campaign(CONFIG_PATH, output_root=tmp_path / "campaign")
    assert first["receipt_digest"] == second["receipt_digest"]
    assert receipt_sha == sha256_file(tmp_path / "campaign/receipt.json")
    receipt = json.loads((tmp_path / "campaign/receipt.json").read_text(encoding="utf-8"))
    verify_receipt(receipt, output_root=tmp_path / "campaign")


def test_receipt_tampering_fails_closed() -> None:
    _loaded()
    receipt = json.loads((OUTPUT_ROOT / "receipt.json").read_text(encoding="utf-8"))
    verify_receipt(receipt, output_root=OUTPUT_ROOT)
    changed = copy.deepcopy(receipt)
    changed["authority"]["training_admission"] = True
    unsigned = copy.deepcopy(changed)
    unsigned.pop("receipt_digest")
    changed["receipt_digest"] = canonical_digest(unsigned)
    with pytest.raises(ProspectiveSimulatorError, match="authority widened"):
        verify_receipt(changed, output_root=OUTPUT_ROOT)

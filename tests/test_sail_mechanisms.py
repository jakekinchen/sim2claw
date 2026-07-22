from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pytest

from sim2claw.sail.contracts import verify_contract
from sim2claw.sail.mechanisms import (
    MechanismError,
    build_mechanism_plugin,
)
from sim2claw.sail.posterior import (
    PosteriorError,
    fit_structure_particle,
    rank_structure_particles,
    run_seeded_mechanism_benchmarks,
    verify_mechanism_receipt,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "configs" / "sail" / "mechanism_registry_v1.json"
OUTPUT_ROOT = REPO_ROOT / "outputs" / "sail" / "retired-bg-v1" / "mechanisms"


@pytest.fixture(scope="module")
def registry_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def plugins(registry_config: dict) -> dict:
    return {
        row["mechanism_id"]: build_mechanism_plugin(row)
        for row in registry_config["plugins"]
    }


@pytest.fixture(scope="module")
def seeded_benchmarks(plugins: dict, registry_config: dict) -> dict:
    return run_seeded_mechanism_benchmarks(plugins, registry_config)


def test_registry_plugins_satisfy_physical_mechanism_v1(plugins: dict) -> None:
    assert len(plugins) == 10
    for plugin in plugins.values():
        assert verify_contract(plugin.contract) == plugin.contract
        assert plugin.contract["predicted_residual_signatures"]
        assert plugin.contract["required_observables"]
        assert plugin.contract["action_immutability_tests"] == ["sha256_before_equals_after"]


def test_parameter_bounds_fail_closed(plugins: dict) -> None:
    with pytest.raises(MechanismError, match="outside declared bounds"):
        plugins["load_compliance_v1"].validate_parameters({"load_bias_coefficient": 2.01})
    with pytest.raises(MechanismError, match="parameter set changed"):
        plugins["load_compliance_v1"].validate_parameters({"wrong": 0.0})


def test_unsupported_mechanism_abstains_without_imputation(plugins: dict) -> None:
    actions = np.arange(18, dtype=np.float32).reshape(3, 6)
    particle = fit_structure_particle(
        plugins["fingertip_contact_v1"],
        design={},
        observations=[],
        available_observables=[],
        seed=7,
        bootstrap_replicates=10,
        confidence_level=0.95,
        actions=actions,
    )
    assert particle["status"] == "abstain_missing_observables"
    assert particle["parameters"] is None
    assert particle["missing_observables"] == [
        "physical_contact_force_or_proxy",
        "physical_contact_state",
    ]


def test_gold_06_load_structure_recovery(seeded_benchmarks: dict) -> None:
    case = next(row for row in seeded_benchmarks["cases"] if row["case_id"] == "GOLD-06")
    assert case["winner"] == "load_compliance_v1"
    assert case["ranking"][0]["bic"] < case["ranking"][1]["bic"]
    fitted = next(row for row in case["particles"] if row["mechanism_id"] == "load_compliance_v1")
    assert fitted["parameters"][0]["value"] == pytest.approx(-0.75, abs=0.02)


def test_gold_07_contact_structure_recovery(seeded_benchmarks: dict) -> None:
    case = next(row for row in seeded_benchmarks["cases"] if row["case_id"] == "GOLD-07")
    assert case["winner"] == "fingertip_contact_v1"
    assert case["action_bytes_unchanged"] is True
    fitted = next(row for row in case["particles"] if row["mechanism_id"] == "fingertip_contact_v1")
    parameters = {row["name"]: row["value"] for row in fitted["parameters"]}
    assert parameters["contact_threshold_m"] == pytest.approx(0.003, abs=0.0002)
    assert parameters["contact_gain"] == pytest.approx(5.0, abs=0.1)


def test_gold_08_camera_fault_attribution(seeded_benchmarks: dict) -> None:
    case = next(row for row in seeded_benchmarks["cases"] if row["case_id"] == "GOLD-08")
    assert case["winner"] == "camera_timing_extrinsics_v1"
    assert case["ranking"][1]["mechanism_id"] == "metric_geometry_v1"
    fitted = next(
        row for row in case["particles"] if row["mechanism_id"] == "camera_timing_extrinsics_v1"
    )
    parameters = {row["name"]: row["value"] for row in fitted["parameters"]}
    assert parameters["camera_latency_s"] == pytest.approx(0.06, abs=0.005)
    assert parameters["camera_yaw_rad"] == pytest.approx(0.2, abs=0.005)


def test_posterior_samples_remain_inside_bounds_and_structures_stay_separate(
    seeded_benchmarks: dict,
) -> None:
    for case in seeded_benchmarks["cases"]:
        assert case["structures_averaged"] is False
        assert len(case["particles"]) == 2
        for particle in case["particles"]:
            for parameter in particle["parameters"]:
                assert parameter["minimum"] <= parameter["value"] <= parameter["maximum"]
                low, high = parameter["bootstrap_interval"]
                assert parameter["minimum"] <= low <= high <= parameter["maximum"]
        ranked_ids = {row["particle_id"] for row in case["ranking"]}
        assert ranked_ids == {row["particle_id"] for row in case["particles"]}


def test_prediction_preserves_action_bytes(plugins: dict) -> None:
    actions = np.arange(30, dtype=np.float64).reshape(5, 6)
    before = actions.tobytes()
    prediction = plugins["load_compliance_v1"].predict(
        {"load": np.linspace(-1.0, 1.0, 5)},
        {"load_bias_coefficient": -0.5},
        actions=actions,
    )
    assert prediction.shape == (5,)
    assert actions.tobytes() == before


def test_bootstrap_fit_is_deterministic(plugins: dict) -> None:
    actions = np.zeros((20, 6), dtype=np.float32)
    load = np.linspace(-1.0, 1.0, 20)
    kwargs = {
        "design": {"load": load},
        "observations": -0.5 * load,
        "available_observables": plugins["load_compliance_v1"].contract[
            "required_observables"
        ],
        "seed": 55,
        "bootstrap_replicates": 20,
        "confidence_level": 0.95,
        "actions": actions,
    }
    first = fit_structure_particle(plugins["load_compliance_v1"], **kwargs)
    second = fit_structure_particle(plugins["load_compliance_v1"], **kwargs)
    assert first == second
    assert first["particle_digest"] == second["particle_digest"]


def test_ranking_does_not_merge_incompatible_particles(seeded_benchmarks: dict) -> None:
    particles = seeded_benchmarks["cases"][0]["particles"]
    ranked = rank_structure_particles(list(reversed(particles)))
    assert len(ranked) == 2
    assert all("parameters" not in row for row in ranked)
    assert len({row["particle_digest"] for row in ranked}) == 2


@pytest.mark.skipif(
    not (OUTPUT_ROOT / "registry.json").is_file(),
    reason="owner-local retained mechanism artifacts are unavailable",
)
def test_historical_wrappers_reproduce_without_result_mutation() -> None:
    artifact = json.loads((OUTPUT_ROOT / "registry.json").read_text(encoding="utf-8"))
    assert len(artifact["plugins"]) == 10
    wrappers = [row["historical_wrapper"] for row in artifact["plugins"]]
    assert all(row["historical_result_mutated"] is False for row in wrappers)
    assert next(row for row in wrappers if row["mechanism_id"] == "timing_delay_v1")[
        "parameters"
    ] == {"delay_s": 0.11}
    assert next(row for row in wrappers if row["mechanism_id"] == "simulation_timestep_v1")[
        "parameters"
    ] == {"timestep_multiplier": 0.45}


def test_retained_missing_mechanisms_abstain() -> None:
    path = OUTPUT_ROOT / "retained_particles.json"
    if not path.is_file():
        pytest.skip("owner-local retained mechanism artifacts are unavailable")
    artifact = json.loads(path.read_text(encoding="utf-8"))
    abstentions = [row for row in artifact["particles"] if row["status"] == "abstain_missing_observables"]
    assert {row["mechanism_id"] for row in abstentions} == {
        "camera_timing_extrinsics_v1",
        "contact_friction_v1",
        "fingertip_contact_v1",
        "load_compliance_v1",
        "object_dynamics_v1",
    }
    assert artifact["structures_averaged"] is False
    assert artifact["physical_mechanism_identified"] is False


def test_mechanism_receipt_binds_outputs_and_authority() -> None:
    path = OUTPUT_ROOT / "receipt.json"
    if not path.is_file():
        pytest.skip("owner-local retained mechanism receipt is unavailable")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    verify_mechanism_receipt(receipt, output_root=OUTPUT_ROOT)
    changed = copy.deepcopy(receipt)
    changed["authority"]["physical_mechanism_identification"] = True
    with pytest.raises(PosteriorError, match="digest mismatch|widened authority"):
        verify_mechanism_receipt(changed, output_root=OUTPUT_ROOT)

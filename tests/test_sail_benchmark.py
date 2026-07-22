from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sim2claw.sail.benchmark import BenchmarkError, build_benchmark, verify_benchmark_receipt

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((REPO_ROOT / "configs/sail/seeded_benchmark_v1.json").read_text())
REGISTRY = json.loads((REPO_ROOT / "tests/fixtures/sail/golden_cases_v1.json").read_text())


@pytest.fixture(scope="module")
def benchmark() -> dict:
    return build_benchmark(CONFIG, REGISTRY)


def test_eight_required_fault_families_and_case_types(benchmark: dict) -> None:
    score = benchmark["scorecard"]
    assert score["case_count"] == 8
    assert len(score["fault_families"]) == 8
    sealed_types = {row["case_type"] for row in benchmark["sealed"]["rows"]}
    assert {"single_fault", "compensating_two_fault", "context_specific", "missing_observable", "distractor_history"} <= sealed_types


def test_public_and_sealed_bytes_are_disjoint(benchmark: dict) -> None:
    assert benchmark["scorecard"]["public_sealed_disjoint"] is True
    public_text = json.dumps(benchmark["public"], sort_keys=True)
    assert "hidden_mechanisms" not in public_text
    assert "oracle_influence_set" not in public_text
    assert benchmark["sealed"]["evaluator_only"] is True


def test_oracle_repairs_beat_unchanged_and_incorrect_controls(benchmark: dict) -> None:
    assert all(row["oracle_beats_controls"] for row in benchmark["scorecard"]["controls"])


def test_methods_cannot_mutate_action_or_evaluator(benchmark: dict) -> None:
    score = benchmark["scorecard"]
    assert score["action_bytes_unchanged"] is True
    assert score["evaluator_state_unchanged"] is True
    assert score["sealed_access_by_method"] is False
    assert score["provider_calls"] == 0


def test_all_primary_metrics_emitted(benchmark: dict) -> None:
    required = {"mechanism_family_top1_accuracy", "mechanism_family_topk_accuracy", "influence_precision", "influence_recall", "sealed_residual_improvement", "regression_count", "calibration_regret_vs_oracle", "probes_to_threshold", "simulator_evaluations", "false_structural_trigger_rate", "false_promotion_rate", "compensation_debt_reduction", "graph_recomputation_cost", "prediction_calibration_error", "twinworthiness_false_positive_rate", "twinworthiness_false_negative_rate"}
    assert len(benchmark["scorecard"]["methods"]) == 10
    assert all(required <= set(row) for row in benchmark["scorecard"]["methods"])


def test_all_25_golden_entrypoints_resolve(benchmark: dict) -> None:
    assert len(benchmark["scorecard"]["golden_cases"]) == 25
    assert benchmark["scorecard"]["all_synthetic_golden_cases_pass"] is True


def test_benchmark_is_deterministic() -> None:
    assert build_benchmark(CONFIG, REGISTRY) == build_benchmark(CONFIG, REGISTRY)


def test_seed_domains_must_not_overlap() -> None:
    changed = dict(CONFIG)
    changed["sealed_seed"] = changed["public_seed"]
    with pytest.raises(BenchmarkError, match="leakage"):
        build_benchmark(changed, REGISTRY)


def test_benchmark_receipt_rejects_tampering() -> None:
    output_root = REPO_ROOT / "outputs/sail/seeded-benchmark-v1"
    path = output_root / "receipt.json"
    if not path.is_file():
        pytest.skip("owner-local benchmark receipt unavailable")
    receipt = json.loads(path.read_text())
    verify_benchmark_receipt(receipt, output_root=output_root)
    changed = copy.deepcopy(receipt)
    changed["authority"]["sealed_access_by_method"] = True
    with pytest.raises(BenchmarkError, match="digest mismatch|widened authority"):
        verify_benchmark_receipt(changed, output_root=output_root)

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

import sim2claw.sail.executed_benchmark as executed
from sim2claw.learning_factory_artifacts import canonical_digest
from sim2claw.sail.executed_benchmark import (
    ExecutedBenchmarkError,
    build_executed_benchmark,
    compile_executed_benchmark,
    verify_executed_benchmark_receipt,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "configs/sail/seeded_benchmark_v2.json"
SEALED_PATH = (
    REPO_ROOT / "configs/sail/evaluator/seeded_benchmark_v2_sealed.json"
)
GOLDEN_PATH = REPO_ROOT / "tests/fixtures/sail/golden_cases_v1.json"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _build(
    *,
    config: dict[str, Any] | None = None,
    sealed: dict[str, Any] | None = None,
    golden: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_executed_benchmark(
        config or _load(CONFIG_PATH),
        sealed or _load(SEALED_PATH),
        golden or _load(GOLDEN_PATH),
        golden_runner=lambda node_ids, repo_root: (
            0 if len(node_ids) == 25 and repo_root == REPO_ROOT else 1
        ),
    )


def _resign(output: dict[str, Any]) -> dict[str, Any]:
    changed = copy.deepcopy(output)
    changed.pop("output_digest", None)
    changed["output_digest"] = canonical_digest(changed)
    return changed


def test_registered_methods_execute_and_evaluator_scores_outputs() -> None:
    built = _build()
    scorecard = built["scorecard"]
    assert len(built["predictions"]) == 64
    assert scorecard["candidate_method_count"] == 8
    assert scorecard["evaluator_control_count"] == 4
    assert built["accounting"] == {
        "method_executions": 64,
        "probes": 54,
        "recomputation": 125,
        "simulator_evaluations": 54,
        "abstentions": 6,
        "failures": 0,
        "provider_calls": 0,
    }
    sail = next(
        row
        for row in scorecard["comparisons"]
        if row["method_id"] == "sail_deterministic_v2"
    )
    assert sail["result_vs_parameter_only"] in {"gain", "tie", "loss"}
    assert all(
        "recovery_threshold_rate" in row
        for row in scorecard["candidate_methods"]
    )
    assert scorecard["candidate_self_scores_used"] is False
    assert scorecard["sealed_truth_disclosed_to_candidate_methods"] is False


def test_public_payload_excludes_every_sealed_scoring_field() -> None:
    built = _build()
    public_bytes = json.dumps(built["public"], sort_keys=True)
    for name in executed.FORBIDDEN_PUBLIC_FIELDS:
        assert f'"{name}"' not in public_bytes
    assert built["public"]["sealed_fields_present"] is False
    assert "not_cryptographic_or_hostile_code_sandboxing" in (
        built["public"]["isolation_guarantee"]
    )


def test_golden_checks_are_executed_and_failure_is_rejected() -> None:
    observed: list[str] = []

    def runner(node_ids: list[str], repo_root: Path) -> int:
        assert repo_root == REPO_ROOT
        observed.extend(node_ids)
        return 0

    executed.execute_golden_checks(
        _load(GOLDEN_PATH), repo_root=REPO_ROOT, runner=runner
    )
    assert len(observed) == 25
    assert all("::test_" in node_id for node_id in observed)
    with pytest.raises(ExecutedBenchmarkError, match="golden checks failed"):
        executed.execute_golden_checks(
            _load(GOLDEN_PATH),
            repo_root=REPO_ROOT,
            runner=lambda node_ids, repo_root: 7,
        )


def test_sealed_field_leakage_is_rejected() -> None:
    config = _load(CONFIG_PATH)
    config["public_cases"][0]["hidden_mechanisms"] = ["leaked"]
    with pytest.raises(ExecutedBenchmarkError, match="leaked sealed truth"):
        _build(config=config)


def test_method_substitution_is_rejected() -> None:
    config = _load(CONFIG_PATH)
    config["candidate_methods"][0]["callable"] = "sail_deterministic"
    with pytest.raises(ExecutedBenchmarkError, match="substitution"):
        _build(config=config)


def test_action_mutation_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    original = executed.execute_registered_method

    def mutate(payload: dict[str, Any]) -> dict[str, Any]:
        output = original(payload)
        output["action_sha256"] = "0" * 64
        return _resign(output)

    monkeypatch.setattr(executed, "execute_registered_method", mutate)
    with pytest.raises(ExecutedBenchmarkError, match="identity or action changed"):
        _build()


def test_malformed_self_scored_or_self_promoting_output_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = executed.execute_registered_method

    def self_score(payload: dict[str, Any]) -> dict[str, Any]:
        output = original(payload)
        output["score"] = 1.0
        output["promotion"] = True
        return _resign(output)

    monkeypatch.setattr(executed, "execute_registered_method", self_score)
    with pytest.raises(ExecutedBenchmarkError, match="self-scored"):
        _build()


def test_budget_overrun_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    original = executed.execute_registered_method

    def overrun(payload: dict[str, Any]) -> dict[str, Any]:
        output = original(payload)
        output["budget"]["provider_calls"] = 1
        return _resign(output)

    monkeypatch.setattr(executed, "execute_registered_method", overrun)
    with pytest.raises(ExecutedBenchmarkError, match="provider_calls budget"):
        _build()


def test_replayed_output_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    original = executed.execute_registered_method
    first: dict[str, dict[str, Any]] = {}

    def replay(payload: dict[str, Any]) -> dict[str, Any]:
        if first:
            return copy.deepcopy(first["output"])
        first["output"] = original(payload)
        return copy.deepcopy(first["output"])

    monkeypatch.setattr(executed, "execute_registered_method", replay)
    with pytest.raises(ExecutedBenchmarkError, match="identity or action changed"):
        _build()


def test_duplicate_case_ids_are_rejected() -> None:
    config = _load(CONFIG_PATH)
    config["public_cases"][1]["case_id"] = config["public_cases"][0]["case_id"]
    with pytest.raises(ExecutedBenchmarkError, match="case ids repeat"):
        _build(config=config)


def test_posthoc_threshold_or_sealed_truth_change_is_rejected() -> None:
    sealed = _load(SEALED_PATH)
    sealed["scoring_thresholds"]["maximum_residual_prediction_error"] = 0.99
    with pytest.raises(ExecutedBenchmarkError, match="frozen source binding"):
        _build(sealed=sealed)


def test_evaluator_mutation_during_scoring_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = executed.evaluate_predictions

    def mutate(**kwargs: Any) -> dict[str, Any]:
        result = original(**kwargs)
        sealed = kwargs["sealed_config"]
        assert isinstance(sealed, dict)
        sealed["scoring_thresholds"]["topk_maximum"] = 999
        return result

    monkeypatch.setattr(executed, "evaluate_predictions", mutate)
    with pytest.raises(ExecutedBenchmarkError, match="evaluator state mutated"):
        _build()


def test_repeated_materialization_is_byte_identical(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    runner = lambda node_ids, repo_root: 0
    compile_executed_benchmark(
        CONFIG_PATH, output_root=first, golden_runner=runner
    )
    compile_executed_benchmark(
        CONFIG_PATH, output_root=second, golden_runner=runner
    )
    first_paths = sorted(
        path.relative_to(first) for path in first.rglob("*") if path.is_file()
    )
    second_paths = sorted(
        path.relative_to(second) for path in second.rglob("*") if path.is_file()
    )
    assert first_paths == second_paths
    for relative in first_paths:
        assert (first / relative).read_bytes() == (second / relative).read_bytes()


def test_receipt_rejects_output_tampering(tmp_path: Path) -> None:
    compile_executed_benchmark(
        CONFIG_PATH,
        output_root=tmp_path,
        golden_runner=lambda node_ids, repo_root: 0,
    )
    receipt = _load(tmp_path / "receipt.json")
    verify_executed_benchmark_receipt(receipt, output_root=tmp_path)
    (tmp_path / "scorecard.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ExecutedBenchmarkError, match="output changed"):
        verify_executed_benchmark_receipt(receipt, output_root=tmp_path)

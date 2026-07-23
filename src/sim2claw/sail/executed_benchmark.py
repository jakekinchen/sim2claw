"""Versioned evaluator-executed SAIL structural benchmark."""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from ..learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    sha256_file,
)
from .benchmark_evaluator import (
    SEALED_SCHEMA,
    evaluate_predictions,
)
from .benchmark_methods import (
    PREDICTION_SCHEMA,
    execute_registered_method,
    registered_methods,
)
from .contracts import REPO_ROOT, SailContractError, verify_source_binding
from .importers import load_json_object


CONFIG_SCHEMA = "sim2claw.sail_executed_benchmark_campaign.v2"
PUBLIC_SCHEMA = "sim2claw.sail_executed_benchmark_public.v2"
GOLDEN_SCHEMA = "sim2claw.sail_executed_golden_execution.v2"
RECEIPT_SCHEMA = "sim2claw.sail_executed_benchmark_receipt.v2"
METHOD_MODULE_PATH = "src/sim2claw/sail/benchmark_methods.py"
EVALUATOR_MODULE_PATH = "src/sim2claw/sail/benchmark_evaluator.py"
COMPILER_MODULE_PATH = "src/sim2claw/sail/executed_benchmark.py"
FORBIDDEN_PUBLIC_FIELDS = {
    "hidden_mechanisms",
    "oracle_influence_set",
    "heldout_residual_reduction",
    "regression_count",
    "abstention_expected",
    "scoring_thresholds",
    "evaluator_controls",
    "score",
    "promotion",
}
ISOLATION_GUARANTEE = (
    "trusted_in_repository_callables_receive_deep_copied_public_payloads_only;"
    "input_output_action_method_and_evaluator_identities_are_digest_checked;"
    "this_is_not_cryptographic_or_hostile_code_sandboxing"
)


class ExecutedBenchmarkError(SailContractError):
    """The executed benchmark crossed its frozen method/evaluator boundary."""


GoldenRunner = Callable[[Sequence[str], Path], int]


def _array_sha256(values: object, *, dtype: str, shape: Sequence[int]) -> str:
    if dtype != "float64":
        raise ExecutedBenchmarkError("benchmark action dtype changed")
    array = np.ascontiguousarray(np.asarray(values, dtype=np.float64))
    if list(array.shape) != [int(value) for value in shape]:
        raise ExecutedBenchmarkError("benchmark action shape changed")
    if not np.all(np.isfinite(array)):
        raise ExecutedBenchmarkError("benchmark action contains non-finite values")
    return hashlib.sha256(array.tobytes()).hexdigest()


def _all_false(value: object, *, label: str) -> dict[str, bool]:
    if not isinstance(value, Mapping) or not value:
        raise ExecutedBenchmarkError(f"{label} authority is missing")
    normalized = dict(value)
    if any(flag is not False for flag in normalized.values()):
        raise ExecutedBenchmarkError(f"{label} authority widened")
    return normalized


def _validate_public_case(raw: Mapping[str, Any]) -> dict[str, Any]:
    case = copy.deepcopy(dict(raw))
    expected = {
        "case_id",
        "candidate_mechanisms",
        "residual_scores",
        "probe_catalog",
        "influence_candidates",
        "influence_universe",
        "required_observable_available",
        "action",
    }
    if set(case) != expected or FORBIDDEN_PUBLIC_FIELDS & set(case):
        raise ExecutedBenchmarkError("public case field set changed or leaked sealed truth")
    case_id = case["case_id"]
    candidates = case["candidate_mechanisms"]
    residuals = case["residual_scores"]
    probes = case["probe_catalog"]
    influence = case["influence_candidates"]
    universe = case["influence_universe"]
    if (
        not isinstance(case_id, str)
        or not case_id
        or not isinstance(candidates, list)
        or len(candidates) < 2
        or len(candidates) != len(set(candidates))
        or not isinstance(residuals, Mapping)
        or set(residuals) != set(candidates)
        or not isinstance(probes, list)
        or not probes
        or not isinstance(influence, Mapping)
        or set(influence) != set(candidates)
        or not isinstance(universe, list)
        or len(universe) != len(set(universe))
        or not isinstance(case["required_observable_available"], bool)
    ):
        raise ExecutedBenchmarkError("public case contract is malformed")
    for value in residuals.values():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ExecutedBenchmarkError("public residual score is invalid")
        if not 0.0 <= float(value) <= 1.0:
            raise ExecutedBenchmarkError("public residual score is out of bounds")
    probe_ids = []
    for probe in probes:
        if not isinstance(probe, Mapping) or set(probe) != {
            "probe_id",
            "cost",
            "evidence_by_mechanism",
        }:
            raise ExecutedBenchmarkError("public probe contract is malformed")
        probe_ids.append(str(probe["probe_id"]))
        evidence = probe["evidence_by_mechanism"]
        if not isinstance(evidence, Mapping) or set(evidence) != set(candidates):
            raise ExecutedBenchmarkError("public probe mechanism coverage changed")
        if (
            isinstance(probe["cost"], bool)
            or not isinstance(probe["cost"], (int, float))
            or float(probe["cost"]) < 0.0
        ):
            raise ExecutedBenchmarkError("public probe cost is invalid")
        for value in evidence.values():
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0.0 <= float(value) <= 1.0
            ):
                raise ExecutedBenchmarkError("public probe evidence is invalid")
    if len(probe_ids) != len(set(probe_ids)):
        raise ExecutedBenchmarkError("public probe ids repeat")
    if any(
        not isinstance(rows, list)
        or any(str(value) not in set(universe) for value in rows)
        for rows in influence.values()
    ):
        raise ExecutedBenchmarkError("public influence candidates are invalid")
    action = case["action"]
    if not isinstance(action, Mapping) or set(action) != {
        "shape",
        "dtype",
        "ordering",
        "values",
        "sha256",
        "byte_identical",
    }:
        raise ExecutedBenchmarkError("public action contract changed")
    observed_action = _array_sha256(
        action["values"], dtype=str(action["dtype"]), shape=action["shape"]
    )
    if (
        action["ordering"] != "C_row_major_time_joint"
        or action["sha256"] != observed_action
        or action["byte_identical"] is not True
    ):
        raise ExecutedBenchmarkError("public action identity changed")
    case["action_sha256"] = observed_action
    case.pop("action")
    case["action_contract"] = copy.deepcopy(dict(action))
    return case


def _validate_config(
    config: Mapping[str, Any], *, repo_root: Path
) -> tuple[dict[str, Any], dict[str, Path]]:
    normalized = copy.deepcopy(dict(config))
    if normalized.get("schema_version") != CONFIG_SCHEMA:
        raise ExecutedBenchmarkError("unexpected executed benchmark config schema")
    _all_false(normalized.get("authority"), label="executed benchmark config")
    if normalized.get("isolation_guarantee") != ISOLATION_GUARANTEE:
        raise ExecutedBenchmarkError("executed benchmark isolation claim changed")
    budget = normalized.get("budget_per_case")
    if not isinstance(budget, Mapping) or set(budget) != {
        "maximum_probes",
        "maximum_recomputation",
        "maximum_simulator_evaluations",
        "maximum_provider_calls",
    }:
        raise ExecutedBenchmarkError("executed benchmark budget changed")
    if any(int(value) < 0 for value in budget.values()):
        raise ExecutedBenchmarkError("executed benchmark budget is negative")
    methods = normalized.get("candidate_methods")
    if not isinstance(methods, list) or not methods:
        raise ExecutedBenchmarkError("executed benchmark candidate registry is empty")
    registry = registered_methods()
    observed_ids = []
    for spec in methods:
        if not isinstance(spec, Mapping) or set(spec) != {
            "method_id",
            "callable",
            "module",
        }:
            raise ExecutedBenchmarkError("executed benchmark method spec changed")
        method_id = str(spec["method_id"])
        callable_name = str(spec["callable"])
        observed_ids.append(method_id)
        method = registry.get(method_id)
        if (
            method is None
            or method.__name__ != callable_name
            or method.__module__ != spec["module"]
        ):
            raise ExecutedBenchmarkError("candidate method substitution rejected")
    if len(observed_ids) != len(set(observed_ids)) or set(observed_ids) != set(registry):
        raise ExecutedBenchmarkError("candidate method inventory changed")
    cases = normalized.get("public_cases")
    if not isinstance(cases, list) or not cases:
        raise ExecutedBenchmarkError("executed benchmark public cases are missing")
    case_ids = [str(row.get("case_id", "")) for row in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ExecutedBenchmarkError("executed benchmark public case ids repeat")
    sources = {
        name: verify_source_binding(binding, repo_root=repo_root)
        for name, binding in normalized["source_bindings"].items()
    }
    return normalized, sources


def _validate_prediction(
    output: Mapping[str, Any],
    *,
    method_id: str,
    callable_name: str,
    public_case: Mapping[str, Any],
    execution_id: str,
    budget: Mapping[str, Any],
) -> dict[str, Any]:
    prediction = copy.deepcopy(dict(output))
    expected_fields = {
        "schema_version",
        "method_id",
        "case_id",
        "execution_id",
        "action_sha256",
        "ranked_mechanisms",
        "influence_set",
        "selected_probe_ids",
        "predictions",
        "abstain",
        "budget",
        "authority",
        "output_digest",
    }
    if set(prediction) != expected_fields:
        raise ExecutedBenchmarkError(
            f"candidate method emitted malformed or self-scored output: {method_id}"
        )
    unsigned = copy.deepcopy(prediction)
    observed_digest = unsigned.pop("output_digest", None)
    if observed_digest != canonical_digest(unsigned):
        raise ExecutedBenchmarkError("candidate prediction digest mismatch")
    if (
        prediction["schema_version"] != PREDICTION_SCHEMA
        or prediction["method_id"] != method_id
        or prediction["case_id"] != public_case["case_id"]
        or prediction["execution_id"] != execution_id
        or prediction["action_sha256"] != public_case["action_sha256"]
    ):
        raise ExecutedBenchmarkError("candidate method identity or action changed")
    ranked = prediction["ranked_mechanisms"]
    influence = prediction["influence_set"]
    probes = prediction["selected_probe_ids"]
    if (
        not isinstance(ranked, list)
        or len(ranked) != len(set(ranked))
        or any(value not in public_case["candidate_mechanisms"] for value in ranked)
        or not isinstance(influence, list)
        or len(influence) != len(set(influence))
        or any(value not in public_case["influence_universe"] for value in influence)
        or not isinstance(probes, list)
        or len(probes) != len(set(probes))
        or any(
            value
            not in {row["probe_id"] for row in public_case["probe_catalog"]}
            for value in probes
        )
        or not isinstance(prediction["abstain"], bool)
    ):
        raise ExecutedBenchmarkError("candidate prediction values are invalid")
    if prediction["abstain"] and (ranked or influence):
        raise ExecutedBenchmarkError("abstaining candidate emitted a substantive result")
    predicted = prediction["predictions"]
    if not isinstance(predicted, Mapping) or set(predicted) != {
        "heldout_residual_reduction",
        "regression_count",
    }:
        raise ExecutedBenchmarkError("candidate held-out prediction contract changed")
    residual = predicted["heldout_residual_reduction"]
    regression = predicted["regression_count"]
    if (
        isinstance(residual, bool)
        or not isinstance(residual, (int, float))
        or not 0.0 <= float(residual) <= 1.0
        or isinstance(regression, bool)
        or not isinstance(regression, int)
        or regression < 0
    ):
        raise ExecutedBenchmarkError("candidate held-out prediction is invalid")
    accounting = prediction["budget"]
    if not isinstance(accounting, Mapping) or set(accounting) != {
        "probes",
        "recomputation",
        "simulator_evaluations",
        "abstentions",
        "failures",
        "provider_calls",
    }:
        raise ExecutedBenchmarkError("candidate budget accounting changed")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in accounting.values()
    ):
        raise ExecutedBenchmarkError("candidate budget accounting is invalid")
    for name, maximum_name in (
        ("probes", "maximum_probes"),
        ("recomputation", "maximum_recomputation"),
        ("simulator_evaluations", "maximum_simulator_evaluations"),
        ("provider_calls", "maximum_provider_calls"),
    ):
        if int(accounting[name]) > int(budget[maximum_name]):
            raise ExecutedBenchmarkError(
                f"candidate method exceeded {name} budget: {method_id}"
            )
    if accounting["abstentions"] != int(prediction["abstain"]):
        raise ExecutedBenchmarkError("candidate abstention accounting changed")
    if accounting["failures"] != 0:
        raise ExecutedBenchmarkError("candidate self-reported a failure as a result")
    _all_false(prediction["authority"], label="candidate prediction")
    return prediction


def _default_golden_runner(node_ids: Sequence[str], repo_root: Path) -> int:
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *node_ids],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return int(completed.returncode)


def execute_golden_checks(
    registry: Mapping[str, Any],
    *,
    repo_root: Path,
    runner: GoldenRunner | None = None,
) -> dict[str, Any]:
    cases = registry.get("cases")
    if not isinstance(cases, list) or len(cases) != 25:
        raise ExecutedBenchmarkError("golden registry count changed")
    node_ids = [str(row["test"]) for row in cases]
    if len(node_ids) != len(set(node_ids)):
        raise ExecutedBenchmarkError("golden entrypoint inventory repeats")
    exit_code = (runner or _default_golden_runner)(node_ids, repo_root)
    if exit_code != 0:
        raise ExecutedBenchmarkError("declared golden checks failed during execution")
    unsigned = {
        "schema_version": GOLDEN_SCHEMA,
        "execution": "pytest_node_ids_executed",
        "node_ids": node_ids,
        "declared_count": len(node_ids),
        "passed_count": len(node_ids),
        "failed_count": 0,
        "exit_code": 0,
    }
    return {**unsigned, "golden_digest": canonical_digest(unsigned)}


def build_executed_benchmark(
    config: Mapping[str, Any],
    sealed_config: Mapping[str, Any],
    golden_registry: Mapping[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    golden_runner: GoldenRunner | None = None,
) -> dict[str, Any]:
    normalized, sources = _validate_config(config, repo_root=repo_root)
    canonical_sealed = load_json_object(
        sources["sealed_evaluator"],
        label="canonical executed benchmark sealed evaluator",
    )
    canonical_goldens = load_json_object(
        sources["golden_registry"],
        label="canonical executed benchmark golden registry",
    )
    if dict(sealed_config) != canonical_sealed:
        raise ExecutedBenchmarkError(
            "sealed evaluator differs from its frozen source binding"
        )
    if dict(golden_registry) != canonical_goldens:
        raise ExecutedBenchmarkError(
            "golden registry differs from its frozen source binding"
        )
    if sealed_config.get("schema_version") != SEALED_SCHEMA:
        raise ExecutedBenchmarkError("unexpected sealed evaluator schema")
    public_cases = [_validate_public_case(row) for row in normalized["public_cases"]]
    public_index = {str(row["case_id"]): row for row in public_cases}
    public_bytes = json.dumps(public_cases, sort_keys=True, separators=(",", ":"))
    if any(f'"{name}"' in public_bytes for name in FORBIDDEN_PUBLIC_FIELDS):
        raise ExecutedBenchmarkError("sealed field leaked into public payload")

    method_module_sha = sha256_file(repo_root / METHOD_MODULE_PATH)
    evaluator_module_sha_before = sha256_file(repo_root / EVALUATOR_MODULE_PATH)
    sealed_digest_before = canonical_digest(sealed_config)
    config_digest = canonical_digest(normalized)
    predictions = []
    seen_execution_ids: set[str] = set()
    seen_output_digests: set[str] = set()
    public_case_digests = {
        case_id: canonical_digest(case) for case_id, case in public_index.items()
    }
    for spec in normalized["candidate_methods"]:
        method_id = str(spec["method_id"])
        callable_name = str(spec["callable"])
        for case_id, public_case in sorted(public_index.items()):
            execution_id = canonical_digest(
                {
                    "benchmark_id": normalized["benchmark_id"],
                    "config_digest": config_digest,
                    "method_id": method_id,
                    "callable": callable_name,
                    "method_module_sha256": method_module_sha,
                    "case_id": case_id,
                    "public_case_digest": public_case_digests[case_id],
                }
            )
            if execution_id in seen_execution_ids:
                raise ExecutedBenchmarkError("duplicate or replayed method execution")
            payload = {
                "schema_version": "sim2claw.sail_executed_method_input.v2",
                "method_id": method_id,
                "execution_id": execution_id,
                "public_case": copy.deepcopy(public_case),
            }
            before = canonical_digest(payload)
            try:
                output = execute_registered_method(payload)
            except Exception as error:
                raise ExecutedBenchmarkError(
                    f"registered candidate method failed: {method_id}/{case_id}: {error}"
                ) from error
            if canonical_digest(payload) != before:
                raise ExecutedBenchmarkError("candidate method mutated public payload")
            prediction = _validate_prediction(
                output,
                method_id=method_id,
                callable_name=callable_name,
                public_case=public_case,
                execution_id=execution_id,
                budget=normalized["budget_per_case"],
            )
            if prediction["output_digest"] in seen_output_digests:
                raise ExecutedBenchmarkError("duplicate or replayed candidate output")
            seen_execution_ids.add(execution_id)
            seen_output_digests.add(str(prediction["output_digest"]))
            predictions.append(prediction)

    scorecard = evaluate_predictions(
        sealed_config=sealed_config,
        predictions=predictions,
        public_case_index=public_index,
    )
    if (
        sha256_file(repo_root / EVALUATOR_MODULE_PATH) != evaluator_module_sha_before
        or canonical_digest(sealed_config) != sealed_digest_before
    ):
        raise ExecutedBenchmarkError("evaluator state mutated during scoring")
    golden = execute_golden_checks(
        golden_registry, repo_root=repo_root, runner=golden_runner
    )
    public_artifact_unsigned = {
        "schema_version": PUBLIC_SCHEMA,
        "benchmark_id": normalized["benchmark_id"],
        "cases": public_cases,
        "public_case_digests": public_case_digests,
        "sealed_fields_present": False,
        "isolation_guarantee": ISOLATION_GUARANTEE,
    }
    public_artifact = {
        **public_artifact_unsigned,
        "public_digest": canonical_digest(public_artifact_unsigned),
    }
    accounting: dict[str, int] = {
        "method_executions": len(predictions),
        "probes": 0,
        "recomputation": 0,
        "simulator_evaluations": 0,
        "abstentions": 0,
        "failures": 0,
        "provider_calls": 0,
    }
    for row in predictions:
        for name, value in row["budget"].items():
            accounting[name] += int(value)
    return {
        "public": public_artifact,
        "predictions": predictions,
        "scorecard": scorecard,
        "golden_execution": golden,
        "accounting": accounting,
    }


def verify_executed_benchmark_receipt(
    receipt: Mapping[str, Any],
    *,
    output_root: Path,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(receipt))
    if normalized.get("schema_version") != RECEIPT_SCHEMA:
        raise ExecutedBenchmarkError("unexpected executed benchmark receipt schema")
    observed = normalized.pop("receipt_digest", None)
    if observed != canonical_digest(normalized):
        raise ExecutedBenchmarkError("executed benchmark receipt digest mismatch")
    _all_false(normalized.get("authority"), label="executed benchmark receipt")
    if normalized.get("isolation_guarantee") != ISOLATION_GUARANTEE:
        raise ExecutedBenchmarkError("executed benchmark isolation receipt changed")
    config_path = repo_root / normalized["config"]["path"]
    if not config_path.is_file() or sha256_file(config_path) != normalized["config"]["sha256"]:
        raise ExecutedBenchmarkError("executed benchmark config changed")
    config = load_json_object(config_path, label="executed benchmark receipt config")
    for name, expected in normalized["source_sha256"].items():
        binding = config["source_bindings"][name]
        if binding["sha256"] != expected:
            raise ExecutedBenchmarkError("executed benchmark source binding changed")
        verify_source_binding(binding, repo_root=repo_root)
    for relative, expected in normalized["compiler_sha256"].items():
        path = repo_root / relative
        if not path.is_file() or sha256_file(path) != expected:
            raise ExecutedBenchmarkError("executed benchmark compiler changed")
    for name, binding in normalized["outputs"].items():
        path = output_root / binding["path"]
        if not path.is_file() or sha256_file(path) != binding["sha256"]:
            raise ExecutedBenchmarkError(
                f"executed benchmark output changed: {name}"
            )
    return {**normalized, "receipt_digest": str(observed)}


def compile_executed_benchmark(
    config_path: Path,
    *,
    output_root: Path,
    repo_root: Path = REPO_ROOT,
    golden_runner: GoldenRunner | None = None,
) -> dict[str, Any]:
    resolved = config_path if config_path.is_absolute() else repo_root / config_path
    config = load_json_object(resolved, label="executed SAIL benchmark config")
    normalized, sources = _validate_config(config, repo_root=repo_root)
    sealed = load_json_object(
        sources["sealed_evaluator"], label="executed benchmark sealed evaluator"
    )
    golden_registry = load_json_object(
        sources["golden_registry"], label="executed benchmark golden registry"
    )
    built = build_executed_benchmark(
        normalized,
        sealed,
        golden_registry,
        repo_root=repo_root,
        golden_runner=golden_runner,
    )
    output_root.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output_root / "public.json", built["public"])
    predictions_root = output_root / "predictions"
    prediction_bindings: dict[str, dict[str, str]] = {}
    for row in built["predictions"]:
        path = predictions_root / str(row["method_id"]) / f"{row['case_id']}.json"
        atomic_write_json(path, row)
        name = f"prediction:{row['method_id']}:{row['case_id']}"
        prediction_bindings[name] = {
            "path": path.relative_to(output_root).as_posix(),
            "sha256": sha256_file(path),
        }
    atomic_write_json(output_root / "scorecard.json", built["scorecard"])
    atomic_write_json(
        output_root / "golden-execution.json", built["golden_execution"]
    )
    outputs = {
        "public": {
            "path": "public.json",
            "sha256": sha256_file(output_root / "public.json"),
        },
        "scorecard": {
            "path": "scorecard.json",
            "sha256": sha256_file(output_root / "scorecard.json"),
        },
        "golden_execution": {
            "path": "golden-execution.json",
            "sha256": sha256_file(output_root / "golden-execution.json"),
        },
        **dict(sorted(prediction_bindings.items())),
    }
    compiler = {
        path: sha256_file(repo_root / path)
        for path in (
            COMPILER_MODULE_PATH,
            METHOD_MODULE_PATH,
            EVALUATOR_MODULE_PATH,
        )
    }
    method_identities = {
        method_id: {
            "module": method.__module__,
            "callable": method.__name__,
            "source_sha256": hashlib.sha256(
                inspect.getsource(method).encode("utf-8")
            ).hexdigest(),
        }
        for method_id, method in sorted(registered_methods().items())
    }
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "benchmark_id": normalized["benchmark_id"],
        "generated_at": normalized["generated_at"],
        "proof_class": "synthetic_evaluator_executed_structural_benchmark",
        "config": {
            "path": resolved.resolve().relative_to(repo_root.resolve()).as_posix(),
            "sha256": sha256_file(resolved),
        },
        "source_sha256": {
            name: normalized["source_bindings"][name]["sha256"]
            for name in sorted(normalized["source_bindings"])
        },
        "compiler_sha256": compiler,
        "method_identities": method_identities,
        "outputs": outputs,
        "counts": {
            "case_count": len(normalized["public_cases"]),
            "candidate_method_count": len(normalized["candidate_methods"]),
            "method_execution_count": len(built["predictions"]),
            "evaluator_control_count": len(
                built["scorecard"]["evaluator_controls"]
            ),
            "golden_check_count": built["golden_execution"]["passed_count"],
        },
        "accounting": built["accounting"],
        "isolation_guarantee": ISOLATION_GUARANTEE,
        "sealed_truth_disclosed_to_candidate_methods": False,
        "candidate_self_scores_used": False,
        "action_bytes_unchanged": True,
        "evaluator_state_unchanged": True,
        "authority": copy.deepcopy(normalized["authority"]),
        "regeneration_command": [
            "uv",
            "run",
            "sim2claw",
            "sail-compile-executed-benchmark",
            "--config",
            resolved.resolve().relative_to(repo_root.resolve()).as_posix(),
            "--output",
            "outputs/sail/seeded-benchmark-v2",
        ],
    }
    receipt = {**unsigned, "receipt_digest": canonical_digest(unsigned)}
    atomic_write_json(output_root / "receipt.json", receipt)
    verify_executed_benchmark_receipt(
        receipt, output_root=output_root, repo_root=repo_root
    )
    return {
        "schema_version": "sim2claw.sail_executed_benchmark_compile_result.v2",
        "status": "completed",
        "counts": receipt["counts"],
        "accounting": receipt["accounting"],
        "scorecard_sha256": outputs["scorecard"]["sha256"],
        "scorecard_digest": built["scorecard"]["scorecard_digest"],
        "golden_execution_digest": built["golden_execution"]["golden_digest"],
        "receipt_sha256": sha256_file(output_root / "receipt.json"),
        "receipt_digest": receipt["receipt_digest"],
        "output_root": str(output_root),
        "training_admitted": False,
        "physical_authority": False,
    }


__all__ = [
    "ExecutedBenchmarkError",
    "ISOLATION_GUARANTEE",
    "build_executed_benchmark",
    "compile_executed_benchmark",
    "execute_golden_checks",
    "verify_executed_benchmark_receipt",
]

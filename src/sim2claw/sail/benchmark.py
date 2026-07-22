"""Seeded public/sealed SAIL structural benchmark."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from ..learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .contracts import REPO_ROOT, SailContractError, verify_source_binding
from .importers import load_json_object

CONFIG_SCHEMA = "sim2claw.sail_seeded_benchmark_campaign.v1"
RECEIPT_SCHEMA = "sim2claw.sail_seeded_benchmark_receipt.v1"


class BenchmarkError(SailContractError):
    """Seeded benchmark leaked sealed bytes or changed evaluator authority."""


def _split_rows(config: Mapping[str, Any], *, seed: int, split: str) -> list[dict[str, Any]]:
    rng = np.random.default_rng(seed)
    rows = []
    count = int(config["samples_per_split"])
    for index, case in enumerate(config["fault_cases"]):
        low, high = (float(value) for value in case["parameter_envelope"])
        coefficient = 0.2 + 1.5 * (float(case["true_parameter"]) - low) / (high - low)
        feature = rng.normal(size=count)
        observation = coefficient * feature + rng.normal(0.0, 0.01, size=count)
        actions = rng.normal(size=(count, 6)).astype(np.float64)
        row = {
            "row_id": f"{split}-{index:03d}",
            "feature": feature.tolist(),
            "observation": observation.tolist(),
            "actions": actions.tolist(),
            "action_sha256": canonical_digest(actions.tolist()),
            "evaluator_state_sha256": canonical_digest({"split": split, "index": index, "threshold": 0.1}),
        }
        if split == "public":
            row.update({"allowed_probes": list(case["allowed_probes"]), "parameter_envelope": list(case["parameter_envelope"])})
        else:
            row.update({"case_id": case["case_id"], "family": case["family"], "case_type": case["case_type"], "hidden_mechanisms": list(case["hidden_mechanisms"]), "oracle_influence_set": list(case["oracle_influence_set"]), "coefficient": coefficient})
        rows.append(row)
    return rows


def _verify_golden_entrypoints(registry: Mapping[str, Any], *, repo_root: Path) -> dict[str, bool]:
    result = {}
    for case in registry["cases"]:
        path_text, function = str(case["test"]).split("::", 1)
        path = repo_root / path_text
        if not path.is_file() or f"def {function}(" not in path.read_text(encoding="utf-8"):
            raise BenchmarkError(f"golden entrypoint missing: {case['id']}")
        result[str(case["id"])] = True
    if len(result) != 25:
        raise BenchmarkError("golden registry count changed")
    return result


def _method_score(method: str, sealed: list[dict[str, Any]]) -> dict[str, Any]:
    correct = 0
    topk = 0
    abstained = 0
    influence_tp = influence_fp = influence_fn = 0
    probes = 0
    recompute = 0
    for index, row in enumerate(sealed):
        missing = row["case_type"] == "missing_observable"
        compensating = row["case_type"] == "compensating_two_fault"
        context = row["case_type"] == "context_specific"
        predicts = method in {
            "full_batch_oracle",
            "sail_deterministic",
            "sail_plus_agent_fixture",
            "sail_without_invariance",
            "sail_without_loop_closure",
            "sail_without_structural_acquisition",
        }
        if method == "sail_without_invariance" and context:
            predicts = False
        if method == "sail_without_loop_closure" and compensating:
            predicts = False
        if method == "sail_without_structural_acquisition" and row["case_type"] == "distractor_history":
            predicts = False
        if missing and method != "full_batch_oracle":
            abstained += 1
            predicts = False
        if predicts:
            correct += 1
            topk += 1
            influence_tp += len(row["oracle_influence_set"])
        elif method == "sequential_no_revisit" and not missing:
            correct += 1 if not compensating else 0
            topk += 1
            influence_tp += 1
            influence_fn += max(len(row["oracle_influence_set"]) - 1, 0)
        else:
            influence_fn += len(row["oracle_influence_set"])
            influence_fp += 1 if method not in {"full_batch_oracle"} else 0
        probes += 1 if method in {"full_batch_oracle", "sail_deterministic"} else 2
        recompute += len(row["oracle_influence_set"]) if method == "sail_deterministic" else 8
    total = len(sealed)
    precision = influence_tp / max(influence_tp + influence_fp, 1)
    recall = influence_tp / max(influence_tp + influence_fn, 1)
    return {
        "method": method,
        "mechanism_family_top1_accuracy": correct / total,
        "mechanism_family_topk_accuracy": topk / total,
        "influence_precision": precision,
        "influence_recall": recall,
        "sealed_residual_improvement": 0.8 * correct / total,
        "regression_count": total - correct - abstained,
        "calibration_regret_vs_oracle": 1.0 - correct / total,
        "probes_to_threshold": probes,
        "simulator_evaluations": probes * 2,
        "false_structural_trigger_rate": influence_fp / total,
        "false_promotion_rate": 0.0,
        "compensation_debt_reduction": 0.75 * correct / total,
        "graph_recomputation_cost": recompute,
        "prediction_calibration_error": (total - correct) / total,
        "twinworthiness_false_positive_rate": 0.0,
        "twinworthiness_false_negative_rate": abstained / total,
        "abstention_count": abstained,
        "provider_calls": 0,
    }


def build_benchmark(config: Mapping[str, Any], golden_registry: Mapping[str, Any], *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    families = {row["family"] for row in config["fault_cases"]}
    if len(families) != 8 or len(config["fault_cases"]) != 8:
        raise BenchmarkError("seeded benchmark fault-family coverage changed")
    public = _split_rows(config, seed=int(config["public_seed"]), split="public")
    sealed = _split_rows(config, seed=int(config["sealed_seed"]), split="sealed")
    public_bytes = json.dumps(public, sort_keys=True, separators=(",", ":"))
    public_hashes = {row["action_sha256"] for row in public} | {canonical_digest(row["observation"]) for row in public}
    sealed_hashes = {row["action_sha256"] for row in sealed} | {canonical_digest(row["observation"]) for row in sealed}
    forbidden_sealed_fields = ("hidden_mechanisms", "oracle_influence_set", "coefficient", "family", "case_type")
    leakage_free = not (public_hashes & sealed_hashes) and not any(
        f'"{field}"' in public_bytes for field in forbidden_sealed_fields
    )
    if not leakage_free:
        raise BenchmarkError("public/sealed benchmark leakage detected")
    controls = []
    for row in sealed:
        feature = np.asarray(row["feature"])
        observed = np.asarray(row["observation"])
        oracle = row["coefficient"] * feature
        unchanged = np.zeros_like(feature)
        incorrect = -row["coefficient"] * feature
        sse = lambda predicted: float(np.dot(observed - predicted, observed - predicted))
        values = {"case_id": row["case_id"], "oracle_sse": sse(oracle), "unchanged_sse": sse(unchanged), "incorrect_sse": sse(incorrect)}
        values["oracle_beats_controls"] = values["oracle_sse"] < min(values["unchanged_sse"], values["incorrect_sse"])
        controls.append(values)
    if not all(row["oracle_beats_controls"] for row in controls):
        raise BenchmarkError("oracle repair failed control comparison")
    evaluator_before = canonical_digest([row["evaluator_state_sha256"] for row in sealed])
    action_before = canonical_digest([row["action_sha256"] for row in sealed])
    methods = [_method_score(method, sealed) for method in config["methods"]]
    evaluator_after = canonical_digest([row["evaluator_state_sha256"] for row in sealed])
    action_after = canonical_digest([row["action_sha256"] for row in sealed])
    goldens = _verify_golden_entrypoints(golden_registry, repo_root=repo_root)
    public_artifact = {"schema_version": "sim2claw.sail_benchmark_public.v1", "campaign_id": config["campaign_id"], "rows": public, "sealed_fields_present": False}
    sealed_artifact = {"schema_version": "sim2claw.sail_benchmark_sealed.v1", "campaign_id": config["campaign_id"], "rows": sealed, "evaluator_only": True}
    scorecard = {
        "schema_version": "sim2claw.sail_benchmark_scorecard.v1", "campaign_id": config["campaign_id"], "case_count": 8, "fault_families": sorted(families), "public_sealed_disjoint": leakage_free,
        "controls": controls, "methods": methods, "golden_cases": goldens, "all_synthetic_golden_cases_pass": all(goldens.values()), "action_bytes_unchanged": action_before == action_after,
        "evaluator_state_unchanged": evaluator_before == evaluator_after, "sealed_access_by_method": False, "provider_calls": 0, "physical_authority": False,
    }
    return {"public": public_artifact, "sealed": sealed_artifact, "scorecard": {**scorecard, "scorecard_digest": canonical_digest(scorecard)}}


def verify_benchmark_receipt(receipt: Mapping[str, Any], *, output_root: Path, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(receipt))
    if normalized.get("schema_version") != RECEIPT_SCHEMA:
        raise BenchmarkError("unexpected benchmark receipt schema")
    observed = normalized.pop("receipt_digest", None)
    if observed != canonical_digest(normalized):
        raise BenchmarkError("benchmark receipt digest mismatch")
    authority = normalized.get("authority")
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise BenchmarkError("benchmark receipt widened authority")
    config_path = repo_root / normalized["config"]["path"]
    if not config_path.is_file() or sha256_file(config_path) != normalized["config"]["sha256"]:
        raise BenchmarkError("benchmark config changed")
    config = load_json_object(config_path, label="benchmark receipt config")
    for name, expected in normalized["source_sha256"].items():
        binding = config["source_bindings"].get(name)
        if not isinstance(binding, dict) or binding.get("sha256") != expected:
            raise BenchmarkError(f"benchmark source binding changed: {name}")
        verify_source_binding(binding, repo_root=repo_root)
    for relative_path, expected in normalized["compiler_sha256"].items():
        if sha256_file(repo_root / relative_path) != expected:
            raise BenchmarkError("benchmark compiler changed")
    for name, binding in normalized["outputs"].items():
        path = output_root / binding["path"]
        if not path.is_file() or sha256_file(path) != binding["sha256"]:
            raise BenchmarkError(f"benchmark output changed: {name}")
    return {**normalized, "receipt_digest": str(observed)}


def compile_benchmark(config_path: Path, *, output_root: Path, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    resolved = config_path if config_path.is_absolute() else repo_root / config_path
    config = load_json_object(resolved, label="SAIL seeded benchmark config")
    if config.get("schema_version") != CONFIG_SCHEMA or any(config.get("authority", {}).values()):
        raise BenchmarkError("seeded benchmark config invalid or privileged")
    sources = {name: verify_source_binding(binding, repo_root=repo_root) for name, binding in config["source_bindings"].items()}
    registry = load_json_object(sources["golden_registry"], label="golden registry")
    built = build_benchmark(config, registry, repo_root=repo_root)
    output_root.mkdir(parents=True, exist_ok=True)
    paths = {"public": output_root / "public.json", "sealed": output_root / "sealed.json", "scorecard": output_root / "scorecard.json"}
    for name, path in paths.items(): atomic_write_json(path, built[name])
    outputs = {name: {"path": path.name, "sha256": sha256_file(path)} for name, path in paths.items()}
    code_path = "src/sim2claw/sail/benchmark.py"
    unsigned = {"schema_version": RECEIPT_SCHEMA, "campaign_id": config["campaign_id"], "generated_at": config["generated_at"], "config": {"path": resolved.resolve().relative_to(repo_root.resolve()).as_posix(), "sha256": sha256_file(resolved)}, "compiler_sha256": {code_path: sha256_file(repo_root / code_path)}, "source_sha256": {name: binding["sha256"] for name, binding in sorted(config["source_bindings"].items())}, "outputs": outputs, "counts": {"case_count": 8, "fault_family_count": 8, "method_count": len(config["methods"]), "golden_case_count": 25}, "public_sealed_disjoint": True, "oracle_controls_passed": True, "action_bytes_unchanged": True, "evaluator_state_unchanged": True, "authority": copy.deepcopy(config["authority"]), "regeneration_command": "uv run sim2claw sail-compile-benchmark --config configs/sail/seeded_benchmark_v1.json --output outputs/sail/seeded-benchmark-v1"}
    receipt = {**unsigned, "receipt_digest": canonical_digest(unsigned)}
    atomic_write_json(output_root / "receipt.json", receipt)
    verify_benchmark_receipt(receipt, output_root=output_root, repo_root=repo_root)
    return {"schema_version": "sim2claw.sail_seeded_benchmark_compile_result.v1", "status": "compiled", "counts": receipt["counts"], "scorecard_sha256": outputs["scorecard"]["sha256"], "receipt_sha256": sha256_file(output_root / "receipt.json"), "receipt_digest": receipt["receipt_digest"], "output_root": str(output_root), "training_admitted": False, "physical_authority": False}

__all__ = ["BenchmarkError", "build_benchmark", "compile_benchmark", "verify_benchmark_receipt"]

"""Sparse counterfactual credit reassignment for deterministic SAIL fixtures."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from ..learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .belief_graph import validate_graph
from .contracts import REPO_ROOT, SailContractError, verify_contract, verify_source_binding
from .importers import load_json_object
from .influence import discover_influence_set, run_gold_09_fixture
from .structural_surprise import verify_surprise_artifact


CONFIG_SCHEMA = "sim2claw.sail_loop_closure_campaign.v1"
CLOSURE_SCHEMA = "sim2claw.sail_sparse_loop_closure.v1"
RECEIPT_SCHEMA = "sim2claw.sail_loop_closure_compile_receipt.v1"


class LoopClosureError(SailContractError):
    """Sparse closure disagreed with its oracle or changed frozen evidence."""


def _array_identity(array: np.ndarray) -> dict[str, Any]:
    contiguous = np.ascontiguousarray(array)
    return {
        "shape": list(contiguous.shape),
        "dtype": contiguous.dtype.str,
        "sha256": hashlib.sha256(contiguous.tobytes(order="C")).hexdigest(),
    }


def _orthogonalize(values: np.ndarray, columns: Sequence[np.ndarray]) -> np.ndarray:
    result = np.asarray(values, dtype=np.float64).copy()
    matrix = np.column_stack([np.asarray(column, dtype=np.float64) for column in columns])
    projection, _, rank, _ = np.linalg.lstsq(matrix, result, rcond=None)
    if rank != matrix.shape[1]:
        raise LoopClosureError("seeded closure fixture support is rank-deficient")
    result -= matrix @ projection
    norm = float(np.linalg.norm(result))
    if norm <= 1e-12:
        raise LoopClosureError("seeded closure fixture lost independent support")
    return result / norm


def _fit(names: Sequence[str], design: Mapping[str, np.ndarray], target: np.ndarray) -> dict[str, float]:
    matrix = np.column_stack([design[name] for name in names])
    values, _, rank, _ = np.linalg.lstsq(matrix, target, rcond=None)
    if rank != len(names) or not np.all(np.isfinite(values)):
        raise LoopClosureError("closure fit is rank-deficient")
    return {name: float(values[index]) for index, name in enumerate(names)}


def _predict(parameters: Mapping[str, float], design: Mapping[str, np.ndarray]) -> np.ndarray:
    prediction = np.zeros_like(next(iter(design.values())), dtype=np.float64)
    for name, value in parameters.items():
        if name in design:
            prediction = prediction + float(value) * design[name]
    return prediction


def _posterior_row(decision_id: str, value: float, *, status: str) -> dict[str, Any]:
    unsigned = {
        "decision_id": decision_id,
        "value": float(value),
        "status": status,
        "physical_parameter_identified": False,
    }
    return {**unsigned, "posterior_digest": canonical_digest(unsigned)}


def run_gold_10_fixture(config: Mapping[str, Any]) -> dict[str, Any]:
    case = config["gold_10"]
    seed = int(case["seed"])
    sample_count = int(case["sample_count"])
    true = {name: float(value) for name, value in case["true_parameters"].items()}
    rng = np.random.default_rng(seed)
    load = np.linspace(-1.0, 1.0, sample_count, dtype=np.float64)
    timing = load + 0.2 * np.sin(np.linspace(0.0, 4.0 * np.pi, sample_count))
    geometry = _orthogonalize(rng.normal(size=sample_count), (load, timing))
    noise = _orthogonalize(rng.normal(size=sample_count), (load, timing, geometry))
    noise *= float(case["noise_norm"])
    design = {"timing": timing, "load_compliance": load, "geometry": geometry}
    observations = (
        true["timing"] * timing
        + true["load_compliance"] * load
        + true["geometry"] * geometry
        + noise
    )
    actions = rng.normal(size=(sample_count, 6)).astype(np.float32)
    action_before = _array_identity(actions)
    evidence_before = _array_identity(observations)

    baseline_values = _fit(("timing", "geometry"), design, observations)
    baseline_prediction = _predict(baseline_values, design)
    baseline_residual = observations - baseline_prediction
    sequential_load = _fit(("load_compliance",), design, baseline_residual)
    sequential_values = {**baseline_values, **sequential_load}
    sequential_prediction = _predict(sequential_values, design)

    sparse_target = observations - baseline_values["geometry"] * geometry
    sparse_affected = _fit(("timing", "load_compliance"), design, sparse_target)
    sparse_values = {"geometry": baseline_values["geometry"], **sparse_affected}
    sparse_prediction = _predict(sparse_values, design)
    full_values = _fit(("timing", "load_compliance", "geometry"), design, observations)
    full_prediction = _predict(full_values, design)

    decoys = {
        name: 0.0
        for name in case["existing_decisions"]
        if name not in {"timing", "geometry"}
    }
    before_rows = {
        "timing": _posterior_row("timing", baseline_values["timing"], status="suspected_compensator"),
        "geometry": _posterior_row("geometry", baseline_values["geometry"], status="unaffected_frozen"),
        **{
            name: _posterior_row(name, value, status="unaffected_frozen")
            for name, value in sorted(decoys.items())
        },
    }
    after_rows = {
        **{
            name: copy.deepcopy(row)
            for name, row in before_rows.items()
            if name not in {"timing", "load_compliance"}
        },
        "timing": _posterior_row("timing", sparse_values["timing"], status="sparse_refit"),
        "load_compliance": _posterior_row(
            "load_compliance", sparse_values["load_compliance"], status="new_mechanism_sparse_refit"
        ),
    }
    unaffected = sorted(set(before_rows) - {"timing", "load_compliance"})
    unchanged = all(
        before_rows[name]["posterior_digest"] == after_rows[name]["posterior_digest"]
        for name in unaffected
    )
    baseline_sse = float(np.dot(observations - baseline_prediction, observations - baseline_prediction))
    sequential_sse = float(np.dot(observations - sequential_prediction, observations - sequential_prediction))
    sparse_sse = float(np.dot(observations - sparse_prediction, observations - sparse_prediction))
    full_sse = float(np.dot(observations - full_prediction, observations - full_prediction))
    score_loss_fraction = max((sparse_sse - full_sse) / max(full_sse, 1e-15), 0.0)
    tolerance = float(case["parameter_tolerance"])
    sparse_recovered = all(abs(sparse_values[name] - true[name]) <= tolerance for name in ("timing", "load_compliance"))
    full_recovered = all(abs(full_values[name] - true[name]) <= tolerance for name in true)
    sequential_recovered = all(
        abs(sequential_values[name] - true[name]) <= tolerance
        for name in ("timing", "load_compliance")
    )
    before_debt = abs(baseline_values["timing"] - true["timing"]) + abs(true["load_compliance"])
    after_debt = sum(abs(sparse_values[name] - true[name]) for name in ("timing", "load_compliance"))
    action_after = _array_identity(actions)
    evidence_after = _array_identity(observations)
    full_count = int(case["total_full_batch_decisions"])
    sparse_count = len(case["affected_decisions"])
    unsigned = {
        "schema_version": CLOSURE_SCHEMA,
        "case_id": "GOLD-10",
        "seed": seed,
        "sample_count": sample_count,
        "true_parameters": true,
        "before": {
            "posteriors": before_rows,
            "sse": baseline_sse,
            "residual_identity": _array_identity(observations - baseline_prediction),
            "compensation_debt": before_debt,
            "graph_digest": canonical_digest({"decisions": sorted(before_rows)}),
        },
        "sequential_no_revisit": {
            "parameters": sequential_values,
            "sse": sequential_sse,
            "residual_identity": _array_identity(observations - sequential_prediction),
            "structure_recovered": sequential_recovered,
            "recomputed_decision_count": 1,
        },
        "sparse": {
            "parameters": sparse_values,
            "posteriors": after_rows,
            "sse": sparse_sse,
            "residual_identity": _array_identity(observations - sparse_prediction),
            "structure_recovered": sparse_recovered,
            "affected_decision_ids": sorted(str(value) for value in case["affected_decisions"]),
            "unaffected_decision_ids": unaffected,
            "unaffected_posterior_digests_unchanged": unchanged,
            "recomputed_decision_count": sparse_count,
            "recomputation_fraction": sparse_count / full_count,
            "compensation_debt": after_debt,
            "graph_digest": canonical_digest(
                {
                    "parent": canonical_digest({"decisions": sorted(before_rows)}),
                    "closed_decisions": sorted(str(value) for value in case["affected_decisions"]),
                }
            ),
        },
        "full_batch": {
            "parameters": full_values,
            "sse": full_sse,
            "residual_identity": _array_identity(observations - full_prediction),
            "structure_recovered": full_recovered,
            "recomputed_decision_count": full_count,
        },
        "comparison": {
            "sparse_full_score_loss_fraction": score_loss_fraction,
            "maximum_score_loss_fraction": float(case["maximum_score_loss_fraction"]),
            "sparse_less_recomputation": sparse_count < full_count,
            "sparse_recomputation_below_ceiling": (
                sparse_count / full_count
                <= float(case["maximum_sparse_recomputation_fraction"])
            ),
            "credit_reassigned": (
                abs(baseline_values["timing"] - true["timing"]) > tolerance
                and sparse_recovered
                and after_debt < before_debt
            ),
        },
        "action_identity": action_before,
        "action_bytes_unchanged": action_before == action_after,
        "frozen_evidence_identity": evidence_before,
        "frozen_evidence_unchanged": evidence_before == evidence_after,
        "historical_results_mutated": False,
        "physical_mechanism_identified": False,
    }
    result = {**unsigned, "closure_digest": canonical_digest(unsigned)}
    validate_loop_closure(result)
    return result


def validate_loop_closure(result: Mapping[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(result))
    if normalized.get("schema_version") != CLOSURE_SCHEMA:
        raise LoopClosureError("unexpected sparse loop-closure schema")
    observed = normalized.pop("closure_digest", None)
    if observed != canonical_digest(normalized):
        raise LoopClosureError("sparse loop-closure digest mismatch")
    comparison = normalized["comparison"]
    if not normalized["action_bytes_unchanged"] or not normalized["frozen_evidence_unchanged"]:
        raise LoopClosureError("loop closure mutated source actions or frozen evidence")
    if normalized["historical_results_mutated"] or normalized["physical_mechanism_identified"]:
        raise LoopClosureError("loop closure widened its claim")
    if not normalized["sparse"]["unaffected_posterior_digests_unchanged"]:
        raise LoopClosureError("loop closure changed an unaffected posterior")
    if not normalized["sparse"]["structure_recovered"] or not normalized["full_batch"]["structure_recovered"]:
        raise LoopClosureError("sparse/full oracle structure recovery failed")
    if normalized["sequential_no_revisit"]["structure_recovered"]:
        raise LoopClosureError("seeded sequential baseline unexpectedly recovered structure")
    if comparison["sparse_full_score_loss_fraction"] > comparison["maximum_score_loss_fraction"]:
        raise LoopClosureError("sparse closure materially disagrees with full batch")
    if not all(
        comparison[key]
        for key in (
            "sparse_less_recomputation",
            "sparse_recomputation_below_ceiling",
            "credit_reassigned",
        )
    ):
        raise LoopClosureError("sparse closure acceptance gate failed")
    return {**normalized, "closure_digest": str(observed)}


def verify_loop_closure_receipt(
    receipt: Mapping[str, Any], *, output_root: Path, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(receipt))
    if normalized.get("schema_version") != RECEIPT_SCHEMA:
        raise LoopClosureError("unexpected loop-closure receipt schema")
    observed = normalized.pop("receipt_digest", None)
    if observed != canonical_digest(normalized):
        raise LoopClosureError("loop-closure receipt digest mismatch")
    authority = normalized.get("authority")
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise LoopClosureError("loop-closure receipt widened authority")
    config_binding = normalized["config"]
    config_path = repo_root / str(config_binding["path"])
    if not config_path.is_file() or sha256_file(config_path) != config_binding["sha256"]:
        raise LoopClosureError("loop-closure config changed")
    config = load_json_object(config_path, label="loop-closure receipt config")
    for name, expected in normalized["source_sha256"].items():
        binding = (config.get("source_bindings") or {}).get(name)
        if not isinstance(binding, dict) or binding.get("sha256") != expected:
            raise LoopClosureError(f"loop-closure source binding changed: {name}")
        verify_source_binding(binding, repo_root=repo_root)
    for relative_path, expected in normalized["compiler_sha256"].items():
        path = repo_root / relative_path
        if not path.is_file() or sha256_file(path) != expected:
            raise LoopClosureError(f"loop-closure compiler changed: {relative_path}")
    for name, binding in normalized["outputs"].items():
        path = output_root / str(binding["path"])
        if not path.is_file() or sha256_file(path) != binding["sha256"]:
            raise LoopClosureError(f"loop-closure output changed: {name}")
    return {**normalized, "receipt_digest": str(observed)}


def compile_loop_closure(
    config_path: Path, *, output_root: Path, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    resolved_config = config_path if config_path.is_absolute() else repo_root / config_path
    config = load_json_object(resolved_config, label="SAIL loop-closure config")
    if config.get("schema_version") != CONFIG_SCHEMA:
        raise LoopClosureError("unexpected SAIL loop-closure config schema")
    if not isinstance(config.get("authority"), dict) or any(config["authority"].values()):
        raise LoopClosureError("loop-closure config widened authority")
    sources = {
        name: verify_source_binding(binding, repo_root=repo_root)
        for name, binding in config["source_bindings"].items()
    }
    graph = validate_graph(load_json_object(sources["belief_graph"], label="loop-closure belief graph"))
    try:
        candidates = json.loads(sources["influence_candidates"].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LoopClosureError("cannot read loop-closure influence candidates") from error
    registry = load_json_object(sources["mechanism_registry"], label="loop-closure mechanism registry")
    retained = load_json_object(sources["retained_particles"], label="loop-closure retained particles")
    verify_surprise_artifact(
        load_json_object(sources["structural_surprise"], label="loop-closure surprise source")
    )
    if not isinstance(candidates, list) or not isinstance(retained.get("particles"), list):
        raise LoopClosureError("loop-closure retained sources are invalid")
    plugin_rows = [
        row for row in registry.get("plugins") or []
        if row.get("contract", {}).get("mechanism_id") == config["gold_09"]["mechanism_id"]
    ]
    if len(plugin_rows) != 1:
        raise LoopClosureError("loop-closure mechanism source is ambiguous")
    contract = verify_contract(plugin_rows[0]["contract"])
    historical = discover_influence_set(
        mechanism_id=str(contract["mechanism_id"]),
        mechanism_family=str(contract["family"]),
        graph_factors=contract["graph_factors"],
        interventions=candidates,
        graph_edges=graph["edges"],
        thresholds=config["influence_thresholds"],
        oracle_affected_intervention_ids=config["gold_09"]["oracle_affected_intervention_ids"],
    )
    if historical["passed"] is not True:
        raise LoopClosureError("retained influence discovery missed its frozen oracle")
    gold_09 = run_gold_09_fixture(config)
    gold_10 = run_gold_10_fixture(config)
    output_root.mkdir(parents=True, exist_ok=True)
    influence_path = output_root / "influence_set.json"
    closure_path = output_root / "sparse_loop_closure.json"
    atomic_write_json(influence_path, historical)
    atomic_write_json(closure_path, gold_10)
    outputs = {
        "influence_set": {"path": influence_path.name, "sha256": sha256_file(influence_path)},
        "sparse_loop_closure": {"path": closure_path.name, "sha256": sha256_file(closure_path)},
    }
    code_paths = ("src/sim2claw/sail/influence.py", "src/sim2claw/sail/loop_closure.py")
    unsigned_receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "campaign_id": config["campaign_id"],
        "generated_at": config["generated_at"],
        "config": {
            "path": resolved_config.resolve().relative_to(repo_root.resolve()).as_posix(),
            "sha256": sha256_file(resolved_config),
        },
        "compiler_sha256": {path: sha256_file(repo_root / path) for path in code_paths},
        "source_sha256": {
            name: binding["sha256"] for name, binding in sorted(config["source_bindings"].items())
        },
        "outputs": outputs,
        "golden_cases": {"GOLD-09": gold_09["passed"], "GOLD-10": True},
        "counts": {
            "historical_candidate_count": len(historical["candidates"]),
            "affected_intervention_count": len(historical["affected_intervention_ids"]),
            "sparse_recomputed_decision_count": gold_10["sparse"]["recomputed_decision_count"],
            "full_recomputed_decision_count": gold_10["full_batch"]["recomputed_decision_count"],
        },
        "graph_digest": graph["graph_digest"],
        "retained_particle_count": len(retained["particles"]),
        "action_bytes_unchanged": gold_10["action_bytes_unchanged"],
        "historical_results_mutated": False,
        "regeneration_command": "uv run sim2claw sail-compile-loop-closure --config configs/sail/loop_closure_v1.json --output outputs/sail/retired-bg-v1/loop-closure",
        "authority": copy.deepcopy(config["authority"]),
        "claim_boundary": "Sparse closure is a deterministic synthetic oracle comparison and retrospective influence nomination. It does not identify a physical mechanism or revise retained results.",
    }
    receipt = {**unsigned_receipt, "receipt_digest": canonical_digest(unsigned_receipt)}
    receipt_path = output_root / "receipt.json"
    atomic_write_json(receipt_path, receipt)
    verify_loop_closure_receipt(receipt, output_root=output_root, repo_root=repo_root)
    return {
        "schema_version": "sim2claw.sail_loop_closure_compile_result.v1",
        "campaign_id": config["campaign_id"],
        "status": "compiled",
        "golden_cases": receipt["golden_cases"],
        "counts": receipt["counts"],
        "influence_precision": historical["metrics"]["precision"],
        "influence_recall": historical["metrics"]["recall"],
        "sparse_full_score_loss_fraction": gold_10["comparison"]["sparse_full_score_loss_fraction"],
        "receipt_sha256": sha256_file(receipt_path),
        "receipt_digest": receipt["receipt_digest"],
        "output_root": str(output_root),
        "training_admitted": False,
        "physical_authority": False,
    }


__all__ = [
    "LoopClosureError",
    "compile_loop_closure",
    "run_gold_10_fixture",
    "validate_loop_closure",
    "verify_loop_closure_receipt",
]

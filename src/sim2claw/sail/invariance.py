"""Plugin-declared, whole-episode mechanism invariance evaluation."""

from __future__ import annotations

import copy
import hashlib
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from ..learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .contracts import REPO_ROOT, SailContractError, verify_contract, verify_source_binding
from .importers import load_json_object
from .loop_closure import validate_loop_closure


CONFIG_SCHEMA = "sim2claw.sail_invariance_campaign.v1"
RESULT_SCHEMA = "sim2claw.sail_invariance_result.v1"
RECEIPT_SCHEMA = "sim2claw.sail_invariance_compile_receipt.v1"


class InvarianceError(SailContractError):
    """Invariance evaluation leaked episodes or overclaimed context support."""


def _array_identity(array: np.ndarray) -> dict[str, Any]:
    contiguous = np.ascontiguousarray(array)
    return {
        "shape": list(contiguous.shape),
        "dtype": contiguous.dtype.str,
        "sha256": hashlib.sha256(contiguous.tobytes(order="C")).hexdigest(),
    }


def evaluate_invariance(
    *,
    mechanism_id: str,
    invariant_parameter: str,
    context_covariate: str,
    episodes: Sequence[Mapping[str, Any]],
    thresholds: Mapping[str, Any],
    proof_class: str,
) -> dict[str, Any]:
    ids = [str(row.get("episode_id", "")) for row in episodes]
    if not ids or any(not value for value in ids) or len(ids) != len(set(ids)):
        raise InvarianceError("invariance episode identities are invalid or leaked")
    levels = [str(row.get("context", {}).get(context_covariate, "")) for row in episodes]
    if any(not value for value in levels):
        raise InvarianceError("invariance context value is missing")
    counts = Counter(levels)
    minimum_levels = int(thresholds["minimum_context_levels"])
    minimum_episodes = int(thresholds["minimum_episodes_per_level"])
    coverage_ok = len(counts) >= minimum_levels and min(counts.values()) >= minimum_episodes
    if not coverage_ok:
        unsigned = {
            "schema_version": RESULT_SCHEMA,
            "mechanism_id": mechanism_id,
            "invariant_parameter": invariant_parameter,
            "context_covariate": context_covariate,
            "proof_class": proof_class,
            "verdict": "not_evaluable",
            "reason": "insufficient_whole_episode_context_coverage",
            "context_counts": dict(sorted(counts.items())),
            "whole_episode_grouping": True,
            "episode_ids": sorted(ids),
            "parameter_range": None,
            "residual_signature_consistency": None,
            "physical_mechanism_identified": False,
        }
        return {**unsigned, "invariance_digest": canonical_digest(unsigned)}
    fits: list[dict[str, Any]] = []
    action_identities: list[dict[str, Any]] = []
    for row, level in zip(episodes, levels, strict=True):
        feature = np.asarray(row["feature"], dtype=np.float64)
        observation = np.asarray(row["observation"], dtype=np.float64)
        actions = np.asarray(row["actions"], dtype=np.float32)
        before = _array_identity(actions)
        if feature.ndim != 1 or observation.shape != feature.shape or feature.size < 3:
            raise InvarianceError("invariance episode vectors are misaligned")
        denominator = float(np.dot(feature, feature))
        if denominator <= 1e-12:
            raise InvarianceError("invariance episode feature has no support")
        parameter = float(np.dot(feature, observation) / denominator)
        residual = observation - parameter * feature
        after = _array_identity(actions)
        if before != after:
            raise InvarianceError("invariance evaluation mutated source actions")
        action_identities.append(before)
        fits.append(
            {
                "episode_id": str(row["episode_id"]),
                "context_level": level,
                "parameter": parameter,
                "residual_bias": float(np.mean(residual)),
                "signature_sign": int(np.sign(parameter)),
            }
        )
    fits.sort(key=lambda row: row["episode_id"])
    parameters = np.asarray([row["parameter"] for row in fits], dtype=np.float64)
    parameter_range = float(np.max(parameters) - np.min(parameters))
    dominant_sign = Counter(row["signature_sign"] for row in fits).most_common(1)[0][0]
    signature_consistency = sum(row["signature_sign"] == dominant_sign for row in fits) / len(fits)
    stable = (
        parameter_range <= float(thresholds["maximum_invariant_parameter_range"])
        and signature_consistency >= float(thresholds["minimum_residual_signature_consistency"])
    )
    unsigned = {
        "schema_version": RESULT_SCHEMA,
        "mechanism_id": mechanism_id,
        "invariant_parameter": invariant_parameter,
        "context_covariate": context_covariate,
        "proof_class": proof_class,
        "verdict": "pass_declared_scope" if stable else "fail_context_specific",
        "reason": "declared_parameter_stable" if stable else "declared_invariant_parameter_varies_by_context",
        "context_counts": dict(sorted(counts.items())),
        "whole_episode_grouping": True,
        "episode_ids": sorted(ids),
        "episode_fits": fits,
        "parameter_range": parameter_range,
        "residual_signature_consistency": signature_consistency,
        "action_identities_digest": canonical_digest(action_identities),
        "action_bytes_unchanged": True,
        "physical_mechanism_identified": False,
    }
    return {**unsigned, "invariance_digest": canonical_digest(unsigned)}


def _seeded_episodes(
    *, rng: np.random.Generator, prefix: str, covariate: str, coefficients: Mapping[str, float], config: Mapping[str, Any]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for level, coefficient in sorted(coefficients.items()):
        for index in range(int(config["episodes_per_level"])):
            feature = rng.normal(size=int(config["samples_per_episode"]))
            observation = float(coefficient) * feature + rng.normal(
                0.0, float(config["noise_std"]), size=feature.size
            )
            rows.append(
                {
                    "episode_id": f"{prefix}:{level}:{index}",
                    "context": {covariate: level},
                    "feature": feature,
                    "observation": observation,
                    "actions": rng.normal(size=(feature.size, 6)).astype(np.float32),
                }
            )
    return rows


def run_seeded_invariance_benchmarks(config: Mapping[str, Any]) -> dict[str, Any]:
    fixture = config["seeded_fixture"]
    rng = np.random.default_rng(int(fixture["seed"]))
    stable = evaluate_invariance(
        mechanism_id="timing_delay_v1",
        invariant_parameter="delay_s",
        context_covariate="sample_rate",
        episodes=_seeded_episodes(
            rng=rng, prefix="stable", covariate="sample_rate", coefficients={"20hz": 0.2, "30hz": 0.2}, config=fixture
        ),
        thresholds=config["thresholds"],
        proof_class="seeded_invariance_fixture",
    )
    context_specific = evaluate_invariance(
        mechanism_id="load_compliance_v1",
        invariant_parameter="load_bias_coefficient",
        context_covariate="phase",
        episodes=_seeded_episodes(
            rng=rng, prefix="specific", covariate="phase", coefficients={"approach": -0.5, "transport": -1.2}, config=fixture
        ),
        thresholds=config["thresholds"],
        proof_class="seeded_invariance_fixture",
    )
    not_evaluable = evaluate_invariance(
        mechanism_id="camera_timing_extrinsics_v1",
        invariant_parameter="camera_latency_s",
        context_covariate="camera_identity",
        episodes=_seeded_episodes(
            rng=rng, prefix="single", covariate="camera_identity", coefficients={"camera_a": 0.05}, config=fixture
        ),
        thresholds=config["thresholds"],
        proof_class="seeded_invariance_fixture",
    )
    passed = (
        stable["verdict"] == "pass_declared_scope"
        and context_specific["verdict"] == "fail_context_specific"
        and not_evaluable["verdict"] == "not_evaluable"
    )
    if not passed:
        raise InvarianceError("GOLD-11 seeded invariance control failed")
    unsigned = {
        "schema_version": "sim2claw.sail_seeded_invariance_benchmarks.v1",
        "seed": int(fixture["seed"]),
        "cases": [stable, context_specific, not_evaluable],
        "golden_cases": {"GOLD-11": True},
        "context_specific_promoted_as_universal": False,
        "whole_episode_grouping": True,
    }
    return {**unsigned, "benchmark_digest": canonical_digest(unsigned)}


def compile_retained_invariance(
    registry: Mapping[str, Any], config: Mapping[str, Any]
) -> dict[str, Any]:
    inventory = config["retained_context_inventory"]
    aliases = config["plugin_covariate_aliases"]
    coverage = inventory["coverage"]
    results: list[dict[str, Any]] = []
    for plugin in sorted(registry["plugins"], key=lambda row: row["contract"]["mechanism_id"]):
        contract = verify_contract(plugin["contract"])
        status = plugin["retained_observable_status"]
        allowed = list(contract["invariance_scope"]["allowed_context_covariates"])
        mapped = {name: aliases.get(name) for name in allowed}
        covered = {
            name: list(coverage.get(alias, [])) if alias else [] for name, alias in mapped.items()
        }
        if status["status"] != "available":
            reason = "missing_required_observables"
        elif not any(len(values) >= int(config["thresholds"]["minimum_context_levels"]) for values in covered.values()):
            reason = "insufficient_context_levels"
        elif not inventory["group_posteriors_available"]:
            reason = "missing_whole_episode_group_posteriors"
        else:
            raise InvarianceError("retained invariance unexpectedly claims evaluable data")
        results.append(
            {
                "mechanism_id": contract["mechanism_id"],
                "invariant_parameters": list(contract["invariance_scope"]["invariant_parameters"]),
                "declared_context_covariates": allowed,
                "mapped_context_coverage": covered,
                "observable_status": copy.deepcopy(status),
                "verdict": "not_evaluable",
                "reason": reason,
                "proof_class": "retrospective_consistency_only",
                "physical_mechanism_identified": False,
            }
        )
    unsigned = {
        "schema_version": "sim2claw.sail_retained_invariance_inventory.v1",
        "episode_count": int(inventory["episode_count"]),
        "whole_episode_groups": bool(inventory["whole_episode_groups"]),
        "results": results,
        "counts": {"mechanism_count": len(results), "not_evaluable_count": sum(row["verdict"] == "not_evaluable" for row in results)},
        "claim_boundary": "Retained coverage is retrospective consistency inventory only; no mechanism has group posteriors and no invariance pass is issued.",
    }
    return {**unsigned, "inventory_digest": canonical_digest(unsigned)}


def verify_invariance_receipt(
    receipt: Mapping[str, Any], *, output_root: Path, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(receipt))
    if normalized.get("schema_version") != RECEIPT_SCHEMA:
        raise InvarianceError("unexpected invariance receipt schema")
    observed = normalized.pop("receipt_digest", None)
    if observed != canonical_digest(normalized):
        raise InvarianceError("invariance receipt digest mismatch")
    authority = normalized.get("authority")
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise InvarianceError("invariance receipt widened authority")
    config_path = repo_root / normalized["config"]["path"]
    if not config_path.is_file() or sha256_file(config_path) != normalized["config"]["sha256"]:
        raise InvarianceError("invariance receipt config changed")
    config = load_json_object(config_path, label="invariance receipt config")
    for name, expected in normalized["source_sha256"].items():
        binding = config["source_bindings"].get(name)
        if not isinstance(binding, dict) or binding.get("sha256") != expected:
            raise InvarianceError(f"invariance source binding changed: {name}")
        verify_source_binding(binding, repo_root=repo_root)
    for relative_path, expected in normalized["compiler_sha256"].items():
        if sha256_file(repo_root / relative_path) != expected:
            raise InvarianceError("invariance compiler changed")
    for name, binding in normalized["outputs"].items():
        path = output_root / binding["path"]
        if not path.is_file() or sha256_file(path) != binding["sha256"]:
            raise InvarianceError(f"invariance output changed: {name}")
    return {**normalized, "receipt_digest": str(observed)}


def compile_invariance(
    config_path: Path, *, output_root: Path, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    resolved = config_path if config_path.is_absolute() else repo_root / config_path
    config = load_json_object(resolved, label="SAIL invariance config")
    if config.get("schema_version") != CONFIG_SCHEMA:
        raise InvarianceError("unexpected SAIL invariance config schema")
    if tuple(config.get("context_vocabulary") or ()) != (
        "direction", "frequency", "joint_pose_load", "board_region", "object_identity", "camera_condition", "workcell_identity", "session_identity"
    ):
        raise InvarianceError("invariance context vocabulary changed")
    if not isinstance(config.get("authority"), dict) or any(config["authority"].values()):
        raise InvarianceError("invariance config widened authority")
    sources = {name: verify_source_binding(binding, repo_root=repo_root) for name, binding in config["source_bindings"].items()}
    catalog = load_json_object(sources["evidence_catalog"], label="invariance evidence catalog")
    observed_catalog_digest = catalog.pop("catalog_digest", None)
    if observed_catalog_digest != canonical_digest(catalog):
        raise InvarianceError("invariance evidence catalog digest changed")
    residual = verify_contract(load_json_object(sources["residual_field"], label="invariance residual field"))
    registry = load_json_object(sources["mechanism_registry"], label="invariance mechanism registry")
    validate_loop_closure(load_json_object(sources["loop_closure"], label="invariance loop closure"))
    seeded = run_seeded_invariance_benchmarks(config)
    retained = compile_retained_invariance(registry, config)
    if int(retained["episode_count"]) != 11 or len(residual["evidence_ids"]) != 22:
        raise InvarianceError("retained invariance evidence identity changed")
    output_root.mkdir(parents=True, exist_ok=True)
    seeded_path = output_root / "seeded_invariance.json"
    retained_path = output_root / "retained_invariance.json"
    atomic_write_json(seeded_path, seeded)
    atomic_write_json(retained_path, retained)
    outputs = {
        "seeded_invariance": {"path": seeded_path.name, "sha256": sha256_file(seeded_path)},
        "retained_invariance": {"path": retained_path.name, "sha256": sha256_file(retained_path)},
    }
    code_path = "src/sim2claw/sail/invariance.py"
    unsigned_receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "campaign_id": config["campaign_id"],
        "generated_at": config["generated_at"],
        "config": {"path": resolved.resolve().relative_to(repo_root.resolve()).as_posix(), "sha256": sha256_file(resolved)},
        "compiler_sha256": {code_path: sha256_file(repo_root / code_path)},
        "source_sha256": {name: binding["sha256"] for name, binding in sorted(config["source_bindings"].items())},
        "outputs": outputs,
        "golden_cases": seeded["golden_cases"],
        "counts": {**retained["counts"], "seeded_case_count": len(seeded["cases"])},
        "action_bytes_unchanged": all(case.get("action_bytes_unchanged", True) for case in seeded["cases"]),
        "retained_invariance_pass_count": 0,
        "regeneration_command": "uv run sim2claw sail-compile-invariance --config configs/sail/invariance_v1.json --output outputs/sail/retired-bg-v1/invariance",
        "authority": copy.deepcopy(config["authority"]),
        "claim_boundary": retained["claim_boundary"],
    }
    receipt = {**unsigned_receipt, "receipt_digest": canonical_digest(unsigned_receipt)}
    receipt_path = output_root / "receipt.json"
    atomic_write_json(receipt_path, receipt)
    verify_invariance_receipt(receipt, output_root=output_root, repo_root=repo_root)
    return {
        "schema_version": "sim2claw.sail_invariance_compile_result.v1",
        "campaign_id": config["campaign_id"],
        "status": "compiled",
        "golden_cases": receipt["golden_cases"],
        "counts": receipt["counts"],
        "receipt_sha256": sha256_file(receipt_path),
        "receipt_digest": receipt["receipt_digest"],
        "output_root": str(output_root),
        "training_admitted": False,
        "physical_authority": False,
    }


__all__ = ["InvarianceError", "compile_invariance", "compile_retained_invariance", "evaluate_invariance", "run_seeded_invariance_benchmarks", "verify_invariance_receipt"]

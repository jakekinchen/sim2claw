"""Bounded conditional posterior fitting for separate SAIL structure particles."""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.optimize import least_squares

from ..learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .contracts import REPO_ROOT, SailContractError, verify_contract, verify_source_binding
from .importers import load_json_object
from .mechanisms import MechanismError, MechanismPlugin, load_mechanism_registry
from .structural_surprise import verify_surprise_artifact


PARTICLE_SCHEMA = "sim2claw.sail_structure_particle_posterior.v1"
RECEIPT_SCHEMA = "sim2claw.sail_mechanism_compile_receipt.v1"


class PosteriorError(SailContractError):
    """A structure-particle fit escaped bounds or collapsed incompatible models."""


def _action_identity(actions: np.ndarray) -> dict[str, Any]:
    contiguous = np.ascontiguousarray(actions)
    return {
        "shape": list(contiguous.shape),
        "dtype": contiguous.dtype.str,
        "sha256": hashlib.sha256(contiguous.tobytes(order="C")).hexdigest(),
    }


def _subset_design(design: Mapping[str, np.ndarray], indices: np.ndarray) -> dict[str, np.ndarray]:
    return {name: np.asarray(values)[indices] for name, values in design.items()}


def fit_structure_particle(
    plugin: MechanismPlugin,
    *,
    design: Mapping[str, Sequence[float] | np.ndarray],
    observations: Sequence[float] | np.ndarray,
    available_observables: Sequence[str],
    seed: int,
    bootstrap_replicates: int,
    confidence_level: float,
    actions: np.ndarray,
) -> dict[str, Any]:
    observable_status = plugin.observable_status(available_observables)
    action_before = _action_identity(actions)
    if observable_status["status"] != "available":
        unsigned = {
            "schema_version": PARTICLE_SCHEMA,
            "particle_id": f"particle:{plugin.mechanism_id}",
            "mechanism_id": plugin.mechanism_id,
            "family": plugin.family,
            "status": "abstain_missing_observables",
            "missing_observables": observable_status["missing_observables"],
            "parameters": None,
            "uncertainty": None,
            "score": None,
            "action_identity": action_before,
            "action_bytes_unchanged": True,
            "physical_mechanism_identified": False,
        }
        return {**unsigned, "particle_digest": canonical_digest(unsigned)}
    observed = np.asarray(observations, dtype=np.float64)
    normalized_design = {name: np.asarray(values, dtype=np.float64) for name, values in design.items()}
    if observed.ndim != 1 or observed.size < 3 or not np.all(np.isfinite(observed)):
        raise PosteriorError("posterior observations are invalid")
    if any(values.shape != observed.shape or not np.all(np.isfinite(values)) for values in normalized_design.values()):
        raise PosteriorError("posterior design is invalid")
    lower, upper = plugin.bounds

    def residuals(parameters: np.ndarray) -> np.ndarray:
        return plugin.predict(normalized_design, parameters, actions=actions) - observed

    fit = least_squares(
        residuals,
        plugin.initial,
        bounds=(lower, upper),
        method="trf",
        xtol=1e-12,
        ftol=1e-12,
        gtol=1e-12,
        max_nfev=5000,
    )
    if not fit.success:
        raise PosteriorError(f"bounded fit failed: {plugin.mechanism_id}")
    fitted = plugin.validate_parameters(fit.x)
    residual_vector = residuals(fitted)
    sse = float(np.dot(residual_vector, residual_vector))
    parameter_count = len(fitted)
    sample_count = observed.size
    variance = max(sse / max(sample_count - parameter_count, 1), 1e-15)
    covariance = variance * np.linalg.pinv(fit.jac.T @ fit.jac, hermitian=True)
    laplace_std = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    rng = np.random.default_rng(seed)
    bootstrap_samples: list[np.ndarray] = []
    for _ in range(bootstrap_replicates):
        indices = rng.integers(0, sample_count, size=sample_count)
        design_bootstrap = _subset_design(normalized_design, indices)
        observed_bootstrap = observed[indices]

        def bootstrap_residuals(parameters: np.ndarray) -> np.ndarray:
            return plugin.predict(design_bootstrap, parameters, actions=actions) - observed_bootstrap

        bootstrap_fit = least_squares(
            bootstrap_residuals,
            fitted,
            bounds=(lower, upper),
            method="trf",
            xtol=1e-10,
            ftol=1e-10,
            gtol=1e-10,
            max_nfev=2000,
        )
        if not bootstrap_fit.success:
            raise PosteriorError(f"bootstrap fit failed: {plugin.mechanism_id}")
        bootstrap_samples.append(plugin.validate_parameters(bootstrap_fit.x))
    samples = np.stack(bootstrap_samples, axis=0)
    alpha = (1.0 - confidence_level) / 2.0
    interval_lower = np.quantile(samples, alpha, axis=0)
    interval_upper = np.quantile(samples, 1.0 - alpha, axis=0)
    if np.any(samples < lower) or np.any(samples > upper):
        raise PosteriorError("posterior bootstrap sample escaped declared bounds")
    mean_squared_error = max(sse / sample_count, 1e-15)
    bic = float(sample_count * np.log(mean_squared_error) + parameter_count * np.log(sample_count))
    action_after = _action_identity(actions)
    if action_before != action_after:
        raise PosteriorError("posterior fitting mutated source actions")
    parameter_rows = [
        {
            "name": name,
            "value": float(fitted[index]),
            "minimum": float(lower[index]),
            "maximum": float(upper[index]),
            "laplace_std": float(laplace_std[index]),
            "bootstrap_interval": [float(interval_lower[index]), float(interval_upper[index])],
        }
        for index, name in enumerate(plugin.parameter_names)
    ]
    unsigned = {
        "schema_version": PARTICLE_SCHEMA,
        "particle_id": f"particle:{plugin.mechanism_id}",
        "mechanism_id": plugin.mechanism_id,
        "family": plugin.family,
        "status": "fitted_conditional_structure_particle",
        "missing_observables": [],
        "parameters": parameter_rows,
        "uncertainty": {
            "laplace_covariance": covariance.tolist(),
            "bootstrap_replicates": bootstrap_replicates,
            "bootstrap_seed": seed,
            "confidence_level": confidence_level,
            "bootstrap_samples_digest": canonical_digest(samples.tolist()),
        },
        "score": {"sse": sse, "bic": bic, "sample_count": sample_count},
        "action_identity": action_before,
        "action_bytes_unchanged": True,
        "physical_mechanism_identified": False,
    }
    return {**unsigned, "particle_digest": canonical_digest(unsigned)}


def rank_structure_particles(particles: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    supported = [row for row in particles if row["status"] == "fitted_conditional_structure_particle"]
    ranked = sorted(
        supported,
        key=lambda row: (float(row["score"]["bic"]), str(row["mechanism_id"])),
    )
    return [
        {
            "rank": index,
            "particle_id": row["particle_id"],
            "mechanism_id": row["mechanism_id"],
            "family": row["family"],
            "bic": row["score"]["bic"],
            "particle_digest": row["particle_digest"],
        }
        for index, row in enumerate(ranked, start=1)
    ]


def _fit_case(
    *,
    case_id: str,
    expected_mechanism: str,
    candidates: Sequence[MechanismPlugin],
    designs: Mapping[str, Mapping[str, np.ndarray]],
    observations: np.ndarray,
    available: Mapping[str, Sequence[str]],
    actions: np.ndarray,
    seed: int,
    replicates: int,
    confidence_level: float,
) -> dict[str, Any]:
    particles = [
        fit_structure_particle(
            plugin,
            design=designs[plugin.mechanism_id],
            observations=observations,
            available_observables=available[plugin.mechanism_id],
            seed=seed + index,
            bootstrap_replicates=replicates,
            confidence_level=confidence_level,
            actions=actions,
        )
        for index, plugin in enumerate(candidates)
    ]
    ranking = rank_structure_particles(particles)
    winner = ranking[0]["mechanism_id"] if ranking else None
    return {
        "case_id": case_id,
        "expected_mechanism": expected_mechanism,
        "winner": winner,
        "passed": winner == expected_mechanism,
        "particles": particles,
        "ranking": ranking,
        "action_identity": _action_identity(actions),
        "action_bytes_unchanged": all(row["action_bytes_unchanged"] for row in particles),
        "structures_averaged": False,
    }


def run_seeded_mechanism_benchmarks(
    plugins: Mapping[str, MechanismPlugin], config: Mapping[str, Any]
) -> dict[str, Any]:
    seed = int(config["bootstrap"]["seed"])
    replicates = int(config["bootstrap"]["replicates"])
    confidence = float(config["bootstrap"]["confidence_level"])
    rng = np.random.default_rng(seed)
    actions = rng.normal(size=(64, 6)).astype(np.float32)
    action_before = _action_identity(actions)

    load = np.linspace(-1.0, 1.0, 80)
    load_observed = -0.75 * load + rng.normal(0.0, 0.01, size=load.size)
    load_case = _fit_case(
        case_id="GOLD-06",
        expected_mechanism="load_compliance_v1",
        candidates=(plugins["load_compliance_v1"], plugins["metric_geometry_v1"]),
        designs={
            "load_compliance_v1": {"load": load},
            "metric_geometry_v1": {"ones": np.ones_like(load)},
        },
        observations=load_observed,
        available={
            "load_compliance_v1": plugins["load_compliance_v1"].contract["required_observables"],
            "metric_geometry_v1": plugins["metric_geometry_v1"].contract["required_observables"],
        },
        actions=actions,
        seed=seed + 100,
        replicates=replicates,
        confidence_level=confidence,
    )

    penetration = np.linspace(0.0, 0.012, 90)
    contact_observed = 5.0 * np.maximum(penetration - 0.003, 0.0) + rng.normal(
        0.0, 0.0005, size=penetration.size
    )
    contact_case = _fit_case(
        case_id="GOLD-07",
        expected_mechanism="fingertip_contact_v1",
        candidates=(plugins["fingertip_contact_v1"], plugins["gripper_aperture_v1"]),
        designs={
            "fingertip_contact_v1": {"penetration": penetration},
            "gripper_aperture_v1": {"aperture_command": penetration},
        },
        observations=contact_observed,
        available={
            "fingertip_contact_v1": plugins["fingertip_contact_v1"].contract["required_observables"],
            "gripper_aperture_v1": plugins["gripper_aperture_v1"].contract["required_observables"],
        },
        actions=actions,
        seed=seed + 200,
        replicates=replicates,
        confidence_level=confidence,
    )

    temporal_gradient = rng.uniform(-2.0, 2.0, 100)
    image_x = rng.uniform(-1.0, 1.0, 100)
    camera_observed = 0.06 * temporal_gradient + 0.2 * image_x + rng.normal(
        0.0, 0.002, size=temporal_gradient.size
    )
    camera_case = _fit_case(
        case_id="GOLD-08",
        expected_mechanism="camera_timing_extrinsics_v1",
        candidates=(plugins["camera_timing_extrinsics_v1"], plugins["metric_geometry_v1"]),
        designs={
            "camera_timing_extrinsics_v1": {"temporal_gradient": temporal_gradient, "image_x": image_x},
            "metric_geometry_v1": {"ones": np.ones_like(temporal_gradient)},
        },
        observations=camera_observed,
        available={
            "camera_timing_extrinsics_v1": plugins["camera_timing_extrinsics_v1"].contract["required_observables"],
            "metric_geometry_v1": plugins["metric_geometry_v1"].contract["required_observables"],
        },
        actions=actions,
        seed=seed + 300,
        replicates=replicates,
        confidence_level=confidence,
    )
    cases = [load_case, contact_case, camera_case]
    if _action_identity(actions) != action_before:
        raise PosteriorError("seeded mechanism benchmark mutated actions")
    if not all(case["passed"] and case["action_bytes_unchanged"] for case in cases):
        raise PosteriorError("seeded mechanism benchmark failed")
    return {
        "schema_version": "sim2claw.sail_seeded_mechanism_benchmarks.v1",
        "seed": seed,
        "bootstrap_replicates": replicates,
        "cases": cases,
        "passed_case_ids": [case["case_id"] for case in cases if case["passed"]],
        "all_passed": True,
        "action_identity": action_before,
        "action_bytes_unchanged": True,
        "structures_averaged": False,
    }


def _retained_particles(
    plugins: Mapping[str, MechanismPlugin],
    wrappers: Mapping[str, Mapping[str, Any]],
    config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    available = config["current_observables"]
    rows: list[dict[str, Any]] = []
    for mechanism_id in sorted(plugins):
        plugin = plugins[mechanism_id]
        observable_status = plugin.observable_status(available)
        wrapper = wrappers[mechanism_id]
        rows.append(
            {
                "particle_id": f"retained:{mechanism_id}",
                "mechanism_id": mechanism_id,
                "family": plugin.family,
                "status": (
                    "historical_configuration_only_not_refit"
                    if observable_status["status"] == "available" and wrapper["parameters"]
                    else "abstain_missing_observables"
                    if observable_status["status"] != "available"
                    else "contract_only_no_retained_fit"
                ),
                "historical_parameters": copy.deepcopy(wrapper["parameters"]),
                "missing_observables": observable_status["missing_observables"],
                "structure_particle_separate": True,
                "physical_mechanism_identified": False,
            }
        )
    return rows


def verify_mechanism_receipt(
    receipt: Mapping[str, Any], *, output_root: Path, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(receipt))
    if normalized.get("schema_version") != RECEIPT_SCHEMA:
        raise PosteriorError("unexpected mechanism compile receipt schema")
    observed = normalized.pop("receipt_digest", None)
    if observed != canonical_digest(normalized):
        raise PosteriorError("mechanism compile receipt digest mismatch")
    authority = normalized.get("authority")
    if not isinstance(authority, dict) or any(authority.values()):
        raise PosteriorError("mechanism compile receipt widened authority")
    config_binding = normalized.get("config") or {}
    config_path = repo_root / str(config_binding.get("path", ""))
    if not config_path.is_file() or sha256_file(config_path) != config_binding.get("sha256"):
        raise PosteriorError("mechanism compile receipt config changed")
    for relative_path, expected_sha256 in (normalized.get("compiler_sha256") or {}).items():
        path = repo_root / str(relative_path)
        if not path.is_file() or sha256_file(path) != expected_sha256:
            raise PosteriorError(f"mechanism compiler changed: {relative_path}")
    for name, binding in (normalized.get("outputs") or {}).items():
        path = output_root / str(binding.get("path", ""))
        if not path.is_file() or sha256_file(path) != binding.get("sha256"):
            raise PosteriorError(f"mechanism output changed: {name}")
    return {**normalized, "receipt_digest": str(observed)}


def compile_mechanisms(
    config_path: Path,
    *,
    output_root: Path,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    config, plugins, wrappers = load_mechanism_registry(config_path, repo_root=repo_root)
    resolved_config = config_path if config_path.is_absolute() else repo_root / config_path
    residual_path = verify_source_binding(config["source_bindings"]["residual_field"], repo_root=repo_root)
    verify_contract(load_json_object(residual_path, label="mechanism residual source"))
    surprise_path = verify_source_binding(config["source_bindings"]["surprise"], repo_root=repo_root)
    verify_surprise_artifact(load_json_object(surprise_path, label="mechanism surprise source"))
    registry_artifact = {
        "schema_version": "sim2claw.sail_mechanism_registry_artifact.v1",
        "registry_id": config["registry_id"],
        "generated_at": config["generated_at"],
        "plugins": [
            {
                "contract": copy.deepcopy(dict(plugins[mechanism_id].contract)),
                "prediction_model": copy.deepcopy(dict(plugins[mechanism_id].prediction_model)),
                "retained_observable_status": plugins[mechanism_id].observable_status(config["current_observables"]),
                "historical_wrapper": copy.deepcopy(wrappers[mechanism_id]),
            }
            for mechanism_id in sorted(plugins)
        ],
        "authority": copy.deepcopy(config["authority"]),
        "claim_boundary": "Plugins are bounded executable hypotheses. Historical wrappers reproduce configurations without revising results, and retained availability does not identify a physical mechanism.",
    }
    benchmarks = run_seeded_mechanism_benchmarks(plugins, config)
    retained = {
        "schema_version": "sim2claw.sail_retained_structure_particles.v1",
        "particles": _retained_particles(plugins, wrappers, config),
        "structures_averaged": False,
        "physical_mechanism_identified": False,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    registry_path = output_root / "registry.json"
    benchmark_path = output_root / "seeded_posteriors.json"
    retained_path = output_root / "retained_particles.json"
    atomic_write_json(registry_path, registry_artifact)
    atomic_write_json(benchmark_path, benchmarks)
    atomic_write_json(retained_path, retained)
    outputs = {
        "registry": {"path": registry_path.name, "sha256": sha256_file(registry_path)},
        "seeded_posteriors": {"path": benchmark_path.name, "sha256": sha256_file(benchmark_path)},
        "retained_particles": {"path": retained_path.name, "sha256": sha256_file(retained_path)},
    }
    code_paths = (
        "src/sim2claw/sail/mechanisms.py",
        "src/sim2claw/sail/posterior.py",
    )
    unsigned_receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "registry_id": config["registry_id"],
        "generated_at": config["generated_at"],
        "config": {"path": resolved_config.resolve().relative_to(repo_root.resolve()).as_posix(), "sha256": sha256_file(resolved_config)},
        "compiler_sha256": {path: sha256_file(repo_root / path) for path in code_paths},
        "source_sha256": {name: binding["sha256"] for name, binding in sorted(config["source_bindings"].items())},
        "outputs": outputs,
        "counts": {
            "plugin_count": len(plugins),
            "historical_wrapper_count": len(wrappers),
            "retained_abstention_count": sum(row["status"] == "abstain_missing_observables" for row in retained["particles"]),
            "seeded_case_count": len(benchmarks["cases"]),
            "seeded_fitted_particle_count": sum(len(case["particles"]) for case in benchmarks["cases"]),
        },
        "golden_cases": {case["case_id"]: case["passed"] for case in benchmarks["cases"]},
        "action_bytes_unchanged": benchmarks["action_bytes_unchanged"],
        "structures_averaged": False,
        "regeneration_command": "uv run sim2claw sail-compile-mechanisms --config configs/sail/mechanism_registry_v1.json --output outputs/sail/retired-bg-v1/mechanisms",
        "authority": copy.deepcopy(config["authority"]),
        "claim_boundary": registry_artifact["claim_boundary"],
    }
    receipt = {**unsigned_receipt, "receipt_digest": canonical_digest(unsigned_receipt)}
    receipt_path = output_root / "receipt.json"
    atomic_write_json(receipt_path, receipt)
    verify_mechanism_receipt(receipt, output_root=output_root, repo_root=repo_root)
    return {
        "schema_version": "sim2claw.sail_mechanism_compile_result.v1",
        "registry_id": config["registry_id"],
        "status": "compiled",
        "counts": receipt["counts"],
        "golden_cases": receipt["golden_cases"],
        "registry_sha256": sha256_file(registry_path),
        "seeded_posteriors_sha256": sha256_file(benchmark_path),
        "retained_particles_sha256": sha256_file(retained_path),
        "receipt_sha256": sha256_file(receipt_path),
        "receipt_digest": receipt["receipt_digest"],
        "output_root": str(output_root),
        "training_admitted": False,
        "physical_authority": False,
    }


__all__ = [
    "PosteriorError",
    "compile_mechanisms",
    "fit_structure_particle",
    "rank_structure_particles",
    "run_seeded_mechanism_benchmarks",
    "verify_mechanism_receipt",
]

"""SAIL PhysicalMechanism.v1 plugin ABI and deterministic registry."""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .contracts import REPO_ROOT, SailContractError, seal_contract, verify_contract, verify_source_binding
from .importers import load_json_object


REGISTRY_SCHEMA = "sim2claw.sail_mechanism_registry.v1"


class MechanismError(SailContractError):
    """A mechanism plugin violated its ABI, bounds, or evidence requirements."""


def _array_identity(array: np.ndarray) -> dict[str, Any]:
    contiguous = np.ascontiguousarray(array)
    return {
        "shape": list(contiguous.shape),
        "dtype": contiguous.dtype.str,
        "sha256": hashlib.sha256(contiguous.tobytes(order="C")).hexdigest(),
    }


def json_pointer(payload: Any, pointer: str) -> Any:
    if pointer == "":
        return payload
    if not pointer.startswith("/"):
        raise MechanismError("historical binding uses an invalid JSON pointer")
    current = payload
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            try:
                current = current[int(token)]
            except (ValueError, IndexError) as error:
                raise MechanismError("historical list pointer is invalid") from error
        elif isinstance(current, dict) and token in current:
            current = current[token]
        else:
            raise MechanismError(f"historical binding pointer is missing: {pointer}")
    return current


@dataclass(frozen=True)
class MechanismPlugin:
    contract: Mapping[str, Any]
    prediction_model: Mapping[str, Any]

    @property
    def mechanism_id(self) -> str:
        return str(self.contract["mechanism_id"])

    @property
    def family(self) -> str:
        return str(self.contract["family"])

    @property
    def parameter_names(self) -> tuple[str, ...]:
        return tuple(str(row["name"]) for row in self.contract["parameters"])

    @property
    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        lower = np.asarray([float(row["minimum"]) for row in self.contract["parameters"]])
        upper = np.asarray([float(row["maximum"]) for row in self.contract["parameters"]])
        return lower, upper

    @property
    def initial(self) -> np.ndarray:
        values: list[float] = []
        lower, upper = self.bounds
        for index, row in enumerate(self.contract["parameters"]):
            prior = row["prior"]
            candidate = prior.get("mean", prior.get("median", (lower[index] + upper[index]) / 2.0))
            values.append(float(np.clip(float(candidate), lower[index], upper[index])))
        return np.asarray(values, dtype=np.float64)

    def observable_status(self, available: Sequence[str]) -> dict[str, Any]:
        available_set = set(str(item) for item in available)
        required = set(str(item) for item in self.contract["required_observables"])
        missing = sorted(required - available_set)
        return {
            "status": "available" if not missing else "abstain_missing_observables",
            "missing_observables": missing,
            "required_observables": sorted(required),
        }

    def validate_parameters(self, parameters: Mapping[str, float] | Sequence[float]) -> np.ndarray:
        if isinstance(parameters, Mapping):
            if set(parameters) != set(self.parameter_names):
                raise MechanismError(f"parameter set changed for {self.mechanism_id}")
            values = np.asarray([parameters[name] for name in self.parameter_names], dtype=np.float64)
        else:
            values = np.asarray(parameters, dtype=np.float64)
        if values.shape != (len(self.parameter_names),) or not np.all(np.isfinite(values)):
            raise MechanismError(f"invalid parameter vector for {self.mechanism_id}")
        lower, upper = self.bounds
        if np.any(values < lower) or np.any(values > upper):
            raise MechanismError(f"parameter outside declared bounds for {self.mechanism_id}")
        return values

    def predict(
        self,
        design: Mapping[str, Sequence[float] | np.ndarray],
        parameters: Mapping[str, float] | Sequence[float],
        *,
        actions: np.ndarray | None = None,
    ) -> np.ndarray:
        values = self.validate_parameters(parameters)
        before = None if actions is None else _array_identity(actions)
        kind = str(self.prediction_model["kind"])
        if kind == "linear":
            features = [
                np.asarray(design[name], dtype=np.float64)
                for name in self.prediction_model["features"]
            ]
            if len(features) != len(values) or not features:
                raise MechanismError("linear mechanism design/parameter dimensions changed")
            shape = features[0].shape
            if len(shape) != 1 or any(feature.shape != shape for feature in features):
                raise MechanismError("linear mechanism design columns are misaligned")
            prediction = sum(value * feature for value, feature in zip(values, features, strict=True))
        elif kind == "hinge":
            feature = np.asarray(design[self.prediction_model["feature"]], dtype=np.float64)
            threshold_index = self.parameter_names.index(str(self.prediction_model["threshold_parameter"]))
            gain_index = self.parameter_names.index(str(self.prediction_model["gain_parameter"]))
            prediction = values[gain_index] * np.maximum(feature - values[threshold_index], 0.0)
        else:
            raise MechanismError(f"unsupported prediction model: {kind}")
        if prediction.ndim != 1 or not np.all(np.isfinite(prediction)):
            raise MechanismError("mechanism prediction is invalid")
        if actions is not None and _array_identity(actions) != before:
            raise MechanismError("mechanism prediction mutated source actions")
        return np.asarray(prediction, dtype=np.float64)


def _plugin_contract(row: Mapping[str, Any]) -> dict[str, Any]:
    fields = {
        key: copy.deepcopy(row[key])
        for key in (
            "mechanism_id",
            "family",
            "physical_interpretation",
            "affected_components",
            "parameters",
            "predicted_residual_signatures",
            "required_observables",
            "non_identifiabilities",
            "candidate_interventions",
            "simulator_mutation",
            "graph_factors",
            "influence_edges",
            "invalidation_rules",
            "invariance_scope",
            "action_immutability_tests",
        )
    }
    return seal_contract(
        {
            "schema_version": "sim2claw.physical_mechanism.v1",
            "version": 1,
            **fields,
        }
    )


def build_mechanism_plugin(row: Mapping[str, Any]) -> MechanismPlugin:
    contract = verify_contract(_plugin_contract(row))
    return MechanismPlugin(
        contract=contract,
        prediction_model=copy.deepcopy(row["prediction_model"]),
    )


def load_mechanism_registry(
    path: Path, *, repo_root: Path = REPO_ROOT
) -> tuple[dict[str, Any], dict[str, MechanismPlugin], dict[str, dict[str, Any]]]:
    resolved = path if path.is_absolute() else repo_root / path
    config = load_json_object(resolved, label="SAIL mechanism registry")
    if config.get("schema_version") != REGISTRY_SCHEMA:
        raise MechanismError("unexpected SAIL mechanism registry schema")
    authority = config.get("authority")
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise MechanismError("mechanism registry widened authority")
    source_paths = {
        name: verify_source_binding(binding, repo_root=repo_root)
        for name, binding in config["source_bindings"].items()
    }
    rows = config.get("plugins") or []
    ids = [str(row.get("mechanism_id", "")) for row in rows]
    if len(ids) != 10 or len(ids) != len(set(ids)) or any(not value for value in ids):
        raise MechanismError("mechanism registry plugin identity changed")
    plugins: dict[str, MechanismPlugin] = {}
    wrappers: dict[str, dict[str, Any]] = {}
    for row in rows:
        plugin = build_mechanism_plugin(row)
        plugins[plugin.mechanism_id] = plugin
        binding = row["historical_binding"]
        source_id = str(binding["source_id"])
        if source_id not in source_paths:
            raise MechanismError("mechanism historical source is undeclared")
        source_payload = load_json_object(source_paths[source_id], label=f"mechanism source {source_id}")
        reproduced: dict[str, float] = {}
        for parameter in binding.get("parameters") or []:
            observed = json_pointer(source_payload, str(parameter["pointer"]))
            expected = parameter["expected"]
            if isinstance(expected, float):
                matched = bool(np.isclose(float(observed), expected, rtol=0.0, atol=1e-12))
            else:
                matched = observed == expected
            if not matched:
                raise MechanismError(f"historical wrapper changed: {plugin.mechanism_id}")
            reproduced[str(parameter["name"])] = float(observed)
        if reproduced:
            plugin.validate_parameters(reproduced)
        wrappers[plugin.mechanism_id] = {
            "mechanism_id": plugin.mechanism_id,
            "source_id": source_id,
            "source": copy.deepcopy(config["source_bindings"][source_id]),
            "status": binding.get("status", "historical_configuration_reproduced"),
            "parameters": reproduced,
            "historical_result_mutated": False,
        }
    return config, plugins, wrappers


__all__ = [
    "MechanismError",
    "MechanismPlugin",
    "build_mechanism_plugin",
    "json_pointer",
    "load_mechanism_registry",
]

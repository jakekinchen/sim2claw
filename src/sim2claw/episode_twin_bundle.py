"""Deterministic physical-source EpisodeTwinBundle.v1 compiler."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .paths import REPO_ROOT


CONTRACT_SCHEMA = "sim2claw.episode_twin_bundle_contract.v1"
BUNDLE_SCHEMA = "sim2claw.episode_twin_bundle.v1"
RECEIPT_SCHEMA = "sim2claw.episode_twin_bundle_receipt.v1"
CONTRACT_PATH = (
    REPO_ROOT / "configs" / "evaluations" / "episode_twin_bundle_v1.json"
)
OUTPUT_DIRECTORY = REPO_ROOT / "outputs" / "episode_twin_bundle_v1"
RECEIPT_PATH = OUTPUT_DIRECTORY / "receipt.json"


def _require_file_hash(path: Path, expected: str, label: str) -> None:
    if not path.is_file() or len(expected) != 64 or sha256_file(path) != expected:
        raise FactoryArtifactError(f"{label} hash rejected: {path}")


def load_bundle_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="episode twin bundle contract")
    if contract.get("schema_version") != CONTRACT_SCHEMA:
        raise FactoryArtifactError("unsupported episode twin bundle contract")
    corpus = contract.get("corpus")
    observation = contract.get("initial_mission_observation")
    tensors = contract.get("tensor_contract")
    if not all(
        isinstance(value, dict) for value in (corpus, observation, tensors)
    ):
        raise FactoryArtifactError("episode twin bundle contract is incomplete")
    for path_key, hash_key, label in (
        ("closeout_path", "closeout_sha256", "corpus closeout"),
        ("receipt_path", "receipt_sha256", "corpus receipt"),
    ):
        _require_file_hash(
            root / corpus[path_key], str(corpus[hash_key]), label
        )
    for path_key, hash_key, label in (
        ("receipt_path", "receipt_file_sha256", "initial observation receipt"),
        ("closeout_path", "closeout_sha256", "initial observation closeout"),
    ):
        _require_file_hash(
            root / observation[path_key],
            str(observation[hash_key]),
            label,
        )
    corpus_receipt = load_json_object(
        root / corpus["receipt_path"], label="corpus receipt"
    )
    if corpus_receipt.get("artifact_sha256") != corpus["artifact_sha256"]:
        raise FactoryArtifactError("corpus artifact identity changed")
    observation_receipt = load_json_object(
        root / observation["receipt_path"], label="initial observation receipt"
    )
    if (
        observation_receipt.get("receipt_sha256")
        != observation["receipt_canonical_sha256"]
    ):
        raise FactoryArtifactError("initial observation identity changed")
    if observation.get("terminal_observation_as_replay_input_allowed") is not False:
        raise FactoryArtifactError("terminal endpoint injection was enabled")
    authority = contract.get("authority")
    if not isinstance(authority, dict) or any(authority.values()):
        raise FactoryArtifactError("episode twin bundle authority widened")
    missing = contract.get("explicitly_missing_observables")
    if not isinstance(missing, list) or len(missing) != len(set(missing)):
        raise FactoryArtifactError("missing-observable list is invalid")
    if set(tensors) != {
        "joint_order",
        "operator_requested",
        "gateway_sent",
        "measured_joints",
        "source_timestamps",
    }:
        raise FactoryArtifactError("tensor contract fields changed")
    if len(tensors["joint_order"]) != 6:
        raise FactoryArtifactError("joint order must contain six joints")
    return contract


def _load_rows(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as error:
        raise FactoryArtifactError(f"cannot read bundle source {path}: {error}") from error
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise FactoryArtifactError(f"bundle source is empty or invalid: {path}")
    return rows


def _tensor(
    rows: list[dict[str, Any]], source_field: str, dtype: str, width: int | None
) -> np.ndarray:
    values = [row.get(source_field) for row in rows]
    array = np.asarray(values, dtype=np.dtype(dtype), order="C")
    expected_shape = (len(rows),) if width is None else (len(rows), width)
    if array.shape != expected_shape or not np.isfinite(array).all():
        raise FactoryArtifactError(
            f"{source_field} is not finite with shape {expected_shape}"
        )
    return np.ascontiguousarray(array)


def _raw_sha256(array: np.ndarray) -> str:
    return hashlib.sha256(array.tobytes(order="C")).hexdigest()


def compile_episode_bundle(
    *,
    corpus_episode: dict[str, Any],
    rows: list[dict[str, Any]],
    contract: dict[str, Any],
    initial_observation: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    recording_id = str(corpus_episode["recording_id"])
    if len(rows) != int(corpus_episode["sample_count"]):
        raise FactoryArtifactError(f"bundle source row count changed: {recording_id}")
    tensors = contract["tensor_contract"]
    arrays = {
        "operator_requested": _tensor(
            rows,
            tensors["operator_requested"]["source_field"],
            tensors["operator_requested"]["dtype"],
            6,
        ),
        "gateway_sent": _tensor(
            rows,
            tensors["gateway_sent"]["source_field"],
            tensors["gateway_sent"]["dtype"],
            6,
        ),
        "measured_joints": _tensor(
            rows,
            tensors["measured_joints"]["source_field"],
            tensors["measured_joints"]["dtype"],
            6,
        ),
        "source_timestamps": _tensor(
            rows,
            tensors["source_timestamps"]["source_field"],
            tensors["source_timestamps"]["dtype"],
            None,
        ),
    }
    if not np.all(np.diff(arrays["source_timestamps"]) > 0.0):
        raise FactoryArtifactError(f"bundle timestamps are not increasing: {recording_id}")
    for name, array in arrays.items():
        expected = corpus_episode["channels"][
            {
                "operator_requested": "operator_requested",
                "gateway_sent": "gateway_sent",
                "measured_joints": "measured_joints",
                "source_timestamps": "source_timestamps",
            }[name]
        ]["little_endian_sha256"]
        if _raw_sha256(array) != expected:
            raise FactoryArtifactError(f"C0 tensor digest changed: {recording_id}:{name}")
    tensor_manifests = {}
    for name, array in arrays.items():
        spec = tensors[name]
        tensor_manifests[name] = {
            "source_field": spec["source_field"],
            "dtype": spec["dtype"],
            "unit": spec["unit"],
            "shape": list(array.shape),
            "raw_little_endian_sha256": _raw_sha256(array),
            "file": f"{name}.{spec['dtype'].replace('<', '')}le.bin",
            "file_sha256": None,
            "first_row": (
                array[0].tolist() if array.ndim == 2 else float(array[0])
            ),
        }
    timestamp_spec = tensor_manifests["source_timestamps"]
    timestamp_spec["time_origin"] = tensors["source_timestamps"]["time_origin"]
    timestamp_spec["actuator_application_semantics"] = False

    unsigned = {
        "schema_version": BUNDLE_SCHEMA,
        "bundle_id": f"episode-twin-{recording_id}",
        "recording_id": recording_id,
        "cohort_role": corpus_episode["role"],
        "proof_class": corpus_episode["proof_class"],
        "source": {
            "directory": corpus_episode["directory"],
            "sample_count": corpus_episode["sample_count"],
            "sample_hz": corpus_episode["sample_hz"],
            "coordinate_contract": corpus_episode["coordinate_contract"],
            "receipt_asset": next(
                asset
                for asset in corpus_episode["assets"]
                if asset["path"].endswith("/recording_receipt.json")
            ),
            "samples_asset": next(
                asset
                for asset in corpus_episode["assets"]
                if asset["path"].endswith("/samples.jsonl")
            ),
        },
        "joint_order": tensors["joint_order"],
        "tensors": tensor_manifests,
        "initial_object_observation": initial_observation,
        "terminal_object_observation_as_replay_input": None,
        "explicitly_missing_observables": contract[
            "explicitly_missing_observables"
        ],
        "claim_boundary": (
            "A deterministic physical-source evidence bundle. It is not a "
            "simulator replay, calibrated plant, contact model, or transfer result."
        ),
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}, arrays


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _write_one_bundle(
    bundle: dict[str, Any],
    arrays: dict[str, np.ndarray],
    output_directory: Path,
) -> dict[str, Any]:
    directory = output_directory / str(bundle["recording_id"])
    completed = json.loads(json.dumps(bundle))
    for name, array in arrays.items():
        file_name = completed["tensors"][name]["file"]
        path = directory / file_name
        payload = array.tobytes(order="C")
        _write_bytes(path, payload)
        completed["tensors"][name]["file_sha256"] = sha256_file(path)
    unsigned = {
        key: value for key, value in completed.items() if key != "artifact_sha256"
    }
    completed["artifact_sha256"] = canonical_digest(unsigned)
    bundle_path = directory / "bundle.json"
    atomic_write_json(bundle_path, completed)
    return {
        "recording_id": completed["recording_id"],
        "cohort_role": completed["cohort_role"],
        "bundle_path": bundle_path.relative_to(REPO_ROOT).as_posix()
        if output_directory.is_relative_to(REPO_ROOT)
        else bundle_path.as_posix(),
        "bundle_file_sha256": sha256_file(bundle_path),
        "bundle_artifact_sha256": completed["artifact_sha256"],
    }


def build_episode_twin_bundles(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_bundle_contract(contract_path, root=root)
    corpus = load_json_object(
        root / contract["corpus"]["receipt_path"], label="C0 corpus receipt"
    )
    required_roles = set(contract["corpus"]["required_roles"])
    selected = [
        episode
        for episode in corpus["episodes"]
        if episode["role"] in required_roles
    ]
    if len(selected) != int(contract["corpus"]["expected_bundle_count"]):
        raise FactoryArtifactError("bundle cohort count changed")
    observation_receipt = load_json_object(
        root / contract["initial_mission_observation"]["receipt_path"],
        label="initial mission observation",
    )
    initial = observation_receipt["observations"]["initial"]
    mission_id = contract["initial_mission_observation"]["recording_id"]
    bindings = []
    for episode in selected:
        samples_path = (
            root / episode["directory"] / "samples.jsonl"
        )
        rows = _load_rows(samples_path)
        initial_observation = None
        if episode["recording_id"] == mission_id:
            initial_observation = {
                "availability": "evaluator_owned_metric_initial_only",
                "square": initial["square"],
                "world_position_m": initial["world_position_m"],
                "board_coordinate": initial["board_coordinate"],
                "square_center_error_m": initial["square_center_error_m"],
                "source_receipt_path": contract[
                    "initial_mission_observation"
                ]["receipt_path"],
                "source_receipt_canonical_sha256": contract[
                    "initial_mission_observation"
                ]["receipt_canonical_sha256"],
                "terminal_observation_included": False,
            }
        bundle, arrays = compile_episode_bundle(
            corpus_episode=episode,
            rows=rows,
            contract=contract,
            initial_observation=initial_observation,
        )
        bindings.append(_write_one_bundle(bundle, arrays, output_directory))
    bindings.sort(key=lambda item: item["recording_id"])
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": sha256_file(contract_path),
        "corpus_artifact_sha256": corpus["artifact_sha256"],
        "bundle_count": len(bindings),
        "cohort_counts": {
            role: sum(item["cohort_role"] == role for item in bindings)
            for role in sorted(required_roles)
        },
        "bundles": bindings,
        "explicitly_missing_observables": contract[
            "explicitly_missing_observables"
        ],
        "authority": contract["authority"],
        "result": "PASS",
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_directory / "receipt.json", receipt)
    return receipt

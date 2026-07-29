"""Compile the frozen retrospective realized-action evidence corpus."""

from __future__ import annotations

import hashlib
import json
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


SCHEMA = "sim2claw.realized_action_retrospective_corpus.v1"
RECEIPT_SCHEMA = "sim2claw.realized_action_retrospective_corpus_receipt.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "realized_action_retrospective_corpus_v1.json"
)
OUTPUT_PATH = (
    REPO_ROOT
    / "outputs"
    / "realized_action_retrospective_corpus_v1"
    / "receipt.json"
)


def _require_hash(root: Path, binding: dict[str, Any], label: str) -> None:
    path = root / str(binding.get("path", ""))
    expected = str(binding.get("sha256", ""))
    if not path.is_file() or len(expected) != 64 or sha256_file(path) != expected:
        raise FactoryArtifactError(f"{label} hash rejected: {path}")


def load_corpus_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="retrospective corpus contract")
    if contract.get("schema_version") != SCHEMA:
        raise FactoryArtifactError("unsupported retrospective corpus schema")
    _require_hash(root, contract.get("catalog", {}), "catalog")
    correction = contract.get("canonical_correction")
    if not isinstance(correction, dict):
        raise FactoryArtifactError("canonical correction binding is missing")
    _require_hash(
        root,
        {
            "path": correction.get("binding_path"),
            "sha256": correction.get("binding_sha256"),
        },
        "canonical correction",
    )
    _require_hash(
        root,
        {
            "path": correction.get("closeout_path"),
            "sha256": correction.get("closeout_sha256"),
        },
        "canonical correction closeout",
    )

    cohorts = contract.get("cohorts")
    diagnostics = contract.get("diagnostic_roles")
    if not isinstance(cohorts, dict) or not isinstance(diagnostics, dict):
        raise FactoryArtifactError("corpus roles are missing")
    role_sets: dict[str, set[str]] = {}
    for role, values in {**cohorts, **diagnostics}.items():
        if not isinstance(values, list) or (role in cohorts and not values):
            raise FactoryArtifactError(f"invalid corpus role: {role}")
        role_sets[role] = {str(value) for value in values}
        if len(role_sets[role]) != len(values):
            raise FactoryArtifactError(f"duplicate recording in role: {role}")
    role_names = sorted(role_sets)
    for index, left in enumerate(role_names):
        for right in role_names[index + 1 :]:
            if role_sets[left] & role_sets[right]:
                raise FactoryArtifactError(
                    f"recording appears in both {left} and {right}"
                )
    sealed = role_sets["sealed"]
    correction_id = str(correction.get("recording_id", ""))
    if sealed != {correction_id}:
        raise FactoryArtifactError("sealed cohort is not the corrected mission episode")

    authority = contract.get("authority")
    if not isinstance(authority, dict) or any(authority.values()):
        raise FactoryArtifactError("retrospective corpus authority widened")
    boundaries = contract.get("proof_boundaries")
    if not isinstance(boundaries, dict) or any(boundaries.values()):
        raise FactoryArtifactError("retrospective proof boundary widened")
    assets = contract.get("asset_paths")
    if not isinstance(assets, list) or len(set(assets)) != len(assets):
        raise FactoryArtifactError("asset path inventory is invalid")
    return contract


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as error:
        raise FactoryArtifactError(f"cannot read source samples {path}: {error}") from error
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise FactoryArtifactError(f"source samples must contain JSON objects: {path}")
    return rows


def _tensor_binding(
    rows: list[dict[str, Any]], field: str, dtype: str
) -> dict[str, Any]:
    present = sum(
        isinstance(row.get(field), list) and len(row.get(field, [])) == 6
        for row in rows
    )
    result: dict[str, Any] = {
        "field": field,
        "available": present == len(rows),
        "present_row_count": present,
        "row_count": len(rows),
        "dtype": dtype,
        "little_endian_sha256": None,
    }
    if present != len(rows):
        return result
    array = np.asarray([row[field] for row in rows], dtype=np.dtype(dtype))
    if array.shape != (len(rows), 6) or not np.isfinite(array).all():
        raise FactoryArtifactError(f"{field} is not a finite Nx6 tensor")
    result["little_endian_sha256"] = hashlib.sha256(
        array.tobytes(order="C")
    ).hexdigest()
    return result


def _timestamp_binding(rows: list[dict[str, Any]]) -> dict[str, Any]:
    field = "timestamp_monotonic_seconds"
    present = sum(field in row for row in rows)
    result: dict[str, Any] = {
        "field": field,
        "available": present == len(rows),
        "present_row_count": present,
        "row_count": len(rows),
        "dtype": "<f8",
        "strictly_increasing": False,
        "little_endian_sha256": None,
        "actuator_application_or_ack_timestamp_row_count": 0,
    }
    result["actuator_application_or_ack_timestamp_row_count"] = sum(
        row.get("observability_timestamps", {}).get(
            "actuator_application_or_ack_timestamp_available"
        )
        is True
        for row in rows
        if isinstance(row.get("observability_timestamps"), dict)
    )
    if present != len(rows):
        return result
    timestamps = np.asarray([row[field] for row in rows], dtype="<f8")
    if not np.isfinite(timestamps).all():
        raise FactoryArtifactError("source timestamps are not finite")
    result["strictly_increasing"] = bool(np.all(np.diff(timestamps) > 0.0))
    result["little_endian_sha256"] = hashlib.sha256(
        timestamps.tobytes(order="C")
    ).hexdigest()
    return result


def _asset_inventory(
    directory: Path, root: Path, asset_paths: list[str]
) -> list[dict[str, Any]]:
    assets = []
    for relative in asset_paths:
        path = directory / relative
        if path.is_file():
            assets.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    return assets


def _role_lookup(contract: dict[str, Any]) -> dict[str, str]:
    roles: dict[str, str] = {}
    for section in ("cohorts", "diagnostic_roles"):
        for role, recording_ids in contract[section].items():
            for recording_id in recording_ids:
                roles[str(recording_id)] = str(role)
    return roles


def _catalog_lookup(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    episodes = catalog.get("episodes")
    if not isinstance(episodes, list):
        raise FactoryArtifactError("catalog episodes are missing")
    lookup: dict[str, dict[str, Any]] = {}
    for episode in episodes:
        if not isinstance(episode, dict):
            raise FactoryArtifactError("catalog episode is not an object")
        recording_id = str(episode.get("recording_id", ""))
        if not recording_id or recording_id in lookup:
            raise FactoryArtifactError("catalog recording identities are invalid")
        lookup[recording_id] = episode
    return lookup


def compile_corpus(
    contract: dict[str, Any], *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    catalog_binding = contract["catalog"]
    catalog = load_json_object(
        root / catalog_binding["path"], label="physical pawn catalog"
    )
    catalog_by_id = _catalog_lookup(catalog)
    if len(catalog_by_id) != int(catalog_binding["expected_episode_count"]):
        raise FactoryArtifactError("catalog episode count changed")
    role_by_id = _role_lookup(contract)
    episode_root = root / contract["episode_root"]
    directories = sorted(
        path
        for path in episode_root.iterdir()
        if path.is_dir()
        and (path / "recording_receipt.json").is_file()
        and (path / "samples.jsonl").is_file()
    )
    if len(directories) != int(contract["expected_discovered_episode_count"]):
        raise FactoryArtifactError("discovered episode count changed")

    correction = contract["canonical_correction"]
    episodes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for directory in directories:
        receipt_path = directory / "recording_receipt.json"
        samples_path = directory / "samples.jsonl"
        receipt = load_json_object(receipt_path, label="recording receipt")
        rows = _load_jsonl(samples_path)
        recording_id = str(receipt.get("recording_id", ""))
        if not recording_id or recording_id in seen:
            raise FactoryArtifactError("discovered recording identities are invalid")
        seen.add(recording_id)
        if int(receipt.get("sample_count", -1)) != len(rows):
            raise FactoryArtifactError(
                f"sample count disagrees with receipt: {recording_id}"
            )
        if [row.get("sample_index") for row in rows] != list(range(len(rows))):
            raise FactoryArtifactError(f"sample indices are not contiguous: {recording_id}")
        if any(row.get("recording_id") != recording_id for row in rows):
            raise FactoryArtifactError(f"sample recording identity drifted: {recording_id}")

        catalog_episode = catalog_by_id.get(recording_id)
        metadata_status = (
            str(catalog_episode.get("metadata_status"))
            if catalog_episode is not None
            else "not_in_20260719_catalog"
        )
        role = role_by_id.get(recording_id)
        if role is None:
            role = (
                "provenance_only_metadata_conflict"
                if metadata_status == "conflict_folder_label_vs_receipt"
                else "provenance_only_unselected"
            )
        if role in {"fit", "validation"} and metadata_status != (
            "consistent_folder_label_and_receipt"
        ):
            raise FactoryArtifactError(
                f"non-self-consistent legacy episode entered {role}: {recording_id}"
            )
        if recording_id == correction["recording_id"]:
            coordinate_contract = {
                "status": "evaluator_corrected_current_canonical",
                "raw_receipt_source_square": receipt.get("source_square"),
                "raw_receipt_destination_square": receipt.get("destination_square"),
                "canonical_source_square": correction["source_square"],
                "canonical_destination_square": correction["destination_square"],
                "binding_path": correction["binding_path"],
                "binding_sha256": correction["binding_sha256"],
            }
        elif metadata_status == "consistent_folder_label_and_receipt":
            coordinate_contract = {
                "status": "legacy_self_consistent_label_unmigrated_noncanonical",
                "raw_receipt_source_square": receipt.get("source_square"),
                "raw_receipt_destination_square": receipt.get("destination_square"),
                "canonical_source_square": None,
                "canonical_destination_square": None,
            }
        else:
            coordinate_contract = {
                "status": "raw_metadata_conflict_or_unreviewed_preserved",
                "raw_receipt_source_square": receipt.get("source_square"),
                "raw_receipt_destination_square": receipt.get("destination_square"),
                "canonical_source_square": None,
                "canonical_destination_square": None,
            }

        requested = _tensor_binding(rows, "follower_requested_degrees", "<f4")
        sent = _tensor_binding(rows, "follower_command_degrees", "<f4")
        measured = _tensor_binding(
            rows, "follower_actual_position_degrees", "<f8"
        )
        requested_sent_mismatch_count = sum(
            row.get("follower_requested_degrees")
            != row.get("follower_command_degrees")
            for row in rows
        )
        episodes.append(
            {
                "recording_id": recording_id,
                "directory": directory.relative_to(root).as_posix(),
                "role": role,
                "receipt_label": receipt.get("label"),
                "mode": receipt.get("mode"),
                "outcome_label": receipt.get("outcome_label"),
                "proof_class": receipt.get("proof_class"),
                "sample_count": len(rows),
                "sample_hz": receipt.get("sample_hz"),
                "metadata_status": metadata_status,
                "catalog_member": catalog_episode is not None,
                "coordinate_contract": coordinate_contract,
                "channels": {
                    "operator_requested": requested,
                    "gateway_sent": sent,
                    "measured_joints": measured,
                    "source_timestamps": _timestamp_binding(rows),
                    "requested_sent_mismatch_row_count": (
                        requested_sent_mismatch_count
                    ),
                    "rate_limited_row_count": sum(
                        row.get("rate_limited") is True for row in rows
                    ),
                    "safety_clamped_row_count": sum(
                        row.get("safety_clamped") is True for row in rows
                    ),
                    "precompiled_exact_row_count": sum(
                        row.get("precompiled_exact_action") is True for row in rows
                    ),
                },
                "assets": _asset_inventory(
                    directory, root, list(contract["asset_paths"])
                ),
            }
        )

    missing_declared = sorted(set(role_by_id) - seen)
    if missing_declared:
        raise FactoryArtifactError(
            f"declared recordings were not discovered: {missing_declared}"
        )
    cohort_sets = {
        role: sorted(str(value) for value in values)
        for role, values in contract["cohorts"].items()
    }
    discarded = catalog.get("discarded_recordings", [])
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": sha256_file(CONTRACT_PATH)
        if root == REPO_ROOT and CONTRACT_PATH.is_file()
        else canonical_digest(contract),
        "frozen_date": contract["frozen_date"],
        "catalog": {
            "path": catalog_binding["path"],
            "sha256": catalog_binding["sha256"],
            "episode_count": len(catalog_by_id),
            "discarded_recordings": discarded,
        },
        "episode_count": len(episodes),
        "cohorts": cohort_sets,
        "cohort_counts": {
            role: len(recording_ids)
            for role, recording_ids in cohort_sets.items()
        },
        "episodes": episodes,
        "proof_boundaries": contract["proof_boundaries"],
        "authority": contract["authority"],
        "result": "PASS",
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def build_corpus_receipt(
    contract_path: Path = CONTRACT_PATH,
    output_path: Path = OUTPUT_PATH,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_corpus_contract(contract_path, root=root)
    receipt = compile_corpus(contract, root=root)
    atomic_write_json(output_path, receipt)
    return receipt

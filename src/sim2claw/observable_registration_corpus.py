"""Freeze the retained evidence boundary for observable registration."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
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


SCHEMA = "sim2claw.observable_registration_corpus_contract.v1"
RECEIPT_SCHEMA = "sim2claw.observable_registration_corpus_receipt.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "observable_registration_corpus_v1.json"
)
OUTPUT_PATH = (
    REPO_ROOT
    / "outputs"
    / "observable_registration_corpus_v1"
    / "receipt.json"
)
ALLOWED_ROLES = {
    "fit",
    "validation_reuse_outcome_known",
    "retrospective_diagnostic",
    "sealed_source",
    "sealed_outcome",
}
ALLOWED_OBSERVABILITY = {
    "available",
    "bounded",
    "diagnostic",
    "recoverable",
    "unavailable",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _source_lookup(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sources = contract.get("sources")
    _require(isinstance(sources, list) and sources, "sources are missing")
    lookup: dict[str, dict[str, Any]] = {}
    paths: set[str] = set()
    for source in sources:
        _require(isinstance(source, dict), "source binding is not an object")
        source_id = str(source.get("id", ""))
        path = str(source.get("path", ""))
        role = str(source.get("role", ""))
        _require(source_id and source_id not in lookup, "source ids are invalid")
        _require(path and path not in paths, "source paths overlap roles")
        _require(role in ALLOWED_ROLES, f"unsupported source role: {role}")
        expected_hash = str(source.get("sha256", ""))
        _require(len(expected_hash) == 64, f"source hash is invalid: {source_id}")
        lookup[source_id] = source
        paths.add(path)
    return lookup


def _validate_bound_sources(
    contract: dict[str, Any], *, root: Path
) -> dict[str, dict[str, Any]]:
    lookup = _source_lookup(contract)
    for source_id, source in lookup.items():
        path = root / str(source["path"])
        _require(path.is_file(), f"bound source is missing: {source_id}")
        _require(
            sha256_file(path) == source["sha256"],
            f"bound source hash drifted: {source_id}",
        )
    return lookup


def load_inventory_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="observable registration corpus")
    _require(contract.get("schema_version") == SCHEMA, "unsupported corpus schema")
    lookup = _validate_bound_sources(contract, root=root)
    _require(
        str(contract.get("recording_id", "")),
        "sealed recording identity is missing",
    )

    streams = contract.get("camera_streams")
    _require(isinstance(streams, dict) and set(streams) == {"c922", "d405_rgb"}, "camera stream contract changed")
    for stream_id, stream in streams.items():
        _require(isinstance(stream, dict), f"{stream_id} stream is invalid")
        for source_key in ("metadata_source_id", "video_source_id"):
            _require(
                stream.get(source_key) in lookup,
                f"{stream_id} {source_key} is not bound",
            )
        _require(stream.get("metric_depth") is False, "RGB stream gained depth")

    matrix = contract.get("observability_matrix")
    _require(isinstance(matrix, dict) and matrix, "observability matrix is missing")
    for channel, row in matrix.items():
        _require(isinstance(row, dict), f"invalid observability row: {channel}")
        _require(
            row.get("status") in ALLOWED_OBSERVABILITY,
            f"invalid observability status: {channel}",
        )
        source_ids = row.get("source_ids")
        _require(
            isinstance(source_ids, list)
            and source_ids
            and all(source_id in lookup for source_id in source_ids),
            f"observability sources are invalid: {channel}",
        )

    boundaries = contract.get("proof_boundaries")
    authority = contract.get("authority")
    _require(
        isinstance(boundaries, dict) and boundaries and not any(boundaries.values()),
        "proof boundary widened",
    )
    _require(
        isinstance(authority, dict) and authority and not any(authority.values()),
        "authority widened",
    )
    return contract


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as error:
        raise FactoryArtifactError(f"cannot read JSONL source {path}: {error}") from error
    _require(rows and all(isinstance(row, dict) for row in rows), f"JSONL source is empty: {path}")
    return rows


def _tensor_hash(rows: list[dict[str, Any]], field: str, dtype: str) -> str:
    _require(
        all(isinstance(row.get(field), list) and len(row[field]) == 6 for row in rows),
        f"{field} is not present on every row",
    )
    values = np.asarray([row[field] for row in rows], dtype=np.dtype(dtype))
    _require(values.shape == (len(rows), 6), f"{field} tensor shape changed")
    _require(np.isfinite(values).all(), f"{field} contains non-finite values")
    return hashlib.sha256(values.tobytes(order="C")).hexdigest()


def _timestamp_hash(rows: list[dict[str, Any]]) -> tuple[str, np.ndarray]:
    values = np.asarray(
        [row.get("timestamp_monotonic_seconds") for row in rows], dtype="<f8"
    )
    _require(
        values.shape == (len(rows),) and np.isfinite(values).all(),
        "source timestamps are invalid",
    )
    _require(bool(np.all(np.diff(values) > 0.0)), "source timestamps are not monotonic")
    return hashlib.sha256(values.tobytes(order="C")).hexdigest(), values


def _stream_summary(
    stream_id: str,
    stream_contract: dict[str, Any],
    *,
    root: Path,
    sources: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    metadata_source = sources[str(stream_contract["metadata_source_id"])]
    video_source = sources[str(stream_contract["video_source_id"])]
    metadata = load_json_object(
        root / str(metadata_source["path"]), label=f"{stream_id} metadata"
    )
    observed = metadata.get("browser_observed_video")
    _require(isinstance(observed, dict), f"{stream_id} browser metadata is missing")
    observed_streams = observed.get("streams")
    _require(
        isinstance(observed_streams, list) and len(observed_streams) == 1,
        f"{stream_id} browser stream count changed",
    )
    observed_stream = observed_streams[0]
    expected = stream_contract
    _require(
        metadata.get("camera_name") == expected["camera_name"],
        f"{stream_id} camera identity changed",
    )
    _require(
        int(observed_stream.get("width", -1)) == int(expected["width"])
        and int(observed_stream.get("height", -1)) == int(expected["height"]),
        f"{stream_id} dimensions changed",
    )
    _require(
        int(observed_stream.get("nb_frames", -1)) == int(expected["frame_count"])
        and int(metadata.get("browser_frame_count", -1))
        == int(expected["frame_count"]),
        f"{stream_id} frame count changed",
    )
    configured_fps = float(metadata.get("configured_fps", 0.0))
    _require(
        abs(configured_fps - float(expected["fps"])) <= 0.001,
        f"{stream_id} frame rate changed",
    )
    _require(
        int(metadata.get("orientation_rotation_degrees", -1))
        == int(expected["rotation_degrees"]),
        f"{stream_id} rotation changed",
    )
    _require(metadata.get("metric_depth") is False, f"{stream_id} depth claim changed")
    _require(
        metadata.get("status") == "completed",
        f"{stream_id} capture is not complete",
    )
    timing = observed.get("container_timing", {})
    return {
        "camera_name": metadata["camera_name"],
        "camera_unique_id": metadata.get("camera_unique_id"),
        "video": {
            "path": video_source["path"],
            "sha256": video_source["sha256"],
            "bytes": (root / str(video_source["path"])).stat().st_size,
            "width": int(expected["width"]),
            "height": int(expected["height"]),
            "fps": configured_fps,
            "frame_count": int(expected["frame_count"]),
            "rotation_degrees": int(expected["rotation_degrees"]),
        },
        "action_interval_seconds": [
            float(metadata["action_start_video_offset_seconds"]),
            float(metadata["action_stop_video_offset_seconds"]),
        ],
        "container_timing_status": timing.get("status"),
        "container_large_gap_count": timing.get("large_gap_count"),
        "apple_drop_callback_count": int(metadata.get("apple_drop_callback_count", 0)),
        "writer_backpressure_count": int(metadata.get("writer_backpressure_count", 0)),
        "metric_depth": False,
        "cross_camera_exposure_synchronized": False,
    }


def compile_inventory(
    contract: dict[str, Any], *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    sources = _validate_bound_sources(contract, root=root)
    by_id = {source_id: source for source_id, source in sources.items()}
    receipt = load_json_object(
        root / str(by_id["sealed_recording_receipt"]["path"]),
        label="sealed recording receipt",
    )
    rows = _load_jsonl(root / str(by_id["sealed_samples"]["path"]))
    recording_id = str(contract["recording_id"])
    expected_action = contract["sealed_action_identity"]
    expected_rows = int(expected_action["expected_row_count"])
    _require(receipt.get("recording_id") == recording_id, "recording receipt identity changed")
    _require(int(receipt.get("sample_count", -1)) == expected_rows, "receipt row count changed")
    _require(len(rows) == expected_rows, "sealed sample row count changed")
    _require(
        [row.get("sample_index") for row in rows] == list(range(expected_rows)),
        "sealed sample indices changed",
    )
    _require(
        all(row.get("recording_id") == recording_id for row in rows),
        "sealed sample recording identity changed",
    )

    requested_hash = _tensor_hash(rows, "follower_requested_degrees", "<f4")
    sent_hash = _tensor_hash(rows, "follower_command_degrees", "<f4")
    measured_hash = _tensor_hash(rows, "follower_actual_position_degrees", "<f8")
    timestamps_hash, timestamps = _timestamp_hash(rows)
    checks = {
        "requested_float32": requested_hash
        == expected_action["requested_float32_sha256"],
        "gateway_sent_float32": sent_hash
        == expected_action["gateway_sent_float32_sha256"],
        "measured_float64": measured_hash
        == expected_action["measured_float64_sha256"],
        "timestamps_float64": timestamps_hash
        == expected_action["timestamps_float64_sha256"],
        "requested_sent_mismatch_rows": sum(
            row["follower_requested_degrees"] != row["follower_command_degrees"]
            for row in rows
        )
        == int(expected_action["requested_sent_mismatch_rows"]),
        "rate_limited_rows": sum(row.get("rate_limited") is True for row in rows)
        == int(expected_action["rate_limited_rows"]),
        "actuator_application_timestamp_rows": sum(
            isinstance(row.get("observability_timestamps"), dict)
            and row["observability_timestamps"].get(
                "actuator_application_or_ack_timestamp_available"
            )
            is True
            for row in rows
        )
        == int(expected_action["actuator_application_timestamp_rows"]),
    }
    _require(all(checks.values()), "sealed action identity changed")

    streams = {
        stream_id: _stream_summary(
            stream_id,
            stream_contract,
            root=root,
            sources=sources,
        )
        for stream_id, stream_contract in contract["camera_streams"].items()
    }
    role_counts = Counter(str(source["role"]) for source in sources.values())
    source_rows = [
        {
            "id": source_id,
            "role": source["role"],
            "path": source["path"],
            "sha256": source["sha256"],
            "bytes": (root / str(source["path"])).stat().st_size,
        }
        for source_id, source in sorted(sources.items())
    ]
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": (
            sha256_file(CONTRACT_PATH)
            if root == REPO_ROOT and CONTRACT_PATH.is_file()
            else canonical_digest(contract)
        ),
        "recording_id": recording_id,
        "sources": source_rows,
        "role_counts": dict(sorted(role_counts.items())),
        "sealed_episode": {
            "sample_count": expected_rows,
            "sample_hz": receipt.get("sample_hz"),
            "duration_seconds": float(timestamps[-1] - timestamps[0]),
            "requested_float32_sha256": requested_hash,
            "gateway_sent_float32_sha256": sent_hash,
            "measured_float64_sha256": measured_hash,
            "timestamps_float64_sha256": timestamps_hash,
            "identity_checks": checks,
        },
        "camera_streams": streams,
        "observability_matrix": contract["observability_matrix"],
        "observability_counts": dict(
            sorted(
                Counter(
                    str(row["status"])
                    for row in contract["observability_matrix"].values()
                ).items()
            )
        ),
        "proof_boundaries": contract["proof_boundaries"],
        "authority": contract["authority"],
        "result": "PASS",
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def build_inventory_receipt(
    contract_path: Path = CONTRACT_PATH,
    output_path: Path = OUTPUT_PATH,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_inventory_contract(contract_path, root=root)
    receipt = compile_inventory(contract, root=root)
    atomic_write_json(output_path, receipt)
    return receipt


__all__ = [
    "CONTRACT_PATH",
    "OUTPUT_PATH",
    "build_inventory_receipt",
    "compile_inventory",
    "load_inventory_contract",
]

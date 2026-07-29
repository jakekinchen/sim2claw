from __future__ import annotations

import json
from pathlib import Path

from sim2claw.learning_factory_artifacts import canonical_digest
from sim2claw.realized_action_corpus import (
    compile_corpus,
    load_corpus_contract,
)


def _write_episode(
    root: Path,
    *,
    folder: str,
    recording_id: str,
    label: str,
) -> None:
    directory = root / "datasets/manipulation_source_recordings" / folder
    directory.mkdir(parents=True)
    rows = []
    for index in range(2):
        values = [float(index + joint) for joint in range(6)]
        rows.append(
            {
                "recording_id": recording_id,
                "sample_index": index,
                "timestamp_monotonic_seconds": 0.05 * (index + 1),
                "follower_requested_degrees": values,
                "follower_command_degrees": values,
                "follower_actual_position_degrees": values,
                "rate_limited": False,
                "safety_clamped": False,
                "precompiled_exact_action": False,
            }
        )
    receipt = {
        "recording_id": recording_id,
        "sample_count": len(rows),
        "sample_hz": 20,
        "label": label,
        "source_square": label.split("-")[0],
        "destination_square": label.split("-")[-1],
        "mode": "physical_follower",
        "outcome_label": "success",
        "proof_class": "fixture",
    }
    (directory / "recording_receipt.json").write_text(
        json.dumps(receipt) + "\n", encoding="utf-8"
    )
    (directory / "samples.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )


def test_live_contract_has_disjoint_closed_authority() -> None:
    contract = load_corpus_contract()
    cohorts = [set(values) for values in contract["cohorts"].values()]
    assert all(
        not cohorts[left] & cohorts[right]
        for left in range(len(cohorts))
        for right in range(left + 1, len(cohorts))
    )
    assert contract["cohorts"]["sealed"] == ["20260727T041737Z-89190e53"]
    assert not any(contract["authority"].values())
    assert not any(contract["proof_boundaries"].values())


def test_compiler_is_deterministic_and_preserves_coordinate_ceiling(
    tmp_path: Path,
) -> None:
    recording_ids = ["fit-id", "validation-id", "sealed-id"]
    for recording_id in recording_ids:
        _write_episode(
            tmp_path,
            folder=f"{recording_id}__folder",
            recording_id=recording_id,
            label="a1-a2",
        )
    catalog = {
        "episodes": [
            {
                "recording_id": recording_id,
                "metadata_status": "consistent_folder_label_and_receipt",
            }
            for recording_id in recording_ids[:2]
        ],
        "discarded_recordings": [],
    }
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(catalog) + "\n", encoding="utf-8")
    correction_path = tmp_path / "correction.json"
    closeout_path = tmp_path / "closeout.json"
    correction_path.write_text("{}\n", encoding="utf-8")
    closeout_path.write_text("{}\n", encoding="utf-8")
    import hashlib

    contract = {
        "schema_version": "sim2claw.realized_action_retrospective_corpus.v1",
        "contract_id": "fixture",
        "frozen_date": "2026-07-29",
        "episode_root": "datasets/manipulation_source_recordings",
        "expected_discovered_episode_count": 3,
        "catalog": {
            "path": "catalog.json",
            "sha256": hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
            "expected_episode_count": 2,
        },
        "canonical_correction": {
            "recording_id": "sealed-id",
            "source_square": "d1",
            "destination_square": "d2",
            "binding_path": "correction.json",
            "binding_sha256": hashlib.sha256(
                correction_path.read_bytes()
            ).hexdigest(),
            "closeout_path": "closeout.json",
            "closeout_sha256": hashlib.sha256(
                closeout_path.read_bytes()
            ).hexdigest(),
        },
        "cohorts": {
            "fit": ["fit-id"],
            "validation": ["validation-id"],
            "sealed": ["sealed-id"],
        },
        "diagnostic_roles": {},
        "asset_paths": ["recording_receipt.json", "samples.jsonl"],
        "proof_boundaries": {"widened": False},
        "authority": {"hardware": False},
    }
    first = compile_corpus(contract, root=tmp_path)
    second = compile_corpus(contract, root=tmp_path)
    assert first == second
    assert first["artifact_sha256"] == canonical_digest(
        {key: value for key, value in first.items() if key != "artifact_sha256"}
    )
    by_id = {row["recording_id"]: row for row in first["episodes"]}
    assert by_id["fit-id"]["coordinate_contract"]["status"] == (
        "legacy_self_consistent_label_unmigrated_noncanonical"
    )
    assert by_id["sealed-id"]["coordinate_contract"]["status"] == (
        "evaluator_corrected_current_canonical"
    )
    assert by_id["sealed-id"]["coordinate_contract"]["canonical_source_square"] == "d1"

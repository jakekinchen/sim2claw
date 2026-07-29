from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sim2claw.learning_factory_artifacts import (
    FactoryArtifactError,
    canonical_digest,
)
from sim2claw.observable_registration_corpus import (
    compile_inventory,
    load_inventory_contract,
)
from sim2claw.paths import REPO_ROOT


def test_live_contract_is_closed_and_role_separated() -> None:
    contract = load_inventory_contract()
    assert not any(contract["authority"].values())
    assert not any(contract["proof_boundaries"].values())
    sources = contract["sources"]
    assert len({row["id"] for row in sources}) == len(sources)
    assert len({row["path"] for row in sources}) == len(sources)
    assert {row["role"] for row in sources} == {
        "fit",
        "validation_reuse_outcome_known",
        "retrospective_diagnostic",
        "sealed_source",
        "sealed_outcome",
    }
    assert contract["observability_matrix"]["pawn_carry_path"]["status"] == (
        "recoverable"
    )
    assert contract["observability_matrix"]["physical_contact_state"]["status"] == (
        "unavailable"
    )


def test_live_inventory_is_deterministic_and_binds_exact_episode() -> None:
    contract = load_inventory_contract()
    first = compile_inventory(contract)
    second = compile_inventory(contract)
    assert first == second
    assert first["artifact_sha256"] == canonical_digest(
        {key: value for key, value in first.items() if key != "artifact_sha256"}
    )
    assert first["result"] == "PASS"
    assert first["sealed_episode"]["sample_count"] == 531
    assert all(first["sealed_episode"]["identity_checks"].values())
    assert first["camera_streams"]["c922"]["video"]["frame_count"] == 1029
    assert first["camera_streams"]["d405_rgb"]["video"]["frame_count"] == 171
    assert first["camera_streams"]["c922"]["metric_depth"] is False
    assert first["camera_streams"]["d405_rgb"]["metric_depth"] is False


def test_contract_rejects_hash_drift_and_role_overlap(tmp_path: Path) -> None:
    contract = load_inventory_contract()
    drifted = copy.deepcopy(contract)
    drifted["sources"][0]["sha256"] = "0" * 64
    drifted_path = tmp_path / "drifted.json"
    drifted_path.write_text(json.dumps(drifted), encoding="utf-8")
    with pytest.raises(FactoryArtifactError, match="hash drifted"):
        load_inventory_contract(drifted_path, root=REPO_ROOT)

    overlapped = copy.deepcopy(contract)
    duplicate = copy.deepcopy(overlapped["sources"][0])
    duplicate["id"] = "duplicate-role-source"
    duplicate["role"] = "fit"
    overlapped["sources"].append(duplicate)
    overlapped_path = tmp_path / "overlapped.json"
    overlapped_path.write_text(json.dumps(overlapped), encoding="utf-8")
    with pytest.raises(FactoryArtifactError, match="paths overlap roles"):
        load_inventory_contract(overlapped_path, root=REPO_ROOT)


def test_compile_rejects_action_identity_drift() -> None:
    contract = load_inventory_contract()
    drifted = copy.deepcopy(contract)
    drifted["sealed_action_identity"]["requested_float32_sha256"] = "f" * 64
    with pytest.raises(FactoryArtifactError, match="sealed action identity changed"):
        compile_inventory(drifted)

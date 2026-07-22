"""Hash-bound receipts for deterministic SAIL evidence compilation."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..learning_factory_artifacts import canonical_digest, sha256_file
from .contracts import REPO_ROOT, SailContractError


RECEIPT_SCHEMA = "sim2claw.sail_evidence_compile_receipt.v1"


def build_compile_receipt(
    *,
    campaign_path: Path,
    campaign: Mapping[str, Any],
    catalog_path: Path,
    omissions_path: Path,
    evidence_files: Sequence[Mapping[str, Any]],
    counts: Mapping[str, Any],
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    code_paths = (
        "src/sim2claw/sail/evidence.py",
        "src/sim2claw/sail/importers.py",
        "src/sim2claw/sail/receipts.py",
        "src/sim2claw/sail/contracts.py",
    )
    code_bindings = {
        path: sha256_file(REPO_ROOT / path)
        for path in code_paths
    }
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "campaign_id": str(campaign["campaign_id"]),
        "generated_at": str(campaign["determinism"]["generated_at"]),
        "proof_class": "deterministic_retained_evidence_compilation",
        "campaign": {
            "path": campaign_path.resolve().relative_to(repo_root.resolve()).as_posix(),
            "sha256": sha256_file(campaign_path),
        },
        "compiler": {
            "code_sha256": code_bindings,
            "json_encoding": str(campaign["determinism"]["json_encoding"]),
            "catalog_sort": str(campaign["determinism"]["catalog_sort"]),
            "array_hash": str(campaign["determinism"]["array_hash"]),
        },
        "outputs": {
            "catalog": {"path": "catalog.json", "sha256": sha256_file(catalog_path)},
            "omissions": {"path": "omissions.json", "sha256": sha256_file(omissions_path)},
            "evidence": [copy.deepcopy(dict(row)) for row in evidence_files],
        },
        "counts": copy.deepcopy(dict(counts)),
        "regeneration_commands": [
            "uv run sim2claw sail-inventory --campaign configs/sail/campaign_retired_bg_v1.json",
            "uv run sim2claw sail-compile-evidence --campaign configs/sail/campaign_retired_bg_v1.json --output outputs/sail/retired-bg-v1/evidence",
        ],
        "authority": {
            "physical_capture": False,
            "robot_motion": False,
            "training_admission": False,
            "policy_selection": False,
            "simulator_promotion": False,
            "physical_transfer": False,
        },
        "claim_boundary": "This receipt verifies deterministic compilation of retained, proof-separated evidence. It does not create new physical evidence, identify omitted channels, promote a simulator, admit training, improve a policy, or establish transfer.",
    }
    return {**unsigned, "receipt_digest": canonical_digest(unsigned)}


def verify_compile_receipt(receipt: Mapping[str, Any], *, output_root: Path) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(receipt))
    if normalized.get("schema_version") != RECEIPT_SCHEMA:
        raise SailContractError("unexpected SAIL evidence receipt schema")
    observed = normalized.pop("receipt_digest", None)
    expected = canonical_digest(normalized)
    if observed != expected:
        raise SailContractError("SAIL evidence receipt digest mismatch")
    authority = normalized.get("authority")
    if not isinstance(authority, dict) or any(authority.values()):
        raise SailContractError("SAIL evidence receipt widened authority")
    outputs = normalized.get("outputs") or {}
    for group in ("catalog", "omissions"):
        binding = outputs.get(group) or {}
        path = output_root / str(binding.get("path", ""))
        if not path.is_file() or sha256_file(path) != binding.get("sha256"):
            raise SailContractError(f"SAIL evidence receipt output changed: {group}")
    for binding in outputs.get("evidence") or []:
        path = output_root / str(binding.get("path", ""))
        if not path.is_file() or sha256_file(path) != binding.get("sha256"):
            raise SailContractError("SAIL evidence receipt item changed")
    return {**normalized, "receipt_digest": str(observed)}

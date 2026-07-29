"""Wiring-only V2 for the elbow-locked static successor."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, Mapping

from . import canonical_elbow_locked_wrist_path_static as _v1
from .paths import REPO_ROOT


class CanonicalElbowLockedStaticV2Error(RuntimeError):
    """The wiring-only V2 contract changed or failed closed."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(binding: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(binding["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise CanonicalElbowLockedStaticV2Error(
            "elbow-locked V2 input escapes repository"
        ) from error
    if not path.is_file() or _sha(path) != binding["sha256"]:
        raise CanonicalElbowLockedStaticV2Error(
            f"bound elbow-locked V2 input changed: {path}"
        )
    return path


def _temporary_json(
    *,
    directory: Path,
    prefix: str,
    payload: Mapping[str, Any],
) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix=prefix,
        dir=directory,
        delete=False,
        encoding="utf-8",
    ) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        return Path(handle.name)


def enumerate_and_freeze(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Apply only the missing inherited binding, then run immutable V1."""

    if output_directory.exists():
        raise CanonicalElbowLockedStaticV2Error(
            "immutable elbow-locked V2 output already exists"
        )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    expected = {
        "schema_version",
        "contract_id",
        "status",
        "proof_class",
        "predecessor_contract",
        "base_contract",
        "mapping_closeout",
        "fresh_wrist_heldout_receipt",
        "elbow_stall_closeout",
        "predecessor_runner_closeout",
        "implementation",
        "live_seed",
        "unchanged_from_base",
        "output_directory",
        "authority",
        "claim_boundary",
    }
    if (
        set(contract) != expected
        or contract.get("schema_version")
        != "sim2claw.canonical_elbow_locked_wrist_path_static.v2"
        or contract.get("status")
        != "frozen_after_v1_pre_model_failure_before_static_enumeration"
        or not all(contract["unchanged_from_base"].values())
        or contract["authority"]
        != {
            "model_loading": True,
            "static_simulation": True,
            "dynamic_simulation": False,
            "mapping_approval": False,
            "camera": False,
            "gateway": False,
            "serial": False,
            "physical_motion": False,
            "physical_task_attempt": False,
            "simulator_promotion": False,
            "transfer_claim": False,
        }
    ):
        raise CanonicalElbowLockedStaticV2Error(
            "elbow-locked wiring-only V2 widened its contract"
        )
    for key in (
        "predecessor_contract",
        "base_contract",
        "mapping_closeout",
        "fresh_wrist_heldout_receipt",
        "elbow_stall_closeout",
        "predecessor_runner_closeout",
        "implementation",
    ):
        _bound(contract[key])
    predecessor_path = _bound(contract["predecessor_contract"])
    predecessor = json.loads(
        predecessor_path.read_text(encoding="utf-8")
    )
    base_v4_path = _bound(contract["base_contract"])
    base_v4 = json.loads(base_v4_path.read_text(encoding="utf-8"))
    base_v1_path = _bound(base_v4["base_contract"])
    base_v1 = json.loads(base_v1_path.read_text(encoding="utf-8"))
    base_v1["inputs"]["implementation"] = base_v4["implementation"]
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporaries: list[Path] = []
    try:
        corrected_v1_path = _temporary_json(
            directory=output_directory.parent,
            prefix="elbow-locked-base-v1-",
            payload=base_v1,
        )
        temporaries.append(corrected_v1_path)
        base_v4["base_contract"] = {
            "path": str(corrected_v1_path.relative_to(REPO_ROOT)),
            "sha256": _sha(corrected_v1_path),
        }
        corrected_v4_path = _temporary_json(
            directory=output_directory.parent,
            prefix="elbow-locked-base-v4-",
            payload=base_v4,
        )
        temporaries.append(corrected_v4_path)
        resolved_v1 = dict(predecessor)
        resolved_v1["base_contract"] = {
            "path": str(corrected_v4_path.relative_to(REPO_ROOT)),
            "sha256": _sha(corrected_v4_path),
        }
        resolved_v1["output_directory"] = contract["output_directory"]
        resolved_v1["claim_boundary"] = contract["claim_boundary"]
        resolved_v1_path = _temporary_json(
            directory=output_directory.parent,
            prefix="elbow-locked-contract-v1-",
            payload=resolved_v1,
        )
        temporaries.append(resolved_v1_path)
        receipt = _v1.enumerate_and_freeze(
            resolved_v1_path.resolve(), output_directory.resolve()
        )
    finally:
        for path in reversed(temporaries):
            path.unlink(missing_ok=True)
    receipt.update(
        {
            "schema_version": (
                "sim2claw.canonical_elbow_locked_wrist_path_static_receipt.v2"
            ),
            "contract_path": str(contract_path.relative_to(REPO_ROOT)),
            "contract_sha256": _sha(contract_path),
            "wiring_only_v2": {
                "resolved_base_v1_implementation_rebound_from_v4": True,
                "live_seed_changed_from_v1": False,
                "elbow_lock_changed_from_v1": False,
                "grid_or_gate_changed_from_v1": False,
            },
            "authority": contract["authority"],
            "claim_boundary": contract["claim_boundary"],
        }
    )
    (output_directory / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = [
    "CanonicalElbowLockedStaticV2Error",
    "enumerate_and_freeze",
]

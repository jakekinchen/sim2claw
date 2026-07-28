"""V05-TK v2 hash-only binding correction over the frozen v1 grid."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from . import bidirectional_pawn_push_v2_action_geometry_static as _v1
from .paths import REPO_ROOT


ActionGeometryStaticError = _v1.ActionGeometryStaticError


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(path: Path) -> Path:
    resolved = path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise ActionGeometryStaticError(
            "V05-TK v2 path escapes repository"
        ) from error
    return resolved


def _verify(entry: Mapping[str, Any]) -> Path:
    path = _resolve(Path(str(entry["path"])))
    if not path.is_file() or _sha(path) != entry["sha256"]:
        raise ActionGeometryStaticError(f"bound V05-TK v2 input changed: {path}")
    return path


def _json_binding(
    entry: Mapping[str, Any],
) -> tuple[Path, dict[str, Any]]:
    path = _verify(entry)
    return path, json.loads(path.read_text(encoding="utf-8"))


def _hash_only_aware_binding(
    entry: Mapping[str, Any],
) -> tuple[Path, dict[str, Any]]:
    path = _verify(entry)
    if path.suffix != ".json":
        return path, {}
    return path, json.loads(path.read_text(encoding="utf-8"))


def enumerate_and_freeze(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    public_contract = _resolve(contract_path)
    public_output = _resolve(output_directory)
    public_spec = json.loads(public_contract.read_text(encoding="utf-8"))
    if (
        public_spec.get("schema_version")
        != "sim2claw.bidirectional_pawn_push_v2_action_geometry_static.v2"
    ):
        raise ActionGeometryStaticError("unexpected V05-TK v2 contract")
    if public_spec.get("only_change") != {
        "separate_hash_only_file_binding_from_json_binding": True,
        "quarantine_family_grid_parameters_selection_gates_unchanged": True,
        "dynamic_or_physical_authority_changed": False,
    }:
        raise ActionGeometryStaticError("V05-TK v2 correction scope changed")

    v1_contract_path, _ = _json_binding(public_spec["frozen_v1_contract"])
    _json_binding(public_spec["v1_binding_failure"])
    _verify(public_spec["v1_implementation"])
    _verify(public_spec["implementation"])

    previous = _v1._bound
    _v1._bound = _hash_only_aware_binding
    try:
        receipt = _v1.enumerate_and_freeze(
            v1_contract_path,
            public_output,
        )
    finally:
        _v1._bound = previous

    receipt.update(
        {
            "schema_version": (
                "sim2claw."
                "bidirectional_pawn_push_v2_action_geometry_static_receipt.v2"
            ),
            "proof_class": (
                "cpu_fp64_static_action_geometry_ik_collision_camera_"
                "gateway_action_freeze_only_v2"
            ),
            "contract_path": str(public_contract.relative_to(REPO_ROOT)),
            "contract_sha256": _sha(public_contract),
            "frozen_v1_contract_sha256": public_spec[
                "frozen_v1_contract"
            ]["sha256"],
            "v1_binding_failure_sha256": public_spec[
                "v1_binding_failure"
            ]["sha256"],
            "binding_loader_correction_only": True,
        }
    )
    receipt_path = public_output / "receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = ["ActionGeometryStaticError", "enumerate_and_freeze"]

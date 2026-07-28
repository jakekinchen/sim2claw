"""V05-TY frozen override of the V05-TX multistart static enumerator."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from . import bidirectional_pawn_push_v2_multistart_approach_static as _base
from .paths import REPO_ROOT


SlowElevatedStaticError = _base.MultistartApproachStaticError


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(path: Path) -> Path:
    resolved = path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise SlowElevatedStaticError(
            "V05-TY path escapes repository"
        ) from error
    return resolved


def _verify(entry: Mapping[str, Any]) -> Path:
    path = _resolve(Path(str(entry["path"])))
    if not path.is_file() or _sha(path) != entry["sha256"]:
        raise SlowElevatedStaticError(f"bound V05-TY input changed: {path}")
    return path


def enumerate_and_freeze(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    public_contract = _resolve(contract_path)
    public_output = _resolve(output_directory)
    contract = json.loads(public_contract.read_text(encoding="utf-8"))
    if (
        contract.get("schema_version")
        != "sim2claw.bidirectional_pawn_push_v2_slow_elevated_static.v1"
    ):
        raise SlowElevatedStaticError("unexpected V05-TY static contract")
    authorization_path = _verify(contract["authorization"])
    previous_contract_path = _verify(contract["base_static_contract"])
    _verify(contract["previous_temporal_receipt"])
    _verify(contract["base_implementation"])
    _verify(contract["implementation"])

    authorization = json.loads(authorization_path.read_text(encoding="utf-8"))
    base = json.loads(previous_contract_path.read_text(encoding="utf-8"))
    overrides = contract["frozen_overrides"]
    if authorization["quarantine"]["case_ids"] != overrides["quarantine_case_ids"]:
        raise SlowElevatedStaticError("V05-TY quarantine binding changed")
    if int(overrides["maximum_total_cells"]) != 360:
        raise SlowElevatedStaticError("V05-TY cell budget changed")

    derived = copy.deepcopy(base)
    derived.update(
        {
            "enumeration_id": (
                "bidirectional-pawn-push-v2-slow-elevated-static-derived-v1"
            ),
            "status": (
                "prospectively_derived_from_frozen_v05_tx_before_model_loading"
            ),
            "authorization": contract["authorization"],
            "quarantine": {
                **derived["quarantine"],
                "case_ids": list(overrides["quarantine_case_ids"]),
                "exact_count": len(overrides["quarantine_case_ids"]),
            },
        }
    )
    derived["family_grid"]["expected_postquarantine_family_count"] = 40
    derived["parameter_grid"]["approach_lateral_offsets_m"] = list(
        overrides["approach_lateral_offsets_m"]
    )
    derived["parameter_grid"].update(
        {
            "cells_per_family": 9,
            "maximum_total_cells": 360,
            "finite_and_nonexpandable_after_freeze": True,
        }
    )
    derived["endpoint_geometry"] = copy.deepcopy(
        overrides["endpoint_geometry"]
    )
    derived["geometry_derivation"] = copy.deepcopy(
        overrides["geometry_derivation"]
    )
    derived["action_identity"]["setup_joint_speed_physical_units_s"] = float(
        overrides["setup_joint_speed_physical_units_s"]
    )
    # The base enumerator verifies and executes this already-frozen
    # implementation. This wrapper changes only the prospectively bound data.
    derived["implementation"] = contract["base_implementation"]

    public_output.mkdir(parents=True, exist_ok=True)
    derived_path = public_output / "derived_contract.json"
    derived_path.write_text(
        json.dumps(derived, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    receipt = _base.enumerate_and_freeze(derived_path, public_output)
    receipt.update(
        {
            "schema_version": (
                "sim2claw."
                "bidirectional_pawn_push_v2_slow_elevated_static_receipt.v1"
            ),
            "proof_class": (
                "cpu_fp64_static_slow_elevated_long_stroke_multistart_"
                "approach_collision_camera_gateway_action_freeze_only"
            ),
            "contract_path": str(public_contract.relative_to(REPO_ROOT)),
            "contract_sha256": _sha(public_contract),
            "derived_contract_path": str(derived_path.relative_to(REPO_ROOT)),
            "derived_contract_sha256": _sha(derived_path),
            "base_static_contract_sha256": contract["base_static_contract"][
                "sha256"
            ],
            "previous_temporal_receipt_sha256": contract[
                "previous_temporal_receipt"
            ]["sha256"],
            "frozen_override_only": True,
        }
    )
    (public_output / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = ["SlowElevatedStaticError", "enumerate_and_freeze"]

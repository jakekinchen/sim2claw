"""V05-UD seeded-orientation open-loop guiding-contact static wrapper."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from . import bidirectional_pawn_push_v2_multistart_approach_static as _multi
from . import bidirectional_pawn_push_v2_orientation_funnel_static_v1 as _base
from .paths import REPO_ROOT


SeededFunnelStaticV1Error = _base.OrientationFunnelStaticV1Error


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(path: Path) -> Path:
    resolved = path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise SeededFunnelStaticV1Error(
            "V05-UD path escapes repository"
        ) from error
    return resolved


def _verify(entry: Mapping[str, Any]) -> Path:
    path = _resolve(Path(str(entry["path"])))
    if not path.is_file() or _sha(path) != entry["sha256"]:
        raise SeededFunnelStaticV1Error(
            f"bound V05-UD input changed: {path}"
        )
    return path


def _seeded_compile(
    *,
    wrist_roll_rad: float,
    branch_model: np.ndarray,
    **kwargs: Any,
) -> tuple[np.ndarray, dict[str, Any]]:
    seeded_branch = np.asarray(branch_model, dtype=np.float64).copy()
    seeded_branch[4] = wrist_roll_rad
    action, metrics = _multi._compile_action(
        branch_model=seeded_branch,
        **kwargs,
    )
    seed_error = abs(
        float(metrics["branch_model_rad"][4]) - float(wrist_roll_rad)
    )
    metrics.update(
        {
            "wrist_roll_target_rad": float(wrist_roll_rad),
            "wrist_roll_seed_target_rad": float(wrist_roll_rad),
            "wrist_constraint_scope": (
                "exact demonstrated setup-branch seed only; "
                "deterministic IK evolves after seed"
            ),
            "maximum_wrist_roll_target_error_rad": seed_error,
        }
    )
    return action, metrics


def enumerate_and_freeze(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    public_contract = _resolve(contract_path)
    public_output = _resolve(output_directory)
    contract = json.loads(public_contract.read_text(encoding="utf-8"))
    if (
        contract.get("schema_version")
        != "sim2claw.bidirectional_pawn_push_v2_seeded_funnel_static.v1"
    ):
        raise SeededFunnelStaticV1Error(
            "unexpected V05-UD static contract"
        )

    authorization_path = _verify(contract["authorization"])
    base_contract_path = _verify(contract["base_static_contract"])
    _verify(contract["v05_uc_static_receipt"])
    _verify(contract["base_implementation"])
    _verify(contract["multistart_implementation"])
    _verify(contract["implementation"])
    authorization = json.loads(
        authorization_path.read_text(encoding="utf-8")
    )
    base = json.loads(base_contract_path.read_text(encoding="utf-8"))
    overrides = contract["frozen_overrides"]
    if (
        authorization["quarantine"]["case_ids"]
        != overrides["quarantine_case_ids"]
    ):
        raise SeededFunnelStaticV1Error(
            "V05-UD quarantine binding changed"
        )
    if int(overrides["maximum_total_cells"]) != 576:
        raise SeededFunnelStaticV1Error("V05-UD cell budget changed")

    derived = copy.deepcopy(base)
    derived.update(
        {
            "enumeration_id": (
                "bidirectional-pawn-push-v2-seeded-funnel-static-derived-v1"
            ),
            "status": (
                "prospectively_derived_from_frozen_v05_uc_before_model_loading"
            ),
            "authorization": contract["authorization"],
            "quarantine": {
                **derived["quarantine"],
                "case_ids": list(overrides["quarantine_case_ids"]),
                "exact_count": len(overrides["quarantine_case_ids"]),
            },
        }
    )
    derived["endpoint_geometry"] = copy.deepcopy(
        overrides["endpoint_geometry"]
    )
    derived["action_identity"]["path_shape"] = overrides["path_shape"]
    derived["parameter_grid"]["wrist_seed_rule"] = (
        overrides["wrist_seed_rule"]
    )
    derived["implementation"] = contract["base_implementation"]

    public_output.mkdir(parents=True, exist_ok=True)
    derived_path = public_output / "derived_contract.json"
    derived_path.write_text(
        json.dumps(derived, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    original_compile = _base._compile_action
    _base._compile_action = _seeded_compile
    try:
        receipt = _base.enumerate_and_freeze(derived_path, public_output)
    finally:
        _base._compile_action = original_compile
    receipt.update(
        {
            "schema_version": (
                "sim2claw."
                "bidirectional_pawn_push_v2_seeded_funnel_static_receipt.v1"
            ),
            "proof_class": (
                "cpu_fp64_static_seeded_orientation_open_loop_ik_"
                "guiding_contact_collision_camera_gateway_action_freeze_only"
            ),
            "contract_path": str(public_contract.relative_to(REPO_ROOT)),
            "contract_sha256": _sha(public_contract),
            "derived_contract_path": str(derived_path.relative_to(REPO_ROOT)),
            "derived_contract_sha256": _sha(derived_path),
            "base_static_contract_sha256": contract[
                "base_static_contract"
            ]["sha256"],
            "v05_uc_static_receipt_sha256": contract[
                "v05_uc_static_receipt"
            ]["sha256"],
            "wrist_constraint_scope": (
                "exact setup-branch seed only; deterministic open-loop IK "
                "evolves after seed"
            ),
            "frozen_override_only": True,
        }
    )
    receipt["claim_boundary"] = (
        "Static-only deterministic seeded-orientation guiding-contact search "
        "with setup included in exact action bytes. No dynamic task outcome, "
        "calibrated plant, physical packet, promotion, or transfer claim."
    )
    (public_output / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = ["SeededFunnelStaticV1Error", "enumerate_and_freeze"]

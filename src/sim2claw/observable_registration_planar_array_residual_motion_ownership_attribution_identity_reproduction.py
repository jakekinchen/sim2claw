"""Identity-bound reproduction wrapper for quarantined OR124 motion ownership."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import observable_registration_planar_array_residual_motion_ownership_attribution as _or124
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT


DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_planar_array_residual_motion_ownership_attribution_identity_reproduction_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_planar_array_residual_motion_ownership_attribution_identity_reproduction_v1"
_ORIGINAL_LOADER = _or124.load_motion_ownership_contract


def load_identity_reproduction_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = _ORIGINAL_LOADER(path)
    if contract["experiment_id"] != "OR124B_IDENTITY_BOUND_RESIDUAL_MOTION_OWNERSHIP_REPRODUCTION_V1":
        raise ValueError("OR124B experiment identity drifted")
    quarantine = contract["sources"]["or124_quarantined_receipt"]
    if quarantine["admitted"] is not False or quarantine["artifact_sha256"] != "32dc4a62dffaef52df2a01906498574dd425f644195c5a69d0b138e963c2be43":
        raise ValueError("OR124B quarantine boundary drifted")
    if contract["sources"]["or124_final_implementation"]["sha256"] != "ef274e8c85452778970266ce56a242c9e923c739e588c2fa39f5da978221f4db":
        raise ValueError("OR124B final logic identity drifted")
    if contract["claim_limits"].get("identity_bound_reproduction_only") is not True:
        raise ValueError("OR124B reproduction claim boundary drifted")
    return contract


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    """Run final OR124 logic once through OR124B's immutable contract loader."""

    load_identity_reproduction_contract(contract_path)
    original_loader = _or124.load_motion_ownership_contract
    try:
        _or124.load_motion_ownership_contract = load_identity_reproduction_contract
        return _or124.evaluate_once(contract_path, output_directory)
    finally:
        _or124.load_motion_ownership_contract = original_loader


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

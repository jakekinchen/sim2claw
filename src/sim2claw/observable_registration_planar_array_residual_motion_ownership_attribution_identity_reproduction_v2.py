"""Second identity-bound reproduction for quarantined OR124/OR124B ownership evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import observable_registration_planar_array_residual_motion_ownership_attribution as _or124
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT


DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_planar_array_residual_motion_ownership_attribution_identity_reproduction_v2.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_planar_array_residual_motion_ownership_attribution_identity_reproduction_v2"
_ORIGINAL_LOADER = _or124.load_motion_ownership_contract


def load_identity_reproduction_v2_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = _ORIGINAL_LOADER(path)
    if contract["experiment_id"] != "OR124C_IDENTITY_BOUND_RESIDUAL_MOTION_OWNERSHIP_REPRODUCTION_V2":
        raise ValueError("OR124C experiment identity drifted")
    prerequisite = contract["sources"]["or125_prerequisite_audit"]
    if prerequisite["status"] != "NOT_RUN_OR124B_PREREQUISITE_IDENTITY_DRIFT":
        raise ValueError("OR124C prerequisite quarantine drifted")
    if contract["sources"]["or124_final_implementation"]["sha256"] != "ef274e8c85452778970266ce56a242c9e923c739e588c2fa39f5da978221f4db":
        raise ValueError("OR124C final logic identity drifted")
    if contract["claim_limits"].get("identity_bound_reproduction_only") is not True:
        raise ValueError("OR124C reproduction claim boundary drifted")
    return contract


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    """Run the final OR124 logic once through OR124C's immutable contract loader."""

    load_identity_reproduction_v2_contract(contract_path)
    original_loader = _or124.load_motion_ownership_contract
    try:
        _or124.load_motion_ownership_contract = load_identity_reproduction_v2_contract
        return _or124.evaluate_once(contract_path, output_directory)
    finally:
        _or124.load_motion_ownership_contract = original_loader


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

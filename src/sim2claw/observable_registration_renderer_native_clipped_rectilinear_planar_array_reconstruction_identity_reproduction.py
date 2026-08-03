"""Identity-bound reproduction of the quarantined OR122 renderer experiment."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import observable_registration_renderer_native_clipped_rectilinear_planar_array_reconstruction as _or122
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, sha256_file


SCHEMA = "sim2claw.observable_registration_renderer_native_clipped_rectilinear_planar_array_reconstruction_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_renderer_native_clipped_rectilinear_planar_array_reconstruction_identity_reproduction_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_renderer_native_clipped_rectilinear_planar_array_reconstruction_identity_reproduction_v1"


def load_identity_reproduction_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR122B contract")
    for group in ("sources", "frozen_identities"):
        for binding in contract[group].values():
            source_path = binding.get("path")
            expected = binding.get("sha256")
            if source_path and expected and sha256_file(REPO_ROOT / source_path) != expected:
                raise ValueError(f"OR122B identity mismatch: {source_path}")
            if source_path and binding.get("hash_source") and not (REPO_ROOT / source_path).is_dir():
                raise ValueError(f"OR122B asset root missing: {source_path}")
    split = contract["split"]
    if split["development_positions"] != list(range(1, 8)):
        raise ValueError("OR122B development split drifted")
    if split["corroboration_positions"] != list(range(8, 12)):
        raise ValueError("OR122B corroboration split drifted")
    if split["corroboration_requires_development_gate"] is not True:
        raise ValueError("OR122B corroboration gate drifted")
    geometry = contract["geometry"]
    if geometry["segment_count"] != 5 or geometry["triangle_count_per_segment"] != 248:
        raise ValueError("OR122B geometry identity drifted")
    if geometry["shared_scene_zbuffer"] is not True or geometry["pixel_composite_allowed"] is not False:
        raise ValueError("OR122B renderer boundary drifted")
    resources = contract["resource_boundary"]
    zero_keys = (
        "geometry_searches_allowed",
        "material_searches_allowed",
        "corroboration_refits_allowed",
        "threshold_changes_allowed",
        "retries_allowed",
        "simulator_replays_allowed",
        "hardware_actions_allowed",
        "physical_pixel_composites_allowed",
    )
    if any(resources[key] != 0 for key in zero_keys):
        raise ValueError("OR122B resource boundary drifted")
    if resources["paid_compute_allowed"] is not False or any(contract["authority"].values()):
        raise ValueError("OR122B authority boundary drifted")
    claims = contract["claim_limits"]
    if any(
        claims[key] is not False
        for key in (
            "specific_object_identity",
            "metric_3d_geometry_calibrated",
            "predictive_simulation",
            "physics_fidelity",
            "physical_transfer",
            "simulator_promotion",
        )
    ):
        raise ValueError("OR122B claim boundary drifted")
    return contract


def evaluate_once(
    contract_path: Path = DEFAULT_CONTRACT,
    output_directory: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    """Run once while forcing the shared renderer through OR122B's bound loader."""

    load_identity_reproduction_contract(contract_path)
    original_loader = _or122.load_planar_array_reconstruction_contract
    try:
        _or122.load_planar_array_reconstruction_contract = load_identity_reproduction_contract
        return _or122.evaluate_once(contract_path, output_directory)
    finally:
        _or122.load_planar_array_reconstruction_contract = original_loader


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

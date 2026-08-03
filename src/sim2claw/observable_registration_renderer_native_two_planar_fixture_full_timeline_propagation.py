"""Propagate OR130's two frozen procedural fixtures through the OR119 timeline."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import numpy as np

from . import observable_registration_post_final_two_material_finite_object_full_timeline_propagation as _or119
from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, sha256_file
from .observable_registration_renderer_native_planar_fixture_static_comparison import _fixture_stream


SCHEMA = "sim2claw.observable_registration_renderer_native_two_planar_fixture_full_timeline_propagation_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_renderer_native_two_planar_fixture_full_timeline_propagation_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_renderer_native_two_planar_fixture_full_timeline_propagation_v1"
_ORIGINAL_LOADER = _or119.load_post_final_two_material_finite_object_full_timeline_propagation_contract
_ORIGINAL_PREPARE = _or119._prepare_full_mesh_stream


def load_two_planar_fixture_full_timeline_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR131 contract")
    for group in ("sources", "frozen_identities"):
        for binding in contract[group].values():
            source_path = binding.get("path")
            expected = binding.get("sha256")
            if source_path and expected and sha256_file(REPO_ROOT / source_path) != expected:
                raise ValueError(f"OR131 identity mismatch: {source_path}")
    fixture = contract["fixture"]
    if fixture["fixture_count"] != 2 or fixture["triangle_count_per_fixture"] != 128 or fixture["total_triangle_count"] != 256:
        raise ValueError("OR131 fixture geometry drifted")
    if fixture["shared_zbuffer"] is not True or fixture["physical_pixel_texture_projection"] is not False or fixture["screen_space_overlay"] is not False:
        raise ValueError("OR131 renderer-native boundary drifted")
    resources = contract["resource_boundary"]
    if resources["physical_frames_compared_allowed"] != 1210 or resources["candidate_frames_rendered_allowed"] != 1210 or resources["candidate_videos_allowed"] != 11:
        raise ValueError("OR131 corpus budget drifted")
    zero = (
        "physical_pixel_texture_projections_allowed",
        "screen_space_overlays_allowed",
        "fits_or_candidate_selections_allowed",
        "threshold_changes_allowed",
        "retries_allowed",
        "simulator_replays_allowed",
        "hardware_actions_allowed",
    )
    if any(resources[key] != 0 for key in zero) or resources["paid_compute_allowed"] is not False:
        raise ValueError("OR131 resource boundary drifted")
    if any(contract["authority"].values()):
        raise ValueError("OR131 authority must remain closed")
    return contract


def _merged_or119_contract(contract: dict[str, Any]) -> dict[str, Any]:
    base_path = REPO_ROOT / contract["sources"]["or119_contract"]["path"]
    merged = deepcopy(_ORIGINAL_LOADER(base_path))
    merged["experiment_id"] = contract["experiment_id"]
    merged["proof_class"] = contract["proof_class"]
    merged["gates"]["expected_total_raster_triangle_count_per_frame"] = int(
        contract["gates"]["expected_total_raster_triangle_count_per_frame"]
    )
    merged["resource_boundary"]["native_full_mesh_plus_object_frames_rendered_allowed"] = 1210
    merged["claim_limits"] = contract["claim_limits"]
    return merged


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR131 one-run receipt already exists")
    contract = load_two_planar_fixture_full_timeline_contract(contract_path)
    predecessor = json.loads((REPO_ROOT / contract["sources"]["or130_receipt"]["path"]).read_text())
    complete_parameters = json.loads((REPO_ROOT / contract["sources"]["or126_parameters"]["path"]).read_text())
    clipped_parameters = json.loads((REPO_ROOT / contract["sources"]["or129_parameters"]["path"]).read_text())
    if predecessor["artifact_sha256"] != contract["sources"]["or130_receipt"]["artifact_sha256"] or predecessor["status"] != "PASS_RENDERER_NATIVE_TWO_PLANAR_FIXTURE_STATIC_COMPARISON":
        raise ValueError("OR131 OR130 prerequisite drifted")
    if complete_parameters["artifact_sha256"] != contract["sources"]["or126_parameters"]["artifact_sha256"]:
        raise ValueError("OR131 complete fixture parameterization drifted")
    if clipped_parameters["artifact_sha256"] != contract["sources"]["or129_parameters"]["artifact_sha256"]:
        raise ValueError("OR131 clipped fixture parameterization drifted")
    merged = _merged_or119_contract(contract)
    or95 = json.loads((REPO_ROOT / merged["sources"]["or95_contract"]["path"]).read_text())
    camera = or95["frozen_candidate"]["camera"]
    response = or95["frozen_candidate"]["global_monotone_response"]
    complete_pixels, complete_depths, complete_colors = _fixture_stream(complete_parameters, camera, contract, response)
    clipped_pixels, clipped_depths, clipped_colors = _fixture_stream(clipped_parameters, camera, contract, response)
    fixture_pixels = np.ascontiguousarray(np.concatenate([complete_pixels, clipped_pixels]))
    fixture_depths = np.ascontiguousarray(np.concatenate([complete_depths, clipped_depths]))
    fixture_colors = np.ascontiguousarray(np.concatenate([complete_colors, clipped_colors]))

    def merged_loader(_path: Path) -> dict[str, Any]:
        return merged

    def prepare_with_fixtures(*args: Any, **kwargs: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
        pixels, depths, colors, count = _ORIGINAL_PREPARE(*args, **kwargs)
        return (
            np.ascontiguousarray(np.concatenate([pixels, fixture_pixels])),
            np.ascontiguousarray(np.concatenate([depths, fixture_depths])),
            np.ascontiguousarray(np.concatenate([colors, fixture_colors])),
            count + len(fixture_pixels),
        )

    original_loader = _or119.load_post_final_two_material_finite_object_full_timeline_propagation_contract
    original_prepare = _or119._prepare_full_mesh_stream
    try:
        _or119.load_post_final_two_material_finite_object_full_timeline_propagation_contract = merged_loader
        _or119._prepare_full_mesh_stream = prepare_with_fixtures
        receipt = _or119.evaluate_once(contract_path, output_directory)
    finally:
        _or119.load_post_final_two_material_finite_object_full_timeline_propagation_contract = original_loader
        _or119._prepare_full_mesh_stream = original_prepare

    base_artifact = receipt.pop("artifact_sha256")
    receipt["schema_version"] = "sim2claw.observable_registration_renderer_native_two_planar_fixture_full_timeline_propagation_receipt.v1"
    receipt["identities"] = {
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "implementation": contract["frozen_identities"]["implementation"],
        "test": contract["frozen_identities"]["test"],
    }
    receipt["fixtures"] = {
        "complete_parameterization": contract["sources"]["or126_parameters"],
        "clipped_parameterization": contract["sources"]["or129_parameters"],
        "complete_triangle_count": len(complete_pixels),
        "clipped_triangle_count": len(clipped_pixels),
        "total_triangle_count": len(fixture_pixels),
        "shared_zbuffer": True,
        "physical_pixel_texture_projection": False,
        "screen_space_overlay": False,
    }
    receipt["base_evaluator_artifact_sha256_before_identity_augmentation"] = base_artifact
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

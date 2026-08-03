"""Re-run the frozen OR120 residual factorization on OR131 videos."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from . import observable_registration_post_object_full_timeline_residual_reconciliation as _or120
from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, sha256_file


SCHEMA = "sim2claw.observable_registration_renderer_native_two_planar_fixture_residual_reconciliation_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_renderer_native_two_planar_fixture_residual_reconciliation_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_renderer_native_two_planar_fixture_residual_reconciliation_v1"
_ORIGINAL_LOADER = _or120.load_post_object_full_timeline_residual_reconciliation_contract


def load_two_planar_fixture_residual_reconciliation_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR132 contract")
    for group in ("sources", "frozen_identities"):
        for binding in contract[group].values():
            if sha256_file(REPO_ROOT / binding["path"]) != binding["sha256"]:
                raise ValueError(f"OR132 identity mismatch: {binding['path']}")
    resources = contract["resource_boundary"]
    if resources != {
        "existing_physical_video_decodes_allowed": 11,
        "existing_candidate_video_decodes_allowed": 11,
        "physical_frames_read_allowed": 1210,
        "candidate_frames_read_allowed": 1210,
        "occupancy_map_outputs_allowed": 11,
        "renders_allowed": 0,
        "fits_allowed": 0,
        "candidate_selections_allowed": 0,
        "threshold_changes_allowed": 0,
        "retries_allowed": 0,
        "simulator_replays_allowed": 0,
        "hardware_actions_allowed": 0,
        "paid_compute_allowed": False,
    }:
        raise ValueError("OR132 resource boundary drifted")
    if any(contract["authority"].values()):
        raise ValueError("OR132 authority must remain closed")
    return contract


def _merged_or120_contract(contract: dict[str, Any]) -> dict[str, Any]:
    base = deepcopy(_ORIGINAL_LOADER(REPO_ROOT / contract["sources"]["or120_contract"]["path"]))
    base["experiment_id"] = contract["experiment_id"]
    base["proof_class"] = contract["proof_class"]
    base["sources"]["or119_closeout"] = contract["sources"]["or131_closeout"]
    base["sources"]["or119_receipt"] = contract["sources"]["or131_receipt"]
    base["sources"]["or119_frame_rows"] = contract["sources"]["or131_frame_rows"]
    base["claim_limits"] = contract["claim_limits"]
    return base


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR132 one-run receipt already exists")
    contract = load_two_planar_fixture_residual_reconciliation_contract(contract_path)
    predecessor = json.loads((REPO_ROOT / contract["sources"]["or131_receipt"]["path"]).read_text())
    if predecessor["artifact_sha256"] != contract["sources"]["or131_receipt"]["artifact_sha256"]:
        raise ValueError("OR132 OR131 artifact drifted")
    merged = _merged_or120_contract(contract)

    def merged_loader(_path: Path) -> dict[str, Any]:
        return merged

    original_loader = _or120.load_post_object_full_timeline_residual_reconciliation_contract
    try:
        _or120.load_post_object_full_timeline_residual_reconciliation_contract = merged_loader
        receipt = _or120.evaluate_once(contract_path, output_directory)
    finally:
        _or120.load_post_object_full_timeline_residual_reconciliation_contract = original_loader

    base_artifact = receipt.pop("artifact_sha256")
    receipt["schema_version"] = "sim2claw.observable_registration_renderer_native_two_planar_fixture_residual_reconciliation_receipt.v1"
    receipt["identities"] = {
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "implementation": contract["frozen_identities"]["implementation"],
        "test": contract["frozen_identities"]["test"],
    }
    receipt["base_evaluator_artifact_sha256_before_identity_augmentation"] = base_artifact
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))

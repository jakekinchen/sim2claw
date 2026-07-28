"""Paused V05-UG low-contact planar unilateral open-jaw static draft.

The draft predates the canonical board-orientation contract and must not load
a model or enumerate until a fresh post-Fable authorization updates the public
contract.  Merely calling the entry point while paused fails closed.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from . import bidirectional_pawn_push_v2_unilateral_open_jaw_static_v1 as _open
from .paths import REPO_ROOT


LowPlanarOpenJawStaticV1Error = _open.UnilateralOpenJawStaticV1Error


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(path: Path) -> Path:
    resolved = (
        path.resolve()
        if path.is_absolute()
        else (REPO_ROOT / path).resolve()
    )
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise LowPlanarOpenJawStaticV1Error(
            "V05-UG path escapes repository"
        ) from error
    return resolved


def _verify(entry: Mapping[str, Any]) -> Path:
    path = _resolve(Path(str(entry["path"])))
    if not path.is_file() or _sha(path) != entry["sha256"]:
        raise LowPlanarOpenJawStaticV1Error(
            f"bound V05-UG input changed: {path}"
        )
    return path


def _write_json(path: Path, payload: Mapping[str, Any]) -> dict[str, str]:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "sha256": _sha(path),
    }


def enumerate_and_freeze(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Execute the one frozen 396-cell low planar static enumeration."""

    public_contract = _resolve(contract_path)
    public_output = _resolve(output_directory)
    contract = json.loads(public_contract.read_text(encoding="utf-8"))
    if (
        contract.get("schema_version")
        != "sim2claw.bidirectional_pawn_push_v2_low_planar_open_jaw_static.v1"
    ):
        raise LowPlanarOpenJawStaticV1Error(
            "unexpected V05-UG static contract"
        )
    if (
        contract.get("status")
        != "fresh_manager_authorized_after_fable_orientation_review"
        or contract.get("resume") is not True
    ):
        raise LowPlanarOpenJawStaticV1Error(
            "V05-UG is paused for canonical-orientation Fable review; "
            "model loading and static enumeration are forbidden"
        )
    authorization_path = _verify(contract["authorization"])
    _verify(contract["v05_uf_temporal_receipt"])
    orientation_path = _verify(contract["orientation_static_contract"])
    seeded_path = _verify(contract["seeded_static_contract"])
    ramped_path = _verify(contract["ramped_static_contract"])
    open_path = _verify(contract["open_jaw_static_contract"])
    for binding in contract["base_implementations"].values():
        _verify(binding)
    _verify(contract["implementation"])

    authorization = json.loads(
        authorization_path.read_text(encoding="utf-8")
    )
    public_quarantine = authorization["quarantine"]["case_ids"]
    overrides = contract["frozen_overrides"]
    if public_quarantine != overrides["cumulative_quarantine_case_ids"]:
        raise LowPlanarOpenJawStaticV1Error(
            "V05-UG cumulative quarantine changed"
        )
    if len(public_quarantine) != 20:
        raise LowPlanarOpenJawStaticV1Error(
            "V05-UG cumulative quarantine is not exact"
        )
    if (
        overrides["contact_height_m"] != 0.018
        or overrides["contact_offset_m"] != 0.016
        or overrides["stroke_m"] != 0.09
        or overrides["vertical_rise_m"] != 0.0
        or overrides["maximum_total_cells"] != 396
    ):
        raise LowPlanarOpenJawStaticV1Error(
            "V05-UG frozen geometry or cell budget changed"
        )

    public_output.mkdir(parents=True, exist_ok=True)
    prior_orientation = json.loads(
        orientation_path.read_text(encoding="utf-8")
    )
    prior_seeded = json.loads(seeded_path.read_text(encoding="utf-8"))
    prior_ramped = json.loads(ramped_path.read_text(encoding="utf-8"))
    prior_open = json.loads(open_path.read_text(encoding="utf-8"))

    compatibility_orientation = copy.deepcopy(prior_orientation)
    compatibility_orientation.update(
        {
            "enumeration_id": (
                "bidirectional-pawn-push-v2-low-planar-open-jaw-"
                "compatibility-orientation-v1"
            ),
            "status": (
                "deterministic_compatibility_scaffold_derived_before_"
                "v05_ug_model_loading"
            ),
        }
    )
    compatibility_orientation["family_grid"].update(
        {
            "excluded_source_squares": list(
                overrides["compatibility_excluded_source_squares"]
            ),
            "expected_prequarantine_family_count": 35,
            "expected_postquarantine_family_count": 22,
            "source_exclusion_rule": (
                "remove every route from all four V05-UF dynamic selected "
                "sources before applying the immutable prior sixteen-case "
                "compatibility filter"
            ),
        }
    )
    compatibility_orientation["parameter_grid"][
        "maximum_total_cells"
    ] = 396
    compatibility_orientation["endpoint_geometry"] = {
        "contact_offset_m": 0.016,
        "contact_height_m": 0.018,
        "stroke_m": 0.09,
        "precontact_clearance_height_above_pawn_base_m": 0.075,
        "inside_v05_tk_bounds": True,
        "static_only_subset_rule": (
            "one exact low contact and completely level 90 mm planar "
            "continuation; no upward or rising segment"
        ),
    }
    compatibility_orientation_binding = _write_json(
        public_output / "compatibility_orientation_contract.json",
        compatibility_orientation,
    )

    compatibility_seeded = copy.deepcopy(prior_seeded)
    compatibility_seeded.update(
        {
            "enumeration_id": (
                "bidirectional-pawn-push-v2-low-planar-open-jaw-"
                "compatibility-seeded-v1"
            ),
            "status": (
                "deterministic_compatibility_scaffold_derived_before_"
                "v05_ug_model_loading"
            ),
            "base_static_contract": compatibility_orientation_binding,
        }
    )
    compatibility_seeded["frozen_overrides"].update(
        {
            "endpoint_geometry": copy.deepcopy(
                compatibility_orientation["endpoint_geometry"]
            ),
            "path_shape": overrides["path_shape"],
            "postquarantine_family_count": 22,
            "maximum_total_cells": 576,
        }
    )
    compatibility_seeded_binding = _write_json(
        public_output / "compatibility_seeded_contract.json",
        compatibility_seeded,
    )

    compatibility_ramped = copy.deepcopy(prior_ramped)
    compatibility_ramped.update(
        {
            "enumeration_id": (
                "bidirectional-pawn-push-v2-low-planar-open-jaw-"
                "compatibility-planar-v1"
            ),
            "status": (
                "deterministic_compatibility_scaffold_derived_before_"
                "v05_ug_model_loading"
            ),
            "base_static_contract": compatibility_seeded_binding,
        }
    )
    compatibility_ramped["frozen_overrides"].update(
        {
            "path_shape": overrides["path_shape"],
            "level_engagement_m": 0.01,
            "ramp_end_planar_progress_m": 0.025,
            "ramp_rise_m": 0.0,
            "planar_endpoint_m": 0.09,
            "derivation": overrides["geometry_derivation"],
            "same_postquarantine_family_count": 22,
            "maximum_total_cells": 576,
        }
    )
    compatibility_ramped_binding = _write_json(
        public_output / "compatibility_planar_contract.json",
        compatibility_ramped,
    )

    compatibility_open = copy.deepcopy(prior_open)
    compatibility_open.update(
        {
            "enumeration_id": (
                "bidirectional-pawn-push-v2-low-planar-open-jaw-"
                "compatibility-open-v1"
            ),
            "status": (
                "deterministic_compatibility_scaffold_derived_before_"
                "v05_ug_model_loading"
            ),
            "base_static_contract": compatibility_ramped_binding,
        }
    )
    compatibility_open["frozen_overrides"].update(
        {
            "path_shape": overrides["path_shape"],
            "same_postquarantine_family_count": 22,
            "maximum_total_cells": 576,
        }
    )
    compatibility_open_binding = _write_json(
        public_output / "compatibility_open_contract.json",
        compatibility_open,
    )

    receipt = _open.enumerate_and_freeze(
        REPO_ROOT / compatibility_open_binding["path"],
        public_output,
    )
    grid_count = int(receipt["grid_result_count"])
    selected = receipt["eligible_cases"]
    leaked_case_ids = sorted(
        {
            str(row["case_id"])
            for row in receipt["grid_results"]
            if row["case_id"] in set(public_quarantine)
        }
    )
    excluded_sources = set(
        overrides["compatibility_excluded_source_squares"]
    )
    leaked_source_squares = sorted(
        {
            str(row["source_square"])
            for row in receipt["grid_results"]
            if row["source_square"] in excluded_sources
        }
    )
    passed = (
        receipt["status"] == "unilateral_open_jaw_static_freeze_pass"
        and grid_count == 396
        and receipt["lane_counts"]
        == {"REAL_TO_SIM": 2, "SIM_TO_REAL": 2}
        and len(selected) == 4
        and not leaked_case_ids
        and not leaked_source_squares
    )
    receipt.update(
        {
            "schema_version": (
                "sim2claw.bidirectional_pawn_push_v2_"
                "low_planar_open_jaw_static_receipt.v1"
            ),
            "status": (
                "low_planar_open_jaw_static_freeze_pass"
                if passed
                else "low_planar_open_jaw_static_freeze_reject"
            ),
            "proof_class": (
                "cpu_fp64_static_low_contact_planar_unilateral_open_jaw_"
                "collision_camera_gateway_action_freeze_only"
            ),
            "contract_path": str(public_contract.relative_to(REPO_ROOT)),
            "contract_sha256": _sha(public_contract),
            "authorization_sha256": contract["authorization"]["sha256"],
            "v05_uf_temporal_receipt_sha256": contract[
                "v05_uf_temporal_receipt"
            ]["sha256"],
            "cumulative_quarantined_case_ids": list(public_quarantine),
            "cumulative_quarantined_case_count": len(public_quarantine),
            "compatibility_excluded_source_squares": sorted(
                excluded_sources
            ),
            "quarantine_case_id_leaks": leaked_case_ids,
            "quarantine_source_leaks": leaked_source_squares,
            "postexclusion_family_count": 22,
            "parameter_cell_count_per_family": 18,
            "maximum_total_cells": 396,
            "contact_height_m": 0.018,
            "contact_offset_m": 0.016,
            "stroke_m": 0.09,
            "vertical_rise_m": 0.0,
            "upward_or_rising_segment_count": 0,
            "open_jaw_target_rad": 1.2,
            "jaw_constant_during_setup_and_push": True,
            "jaw_closing_allowed": False,
            "bilateral_contact_allowed": False,
            "grasp_or_enclosure_allowed": False,
            "selected_pawn_lift_allowed": False,
            "robot_board_contact_allowed": False,
            "dynamic_replay_executed": False,
            "physical_motion": False,
            "physical_task_attempts": 0,
            "compatibility_contracts": {
                "orientation": compatibility_orientation_binding,
                "seeded": compatibility_seeded_binding,
                "planar": compatibility_ramped_binding,
                "open": compatibility_open_binding,
            },
            "claim_boundary": (
                "Static-only deterministic exact-geometry low-contact "
                "planar unilateral open-jaw search over 396 fresh cells. "
                "No upward segment, grasp, lift, dynamic task outcome, "
                "physical packet, promotion, or transfer claim."
            ),
        }
    )
    (public_output / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = [
    "LowPlanarOpenJawStaticV1Error",
    "enumerate_and_freeze",
]

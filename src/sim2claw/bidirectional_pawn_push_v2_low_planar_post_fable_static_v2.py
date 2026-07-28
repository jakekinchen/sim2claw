"""Post-Fable current-task low-planar static freeze."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from . import bidirectional_pawn_push_v2_current_task_static_v1 as _current
from . import bidirectional_pawn_push_v2_low_planar_open_jaw_static_v1 as _ug
from . import bidirectional_pawn_push_v2_orientation_funnel_static_v1 as _orientation
from .paths import REPO_ROOT


SCHEMA = "sim2claw.bidirectional_pawn_push_v2_low_planar_post_fable_static.v2"


class LowPlanarPostFableStaticV2Error(RuntimeError):
    """The bounded post-Fable static freeze failed closed."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(path: Path) -> Path:
    resolved = path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise LowPlanarPostFableStaticV2Error(
            "post-Fable static path escapes repository"
        ) from error
    return resolved


def _verify(entry: Mapping[str, Any]) -> Path:
    path = _resolve(Path(str(entry["path"])))
    if not path.is_file() or _sha(path) != entry["sha256"]:
        raise LowPlanarPostFableStaticV2Error(
            f"bound post-Fable static input changed: {path}"
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
    public_contract = _resolve(contract_path)
    public_output = _resolve(output_directory)
    contract = json.loads(public_contract.read_text(encoding="utf-8"))
    if contract.get("schema_version") != SCHEMA:
        raise LowPlanarPostFableStaticV2Error(
            "unexpected post-Fable static contract"
        )
    if (
        contract.get("status") != "frozen_before_model_loading"
        or contract.get("resume") is not True
    ):
        raise LowPlanarPostFableStaticV2Error(
            "post-Fable static contract is not frozen and resumed"
        )

    authorization_path = _verify(contract["authorization"])
    authorization = json.loads(
        authorization_path.read_text(encoding="utf-8")
    )
    _verify(contract["post_fable_decision"])
    _verify(contract["current_task_scene_labels"])
    _verify(contract["supersedes_paused_v05_ug"])
    _verify(contract["selection_source_static_receipt"])
    _verify(contract["v05_uf_temporal_receipt"])
    orientation_path = _verify(contract["orientation_static_contract"])
    _verify(contract["seeded_static_contract"])
    _verify(contract["ramped_static_contract"])
    _verify(contract["open_jaw_static_contract"])
    for binding in contract["base_implementations"].values():
        _verify(binding)
    _verify(contract["legacy_compatibility_implementation"])
    _verify(contract["current_task_adapter"])
    _verify(contract["implementation"])

    if (
        authorization.get("status")
        != "authorized_static_only_after_milestone_a_commit"
        or authorization.get("milestone_a_commit") != "f154ac1"
    ):
        raise LowPlanarPostFableStaticV2Error(
            "Milestone A commit is not bound"
        )
    frozen = contract["frozen_design"]
    quarantine = list(frozen["cumulative_quarantine_case_ids"])
    if (
        quarantine != authorization["quarantine"]["case_ids"]
        or len(quarantine) != 20
    ):
        raise LowPlanarPostFableStaticV2Error(
            "post-Fable quarantine changed"
        )
    expected_scalars = {
        "selected_family_count": 6,
        "contact_height_m": 0.018,
        "contact_offset_m": 0.016,
        "stroke_m": 0.09,
        "vertical_rise_m": 0.0,
        "maximum_total_cells": 108,
        "flat_closed_jaw_side_or_back_anti_wedge_hedge_count": 0,
    }
    if any(frozen.get(key) != value for key, value in expected_scalars.items()):
        raise LowPlanarPostFableStaticV2Error(
            "post-Fable frozen static design changed"
        )
    if frozen["dynamic_outcomes_available_to_ranking"] is not False:
        raise LowPlanarPostFableStaticV2Error(
            "dynamic outcomes leaked into static ranking"
        )
    priority_case_ids = list(frozen["priority_case_ids"])
    if priority_case_ids != [
        "brown_pawn_d1__d1_c1",
        "tan_pawn_b7__b7_b8",
        "tan_pawn_b7__b7_a7",
        "tan_pawn_c8__c8_b8",
        "tan_pawn_c8__c8_c7",
        "tan_pawn_a8__a8_b8",
    ]:
        raise LowPlanarPostFableStaticV2Error(
            "post-Fable priority family list changed"
        )

    public_output.mkdir(parents=True, exist_ok=True)
    orientation = json.loads(orientation_path.read_text(encoding="utf-8"))
    orientation = copy.deepcopy(orientation)
    orientation.update(
        {
            "enumeration_id": (
                "bidirectional-pawn-push-v2-post-fable-"
                "orientation-source-v2"
            ),
            "status": (
                "prospective_static_ranking_frozen_before_model_loading"
            ),
        }
    )
    orientation["selection"].update(
        {
            "selected_family_count": 6,
            "minimum_distinct_families_per_direction": 2,
            "fewer_than_four_eligible_families": (
                "fewer_than_six_is_terminal_static_reject"
            ),
            "dynamic_outcome_used": False,
            "grid_expansion_after_result": False,
        }
    )
    prospective_orientation = _write_json(
        public_output / "prospective_orientation_source_v2.json",
        orientation,
    )

    compatibility = {
        "schema_version": (
            "sim2claw.bidirectional_pawn_push_v2_"
            "low_planar_open_jaw_static.v1"
        ),
        "enumeration_id": (
            "bidirectional-pawn-push-v2-post-fable-"
            "low-planar-compatibility-v2"
        ),
        "status": "fresh_manager_authorized_after_fable_orientation_review",
        "proof_class": (
            "prospective_current_task_compatibility_static_scaffold_only"
        ),
        "resume": True,
        "authorization": contract["authorization"],
        "current_task_scene_labels": contract["current_task_scene_labels"],
        "v05_uf_temporal_receipt": contract["v05_uf_temporal_receipt"],
        "orientation_static_contract": prospective_orientation,
        "seeded_static_contract": contract["seeded_static_contract"],
        "ramped_static_contract": contract["ramped_static_contract"],
        "open_jaw_static_contract": contract["open_jaw_static_contract"],
        "base_implementations": contract["base_implementations"],
        "implementation": contract["legacy_compatibility_implementation"],
        "frozen_overrides": {
            "cumulative_quarantine_case_ids": quarantine,
            "compatibility_excluded_source_squares": list(
                frozen["compatibility_excluded_source_squares"]
            ),
            "contact_height_m": frozen["contact_height_m"],
            "contact_offset_m": frozen["contact_offset_m"],
            "stroke_m": frozen["stroke_m"],
            "vertical_rise_m": frozen["vertical_rise_m"],
            "maximum_total_cells": 396,
            "path_shape": frozen["path_shape"],
            "geometry_derivation": frozen["geometry_derivation"],
        },
    }
    compatibility_binding = _write_json(
        public_output / "compatibility_static_contract_v2.json",
        compatibility,
    )

    original_selection_key = _orientation._selection_key
    original_open_enumerator = _ug._open.enumerate_and_freeze
    original_neighbor_enumerator = (
        _orientation._static.enumerate_empty_orthogonal_neighbors
    )
    priority = {
        case_id: index for index, case_id in enumerate(priority_case_ids)
    }
    finite_chain: dict[str, dict[str, str]] = {}

    def frozen_priority_selection_key(
        row: Mapping[str, Any],
    ) -> tuple[Any, ...]:
        return (
            priority.get(str(row["case_id"]), len(priority_case_ids)),
            *original_selection_key(row),
        )

    def exact_priority_neighbors(
        pieces_by_square: Mapping[str, str],
        *,
        excluded_squares: list[str],
    ) -> list[dict[str, str]]:
        complete = original_neighbor_enumerator(
            pieces_by_square,
            excluded_squares=excluded_squares,
        )
        allowed = set(priority_case_ids)
        return [
            row
            for row in complete
            if (
                f"{row['selected_piece_id']}__"
                f"{row['source_square']}_{row['destination_square']}"
            )
            in allowed
        ]

    def finite_open_enumerator(
        open_contract_path: Path,
        output_directory: Path,
    ) -> dict[str, Any]:
        open_contract = json.loads(
            open_contract_path.read_text(encoding="utf-8")
        )
        ramped_path = _verify(open_contract["base_static_contract"])
        ramped = json.loads(ramped_path.read_text(encoding="utf-8"))
        seeded_path = _verify(ramped["base_static_contract"])
        seeded = json.loads(seeded_path.read_text(encoding="utf-8"))
        orientation_path = _verify(seeded["base_static_contract"])
        orientation_contract = json.loads(
            orientation_path.read_text(encoding="utf-8")
        )
        orientation_contract["family_grid"].update(
            {
                "expected_prequarantine_family_count": 6,
                "expected_postquarantine_family_count": 6,
                "allowed_case_ids": priority_case_ids,
                "no_substitution": True,
            }
        )
        orientation_contract["parameter_grid"]["maximum_total_cells"] = 108
        orientation_contract["selection"].update(
            {
                "selected_family_count": 6,
                "minimum_distinct_families_per_direction": 2,
                "dynamic_outcome_used": False,
                "grid_expansion_after_result": False,
            }
        )
        finite_chain["orientation"] = _write_json(
            orientation_path,
            orientation_contract,
        )
        seeded["base_static_contract"] = finite_chain["orientation"]
        finite_chain["seeded"] = _write_json(seeded_path, seeded)
        ramped["base_static_contract"] = finite_chain["seeded"]
        finite_chain["planar"] = _write_json(ramped_path, ramped)
        open_contract["base_static_contract"] = finite_chain["planar"]
        finite_chain["open"] = _write_json(
            open_contract_path,
            open_contract,
        )
        _orientation._static.enumerate_empty_orthogonal_neighbors = (
            exact_priority_neighbors
        )
        try:
            return original_open_enumerator(
                open_contract_path,
                output_directory,
            )
        finally:
            _orientation._static.enumerate_empty_orthogonal_neighbors = (
                original_neighbor_enumerator
            )

    _orientation._selection_key = frozen_priority_selection_key
    _ug._open.enumerate_and_freeze = finite_open_enumerator
    try:
        receipt = _current.enumerate_low_planar_and_freeze(
            REPO_ROOT / compatibility_binding["path"],
            public_output,
        )
    finally:
        _orientation._selection_key = original_selection_key
        _ug._open.enumerate_and_freeze = original_open_enumerator
        _orientation._static.enumerate_empty_orthogonal_neighbors = (
            original_neighbor_enumerator
        )
    selected = receipt["eligible_cases"]
    selected_case_ids = [row["case_id"] for row in selected]
    selected_by_lane = {
        lane: [
            row["case_id"]
            for row in selected
            if row["direction_lane"] == lane
        ]
        for lane in ("REAL_TO_SIM", "SIM_TO_REAL")
    }
    expected_by_lane = {
        lane: list(frozen["direction_composition"][lane])
        for lane in ("REAL_TO_SIM", "SIM_TO_REAL")
    }
    lane_counts = {
        lane: sum(row["direction_lane"] == lane for row in selected)
        for lane in ("REAL_TO_SIM", "SIM_TO_REAL")
    }
    passed = (
        receipt["grid_result_count"] == 108
        and receipt["statically_eligible_family_count"] >= 6
        and len(selected) == 6
        and selected_case_ids == priority_case_ids
        and selected_by_lane == expected_by_lane
        and lane_counts["REAL_TO_SIM"] >= 2
        and lane_counts["SIM_TO_REAL"] >= 2
        and not receipt["quarantine_case_id_leaks"]
        and not receipt["quarantine_source_leaks"]
        and receipt["current_task_scene_labels"][
            "compiled_reset_layout_invariant_checked"
        ]
    )
    compatibility_status = receipt["status"]
    receipt.update(
        {
            "schema_version": (
                "sim2claw.bidirectional_pawn_push_v2_"
                "low_planar_post_fable_static_receipt.v2"
            ),
            "status": (
                "post_fable_static_freeze_pass"
                if passed
                else "post_fable_static_terminal_negative"
            ),
            "proof_class": (
                "cpu_fp64_current_task_low_planar_static_"
                "ranking_and_action_freeze_only"
            ),
            "contract_path": str(public_contract.relative_to(REPO_ROOT)),
            "contract_sha256": _sha(public_contract),
            "compatibility_contract": compatibility_binding,
            "compatibility_status_before_v2_adjudication": compatibility_status,
            "prospective_orientation_source": prospective_orientation,
            "finite_compatibility_chain": finite_chain,
            "evaluated_family_count": 6,
            "parameter_cell_count_per_family": 18,
            "maximum_total_cells": 108,
            "selected_family_count": len(selected),
            "priority_case_ids": priority_case_ids,
            "selected_case_ids": selected_case_ids,
            "selected_case_ids_by_direction": selected_by_lane,
            "priority_family_substitution_allowed": False,
            "priority_family_substitution_observed": (
                selected_case_ids != priority_case_ids
            ),
            "lane_counts": lane_counts,
            "minimum_families_per_direction": 2,
            "rank_criterion_frozen_before_dynamics": True,
            "dynamic_outcomes_available_to_ranking": False,
            "flat_closed_jaw_side_or_back_anti_wedge_hedge_count": 0,
            "flat_closed_jaw_side_or_back_anti_wedge_hedge_geometry": None,
            "dynamic_replay_executed": False,
            "physical_motion": False,
            "physical_task_attempts": 0,
            "authority": contract["authority"],
            "claim_boundary": (
                "One prospective CPU/fp64 current-task static ranking and "
                "action freeze. No dynamic task outcome, camera or gateway "
                "opening, physical packet, promotion, or transfer claim."
            ),
        }
    )
    (public_output / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = ["LowPlanarPostFableStaticV2Error", "enumerate_and_freeze"]

"""Extract a non-metric physical enclosure proxy from retained wrist footage."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from pathlib import Path
from typing import Any

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
)
from .observable_registration_belief_recalculation import (
    REPO_ROOT,
    _bound_json,
    _bound_path,
)


SCHEMA = "sim2claw.observable_registration_footage_enclosure_audit_contract.v1"
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_footage_enclosure_audit_receipt.v1"
)
ROWS_SCHEMA = "sim2claw.observable_registration_footage_enclosure_rows.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/observable_registration_footage_enclosure_audit_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT / "outputs/observable_registration_footage_enclosure_audit_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _projection(
    fixed: list[float], moving: list[float], crown: list[float]
) -> dict[str, float | bool]:
    axis_x = float(moving[0]) - float(fixed[0])
    axis_y = float(moving[1]) - float(fixed[1])
    separation_squared = axis_x * axis_x + axis_y * axis_y
    _require(separation_squared > 0.0, "coincident jaw landmarks")
    crown_x = float(crown[0]) - float(fixed[0])
    crown_y = float(crown[1]) - float(fixed[1])
    axial_fraction = (
        crown_x * axis_x + crown_y * axis_y
    ) / separation_squared
    perpendicular_fraction = (
        -crown_x * axis_y + crown_y * axis_x
    ) / separation_squared
    return {
        "jaw_separation_px": math.sqrt(separation_squared),
        "crown_axial_fraction_fixed_to_moving": axial_fraction,
        "crown_perpendicular_fraction_of_jaw_separation": perpendicular_fraction,
        "crown_projection_between_jaw_tips": 0.0 <= axial_fraction <= 1.0,
    }


def _summary(values: list[float]) -> dict[str, float]:
    _require(bool(values), "empty summary population")
    return {
        "minimum": min(values),
        "maximum": max(values),
        "mean": statistics.fmean(values),
        "population_standard_deviation": statistics.pstdev(values),
        "range": max(values) - min(values),
    }


def _scope_summary(
    rows: list[dict[str, Any]], pass_name: str
) -> dict[str, Any]:
    projections = [row["projections"][pass_name] for row in rows]
    return {
        "row_count": len(rows),
        "sample_indices": [row["sample_index"] for row in rows],
        "between_jaw_tip_count": sum(
            bool(value["crown_projection_between_jaw_tips"])
            for value in projections
        ),
        "all_crown_projections_between_jaw_tips": all(
            bool(value["crown_projection_between_jaw_tips"])
            for value in projections
        ),
        "jaw_separation_px": _summary(
            [float(value["jaw_separation_px"]) for value in projections]
        ),
        "crown_axial_fraction_fixed_to_moving": _summary(
            [
                float(value["crown_axial_fraction_fixed_to_moving"])
                for value in projections
            ]
        ),
        "crown_perpendicular_fraction_of_jaw_separation": _summary(
            [
                float(
                    value["crown_perpendicular_fraction_of_jaw_separation"]
                )
                for value in projections
            ]
        ),
    }


def _matching_runs(
    samples: list[dict[str, Any]],
    *,
    start: int,
    stop: int,
    joint_index: int,
    field: str,
    target: float,
    tolerance: float,
) -> list[tuple[int, int]]:
    matching = [
        start <= index <= stop
        and abs(float(row[field][joint_index]) - target) <= tolerance
        for index, row in enumerate(samples)
    ]
    runs: list[tuple[int, int]] = []
    run_start: int | None = None
    for index in range(start, stop + 2):
        is_match = index <= stop and matching[index]
        if is_match and run_start is None:
            run_start = index
        elif not is_match and run_start is not None:
            runs.append((run_start, index - 1))
            run_start = None
    return runs


def load_footage_enclosure_audit_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR52 footage enclosure audit")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)

    footage = contract["footage_policy"]
    _require(
        footage["recording_id"] == "20260727T041737Z-89190e53"
        and footage["physical_definite_carry_interval_samples_inclusive"]
        == [260, 390]
        and footage["annotation_pass_fields"] == ["pass_a_xy", "pass_b_xy"]
        and footage["minimum_coaccepted_carry_rows"] == 8
        and footage["minimum_coaccepted_carry_span_samples"] == 80
        and footage["crown_axial_fraction_bounds_inclusive"] == [0.0, 1.0]
        and footage["failed_or_missing_rows_abstain"] is True,
        "footage cohort or gates drifted",
    )
    _require(
        not any(
            footage[name]
            for name in (
                "reannotation_allowed",
                "interpolation_allowed",
                "cross_episode_merge_allowed",
            )
        ),
        "footage policy widened",
    )
    hold = contract["closed_command_hold"]
    _require(
        hold["selection_rule"] == "longest_contiguous_matching_run"
        and hold["minimum_coaccepted_hold_rows"] == 4
        and hold["stability_threshold_or_parameter_fit_allowed"] is False,
        "closed-command audit widened",
    )
    execution = contract["execution"]
    _require(
        all(
            execution[name] == 0
            for name in (
                "new_annotations_allowed",
                "simulator_replays_allowed",
                "new_candidates_allowed",
                "parameter_changes_allowed",
                "hardware_actions_allowed",
            )
        )
        and execution["heldout_open_allowed"] is False,
        "execution boundary widened",
    )
    _require(not any(contract["claim_limits"].values()), "claim boundary widened")
    _require(not any(contract["authority"].values()), "authority widened")
    return contract


def run_footage_enclosure_audit_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR52 one-run receipt already exists")
    contract = load_footage_enclosure_audit_contract(contract_path, root=root)
    physical = _bound_json(
        contract["sources"]["physical_episode"], root=root, label="physical episode"
    )
    proxy_rows = _bound_json(
        contract["sources"]["or22_proxy_rows"], root=root, label="OR22 rows"
    )
    or22 = _bound_json(
        contract["sources"]["or22_receipt"], root=root, label="OR22 receipt"
    )
    raw_path = _bound_path(
        contract["sources"]["raw_samples"], root=root, label="raw samples"
    )
    or51 = _bound_json(
        contract["sources"]["or51_receipt"], root=root, label="OR51 receipt"
    )
    episode = physical["observable_episode"]
    footage = contract["footage_policy"]
    _require(
        episode["recording_id"] == footage["recording_id"],
        "physical recording identity drifted",
    )
    carry = episode["contact_and_motion_events"][
        "definite_carried_motion_interval_samples"
    ]["sample_indices"]
    _require(
        carry == footage["physical_definite_carry_interval_samples_inclusive"],
        "physical carry interval drifted",
    )
    _require(
        episode["object_observations"]["metric_depth_available"] is False
        and episode["object_observations"]["metric_object_pose_available"] is False,
        "physical proof class drifted",
    )
    _require(
        or22["status"]
        == "PASS_BOUNDED_JAW_CROWN_EVENT_PROXY_PAWN_AXIS_INSUFFICIENT"
        and or22["proxy_rows_sha256"]
        == contract["sources"]["or22_proxy_rows"]["sha256"],
        "OR22 boundary drifted",
    )
    _require(
        proxy_rows["recording_id"] == footage["recording_id"],
        "OR22 row identity drifted",
    )

    required_points = tuple(footage["required_points"])
    rows: list[dict[str, Any]] = []
    for track in episode["object_observations"]["wrist_rgb_tracks"]:
        sample = int(track["sample_index"])
        if not int(carry[0]) <= sample <= int(carry[1]):
            continue
        points = track["points"]
        if not all(points[name]["accepted"] for name in required_points):
            continue
        projections = {
            pass_name: _projection(
                points["fixed_jaw_tip"][field],
                points["moving_jaw_tip"][field],
                points["selected_pawn_crown"][field],
            )
            for pass_name, field in (
                ("pass_a", "pass_a_xy"),
                ("pass_b", "pass_b_xy"),
                ("consensus", "consensus_xy"),
            )
        }
        rows.append(
            {
                "sample_index": sample,
                "sample_time_seconds": track["sample_time_seconds"],
                "d405_frame_index": track["d405_frame_index"],
                "association_error_ms": track["association_error_ms"],
                "projections": projections,
            }
        )
    rows.sort(key=lambda row: row["sample_index"])
    proxy_samples = [
        int(row["sample_index"])
        for row in proxy_rows["rows"]
        if int(carry[0]) <= int(row["sample_index"]) <= int(carry[1])
        and row["jaw_proxy_available"]
        and row["crown_proxy_available"]
    ]
    sample_indices = [int(row["sample_index"]) for row in rows]
    _require(sample_indices == proxy_samples, "OR22 accepted cohort drifted")

    raw_samples = _load_jsonl(raw_path)
    _require(
        len(raw_samples) == 531
        and [int(row["sample_index"]) for row in raw_samples] == list(range(531)),
        "raw sample schedule drifted",
    )
    hold = contract["closed_command_hold"]
    hold_runs = _matching_runs(
        raw_samples,
        start=int(hold["search_sample_range_inclusive"][0]),
        stop=int(hold["search_sample_range_inclusive"][1]),
        joint_index=int(hold["gripper_joint_index"]),
        field=str(hold["command_field"]),
        target=float(hold["closed_command_target_degrees"]),
        tolerance=float(hold["absolute_tolerance_degrees"]),
    )
    _require(bool(hold_runs), "closed-command hold absent")
    hold_start, hold_stop = max(
        hold_runs, key=lambda run: (run[1] - run[0] + 1, -run[0])
    )
    hold_rows = [
        row for row in rows if hold_start <= int(row["sample_index"]) <= hold_stop
    ]

    carry_span = sample_indices[-1] - sample_indices[0] if rows else 0
    pass_summaries = {
        pass_name: _scope_summary(rows, pass_name)
        for pass_name in ("pass_a", "pass_b", "consensus")
    }
    hold_summaries = {
        pass_name: _scope_summary(hold_rows, pass_name)
        for pass_name in ("pass_a", "pass_b", "consensus")
    }
    gates = {
        "minimum_coaccepted_carry_rows": len(rows)
        >= int(footage["minimum_coaccepted_carry_rows"]),
        "minimum_coaccepted_carry_span": carry_span
        >= int(footage["minimum_coaccepted_carry_span_samples"]),
        "pass_a_all_crown_projections_between_jaw_tips": pass_summaries[
            "pass_a"
        ]["all_crown_projections_between_jaw_tips"],
        "pass_b_all_crown_projections_between_jaw_tips": pass_summaries[
            "pass_b"
        ]["all_crown_projections_between_jaw_tips"],
        "minimum_coaccepted_closed_hold_rows": len(hold_rows)
        >= int(hold["minimum_coaccepted_hold_rows"]),
    }
    physical_proxy_pass = all(gates.values())

    comparison = contract["simulator_comparison"]
    _require(
        or51["status"] == comparison["expected_or51_status"],
        "OR51 status drifted",
    )
    trace_contact = or51["event_audit"]["trace_contact_audit"]
    _require(
        trace_contact["required_named_jaw_bodies"]
        == comparison["required_named_jaw_bodies"],
        "OR51 jaw identities drifted",
    )

    rows_document = {
        "schema_version": ROWS_SCHEMA,
        "recording_id": footage["recording_id"],
        "carry_interval_samples_inclusive": carry,
        "rows": rows,
    }
    output_directory.mkdir(parents=True, exist_ok=False)
    rows_path = output_directory / "enclosure_rows.json"
    atomic_write_json(rows_path, rows_document)

    status = (
        "PASS_FOOTAGE_ONLY_PERSISTENT_ENCLOSURE_PROXY_SIMULATOR_"
        "BILATERAL_CONTACT_ABSENT"
        if physical_proxy_pass
        else "INSUFFICIENT_FOOTAGE_ENCLOSURE_PROXY_NO_REANNOTATION"
    )
    result = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": status,
        "source_bindings": {
            name: binding["sha256"]
            for name, binding in contract["sources"].items()
        },
        "physical_footage_audit": {
            "recording_id": footage["recording_id"],
            "camera_stream": footage["camera_stream"],
            "metric_depth_available": False,
            "carry_interval_samples_inclusive": carry,
            "coaccepted_carry_row_count": len(rows),
            "coaccepted_carry_sample_span": carry_span,
            "coaccepted_carry_sample_indices": sample_indices,
            "closed_command_hold_interval_samples_inclusive": [
                hold_start,
                hold_stop,
            ],
            "closed_command_hold_row_count": len(hold_rows),
            "closed_command_hold_sample_indices": [
                int(row["sample_index"]) for row in hold_rows
            ],
            "carry_pass_summaries": pass_summaries,
            "closed_command_hold_pass_summaries": hold_summaries,
            "gates": gates,
            "persistent_image_plane_enclosure_proxy": physical_proxy_pass,
            "bilateral_physical_contact_proven": False,
            "metric_aperture_proven": False,
        },
        "simulator_comparison": {
            "or51_status": or51["status"],
            "first_named_jaw_contact_sample": trace_contact[
                "first_named_jaw_contact_sample"
            ],
            "first_bilateral_jaw_contact_sample": trace_contact[
                "first_bilateral_jaw_contact_sample"
            ],
            "observed_named_jaw_bodies": trace_contact[
                "observed_named_jaw_bodies"
            ],
            "both_named_jaw_surfaces_contact": trace_contact[
                "both_named_jaw_surfaces_contact"
            ],
            "preterminal_gate_pass_count": or51["event_audit"][
                "preterminal_gate_pass_count"
            ],
            "preterminal_gate_total_count": or51["event_audit"][
                "preterminal_gate_total_count"
            ],
            "footage_proxy_and_simulator_named_contact_are_same_proof_class": False,
            "diagnostic": (
                "physical footage shows persistent image-plane enclosure during "
                "carry while the selected simulator trace has moving-jaw-only "
                "named contact and no bilateral named contact"
            ),
        },
        "constraint_for_any_future_offline_candidate": {
            "must_reproduce_bilateral_named_jaw_contact": True,
            "must_pass_physical_contact_lift_support_and_upright_event_gates": True,
            "terminal_outcome_may_not_select_a_promotable_candidate": True,
            "metric_pad_geometry_still_unidentified": True,
        },
        "enclosure_rows_sha256": hashlib.sha256(rows_path.read_bytes()).hexdigest(),
        "new_execution": {
            "new_annotations": 0,
            "simulator_replays": 0,
            "new_candidates": 0,
            "parameter_changes": 0,
            "hardware_actions": 0,
            "heldout_opened": False,
        },
        "claim_limits": contract["claim_limits"],
        "authority": contract["authority"],
    }
    result["artifact_sha256"] = canonical_digest(result)
    atomic_write_json(receipt_path, result)
    return result


def main() -> int:
    run_footage_enclosure_audit_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

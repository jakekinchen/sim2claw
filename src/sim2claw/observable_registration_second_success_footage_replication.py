"""Fail-closed two-pass tracking replication on a second retained episode."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
)
from .observable_physical_episode import (
    _decode_grayscale_video,
    bidirectional_point_tracks,
)
from .observable_registration_belief_recalculation import (
    REPO_ROOT,
    _bound_json,
    _bound_path,
)
from .observable_registration_footage_enclosure_audit import _matching_runs


SCHEMA = (
    "sim2claw.observable_registration_second_success_footage_replication_"
    "contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_second_success_footage_replication_"
    "receipt.v1"
)
ROWS_SCHEMA = (
    "sim2claw.observable_registration_second_success_footage_replication_rows.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "observable_registration_second_success_footage_replication_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs/observable_registration_second_success_footage_replication_v1"
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
    squared = axis_x * axis_x + axis_y * axis_y
    _require(squared > 0.0, "coincident jaw landmarks")
    crown_x = float(crown[0]) - float(fixed[0])
    crown_y = float(crown[1]) - float(fixed[1])
    axial = (crown_x * axis_x + crown_y * axis_y) / squared
    return {
        "jaw_separation_px": math.sqrt(squared),
        "crown_axial_fraction_fixed_to_moving": axial,
        "crown_projection_between_jaw_tips": 0.0 <= axial <= 1.0,
    }


def load_second_success_footage_replication_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR54 footage replication")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
    policy = contract["recording_policy"]
    _require(
        policy["recording_id"] == "20260727T041623Z-4b8cba4b"
        and policy["directory_label"] == "b5-to-a5"
        and policy["authoritative_receipt_source_square"] == "b2"
        and policy["authoritative_receipt_destination_square"] == "b1"
        and policy["authoritative_receipt_piece_id"] == "brown_pawn_b2"
        and policy["authoritative_receipt_outcome_label"] == "success"
        and policy["known_outcome_quarantine_permanent"] is True
        and policy["heldout_claim_allowed"] is False
        and policy["cross_episode_parameter_fit_allowed"] is False,
        "recording policy widened",
    )
    tracking = contract["tracking"]
    _require(
        tracking["frame_range_inclusive"] == [100, 125]
        and tracking["pass_a"]["anchor_frame_index"] == 100
        and tracking["pass_b"]["anchor_frame_index"] == 125
        and tracking["minimum_accepted_rows_per_point"] == 20
        and tracking["maximum_jaw_tip_pass_disagreement_px"] == 8.0
        and tracking["maximum_pawn_crown_pass_disagreement_px"] == 8.0
        and tracking["per_frame_manual_correction_allowed"] is False
        and tracking["interpolation_allowed"] is False
        and tracking["failed_tracks_abstain"] is True,
        "tracking policy drifted",
    )
    execution = contract["execution"]
    _require(
        execution["endpoint_anchor_count"] == 6
        and execution["per_frame_manual_annotations_allowed"] == 0
        and all(
            execution[name] == 0
            for name in (
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


def run_second_success_footage_replication_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR54 one-run receipt already exists")
    contract = load_second_success_footage_replication_contract(
        contract_path, root=root
    )
    receipt = _bound_json(
        contract["sources"]["recording_receipt"],
        root=root,
        label="recording receipt",
    )
    metadata = _bound_json(
        contract["sources"]["wrist_rgb_metadata"],
        root=root,
        label="wrist RGB metadata",
    )
    policy = contract["recording_policy"]
    _require(
        receipt["recording_id"] == policy["recording_id"]
        and receipt["source_square"]
        == policy["authoritative_receipt_source_square"]
        and receipt["destination_square"]
        == policy["authoritative_receipt_destination_square"]
        and receipt["piece_id"] == policy["authoritative_receipt_piece_id"]
        and receipt["outcome_label"]
        == policy["authoritative_receipt_outcome_label"]
        and receipt["held_out_membership"] is False
        and receipt["is_training_data"] is False,
        "recording identity or quarantine drifted",
    )
    _require(
        metadata["browser_frame_count"] == 196
        and metadata["configured_fps"] == 5.0
        and metadata["metric_depth"] is False
        and metadata["claim_limits"]["camera_exposure_synchronization"]
        is False,
        "wrist RGB proof class drifted",
    )
    or52 = _bound_json(
        contract["sources"]["or52_closeout"], root=root, label="OR52 closeout"
    )
    or53 = _bound_json(
        contract["sources"]["or53_closeout"], root=root, label="OR53 closeout"
    )
    _require(
        or52["result"]["persistent_image_plane_enclosure_proxy"] is True
        and or53["result"]["all_five_gate_candidate_count"] == 0,
        "predecessor boundary drifted",
    )

    samples_path = _bound_path(
        contract["sources"]["raw_samples"], root=root, label="raw samples"
    )
    samples = _load_jsonl(samples_path)
    _require(
        len(samples) == 632
        and [int(row["sample_index"]) for row in samples] == list(range(632)),
        "raw sample schedule drifted",
    )
    hold = contract["closed_command_hold"]
    runs = _matching_runs(
        samples,
        start=int(hold["search_sample_range_inclusive"][0]),
        stop=int(hold["search_sample_range_inclusive"][1]),
        joint_index=int(hold["gripper_joint_index"]),
        field=str(hold["command_field"]),
        target=float(hold["closed_command_target_degrees"]),
        tolerance=float(hold["absolute_tolerance_degrees"]),
    )
    _require(bool(runs), "closed-command hold absent")
    hold_start, hold_stop = max(runs, key=lambda run: (run[1] - run[0] + 1, -run[0]))

    video_path = _bound_path(
        contract["sources"]["wrist_rgb_video"],
        root=root,
        label="wrist RGB video",
    )
    frames = _decode_grayscale_video(video_path)
    _require(len(frames) == 196, "decoded frame count drifted")
    tracks = bidirectional_point_tracks(frames, contract["tracking"])
    association = contract["frame_association"]
    fps = float(association["browser_frame_rate_hz"])
    time_field = str(association["sample_video_time_field"])
    max_error_ms = float(association["maximum_association_error_ms"])
    labels = [str(value) for value in contract["tracking"]["labels"]]
    rows: list[dict[str, Any]] = []
    for frame_index in range(100, 126):
        frame_time = frame_index / fps
        sample = min(samples, key=lambda row: abs(float(row[time_field]) - frame_time))
        error_ms = abs(float(sample[time_field]) - frame_time) * 1000.0
        _require(error_ms <= max_error_ms, "frame/sample association gate failed")
        points = tracks[frame_index]
        projections: dict[str, Any] = {}
        for pass_name, field in (("pass_a", "pass_a_xy"), ("pass_b", "pass_b_xy")):
            projections[pass_name] = _projection(
                points["fixed_jaw_tip"][field],
                points["moving_jaw_tip"][field],
                points["selected_pawn_crown"][field],
            )
        if all(points[label]["accepted"] for label in labels):
            projections["consensus"] = _projection(
                points["fixed_jaw_tip"]["consensus_xy"],
                points["moving_jaw_tip"]["consensus_xy"],
                points["selected_pawn_crown"]["consensus_xy"],
            )
        else:
            projections["consensus"] = None
        rows.append(
            {
                "frame_index": frame_index,
                "container_pts_seconds": frame_time,
                "nearest_sample_index": int(sample["sample_index"]),
                "association_error_ms": error_ms,
                "inside_closed_command_hold": hold_start
                <= int(sample["sample_index"])
                <= hold_stop,
                "points": points,
                "projections": projections,
            }
        )

    _require(
        len({row["nearest_sample_index"] for row in rows}) == len(rows),
        "selected frames did not map to unique samples",
    )
    accepted_counts = {
        label: sum(bool(row["points"][label]["accepted"]) for row in rows)
        for label in labels
    }
    minimum = int(contract["tracking"]["minimum_accepted_rows_per_point"])
    point_gates = {
        label: count >= minimum for label, count in accepted_counts.items()
    }
    all_inside_hold = all(row["inside_closed_command_hold"] for row in rows)
    replication_pass = all_inside_hold and all(point_gates.values())
    consensus_rows = [row for row in rows if row["projections"]["consensus"]]
    pass_b_between = sum(
        bool(row["projections"]["pass_b"]["crown_projection_between_jaw_tips"])
        for row in rows
    )
    status = (
        "PASS_QUARANTINED_SECOND_SUCCESSFUL_EPISODE_TWO_PASS_ENCLOSURE_REPLICATION"
        if replication_pass
        else "TERMINAL_SECOND_SUCCESSFUL_EPISODE_JAW_TRACKS_REPLICATE_"
        "PAWN_CROWN_TWO_PASS_ABSTAINS"
    )
    rows_document = {
        "schema_version": ROWS_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "recording_id": policy["recording_id"],
        "rows": rows,
    }
    output_directory.mkdir(parents=True, exist_ok=True)
    rows_path = output_directory / "tracking_rows.json"
    atomic_write_json(rows_path, rows_document)
    rows_sha256 = hashlib.sha256(rows_path.read_bytes()).hexdigest()
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "status": status,
        "proof_class": contract["proof_class"],
        "source_bindings": {
            name: binding["sha256"] for name, binding in contract["sources"].items()
        },
        "recording_identity": {
            "directory_label": policy["directory_label"],
            "authoritative_source_square": receipt["source_square"],
            "authoritative_destination_square": receipt["destination_square"],
            "authoritative_piece_id": receipt["piece_id"],
            "outcome_label": receipt["outcome_label"],
            "directory_receipt_semantic_conflict": True,
            "known_outcome_quarantine_permanent": True,
            "heldout": False,
        },
        "closed_command_hold_interval_samples_inclusive": [hold_start, hold_stop],
        "tracking": {
            "frame_count": len(rows),
            "frame_range_inclusive": [100, 125],
            "nearest_sample_range_inclusive": [
                rows[0]["nearest_sample_index"],
                rows[-1]["nearest_sample_index"],
            ],
            "maximum_association_error_ms": max(
                float(row["association_error_ms"]) for row in rows
            ),
            "all_frames_inside_closed_command_hold": all_inside_hold,
            "accepted_counts": accepted_counts,
            "minimum_accepted_rows_per_point": minimum,
            "point_gates": point_gates,
            "consensus_all_point_row_count": len(consensus_rows),
            "pass_b_crown_projection_between_jaw_tips_count": pass_b_between,
            "two_pass_enclosure_replication_pass": replication_pass,
        },
        "tracking_rows_sha256": rows_sha256,
        "execution": {
            "endpoint_anchor_count": 6,
            "per_frame_manual_annotations": 0,
            "simulator_replays": 0,
            "new_candidates": 0,
            "parameter_changes": 0,
            "hardware_actions": 0,
            "heldout_opened": False,
        },
        "claim_limits": contract["claim_limits"],
        "authority": contract["authority"],
    }
    result = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(receipt_path, result)
    return result


def main() -> None:
    run_second_success_footage_replication_once()


if __name__ == "__main__":
    main()

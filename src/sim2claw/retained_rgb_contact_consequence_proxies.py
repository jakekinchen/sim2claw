"""Reduce accepted successful-episode RGB tracks to bounded proxies."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

import numpy as np

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

SCHEMA = "sim2claw.retained_rgb_contact_consequence_proxies_contract.v1"
RECEIPT_SCHEMA = (
    "sim2claw.retained_rgb_contact_consequence_proxies_receipt.v1"
)
ROWS_SCHEMA = "sim2claw.retained_rgb_contact_consequence_proxy_rows.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "retained_rgb_contact_consequence_proxies_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT / "outputs/retained_rgb_contact_consequence_proxies_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_retained_rgb_contact_consequence_proxies_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="retained RGB proxies")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
    policy = contract["proxy_policy"]
    _require(
        policy["require_two_pass_accepted_points"] is True
        and policy[
            "pawn_axis_requires_distinct_accepted_crown_and_base_points"
        ]
        is True
        and policy["support_loss_is_event_interval_not_pixel_contact_state"]
        is True,
        "proxy observation gate weakened",
    )
    forbidden = (
        "metric_depth_restoration_allowed",
        "contact_force_inference_allowed",
        "cross_episode_merge_allowed",
        "reannotation_allowed",
    )
    _require(
        all(policy[name] is False for name in forbidden),
        "proxy policy widened",
    )
    _require(
        not any(contract["authority"].values()),
        "proxy authority widened",
    )
    return contract


def _accepted_xy(point: dict[str, Any]) -> np.ndarray | None:
    if not point["accepted"] or point["consensus_xy"] is None:
        return None
    return np.asarray(point["consensus_xy"], dtype=np.float64)


def build_retained_rgb_contact_consequence_proxies(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR22 output already exists")
    contract = load_retained_rgb_contact_consequence_proxies_contract(
        contract_path, root=root
    )
    physical = _bound_json(
        contract["sources"]["physical_episode"],
        root=root,
        label="physical episode",
    )
    or21 = _bound_json(
        contract["sources"]["or21_closeout"],
        root=root,
        label="OR21 closeout",
    )
    or22a = _bound_json(
        contract["sources"]["or22a_closeout"],
        root=root,
        label="OR22A closeout",
    )
    episode = physical["observable_episode"]
    _require(
        episode["schema_version"] == "sim2claw.observable_episode.v2-min"
        and episode["recording_id"] == "20260727T041737Z-89190e53",
        "successful episode identity changed",
    )
    _require(
        or21["status"] == "PASS_EXACT_REPRODUCTION_CONTACT_TRACE",
        "OR21 prerequisite changed",
    )
    _require(
        or22a["result"]["original_successful_d1_d2_pi_available"]
        is False,
        "successful episode Pi lineage changed",
    )
    rows: list[dict[str, Any]] = []
    for track in episode["object_observations"]["wrist_rgb_tracks"]:
        sample = int(track["sample_index"])
        if not (
            int(contract["proxy_policy"]["analysis_source_sample_start"])
            <= sample
            <= int(
                contract["proxy_policy"]["analysis_source_sample_end"]
            )
        ):
            continue
        points = track["points"]
        fixed = _accepted_xy(points["fixed_jaw_tip"])
        moving = _accepted_xy(points["moving_jaw_tip"])
        crown = _accepted_xy(points["selected_pawn_crown"])
        jaw_available = fixed is not None and moving is not None
        if jaw_available:
            axis = moving - fixed
            midpoint = 0.5 * (fixed + moving)
            separation = float(np.linalg.norm(axis))
            angle = math.degrees(math.atan2(float(axis[1]), float(axis[0])))
        else:
            axis = midpoint = None
            separation = angle = None
        crown_relative = (
            (crown - midpoint).tolist()
            if crown is not None and midpoint is not None
            else None
        )
        rows.append(
            {
                "sample_index": sample,
                "sample_time_seconds": track["sample_time_seconds"],
                "d405_frame_index": track["d405_frame_index"],
                "association_error_ms": track["association_error_ms"],
                "jaw_proxy_available": jaw_available,
                "jaw_midpoint_xy": (
                    midpoint.tolist() if midpoint is not None else None
                ),
                "jaw_aperture_axis_xy": (
                    axis.tolist() if axis is not None else None
                ),
                "jaw_separation_px": separation,
                "jaw_axis_angle_degrees": angle,
                "crown_proxy_available": crown is not None,
                "crown_xy": crown.tolist() if crown is not None else None,
                "crown_to_jaw_midpoint_xy": crown_relative,
                "pawn_base_proxy_available": False,
                "pawn_axis_orientation_available": False,
                "pawn_axis_orientation_missing_reason": (
                    "no_distinct_two_pass_accepted_pawn_base_point"
                ),
            }
        )
    jaw_rows = [row for row in rows if row["jaw_proxy_available"]]
    crown_rows = [row for row in rows if row["crown_proxy_available"]]
    events = episode["contact_and_motion_events"]
    contact_interval = events["candidate_contact_interval_samples"][
        "sample_indices"
    ]
    lift_interval = events["candidate_lift_interval_samples"][
        "sample_indices"
    ]
    carried_interval = events[
        "definite_carried_motion_interval_samples"
    ]["sample_indices"]
    first_crown = (
        min(row["sample_index"] for row in crown_rows)
        if crown_rows
        else None
    )
    rows_path = output_directory / "proxy_rows.json"
    atomic_write_json(
        rows_path,
        {
            "schema_version": ROWS_SCHEMA,
            "recording_id": episode["recording_id"],
            "rows": rows,
        },
    )
    summary = {
        "successful_episode_primary_streams": ["c922", "d405_rgb"],
        "successful_episode_pi_available": False,
        "jaw_proxy_row_count": len(jaw_rows),
        "accepted_crown_row_count": len(crown_rows),
        "first_accepted_crown_source_sample": first_crown,
        "pawn_base_proxy_row_count": 0,
        "pawn_axis_orientation_available": False,
        "pawn_axis_orientation_missing_reason": (
            "no_distinct_two_pass_accepted_pawn_base_point"
        ),
        "physical_first_contact_interval_samples": contact_interval,
        "physical_candidate_lift_interval_samples": lift_interval,
        "physical_definite_carry_interval_samples": carried_interval,
        "support_loss_pixel_contact_state_available": False,
        "support_loss_event_interval_proxy_samples": lift_interval,
        "simulator_first_unilateral_contact_sample": or21["result"][
            "first_unilateral_jaw_contact_source_sample"
        ],
        "simulator_first_orientation_over_5_degrees_sample": or21[
            "result"
        ]["first_orientation_over_5_degrees_source_sample"],
        "simulator_first_bilateral_contact_sample": or21["result"][
            "first_bilateral_jaw_contact_source_sample"
        ],
        "simulator_first_sustained_support_loss_sample": or21["result"][
            "first_sustained_support_loss_source_sample"
        ],
        "event_timing_correspondence": {
            "sim_contact_inside_physical_contact_interval": (
                contact_interval[0]
                <= or21["result"][
                    "first_unilateral_jaw_contact_source_sample"
                ]
                <= contact_interval[1]
            ),
            "sim_orientation_onset_inside_physical_lift_interval": (
                lift_interval[0]
                <= or21["result"][
                    "first_orientation_over_5_degrees_source_sample"
                ]
                <= lift_interval[1]
            ),
            "sim_support_loss_equals_physical_carry_start": (
                or21["result"][
                    "first_sustained_support_loss_source_sample"
                ]
                == carried_interval[0]
            ),
        },
        "metric_depth_available": False,
        "contact_force_available": False,
    }
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": (
            "PASS_BOUNDED_JAW_CROWN_EVENT_PROXY_PAWN_AXIS_INSUFFICIENT"
        ),
        "proxy_summary": summary,
        "proxy_rows_sha256": _sha256(rows_path),
        "parameter_fit_allowed": False,
        "global_mapping_approved": False,
        "task_success_claim": False,
        "transfer_claim": False,
        "authority": contract["authority"],
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


def main() -> int:
    build_retained_rgb_contact_consequence_proxies()
    return 0

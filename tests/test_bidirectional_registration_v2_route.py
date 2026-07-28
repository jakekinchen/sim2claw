from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from sim2claw.bidirectional_registration_v2_route import (
    compile_exact_route,
    evaluate_route,
    load_route,
)


ROOT = Path(__file__).resolve().parents[1]
ROUTE = (
    ROOT
    / "configs/hardware/"
    "bidirectional_pawn_push_v2_registration_route_v1.json"
)
RECOVERY_ROUTE = (
    ROOT
    / "configs/hardware/"
    "bidirectional_pawn_push_v2_registration_route_v2.json"
)
EMPIRICAL_RECOVERY_ROUTE = (
    ROOT
    / "configs/hardware/"
    "bidirectional_pawn_push_v2_registration_route_v3.json"
)


def test_v2_route_compiles_disjoint_capture_holds_and_no_authority() -> None:
    route, acquisition, _ = load_route(ROUTE)
    compiled = compile_exact_route(route, acquisition)
    assert compiled["egress"].dtype == np.dtype("<f8")
    assert compiled["main"].dtype == np.dtype("<f8")
    assert compiled["egress"].shape[1] == compiled["main"].shape[1] == 6
    assert len(compiled["capture_slices"]) == 8
    assert {
        row["target_id"] for row in compiled["capture_slices"]
    } == set(route["capture_order"])
    for item in compiled["capture_slices"]:
        hold = compiled["main"][
            item["start_index"] : item["end_index_exclusive"]
        ]
        assert len(hold) == 50
        assert np.all(hold == hold[0])
    assert not any(route["motion_contract"].values())


def test_v2_route_cpu_preview_passes_without_motion(tmp_path: Path) -> None:
    result = evaluate_route(
        route_path=ROUTE,
        output_root=tmp_path / "v02",
    )
    assert result["reviewer"]["decision"] == "CONTINUE"
    assert all(result["gates"].values())
    assert result["physical_motion_commanded"] is False
    assert result["camera_opened"] is False
    assert result["gateway_constructed"] is False
    assert result["counted_physical_attempts"] == 0
    assert result["external_clearance"]["pawns"]["distance_m"] >= 0.05
    assert result["external_clearance"]["board"]["distance_m"] >= 0.08
    assert result["visibility"]["reference_line_of_sight"]["all_passed"]
    assert {
        row["first_hit_body"]
        for row in result["visibility"]["reference_line_of_sight"]["target_rows"]
    } == {"left_moving_jaw_so101_v1"}
    receipt = json.loads(
        (tmp_path / "v02" / "evaluation.json").read_text(encoding="utf-8")
    )
    assert receipt["reviewer"]["evidence_anchor"] == 100


def test_v2_recovery_route_compiles_waypoint_egress_and_ten_holds() -> None:
    route, acquisition, _ = load_route(RECOVERY_ROUTE)
    compiled = compile_exact_route(route, acquisition)
    assert len(compiled["capture_slices"]) == 10
    assert np.array_equal(
        compiled["egress"][0],
        np.asarray(route["source_rebase"]["expected_degrees_percent"]),
    )
    assert np.array_equal(
        compiled["egress"][-1],
        np.asarray(route["source_egress"]["target_degrees_percent"]),
    )
    for waypoint in route["source_egress"]["waypoints_degrees_percent"]:
        assert np.any(
            np.all(compiled["egress"] == np.asarray(waypoint), axis=1)
        )
    for waypoint in (
        route["pre_capture_waypoints_degrees_percent"]
        + route["post_capture_waypoints_degrees_percent"]
    ):
        assert np.any(
            np.all(compiled["main"] == np.asarray(waypoint), axis=1)
        )
    assert not any(route["motion_contract"].values())


def test_v2_recovery_route_cpu_preview_passes_without_motion(
    tmp_path: Path,
) -> None:
    result = evaluate_route(
        route_path=RECOVERY_ROUTE,
        output_root=tmp_path / "v04-recovery",
    )
    assert result["reviewer"]["decision"] == "CONTINUE"
    assert all(result["gates"].values())
    assert result["physical_motion_commanded"] is False
    assert result["camera_opened"] is False
    assert result["gateway_constructed"] is False
    assert result["counted_physical_attempts"] == 0
    assert result["external_clearance"]["pawns"]["distance_m"] >= 0.05
    assert result["external_clearance"]["board"]["distance_m"] >= 0.08
    assert result["visibility"]["reference_line_of_sight"]["all_passed"]
    for row in result["visibility"]["reference_line_of_sight"]["target_rows"]:
        assert {
            endpoint["reference_name"]: endpoint["first_hit_body"]
            for endpoint in row["endpoints"]
        } == {
            "fixed_tip": "left_gripper",
            "moving_tip": "left_moving_jaw_so101_v1",
        }


def test_v3_route_binds_empirical_occlusion_family_and_height_diversity(
    tmp_path: Path,
) -> None:
    route, acquisition, _ = load_route(EMPIRICAL_RECOVERY_ROUTE)
    compiled = compile_exact_route(route, acquisition)
    assert len(compiled["capture_slices"]) == 10
    assert len(
        {
            row["physical_degrees_percent"][1]
            for split in ("fit_targets", "heldout_targets")
            for row in acquisition["split"][split]
        }
    ) == 4
    assert not any(route["motion_contract"].values())

    result = evaluate_route(
        route_path=EMPIRICAL_RECOVERY_ROUTE,
        output_root=tmp_path / "v04-recovery-v3",
    )
    assert result["reviewer"]["decision"] == "CONTINUE"
    assert all(result["gates"].values())
    assert result["empirical_visibility"]["all_passed"]
    assert result["empirical_visibility"]["positive_scorable_fit_image_count"] == 4
    assert result["target_geometry"][
        "smallest_model_midpoint_singular_value_mm"
    ] >= 5.0
    assert result["physical_motion_commanded"] is False
    assert result["camera_opened"] is False
    assert result["gateway_constructed"] is False
    assert result["counted_physical_attempts"] == 0

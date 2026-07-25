from __future__ import annotations

import json
from pathlib import Path

import pytest

from sim2claw.paths import REPO_ROOT
from sim2claw.wrist_camera_pose_grid import (
    load_contract,
    search_wrist_camera_pose_grid,
)


@pytest.fixture(scope="module")
def receipt(tmp_path_factory: pytest.TempPathFactory) -> dict:
    candidate_config = json.loads(
        (
            REPO_ROOT / "configs" / "sysid" / "recorded_action_sysid_v1.json"
        ).read_text(encoding="utf-8")
    )
    manifest: Path = tmp_path_factory.mktemp("wrist-grid") / "candidate.json"
    manifest.write_text(
        json.dumps(
            {
                "candidate_digest": "synthetic-test-candidate",
                "candidate_config": candidate_config,
                "runtime": {"camera_transform_supported": False},
            }
        ),
        encoding="utf-8",
    )
    return search_wrist_camera_pose_grid(candidate_manifest_path=manifest)


def test_contract_freezes_two_bounded_three_level_families() -> None:
    contract = load_contract()
    assert [family["name"] for family in contract["grid_families"]] == [
        "v24_local",
        "current_reframe_local",
    ]
    assert len(contract["grid_families"]) * 3**5 == 486
    assert not any(contract["authority"].values())


def test_grid_finds_action_free_collision_clean_frustum_candidate(
    receipt: dict,
) -> None:
    assert receipt["grid_candidate_count"] == 486
    assert receipt["passed_candidate_count"] > 0
    assert receipt["action_free"] is True
    assert receipt["hardware_accessed"] is False
    assert receipt["metric_calibration_used"] is False
    best = receipt["ranked_candidates"][0]
    assert best["physical_joint_vector_degrees_percent"] == pytest.approx(
        [-5.0, -100.0, 30.0, 80.0, -95.0, 3.0878859857482186]
    )
    assert best["forbidden_contact_count"] == 0
    assert best["image_edge_margins_px"]["minimum"] > 20.0
    assert best["minimum_boundary_direct_ray_visible_fraction"] >= 0.5
    assert best["minimum_forbidden_geometry_distance_m"] >= 0.0


def test_v24_local_family_does_not_claim_full_frustum(receipt: dict) -> None:
    assert receipt["grid_family_summary"]["v24_local"] == {
        "candidate_count": 243,
        "passed_count": 0,
    }
    assert receipt["verdict"][
        "grants_physical_reachability_or_camera_calibration"
    ] is False

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from sim2claw.bidirectional_registration_v2_fit import _model_jaw_midpoints


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "configs/evaluations/"
    "bidirectional_pawn_push_v2_registration_acquisition_v2.json"
)
CANDIDATE_MANIFEST = (
    ROOT
    / "runs/physical_excitation/20260725-follower-only-v1/"
    "simulation-canary-v1/candidate_manifest.json"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_recovery_contract_binds_immutable_sources_and_no_authority() -> None:
    contract = _load()
    assert (
        contract["schema_version"]
        == "sim2claw.bidirectional_pawn_push_v2_registration_acquisition.v2"
    )
    assert contract["status"] == "preregistered_before_replacement_capture_or_motion"
    for binding_id, binding in contract["sources"].items():
        path = ROOT / binding["path"]
        assert path.is_file(), binding_id
        if "sha256" in binding:
            assert _sha256(path) == binding["sha256"]
    graph = contract["sources"]["current_campaign_graph"]
    assert len(graph["outer_sha256_at_design_start"]) == 64
    assert len(graph["embedded_graph_digest_at_design_start"]) == 64
    assert contract["authority"] == {
        "camera_open": False,
        "gateway_construction": False,
        "physical_motion": False,
        "heldout_open": False,
        "counted_task_action": False,
        "task_success": False,
        "bidirectional_transfer": False,
    }


def test_recovery_split_is_new_disjoint_and_three_dimensionally_informative() -> None:
    contract = _load()
    split = contract["split"]
    fit = split["fit_targets"]
    heldout = split["heldout_targets"]
    assert split["frozen_before_capture"] is True
    assert split["acquisition_v1_target_or_heldout_reuse_forbidden"] is True
    assert len(fit) == 6
    assert len(heldout) == 4
    ids = [row["target_id"] for row in fit + heldout]
    assert len(ids) == len(set(ids))
    assert all(target_id.startswith("v2r2-") for target_id in ids)
    opaque = [row["opaque_id"] for row in heldout]
    assert len(opaque) == len(set(opaque))

    fit_values = np.asarray(
        [row["physical_degrees_percent"] for row in fit], dtype=np.float64
    )
    heldout_values = np.asarray(
        [row["physical_degrees_percent"] for row in heldout], dtype=np.float64
    )
    assert fit_values.shape == (6, 6)
    assert heldout_values.shape == (4, 6)
    assert not {tuple(row) for row in fit_values} & {
        tuple(row) for row in heldout_values
    }
    candidate = json.loads(
        CANDIDATE_MANIFEST.read_text(encoding="utf-8")
    )["candidate_config"]
    world = _model_jaw_midpoints(fit_values, candidate)
    singular_mm = np.linalg.svd(
        (world - np.mean(world, axis=0)) * 1000.0,
        compute_uv=False,
    )
    assert singular_mm[-1] >= contract["gates"][
        "minimum_fit_model_xyz_smallest_singular_value_mm"
    ]


def test_recovery_family_and_gates_are_frozen_before_capture() -> None:
    contract = _load()
    family = contract["candidate_family"]
    assert (
        family["family_id"]
        == "normalized_projective_camera_plus_planar_robot_board_rigid_v2"
    )
    assert family["per_pose_nuisance_parameters"] == 0
    assert family["joint_zero_fit_parameters"] == 0
    assert family["board_pose_fit_parameters"] == 0
    assert family["scale_fit_parameters"] == 0
    assert family["candidate_selection_after_heldout_forbidden"] is True

    gates = contract["gates"]
    assert gates["maximum_fit_task_plane_max_mm_exclusive"] == 25.0
    assert gates["maximum_heldout_task_plane_error_mm_exclusive"] == 25.0
    assert gates["maximum_heldout_reprojection_error_px"] == 8.0
    assert gates["all_heldout_targets_must_pass"] is True
    assert contract["sealing"]["heldout_open_count_maximum"] == 1
    assert contract["sealing"]["postopen_refit_forbidden"] is True
    assert contract["recapture_fallback"]["threshold_weakening_forbidden"] is True

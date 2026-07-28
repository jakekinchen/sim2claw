from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "configs/evaluations/"
    "bidirectional_pawn_push_v2_registration_acquisition_v1.json"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_v2_registration_contract_binds_sources_and_preserves_v1() -> None:
    contract = _load()
    assert (
        contract["schema_version"]
        == "sim2claw.bidirectional_pawn_push_v2_registration_acquisition.v1"
    )
    assert contract["status"] == "preregistered_before_authoritative_capture_or_motion"
    for binding in contract["sources"].values():
        path = ROOT / binding["path"]
        assert path.is_file(), path
        assert _sha256(path) == binding["sha256"]

    prior = contract["sources"]["prior_scene_registration_diagnostic"]
    assert "starting hypothesis only" in prior["use"]
    assert contract["split"]["v1_b7_heldout_reuse_forbidden"] is True
    assert contract["authority"] == {
        "registration_acquisition_preregistration": True,
        "physical_camera_observation": False,
        "physical_motion": False,
        "scene_registration": False,
        "action_compilation": False,
        "physical_attempt": False,
        "task_success": False,
        "transfer": False,
        "training": False,
    }


def test_v2_registration_split_and_camera_gates_are_prospective() -> None:
    contract = _load()
    split = contract["split"]
    fit = split["fit_targets"]
    heldout = split["heldout_targets"]
    assert split["frozen_before_capture"] is True
    assert len(fit) == 4
    assert len(heldout) == 4
    ids = [row["target_id"] for row in fit + heldout]
    assert len(ids) == len(set(ids))
    assert all("b7" not in target_id.lower() for target_id in ids)

    fit_values = np.asarray(
        [row["physical_degrees_percent"] for row in fit], dtype=np.float64
    )
    heldout_values = np.asarray(
        [row["physical_degrees_percent"] for row in heldout],
        dtype=np.float64,
    )
    assert fit_values.shape == heldout_values.shape == (4, 6)
    assert not {
        tuple(row) for row in fit_values
    } & {tuple(row) for row in heldout_values}
    assert fit_values[:, 0].tolist() == [-21.0, -11.0, -1.0, 9.0]
    assert heldout_values[:3, 0].tolist() == [-16.0, -6.0, 4.0]
    assert heldout_values[3, 1] == -90.0
    assert np.all(fit_values[:, 2] >= 96.0)
    assert np.all(heldout_values[:, 2] >= 96.0)

    camera = contract["camera_ownership"]
    assert camera["task_and_board_owner"] == "fixed_c922"
    assert camera["d405_depth_used"] is False
    assert camera["metric_depth_required"] is False
    assert contract["gripper_reference"]["annotation_protocol"][
        "blinded_to_target_id_model_projection_and_fit_result"
    ]
    assert contract["sealing"]["heldout_open_count_maximum"] == 1
    assert contract["sealing"]["postopen_refit_forbidden"] is True

    gates = contract["gates"]
    assert gates["maximum_heldout_task_plane_error_mm_exclusive"] == 25.0
    assert gates["maximum_heldout_reprojection_error_px"] == 8.0
    assert gates["all_heldout_targets_must_pass"] is True
    assert gates["maximum_annotation_midpoint_disagreement_px"] <= 4.0
    assert gates["maximum_fit_hover_reprojection_max_px"] <= 10.0


def test_v2_registration_contract_cannot_authorize_motion_or_counted_action() -> None:
    contract = _load()
    safety = contract["acquisition_safety"]
    budget = contract["operation_budget"]
    fallback = contract["recapture_fallback"]
    assert safety["v02_cpu_fp64_route_and_visibility_review_required"] is True
    assert safety["v02_reviewer_decision_required"] == "CONTINUE"
    assert safety["reviewed_gateway_only"] is True
    assert safety["torque_off_every_exit"] is True
    assert safety["robot_motion_authorized_by_this_contract"] is False
    assert budget["counted_task_actions_maximum"] == 0
    assert budget["pawn_contacts_maximum"] == 0
    assert fallback["counted_physical_attempt_consumed"] is False
    assert fallback["threshold_weakening_forbidden"] is True
    assert fallback["terminal_result"] is False

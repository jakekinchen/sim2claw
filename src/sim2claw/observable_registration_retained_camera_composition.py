"""Compose retained-camera and frozen static-joint evidence under OR13 geometry."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .observable_registration_belief_recalculation import (
    CONTRACT_PATH as OR14_CONTRACT_PATH,
    REPO_ROOT,
    _Dataset,
    _bound_json,
    _bound_path,
    _family_points,
    _load_observations,
    _project,
    _score_pixels,
    load_belief_recalculation_contract,
)
from .observable_registration_factor_isolation import _camera_from_or10
from .post_hackathon_home_workspace_geometry_camera import (
    _contact_phase_candidate,
    load_geometry_camera_contract,
)


SCHEMA = "sim2claw.observable_registration_retained_camera_composition_contract.v1"
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_retained_camera_composition_receipt.v1"
)
TRACE_SCHEMA = (
    "sim2claw.observable_registration_retained_camera_composition_trace.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "observable_registration_retained_camera_composition_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs"
    / "observable_registration_retained_camera_composition_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_retained_camera_composition_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="retained-camera composition")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    sources = contract.get("sources")
    _require(isinstance(sources, dict) and len(sources) == 6, "sources changed")
    for source_id, binding in sources.items():
        _bound_path(binding, root=root, label=source_id)
    camera = contract.get("camera_cohort_policy")
    _require(
        isinstance(camera, dict)
        and camera.get("or13_camera_mount_hash_bound_to_retained_replay")
        is False
        and camera.get("or13_camera_allowed_for_retained_replay_registration")
        is False
        and camera.get("retained_replay_camera_source")
        == "or10_same_session_pixels"
        and camera.get("camera_refit_allowed") is False,
        "camera cohort boundary widened",
    )
    candidate = contract.get("frozen_joint_candidate")
    _require(
        isinstance(candidate, dict)
        and candidate.get("family_id")
        == "shoulder_pan_lift_zero_offsets_v1"
        and candidate.get("joint_indices") == [0, 1]
        and candidate.get("refit_allowed") is False,
        "joint candidate changed",
    )
    gate = contract.get("contact_phase_gate")
    _require(
        isinstance(gate, dict)
        and gate.get("precontact_latest_sample") == 224
        and gate.get("candidate_contact_samples") == [228, 232]
        and gate.get("task_rows_allowed_in_fit") is False
        and gate.get("task_outcome_allowed_in_fit") is False
        and gate.get("physics_integration_allowed") is False
        and gate.get("dynamics_allowed") is False,
        "contact gate widened",
    )
    _require(
        not any(contract["authority"].values()), "authority widened"
    )
    _require(
        contract["promotion"]["global_mapping_approved"] is False
        and contract["promotion"]["canonical_scene_replacement_allowed"]
        is False,
        "promotion widened",
    )
    return contract


def _improvement(baseline: float, candidate: float) -> float:
    return float((baseline - candidate) / baseline)


def evaluate_retained_camera_composition(
    contract: dict[str, Any], *, root: Path = REPO_ROOT
) -> tuple[dict[str, Any], dict[str, Any]]:
    sources = contract["sources"]
    or14_receipt = _bound_json(
        sources["or14_receipt"], root=root, label="OR14 receipt"
    )
    _require(
        or14_receipt["status"]
        == "TERMINAL_NEGATIVE_NO_STABLE_STATIC_FAMILY",
        "OR14 status changed",
    )
    or11 = _bound_json(
        sources["or11_factor_receipt"], root=root, label="OR11 factor"
    )
    frozen = contract["frozen_joint_candidate"]
    prior = or11["camera_results"]["or10"]["branches"]["joint_j2"]
    _require(prior["numerically_accepted"] is True, "OR11 candidate not accepted")
    values = np.asarray(frozen["parameter_values_rad"], dtype=np.float64)
    _require(
        np.array_equal(values, np.asarray(prior["parameters"], dtype=np.float64)),
        "frozen joint values drifted",
    )
    or10 = _bound_json(
        sources["or10_receipt"], root=root, label="OR10 receipt"
    )
    or13 = _bound_json(
        sources["or13_receipt"], root=root, label="OR13 receipt"
    )
    or14_contract = load_belief_recalculation_contract(
        OR14_CONTRACT_PATH, root=root
    )
    or14_sources = or14_contract["sources"]
    manifest = _bound_json(
        or14_sources["or6_candidate"], root=root, label="OR6 candidate"
    )
    scene_path = _bound_path(
        sources["or13_scene"], root=root, label="OR13 scene"
    )
    dataset = _Dataset(
        scene_path,
        manifest["candidate_config"],
        float(or13["board_object_geometry"]["pawn_height_m"]),
    )
    observations = _load_observations(or14_contract, root=root)
    camera = _camera_from_or10(or10)
    pixel_roles: dict[str, Any] = {}
    for role, physical_key, observed_key in (
        ("fit", "fit_physical", "fit_observed"),
        (
            "known_outcome_validation",
            "validation_physical",
            "validation_observed",
        ),
    ):
        physical = observations[physical_key]
        observed = observations[observed_key]
        baseline = _score_pixels(
            _project(dataset.evaluate(physical)[0], camera), observed
        )
        candidate_points = _family_points(
            frozen["family_id"],
            values,
            dataset=dataset,
            physical=physical,
        )
        candidate_score = _score_pixels(
            _project(candidate_points, camera), observed
        )
        pixel_roles[role] = {
            "baseline": baseline,
            "candidate": candidate_score,
            "midpoint_improvement_fraction": _improvement(
                baseline["midpoint_rms_px"],
                candidate_score["midpoint_rms_px"],
            ),
            "candidate_refit": False,
            "promotion_eligible": False,
        }
    or13_contract, _ = load_geometry_camera_contract(
        _bound_path(
            sources["or13_contract"], root=root, label="OR13 contract"
        ),
        root=root,
    )
    phase, phase_trace = _contact_phase_candidate(
        contract=or13_contract,
        scene_path=scene_path,
        pawn_height_m=float(or13["board_object_geometry"]["pawn_height_m"]),
        board_thickness_m=float(
            or13["board_object_geometry"]["outside_side_m"] * 0.0
            + load_json_object(scene_path, label="OR13 scene")[
                "simulation_estimates"
            ]["board"]["thickness_m"]
        ),
        root=root,
        joint_zero_overrides={0: float(values[0]), 1: float(values[1])},
    )
    precontact_latest = int(
        contract["contact_phase_gate"]["precontact_latest_sample"]
    )
    precontact_rows = [
        row
        for row in phase_trace["rows"]
        if int(row["source_sample_index"]) <= precontact_latest
    ]
    precontact_clear = not any(
        bool(row["phase_contact_geometry_pass"]) for row in precontact_rows
    )
    static_gate_passed = bool(
        precontact_clear and phase["contact_at_expected_phase"]
    )
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": (
            "PASS_STATIC_NAMED_CONTACT_NO_DYNAMICS"
            if static_gate_passed
            else "TERMINAL_NEGATIVE_NO_PHASE_CORRECT_NAMED_CONTACT"
        ),
        "source_hashes": {
            source_id: binding["sha256"]
            for source_id, binding in sources.items()
        },
        "camera_cohort_reconciliation": {
            **contract["camera_cohort_policy"],
            "or13_camera_fit_midpoint_rms_px": or14_receipt["baseline"][
                "fit"
            ]["midpoint_rms_px"],
            "or13_camera_validation_midpoint_rms_px": or14_receipt[
                "baseline"
            ]["known_outcome_validation"]["midpoint_rms_px"],
        },
        "frozen_joint_candidate": {
            **frozen,
            "source_numerically_accepted": True,
        },
        "static_pixel_composition": pixel_roles,
        "contact_phase": {
            **phase,
            "precontact_clear_through_sample_224": precontact_clear,
            "static_gate_passed": static_gate_passed,
        },
        "actions_changed": False,
        "joint_candidate_refit": False,
        "task_rows_used_for_fit": 0,
        "task_outcome_used_for_fit": False,
        "physics_integration_steps": 0,
        "dynamic_replays": 0,
        "authority": contract["authority"],
        "promotion": contract["promotion"],
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    trace = {
        "schema_version": TRACE_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "rows": phase_trace["rows"],
    }
    return receipt, trace


def build_retained_camera_composition_receipt(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_retained_camera_composition_contract(
        contract_path, root=root
    )
    receipt, trace = evaluate_retained_camera_composition(
        contract, root=root
    )
    atomic_write_json(output_directory / "trace.json", trace)
    atomic_write_json(output_directory / "receipt.json", receipt)
    return receipt


def main() -> int:
    build_retained_camera_composition_receipt()
    return 0


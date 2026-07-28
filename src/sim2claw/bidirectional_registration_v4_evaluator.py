"""One-open evaluator for the frozen bidirectional registration v4 candidate."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from .bidirectional_scene_registration_v4 import (
    CANDIDATE_PATH,
    DATASET_PATH,
    build_registered_scene,
    load_candidate,
    physical_square_center,
    reproduce_fit,
    sha256_file,
)
from .paths import REPO_ROOT
from .wrist_view_reposition import _physical_to_model_position

CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "bidirectional_pawn_push_registration_v4_validation_v1.json"
)


class BidirectionalRegistrationEvaluationError(RuntimeError):
    pass


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_bytes())


def _resolve_input(dataset: dict[str, Any], input_id: str) -> Path:
    entry = next(item for item in dataset["inputs"] if item["id"] == input_id)
    path = REPO_ROOT / entry["path"]
    if sha256_file(path) != entry["sha256"]:
        raise BidirectionalRegistrationEvaluationError(
            f"held-out input changed: {input_id}"
        )
    return path


def _external_contact_pairs(action: np.ndarray, mapping: dict[str, Any]) -> list[dict[str, Any]]:
    mapped = _physical_to_model_position(action, mapping)
    model, data = build_registered_scene()
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        for name in mapping["bindings"]["joint_names"]
    ]
    qpos = [model.jnt_qposadr[joint_id] for joint_id in joint_ids]
    pairs: dict[tuple[str, str], dict[str, Any]] = {}
    for row_index, row in enumerate(mapped):
        data.qpos[qpos] = row
        data.qvel[:] = 0.0
        mujoco.mj_forward(model, data)
        for contact_index in range(data.ncon):
            contact = data.contact[contact_index]
            geom1 = (
                mujoco.mj_id2name(
                    model, mujoco.mjtObj.mjOBJ_GEOM, int(contact.geom1)
                )
                or f"geom_{contact.geom1}"
            )
            geom2 = (
                mujoco.mj_id2name(
                    model, mujoco.mjtObj.mjOBJ_GEOM, int(contact.geom2)
                )
                or f"geom_{contact.geom2}"
            )
            key = tuple(sorted((geom1, geom2)))
            existing = pairs.setdefault(
                key,
                {
                    "geoms": list(key),
                    "first_row": row_index,
                    "last_row": row_index,
                    "minimum_distance_m": float(contact.dist),
                },
            )
            existing["last_row"] = row_index
            existing["minimum_distance_m"] = min(
                existing["minimum_distance_m"], float(contact.dist)
            )
    return list(pairs.values())


def evaluate() -> dict[str, Any]:
    contract = _json(CONTRACT_PATH)
    if sha256_file(CANDIDATE_PATH) != contract["candidate_sha256"]:
        raise BidirectionalRegistrationEvaluationError("candidate hash changed")
    if sha256_file(DATASET_PATH) != contract["dataset_sha256"]:
        raise BidirectionalRegistrationEvaluationError("dataset hash changed")
    candidate = load_candidate()
    dataset = _json(DATASET_PATH)

    packet_path = _resolve_input(dataset, "heldout_b7_packet")
    _resolve_input(dataset, "heldout_b7_joint_samples")
    _resolve_input(dataset, "heldout_b7_c922_native")
    diagnostic_path = _resolve_input(dataset, "heldout_b7_transfer_diagnostic")
    packet = _json(packet_path)
    diagnostic = _json(diagnostic_path)

    route_path = Path(packet["route"]["path"])
    if sha256_file(route_path) != packet["route"]["sha256"]:
        raise BidirectionalRegistrationEvaluationError("held-out route hash changed")
    route = _json(route_path)
    derivation = route["geometric_derivation"]
    task_relative_offset = np.asarray(
        derivation["hover_pinch_target_world_m"], dtype=np.float64
    ) - np.asarray(derivation["piece_center_world_m"], dtype=np.float64)
    expected = physical_square_center(
        "b7", candidate
    ) + task_relative_offset
    observed = np.asarray(
        diagnostic["apex"]["actual_pinch_xyz_m"], dtype=np.float64
    )
    held_out_delta = observed - expected
    held_out_residual_mm = float(np.linalg.norm(held_out_delta) * 1000.0)

    payload = packet["stages"][0]["frozen_action_payload"]
    action_bytes = base64.b64decode(payload["base64"])
    if hashlib.sha256(action_bytes).hexdigest() != payload["sha256"]:
        raise BidirectionalRegistrationEvaluationError("held-out action hash changed")
    action = np.frombuffer(action_bytes, dtype="<f8").reshape(payload["shape"])
    mapping_path = Path(packet["candidate_manifest"]["path"])
    if sha256_file(mapping_path) != packet["candidate_manifest"]["sha256"]:
        raise BidirectionalRegistrationEvaluationError("mapping hash changed")
    mapping = _json(mapping_path)["candidate_config"]
    contacts = _external_contact_pairs(action, mapping)

    fit = reproduce_fit()
    gates = contract["gates"]
    fit_passed = fit["fit_residual_mm"] <= gates["maximum_fit_residual_mm"]
    held_out_passed = (
        held_out_residual_mm <= gates["maximum_held_out_residual_mm"]
    )
    contact_passed = not contacts
    admitted = fit_passed and held_out_passed and contact_passed
    return {
        "schema_version": "sim2claw.bidirectional_pawn_push_registration_validation_receipt.v1",
        "evaluation_id": contract["evaluation_id"],
        "status": "admitted" if admitted else "terminal_negative_f1_triggered",
        "proof_class": "zero_motion_fit_and_single_open_heldout_registration_validation",
        "candidate_sha256": contract["candidate_sha256"],
        "dataset_sha256": contract["dataset_sha256"],
        "held_out_open_count": 1,
        "fit": {
            "physical_square": "c2",
            "mapped_scene_square": fit["mapped_fit_square"],
            "residual_mm": fit["fit_residual_mm"],
            "maximum_mm": gates["maximum_fit_residual_mm"],
            "passed": fit_passed,
        },
        "held_out": {
            "physical_square": "b7",
            "mapped_scene_square": "b2",
            "apex_sample_index": diagnostic["apex"]["sample_index"],
            "expected_task_relative_pinch_xyz_m": expected.tolist(),
            "observed_actual_pinch_xyz_m": observed.tolist(),
            "observed_minus_expected_xyz_mm": (held_out_delta * 1000.0).tolist(),
            "residual_mm": held_out_residual_mm,
            "maximum_mm": gates["maximum_held_out_residual_mm"],
            "passed": held_out_passed,
        },
        "known_safe_geometry": {
            "held_out_action_sha256": payload["sha256"],
            "perfect_tracking_external_contact_pairs": contacts,
            "no_new_external_contact": contact_passed,
        },
        "admitted": admitted,
        "fallback": "none" if admitted else contract["fallback_on_failure"],
        "authority": contract["authority"],
        "claim_boundary": (
            "The fit gate passed, but the single-open independent B7 held-out "
            "correspondence failed. V4 is rejected for metric registration. "
            "F1 may reduce the prospective consequence claim before action "
            "compilation; this receipt proves no task or transfer success."
        ),
    }

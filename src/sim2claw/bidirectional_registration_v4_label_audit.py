"""Post-Q15 label-authority audit for the single-open Q03 held-out episode."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from .bidirectional_scene_registration_v4 import (
    load_candidate,
    physical_square_center,
    reproduce_fit,
)
from .paths import REPO_ROOT

CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "bidirectional_pawn_push_registration_v4_label_audit_v2.json"
)


class RegistrationLabelAuditError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_bytes())


def evaluate() -> dict[str, Any]:
    contract = _json(CONTRACT_PATH)
    if (
        contract.get("schema_version")
        != "sim2claw.bidirectional_pawn_push_registration_label_audit.v2"
    ):
        raise RegistrationLabelAuditError("unexpected label-audit schema")
    for source in contract["sealed_sources"]:
        path = REPO_ROOT / source["path"]
        if not path.is_file() or _sha256(path) != source["sha256"]:
            raise RegistrationLabelAuditError(
                f"changed sealed source: {source['path']}"
            )

    original = contract["original_evaluation"]
    original_receipt_path = REPO_ROOT / original["receipt_path"]
    if _sha256(original_receipt_path) != original["receipt_sha256"]:
        raise RegistrationLabelAuditError("original Q03 receipt changed")
    original_receipt = _json(original_receipt_path)

    sources = {row["role"]: REPO_ROOT / row["path"] for row in contract["sealed_sources"]}
    packet = _json(sources["heldout_packet"])
    route_path = Path(packet["route"]["path"])
    if _sha256(route_path) != packet["route"]["sha256"]:
        raise RegistrationLabelAuditError("held-out route changed")
    route = _json(route_path)
    derivation = route["geometric_derivation"]
    offset = np.asarray(
        derivation["hover_pinch_target_world_m"], dtype=np.float64
    ) - np.asarray(derivation["piece_center_world_m"], dtype=np.float64)
    diagnostic = _json(sources["transfer_diagnostic"])
    observed = np.asarray(
        diagnostic["apex"]["actual_pinch_xyz_m"], dtype=np.float64
    )
    candidate = load_candidate()

    counterfactuals = []
    raw_center_proximities = []
    for rank in range(1, 9):
        for file_name in "abcdefgh":
            square = f"{file_name}{rank}"
            center = physical_square_center(square, candidate)
            expected = center + offset
            delta_mm = (observed - expected) * 1000.0
            counterfactuals.append(
                {
                    "physical_square_if_assumed": square,
                    "residual_mm": float(np.linalg.norm(delta_mm)),
                    "observed_minus_expected_xyz_mm": delta_mm.tolist(),
                    "authoritative": False,
                }
            )
            raw_center_proximities.append(
                {
                    "physical_square_if_assumed": square,
                    "horizontal_distance_mm": float(
                        np.linalg.norm((observed - center)[:2]) * 1000.0
                    ),
                    "valid_heldout_score": False,
                }
            )
    counterfactuals.sort(key=lambda row: row["residual_mm"])
    raw_center_proximities.sort(key=lambda row: row["horizontal_distance_mm"])

    camera = contract["camera_adjudication"]
    if camera["camera_owned_physical_square"] is not None:
        raise RegistrationLabelAuditError(
            "contract unexpectedly supplies a camera-owned square"
        )
    correction = contract["correction"]
    if (
        correction["held_out_open_count_after_correction"] != 1
        or correction["corrected_residual_mm"] is not None
        or correction["f1_trigger_supported"] is not False
    ):
        raise RegistrationLabelAuditError("correction widened held-out authority")

    fit = reproduce_fit()
    return {
        "schema_version": "sim2claw.bidirectional_pawn_push_registration_label_audit_receipt.v2",
        "evaluation_id": contract["evaluation_id"],
        "status": correction["disposition"],
        "proof_class": "zero_motion_single_open_heldout_label_authority_audit",
        "contract_sha256": _sha256(CONTRACT_PATH),
        "original_q03": {
            "receipt_path": original["receipt_path"],
            "receipt_sha256": original["receipt_sha256"],
            "reported_physical_square": original_receipt["held_out"][
                "physical_square"
            ],
            "reported_residual_mm": original_receipt["held_out"]["residual_mm"],
            "reported_status": original_receipt["status"],
            "camera_owned": False,
            "valid_heldout_decision": False,
        },
        "fit": {
            "residual_mm": fit["fit_residual_mm"],
            "maximum_mm": contract["unchanged_gates"]["maximum_fit_residual_mm"],
            "passed": (
                fit["fit_residual_mm"]
                <= contract["unchanged_gates"]["maximum_fit_residual_mm"]
            ),
        },
        "camera_adjudication": camera,
        "corrected_heldout": {
            "physical_square": None,
            "residual_mm": None,
            "maximum_mm": contract["unchanged_gates"][
                "maximum_held_out_residual_mm"
            ],
            "passed": None,
            "held_out_open_count": correction[
                "held_out_open_count_after_correction"
            ],
        },
        "counterfactual_nearest_with_task_offset": counterfactuals[:6],
        "counterfactual_nearest_without_task_offset": raw_center_proximities[:6],
        "counterfactuals_are_not_labels_or_scores": True,
        "registration_admitted": False,
        "registration_rejected_by_heldout": False,
        "f1_trigger_supported": False,
        "new_data_opened": False,
        "new_robot_motion": False,
        "authority": contract["authority"],
        "claim_boundary": contract["claim_boundary"],
    }

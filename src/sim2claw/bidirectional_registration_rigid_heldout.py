"""Single-open heldout evaluator for the frozen V4 rigid registration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np

from .bidirectional_registration_rigid_fit import _task_plane_errors
from .bidirectional_registration_v2_fit import (
    _model_jaw_midpoints,
    project,
)
from .paths import REPO_ROOT


class RigidRegistrationHeldoutError(RuntimeError):
    """The sealed heldout protocol or frozen evaluation changed."""


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _path(entry: Mapping[str, Any]) -> Path:
    raw = Path(str(entry["path"]))
    return raw if raw.is_absolute() else REPO_ROOT / raw


def _bound_json(entry: Mapping[str, Any]) -> dict[str, Any]:
    path = _path(entry)
    payload = path.read_bytes()
    if _sha_bytes(payload) != entry["sha256"]:
        raise RigidRegistrationHeldoutError(f"bound input changed: {path}")
    return json.loads(payload)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _output_paths(contract: Mapping[str, Any]) -> dict[str, Path]:
    root = REPO_ROOT / contract["outputs"]["root"]
    return {
        name: root / filename
        for name, filename in contract["outputs"].items()
        if name != "root"
    }


def _verify_preopen_lineage(contract: Mapping[str, Any]) -> None:
    candidate = _bound_json(contract["candidate"])
    fit_receipt = _bound_json(contract["fit_receipt"])
    review = _bound_json(contract["independent_fit_review"])
    _bound_json(contract["acquisition_contract"])
    _bound_json(contract["fit_annotations"])
    _bound_json(contract["candidate_manifest"])
    joint_path = _path(contract["joint_samples"])
    if _sha(joint_path) != contract["joint_samples"]["sha256"]:
        raise RigidRegistrationHeldoutError("joint ledger changed")
    if (
        fit_receipt["candidate_sha256"] != contract["candidate"]["sha256"]
        or review["candidate_sha256"] != contract["candidate"]["sha256"]
        or review["status"] != "CONTINUE_TO_SINGLE_SEALED_HELDOUT_OPEN"
        or review["heldout_open_count"] != 0
        or review["heldout_content_read"] is not False
        or review["sealed_heldout_open_authorized"] is not True
        or not all(review["checks"].values())
        or candidate.get("fit_split_only") is False
    ):
        raise RigidRegistrationHeldoutError("fit admission lineage is invalid")


def open_all_once(contract_path: Path) -> dict[str, Any]:
    """Open the sealed manifest and each raw image once into one derived sheet."""
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    _verify_preopen_lineage(contract)
    paths = _output_paths(contract)
    if any(path.exists() for path in paths.values()):
        raise RigidRegistrationHeldoutError("heldout open/output already exists")

    manifest_path = _path(contract["sealed_manifest"])
    manifest_bytes = manifest_path.read_bytes()
    if _sha_bytes(manifest_bytes) != contract["sealed_manifest"]["sha256"]:
        raise RigidRegistrationHeldoutError("sealed manifest changed")
    manifest = json.loads(manifest_bytes)
    expected = {
        row["opaque_id"]: row for row in contract["expected_members"]
    }
    members = {
        str(row.get("opaque_id", row.get("target_id"))): row
        for row in manifest["members"]
    }
    protocol = contract["single_open_protocol"]
    if (
        len(members) != protocol["required_member_count"]
        or set(members) != set(expected)
    ):
        raise RigidRegistrationHeldoutError("sealed membership changed")

    opened = []
    images = []
    for opaque_id in expected:
        member = members[opaque_id]
        image_path = Path(str(member["image_path"]))
        image_bytes = image_path.read_bytes()
        digest = _sha_bytes(image_bytes)
        if (
            digest != member["image_sha256"]
            or len(image_bytes) != int(member["image_bytes"])
        ):
            raise RigidRegistrationHeldoutError("sealed image changed")
        image = cv2.imdecode(
            np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR
        )
        if image is None:
            raise RigidRegistrationHeldoutError("sealed image is undecodable")
        display = image.copy()
        cv2.rectangle(display, (0, 0), (display.shape[1], 34), (0, 0, 0), -1)
        cv2.putText(
            display,
            opaque_id,
            (12, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        images.append(display)
        opened.append(
            {
                "opaque_id": opaque_id,
                "target_id": expected[opaque_id]["target_id"],
                "image_path": str(image_path),
                "image_sha256": digest,
                "image_bytes": len(image_bytes),
                "capture_receipt_path": member["capture_receipt_path"],
                "capture_receipt_sha256": member["capture_receipt_sha256"],
                "raw_image_read_count": 1,
            }
        )
    if len({image.shape for image in images}) != 1:
        raise RigidRegistrationHeldoutError("sealed image shapes differ")
    sheet = np.vstack(
        (np.hstack((images[0], images[1])), np.hstack((images[2], images[3])))
    )
    paths["contact_sheet"].parent.mkdir(parents=True, exist_ok=False)
    if not cv2.imwrite(str(paths["contact_sheet"]), sheet):
        raise RigidRegistrationHeldoutError("contact sheet write failed")
    receipt = {
        "schema_version": "sim2claw.bidirectional_pawn_push_v2_registration_heldout_open_receipt.v1",
        "status": "all_four_heldouts_opened_together_once",
        "proof_class": "sealed_registration_heldout_content_open_only",
        "contract_path": str(contract_path.relative_to(REPO_ROOT)),
        "contract_sha256": _sha(contract_path),
        "sealed_manifest_sha256": _sha_bytes(manifest_bytes),
        "sealed_manifest_read_count": 1,
        "heldout_open_count": 1,
        "members": opened,
        "contact_sheet_path": str(paths["contact_sheet"].relative_to(REPO_ROOT)),
        "contact_sheet_sha256": _sha(paths["contact_sheet"]),
        "candidate_sha256": contract["candidate"]["sha256"],
        "candidate_refit": False,
        "authority": contract["authority"],
        "claim_boundary": "All four frozen registration heldouts opened once; no evaluation, promotion, task, motion, or transfer claim yet.",
    }
    _write_json(paths["open_receipt"], receipt)
    marker = {
        "schema_version": "sim2claw.bidirectional_pawn_push_v2_registration_heldout_open_marker.v1",
        "heldout_open_count": 1,
        "open_receipt_sha256": _sha(paths["open_receipt"]),
        "raw_manifest_read_count": 1,
        "raw_image_read_count_per_member": 1,
    }
    _write_json(paths["open_marker"], marker)
    return receipt


def recover_open_all_once(contract_path: Path) -> dict[str, Any]:
    """Run the versioned recovery after one recorded manifest-only failure."""
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    _verify_preopen_lineage(contract)
    failure = _bound_json(contract["prior_failed_open"])
    if (
        failure["status"] != "failed_closed_before_raw_image_access"
        or failure["cumulative_manifest_read_count"] != 1
        or failure["raw_image_read_count_total"] != 0
        or failure["heldout_pixel_content_read"] is not False
        or failure["candidate_sha256"] != contract["candidate"]["sha256"]
        or failure["threshold_update"] is not False
        or failure["candidate_refit"] is not False
    ):
        raise RigidRegistrationHeldoutError("prior failed-open evidence changed")
    paths = _output_paths(contract)
    if any(path.exists() for path in paths.values()):
        raise RigidRegistrationHeldoutError("recovery open/output already exists")

    manifest_path = _path(contract["sealed_manifest"])
    manifest_bytes = manifest_path.read_bytes()
    if _sha_bytes(manifest_bytes) != contract["sealed_manifest"]["sha256"]:
        raise RigidRegistrationHeldoutError("sealed manifest changed")
    manifest = json.loads(manifest_bytes)
    expected = {
        row["opaque_id"]: row for row in contract["expected_members"]
    }
    members = {str(row["opaque_id"]): row for row in manifest["members"]}
    schema = contract["recovery_schema"]
    required_keys = set(schema["sealed_member_keys"])
    if (
        len(members) != contract["single_open_protocol"]["required_member_count"]
        or set(members) != set(expected)
        or any(set(row) != required_keys for row in manifest["members"])
    ):
        raise RigidRegistrationHeldoutError("sealed recovery schema changed")

    opened = []
    images = []
    sealed_root = manifest_path.parent / schema["sealed_directory"]
    for opaque_id in expected:
        member = members[opaque_id]
        member_root = sealed_root / opaque_id
        image_path = member_root / schema["image_filename"]
        receipt_path = member_root / schema["capture_receipt_filename"]
        image_bytes = image_path.read_bytes()
        digest = _sha_bytes(image_bytes)
        if (
            digest != member["image_sha256"]
            or len(image_bytes) != int(member["image_bytes"])
            or _sha(receipt_path) != member["capture_receipt_sha256"]
        ):
            raise RigidRegistrationHeldoutError("recovered sealed member changed")
        image = cv2.imdecode(
            np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR
        )
        if image is None:
            raise RigidRegistrationHeldoutError("sealed image is undecodable")
        display = image.copy()
        cv2.rectangle(display, (0, 0), (display.shape[1], 34), (0, 0, 0), -1)
        cv2.putText(
            display,
            opaque_id,
            (12, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        images.append(display)
        opened.append(
            {
                "opaque_id": opaque_id,
                "target_id": expected[opaque_id]["target_id"],
                "image_path": str(image_path),
                "image_sha256": digest,
                "image_bytes": len(image_bytes),
                "capture_receipt_path": str(receipt_path),
                "capture_receipt_sha256": member[
                    "capture_receipt_sha256"
                ],
                "raw_image_read_count": 1,
            }
        )
    if len({image.shape for image in images}) != 1:
        raise RigidRegistrationHeldoutError("sealed image shapes differ")
    sheet = np.vstack(
        (np.hstack((images[0], images[1])), np.hstack((images[2], images[3])))
    )
    paths["contact_sheet"].parent.mkdir(parents=True, exist_ok=False)
    if not cv2.imwrite(str(paths["contact_sheet"]), sheet):
        raise RigidRegistrationHeldoutError("contact sheet write failed")
    receipt = {
        "schema_version": "sim2claw.bidirectional_pawn_push_v2_registration_heldout_recovery_open_receipt.v1",
        "status": "all_four_heldouts_opened_once_after_manifest_only_recovery",
        "proof_class": "versioned_recovery_sealed_registration_heldout_content_open_only",
        "contract_path": str(contract_path.relative_to(REPO_ROOT)),
        "contract_sha256": _sha(contract_path),
        "prior_failure_sha256": contract["prior_failed_open"]["sha256"],
        "sealed_manifest_sha256": _sha_bytes(manifest_bytes),
        "manifest_read_count_this_recovery": 1,
        "cumulative_manifest_read_count": 2,
        "heldout_pixel_open_count": 1,
        "members": opened,
        "contact_sheet_path": str(paths["contact_sheet"].relative_to(REPO_ROOT)),
        "contact_sheet_sha256": _sha(paths["contact_sheet"]),
        "candidate_sha256": contract["candidate"]["sha256"],
        "candidate_refit": False,
        "threshold_update": False,
        "authority": contract["authority"],
        "claim_boundary": "All four frozen registration heldout pixels opened once after one recorded manifest-only failure; no evaluation, promotion, task, motion, or transfer claim yet.",
    }
    _write_json(paths["open_receipt"], receipt)
    marker = {
        "schema_version": "sim2claw.bidirectional_pawn_push_v2_registration_heldout_recovery_open_marker.v1",
        "heldout_open_count": 1,
        "cumulative_manifest_read_count": 2,
        "open_receipt_sha256": _sha(paths["open_receipt"]),
        "raw_image_read_count_per_member": 1,
        "prior_failure_sha256": contract["prior_failed_open"]["sha256"],
    }
    _write_json(paths["open_marker"], marker)
    return receipt


def evaluate_frozen(
    contract_path: Path,
    annotation_path: Path,
) -> dict[str, Any]:
    """Score derived annotations without reopening raw heldout content."""
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    paths = _output_paths(contract)
    if paths["evaluation_receipt"].exists():
        raise RigidRegistrationHeldoutError("heldout evaluation already exists")
    marker = json.loads(paths["open_marker"].read_text(encoding="utf-8"))
    open_receipt = json.loads(paths["open_receipt"].read_text(encoding="utf-8"))
    annotations = json.loads(annotation_path.read_text(encoding="utf-8"))
    if (
        marker["heldout_open_count"] != 1
        or marker["open_receipt_sha256"] != _sha(paths["open_receipt"])
        or annotations["open_receipt_sha256"] != _sha(paths["open_receipt"])
        or annotations["contact_sheet_sha256"]
        != open_receipt["contact_sheet_sha256"]
        or annotations["candidate_sha256"] != contract["candidate"]["sha256"]
    ):
        raise RigidRegistrationHeldoutError("single-open annotation lineage changed")

    candidate = _bound_json(contract["candidate"])
    wrapper = _bound_json(contract["candidate_manifest"])
    joint_path = _path(contract["joint_samples"])
    if _sha(joint_path) != contract["joint_samples"]["sha256"]:
        raise RigidRegistrationHeldoutError("joint ledger changed")
    samples = [
        json.loads(line)
        for line in joint_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    opened = {row["opaque_id"]: row for row in open_receipt["members"]}
    annotated = {row["opaque_id"]: row for row in annotations["members"]}
    expected = [row["opaque_id"] for row in contract["expected_members"]]
    if set(opened) != set(expected) or set(annotated) != set(expected):
        raise RigidRegistrationHeldoutError("heldout annotation membership changed")

    physical = []
    observed = []
    annotation_metrics = {}
    for opaque_id in expected:
        member = opened[opaque_id]
        receipt_path = Path(member["capture_receipt_path"])
        if _sha(receipt_path) != member["capture_receipt_sha256"]:
            raise RigidRegistrationHeldoutError("heldout capture receipt changed")
        capture = json.loads(receipt_path.read_text(encoding="utf-8"))
        first = int(capture["scored_hold_first_host_continuous_ns"])
        last = int(capture["scored_hold_last_host_continuous_ns"])
        rows = [
            row["actual_physical_units"]
            for row in samples
            if first <= int(row["host_continuous_ns"]) <= last
        ]
        if len(rows) != int(capture["scored_hold_sample_count"]):
            raise RigidRegistrationHeldoutError("heldout hold samples changed")
        physical.append(np.mean(np.asarray(rows, dtype=float), axis=0))
        row = annotated[opaque_id]
        first_tips = np.asarray(row["pass_a_tip_pixels"], dtype=float)
        second_tips = np.asarray(row["pass_b_tip_pixels"], dtype=float)
        tip_delta = np.linalg.norm(first_tips - second_tips, axis=1)
        midpoint_a = np.mean(first_tips, axis=0)
        midpoint_b = np.mean(second_tips, axis=0)
        observed.append((midpoint_a + midpoint_b) / 2.0)
        annotation_metrics[opaque_id] = {
            "maximum_tip_disagreement_px": float(np.max(tip_delta)),
            "midpoint_disagreement_px": float(
                np.linalg.norm(midpoint_a - midpoint_b)
            ),
        }

    jaw_world = _model_jaw_midpoints(
        np.asarray(physical), wrapper["candidate_config"]
    )
    yaw = float(candidate["robot_board_yaw_radians"])
    translation = np.asarray(candidate["robot_board_translation_xyz_m"])
    cosine, sine = np.cos(yaw), np.sin(yaw)
    rotation = np.asarray(
        [[cosine, -sine, 0], [sine, cosine, 0], [0, 0, 1.0]]
    )
    corrected = jaw_world @ rotation.T + translation
    camera = np.asarray(candidate["camera_matrix_3x4"], dtype=float)
    observed_array = np.asarray(observed)
    projected = project(camera, corrected)
    reprojection = np.linalg.norm(projected - observed_array, axis=1)
    task_plane = _task_plane_errors(camera, observed_array, corrected)
    gates = contract["frozen_gates"]
    annotation_gate = contract["annotation_protocol"]
    rows = []
    for index, opaque_id in enumerate(expected):
        metrics = annotation_metrics[opaque_id]
        checks = {
            "annotation_tip_agreement": metrics[
                "maximum_tip_disagreement_px"
            ]
            <= annotation_gate["maximum_tip_disagreement_px"],
            "annotation_midpoint_agreement": metrics[
                "midpoint_disagreement_px"
            ]
            <= annotation_gate["maximum_midpoint_disagreement_px"],
            "reprojection": reprojection[index]
            <= gates["maximum_per_member_reprojection_error_px"],
            "task_plane": task_plane[index]
            < gates["maximum_per_member_task_plane_error_mm_exclusive"],
        }
        rows.append(
            {
                "opaque_id": opaque_id,
                "target_id": opened[opaque_id]["target_id"],
                "image_sha256": opened[opaque_id]["image_sha256"],
                "observed_midpoint_px": observed_array[index].tolist(),
                "projected_midpoint_px": projected[index].tolist(),
                "reprojection_error_px": float(reprojection[index]),
                "task_plane_error_mm": float(task_plane[index]),
                "annotation": metrics,
                "checks": {name: bool(value) for name, value in checks.items()},
                "passed": bool(all(checks.values())),
            }
        )
    aggregate = {
        "reprojection_rms_px": float(np.sqrt(np.mean(reprojection**2))),
        "reprojection_max_px": float(np.max(reprojection)),
        "task_plane_rms_mm": float(np.sqrt(np.mean(task_plane**2))),
        "task_plane_max_mm": float(np.max(task_plane)),
    }
    checks = {
        "all_four_scorable": len(rows) == 4,
        "all_four_member_gates": all(row["passed"] for row in rows),
        "aggregate_reprojection": aggregate["reprojection_rms_px"]
        <= gates["maximum_aggregate_reprojection_rms_px"],
        "aggregate_task_plane": aggregate["task_plane_rms_mm"]
        < gates["maximum_aggregate_task_plane_rms_mm_exclusive"],
        "candidate_hash_unchanged": _sha(_path(contract["candidate"]))
        == contract["candidate"]["sha256"],
        "candidate_refit_false": contract["frozen_candidate_policy"][
            "candidate_refit"
        ]
        is False,
        "heldout_open_count_one": marker["heldout_open_count"] == 1,
    }
    passed = all(checks.values())
    receipt = {
        "schema_version": "sim2claw.bidirectional_pawn_push_v2_registration_heldout_evaluation_receipt.v1",
        "status": "registration_heldout_pass" if passed else "registration_heldout_reject",
        "proof_class": "sealed_registration_heldout_evaluation_only",
        "contract_sha256": _sha(contract_path),
        "annotation_path": str(annotation_path.relative_to(REPO_ROOT)),
        "annotation_sha256": _sha(annotation_path),
        "open_receipt_sha256": _sha(paths["open_receipt"]),
        "heldout_open_count": 1,
        "candidate_sha256": contract["candidate"]["sha256"],
        "candidate_refit": False,
        "members": rows,
        "aggregate": aggregate,
        "checks": {name: bool(value) for name, value in checks.items()},
        "passed": bool(passed),
        "authority": contract["authority"],
        "claim_boundary": contract["claim_boundary"],
    }
    _write_json(paths["evaluation_receipt"], receipt)
    return receipt

#!/usr/bin/env python3
"""Evaluate the frozen J/S/K/L -> M Pi CAD-keyed mapping split.

This evaluator intentionally fails closed when the pre-M fit sources contain
no independently frozen fixed-base CAD correspondences.  AprilTags are
reported as supplementary observations only: with free rigid tag mounts, a
constant revolute-joint zero can be absorbed by the mount gauge and cannot
select identity versus Stage-D.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import mujoco
import numpy as np

from sim2claw.recorded_replay import _compile_model


CONTRACT_SCHEMA = "sim2claw.current_pi_cad_keyed_joint_mapping_contract.v1"
RESULT_SCHEMA = "sim2claw.current_pi_cad_keyed_joint_mapping_result.v1"
FIT_POSES = ("J", "S", "K", "L")
TAG_BODY = {
    0: "left_shoulder",
    1: "left_upper_arm",
    2: "left_wrist",
    3: "left_shoulder",
}
REQUIRED_VISUAL_BODIES = {
    "left_base",
    "left_shoulder",
    "left_upper_arm",
    "left_lower_arm",
    "left_wrist",
    "left_gripper",
    "left_camera_mount",
    "left_moving_jaw_so101_v1",
}


class CadMappingEvaluationError(RuntimeError):
    """Frozen lineage or evaluator semantics changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CadMappingEvaluationError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CadMappingEvaluationError(
            f"{label} is not readable JSON"
        ) from error
    _require(isinstance(value, dict), f"{label} must be a JSON object")
    return value


def _inside(root: Path, relative: str, label: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise CadMappingEvaluationError(
            f"{label} escapes the repository root"
        ) from error
    _require(path.is_file(), f"{label} is missing: {path}")
    return path


def _bound(
    root: Path, binding: dict[str, Any], label: str
) -> Path:
    relative = binding.get("path")
    expected = binding.get("sha256")
    _require(
        isinstance(relative, str)
        and isinstance(expected, str)
        and len(expected) == 64,
        f"{label} binding is incomplete",
    )
    path = _inside(root, relative, label)
    _require(sha256_file(path) == expected, f"{label} hash changed")
    return path


def validate_contract(contract: dict[str, Any]) -> None:
    _require(
        contract.get("schema_version") == CONTRACT_SCHEMA,
        "unexpected CAD-keyed mapping contract",
    )
    _require(
        contract.get("status")
        == "fit_and_fresh_validation_split_frozen_before_pose_m_execution",
        "mapping split was not frozen before M",
    )
    split = contract.get("split") or {}
    _require(
        split.get("fit_poses") == list(FIT_POSES)
        and split.get("fresh_validation_pose") == "M"
        and split.get("pose_m_observation_accessed_at_freeze") is False,
        "J/S/K/L -> M split changed",
    )
    hypotheses = contract.get("fixed_hypotheses") or {}
    _require(
        hypotheses.get("identity_joint_zero_offsets_degrees")
        == [0.0] * 5,
        "identity mapping changed",
    )
    stage_d = hypotheses.get("stage_d_joint_zero_offsets_degrees")
    _require(
        isinstance(stage_d, list)
        and len(stage_d) == 5
        and abs(float(stage_d[1]) - 18.701248448127163) < 1e-12,
        "Stage-D mapping changed",
    )
    _require(
        hypotheses.get("tag_body_map")
        == {str(key): body for key, body in TAG_BODY.items()},
        "tag body map changed",
    )
    _require(
        hypotheses["tag_body_map"]["3"] == "left_shoulder",
        "tag 3 must map to left_shoulder",
    )
    method = contract.get("fit_method") or {}
    _require(
        method.get("identifiability_fail_closed") is True
        and "per_pose_camera_refit" in (method.get("forbidden") or [])
        and "manual_pose_M_keypoints" in (method.get("forbidden") or []),
        "identifiability or held-out controls changed",
    )
    authority = contract.get("authority") or {}
    _require(
        authority.get("tag_only_promotion") is False
        and authority.get("P8_or_P13_replacement") is False
        and authority.get("physical_task") is False
        and authority.get("policy") is False,
        "mapping authority widened",
    )


def load_contract(path: Path) -> dict[str, Any]:
    contract = _json(path, "CAD-keyed mapping contract")
    validate_contract(contract)
    return contract


def detect_tags(image: np.ndarray) -> dict[int, np.ndarray]:
    dictionary = cv2.aruco.getPredefinedDictionary(
        cv2.aruco.DICT_APRILTAG_36h11
    )
    detector = cv2.aruco.ArucoDetector(
        dictionary, cv2.aruco.DetectorParameters()
    )
    corners, identifiers, _ = detector.detectMarkers(image)
    if identifiers is None:
        return {}
    found: dict[int, list[np.ndarray]] = {}
    for identifier, corner in zip(
        identifiers.ravel(), corners, strict=True
    ):
        tag_id = int(identifier)
        if tag_id in TAG_BODY:
            found.setdefault(tag_id, []).append(
                corner[0].astype(np.float64)
            )
    return {
        tag_id: rows[0]
        for tag_id, rows in found.items()
        if len(rows) == 1
    }


def hold_statistics(
    samples_path: Path, maximum_drift_degrees: float
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    try:
        with samples_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    value = json.loads(line)
                    if value.get("phase") == "capture_hold":
                        rows.append(value)
    except (OSError, json.JSONDecodeError) as error:
        raise CadMappingEvaluationError(
            f"joint samples are invalid: {samples_path}"
        ) from error
    _require(len(rows) >= 80, "capture hold has fewer than 80 samples")
    values = np.asarray(
        [
            row.get("follower_actual_position_degrees")
            for row in rows
        ],
        dtype=np.float64,
    )
    _require(
        values.shape == (len(rows), 6)
        and np.all(np.isfinite(values)),
        "capture-hold joints are malformed",
    )
    drift = np.abs(values[-1] - values[0])
    return {
        "sample_count": len(rows),
        "first_actual_degrees": values[0].tolist(),
        "last_actual_degrees": values[-1].tolist(),
        "absolute_drift_degrees": drift.tolist(),
        "maximum_absolute_drift_degrees": float(np.max(drift)),
        "gate_passed": bool(
            np.max(drift) <= float(maximum_drift_degrees)
        ),
    }


def _pose_from_paths(
    *,
    name: str,
    receipt_path: Path,
    image_path: Path,
    receipt_sha256: str,
    image_sha256: str,
    maximum_drift_degrees: float,
) -> dict[str, Any]:
    _require(
        sha256_file(receipt_path) == receipt_sha256,
        f"pose {name} receipt hash changed",
    )
    _require(
        sha256_file(image_path) == image_sha256,
        f"pose {name} image hash changed",
    )
    receipt = _json(receipt_path, f"pose {name} receipt")
    _require(
        receipt.get("status")
        == "completed_wrist_view_reposition_stage"
        and receipt.get("physical_follower_torque_enabled") is False,
        f"pose {name} is not a completed torque-off capture",
    )
    pi = receipt.get("pi_hold_still") or {}
    _require(
        pi.get("sha256") == image_sha256
        and pi.get("camera") == "imx708_wide"
        and pi.get("width") == 1536
        and pi.get("height") == 864
        and pi.get("horizontal_flip") is True
        and pi.get("vertical_flip") is True,
        f"pose {name} Pi capture identity changed",
    )
    samples_path = receipt_path.parent / "joint_samples.jsonl"
    _require(
        samples_path.is_file()
        and sha256_file(samples_path)
        == receipt.get("joint_samples_sha256"),
        f"pose {name} joint samples changed",
    )
    joints = np.asarray(
        receipt.get("final_actual_degrees"), dtype=np.float64
    )
    _require(
        joints.shape == (6,) and np.all(np.isfinite(joints)),
        f"pose {name} actual joints are invalid",
    )
    image = cv2.imread(str(image_path))
    _require(
        image is not None and image.shape[:2] == (864, 1536),
        f"pose {name} Pi image shape changed",
    )
    tags = detect_tags(image)
    return {
        "name": name,
        "receipt_path": str(receipt_path),
        "receipt_sha256": receipt_sha256,
        "pi_image_path": str(image_path),
        "pi_image_sha256": image_sha256,
        "action_sha256": receipt.get("action_sha256"),
        "final_actual_degrees": joints.tolist(),
        "hold": hold_statistics(
            samples_path, maximum_drift_degrees
        ),
        "detected_tags": {
            str(tag_id): {
                "body": TAG_BODY[tag_id],
                "corners_pixels": corners.tolist(),
                "supplementary_only": True,
            }
            for tag_id, corners in sorted(tags.items())
        },
    }


def load_fit_poses(
    root: Path, contract: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    threshold = float(contract["gates"]["hold_maximum_drift_degrees"])
    observations = contract["sources"]["fit_observations"]
    result: dict[str, dict[str, Any]] = {}
    for name in FIT_POSES:
        binding = observations[name]
        directory = (root / binding["directory"]).resolve()
        try:
            directory.relative_to(root.resolve())
        except ValueError as error:
            raise CadMappingEvaluationError(
                f"pose {name} directory escapes repository root"
            ) from error
        result[name] = _pose_from_paths(
            name=name,
            receipt_path=directory / "execution_receipt.json",
            image_path=directory / "pi_imx708_torque_on_hold.jpg",
            receipt_sha256=binding["execution_receipt_sha256"],
            image_sha256=binding["pi_imx708_sha256"],
            maximum_drift_degrees=threshold,
        )
    return result


def load_fresh_m(
    *,
    receipt_path: Path,
    image_path: Path,
    receipt_sha256: str,
    image_sha256: str,
    contract: dict[str, Any],
    packet: dict[str, Any],
) -> dict[str, Any]:
    result = _pose_from_paths(
        name="M",
        receipt_path=receipt_path,
        image_path=image_path,
        receipt_sha256=receipt_sha256,
        image_sha256=image_sha256,
        maximum_drift_degrees=float(
            contract["gates"]["hold_maximum_drift_degrees"]
        ),
    )
    frozen = contract["sources"]["fresh_validation_packet"]
    _require(
        result["action_sha256"] == frozen["action_sha256"]
        and packet.get("plan_sha256") == frozen["plan_sha256"],
        "fresh M did not consume the frozen action/plan",
    )
    return result


def inspect_full_cad(manifest: dict[str, Any]) -> dict[str, Any]:
    config = manifest.get("candidate_config")
    _require(isinstance(config, dict), "CAD manifest lacks candidate config")
    model, _ = _compile_model(config, base_directory=None)
    bodies: set[str] = set()
    geom_count = 0
    for geom_id in range(model.ngeom):
        if int(model.geom_group[geom_id]) != 2:
            continue
        body_name = mujoco.mj_id2name(
            model,
            mujoco.mjtObj.mjOBJ_BODY,
            int(model.geom_bodyid[geom_id]),
        )
        if body_name and body_name.startswith("left_"):
            bodies.add(body_name)
            geom_count += 1
    missing = sorted(REQUIRED_VISUAL_BODIES - bodies)
    inventory = {
        "left_visual_geom_count": geom_count,
        "left_visual_bodies": sorted(bodies),
        "required_visual_bodies": sorted(REQUIRED_VISUAL_BODIES),
        "missing_required_visual_bodies": missing,
        "full_so101_visual_tree_present": (
            not missing and geom_count >= 18
        ),
    }
    _require(
        inventory["full_so101_visual_tree_present"],
        "exact full SO-101 CAD is incomplete",
    )
    return inventory


def fixed_base_metric_evidence_bound(
    sources: dict[str, Any],
) -> bool:
    """Return whether the frozen split binds an independent base anchor."""
    return any(
        key in sources
        for key in (
            "fixed_base_landmarks",
            "fixed_base_edge_masks",
            "fixed_base_annotation_receipt",
        )
    )


def evaluate(
    contract_path: Path,
    *,
    fresh_m_receipt: Path,
    fresh_m_image: Path,
    fresh_m_receipt_sha256: str,
    fresh_m_image_sha256: str,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    root = (
        repository_root.resolve()
        if repository_root is not None
        else Path(__file__).resolve().parents[1]
    )
    contract = load_contract(contract_path)
    sources = contract["sources"]
    intrinsics_path = _bound(
        root, sources["intrinsics"], "Pi intrinsics"
    )
    initialization_path = _bound(
        root,
        sources["camera_and_tag_initialization_only"],
        "camera/tag initialization",
    )
    stage_d_path = _bound(
        root, sources["stage_d"], "Stage-D source"
    )
    manifest_path = _bound(
        root, sources["exact_CAD_scene"], "exact CAD scene"
    )
    route_path = _bound(
        root, sources["fresh_validation_route"], "fresh M route"
    )
    packet_path = _bound(
        root, sources["fresh_validation_packet"], "fresh M packet"
    )
    intrinsics = _json(intrinsics_path, "Pi intrinsics")
    initialization = _json(
        initialization_path, "camera/tag initialization"
    )
    stage_d = _json(stage_d_path, "Stage-D source")
    manifest = _json(manifest_path, "exact CAD scene")
    route = _json(route_path, "fresh M route")
    packet = _json(packet_path, "fresh M packet")
    _require(
        (intrinsics.get("output_resolution") or {}).get("size_px")
        == [1536, 864],
        "Pi intrinsics output mode changed",
    )
    _require(
        route.get("route_id")
        == sources["fresh_validation_route"]["route_id"]
        and (packet.get("route") or {}).get("sha256")
        == sources["fresh_validation_route"]["sha256"]
        and packet.get("plan_sha256")
        == sources["fresh_validation_packet"]["plan_sha256"],
        "fresh M route/packet identity changed",
    )
    declared_stage_d = contract["fixed_hypotheses"][
        "stage_d_joint_zero_offsets_degrees"
    ]
    source_offsets = (
        (stage_d.get("stage_d") or {}).get("parameters") or {}
    ).get("joint_zero_offsets_degrees")
    _require(
        source_offsets == declared_stage_d,
        "Stage-D source no longer matches the frozen hypothesis",
    )
    _require(
        (
            (initialization.get("tag_model") or {})
            .get("tags", {})
            .get("1", {})
            .get("body")
        )
        == "left_upper_arm",
        "tag initialization identity changed",
    )
    fit_poses = load_fit_poses(root, contract)
    cad_inventory = inspect_full_cad(manifest)

    # The frozen pre-M contract names fixed-base CAD edges/landmarks as the
    # required camera constraint, but binds no landmark coordinates, masks,
    # annotation receipt, or edge-selection receipt.  M is forbidden from
    # supplying them.  This is therefore a terminal identifiability failure,
    # not an invitation to fit those nuisance parameters after seeing M.
    fixed_base_evidence_bound = fixed_base_metric_evidence_bound(sources)
    fit_candidate = None
    fit_status = (
        "fixed_base_metric_anchor_unavailable_no_fit_candidate"
        if not fixed_base_evidence_bound
        else "fixed_base_evidence_present_but_evaluator_not_implemented"
    )

    # Open M exactly once only after the fit state above has been finalized.
    fresh_m = load_fresh_m(
        receipt_path=fresh_m_receipt,
        image_path=fresh_m_image,
        receipt_sha256=fresh_m_receipt_sha256,
        image_sha256=fresh_m_image_sha256,
        contract=contract,
        packet=packet,
    )
    heldout_status = (
        "not_scored_no_pre_m_fit_candidate"
        if fit_candidate is None
        else "score_pending"
    )
    result: dict[str, Any] = {
        "schema_version": RESULT_SCHEMA,
        "status": "identifiability_failed_no_mapping_verdict",
        "proof_class": contract["proof_class"],
        "contract": {
            "path": str(contract_path.resolve()),
            "sha256": sha256_file(contract_path),
            "commit_frozen_before_m": "a751a40",
        },
        "source_hashes_verified": True,
        "fit_poses": fit_poses,
        "fresh_validation_pose": fresh_m,
        "fresh_m_open_count": 1,
        "fit_hold_gates_all_passed": all(
            pose["hold"]["gate_passed"] for pose in fit_poses.values()
        ),
        "fresh_m_hold_gate_passed": fresh_m["hold"]["gate_passed"],
        "full_cad_inventory": cad_inventory,
        "tag_gauge": {
            "tag_3_body": "left_shoulder",
            "tag_only_absolute_joint_zero_identifiable": False,
            "tags_used_for_candidate_selection": False,
            "reason": (
                "Free tag-to-body transforms can absorb a constant joint-zero "
                "rotation. Tags are supplementary and cannot anchor the "
                "identity-versus-Stage-D comparison."
            ),
        },
        "fixed_base_identifiability": {
            "required_by_frozen_contract": True,
            "metric_evidence_bound_before_m": fixed_base_evidence_bound,
            "camera_fit_attempted": False,
            "reason": (
                "The pre-M contract binds no fixed-base CAD landmark pixels, "
                "follower-only base edge masks, or annotation/selection "
                "receipt. Fitting any from M would violate the held-out split."
            ),
        },
        "fit": {
            "status": fit_status,
            "candidate": fit_candidate,
        },
        "heldout": {
            "status": heldout_status,
            "camera_refit": False,
            "tag_mount_refit": False,
            "mask_or_keypoint_creation": False,
            "mapping_score": None,
        },
        "current_data_can_yield_defensible_mapping_candidate": False,
        "mapping_verdict": None,
        "authority": {
            "joint_mapping_rejected": False,
            "joint_mapping_promoted": False,
            "simulator_parameter_promotion": False,
            "P8_or_P13_replacement": False,
            "physical_task": False,
            "policy": False,
        },
    }
    result["result_digest"] = canonical_sha256(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--fresh-m-receipt", type=Path, required=True)
    parser.add_argument("--fresh-m-image", type=Path, required=True)
    parser.add_argument(
        "--fresh-m-receipt-sha256", required=True
    )
    parser.add_argument("--fresh-m-image-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    result = evaluate(
        arguments.contract.resolve(),
        fresh_m_receipt=arguments.fresh_m_receipt.resolve(),
        fresh_m_image=arguments.fresh_m_image.resolve(),
        fresh_m_receipt_sha256=arguments.fresh_m_receipt_sha256,
        fresh_m_image_sha256=arguments.fresh_m_image_sha256,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "mapping_verdict": result["mapping_verdict"],
                "fresh_m_open_count": result["fresh_m_open_count"],
                "output": str(arguments.output.resolve()),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

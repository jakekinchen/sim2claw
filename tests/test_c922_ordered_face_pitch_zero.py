from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np
import pytest

from sim2claw.c922_ordered_face_pitch_zero import (
    DEFAULT_CONTRACT_PATH,
    OrderedFaceRankPreflightError,
    _project,
    evaluate_c922_ordered_face_rank_preflight,
)
from sim2claw.learning_factory_artifacts import sha256_file
from sim2claw.physical_fk_frame import load_physical_fk_contract


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    contract = json.loads(DEFAULT_CONTRACT_PATH.read_text(encoding="utf-8"))
    contract_path = tmp_path / "contract.json"
    _write_json(contract_path, contract)
    intrinsics = {
        "schema_version": "sim2claw.c922_intrinsics.v1",
        "camera_matrix": [[820.0, 0.0, 640.0], [0.0, 815.0, 360.0], [0.0, 0.0, 1.0]],
        "distortion_coefficients": [0.0, 0.0, 0.0, 0.0, 0.0],
        "image_size": [1280, 720],
    }
    intrinsics_path = tmp_path / "intrinsics.json"
    _write_json(intrinsics_path, intrinsics)
    intrinsics_sha = sha256_file(intrinsics_path)
    fk_contract, model = load_physical_fk_contract()
    rows = [
        {"pose_id": row["pose_id"], "split": row["split"], "actual": np.asarray(row["settled_actual"])}
        for row in contract["candidate_poses"]
    ]
    parameters = np.array([1.47, 0.05, 0.03, 0.02, 0.14, 0.72, 0.0, 0.0, 0.0])
    pixels = _project(
        parameters,
        rows,
        model,
        fk_contract,
        contract,
        np.asarray(intrinsics["camera_matrix"]),
        np.asarray(intrinsics["distortion_coefficients"]),
    ).reshape(-1, 2)
    annotation_rows = []
    cursor = 0
    for pose in contract["candidate_poses"]:
        image_path = tmp_path / f"{pose['pose_id']}.jpg"
        image_path.write_bytes(f"fixture-{pose['pose_id']}".encode())
        image_sha = sha256_file(image_path)
        receipt = {
            "schema_version": "sim2claw.c922_ordered_link_face_pose_receipt.v1",
            "candidate_pose_id": pose["pose_id"],
            "settled_actual": pose["settled_actual"],
            "empty_gripper": True,
            "camera": {
                "role": "c922",
                "camera_fixed": True,
                "session_id": "one-session",
                "fixed_mount_token": "untouched-mount",
                "intrinsics_sha256": intrinsics_sha,
                "image_sha256": image_sha,
            },
            "gateway": {"admitted": True, "safety_clamped": False, "stalled": False},
        }
        receipt_path = tmp_path / f"{pose['pose_id']}-receipt.json"
        _write_json(receipt_path, receipt)
        faces = {}
        for face in contract["faces"]:
            faces[face["face_id"]] = pixels[cursor : cursor + 4].tolist()
            cursor += 4
        annotation_rows.append(
            {
                "pose_id": pose["pose_id"],
                "split": pose["split"],
                "image": {"path": image_path.name, "sha256": image_sha},
                "pose_receipt": {"path": receipt_path.name, "sha256": sha256_file(receipt_path)},
                "faces": faces,
            }
        )
    annotations = {
        "schema_version": "sim2claw.c922_ordered_link_face_annotations.v1",
        "intrinsics": {"path": intrinsics_path.name, "sha256": intrinsics_sha},
        "nominal_camera_from_base": {
            "rotation_vector_rad": parameters[:3].tolist(),
            "translation_m": parameters[3:6].tolist(),
        },
        "poses": annotation_rows,
    }
    annotation_path = tmp_path / "annotations.json"
    _write_json(annotation_path, annotations)
    return contract_path, annotation_path


def test_rank_preflight_is_ready_without_fitting_or_authority(tmp_path: Path) -> None:
    contract_path, annotation_path = _fixture(tmp_path)
    result = evaluate_c922_ordered_face_rank_preflight(
        annotation_path=annotation_path, contract_path=contract_path
    )
    assert result["ready_for_separately_reviewed_future_fit"] is True
    assert result["jacobian"]["rank"] == 9
    assert result["jacobian"]["sigma_min_over_sigma_max"] >= 1e-4
    assert result["held_out_used_for_rank"] is False
    assert result["fit_performed"] is False
    assert result["authority"] and not any(result["authority"].values())


def test_held_out_pose_does_not_change_rank_result(tmp_path: Path) -> None:
    contract_path, annotation_path = _fixture(tmp_path)
    first = evaluate_c922_ordered_face_rank_preflight(
        annotation_path=annotation_path, contract_path=contract_path
    )
    annotations = json.loads(annotation_path.read_text(encoding="utf-8"))
    receipt_ref = annotations["poses"][-1]["pose_receipt"]
    receipt_path = tmp_path / receipt_ref["path"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["settled_actual"][0] += 0.5
    _write_json(receipt_path, receipt)
    receipt_ref["sha256"] = sha256_file(receipt_path)
    _write_json(annotation_path, annotations)
    second = evaluate_c922_ordered_face_rank_preflight(
        annotation_path=annotation_path, contract_path=contract_path
    )
    assert first["jacobian"] == second["jacobian"]


def test_camera_mount_drift_fails_closed(tmp_path: Path) -> None:
    contract_path, annotation_path = _fixture(tmp_path)
    annotations = json.loads(annotation_path.read_text(encoding="utf-8"))
    receipt_ref = annotations["poses"][-1]["pose_receipt"]
    receipt_path = tmp_path / receipt_ref["path"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["camera"]["fixed_mount_token"] = "moved"
    _write_json(receipt_path, receipt)
    receipt_ref["sha256"] = sha256_file(receipt_path)
    _write_json(annotation_path, annotations)
    with pytest.raises(OrderedFaceRankPreflightError, match="fixed-mount token changed"):
        evaluate_c922_ordered_face_rank_preflight(
            annotation_path=annotation_path, contract_path=contract_path
        )


def test_intrinsics_placeholder_fails_closed_until_hash_bound(tmp_path: Path) -> None:
    contract_path, annotation_path = _fixture(tmp_path)
    annotations = json.loads(annotation_path.read_text(encoding="utf-8"))
    annotations["intrinsics"].pop("sha256")
    _write_json(annotation_path, annotations)
    with pytest.raises(OrderedFaceRankPreflightError, match="intrinsics sha256 is required"):
        evaluate_c922_ordered_face_rank_preflight(
            annotation_path=annotation_path, contract_path=contract_path
        )


def test_contract_freezes_requested_inventory_and_authority() -> None:
    contract = json.loads(DEFAULT_CONTRACT_PATH.read_text(encoding="utf-8"))
    assert len(contract["candidate_poses"]) == 4
    assert [row["split"] for row in contract["candidate_poses"]].count("held_out") == 1
    assert len(contract["faces"]) == 3
    assert all(len(row["ordered_points_body_xyz_m"]) == 4 for row in contract["faces"])
    assert contract["rank_preflight"]["required_jacobian_rank"] == 9
    assert contract["rank_preflight"]["minimum_sigma_min_over_sigma_max"] == 1e-4
    assert not any(contract["authority"].values())


def test_ordered_faces_are_exact_quads_from_hash_bound_visual_mesh_triangles() -> None:
    contract = json.loads(DEFAULT_CONTRACT_PATH.read_text(encoding="utf-8"))
    for face in contract["faces"]:
        source = face["source_visual_mesh"]
        path = DEFAULT_CONTRACT_PATH.parents[2] / source["path"]
        assert sha256_file(path) == source["sha256"]
        payload = path.read_bytes()
        count = struct.unpack("<I", payload[80:84])[0]
        triangles = np.frombuffer(
            payload,
            dtype=np.dtype(
                [("normal", "<f4", (3,)), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")]
            ),
            offset=84,
            count=count,
        )["vertices"].astype(np.float64)
        quaternion = np.asarray(source["mesh_to_body_quaternion_wxyz"], dtype=np.float64)
        quaternion /= np.linalg.norm(quaternion)
        w, x, y, z = quaternion
        rotation = np.array(
            [
                [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
            ]
        )
        selected = triangles[source["triangle_indices_zero_based"]]
        selected = selected @ rotation.T + np.asarray(source["mesh_to_body_position_m"])
        actual = np.unique(np.round(selected.reshape(-1, 3), 7), axis=0)
        frozen = np.unique(np.round(face["ordered_points_body_xyz_m"], 7), axis=0)
        assert np.array_equal(actual, frozen)

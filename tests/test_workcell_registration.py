from __future__ import annotations

import copy
import hashlib
import json
import math
import shutil
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from sim2claw import metric_registration_readiness as readiness
from sim2claw import workcell_registration as registration
from sim2claw.cli import main as cli_main


def _write(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pointer(path: Path, root: Path) -> dict[str, str]:
    return {
        "artifact_path": str(path.relative_to(root)),
        "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _fixture(tmp_path: Path) -> dict[str, object]:
    root = tmp_path / "repo"
    artifacts = root / "artifacts"
    evidence = root / "evidence"
    tools = root / "tools"
    evidence.mkdir(parents=True)
    tools.mkdir()
    evaluator = tools / "workcell_registration.py"
    shutil.copy2(Path(registration.__file__), evaluator)
    decoder = tools / "decoder"
    decoder.write_bytes(b"fixture-decoder")
    video = evidence / "overhead.mp4"
    video.write_bytes(b"stationary-c922-fixture")
    frame = evidence / "frame.png"
    Image.new("RGB", (640, 480), (20, 30, 40)).save(frame)
    video_sha = hashlib.sha256(video.read_bytes()).hexdigest()
    frame_sha = hashlib.sha256(frame.read_bytes()).hexdigest()
    capture = evidence / "capture.json"
    capture_sha = _write(
        capture,
        {
            "proof_class": "physical_command_replay_observation_unqualified_dual_camera",
            "promotion_authority": False,
            "training_admission": False,
            "camera_reports": [
                {
                    "id": "logitech-overhead",
                    "name": "C922 Pro Stream Webcam",
                    "role": "overhead_workspace",
                    "filter": "hflip,vflip",
                    "status": "completed_full_timestamp_coverage",
                    "sha256": video_sha,
                    "size": "640x480",
                }
            ],
        },
    )
    extraction = artifacts / "extraction.json"
    _write(
        extraction,
        {
            "schema_version": "sim2claw.frame_extraction_receipt.v1",
            "source_video_sha256": video_sha,
            "source_timestamp_seconds": 0.0,
            "decoder_identity": {
                "name": "fixture-decoder",
                "version": "1",
                "executable_path": str(decoder.relative_to(root)),
                "executable_sha256": hashlib.sha256(decoder.read_bytes()).hexdigest(),
            },
            "orientation_filter": "hflip,vflip",
            "output_frame_sha256": frame_sha,
        },
    )
    board = artifacts / "board.json"
    board_sha = _write(
        board,
        {
            "schema_version": "sim2claw.direct_board_measurement_receipt.v1",
            "measurement_method": "direct_physical_measurement",
            "playing_side_m": 0.3556,
            "standard_uncertainty_m": 0.0001,
            "measurement_tool_id": "fixture-caliper",
            "nominal_value_substituted": False,
            "synthetic": False,
        },
    )
    camera_matrix = np.asarray(
        [[610.0, 0.0, 320.0], [0.0, 608.0, 240.0], [0.0, 0.0, 1.0]]
    )
    coefficients = np.asarray([0.01, -0.005, 0.0002, -0.0001, 0.001])
    exact_mode = {
        "localized_name": "C922 Pro Stream Webcam",
        "model_id": "UVC Camera VendorID_1133 ProductID_2140",
        "unique_id": "0x8310000046d085c",
        "media_subtype": "420v",
        "format_index": 16,
        "frame_rate_range_index": 0,
        "frame_rate_fps": 30.00003000003,
        "orientation_filter": "hflip,vflip",
    }
    intrinsics = artifacts / "intrinsics.json"
    _write(
        intrinsics,
        {
            "schema_version": "sim2claw.camera_intrinsics_receipt.v1",
            "camera_id": "logitech-overhead",
            "image_size_px": [640, 480],
            "exact_mode": exact_mode,
            "camera_matrix": camera_matrix.tolist(),
            "evaluator_owned": True,
            "self_scored": False,
        },
    )
    distortion = artifacts / "distortion.json"
    _write(
        distortion,
        {
            "schema_version": "sim2claw.lens_distortion_receipt.v1",
            "camera_id": "logitech-overhead",
            "image_size_px": [640, 480],
            "exact_mode": exact_mode,
            "model": "opencv_pinhole_k1_k2_p1_p2_k3",
            "coefficients": coefficients.tolist(),
            "evaluator_owned": True,
            "self_scored": False,
        },
    )
    board_points = np.asarray(
        [
            [-0.13, 0.13, 0.0],
            [-0.05, 0.05, 0.0],
            [0.05, 0.05, 0.0],
            [0.13, 0.13, 0.0],
            [-0.13, -0.13, 0.0],
            [-0.05, -0.05, 0.0],
            [0.05, -0.05, 0.0],
            [0.13, -0.13, 0.0],
        ],
        dtype=np.float64,
    )
    rvec = np.asarray([0.12, -0.18, 0.08], dtype=np.float64)
    translation = np.asarray([0.015, -0.01, 0.82], dtype=np.float64)
    rotation, _ = cv2.Rodrigues(rvec)
    pixels, _ = cv2.projectPoints(
        board_points, rvec, translation, camera_matrix, coefficients
    )
    correspondences = []
    for index, (point, pixel) in enumerate(
        zip(board_points, pixels.reshape(-1, 2), strict=True)
    ):
        quadrant = (
            ("north" if point[1] > 0 else "south")
            + "_"
            + ("east" if point[0] > 0 else "west")
        )
        correspondences.append(
            {
                "point_id": f"point-{index}",
                "board_xy_m": point[:2].tolist(),
                "board_quadrant": quadrant,
                "source_frame_sha256": frame_sha,
                "synthetic": False,
                "annotations": [
                    {
                        "annotator_id": "annotator-a",
                        "pixel_xy": (pixel + [0.03, -0.02]).tolist(),
                    },
                    {
                        "annotator_id": "annotator-b",
                        "pixel_xy": (pixel + [-0.03, 0.02]).tolist(),
                    },
                ],
            }
        )
    manifest = {
        "schema_version": readiness.INPUT_SCHEMA,
        "input_id": "stationary-workcell-registration-fixture",
        "physical_source": {
            "observation_id": "fixture",
            "capture_receipt_path": str(capture.relative_to(root)),
            "capture_receipt_sha256": capture_sha,
            "overhead_video_path": str(video.relative_to(root)),
            "overhead_video_sha256": video_sha,
            "source_frame_path": str(frame.relative_to(root)),
            "source_frame_sha256": frame_sha,
            "source_frame_size_px": [640, 480],
            "frame_extraction_receipt": _pointer(extraction, root),
            "camera_id": "logitech-overhead",
            "camera_name": "C922 Pro Stream Webcam",
            "camera_role": "overhead_workspace",
            "capture_orientation_filter": "hflip,vflip",
            "proof_class": "physical_command_replay_observation_unqualified_dual_camera",
            "exact_mode": exact_mode,
        },
        "metric_measurements": {
            "board_playing_side": _pointer(board, root),
            "camera_intrinsics_receipt": _pointer(intrinsics, root),
            "lens_distortion_receipt": _pointer(distortion, root),
            "board_correspondences": correspondences,
            "board_fit_evaluation": None,
            "object_keypoint_observations": [],
            "overhead_camera_to_workcell_transform": None,
            "wrist_camera_extrinsics": None,
        },
        "authority": {
            "nominal_board_size_is_measurement": False,
            "proposal_homography_is_metric_calibration": False,
            "synthetic_values_allowed": False,
            "training_rows_authorized": 0,
            "promotion_authority": False,
            "physical_motion_authority": False,
            "task_success_verified": False,
        },
    }
    manifest_path = root / "manifest.json"
    _write(manifest_path, manifest)
    notes = evidence / "survey-notes.txt"
    notes.write_text("fixture-only independently reviewed survey notes")
    angle = math.radians(25.0)
    workcell_from_board = np.asarray(
        [
            [math.cos(angle), -math.sin(angle), 0.0, 0.12],
            [math.sin(angle), math.cos(angle), 0.0, -0.04],
            [0.0, 0.0, 1.0, 0.03],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )
    survey = {
        "schema_version": registration.SURVEY_SCHEMA,
        "status": "independently_reviewed_physical_survey",
        "workspace_pose_id": registration.WORKSPACE_POSE_ID,
        "board_pose_id": registration.BOARD_POSE_ID,
        "board_measurement_sha256": board_sha,
        "frame_convention": {
            "origin": "physical_board_center",
            "physical_a1_marker": "red-dot",
            "physical_h1_marker": "blue-dot",
            "physical_a8_marker": "green-dot",
            "positive_x": "a1_to_h1",
            "positive_y": "a1_to_a8_robotward",
            "positive_z": "table_normal_upward",
            "handedness": "right_handed",
        },
        "transform_direction": "board_to_workcell",
        "board_to_workcell_transform_4x4": workcell_from_board.tolist(),
        "measurement": {
            "method": "surveyed_board_center_and_directed_axes",
            "tool_id": "fixture-survey-tool",
            "operator": "operator-a",
            "measured_at": "2026-07-24T12:00:00-05:00",
            "translation_uncertainty_95_m": 0.0005,
            "rotation_uncertainty_95_degrees": 0.2,
        },
        "independent_review": {
            "reviewer": "reviewer-b",
            "decision": "accepted",
            "reviewed_at": "2026-07-24T12:30:00-05:00",
        },
        "evidence_attachments": [
            {
                "kind": "measurement_notes",
                "path": str(notes.relative_to(root)),
                "sha256": hashlib.sha256(notes.read_bytes()).hexdigest(),
            }
        ],
        "nominal_values_substituted": False,
        "synthetic": False,
        "self_scored": False,
        "evaluator_owned": False,
        "physical_authority": False,
    }
    survey_path = root / "survey.json"
    _write(survey_path, survey)
    camera_from_board = np.eye(4)
    camera_from_board[:3, :3] = rotation
    camera_from_board[:3, 3] = translation
    return {
        "root": root,
        "manifest": manifest,
        "manifest_path": manifest_path,
        "survey": survey,
        "survey_path": survey_path,
        "evaluator": evaluator,
        "expected_workcell_from_camera": workcell_from_board
        @ np.linalg.inv(camera_from_board),
    }


def test_worksheet_is_incomplete_and_non_authoritative(tmp_path: Path) -> None:
    result = registration.write_survey_worksheet(tmp_path / "worksheet.json")
    assert result["status"] == "incomplete_operator_worksheet"
    assert result["board_to_workcell_transform_4x4"] is None
    assert result["synthetic"] is None
    assert result["evaluator_owned"] is False
    assert result["physical_authority"] is False


def test_cli_writes_only_the_non_authoritative_worksheet(tmp_path: Path) -> None:
    path = tmp_path / "survey-worksheet.json"
    assert (
        cli_main(
            [
                "workcell-registration",
                "--phase",
                "worksheet",
                "--output",
                str(path),
            ]
        )
        == 0
    )
    assert json.loads(path.read_text())["status"] == "incomplete_operator_worksheet"


def test_known_transform_recovery_composition_and_sealing(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    manifest_before = Path(fixture["manifest_path"]).read_bytes()
    result = registration.evaluate_stationary_registration(
        survey_path=Path(fixture["survey_path"]),
        manifest_path=Path(fixture["manifest_path"]),
        output_directory=Path(fixture["root"]) / "outputs/registration",
        repo_root=Path(fixture["root"]),
        evaluator_path=Path(fixture["evaluator"]),
    )
    receipt = json.loads(Path(result["transform_receipt_path"]).read_text())
    assert np.allclose(
        receipt["transform_4x4"],
        fixture["expected_workcell_from_camera"],
        atol=2e-3,
    )
    assert receipt["transform_convention"]["matrix_direction"] == "workcell_from_camera"
    assert receipt["assignment_digest"]
    assert receipt["translation_uncertainty_95_m"] > 0.0
    assert receipt["rotation_uncertainty_95_degrees"] > 0.0
    assert receipt["evaluator_owned"] is True
    assert receipt["self_scored"] is False
    assert result["metric_readiness_verdict"] == "measurement_prerequisites_missing"
    assert set(result["remaining_prerequisites"]) == {
        "metric_object_keypoints_with_uncertainty",
        "wrist_camera_extrinsics",
    }
    assert Path(fixture["manifest_path"]).read_bytes() == manifest_before


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda survey: survey.update(workspace_pose_id="wrong-workspace"),
            "workspace or board identity",
        ),
        (
            lambda survey: survey["frame_convention"].update(physical_h1_marker=None),
            "a1, h1, and a8",
        ),
        (
            lambda survey: survey["frame_convention"].update(handedness="left_handed"),
            "axes are ambiguous",
        ),
        (
            lambda survey: survey.update(nominal_values_substituted=True),
            "nominal, synthetic",
        ),
        (
            lambda survey: survey.update(self_scored=True),
            "nominal, synthetic",
        ),
        (
            lambda survey: survey["independent_review"].update(reviewer="operator-a"),
            "independent accepting review",
        ),
    ],
)
def test_survey_rejections(tmp_path: Path, mutation, message: str) -> None:
    fixture = _fixture(tmp_path)
    survey = copy.deepcopy(fixture["survey"])
    mutation(survey)
    path = Path(fixture["root"]) / "mutated-survey.json"
    _write(path, survey)
    with pytest.raises(registration.WorkcellRegistrationError, match=message):
        registration.evaluate_stationary_registration(
            survey_path=path,
            manifest_path=Path(fixture["manifest_path"]),
            output_directory=Path(fixture["root"]) / "outputs/rejected",
            repo_root=Path(fixture["root"]),
            evaluator_path=Path(fixture["evaluator"]),
        )


def test_mirror_transform_and_hash_drift_rejected(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    survey = copy.deepcopy(fixture["survey"])
    survey["board_to_workcell_transform_4x4"][0][0] *= -1.0
    survey["board_to_workcell_transform_4x4"][1][0] *= -1.0
    path = Path(fixture["root"]) / "mirror.json"
    _write(path, survey)
    with pytest.raises(registration.WorkcellRegistrationError, match="not rigid"):
        registration.evaluate_stationary_registration(
            survey_path=path,
            manifest_path=Path(fixture["manifest_path"]),
            output_directory=Path(fixture["root"]) / "outputs/mirror",
            repo_root=Path(fixture["root"]),
            evaluator_path=Path(fixture["evaluator"]),
        )
    notes = Path(fixture["root"]) / fixture["survey"]["evidence_attachments"][0]["path"]
    notes.write_text("tampered")
    with pytest.raises(registration.WorkcellRegistrationError, match="attachment hash"):
        registration.evaluate_stationary_registration(
            survey_path=Path(fixture["survey_path"]),
            manifest_path=Path(fixture["manifest_path"]),
            output_directory=Path(fixture["root"]) / "outputs/hash-drift",
            repo_root=Path(fixture["root"]),
            evaluator_path=Path(fixture["evaluator"]),
        )


def test_stationary_frame_exact_mode_mismatch_rejected(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    manifest = copy.deepcopy(fixture["manifest"])
    manifest["physical_source"]["exact_mode"]["format_index"] = 15
    path = Path(fixture["root"]) / "wrong-mode.json"
    _write(path, manifest)
    with pytest.raises(registration.WorkcellRegistrationError, match="exact C922 mode"):
        registration.evaluate_stationary_registration(
            survey_path=Path(fixture["survey_path"]),
            manifest_path=path,
            output_directory=Path(fixture["root"]) / "outputs/wrong-mode",
            repo_root=Path(fixture["root"]),
            evaluator_path=Path(fixture["evaluator"]),
        )
